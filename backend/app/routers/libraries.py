"""Runtime library management (add/remove folders from the UI, like Jellyfin)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..models import Course, Library
from ..scanner.service import run_scan
from ..search import rebuild_index

router = APIRouter(prefix="/libraries", tags=["libraries"], dependencies=[Depends(require_admin)])


class LibraryIn(BaseModel):
    path: str
    name: str | None = None


@router.get("")
def list_libraries(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Library)).all()
    counts = dict(
        db.execute(
            select(Course.library_id, func.count())
            .where(Course.missing.is_(False))
            .group_by(Course.library_id)
        ).all()
    )
    return [
        {
            "id": lib.id,
            "path": lib.path,
            "name": lib.name,
            "courseCount": counts.get(lib.id, 0),
            "accessible": Path(lib.path).is_dir(),
        }
        for lib in rows
    ]


@router.post("", status_code=201)
def add_library(
    body: LibraryIn, background: BackgroundTasks, db: Session = Depends(get_db)
) -> dict:
    path = body.path.strip()
    if len(path) > 1:
        path = path.rstrip("/")
    if not path:
        raise HTTPException(400, "Path is required")
    if not Path(path).is_dir():
        raise HTTPException(400, f"Not a directory or not accessible inside the container: {path}")
    if db.scalar(select(Library).where(Library.path == path)):
        raise HTTPException(409, "That library already exists")

    lib = Library(path=path, name=(body.name or "").strip() or Path(path).name, group_depth=0)
    db.add(lib)
    db.commit()
    db.refresh(lib)
    background.add_task(run_scan)  # scan the new folder in the background
    return {"id": lib.id, "path": lib.path, "name": lib.name}


@router.delete("/{library_id}", status_code=204)
def delete_library(library_id: int, db: Session = Depends(get_db)) -> None:
    if db.get(Library, library_id) is None:
        raise HTTPException(404, "Library not found")
    # ON DELETE CASCADE removes its courses/sections/lectures/progress
    db.execute(delete(Library).where(Library.id == library_id))
    rebuild_index(db.connection())
    db.commit()


@router.get("/browse")
def browse(path: str = "/") -> dict:
    p = Path(path or "/")
    if not p.is_dir():
        raise HTTPException(400, f"Not a directory: {path}")
    try:
        dirs = sorted(
            (c for c in p.iterdir() if c.is_dir() and not c.name.startswith(".")),
            key=lambda c: c.name.lower(),
        )
    except OSError as e:
        raise HTTPException(400, f"Cannot read {path}: {e}")
    return {
        "path": str(p),
        "parent": str(p.parent) if p != p.parent else None,
        "dirs": [{"name": c.name, "path": str(c)} for c in dirs[:1000]],
    }
