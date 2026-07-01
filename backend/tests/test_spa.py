from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_STATIC = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
_HAS_SPA = _STATIC.is_file()


def test_unknown_api_route_is_404_not_spa():
    # the catch-all must not swallow /api/* into index.html
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert "text/html" not in r.headers.get("content-type", "")


def test_spa_deeplink_serves_index():
    if not _HAS_SPA:
        return  # frontend not built in this environment
    r = client.get("/course/some-slug")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="root"' in r.text
