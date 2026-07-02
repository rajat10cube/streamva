"""Stable, content-addressed filenames for generated course covers.

Covers are keyed by the course's on-disk location (library path + course
relative path), NOT by its database primary key. Primary keys are reused by
SQLite after deletes and reset to 1 on a fresh DB, so an id-keyed cache can
serve a stale thumbnail for the wrong course. A location-based key can't: a
different folder always yields a different filename.
"""

from __future__ import annotations

import hashlib
import json
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


def subtitles_dir() -> Path:
    return get_settings().data_dir / "subtitles"


def uploaded_subtitle_path(lib_path: str, lecture_rel: str) -> Path:
    """User-uploaded subtitle (stored as VTT in the data dir, keyed by the video)."""
    return subtitles_dir() / f"{cover_token(lib_path, lecture_rel)}.vtt"


# --- embedded subtitle tracks (extracted from the container at scan time) ----

def embedded_subs_dir() -> Path:
    return get_settings().data_dir / "embedded_subs"


def embedded_manifest_path(lib_path: str, lecture_rel: str) -> Path:
    """Per-video record of which embedded subtitle tracks were extracted."""
    return embedded_subs_dir() / f"{cover_token(lib_path, lecture_rel)}.json"


def embedded_vtt_path(lib_path: str, lecture_rel: str, idx: int) -> Path:
    """A single embedded subtitle stream (subtitle-relative ``idx``) as WebVTT."""
    return embedded_subs_dir() / f"{cover_token(lib_path, lecture_rel)}.s{idx}.vtt"


def embedded_tracks(lib_path: str, lecture_rel: str) -> list[dict]:
    """Read the scan-time manifest of extracted embedded tracks (empty if none)."""
    try:
        data = json.loads(embedded_manifest_path(lib_path, lecture_rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    tracks = data.get("tracks")
    return tracks if isinstance(tracks, list) else []
