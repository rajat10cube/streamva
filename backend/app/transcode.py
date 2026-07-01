"""On-the-fly ffmpeg remux for non-native containers (Decision A, tier 3).

Confirmed against the real libraries: `.mkv`/`.ts` are H.264/AAC, so a stream
*copy* into fragmented MP4 is enough — no re-encode, no GPU.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import StreamingResponse


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def remux_response(path: Path) -> StreamingResponse:
    if not ffmpeg_available():
        raise HTTPException(503, "ffmpeg is not available for remuxing")

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(path),
        "-map", "0:v:0?", "-map", "0:a:0?",   # video + audio only (skip subs/data)
        "-c", "copy",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4", "pipe:1",
    ]
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
