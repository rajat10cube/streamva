"""Prepare non-native videos (.mkv/.avi/.flv) for browser playback.

We remux/transcode each file once into a complete, faststart MP4 cached on disk,
then serve that with normal HTTP-range requests — so it's seekable and reports
the correct duration (unlike a live fragmented stream). Streams the browser can
already decode are stream-copied; the rest are transcoded (video -> H.264 8-bit,
audio -> AAC). The cache is bounded by ``STREAMVA_REMUX_CACHE_MB`` (LRU).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import get_settings
from .covers import cover_token

# Codecs a browser can play inside MP4 without transcoding.
_MP4_VIDEO_OK = {"h264"}
_MP4_AUDIO_OK = {"aac", "mp3"}


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def remux_dir() -> Path:
    return get_settings().data_dir / "remux"


def remux_cache_path(lib_path: str, lecture_rel: str) -> Path:
    return remux_dir() / f"{cover_token(lib_path, lecture_rel)}.mp4"


def _probe_stream_codec(path: Path, stream: str) -> str:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", stream,
             "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    lines = out.stdout.strip().splitlines()
    return lines[0].strip() if lines else ""


def build_playable_mp4(src: Path, out: Path) -> bool:
    """Produce a seekable, browser-playable MP4 at ``out``. Returns success.

    Stream-copies H.264 video and AAC/MP3 audio; transcodes anything else so
    even HEVC/AC3/DTS/FLAC files play (video forced to 8-bit yuv420p for browser
    compatibility). Slow on first play for transcodes, then cached.
    """
    if not ffmpeg_available():
        return False
    out.parent.mkdir(parents=True, exist_ok=True)

    vcodec = _probe_stream_codec(src, "v:0")
    acodec = _probe_stream_codec(src, "a:0")
    v = (["-c:v", "copy"] if vcodec in _MP4_VIDEO_OK
         else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"])
    a = (["-c:a", "copy"] if acodec in _MP4_AUDIO_OK
         else ["-c:a", "aac", "-b:a", "192k"])

    tmp = out.with_suffix(".tmp.mp4")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
           *v, *a, "-movflags", "+faststart", str(tmp)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=7200)
    except (subprocess.SubprocessError, OSError):
        tmp.unlink(missing_ok=True)
        return False
    if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(out)
        _evict_cache()
        return True
    tmp.unlink(missing_ok=True)
    return False


def _evict_cache() -> None:
    """Delete least-recently-used remuxes to keep the cache under the size cap."""
    cap = get_settings().remux_cache_mb * 1024 * 1024
    d = remux_dir()
    try:
        files = sorted(d.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    sized = []
    total = 0
    for f in files:
        try:
            s = f.stat().st_size
        except OSError:
            s = 0
        sized.append((f, s))
        total += s
    for f, s in sized:
        if total <= cap:
            break
        try:
            f.unlink()
            total -= s
        except OSError:
            pass
