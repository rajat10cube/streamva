"""Prepare non-native videos for browser playback.

Two paths, chosen per file by probing its codecs:

* Already browser-friendly (H.264 8-bit video + AAC/MP3 audio) — remux (``-c
  copy``) once into a complete, faststart MP4 cached on disk, served with
  HTTP-range requests (seekable, correct duration).
* Anything else (MPEG-2, HEVC, 10-bit, PCM/AC3/DTS/FLAC…) — transcode to H.264
  8-bit + AAC and **stream it live** so playback starts immediately.

The video transcode uses Intel Quick Sync (VAAPI or QSV via ``/dev/dri``) when
``STREAMVA_HWACCEL`` is set and actually works on the box; otherwise it falls
back to software (libx264). Only the *video* is hardware-encoded; audio and
copy-only files never touch the GPU.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from starlette.responses import Response

from .config import get_settings
from .covers import cover_token

logger = logging.getLogger("streamva.transcode")

_MP4_AUDIO_OK = {"aac", "mp3"}
_H264_8BIT = {"yuv420p", "yuvj420p", "nv12", ""}  # "" = probe unknown, assume 8-bit
_SW_VIDEO = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]


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


def _stream_plan(src: Path) -> tuple[bool, bool]:
    """Return (video_is_copyable, audio_is_copyable)."""
    v = _probe(src, "v:0", "codec_name,pix_fmt")
    vcodec = v[0] if len(v) >= 1 else ""
    vpix = v[1] if len(v) >= 2 else ""
    acodec = (_probe(src, "a:0", "codec_name") or [""])[0]
    return (vcodec == "h264" and vpix in _H264_8BIT), (acodec in _MP4_AUDIO_OK)


# --- hardware (Intel Quick Sync) video encoding -----------------------------

def _hw_env() -> dict[str, str]:
    """ffmpeg environment for HW: force the Intel iHD VA driver (libva otherwise
    guesses a non-existent 'xe' driver on Meteor Lake and fails to init)."""
    env = dict(os.environ)
    env.setdefault("LIBVA_DRIVER_NAME", "iHD")
    return env


def _hw_args(mode: str, dev: str) -> tuple[list[str], list[str], list[str]] | None:
    """(input_flags, video_filter, video_encoder) for HW encode, or None."""
    if mode == "vaapi":
        return (["-vaapi_device", dev],
                ["-vf", "format=nv12,hwupload"],
                ["-c:v", "h264_vaapi", "-qp", "24"])
    if mode == "qsv":
        return (["-init_hw_device", f"qsv=hw:{dev}", "-filter_hw_device", "hw"],
                ["-vf", "format=nv12,hwupload=extra_hw_frames=64"],
                ["-c:v", "h264_qsv", "-global_quality", "24"])
    return None


@lru_cache(maxsize=4)
def _hwaccel_functional(mode: str, dev: str) -> bool:
    """Probe once whether HW encoding actually works (device + driver present)."""
    hw = _hw_args(mode, dev)
    if hw is None:
        return False
    in_flags, vf, venc = hw
    test = ["ffmpeg", "-hide_banner", "-loglevel", "error", *in_flags,
            "-f", "lavfi", "-i", "color=c=black:s=128x128:d=0.2:r=5",
            *vf, *venc, "-f", "null", "-"]
    try:
        ok = subprocess.run(test, capture_output=True, timeout=30, env=_hw_env()).returncode == 0
    except (subprocess.SubprocessError, OSError):
        ok = False
    if not ok:
        logger.warning("hwaccel %s not functional (device=%s) — using software transcode", mode, dev)
    return ok


def _video_encode() -> tuple[list[str], list[str], list[str]]:
    s = get_settings()
    if s.hwaccel != "none" and _hwaccel_functional(s.hwaccel, s.hwaccel_device):
        return _hw_args(s.hwaccel, s.hwaccel_device)  # type: ignore[return-value]
    return [], [], _SW_VIDEO


# --- serving ----------------------------------------------------------------

def serve_remuxed(src: Path, cache: Path) -> Response:
    if not ffmpeg_available():
        raise HTTPException(503, "ffmpeg is not available")
    video_copy, audio_copy = _stream_plan(src)
    if video_copy and audio_copy:
        if not cache.is_file() and not _copy_to_file(src, cache):
            raise HTTPException(500, "Could not prepare this video for playback")
        return FileResponse(cache, media_type="video/mp4")
    return _transcode_stream(src, video_copy, audio_copy)


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


def _transcode_stream(src: Path, video_copy: bool, audio_copy: bool) -> StreamingResponse:
    env = None
    if video_copy:
        in_flags, vf, venc = [], [], ["-c:v", "copy"]
    else:
        in_flags, vf, venc = _video_encode()
        if in_flags:  # hardware encode -> force the iHD VA driver
            env = _hw_env()
    aenc = ["-c:a", "copy"] if audio_copy else ["-c:a", "aac", "-b:a", "192k"]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", *in_flags, "-i", str(src),
           "-map", "0:v:0", "-map", "0:a:0?", *vf, *venc, *aenc,
           "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)

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
