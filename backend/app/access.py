"""Per-library access control.

Admins and users with ``all_libraries`` see everything; otherwise a user sees
only the libraries explicitly granted via ``library_access``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Course, LibraryAccess, User


def accessible_library_ids(db: Session, user: User) -> set[int] | None:
    """Return the set of library ids the user may see, or ``None`` for *all*."""
    if user.is_admin or user.all_libraries:
        return None
    return set(
        db.scalars(select(LibraryAccess.library_id).where(LibraryAccess.user_id == user.id)).all()
    )


def can_access_course(db: Session, user: User, course: Course) -> bool:
    ids = accessible_library_ids(db, user)
    return ids is None or course.library_id in ids
