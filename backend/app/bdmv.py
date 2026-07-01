"""Detect Blu-ray (BDMV) disc folders and convert their main titles to MP4.

A BDMV folder (``<disc>/BDMV/STREAM/*.m2ts``) can't be played directly, so we
transcode its substantial titles (skipping menus/trailers by size) to H.264/AAC
MP4 saved next to the disc — which the scanner then picks up as normal videos.
Uses the same hardware encoder as playback when configured. Progress is exposed
like the scan status so the UI can show a bar.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal
from .models import Library
from .probe import ffmpeg_bin, probe_duration
from .transcode import _hw_env, _video_encode

_MIN_TITLE_BYTES = 200 * 1024 * 1024          # skip menus/trailers (< 200 MB)
_OUTPUT_EXTS = {".mp4", ".mkv", ".m4v", ".webm", ".mov"}

_lock = threading.Lock()
_status: dict = {
    "running": False,
    "phase": "idle",
    "current": None,
    "done": 0,
    "total": 0,
    "percent": 0,
    "errors": [],
    "finished": None,
}


def convert_status() -> dict:
    return dict(_status)


def _safe_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def _already_converted(disc: Path) -> bool:
    """A playable video sitting next to the BDMV folder = already done."""
    try:
        return any(f.is_file() and f.suffix.lower() in _OUTPUT_EXTS for f in disc.iterdir())
    except OSError:
        return False


def _titles(disc: Path) -> list[Path]:
    """Substantial .m2ts titles in a disc's STREAM folder (largest first)."""
    stream = disc / "BDMV" / "STREAM"
    try:
        items = [f for f in stream.iterdir() if f.is_file() and f.suffix.lower() == ".m2ts"]
    except OSError:
        return []
    big = [f for f in items if _safe_size(f) >= _MIN_TITLE_BYTES]
    return sorted(big, key=lambda f: -_safe_size(f))


def _library_roots() -> list[Path]:
    with SessionLocal() as db:
        return [Path(p) for (p,) in db.execute(select(Library.path)).all()]


def find_discs() -> list[dict]:
    """BDMV disc folders across all libraries that still need converting."""
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
            titles = _titles(disc)
            if titles:
                discs.append({"path": str(disc), "name": disc.name, "titles": len(titles)})
    return sorted(discs, key=lambda d: d["name"])


def _out_path(disc: Path, index: int, multi: bool) -> Path:
    stem = f"{disc.name} - {index:02d}" if multi else disc.name
    return disc / f"{stem}.mp4"


def _convert_one(src: Path, out: Path) -> bool:
    duration = probe_duration(src) or 0
    in_flags, vf, venc = _video_encode()
    env = _hw_env() if in_flags else None
    tmp = out.with_suffix(".tmp.mp4")
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", *in_flags, "-i", str(src),
           "-map", "0:v:0", "-map", "0:a:0?", *vf, *venc, "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(tmp)]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
        assert proc.stdout is not None
        for line in proc.stdout:
            # ffmpeg's out_time_ms is actually microseconds
            if line.startswith("out_time_ms=") and duration > 0:
                try:
                    secs = int(line.split("=", 1)[1]) / 1_000_000
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
    """Convert every substantial title of every un-converted BDMV disc, then rescan."""
    if not _lock.acquire(blocking=False):
        return {"skipped": "conversion already running"}
    try:
        jobs: list[tuple[Path, Path]] = []
        for d in find_discs():
            disc = Path(d["path"])
            titles = _titles(disc)
            multi = len(titles) > 1
            for i, m in enumerate(titles, 1):
                out = _out_path(disc, i, multi)
                if not out.exists():
                    jobs.append((m, out))

        _status.update({
            "running": True, "phase": "converting", "current": None,
            "done": 0, "total": len(jobs), "percent": 0, "errors": [], "finished": None,
        })
        for src, out in jobs:
            _status["current"] = out.name
            _status["percent"] = 0
            if not _convert_one(src, out):
                _status["errors"].append({"disc": out.parent.name, "error": f"failed: {src.name}"})
            _status["done"] += 1
    finally:
        _status.update({"running": False, "phase": "idle", "current": None, "finished": time.time()})
        _lock.release()

    from .scanner.service import run_scan  # pick up the new files
    run_scan()
    return {"converted": _status["done"], "errors": _status["errors"]}
