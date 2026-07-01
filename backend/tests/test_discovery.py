"""Discovery for the two-level video library.

Top-level folders become collections of the videos directly inside them; loose
top-level video files become standalone single-video items. No deeper nesting.
"""

from pathlib import Path

from app.scanner.walk import discover_courses, walk_course


def _mk(p: Path, size: int = 2048) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)


def _names(lib: Path):
    return sorted(p.name for p in discover_courses(lib))


def test_folders_and_loose_videos_both_discovered(tmp_path):
    lib = tmp_path / "lib"
    _mk(lib / "Intro.mp4")            # loose video
    _mk(lib / "Outro.mp4")            # loose video
    _mk(lib / "Series A" / "a1.mp4")  # folder with videos
    _mk(lib / "Series A" / "a2.mp4")
    _mk(lib / "Series B" / "b1.mkv")
    assert _names(lib) == ["Intro.mp4", "Outro.mp4", "Series A", "Series B"]


def test_folder_collection_lists_its_videos_flat(tmp_path):
    lib = tmp_path / "lib"
    _mk(lib / "Series A" / "01 First.mp4")
    _mk(lib / "Series A" / "02 Second.mp4")
    _mk(lib / "Series A" / "03 Third.mp4")
    folder = next(p for p in discover_courses(lib) if p.name == "Series A")
    sc = walk_course(folder, lib, 0)
    assert sc.title == "Series A"
    assert [lec.title for lec in sc.lectures] == ["First", "Second", "Third"]
    assert len(sc.sections) == 1  # flat, single section
    assert all(lec.section_rel == "" for lec in sc.lectures)


def test_loose_video_is_a_single_item(tmp_path):
    lib = tmp_path / "lib"
    _mk(lib / "My Clip.mp4")
    item = next(iter(discover_courses(lib)))
    sc = walk_course(item, lib, 0)
    assert sc.title == "My Clip"  # extension stripped
    assert len(sc.lectures) == 1 and sc.lectures[0].kind == "video"


def test_empty_and_nonmedia_folders_are_skipped(tmp_path):
    lib = tmp_path / "lib"
    (lib / "Empty").mkdir(parents=True)
    _mk(lib / "Docs" / "readme.txt")     # no media inside -> skipped
    _mk(lib / "Has Video" / "v.mp4")
    assert _names(lib) == ["Has Video"]


def test_subtitle_binds_to_its_video(tmp_path):
    lib = tmp_path / "lib"
    _mk(lib / "Series" / "01 Lesson.mp4")
    (lib / "Series" / "01 Lesson.srt").write_text("1\n00:00 --> 00:01\nhi\n")
    sc = walk_course(next(iter(discover_courses(lib))), lib, 0)
    assert sc.lectures[0].subtitle_rel is not None
