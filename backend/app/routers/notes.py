"""Per-user, timestamped lecture notes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access import can_access_course
from ..auth import require_user
from ..db import get_db
from ..models import Course, Lecture, Note, User

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteIn(BaseModel):
    lecture_id: int
    position_sec: float = 0.0
    text: str


class NoteEdit(BaseModel):
    text: str


def _require_lecture_access(db: Session, user: User, lecture_id: int) -> None:
    lec = db.get(Lecture, lecture_id)
    if lec is None:
        raise HTTPException(404, "Lecture not found")
    course = db.get(Course, lec.course_id)
    if course is None or not can_access_course(db, user, course):
        raise HTTPException(404, "Lecture not found")


def _json(n: Note) -> dict:
    return {"id": n.id, "positionSec": n.position_sec, "text": n.text}


@router.get("")
def list_notes(lecture: int, user: User = Depends(require_user), db: Session = Depends(get_db)) -> list[dict]:
    _require_lecture_access(db, user, lecture)
    rows = db.scalars(
        select(Note)
        .where(Note.lecture_id == lecture, Note.user_id == user.id)
        .order_by(Note.position_sec, Note.id)
    ).all()
    return [_json(n) for n in rows]


@router.post("", status_code=201)
def create_note(body: NoteIn, user: User = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Note text is required")
    _require_lecture_access(db, user, body.lecture_id)
    n = Note(user_id=user.id, lecture_id=body.lecture_id,
             position_sec=max(0.0, body.position_sec), text=text)
    db.add(n)
    db.commit()
    db.refresh(n)
    return _json(n)


@router.put("/{note_id}")
def edit_note(note_id: int, body: NoteEdit, user: User = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    n = db.scalar(select(Note).where(Note.id == note_id, Note.user_id == user.id))
    if n is None:
        raise HTTPException(404, "Note not found")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Note text is required")
    n.text = text
    db.commit()
    return _json(n)


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)) -> None:
    n = db.scalar(select(Note).where(Note.id == note_id, Note.user_id == user.id))
    if n is None:
        raise HTTPException(404, "Note not found")
    db.delete(n)
    db.commit()
