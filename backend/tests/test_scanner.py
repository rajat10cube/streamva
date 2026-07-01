"""walk_course details for the video-library model."""

from pathlib import Path

from app.scanner.walk import walk_course


def _mk(p: Path, data: bytes = b"x" * 2048) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def test_min_video_bytes_filters_small_videos(tmp_path: Path):
    lib = tmp_path / "lib"
    _mk(lib / "S" / "big.mp4", b"x" * 5000)
    _mk(lib / "S" / "tiny.mp4", b"x" * 100)
    sc = walk_course(lib / "S", lib, min_video_bytes=1000)
    titles = [lec.title for lec in sc.lectures]
    assert "big" in titles and "tiny" not in titles


def test_folder_art_becomes_cover_and_junk_is_skipped(tmp_path: Path):
    lib = tmp_path / "lib"
    _mk(lib / "S" / "01 video.mp4")
    _mk(lib / "S" / "cover.jpg")   # folder art -> cover, not an item
    _mk(lib / "S" / "thumbs.db")   # junk -> ignored
    sc = walk_course(lib / "S", lib, 0)
    assert any(lec.kind == "video" for lec in sc.lectures)
    assert sc.cover_rel is not None and sc.cover_rel.endswith("cover.jpg")
    assert all("thumbs" not in lec.rel_path for lec in sc.lectures)


def test_mkv_flagged_for_transcode(tmp_path: Path):
    lib = tmp_path / "lib"
    _mk(lib / "S" / "clip.mkv")
    sc = walk_course(lib / "S", lib, 0)
    assert sc.lectures[0].needs_transcode is True


def test_empty_folder_returns_none(tmp_path: Path):
    lib = tmp_path / "lib"
    (lib / "S").mkdir(parents=True)
    assert walk_course(lib / "S", lib, 0) is None


def test_walk_on_unreadable_returns_none(tmp_path: Path):
    # a non-directory, non-media path -> nothing playable -> None (never raises)
    f = tmp_path / "not-media.txt"
    f.write_bytes(b"x")
    assert walk_course(f, tmp_path, 0) is None
