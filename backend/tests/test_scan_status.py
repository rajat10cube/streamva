"""Scan orchestration: per-library error isolation + live status.

A bad library path must be recorded as an error without aborting the whole run,
and a healthy library scanned alongside it must still import its courses. Guards
the regression where one unreadable mount (e.g. ``/``) aborted the entire scan.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import Course, Library
from app.scanner.service import run_scan, scan_status

init_db()


def _mk_course(root: Path) -> None:
    p = root / "Good Course" / "001 Welcome.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * 4096)


def test_bad_library_is_isolated_and_good_one_still_scans(tmp_path):
    good = tmp_path / "good"
    _mk_course(good)
    ghost = tmp_path / "ghost"  # deliberately never created

    with SessionLocal() as db:
        db.add(Library(path=str(good), name="good"))
        db.add(Library(path=str(ghost), name="ghost"))
        db.commit()

    result = run_scan()

    # the missing path is reported, but the run completes
    errs = {e["library"]: e["error"] for e in result["errors"]}
    assert str(ghost) in errs
    assert "path not found" in errs[str(ghost)]

    # the healthy library imported its course despite the bad sibling
    with SessionLocal() as db:
        titles = db.scalars(
            select(Course.title)
            .join(Library, Library.id == Course.library_id)
            .where(Library.path == str(good), Course.missing.is_(False))
        ).all()
    assert "Good Course" in titles

    # status settled cleanly afterwards
    st = scan_status()
    assert st["running"] is False
    assert st["finished"] is not None
    assert st["librariesTotal"] >= 2


def test_one_failing_course_is_isolated(tmp_path, monkeypatch):
    # a collection that errors during sync must not take down the whole library
    base = tmp_path / "lib"
    for name in ("Good Course", "Bad Course"):
        p = base / name / "001 a.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * 4096)
    with SessionLocal() as db:
        db.add(Library(path=str(base), name="L", group_depth=0))
        db.commit()

    import app.scanner.service as svc

    real_sync = svc.sync_course

    def flaky(db, library_id, sc):
        if sc.title == "Bad Course":
            raise RuntimeError("boom during sync")
        return real_sync(db, library_id, sc)

    monkeypatch.setattr(svc, "sync_course", flaky)
    run_scan()

    with SessionLocal() as db:
        titles = db.scalars(
            select(Course.title)
            .join(Library, Library.id == Course.library_id)
            .where(Library.path == str(base), Course.missing.is_(False))
        ).all()
    assert "Good Course" in titles  # imported despite the bad sibling
    assert "Bad Course" not in titles


def test_empty_library_reports_no_courses_found(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()

    with SessionLocal() as db:
        db.add(Library(path=str(empty), name="empty"))
        db.commit()

    result = run_scan()
    errs = {e["library"]: e["error"] for e in result["errors"]}
    assert str(empty) in errs
    assert "no courses found" in errs[str(empty)]
