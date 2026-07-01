from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()


def test_login_session_flow():
    c = TestClient(app)  # own cookie jar
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401

    r = c.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
    assert r.status_code == 200 and r.json()["username"] == "admin"

    # session cookie now authorizes protected endpoints (no Basic header)
    assert c.get("/api/auth/me").status_code == 200
    assert c.get("/api/courses").status_code == 200

    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").status_code == 401
    assert c.get("/api/courses").status_code == 401


def test_basic_still_accepted_for_api():
    c = TestClient(app)
    assert c.get("/api/courses", auth=("admin", "change-me")).status_code == 200
    assert c.get("/api/courses").status_code == 401  # no creds, no cookie


def test_401_has_no_basic_challenge():
    c = TestClient(app)
    r = c.get("/api/courses")
    assert r.status_code == 401
    # no WWW-Authenticate header -> browsers won't show the native popup
    assert "www-authenticate" not in {k.lower() for k in r.headers}
