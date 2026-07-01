"""Persist a scanned course tree into the DB idempotently.

Lectures/sections are upserted by path so IDs stay stable across rescans
(important once progress is keyed by lecture_id in Phase 3).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Attachment, Course, Lecture, Section
from .naming import slugify
from .walk import SCourse


def _unique_slug(db: Session, base: str) -> str:
    slug = base or "course"
    i = 2
    while db.scalar(select(Course.id).where(Course.slug == slug)) is not None:
        slug = f"{base}-{i}"
        i += 1
    return slug


def sync_course(db: Session, library_id: int, sc: SCourse) -> Course:
    course = db.scalar(select(Course).where(Course.path == sc.rel_path))
    if course is None:
        course = Course(path=sc.rel_path, slug=_unique_slug(db, slugify(sc.title)))
        db.add(course)

    course.title = sc.title
    course.category = sc.category
    course.provider = sc.provider
    course.library_id = library_id
    course.cover_path = sc.cover_rel
    course.missing = False
    course.lecture_count = len(sc.lectures)
    course.scanned_at = datetime.now(timezone.utc)
    db.flush()

    # --- sections ---
    existing_sections = {
        s.path: s for s in db.scalars(select(Section).where(Section.course_id == course.id))
    }
    sec_id_by_rel: dict[str, int] = {}
    seen_sections: set[str] = set()
    for pos, s in enumerate(sc.sections):
        sec = existing_sections.get(s.rel)
        if sec is None:
            sec = Section(course_id=course.id, path=s.rel)
            db.add(sec)
        sec.title = s.title
        sec.position = pos
        db.flush()
        sec_id_by_rel[s.rel] = sec.id
        seen_sections.add(s.rel)
    for path, sec in existing_sections.items():
        if path not in seen_sections:
            db.delete(sec)

    # --- lectures ---
    existing_lectures = {
        lec.path: lec for lec in db.scalars(select(Lecture).where(Lecture.course_id == course.id))
    }
    seen_lectures: set[str] = set()
    for pos, lec_in in enumerate(sc.lectures):
        lec = existing_lectures.get(lec_in.rel_path)
        if lec is None:
            lec = Lecture(path=lec_in.rel_path)
            db.add(lec)
        lec.course_id = course.id
        lec.section_id = sec_id_by_rel.get(lec_in.section_rel)
        lec.title = lec_in.title
        lec.kind = lec_in.kind
        lec.mime = lec_in.mime
        lec.size_bytes = lec_in.size
        lec.needs_transcode = lec_in.needs_transcode
        lec.subtitle_path = lec_in.subtitle_rel
        lec.position = pos
        seen_lectures.add(lec_in.rel_path)
    for path, lec in existing_lectures.items():
        if path not in seen_lectures:
            db.delete(lec)

    # --- attachments (simple replace; not referenced by other rows) ---
    db.execute(delete(Attachment).where(Attachment.course_id == course.id))
    for a in sc.attachments:
        db.add(
            Attachment(
                course_id=course.id, title=a.title, path=a.rel_path,
                kind=a.kind, mime=a.mime, size_bytes=a.size,
            )
        )

    return course
