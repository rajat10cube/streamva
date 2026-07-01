"""Per-user, per-lecture playback progress."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..access import can_access_course
from ..auth import require_user
from ..db import get_db
from ..models import Course, Lecture, Progress, User

router = APIRouter(prefix="/progress", tags=["progress"])

_COMPLETE_RATIO = 0.9


class ProgressIn(BaseModel):
    position_sec: float
    duration_sec: float | None = None
    completed: bool | None = None


@router.put("/{lecture_id}")
def put_progress(
    lecture_id: int,
    body: ProgressIn,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    lec = db.get(Lecture, lecture_id)
    if lec is None:
        raise HTTPException(404, "Lecture not found")
    course = db.get(Course, lec.course_id)
    if course is None or not can_access_course(db, user, course):
        raise HTTPException(404, "Lecture not found")

    p = db.scalar(
        select(Progress).where(Progress.lecture_id == lecture_id, Progress.user_id == user.id)
    )
    if p is None:
        p = Progress(lecture_id=lecture_id, user_id=user.id)
        db.add(p)

    p.position_sec = max(0.0, body.position_sec)
    if body.duration_sec:
        p.duration_sec = body.duration_sec

    if body.completed is not None:
        p.completed = body.completed  # explicit manual override (mark complete/incomplete)
    else:
        auto = bool(
            p.duration_sec
            and p.duration_sec > 0
            and (body.position_sec / p.duration_sec) >= _COMPLETE_RATIO
        )
        p.completed = bool(p.completed or auto)  # auto-completion is sticky

    db.commit()
    return {"lectureId": lecture_id, "positionSec": p.position_sec, "completed": p.completed}


def _resolve_course(db: Session, user: User, slug: str) -> Course:
    c = db.scalar(select(Course).where(Course.slug == slug))
    if c is None or not can_access_course(db, user, c):
        raise HTTPException(404, "Course not found")
    return c


@router.delete("/course/{slug}", status_code=204)
def reset_course_progress(
    slug: str, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> None:
    """Wipe this user's progress for every lecture in a course."""
    c = _resolve_course(db, user, slug)
    db.execute(
        delete(Progress).where(
            Progress.user_id == user.id,
            Progress.lecture_id.in_(select(Lecture.id).where(Lecture.course_id == c.id)),
        )
    )
    db.commit()


@router.put("/course/{slug}/complete")
def complete_course(
    slug: str, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict:
    """Mark every lecture in a course as completed for this user."""
    c = _resolve_course(db, user, slug)
    lectures = db.scalars(select(Lecture).where(Lecture.course_id == c.id)).all()
    existing = {
        p.lecture_id: p
        for p in db.scalars(
            select(Progress)
            .join(Lecture, Lecture.id == Progress.lecture_id)
            .where(Lecture.course_id == c.id, Progress.user_id == user.id)
        )
    }
    for lec in lectures:
        p = existing.get(lec.id)
        if p is None:
            p = Progress(lecture_id=lec.id, user_id=user.id)
            db.add(p)
        p.completed = True
        if lec.duration_sec:
            p.duration_sec = lec.duration_sec
            p.position_sec = lec.duration_sec
    db.commit()
    return {"slug": slug, "completedCount": len(lectures)}


@router.get("")
def get_progress(
    course: str, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict:
    c = db.scalar(select(Course).where(Course.slug == course))
    if c is None or not can_access_course(db, user, c):
        raise HTTPException(404, "Course not found")
    rows = db.scalars(
        select(Progress)
        .join(Lecture, Lecture.id == Progress.lecture_id)
        .where(Lecture.course_id == c.id, Progress.user_id == user.id)
    ).all()
    return {
        str(p.lecture_id): {
            "positionSec": p.position_sec,
            "durationSec": p.duration_sec,
            "completed": p.completed,
        }
        for p in rows
    }
