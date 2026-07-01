"""Safe resolution of on-disk media paths (path-traversal guard)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from .models import Course, Library


def library_root(db: Session, course: Course) -> Path | None:
    if course.library_id is None:
        return None
    lib = db.get(Library, course.library_id)
    return Path(lib.path) if lib else None


def safe_media_path(root: Path, rel: str) -> Path | None:
    """Join ``rel`` onto ``root`` and confirm the result stays inside ``root``."""
    try:
        base = root.resolve()
        target = (base / rel).resolve()
        target.relative_to(base)  # raises ValueError on escape
    except (ValueError, OSError):
        return None
    return target if target.is_file() else None
