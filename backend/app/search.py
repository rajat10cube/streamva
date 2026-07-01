"""SQLite FTS5 full-text search over courses + lectures."""

from __future__ import annotations

import re

FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5("
    "kind UNINDEXED, ref_id UNINDEXED, slug UNINDEXED, title, context, "
    "tokenize='porter unicode61')"
)

_TOKEN = re.compile(r"\w+", re.UNICODE)


def ensure_fts(conn) -> None:
    conn.exec_driver_sql(FTS_DDL)


def rebuild_index(conn) -> None:
    """Rebuild the whole index from current course/lecture rows (cheap)."""
    ensure_fts(conn)
    conn.exec_driver_sql("DELETE FROM search_fts")
    conn.exec_driver_sql(
        "INSERT INTO search_fts (kind, ref_id, slug, title, context) "
        "SELECT 'course', id, slug, title, COALESCE(category, '') "
        "FROM course WHERE missing = 0"
    )
    conn.exec_driver_sql(
        "INSERT INTO search_fts (kind, ref_id, slug, title, context) "
        "SELECT 'lecture', l.id, c.slug, l.title, c.title "
        "FROM lecture l JOIN course c ON c.id = l.course_id "
        "WHERE c.missing = 0"
    )


def build_match(q: str) -> str:
    """Turn free text into a safe FTS5 prefix-AND query (e.g. ``climb* system*``)."""
    return " ".join(f"{t}*" for t in _TOKEN.findall(q or ""))


def run_search(conn, q: str, limit: int = 50) -> list[dict]:
    match = build_match(q)
    if not match:
        return []
    rows = conn.exec_driver_sql(
        "SELECT kind, ref_id, slug, title, context FROM search_fts "
        "WHERE search_fts MATCH ? ORDER BY rank LIMIT ?",
        (match, limit),
    ).fetchall()
    return [
        {"kind": r[0], "refId": r[1], "slug": r[2], "title": r[3], "context": r[4]}
        for r in rows
    ]
