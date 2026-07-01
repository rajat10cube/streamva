"""Filesystem walk: turn a video library into an in-memory tree.

The library layout is exactly two levels:
  - top-level folders     -> a collection of the videos directly inside it
  - loose top-level videos -> a standalone single-video item
There is no deeper nesting and no sections. Pure (no DB) — returns dataclasses
the sync layer persists.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from . import classify as C
from .naming import clean_title, media_stem, sort_key, subtitle_base

_COVER_PRIORITY = ["cover", "poster", "folder", "thumb", "banner"]


@dataclass
class SLecture:
    rel_path: str          # relative to the library root (lookup key)
    title: str
    kind: str
    mime: str | None
    size: int
    needs_transcode: bool
    section_rel: str       # always "" here (flat, single section)
    subtitle_rel: str | None
    sort: tuple


@dataclass
class SSection:
    rel: str
    title: str
    sort: tuple


@dataclass
class SAttachment:
    rel_path: str
    title: str
    kind: str
    mime: str | None
    size: int


@dataclass
class SCourse:
    rel_path: str          # relative to the library root (identity)
    title: str
    category: str | None
    cover_rel: str | None
    sections: list[SSection]
    lectures: list[SLecture]
    attachments: list[SAttachment] = field(default_factory=list)
    provider: str | None = None


def _rel(p: Path, base: Path) -> str:
    return p.relative_to(base).as_posix()


def _ignored(name: str) -> bool:
    return name.startswith(".") or name.lower() in C.IGNORE_DIRS


def _safe_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def _safe_iterdir(d: Path) -> list[Path]:
    try:
        return sorted(d.iterdir())
    except OSError:
        return []


def _is_media(name: str) -> bool:
    return C.classify(name)[0] == "lecture"


def _has_direct_media(d: Path) -> bool:
    try:
        return any(e.is_file() and _is_media(e.name) for e in d.iterdir())
    except OSError:
        return False


def discover_courses(lib_root: Path) -> Iterator[Path]:
    """Yield each item that becomes a collection: a top-level folder holding
    videos, or a loose top-level video file. Two levels only — no recursion."""
    for entry in _safe_iterdir(lib_root):
        if _ignored(entry.name):
            continue
        if entry.is_dir():
            if _has_direct_media(entry):
                yield entry
        elif entry.is_file() and _is_media(entry.name):
            yield entry


def walk_course(item: Path, lib_root: Path, min_video_bytes: int) -> SCourse | None:
    """Build a collection from a folder (its direct videos) or a single loose
    video file. Returns None if nothing playable is found."""
    is_file = item.is_file()
    scan_dir = item.parent if is_file else item
    dir_files = [e for e in _safe_iterdir(scan_dir) if e.is_file()]

    # subtitles sitting next to the videos, keyed by language-stripped stem
    subs: dict[str, str] = {}
    for f in dir_files:
        if C.classify(f.name)[0] == "subtitle":
            subs[subtitle_base(media_stem(f.name)).lower()] = _rel(f, lib_root)

    candidates = [item] if is_file else dir_files
    images: list[tuple[int, Path]] = []
    lectures: list[SLecture] = []
    for f in candidates:
        cat, kind = C.classify(f.name)
        if cat in ("ignore", "subtitle", "link", "resource"):
            continue
        if cat == "image":
            if not is_file:  # folder art is a possible cover
                stem = media_stem(f.name).lower()
                pr = _COVER_PRIORITY.index(stem) if stem in _COVER_PRIORITY else len(_COVER_PRIORITY)
                images.append((pr, f))
            continue
        size = _safe_size(f)
        if size == 0 or (kind == "video" and size < min_video_bytes):
            continue
        lectures.append(
            SLecture(
                rel_path=_rel(f, lib_root),
                title=clean_title(f.name),
                kind=kind,
                mime=mimetypes.guess_type(f.name)[0],
                size=size,
                needs_transcode=Path(f.name).suffix.lower() in C.VIDEO_TRANSCODE,
                section_rel="",
                subtitle_rel=subs.get(media_stem(f.name).lower()),
                sort=sort_key(f.name),
            )
        )

    if not lectures:
        return None
    lectures.sort(key=lambda lec: (lec.sort, lec.rel_path))

    cover_rel = None
    if images:
        images.sort(key=lambda t: t[0])
        cover_rel = _rel(images[0][1], lib_root)

    return SCourse(
        rel_path=_rel(item, lib_root),
        title=clean_title(item.name, strip_ext=is_file),
        category=None,
        cover_rel=cover_rel,
        sections=[SSection("", "Videos", (-1,))],
        lectures=lectures,
        attachments=[],
        provider=None,
    )
