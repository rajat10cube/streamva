from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Course, Lecture, Library, Section

init_db()
client = TestClient(app)
AUTH = ("admin", "change-me")


def _seed(tmp_path: Path) -> tuple[str, int, int]:
    token = tmp_path.name
    with SessionLocal() as db:
        lib = Library(path=str(tmp_path / f"lib-{token}"), group_depth=0)
        db.add(lib)
        db.flush()
        c = Course(slug=f"p-{token}", title="P", path=f"C-{token}", library_id=lib.id, lecture_count=2)
        db.add(c)
        db.flush()
        sec = Section(course_id=c.id, title="S", path=f"C-{token}/S", position=0)
        db.add(sec)
        db.flush()
        l1 = Lecture(course_id=c.id, section_id=sec.id, title="a",
                     path=f"C-{token}/S/a.mp4", kind="video", size_bytes=10, position=0)
        l2 = Lecture(course_id=c.id, section_id=sec.id, title="b",
                     path=f"C-{token}/S/b.mp4", kind="video", size_bytes=10, position=1)
        db.add_all([l1, l2])
        db.commit()
        return c.slug, l1.id, l2.id


def test_put_and_get_progress(tmp_path):
    slug, l1, l2 = _seed(tmp_path)

    r = client.put(f"/api/progress/{l1}", json={"position_sec": 30, "duration_sec": 100}, auth=AUTH)
    assert r.status_code == 200 and r.json()["completed"] is False

    r = client.put(f"/api/progress/{l1}", json={"position_sec": 95, "duration_sec": 100}, auth=AUTH)
    assert r.json()["completed"] is True

    d = client.get(f"/api/courses/{slug}", auth=AUTH).json()
    assert d["completedCount"] == 1
    assert d["resumeLectureId"] == l2
    lecs = {lec["id"]: lec for s in d["sections"] for lec in s["lectures"]}
    assert lecs[l1]["completed"] is True
    assert lecs[l1]["positionSec"] == 95

    card = next(c for c in client.get("/api/courses", auth=AUTH).json()["courses"] if c["slug"] == slug)
    assert card["completedCount"] == 1 and card["lastActivity"] is not None


def test_completion_is_sticky(tmp_path):
    _slug, l1, _l2 = _seed(tmp_path)
    client.put(f"/api/progress/{l1}", json={"position_sec": 95, "duration_sec": 100}, auth=AUTH)
    # rewatching from the start must not un-complete it
    r = client.put(f"/api/progress/{l1}", json={"position_sec": 5, "duration_sec": 100}, auth=AUTH)
    assert r.json()["completed"] is True


def test_mark_incomplete_overrides_auto_completion(tmp_path):
    _slug, l1, _l2 = _seed(tmp_path)
    # auto-completes by watch ratio
    assert client.put(f"/api/progress/{l1}", json={"position_sec": 95, "duration_sec": 100}, auth=AUTH).json()["completed"] is True
    # explicit completed:false un-completes it (manual "mark as not watched")
    r = client.put(f"/api/progress/{l1}", json={"position_sec": 95, "duration_sec": 100, "completed": False}, auth=AUTH)
    assert r.json()["completed"] is False
    d = client.get(f"/api/courses/{_slug}", auth=AUTH).json()
    assert d["completedCount"] == 0


def test_mark_complete_without_duration(tmp_path):
    _slug, l1, _l2 = _seed(tmp_path)
    # no duration known, but an explicit completed:true still marks it done
    r = client.put(f"/api/progress/{l1}", json={"position_sec": 1, "completed": True}, auth=AUTH)
    assert r.json()["completed"] is True


def test_reset_course_progress(tmp_path):
    slug, l1, l2 = _seed(tmp_path)
    client.put(f"/api/progress/{l1}", json={"position_sec": 95, "duration_sec": 100}, auth=AUTH)
    client.put(f"/api/progress/{l2}", json={"position_sec": 30, "duration_sec": 100}, auth=AUTH)
    assert client.get(f"/api/courses/{slug}", auth=AUTH).json()["completedCount"] == 1

    r = client.delete(f"/api/progress/course/{slug}", auth=AUTH)
    assert r.status_code == 204

    d = client.get(f"/api/courses/{slug}", auth=AUTH).json()
    assert d["completedCount"] == 0
    lecs = {lec["id"]: lec for s in d["sections"] for lec in s["lectures"]}
    assert lecs[l1]["positionSec"] == 0 and lecs[l1]["completed"] is False
    assert lecs[l2]["positionSec"] == 0


def test_reset_is_per_user(tmp_path):
    slug, l1, _l2 = _seed(tmp_path)
    client.put(f"/api/progress/{l1}", json={"position_sec": 95, "duration_sec": 100}, auth=AUTH)

    # a second user with their own progress on the same lecture
    uname = f"rp-{tmp_path.name}"
    client.post("/api/users", json={"username": uname, "password": "pw1234"}, auth=AUTH)
    other = TestClient(app)
    other.post("/api/auth/login", json={"username": uname, "password": "pw1234"})
    other.put(f"/api/progress/{l1}", json={"position_sec": 50, "duration_sec": 100})

    # admin resets only their own progress
    assert client.delete(f"/api/progress/course/{slug}", auth=AUTH).status_code == 204
    assert client.get(f"/api/courses/{slug}", auth=AUTH).json()["completedCount"] == 0
    # the other user's progress is untouched
    o = other.get(f"/api/courses/{slug}").json()
    lecs = {lec["id"]: lec for s in o["sections"] for lec in s["lectures"]}
    assert lecs[l1]["positionSec"] == 50


def test_complete_course_marks_all(tmp_path):
    slug, l1, l2 = _seed(tmp_path)
    r = client.put(f"/api/progress/course/{slug}/complete", auth=AUTH)
    assert r.status_code == 200 and r.json()["completedCount"] == 2

    d = client.get(f"/api/courses/{slug}", auth=AUTH).json()
    assert d["completedCount"] == 2
    lecs = {lec["id"]: lec for s in d["sections"] for lec in s["lectures"]}
    assert lecs[l1]["completed"] is True and lecs[l2]["completed"] is True


def test_reset_unknown_course_is_404(tmp_path):
    assert client.delete("/api/progress/course/does-not-exist", auth=AUTH).status_code == 404


def test_course_progress_actions_require_auth(tmp_path):
    slug, _l1, _l2 = _seed(tmp_path)
    assert client.delete(f"/api/progress/course/{slug}").status_code == 401
    assert client.put(f"/api/progress/course/{slug}/complete").status_code == 401


def test_progress_requires_auth(tmp_path):
    _slug, l1, _l2 = _seed(tmp_path)
    assert client.put(f"/api/progress/{l1}", json={"position_sec": 1}).status_code == 401
