from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Course, Lecture, Library, Section

init_db()
ADMIN = ("admin", "change-me")


def _seed_lecture(tmp_path: Path) -> int:
    token = tmp_path.name
    with SessionLocal() as db:
        lib = Library(path=str(tmp_path / f"l-{token}"), group_depth=0)
        db.add(lib)
        db.flush()
        c = Course(slug=f"n-{token}", title="N", path=f"C-{token}", library_id=lib.id, lecture_count=1)
        db.add(c)
        db.flush()
        sec = Section(course_id=c.id, title="S", path=f"C-{token}/S", position=0)
        db.add(sec)
        db.flush()
        lec = Lecture(course_id=c.id, section_id=sec.id, title="a",
                      path=f"C-{token}/S/a.mp4", kind="video", size_bytes=10, position=0)
        db.add(lec)
        db.commit()
        return lec.id


def test_notes_crud_and_per_user(tmp_path):
    lid = _seed_lecture(tmp_path)
    c = TestClient(app)

    r = c.post("/api/notes", json={"lecture_id": lid, "position_sec": 42, "text": "hello"}, auth=ADMIN)
    assert r.status_code == 201
    nid = r.json()["id"]

    notes = c.get("/api/notes", params={"lecture": lid}, auth=ADMIN).json()
    assert len(notes) == 1 and notes[0]["positionSec"] == 42 and notes[0]["text"] == "hello"

    # a different user doesn't see the admin's notes
    c.post("/api/users", json={"username": f"nv-{tmp_path.name}", "password": "pw1234"}, auth=ADMIN)
    other = TestClient(app)
    other.post("/api/auth/login", json={"username": f"nv-{tmp_path.name}", "password": "pw1234"})
    assert other.get("/api/notes", params={"lecture": lid}).json() == []

    assert c.delete(f"/api/notes/{nid}", auth=ADMIN).status_code == 204
    assert c.get("/api/notes", params={"lecture": lid}, auth=ADMIN).json() == []


def test_edit_note(tmp_path):
    lid = _seed_lecture(tmp_path)
    c = TestClient(app)
    nid = c.post("/api/notes", json={"lecture_id": lid, "text": "draft"}, auth=ADMIN).json()["id"]
    r = c.put(f"/api/notes/{nid}", json={"text": "final"}, auth=ADMIN)
    assert r.status_code == 200 and r.json()["text"] == "final"
    assert c.get("/api/notes", params={"lecture": lid}, auth=ADMIN).json()[0]["text"] == "final"


def test_blank_note_is_rejected(tmp_path):
    lid = _seed_lecture(tmp_path)
    c = TestClient(app)
    assert c.post("/api/notes", json={"lecture_id": lid, "text": "   "}, auth=ADMIN).status_code == 400
    nid = c.post("/api/notes", json={"lecture_id": lid, "text": "ok"}, auth=ADMIN).json()["id"]
    assert c.put(f"/api/notes/{nid}", json={"text": "  "}, auth=ADMIN).status_code == 400


def test_edit_missing_note_is_404(tmp_path):
    assert TestClient(app).put("/api/notes/99999999", json={"text": "x"}, auth=ADMIN).status_code == 404


def test_notes_require_auth(tmp_path):
    lid = _seed_lecture(tmp_path)
    assert TestClient(app).get("/api/notes", params={"lecture": lid}).status_code == 401
