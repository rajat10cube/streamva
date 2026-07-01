"""Stable, content-addressed filenames for generated course covers.

Covers are keyed by the course's on-disk location (library path + course
relative path), NOT by its database primary key. Primary keys are reused by
SQLite after deletes and reset to 1 on a fresh DB, so an id-keyed cache can
serve a stale thumbnail for the wrong course. A location-based key can't: a
different folder always yields a different filename.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .config import get_settings


def cover_token(lib_path: str, course_rel: str) -> str:
    """A short, stable hash identifying a course by where it lives on disk."""
    raw = f"{lib_path}\x00{course_rel}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:20]


def covers_dir() -> Path:
    return get_settings().data_dir / "covers"


def cover_path(lib_path: str, course_rel: str) -> Path:
    return covers_dir() / f"{cover_token(lib_path, course_rel)}.jpg"


# Hover-preview storyboard: a few frames sampled across the item's video.
PREVIEW_COUNT = 10


def previews_dir() -> Path:
    return get_settings().data_dir / "previews"


def preview_path(lib_path: str, course_rel: str, index: int) -> Path:
    return previews_dir() / f"{cover_token(lib_path, course_rel)}_{index}.jpg"
