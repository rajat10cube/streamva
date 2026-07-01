import uuid

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Course, Lecture, Library, Section

init_db()
ADMIN = ("admin", "change-me")


def _seed_two_libraries():
    t = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        a = Library(path=f"/tmp/libA-{t}", group_depth=0)
        b = Library(path=f"/tmp/libB-{t}", group_depth=0)
        db.add_all([a, b])
        db.flush()
        ca = Course(slug=f"ca-{t}", title="CourseA", path=f"A-{t}", library_id=a.id, lecture_count=1)
        cb = Course(slug=f"cb-{t}", title="CourseB", path=f"B-{t}", library_id=b.id, lecture_count=1)
        db.add_all([ca, cb])
        db.flush()
        sec = Section(course_id=cb.id, title="S", path=f"B-{t}/S", position=0)
        db.add(sec)
        db.flush()
        lec = Lecture(course_id=cb.id, section_id=sec.id, title="x",
                      path=f"B-{t}/S/x.mp4", kind="video", size_bytes=10, position=0)
        db.add(lec)
        db.commit()
        return {"libA": a.id, "libB": b.id, "slugA": ca.slug, "slugB": cb.slug, "lecB": lec.id, "t": t}


def test_per_library_access():
    s = _seed_two_libraries()
    c = TestClient(app)

    r = c.post("/api/users", json={"username": f"eve-{s['t']}", "password": "evepass"}, auth=ADMIN)
    assert r.status_code == 201
    eid = r.json()["id"]
    # restrict eve to library A only
    assert c.put(f"/api/users/{eid}/access",
                 json={"all_libraries": False, "library_ids": [s["libA"]]}, auth=ADMIN).status_code == 200

    eve = TestClient(app)
    eve.post("/api/auth/login", json={"username": f"eve-{s['t']}", "password": "evepass"})

    slugs = [x["slug"] for x in eve.get("/api/courses").json()["courses"]]
    assert s["slugA"] in slugs
    assert s["slugB"] not in slugs                       # B is hidden
    assert eve.get(f"/api/courses/{s['slugB']}").status_code == 404
    assert eve.get(f"/api/lectures/{s['lecB']}/stream").status_code == 404  # cannot stream B

    # admin sees both
    aslugs = [x["slug"] for x in c.get("/api/courses", auth=ADMIN).json()["courses"]]
    assert s["slugA"] in aslugs and s["slugB"] in aslugs


def test_default_user_sees_all():
    s = _seed_two_libraries()
    c = TestClient(app)
    c.post("/api/users", json={"username": f"frank-{s['t']}", "password": "frankpw"}, auth=ADMIN)
    frank = TestClient(app)
    frank.post("/api/auth/login", json={"username": f"frank-{s['t']}", "password": "frankpw"})
    slugs = [x["slug"] for x in frank.get("/api/courses").json()["courses"]]
    assert s["slugA"] in slugs and s["slugB"] in slugs   # default = all libraries
