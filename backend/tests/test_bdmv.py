"""Blu-ray (BDMV) disc detection, playlist parsing, and conversion."""

import struct
import subprocess
from pathlib import Path

import pytest

from app import bdmv
from app.db import SessionLocal, init_db
from app.models import Library
from app.probe import ffmpeg_available

init_db()

needs_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")


def _make_mpls(items: list[tuple[str, float]]) -> bytes:
    """Minimal valid .mpls: items = [(clip_id, duration_seconds)]."""
    playitems = b""
    for name, dur in items:
        ticks = int(dur * 45000)
        d = (name.encode("ascii").ljust(5, b"\0")[:5] + b"M2TS" + b"\x00\x00" + b"\x00"
             + struct.pack(">I", 0) + struct.pack(">I", ticks))  # clip+codec+flags+stc+IN+OUT = 20B
        playitems += struct.pack(">H", len(d)) + d
    plsec = (struct.pack(">I", len(playitems) + 6) + b"\x00\x00"
             + struct.pack(">H", len(items)) + struct.pack(">H", 0) + playitems)
    header = b"MPLS0200" + struct.pack(">I", 40) + b"\x00" * 28  # 40-byte header, PlayList at 40
    return header + plsec


def _mk_disc(disc: Path, clips: list[str]) -> tuple[Path, Path]:
    stream = disc / "BDMV" / "STREAM"
    pl = disc / "BDMV" / "PLAYLIST"
    stream.mkdir(parents=True, exist_ok=True)
    pl.mkdir(parents=True, exist_ok=True)
    for c in clips:
        (stream / f"{c}.m2ts").write_bytes(b"x" * 2048)
    return stream, pl


def test_playlist_selects_main_title_and_joins_segments(tmp_path, monkeypatch):
    monkeypatch.setattr(bdmv, "_MIN_DURATION_SEC", 600)
    disc = tmp_path / "lib" / "Movie"
    _, pl = _mk_disc(disc, ["00001", "00002", "00003"])
    (pl / "00000.mpls").write_bytes(_make_mpls([("00001", 3000), ("00002", 2400)]))  # main, branched
    (pl / "00001.mpls").write_bytes(_make_mpls([("00003", 120)]))                    # short extra

    titles = bdmv._disc_titles(disc)
    assert len(titles) == 1
    assert [c.name for c in titles[0]["clips"]] == ["00001.m2ts", "00002.m2ts"]  # joined, in order
    assert titles[0]["duration"] > 5000


def test_playlist_drops_play_all_superset(tmp_path, monkeypatch):
    monkeypatch.setattr(bdmv, "_MIN_DURATION_SEC", 60)
    disc = tmp_path / "lib2" / "Series"
    _, pl = _mk_disc(disc, ["00001", "00002"])
    (pl / "00000.mpls").write_bytes(_make_mpls([("00001", 1400), ("00002", 1400)]))  # play-all
    (pl / "00001.mpls").write_bytes(_make_mpls([("00001", 1400)]))                    # episode 1
    (pl / "00002.mpls").write_bytes(_make_mpls([("00002", 1400)]))                    # episode 2

    titles = bdmv._disc_titles(disc)
    names = sorted(c.name for t in titles for c in t["clips"])
    assert len(titles) == 2                        # play-all superset dropped
    assert names == ["00001.m2ts", "00002.m2ts"]   # both episodes kept


def test_fallback_to_size_heuristic_without_playlists(tmp_path, monkeypatch):
    monkeypatch.setattr(bdmv, "_MIN_TITLE_BYTES", 1000)
    disc = tmp_path / "lib3" / "NoPlaylist"
    stream = disc / "BDMV" / "STREAM"
    stream.mkdir(parents=True)
    (stream / "00001.m2ts").write_bytes(b"x" * 4096)   # real
    (stream / "00002.m2ts").write_bytes(b"x" * 100)    # tiny (menu)
    titles = bdmv._disc_titles(disc)
    assert [c.name for t in titles for c in t["clips"]] == ["00001.m2ts"]


def test_find_discs_flags_converted_titles(tmp_path, monkeypatch):
    monkeypatch.setattr(bdmv, "_MIN_DURATION_SEC", 60)
    lib = tmp_path / "lib4"
    done = lib / "Done"
    _mk_disc(done, ["00001"])
    (done / "BDMV" / "PLAYLIST" / "00000.mpls").write_bytes(_make_mpls([("00001", 1400)]))
    (done / "Done.mp4").write_bytes(b"x" * 2048)  # output already exists
    todo = lib / "Todo"
    _mk_disc(todo, ["00001"])
    (todo / "BDMV" / "PLAYLIST" / "00000.mpls").write_bytes(_make_mpls([("00001", 1400)]))
    with SessionLocal() as db:
        db.add(Library(path=str(lib), name="L4", group_depth=0))
        db.commit()

    discs = {d["name"]: d for d in bdmv.find_discs() if str(lib) in d["path"]}
    assert discs["Done"]["titles"][0]["converted"] is True
    assert discs["Todo"]["titles"][0]["converted"] is False


def test_delete_outputs_only_removes_known_converted(tmp_path, monkeypatch):
    monkeypatch.setattr(bdmv, "_MIN_DURATION_SEC", 60)
    lib = tmp_path / "lib5"
    disc = lib / "Movie"
    _mk_disc(disc, ["00001"])
    (disc / "BDMV" / "PLAYLIST" / "00000.mpls").write_bytes(_make_mpls([("00001", 1400)]))
    out = disc / "Movie.mp4"
    out.write_bytes(b"x" * 2048)
    bogus = tmp_path / "elsewhere.mp4"
    bogus.write_bytes(b"x" * 8)
    with SessionLocal() as db:
        db.add(Library(path=str(lib), name="L5", group_depth=0))
        db.commit()

    n = bdmv.delete_outputs([str(out), str(bogus)])
    assert n == 1
    assert not out.exists()   # the converted output was removed
    assert bogus.exists()     # a path outside known outputs is refused


def test_build_cmd_burns_subtitles_only_when_requested(tmp_path):
    clips = [tmp_path / "a.m2ts"]
    on = " ".join(bdmv._build_cmd(clips, tmp_path / "o.tmp.mp4", True))
    off = " ".join(bdmv._build_cmd(clips, tmp_path / "o.tmp.mp4", False))
    assert "-filter_complex" in on and "[0:s:0]overlay" in on
    assert "-filter_complex" not in off and "-map 0:v:0" in off


@needs_ffmpeg
def test_first_subtitle_index_detects_subs(tmp_path):
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    withsub = tmp_path / "withsub.mkv"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "testsrc=d=1:s=64x64:r=5", "-i", str(srt),
         "-c:v", "libx264", "-c:s", "srt", "-y", str(withsub)],
        capture_output=True,
    )
    nosub = tmp_path / "nosub.mp4"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "testsrc=d=1:s=64x64:r=5", "-c:v", "libx264", "-y", str(nosub)],
        capture_output=True,
    )
    assert bdmv._first_subtitle_index(withsub) == 0
    assert bdmv._first_subtitle_index(nosub) is None


@needs_ffmpeg
def test_convert_one_produces_playable_mp4(tmp_path):
    src = tmp_path / "title.m2ts"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "testsrc=d=1:s=320x240:r=10",
         "-f", "lavfi", "-i", "sine=d=1", "-c:v", "mpeg2video", "-c:a", "mp2", "-y", str(src)],
        capture_output=True,
    )
    out = tmp_path / "out.mp4"
    assert bdmv._convert_one([src], out, 1.0) is None  # None == success
    assert out.is_file() and out.stat().st_size > 0
