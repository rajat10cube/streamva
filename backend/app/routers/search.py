"""Full-text search endpoint (courses + lectures), scoped to accessible libraries."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access import accessible_library_ids
from ..auth import require_user
from ..db import get_db
from ..models import Course, User
from ..search import run_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(q: str, user: User = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    results = run_search(db.connection(), q)
    allowed = accessible_library_ids(db, user)
    if allowed is not None:
        slugs = set(
            db.scalars(select(Course.slug).where(Course.library_id.in_(allowed))).all()
        )
        results = [r for r in results if r["slug"] in slugs]
    return {"results": results}
