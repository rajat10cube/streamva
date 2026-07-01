"""Detect Blu-ray (BDMV) disc folders and convert their main titles to MP4.

Playlist-aware (a mini-MakeMKV): we parse ``BDMV/PLAYLIST/*.mpls`` to find the
real titles — the longest playlists, with seamless-branched ``.m2ts`` segments
joined in order — and drop "play-all" supersets and short menus/trailers. Each
selected title is transcoded to H.264/AAC MP4 next to the disc (hardware-encoded
when configured), then the scanner picks it up. Discs without usable playlists
fall back to a size heuristic (biggest ``.m2ts``).
"""

from __future__ import annotations

import struct
import subprocess
import threading
import time
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal
from .models import Library
from .probe import ffmpeg_bin, probe_duration
from .transcode import _hw_env, _video_encode

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

def _already_converted(disc: Path) -> bool:
    try:
        return any(f.is_file() and f.suffix.lower() in _OUTPUT_EXTS for f in disc.iterdir())
    except OSError:
        return False


def _library_roots() -> list[Path]:
    with SessionLocal() as db:
        return [Path(p) for (p,) in db.execute(select(Library.path)).all()]


def find_discs() -> list[dict]:
    discs: list[dict] = []
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
            if _already_converted(disc):
                continue
            titles = _disc_titles(disc)
            if titles:
                discs.append({"path": str(disc), "name": disc.name, "titles": len(titles)})
    return sorted(discs, key=lambda d: d["name"])


# --- conversion --------------------------------------------------------------

def _out_path(disc: Path, index: int, multi: bool) -> Path:
    stem = f"{disc.name} - {index:02d}" if multi else disc.name
    return disc / f"{stem}.mp4"


def _convert_one(clips: list[Path], out: Path, duration: float) -> bool:
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
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.startswith("out_time_ms=") and duration > 0:
                try:
                    secs = int(line.split("=", 1)[1]) / 1_000_000  # out_time_ms is microseconds
                    _status["percent"] = max(0, min(99, int(secs / duration * 100)))
                except ValueError:
                    pass
        proc.wait()
    except (subprocess.SubprocessError, OSError):
        tmp.unlink(missing_ok=True)
        return False
    if proc.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(out)
        _status["percent"] = 100
        return True
    tmp.unlink(missing_ok=True)
    return False


def convert_all() -> dict:
    if not _lock.acquire(blocking=False):
        return {"skipped": "conversion already running"}
    try:
        jobs: list[tuple[list[Path], float, Path]] = []
        for d in find_discs():
            disc = Path(d["path"])
            titles = _disc_titles(disc)
            multi = len(titles) > 1
            for i, t in enumerate(titles, 1):
                out = _out_path(disc, i, multi)
                if not out.exists():
                    jobs.append((t["clips"], t["duration"], out))

        _status.update({"running": True, "phase": "converting", "current": None,
                        "done": 0, "total": len(jobs), "percent": 0, "errors": [], "finished": None})
        for clips, duration, out in jobs:
            _status["current"] = out.name
            _status["percent"] = 0
            if not _convert_one(clips, out, duration):
                _status["errors"].append({"disc": out.parent.name, "error": f"failed: {out.name}"})
            _status["done"] += 1
    finally:
        _status.update({"running": False, "phase": "idle", "current": None, "finished": time.time()})
        _lock.release()

    from .scanner.service import run_scan
    run_scan()
    return {"converted": _status["done"], "errors": _status["errors"]}
