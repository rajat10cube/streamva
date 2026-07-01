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
        lib = Library(path=str(tmp_path / f"lib-{token}"), group_depth=0)
        db.add(lib)
        db.flush()
        c = Course(slug=f"u-{token}", title="U", path=f"C-{token}", library_id=lib.id, lecture_count=1)
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


def test_admin_can_create_user_and_nonadmin_is_blocked():
    c = TestClient(app)
    # create a regular user as admin
    r = c.post("/api/users", json={"username": "bob", "password": "bobpass", "is_admin": False}, auth=ADMIN)
    assert r.status_code == 201

    # bob logs in (session)
    bob = TestClient(app)
    assert bob.post("/api/auth/login", json={"username": "bob", "password": "bobpass"}).status_code == 200
    assert bob.get("/api/auth/me").json()["isAdmin"] is False

    # non-admin cannot manage users or libraries
    assert bob.get("/api/users").status_code == 403
    assert bob.post("/api/libraries", json={"path": "/tmp"}).status_code == 403


def test_progress_is_per_user(tmp_path):
    lec_id = _seed_lecture(tmp_path)
    # ensure a second user exists
    TestClient(app).post(
        "/api/users", json={"username": "carol", "password": "carolpw", "is_admin": False}, auth=ADMIN
    )

    admin = TestClient(app)
    admin.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
    carol = TestClient(app)
    carol.post("/api/auth/login", json={"username": "carol", "password": "carolpw"})

    # admin marks the lecture complete
    admin.put(f"/api/progress/{lec_id}", json={"position_sec": 95, "duration_sec": 100})

    admin_prog = admin.get("/api/progress", params={"course": f"u-{tmp_path.name}"}).json()
    carol_prog = carol.get("/api/progress", params={"course": f"u-{tmp_path.name}"}).json()
    assert admin_prog.get(str(lec_id), {}).get("completed") is True
    assert str(lec_id) not in carol_prog  # carol has her own (empty) progress


def test_self_password_change():
    c = TestClient(app)
    c.post("/api/users", json={"username": "dave", "password": "davepass", "is_admin": False}, auth=ADMIN)
    dave = TestClient(app)
    dave.post("/api/auth/login", json={"username": "dave", "password": "davepass"})
    # wrong current password rejected
    assert dave.post("/api/auth/password", json={"current_password": "x", "new_password": "newpass"}).status_code == 400
    # correct change works, and the new password logs in
    assert dave.post("/api/auth/password", json={"current_password": "davepass", "new_password": "newpass"}).status_code == 200
    fresh = TestClient(app)
    assert fresh.post("/api/auth/login", json={"username": "dave", "password": "newpass"}).status_code == 200
