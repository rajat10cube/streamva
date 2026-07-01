from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

# Ensure tables exist regardless of whether the test client runs the lifespan.
init_db()

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "streamva"


def test_courses_requires_auth():
    # auth defaults to basic -> unauthenticated request is rejected
    r = client.get("/api/courses")
    assert r.status_code == 401


def test_courses_with_auth_returns_shape():
    r = client.get("/api/courses", auth=("admin", "change-me"))
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["courses"], list)
    assert isinstance(body["categories"], list)
