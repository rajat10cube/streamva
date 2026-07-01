"""Subtitle conversion (SRT -> WebVTT) and next-lecture lookup."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Course, Lecture, Library, Section
from app.routers.lectures import srt_to_vtt

init_db()
client = TestClient(app)
AUTH = ("admin", "change-me")

SRT = "1\n00:00:01,000 --> 00:00:04,000\nHello, world\n"


def _seed(tmp_path: Path, *, with_srt: bool = False) -> tuple[int, int]:
    token = tmp_path.name
    root = tmp_path / "lib"
    rel_course = f"Course-{token}"
    sub_rel = f"{rel_course}/01 - S/001 v.srt"
    if with_srt:
        p = root / sub_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(SRT, encoding="utf-8")
    with SessionLocal() as db:
        lib = Library(path=str(root), group_depth=0)
        db.add(lib)
        db.flush()
        c = Course(slug=f"lx-{token}", title="LX", path=rel_course, library_id=lib.id, lecture_count=2)
        db.add(c)
        db.flush()
        sec = Section(course_id=c.id, title="S", path=f"{rel_course}/01 - S", position=0)
        db.add(sec)
        db.flush()
        l1 = Lecture(course_id=c.id, section_id=sec.id, title="a",
                     path=f"{rel_course}/01 - S/001 v.mp4", kind="video", size_bytes=10, position=0,
                     subtitle_path=(sub_rel if with_srt else None))
        l2 = Lecture(course_id=c.id, section_id=sec.id, title="b",
                     path=f"{rel_course}/01 - S/002 v.mp4", kind="video", size_bytes=10, position=1)
        db.add_all([l1, l2])
        db.commit()
        return l1.id, l2.id


def test_srt_to_vtt_converts_timestamp_separator():
    out = srt_to_vtt(SRT)
    assert out.startswith("WEBVTT\n\n")
    assert "00:00:01.000 --> 00:00:04.000" in out  # comma -> dot
    assert "00:00:01,000" not in out  # original comma form gone
    assert "Hello, world" in out  # text commas untouched


def test_subtitle_endpoint_serves_vtt(tmp_path):
    l1, _ = _seed(tmp_path, with_srt=True)
    r = client.get(f"/api/lectures/{l1}/subtitle", auth=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/vtt")
    assert r.text.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:04.000" in r.text


def test_subtitle_404_when_lecture_has_none(tmp_path):
    l1, _ = _seed(tmp_path, with_srt=False)
    assert client.get(f"/api/lectures/{l1}/subtitle", auth=AUTH).status_code == 404


def test_next_lecture_walks_then_ends(tmp_path):
    l1, l2 = _seed(tmp_path)
    assert client.get(f"/api/lectures/{l1}/next", auth=AUTH).json()["next"]["id"] == l2
    assert client.get(f"/api/lectures/{l2}/next", auth=AUTH).json()["next"] is None


def test_next_requires_auth(tmp_path):
    l1, _ = _seed(tmp_path)
    assert client.get(f"/api/lectures/{l1}/next").status_code == 401
