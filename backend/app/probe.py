"""ffprobe/ffmpeg helpers for media duration + thumbnails (best-effort, optional)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .config import get_settings


def ffmpeg_bin() -> str:
    return get_settings().ffmpeg_path or "ffmpeg"


def ffprobe_bin() -> str:
    return get_settings().ffprobe_path or "ffprobe"


def ffprobe_available() -> bool:
    return shutil.which(ffprobe_bin()) is not None


def ffmpeg_available() -> bool:
    return shutil.which(ffmpeg_bin()) is not None


def generate_cover(video: Path, out: Path, at: float = 15.0) -> bool:
    """Extract a single frame ~``at`` seconds into ``video`` as a JPEG cover."""
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [ffmpeg_bin(), "-y", "-ss", str(at), "-i", str(video),
             "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", str(out)],
            capture_output=True, timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return out.exists() and out.stat().st_size > 0


def generate_previews(
    video: Path, out_dir: Path, token: str, count: int, duration: float | None
) -> int:
    """Extract ``count`` frames evenly spread across ``video`` for a hover preview.

    Frames are written as ``{token}_{i}.jpg`` (0-indexed). Uses fast input seeking
    (``-ss`` before ``-i``) so long videos don't get fully decoded. Returns how
    many frames were produced.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{token}_*.jpg"):  # clear stale frames for this item
        try:
            old.unlink()
        except OSError:
            pass
    dur = duration if (duration and duration > 2) else None
    made = 0
    for i in range(count):
        # spread across the middle ~90% of the video (skip intro/outro edges)
        at = dur * (0.05 + 0.9 * (i + 0.5) / count) if dur else 5.0 + i * 10.0
        out = out_dir / f"{token}_{i}.jpg"
        try:
            subprocess.run(
                [ffmpeg_bin(), "-y", "-ss", f"{at:.2f}", "-i", str(video),
                 "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "5", str(out)],
                capture_output=True, timeout=60,
            )
        except (subprocess.SubprocessError, OSError):
            continue
        if out.exists() and out.stat().st_size > 0:
            made += 1
    return made


def audio_tracks(path: Path) -> list[dict]:
    """List audio streams as [{index (audio-relative), language, title, channels}]."""
    try:
        out = subprocess.run(
            [ffprobe_bin(), "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=channels:stream_tags=language,title", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(out.stdout or "{}")
    except (subprocess.SubprocessError, OSError, ValueError):
        return []
    tracks = []
    for i, s in enumerate(data.get("streams") or []):
        tags = s.get("tags") or {}
        tracks.append({
            "index": i,
            "language": tags.get("language"),
            "title": tags.get("title"),
            "channels": s.get("channels"),
        })
    return tracks


# Image-based subtitle codecs need OCR to become text — we can't extract these to
# WebVTT, so they're skipped (they still occupy a subtitle-stream index).
IMAGE_SUB_CODECS = {"hdmv_pgs_subtitle", "pgssub", "dvd_subtitle", "dvbsub", "dvb_subtitle", "xsub"}


def subtitle_tracks(path: Path) -> list[dict]:
    """List embedded subtitle streams as [{idx (subtitle-relative), codec, language, title}].

    ``idx`` is the position among subtitle streams, i.e. the ``N`` in ffmpeg's
    ``-map 0:s:N`` (image-based tracks are included so indices stay correct).
    """
    try:
        out = subprocess.run(
            [ffprobe_bin(), "-v", "error", "-select_streams", "s",
             "-show_entries", "stream=codec_name:stream_tags=language,title", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(out.stdout or "{}")
    except (subprocess.SubprocessError, OSError, ValueError):
        return []
    tracks = []
    for i, s in enumerate(data.get("streams") or []):
        tags = s.get("tags") or {}
        tracks.append({
            "idx": i,
            "codec": s.get("codec_name"),
            "language": tags.get("language"),
            "title": tags.get("title"),
        })
    return tracks


def extract_subtitle(video: Path, out: Path, idx: int) -> bool:
    """Extract text-based subtitle stream ``idx`` (subtitle-relative) to WebVTT."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.vtt")
    try:
        r = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(video), "-map", f"0:s:{idx}", "-f", "webvtt", str(tmp)],
            capture_output=True, timeout=180,
        )
    except (subprocess.SubprocessError, OSError):
        tmp.unlink(missing_ok=True)
        return False
    if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(out)
        return True
    tmp.unlink(missing_ok=True)
    return False


def probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    value = out.stdout.strip()
    try:
        d = float(value)
        return d if d > 0 else None
    except ValueError:
        return None
