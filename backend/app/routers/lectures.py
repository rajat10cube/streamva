"""Lecture metadata, media streaming, subtitles, and next-lecture lookup."""

from __future__ import annotations

import mimetypes
import os
import re
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access import can_access_course
from ..auth import require_user
from ..covers import uploaded_subtitle_path
from ..db import get_db
from ..models import Course, Lecture, Library, User
from ..paths import library_root, safe_media_path
from ..probe import audio_tracks, ffmpeg_bin
from ..transcode import audio_variant_path, remux_cache_path, serve_audio_variant, serve_remuxed

router = APIRouter(prefix="/lectures", tags=["lectures"])

_TS_RE = re.compile(r"(\d\d:\d\d:\d\d),(\d{3})")
_SUB_MAX_BYTES = 5 * 1024 * 1024


def _resolve(db: Session, lecture_id: int, user: User) -> tuple[Lecture, "Course", object]:
    lec = db.get(Lecture, lecture_id)
    if lec is None:
        raise HTTPException(404, "Lecture not found")
    course = db.get(Course, lec.course_id)
    if course is None or not can_access_course(db, user, course):
        raise HTTPException(404, "Lecture not found")
    root = library_root(db, course)
    if root is None:
        raise HTTPException(404, "Library not available")
    return lec, course, root


def srt_to_vtt(text: str) -> str:
    return "WEBVTT\n\n" + _TS_RE.sub(r"\1.\2", text)


def _ffmpeg_to_vtt(raw: bytes, ext: str) -> str | None:
    """Convert an .ass/.ssa/.sub subtitle to WebVTT via ffmpeg (styling is dropped)."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / f"in{ext}"
        dst = Path(td) / "out.vtt"
        src.write_bytes(raw)
        try:
            r = subprocess.run([ffmpeg_bin(), "-y", "-i", str(src), str(dst)],
                               capture_output=True, timeout=60)
        except (subprocess.SubprocessError, OSError):
            return None
        if r.returncode == 0 and dst.is_file():
            return dst.read_text(encoding="utf-8", errors="ignore")
    return None


def _to_vtt(raw: bytes, filename: str) -> str | None:
    """Normalize an uploaded subtitle to WebVTT text (None if unsupported)."""
    ext = Path(filename).suffix.lower()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    if ext == ".vtt":
        return text if text.lstrip().startswith("WEBVTT") else "WEBVTT\n\n" + text
    if ext in (".srt", ".txt", ""):
        return srt_to_vtt(text)
    if ext in (".ass", ".ssa", ".sub"):
        return _ffmpeg_to_vtt(raw, ext)
    return None


@router.get("/{lecture_id}")
def get_lecture(
    lecture_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict:
    lec, course, _ = _resolve(db, lecture_id, user)
    lib = db.get(Library, course.library_id) if course.library_id else None
    has_sub = lec.subtitle_path is not None or (
        lib is not None and uploaded_subtitle_path(lib.path, lec.path).is_file()
    )
    return {
        "id": lec.id,
        "title": lec.title,
        "kind": lec.kind,
        "needsTranscode": lec.needs_transcode,
        "hasSubtitle": has_sub,
        "durationSec": lec.duration_sec,
        "courseSlug": course.slug,
        "stream": f"/api/lectures/{lec.id}/stream",
    }


@router.get("/{lecture_id}/audio-tracks")
def audio_track_list(
    lecture_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> list[dict]:
    lec, _course, root = _resolve(db, lecture_id, user)
    path = safe_media_path(root, lec.path)
    return audio_tracks(path) if path is not None else []


@router.get("/{lecture_id}/stream")
def stream(
    lecture_id: int,
    audio: int | None = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    lec, course, root = _resolve(db, lecture_id, user)
    path = safe_media_path(root, lec.path)
    if path is None:
        raise HTTPException(404, "File not found")
    # a specific (non-default) audio track -> serve a cached single-audio variant
    if audio is not None and audio > 0:
        lib = db.get(Library, course.library_id) if course.library_id else None
        if lib is None:
            raise HTTPException(404, "Library not available")
        return serve_audio_variant(path, audio_variant_path(lib.path, lec.path, audio), audio)
    ctype = lec.mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    # FileResponse streams the file efficiently and handles HTTP Range (seeking)
    # natively, plus ETag/Last-Modified caching — far better than a hand-rolled
    # generator for large media.
    return FileResponse(path, media_type=ctype)


@router.get("/{lecture_id}/remux")
def remux(lecture_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    lec, course, root = _resolve(db, lecture_id, user)
    path = safe_media_path(root, lec.path)
    if path is None:
        raise HTTPException(404, "File not found")
    lib = db.get(Library, course.library_id) if course.library_id else None
    if lib is None:
        raise HTTPException(404, "Library not available")
    # compatible files -> cached seekable MP4; the rest -> live transcode stream
    return serve_remuxed(path, remux_cache_path(lib.path, lec.path))


@router.get("/{lecture_id}/subtitle")
def subtitle(lecture_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    lec, course, root = _resolve(db, lecture_id, user)
    lib = db.get(Library, course.library_id) if course.library_id else None
    if lib is not None:  # a user-uploaded subtitle wins over any sidecar
        up = uploaded_subtitle_path(lib.path, lec.path)
        if up.is_file():
            return Response(up.read_text(encoding="utf-8", errors="ignore"), media_type="text/vtt")
    if lec.subtitle_path:
        path = safe_media_path(root, lec.subtitle_path)
        if path is not None:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if path.suffix.lower() != ".vtt":
                text = srt_to_vtt(text)
            return Response(text, media_type="text/vtt")
    raise HTTPException(404, "No subtitle")


@router.post("/{lecture_id}/subtitle")
async def upload_subtitle(
    lecture_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    lec, course, _root = _resolve(db, lecture_id, user)
    lib = db.get(Library, course.library_id) if course.library_id else None
    if lib is None:
        raise HTTPException(404, "Library not available")
    raw = await file.read()
    if len(raw) > _SUB_MAX_BYTES:
        raise HTTPException(413, "Subtitle file too large")
    vtt = _to_vtt(raw, file.filename or "")
    if not vtt:
        raise HTTPException(400, "Unsupported or unreadable subtitle file (use .srt, .vtt, or .ass)")
    out = uploaded_subtitle_path(lib.path, lec.path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(vtt, encoding="utf-8")
    return {"ok": True}


@router.delete("/{lecture_id}/subtitle")
def delete_subtitle(
    lecture_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict:
    lec, course, _root = _resolve(db, lecture_id, user)
    lib = db.get(Library, course.library_id) if course.library_id else None
    if lib is not None:
        uploaded_subtitle_path(lib.path, lec.path).unlink(missing_ok=True)
    return {"ok": True}


@router.get("/{lecture_id}/next")
def next_lecture(
    lecture_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict:
    lec, _course, _root = _resolve(db, lecture_id, user)
    nxt = db.scalar(
        select(Lecture)
        .where(Lecture.course_id == lec.course_id, Lecture.position > lec.position)
        .order_by(Lecture.position)
        .limit(1)
    )
    return {"next": {"id": nxt.id, "title": nxt.title} if nxt else None}
