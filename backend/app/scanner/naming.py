"""Order-token extraction, title cleanup, natural sort, and slugs."""

from __future__ import annotations

import os
import re
import unicodedata

# Leading order tokens, tried in order. The capture group is the order number.
_ORDER_PATTERNS = [
    re.compile(r"^\s*(\d{1,4})\s*[-_.)\]]\s*"),                      # "01 - ", "12. ", "3) ", "[04] "
    re.compile(r"^\s*(\d{1,4})\s+(?=\S)"),                           # "001 Title", "1 Title"
    re.compile(
        r"^\s*(?:lesson|lecture|part|chapter|module|section|day|ep|episode)"
        r"\s*0*(\d{1,4})\b[\s:_.\-]*",
        re.IGNORECASE,
    ),
]

# Conservative provider/site suffixes to strip from titles.
_SUFFIXES = [
    re.compile(r"\s*[-–]\s*Stylized Station'?s Crafting Hall\s*$", re.IGNORECASE),
    re.compile(r"\s*\[\d{3,4}p\]\s*$", re.IGNORECASE),
]

_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_LANG_TAG_RE = re.compile(r"[._-][A-Za-z]{2,3}$")


def extract_order(name: str) -> tuple[int | None, str]:
    """Return ``(number, remainder)`` after stripping a leading order token."""
    for pat in _ORDER_PATTERNS:
        m = pat.match(name)
        if m:
            return int(m.group(1)), name[m.end():]
    return None, name


def clean_title(name: str, *, strip_ext: bool = True) -> str:
    """Derive a human title from a file or folder name (cosmetic only)."""
    title = name
    if strip_ext:
        title = _EXT_RE.sub("", title)
    _, title = extract_order(title)
    for pat in _SUFFIXES:
        title = pat.sub("", title)
    title = title.replace("_", " ")
    title = re.sub(r"[\s.\-–]+", " ", title).strip(" -._–")
    return title or name


def _nat_chunks(s: str) -> list[tuple]:
    """Split into typed chunks so int/str never get compared directly."""
    out: list[tuple] = []
    for tok in re.split(r"(\d+)", s.lower()):
        if tok == "":
            continue
        if tok.isdigit():
            out.append((0, int(tok), ""))
        else:
            out.append((1, 0, tok))
    return out


def sort_key(name: str) -> tuple:
    """Natural sort key: numbered items first (by number), then natural alpha."""
    num, rem = extract_order(name)
    return (0 if num is not None else 1, num if num is not None else 0, _nat_chunks(rem))


def subtitle_base(stem: str) -> str:
    """Strip a trailing 2-3 letter language tag (``Intro_en`` -> ``Intro``)."""
    m = _LANG_TAG_RE.search(stem)
    return stem[: m.start()] if m else stem


def media_stem(filename: str) -> str:
    return os.path.splitext(filename)[0]


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or "course"
