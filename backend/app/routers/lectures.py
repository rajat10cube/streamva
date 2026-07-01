"""Lecture metadata, media streaming, subtitles, and next-lecture lookup."""

from __future__ import annotations

import mimetypes
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access import can_access_course
from ..auth import require_user
from ..db import get_db
from ..models import Course, Lecture, User
from ..paths import library_root, safe_media_path
from ..transcode import remux_response

router = APIRouter(prefix="/lectures", tags=["lectures"])

_TS_RE = re.compile(r"(\d\d:\d\d:\d\d),(\d{3})")


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


@router.get("/{lecture_id}")
def get_lecture(
    lecture_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict:
    lec, course, _ = _resolve(db, lecture_id, user)
    return {
        "id": lec.id,
        "title": lec.title,
        "kind": lec.kind,
        "needsTranscode": lec.needs_transcode,
        "hasSubtitle": lec.subtitle_path is not None,
        "durationSec": lec.duration_sec,
        "courseSlug": course.slug,
        "stream": f"/api/lectures/{lec.id}/stream",
    }


@router.get("/{lecture_id}/stream")
def stream(lecture_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    lec, _course, root = _resolve(db, lecture_id, user)
    path = safe_media_path(root, lec.path)
    if path is None:
        raise HTTPException(404, "File not found")
    ctype = lec.mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    # FileResponse streams the file efficiently and handles HTTP Range (seeking)
    # natively, plus ETag/Last-Modified caching — far better than a hand-rolled
    # generator for large media.
    return FileResponse(path, media_type=ctype)


@router.get("/{lecture_id}/remux")
def remux(lecture_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    lec, _course, root = _resolve(db, lecture_id, user)
    path = safe_media_path(root, lec.path)
    if path is None:
        raise HTTPException(404, "File not found")
    return remux_response(path)


@router.get("/{lecture_id}/subtitle")
def subtitle(lecture_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    lec, _course, root = _resolve(db, lecture_id, user)
    if not lec.subtitle_path:
        raise HTTPException(404, "No subtitle")
    path = safe_media_path(root, lec.subtitle_path)
    if path is None:
        raise HTTPException(404, "Subtitle not found")
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() != ".vtt":
        text = srt_to_vtt(text)
    return Response(text, media_type="text/vtt")


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
