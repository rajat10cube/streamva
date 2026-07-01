"""Prepare non-native videos for browser playback.

Two paths, chosen per file by probing its codecs:

* Already browser-friendly (H.264 8-bit video + AAC/MP3 audio) — remux (``-c
  copy``) once into a complete, faststart MP4 cached on disk, served with
  HTTP-range requests (seekable, correct duration).
* Anything else (MPEG-2, HEVC, 10-bit, PCM/AC3/DTS/FLAC…) — transcode to H.264
  8-bit + AAC and **stream it live** so playback starts immediately instead of
  waiting for the whole file. Live transcodes aren't seekable and the timeline
  is approximate, but they play. (Software transcode must keep up with real time
  — fine for SD/MPEG-2, needs hardware accel for HD HEVC.)
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from starlette.responses import Response

from .config import get_settings
from .covers import cover_token

logger = logging.getLogger("streamva.transcode")

# What a browser can play inside MP4 without re-encoding.
_MP4_AUDIO_OK = {"aac", "mp3"}
_H264_8BIT = {"yuv420p", "yuvj420p", "nv12", ""}  # "" = probe unknown, assume 8-bit


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def remux_dir() -> Path:
    return get_settings().data_dir / "remux"


def remux_cache_path(lib_path: str, lecture_rel: str) -> Path:
    return remux_dir() / f"{cover_token(lib_path, lecture_rel)}.mp4"


def _probe(path: Path, stream: str, entries: str) -> list[str]:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", stream,
             "-show_entries", f"stream={entries}", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    return [ln.strip() for ln in out.stdout.strip().splitlines()]


def _stream_plan(src: Path) -> tuple[list[str], list[str], bool]:
    """Return (video_args, audio_args, both_streams_copyable)."""
    v = _probe(src, "v:0", "codec_name,pix_fmt")
    vcodec = v[0] if len(v) >= 1 else ""
    vpix = v[1] if len(v) >= 2 else ""
    a = _probe(src, "a:0", "codec_name")
    acodec = a[0] if a else ""

    video_copy = vcodec == "h264" and vpix in _H264_8BIT
    audio_copy = acodec in _MP4_AUDIO_OK
    va = (["-c:v", "copy"] if video_copy
          else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"])
    aa = (["-c:a", "copy"] if audio_copy else ["-c:a", "aac", "-b:a", "192k"])
    return va, aa, (video_copy and audio_copy)


def serve_remuxed(src: Path, cache: Path) -> Response:
    """Serve a browser-playable version of ``src`` (cached copy or live transcode)."""
    if not ffmpeg_available():
        raise HTTPException(503, "ffmpeg is not available")
    va, aa, both_copy = _stream_plan(src)
    if both_copy:
        if not cache.is_file() and not _copy_to_file(src, cache):
            raise HTTPException(500, "Could not prepare this video for playback")
        return FileResponse(cache, media_type="video/mp4")
    return _transcode_stream(src, va, aa)


def _copy_to_file(src: Path, out: Path) -> bool:
    """Stream-copy into a complete, seekable faststart MP4."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.mp4")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
           "-movflags", "+faststart", str(tmp)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=3600)
    except (subprocess.SubprocessError, OSError) as e:
        logger.error("remux copy failed to start for %s: %r", src, e)
        tmp.unlink(missing_ok=True)
        return False
    if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(out)
        _evict_cache()
        return True
    logger.error("remux copy failed (rc=%s) for %s: %s", r.returncode, src,
                 (r.stderr or b"").decode("utf-8", "replace")[-1000:])
    tmp.unlink(missing_ok=True)
    return False


def _transcode_stream(src: Path, va: list[str], aa: list[str]) -> StreamingResponse:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src),
           "-map", "0:v:0", "-map", "0:a:0?", *va, *aa,
           "-movflags", "frag_keyframe+empty_moov+default_base_moof",
           "-f", "mp4", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def gen():
        try:
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            if proc.stdout:
                proc.stdout.close()
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    return StreamingResponse(gen(), media_type="video/mp4")


def _evict_cache() -> None:
    """Delete least-recently-used remuxes to keep the cache under the size cap."""
    cap = get_settings().remux_cache_mb * 1024 * 1024
    try:
        files = sorted(remux_dir().glob("*.mp4"), key=lambda p: p.stat().st_mtime)
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
