from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Course, Lecture, Library, Section
from app.paths import safe_media_path

init_db()
client = TestClient(app)
AUTH = ("admin", "change-me")


def _seed(tmp_path: Path) -> tuple[int, int]:
    token = tmp_path.name  # unique per test -> unique course/lecture paths
    rel_course = f"Course-{token}"
    rel_lecture = f"{rel_course}/01 - S/001 v.mp4"
    data = bytes(range(256)) * 100  # 25600 bytes
    f = tmp_path / "lib" / rel_lecture
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    with SessionLocal() as db:
        lib = Library(path=str(tmp_path / "lib"), group_depth=0)
        db.add(lib)
        db.flush()
        c = Course(slug=f"t-{token}", title="T", path=rel_course, library_id=lib.id)
        db.add(c)
        db.flush()
        sec = Section(course_id=c.id, title="S", path=f"{rel_course}/01 - S", position=0)
        db.add(sec)
        db.flush()
        lec = Lecture(
            course_id=c.id, section_id=sec.id, title="v",
            path=rel_lecture, kind="video",
            mime="video/mp4", size_bytes=len(data), position=0,
        )
        db.add(lec)
        db.commit()
        return lec.id, len(data)


def test_stream_partial_range(tmp_path):
    lec_id, size = _seed(tmp_path)
    r = client.get(f"/api/lectures/{lec_id}/stream", headers={"Range": "bytes=0-99"}, auth=AUTH)
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-99/{size}"
    assert r.headers["accept-ranges"] == "bytes"
    assert len(r.content) == 100


def test_stream_full(tmp_path):
    lec_id, size = _seed(tmp_path)
    r = client.get(f"/api/lectures/{lec_id}/stream", auth=AUTH)
    assert r.status_code == 200
    assert len(r.content) == size


def test_stream_requires_auth(tmp_path):
    lec_id, _ = _seed(tmp_path)
    assert client.get(f"/api/lectures/{lec_id}/stream").status_code == 401


def test_safe_media_path_blocks_traversal(tmp_path):
    root = tmp_path / "lib"
    (root / "a").mkdir(parents=True)
    (root / "a" / "ok.mp4").write_bytes(b"x")
    (tmp_path / "secret.txt").write_bytes(b"nope")
    assert safe_media_path(root, "a/ok.mp4") is not None
    assert safe_media_path(root, "../secret.txt") is None
    assert safe_media_path(root, "a/../../secret.txt") is None
