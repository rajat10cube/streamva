"""Course library + detail endpoints (with progress)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..access import accessible_library_ids, can_access_course
from ..auth import require_user
from ..covers import PREVIEW_COUNT, cover_path, cover_token, preview_path, uploaded_subtitle_path
from ..db import get_db
from ..models import Attachment, Course, Lecture, Library, Progress, Section, User
from .lectures import embedded_subtitle_list

router = APIRouter(prefix="/courses", tags=["courses"])

_NATIVE_VIDEO = {".mp4", ".m4v", ".webm", ".mov"}


def _playback(lec: Lecture) -> str:
    """How the client should play this lecture (see Decision A)."""
    if lec.kind == "document":
        return "document"
    if lec.kind == "audio":
        return "native"
    ext = os.path.splitext(lec.path)[1].lower()
    if ext in _NATIVE_VIDEO:
        return "native"
    if ext == ".ts":
        return "mpegts"
    return "remux"  # mkv/avi/... -> server remux (Phase 4)


def _cover_url(c: Course, lib_path: str | None) -> str | None:
    if c.cover_path:
        return f"/api/media/cover/{c.slug}"
    # generated thumbnail: include a location-derived token so the browser drops
    # its cache if the course at this slug ever changes identity.
    if lib_path and cover_path(lib_path, c.path).is_file():
        return f"/api/media/cover/{c.slug}?v={cover_token(lib_path, c.path)}"
    return None


def _preview_urls(c: Course, lib_path: str | None) -> list[str]:
    """Hover-preview frame URLs (empty if none were generated for this item)."""
    if not lib_path or not preview_path(lib_path, c.path, 0).is_file():
        return []
    token = cover_token(lib_path, c.path)
    return [
        f"/api/media/preview/{c.slug}/{i}?v={token}"
        for i in range(PREVIEW_COUNT)
        if preview_path(lib_path, c.path, i).is_file()
    ]


@router.get("")
def list_courses(user: User = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    q = select(Course).where(Course.missing.is_(False))
    allowed = accessible_library_ids(db, user)
    if allowed is not None:
        q = q.where(Course.library_id.in_(allowed))
    rows = db.scalars(q.order_by(Course.position, Course.title)).all()
    lib_rows = db.execute(select(Library.id, Library.name, Library.path)).all()
    lib_paths = {i: p for i, _n, p in lib_rows}
    lib_names = {i: (n or Path(p).name) for i, n, p in lib_rows}

    completed_map = dict(
        db.execute(
            select(Lecture.course_id, func.count())
            .join(Progress, Progress.lecture_id == Lecture.id)
            .where(Progress.completed.is_(True), Progress.user_id == user.id)
            .group_by(Lecture.course_id)
        ).all()
    )
    activity_map = dict(
        db.execute(
            select(Lecture.course_id, func.max(Progress.updated_at))
            .join(Progress, Progress.lecture_id == Lecture.id)
            .where(Progress.user_id == user.id)
            .group_by(Lecture.course_id)
        ).all()
    )

    courses = [
        {
            "id": c.id,
            "slug": c.slug,
            "title": c.title,
            "category": c.category,
            "provider": c.provider,
            "library": lib_names.get(c.library_id),
            "cover": _cover_url(c, lib_paths.get(c.library_id)),
            "previews": _preview_urls(c, lib_paths.get(c.library_id)),
            "lectureCount": c.lecture_count,
            "completedCount": completed_map.get(c.id, 0),
            "lastActivity": str(activity_map[c.id]) if activity_map.get(c.id) else None,
            "createdAt": str(c.created_at) if c.created_at else None,
        }
        for c in rows
    ]
    categories = sorted({c["category"] for c in courses if c["category"]})
    providers = sorted({c["provider"] for c in courses if c["provider"]})
    libraries = sorted({c["library"] for c in courses if c["library"]})
    return {
        "courses": courses,
        "categories": categories,
        "providers": providers,
        "libraries": libraries,
    }


@router.get("/{slug}")
def get_course(
    slug: str, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict:
    c = db.scalar(select(Course).where(Course.slug == slug, Course.missing.is_(False)))
    if c is None or not can_access_course(db, user, c):
        raise HTTPException(status_code=404, detail="Course not found")

    lib = db.get(Library, c.library_id) if c.library_id else None

    sections = db.scalars(
        select(Section).where(Section.course_id == c.id).order_by(Section.position)
    ).all()
    lectures = db.scalars(
        select(Lecture).where(Lecture.course_id == c.id).order_by(Lecture.position)
    ).all()
    attachments = db.scalars(select(Attachment).where(Attachment.course_id == c.id)).all()
    prog = {
        p.lecture_id: p
        for p in db.scalars(
            select(Progress).join(Lecture, Lecture.id == Progress.lecture_id).where(
                Lecture.course_id == c.id, Progress.user_id == user.id
            )
        )
    }

    by_section: dict[int | None, list[Lecture]] = {}
    for lec in lectures:
        by_section.setdefault(lec.section_id, []).append(lec)

    # resume = first lecture (in order) that isn't completed; else the first one
    resume_id = next((lec.id for lec in lectures if not (prog.get(lec.id) and prog[lec.id].completed)), None)
    if resume_id is None and lectures:
        resume_id = lectures[0].id

    def lecture_json(lec: Lecture) -> dict:
        p = prog.get(lec.id)
        has_sub = lec.subtitle_path is not None or (
            lib is not None and uploaded_subtitle_path(lib.path, lec.path).is_file()
        )
        return {
            "id": lec.id,
            "title": lec.title,
            "kind": lec.kind,
            "playback": _playback(lec),
            "needsTranscode": lec.needs_transcode,
            "hasSubtitle": has_sub,
            "durationSec": lec.duration_sec,
            "positionSec": p.position_sec if p else 0.0,
            "completed": bool(p.completed) if p else False,
            "stream": f"/api/lectures/{lec.id}/stream",
            "subtitle": f"/api/lectures/{lec.id}/subtitle" if has_sub else None,
            "subtitles": embedded_subtitle_list(lec.id, lib.path if lib else None, lec.path),
        }

    return {
        "slug": c.slug,
        "title": c.title,
        "category": c.category,
        "provider": c.provider,
        "cover": _cover_url(c, lib.path if lib else None),
        "lectureCount": c.lecture_count,
        "completedCount": sum(1 for p in prog.values() if p.completed),
        "resumeLectureId": resume_id,
        "sections": [
            {
                "id": s.id,
                "title": s.title,
                "lectures": [lecture_json(lec) for lec in by_section.get(s.id, [])],
            }
            for s in sections
        ],
        "attachments": [{"id": a.id, "title": a.title, "kind": a.kind} for a in attachments],
    }
