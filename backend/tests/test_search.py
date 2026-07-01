from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SessionLocal, engine, init_db
from app.main import app
from app.models import Course, Lecture, Library, Section
from app.search import rebuild_index

init_db()
client = TestClient(app)
AUTH = ("admin", "change-me")


def _seed(tmp_path: Path) -> str:
    token = tmp_path.name
    with SessionLocal() as db:
        lib = Library(path=str(tmp_path / f"lib-{token}"), group_depth=0)
        db.add(lib)
        db.flush()
        c = Course(slug=f"s-{token}", title=f"Climbing System {token}", path=f"C-{token}",
                   library_id=lib.id, category="Unreal", lecture_count=1)
        db.add(c)
        db.flush()
        sec = Section(course_id=c.id, title="S", path=f"C-{token}/S", position=0)
        db.add(sec)
        db.flush()
        db.add(Lecture(course_id=c.id, section_id=sec.id, title="Ledge Grab Montage",
                       path=f"C-{token}/S/a.mp4", kind="video", size_bytes=10, position=0))
        db.commit()
    with engine.begin() as conn:
        rebuild_index(conn)
    return f"s-{token}"


def test_search_finds_lecture_by_title(tmp_path):
    slug = _seed(tmp_path)
    r = client.get("/api/search", params={"q": "ledge"}, auth=AUTH).json()["results"]
    hit = next((x for x in r if x["kind"] == "lecture" and x["slug"] == slug), None)
    assert hit is not None
    assert hit["title"] == "Ledge Grab Montage"


def test_search_finds_course_prefix(tmp_path):
    slug = _seed(tmp_path)
    r = client.get("/api/search", params={"q": "climb"}, auth=AUTH).json()["results"]
    assert any(x["kind"] == "course" and x["slug"] == slug for x in r)


def test_search_requires_auth():
    assert client.get("/api/search", params={"q": "x"}).status_code == 401
