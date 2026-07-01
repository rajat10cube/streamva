"""Detect Blu-ray (BDMV) disc folders and convert their main titles to MP4.

Playlist-aware (a mini-MakeMKV): we parse ``BDMV/PLAYLIST/*.mpls`` to find the
real titles — the longest playlists, with seamless-branched ``.m2ts`` segments
joined in order — and drop "play-all" supersets and short menus/trailers. Each
selected title is transcoded to H.264/AAC MP4 next to the disc (hardware-encoded
when configured), then the scanner picks it up. Discs without usable playlists
fall back to a size heuristic (biggest ``.m2ts``).
"""

from __future__ import annotations

import logging
import os
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal
from .models import Library
from .probe import ffmpeg_bin, probe_duration
from .transcode import _hw_env, _video_encode

logger = logging.getLogger("streamva.bdmv")

_MIN_DURATION_SEC = 120                        # skip menus/short extras (playlist path)
_MIN_TITLE_BYTES = 200 * 1024 * 1024           # fallback when no playlists
_OUTPUT_EXTS = {".mp4", ".mkv", ".m4v", ".webm", ".mov"}

_lock = threading.Lock()
_status: dict = {
    "running": False, "phase": "idle", "current": None,
    "done": 0, "total": 0, "percent": 0, "errors": [], "finished": None,
}


def convert_status() -> dict:
    return dict(_status)


def _safe_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


# --- .mpls playlist parsing --------------------------------------------------

def _parse_mpls(path: Path) -> dict | None:
    """Return {'clips': [clip_id, …], 'duration': seconds} for a playlist file."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 12 or data[:4] != b"MPLS":
        return None
    try:
        p = int.from_bytes(data[8:12], "big")            # PlayList section offset
        num_items = int.from_bytes(data[p + 6:p + 8], "big")
        q = p + 10                                        # first PlayItem
        clips: list[str] = []
        ticks = 0
        for _ in range(num_items):
            length = int.from_bytes(data[q:q + 2], "big")
            d = data[q + 2:q + 2 + length]
            if len(d) < 20:
                return None
            clips.append(d[0:5].decode("ascii", "ignore"))
            in_t = int.from_bytes(d[12:16], "big")
            out_t = int.from_bytes(d[16:20], "big")
            ticks += max(0, out_t - in_t)
            q += 2 + length
    except (IndexError, ValueError):
        return None
    return {"clips": clips, "duration": ticks / 45000.0}  # BD time base = 45 kHz


def _disc_titles(disc: Path) -> list[dict]:
    """Selected titles for a disc: [{'name', 'clips': [Path], 'duration'}]."""
    stream = disc / "BDMV" / "STREAM"
    playlist = disc / "BDMV" / "PLAYLIST"

    def m2ts(clip_id: str) -> Path | None:
        f = stream / f"{clip_id}.m2ts"
        return f if f.is_file() else None

    parsed: list[dict] = []
    try:
        mpls_files = sorted(playlist.glob("*.mpls"))
    except OSError:
        mpls_files = []
    for mp in mpls_files:
        pl = _parse_mpls(mp)
        if not pl or pl["duration"] < _MIN_DURATION_SEC:
            continue
        paths = [m2ts(c) for c in pl["clips"]]
        if not paths or any(p is None for p in paths):
            continue
        parsed.append({"name": mp.stem, "clips": paths, "duration": pl["duration"],
                       "set": frozenset(pl["clips"])})

    if parsed:
        # drop "play-all" playlists whose clip set is a proper superset of another
        sets = [t["set"] for t in parsed]
        keep = [t for i, t in enumerate(parsed)
                if not any(sets[j] < sets[i] for j in range(len(parsed)) if j != i)]
        # collapse identical clip sets (keep the longest)
        best: dict = {}
        for t in sorted(keep, key=lambda x: -x["duration"]):
            best.setdefault(t["set"], t)
        return sorted(best.values(), key=lambda x: x["name"])

    # fallback: no usable playlists -> substantial .m2ts as individual titles
    try:
        big = [f for f in stream.iterdir()
               if f.is_file() and f.suffix.lower() == ".m2ts" and _safe_size(f) >= _MIN_TITLE_BYTES]
    except OSError:
        big = []
    return [{"name": f.stem, "clips": [f], "duration": probe_duration(f) or 0.0}
            for f in sorted(big, key=lambda f: f.name)]


# --- detection ---------------------------------------------------------------

def _library_roots() -> list[Path]:
    with SessionLocal() as db:
        return [Path(p) for (p,) in db.execute(select(Library.path)).all()]


def _all_titles() -> list[dict]:
    """Every title across all libraries, with its output path and converted flag."""
    items: list[dict] = []
    seen: set[Path] = set()
    for root in _library_roots():
        if not root.is_dir():
            continue
        try:
            bdmvs = list(root.rglob("BDMV"))
        except OSError:
            continue
        for bdmv in bdmvs:
            disc = bdmv.parent
            if disc in seen or not bdmv.is_dir():
                continue
            seen.add(disc)
            titles = _disc_titles(disc)
            multi = len(titles) > 1
            for i, t in enumerate(titles, 1):
                out = _out_path(disc, i, multi)
                items.append({
                    "out": out, "clips": t["clips"], "duration": t["duration"],
                    "disc_path": str(disc), "disc": disc.name,
                    "label": out.name, "segments": len(t["clips"]),
                    "converted": out.exists(),
                })
    return items


def _all_jobs() -> list[dict]:
    return [t for t in _all_titles() if not t["converted"]]


def find_discs() -> list[dict]:
    """All titles grouped by disc (converted ones flagged), for the UI."""
    by_disc: dict[str, dict] = {}
    for t in _all_titles():
        d = by_disc.setdefault(t["disc_path"], {"path": t["disc_path"], "name": t["disc"], "titles": []})
        d["titles"].append({
            "id": str(t["out"]), "label": t["label"],
            "durationSec": round(t["duration"]), "segments": t["segments"],
            "converted": t["converted"],
        })
    return sorted(by_disc.values(), key=lambda d: d["name"])


def delete_outputs(targets: list[str]) -> int:
    """Delete converted MP4 outputs (only known, already-converted title paths)."""
    valid = {str(t["out"]) for t in _all_titles() if t["converted"]}
    deleted = 0
    for tgt in targets:
        if tgt not in valid:
            continue
        try:
            Path(tgt).unlink()
            deleted += 1
            logger.info("bdmv: deleted %s", tgt)
        except OSError as e:
            logger.error("bdmv: could not delete %s: %s", tgt, e)
    if deleted:
        from .scanner.service import run_scan
        run_scan()  # drop the removed videos from the library
    return deleted


# --- conversion --------------------------------------------------------------

def _out_path(disc: Path, index: int, multi: bool) -> Path:
    stem = f"{disc.name} - {index:02d}" if multi else disc.name
    return disc / f"{stem}.mp4"


def _convert_one(clips: list[Path], out: Path, duration: float) -> str | None:
    """Convert one title. Returns None on success, else a short error message."""
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return f"cannot create output folder ({e.strerror or e})"
    if not os.access(out.parent, os.W_OK):
        return "library is read-only — remount it read-write to save the MP4"

    if len(clips) == 1:
        input_args = ["-i", str(clips[0])]
    else:  # seamless-branched: byte-concat the MPEG-TS segments
        input_args = ["-i", "concat:" + "|".join(str(c) for c in clips)]
    in_flags, vf, venc = _video_encode()
    env = _hw_env() if in_flags else None
    tmp = out.with_suffix(".tmp.mp4")
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", *in_flags, *input_args,
           "-map", "0:v:0", "-map", "0:a:0?", *vf, *venc, "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(tmp)]
    logger.info("bdmv: converting %s (%d segment(s)) -> %s", out.stem, len(clips), out)
    try:
        with tempfile.TemporaryFile() as errf:  # capture stderr without deadlocking the progress pipe
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf, text=True, env=env)
            assert proc.stdout is not None
            for line in proc.stdout:
                if line.startswith("out_time_ms=") and duration > 0:
                    try:
                        secs = int(line.split("=", 1)[1]) / 1_000_000  # out_time_ms is microseconds
                        _status["percent"] = max(0, min(99, int(secs / duration * 100)))
                    except ValueError:
                        pass
            proc.wait()
            if proc.returncode != 0:
                errf.seek(0)
                tail = errf.read()[-1500:].decode("utf-8", "replace").strip()
                logger.error("bdmv: ffmpeg rc=%s for %s\n%s", proc.returncode, out, tail)
                tmp.unlink(missing_ok=True)
                last = tail.splitlines()[-1] if tail else ""
                return f"ffmpeg failed (rc={proc.returncode}){': ' + last if last else ''}"
    except (subprocess.SubprocessError, OSError) as e:
        tmp.unlink(missing_ok=True)
        return f"ffmpeg could not run ({e})"
    if not (tmp.exists() and tmp.stat().st_size > 0):
        tmp.unlink(missing_ok=True)
        return "no output was produced"
    try:
        tmp.replace(out)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        return f"could not save output ({e.strerror or e})"
    _status["percent"] = 100
    logger.info("bdmv: wrote %s", out)
    return None


def convert_all(targets: list[str] | None = None) -> dict:
    """Convert the given titles (by id/output path), or all un-converted titles."""
    if not _lock.acquire(blocking=False):
        return {"skipped": "conversion already running"}
    try:
        jobs = _all_jobs()
        if targets:
            want = set(targets)
            jobs = [j for j in jobs if str(j["out"]) in want]

        _status.update({"running": True, "phase": "converting", "current": None,
                        "done": 0, "total": len(jobs), "percent": 0, "errors": [], "finished": None})
        for j in jobs:
            _status["current"] = j["label"]
            _status["percent"] = 0
            err = _convert_one(j["clips"], j["out"], j["duration"])
            if err:
                _status["errors"].append({"disc": j["disc"], "title": j["label"], "error": err})
            _status["done"] += 1
    finally:
        _status.update({"running": False, "phase": "idle", "current": None, "finished": time.time()})
        _lock.release()

    from .scanner.service import run_scan
    run_scan()
    succeeded = _status["done"] - len(_status["errors"])
    return {"converted": succeeded, "failed": len(_status["errors"]), "errors": _status["errors"]}
