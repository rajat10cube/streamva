"""ffprobe durations + ffmpeg cover generation.

Unit-tests the probe helpers and verifies a scan enriches lectures with
real durations and generates a thumbnail. Tests that need real media are
skipped when ffmpeg/ffprobe aren't on PATH.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.probe import ffmpeg_available, ffprobe_available, generate_cover, probe_duration

init_db()

ADMIN = ("admin", "change-me")
needs_ffmpeg = pytest.mark.skipif(
    not (ffmpeg_available() and ffprobe_available()),
    reason="ffmpeg/ffprobe not installed",
)


def _make_video(path: Path, secs: int = 3) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i",
         f"testsrc=duration={secs}:size=320x240:rate=10",
         "-pix_fmt", "yuv420p", "-y", str(path)],
        capture_output=True,
    )
    return path


def _make_src_video(path: Path, src: str, secs: int = 5) -> Path:
    """Make a video from a distinct lavfi pattern (e.g. testsrc vs smptebars)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i",
         f"{src}=size=320x240:duration={secs}:rate=10",
         "-pix_fmt", "yuv420p", "-y", str(path)],
        capture_output=True,
    )
    return path


@needs_ffmpeg
def test_probe_duration_reads_real_length(tmp_path):
    d = probe_duration(_make_video(tmp_path / "a.mp4", 3))
    assert d is not None
    assert 2.5 < d < 3.5


def test_probe_duration_on_non_media_is_none(tmp_path):
    p = tmp_path / "x.mp4"
    p.write_bytes(b"definitely not a video")
    assert probe_duration(p) is None


@needs_ffmpeg
def test_generate_cover_writes_jpeg(tmp_path):
    out = tmp_path / "cover.jpg"
    assert generate_cover(_make_video(tmp_path / "a.mp4", 3), out, at=1.0) is True
    assert out.is_file() and out.stat().st_size > 0


def test_generate_cover_on_missing_video_fails(tmp_path):
    assert generate_cover(tmp_path / "nope.mp4", tmp_path / "out.jpg", at=1.0) is False


@needs_ffmpeg
def test_scan_enriches_duration_and_cover(tmp_path):
    _make_video(tmp_path / "lib" / "My Course" / "001 Welcome.mp4", 3)
    c = TestClient(app)
    assert c.post("/api/libraries", json={"path": str(tmp_path / "lib")}, auth=ADMIN).status_code == 201
    c.post("/api/admin/rescan", params={"wait": "true"}, auth=ADMIN)

    cards = c.get("/api/courses", auth=ADMIN).json()["courses"]
    card = next(x for x in cards if x["title"] == "My Course")
    assert card["cover"] is not None  # ffmpeg generated a thumbnail

    detail = c.get(f"/api/courses/{card['slug']}", auth=ADMIN).json()
    lec = detail["sections"][0]["lectures"][0]
    assert lec["durationSec"] is not None and lec["durationSec"] > 2


def test_cover_token_is_location_based():
    from app.covers import cover_token

    a = cover_token("/media/lib", "Course A")
    assert a != cover_token("/media/lib", "Course B")  # different course
    assert a != cover_token("/other/lib", "Course A")  # different library path
    assert a == cover_token("/media/lib", "Course A")  # stable for same location


@needs_ffmpeg
def test_each_course_gets_its_own_cover(tmp_path):
    # two visually distinct courses — covers must not be shared/swapped
    _make_src_video(tmp_path / "lib" / "Bars Course" / "001 a.mp4", "smptebars")
    _make_src_video(tmp_path / "lib" / "Test Course" / "001 a.mp4", "testsrc")
    c = TestClient(app)
    c.post("/api/libraries", json={"path": str(tmp_path / "lib")}, auth=ADMIN)
    c.post("/api/admin/rescan", params={"wait": "true"}, auth=ADMIN)

    cards = {x["title"]: x for x in c.get("/api/courses", auth=ADMIN).json()["courses"]}
    assert cards["Bars Course"]["cover"] and cards["Test Course"]["cover"]
    bars = c.get(cards["Bars Course"]["cover"], auth=ADMIN)
    test = c.get(cards["Test Course"]["cover"], auth=ADMIN)
    assert bars.status_code == 200 and test.status_code == 200
    assert bars.content != test.content  # distinct frames -> distinct files


@needs_ffmpeg
def test_scan_generates_hover_previews(tmp_path):
    _make_video(tmp_path / "lib" / "Clip Collection" / "001 a.mp4", 6)
    c = TestClient(app)
    c.post("/api/libraries", json={"path": str(tmp_path / "lib")}, auth=ADMIN)
    c.post("/api/admin/rescan", params={"wait": "true"}, auth=ADMIN)

    card = next(
        x for x in c.get("/api/courses", auth=ADMIN).json()["courses"] if x["title"] == "Clip Collection"
    )
    assert len(card["previews"]) >= 2  # several storyboard frames
    r = c.get(card["previews"][0], auth=ADMIN)
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/")


def test_scan_removes_orphan_covers(tmp_path):
    from app.config import get_settings

    _make_video(tmp_path / "lib" / "My Course" / "001 a.mp4", 2)
    covers = get_settings().data_dir / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    orphan = covers / "0.jpg"  # legacy id-keyed file from before the fix
    orphan.write_bytes(b"stale")

    c = TestClient(app)
    c.post("/api/libraries", json={"path": str(tmp_path / "lib")}, auth=ADMIN)
    c.post("/api/admin/rescan", params={"wait": "true"}, auth=ADMIN)

    assert not orphan.exists()
