from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def test_status_reports_already_set_up():
    # conftest seeds an admin, so setup is not needed and an anon caller has no user
    s = client.get("/api/auth/status").json()
    assert s["authDisabled"] is False
    assert s["needsSetup"] is False
    assert s["user"] is None


def test_setup_blocked_once_an_admin_exists():
    r = client.post("/api/auth/setup", json={"username": "root", "password": "rootpass"})
    assert r.status_code == 409
