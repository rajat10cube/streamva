"""Serve course cover images (generated covers + on-disk art come later)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access import can_access_course
from ..auth import require_user
from ..covers import cover_path, preview_path
from ..db import get_db
from ..models import Course, Library, User
from ..paths import library_root, safe_media_path

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/cover/{slug}")
def cover(slug: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    c = db.scalar(select(Course).where(Course.slug == slug))
    if c is None or not can_access_course(db, user, c):
        raise HTTPException(404, "No cover")
    # 1) on-disk art shipped with the course
    if c.cover_path:
        root = library_root(db, c)
        path = safe_media_path(root, c.cover_path) if root else None
        if path is not None:
            return FileResponse(path)
    # 2) generated thumbnail, keyed by the course's on-disk location
    lib = db.get(Library, c.library_id) if c.library_id else None
    if lib is not None:
        generated = cover_path(lib.path, c.path)
        if generated.is_file():
            return FileResponse(generated)
    raise HTTPException(404, "No cover")


@router.get("/preview/{slug}/{index}")
def preview(
    slug: str, index: int, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    c = db.scalar(select(Course).where(Course.slug == slug))
    if c is None or not can_access_course(db, user, c):
        raise HTTPException(404, "No preview")
    lib = db.get(Library, c.library_id) if c.library_id else None
    if lib is not None:
        frame = preview_path(lib.path, c.path, index)
        if frame.is_file():
            return FileResponse(frame)
    raise HTTPException(404, "No preview")
