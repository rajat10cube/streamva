"""Scan orchestration: walk every DB-registered library and sync into the DB.

Libraries are managed at runtime (added/removed via the API). Each library is
scanned in isolation so one bad path (e.g. an unreadable mount) can't abort the
whole run, and live progress + per-library errors are exposed via scan_status().
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from sqlalchemy import func, select

from ..config import get_settings
from ..db import SessionLocal
from ..models import Course, Lecture, Library
from .walk import discover_courses, walk_course
from .sync import sync_course

_lock = threading.Lock()
_status: dict = {
    "running": False,
    "phase": "idle",
    "started": None,
    "finished": None,
    "librariesTotal": 0,
    "librariesDone": 0,
    "current": None,
    "courses": 0,
    "lectures": 0,
    "errors": [],
}


def scan_status() -> dict:
    return dict(_status)


def seed_libraries_from_config() -> None:
    """If no libraries exist yet, import any from config/env (first-run convenience)."""
    settings = get_settings()
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(Library)):
            return
        for cfg in settings.libraries():
            db.add(Library(path=cfg.path, name=cfg.name,
                           group_depth=(-1 if isinstance(cfg.group_depth, str) else cfg.group_depth)))
        db.commit()


def _scan_library(db, settings, lib: Library) -> None:
    root = Path(lib.path)
    if not root.is_dir():
        _status["errors"].append({"library": lib.path, "error": "path not found inside the container"})
        return

    # video library: top-level folders (collections) + loose top-level videos
    seen: set[str] = set()
    found = 0
    for item in discover_courses(root):
        try:
            sc = walk_course(item, root, settings.min_video_bytes)
            if sc is None:
                continue
            sync_course(db, lib.id, sc)
            db.commit()  # each collection is its own transaction: a bad one rolls
            #              back alone and can't corrupt the session for the rest
        except Exception as e:  # noqa: BLE001 - isolate one bad item, keep scanning
            db.rollback()
            _status["errors"].append({"library": lib.path, "error": f"{item.name}: {e!r}"})
            continue
        seen.add(sc.rel_path)
        found += 1
        _status["courses"] += 1
        _status["lectures"] += len(sc.lectures)

    for c in db.scalars(select(Course).where(Course.library_id == lib.id)):
        c.missing = c.path not in seen
    db.commit()

    _probe_durations(db, settings, lib)
    _generate_covers(db, settings, lib)
    _generate_previews(db, settings, lib)

    if found == 0:
        _status["errors"].append(
            {"library": lib.path, "error": "no courses found — check the folder structure or read permissions"}
        )


def _probe_durations(db, settings, lib: Library) -> None:
    """Fill in missing media durations with ffprobe (new lectures only)."""
    if settings.ffmpeg == "off":
        return
    from ..probe import ffprobe_available, probe_duration

    if not ffprobe_available():
        return
    pending = db.scalars(
        select(Lecture)
        .join(Course, Course.id == Lecture.course_id)
        .where(Course.library_id == lib.id, Lecture.duration_sec.is_(None), Lecture.kind != "document")
    ).all()
    if not pending:
        return

    root = Path(lib.path)
    _status["phase"] = "probing media"
    for n, lec in enumerate(pending):
        d = probe_duration(root / lec.path)
        if d:
            lec.duration_sec = d
        if n % 25 == 0:
            db.commit()
    db.commit()
    _status["phase"] = "scanning"


def _generate_covers(db, settings, lib: Library) -> None:
    """Generate a poster frame for courses lacking an on-disk or cached cover."""
    if settings.ffmpeg == "off":
        return
    from ..probe import ffmpeg_available, generate_cover

    if not ffmpeg_available():
        return
    from ..covers import cover_path

    root = Path(lib.path)
    courses = db.scalars(
        select(Course).where(Course.library_id == lib.id, Course.missing.is_(False))
    ).all()
    for c in courses:
        if c.cover_path:  # has on-disk art
            continue
        out = cover_path(lib.path, c.path)
        if out.exists():
            continue
        lec = db.scalar(
            select(Lecture)
            .where(Lecture.course_id == c.id, Lecture.kind == "video")
            .order_by(Lecture.position)
            .limit(1)
        )
        if lec is None:
            continue
        at = min(max((lec.duration_sec or 150.0) * 0.1, 2.0), 120.0)
        _status["phase"] = "thumbnails"
        generate_cover(root / lec.path, out, at)
    _status["phase"] = "scanning"


def _generate_previews(db, settings, lib: Library) -> None:
    """Generate a few hover-preview frames per course from its first video."""
    if settings.ffmpeg == "off":
        return
    from ..probe import ffmpeg_available, generate_previews

    if not ffmpeg_available():
        return
    from ..covers import PREVIEW_COUNT, cover_token, previews_dir

    root = Path(lib.path)
    pdir = previews_dir()
    courses = db.scalars(
        select(Course).where(Course.library_id == lib.id, Course.missing.is_(False))
    ).all()
    for c in courses:
        token = cover_token(lib.path, c.path)
        if (pdir / f"{token}_0.jpg").exists():  # already generated
            continue
        lec = db.scalar(
            select(Lecture)
            .where(Lecture.course_id == c.id, Lecture.kind == "video")
            .order_by(Lecture.position)
            .limit(1)
        )
        if lec is None:
            continue
        _status["phase"] = "previews"
        generate_previews(root / lec.path, pdir, token, PREVIEW_COUNT, lec.duration_sec)
    _status["phase"] = "scanning"


def _cleanup_covers(db) -> None:
    """Drop generated covers/previews that no longer belong to any course.

    Removes orphans from deleted courses/libraries and legacy id-keyed files, so
    the caches only hold current, correctly-addressed images.
    """
    from ..covers import cover_token, covers_dir, previews_dir

    lib_paths = dict(db.execute(select(Library.id, Library.path)).all())
    keep = {
        cover_token(lib_paths[c.library_id], c.path)
        for c in db.scalars(select(Course))
        if c.library_id in lib_paths
    }
    cdir = covers_dir()
    if cdir.is_dir():
        for f in cdir.glob("*.jpg"):  # covers are "{token}.jpg"
            if f.stem not in keep:
                try:
                    f.unlink()
                except OSError:
                    pass
    pdir = previews_dir()
    if pdir.is_dir():
        for f in pdir.glob("*.jpg"):  # previews are "{token}_{i}.jpg"
            if f.stem.rsplit("_", 1)[0] not in keep:
                try:
                    f.unlink()
                except OSError:
                    pass


def run_scan() -> dict:
    if not _lock.acquire(blocking=False):
        return {"skipped": "scan already running"}

    settings = get_settings()
    t0 = time.time()
    _status.update({
        "running": True, "phase": "scanning", "started": t0, "finished": None,
        "librariesDone": 0, "current": None, "courses": 0, "lectures": 0, "errors": [],
    })
    try:
        with SessionLocal() as db:
            libs = db.scalars(select(Library)).all()
            _status["librariesTotal"] = len(libs)
            for i, lib in enumerate(libs):
                _status["current"] = lib.path
                try:
                    _scan_library(db, settings, lib)
                except Exception as e:  # isolate failures per library
                    db.rollback()
                    _status["errors"].append({"library": lib.path, "error": repr(e)})
                finally:
                    _status["librariesDone"] = i + 1

            _cleanup_covers(db)

            _status["phase"] = "indexing"
            _status["current"] = None
            from ..search import rebuild_index

            rebuild_index(db.connection())
            db.commit()
    finally:
        _status.update({"running": False, "phase": "idle", "finished": time.time()})
        _lock.release()

    return {
        "courses": _status["courses"],
        "lectures": _status["lectures"],
        "errors": _status["errors"],
        "seconds": round(time.time() - t0, 2),
    }
