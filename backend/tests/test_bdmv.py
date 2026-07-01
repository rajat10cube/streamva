"""Blu-ray (BDMV) disc detection + conversion."""

import subprocess
from pathlib import Path

import pytest

from app import bdmv
from app.db import SessionLocal, init_db
from app.models import Library
from app.probe import ffmpeg_available

init_db()

needs_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")


def _mk_bdmv(disc: Path, sizes: list[int]) -> None:
    stream = disc / "BDMV" / "STREAM"
    stream.mkdir(parents=True, exist_ok=True)
    (disc / "BDMV" / "PLAYLIST").mkdir(exist_ok=True)
    for i, n in enumerate(sizes):
        (stream / f"{i:05d}.m2ts").write_bytes(b"x" * n)


def test_find_discs_detects_bdmv_and_skips_small_titles(tmp_path, monkeypatch):
    monkeypatch.setattr(bdmv, "_MIN_TITLE_BYTES", 1000)
    lib = tmp_path / "lib"
    _mk_bdmv(lib / "MovieA", [4096, 100])          # one real title + a tiny menu
    _mk_bdmv(lib / "sub" / "MovieB", [3000, 3000])  # nested disc, two episodes
    (lib / "NotADisc").mkdir(parents=True)
    with SessionLocal() as db:
        db.add(Library(path=str(lib), name="L", group_depth=0))
        db.commit()

    discs = {d["name"]: d for d in bdmv.find_discs() if str(lib) in d["path"]}
    assert discs["MovieA"]["titles"] == 1   # 100-byte menu skipped
    assert discs["MovieB"]["titles"] == 2   # nested + both episodes
    assert "NotADisc" not in discs


def test_already_converted_disc_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(bdmv, "_MIN_TITLE_BYTES", 1000)
    lib = tmp_path / "lib2"
    disc = lib / "MovieC"
    _mk_bdmv(disc, [4096])
    (disc / "MovieC.mp4").write_bytes(b"x" * 2048)  # a video already sits next to BDMV
    with SessionLocal() as db:
        db.add(Library(path=str(lib), name="L2", group_depth=0))
        db.commit()

    names = [d["name"] for d in bdmv.find_discs() if str(lib) in d["path"]]
    assert "MovieC" not in names


@needs_ffmpeg
def test_convert_one_produces_playable_mp4(tmp_path):
    src = tmp_path / "title.m2ts"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "testsrc=d=1:s=320x240:r=10",
         "-f", "lavfi", "-i", "sine=d=1", "-c:v", "mpeg2video", "-c:a", "mp2", "-y", str(src)],
        capture_output=True,
    )
    out = tmp_path / "out.mp4"
    assert bdmv._convert_one(src, out) is True
    assert out.is_file() and out.stat().st_size > 0
