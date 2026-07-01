"""File/directory classification (videos, audio, docs, subtitles, junk)."""

from __future__ import annotations

import os

VIDEO_NATIVE = {".mp4", ".m4v", ".webm", ".mov"}
VIDEO_TRANSCODE = {".mkv", ".ts", ".avi", ".flv"}
AUDIO = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav"}
DOCUMENT = {".pdf", ".html", ".htm", ".md", ".markdown", ".epub"}
SUBTITLE = {".srt", ".vtt", ".ass", ".sub"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
LINK = {".url", ".webloc"}

# Extensions we never surface (download cruft, engine/build junk, partials, sidecars).
IGNORE_EXT = {
    ".m3u8", ".part", ".partial", ".crdownload", ".tmp", ".log", ".dmp",
    ".runtime-xml", ".bin", ".pur", ".pth", ".cfg", ".assbin", ".list",
    ".in", ".nfo", ".ini", ".db",
}
IGNORE_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}

# Directories never descended into.
IGNORE_DIRS = {
    "temp", "@eadir", "#recycle", "$recycle.bin", "system volume information",
    "lost+found", "saved", "intermediate", "deriveddatacache", "binaries",
}

# Directories treated as a single "Project Files" resource bundle.
BUNDLE_DIR_NAMES = {
    "files", "content", "assets", "source", "startercontent",
    "project files", "projects", "project",
}


def classify(filename: str) -> tuple[str, str]:
    """Return ``(category, kind)``.

    category in {lecture, subtitle, image, link, resource, ignore};
    kind in {video, audio, document, ""}.
    """
    lname = filename.lower()
    ext = os.path.splitext(lname)[1]
    if lname in IGNORE_NAMES or ext in IGNORE_EXT:
        return ("ignore", "")
    if ext in VIDEO_NATIVE or ext in VIDEO_TRANSCODE:
        return ("lecture", "video")
    if ext in AUDIO:
        return ("lecture", "audio")
    if ext in DOCUMENT:
        return ("lecture", "document")
    if ext in SUBTITLE:
        return ("subtitle", "")
    if ext in IMAGE:
        return ("image", "")
    if ext in LINK:
        return ("link", "")
    return ("resource", "")
