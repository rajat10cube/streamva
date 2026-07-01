"""Admin user management (accounts + per-library access)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..auth import hash_password, require_admin
from ..db import get_db
from ..models import LibraryAccess, User

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


class UserIn(BaseModel):
    username: str
    password: str
    is_admin: bool = False
    all_libraries: bool = True
    library_ids: list[int] = []


class PasswordReset(BaseModel):
    password: str


class AccessIn(BaseModel):
    all_libraries: bool
    library_ids: list[int] = []


def _access_map(db: Session) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for uid, lid in db.execute(select(LibraryAccess.user_id, LibraryAccess.library_id)).all():
        out.setdefault(uid, []).append(lid)
    return out


def _json(u: User, amap: dict[int, list[int]]) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "isAdmin": u.is_admin,
        "allLibraries": u.all_libraries,
        "libraryIds": amap.get(u.id, []),
    }


@router.get("")
def list_users(db: Session = Depends(get_db)) -> list[dict]:
    amap = _access_map(db)
    return [_json(u, amap) for u in db.scalars(select(User).order_by(User.id)).all()]


@router.post("", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db)) -> dict:
    username = body.username.strip()
    if not username or len(body.password) < 4:
        raise HTTPException(400, "Username required and password must be at least 4 characters")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, "Username already exists")
    user = User(
        username=username,
        password_hash=hash_password(body.password),
        is_admin=body.is_admin,
        all_libraries=body.all_libraries,
    )
    db.add(user)
    db.flush()
    if not body.all_libraries:
        for lid in set(body.library_ids):
            db.add(LibraryAccess(user_id=user.id, library_id=lid))
    db.commit()
    return _json(user, _access_map(db))


@router.put("/{user_id}/access")
def set_access(user_id: int, body: AccessIn, db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    user.all_libraries = body.all_libraries
    db.execute(delete(LibraryAccess).where(LibraryAccess.user_id == user_id))
    if not body.all_libraries:
        for lid in set(body.library_ids):
            db.add(LibraryAccess(user_id=user_id, library_id=lid))
    db.commit()
    return {"ok": True}


@router.post("/{user_id}/password")
def reset_password(user_id: int, body: PasswordReset, db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if len(body.password) < 4:
        raise HTTPException(400, "Password is too short")
    user.password_hash = hash_password(body.password)
    db.commit()
    return {"ok": True}


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(400, "You can't delete your own account")
    if user.is_admin:
        admins = db.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True)))
        if admins <= 1:
            raise HTTPException(400, "Can't delete the last admin")
    db.delete(user)
    db.commit()
