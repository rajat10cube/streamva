"""Login / logout / session info / self password change (cookie-based)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import authenticate, get_current_user, hash_password, require_user, verify_password
from ..config import get_settings
from ..db import get_db
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class SetupIn(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


def _user_json(user: User) -> dict:
    return {
        "username": user.username,
        "isAdmin": user.is_admin,
        "authDisabled": get_settings().auth == "none",
    }


def _user_min(user: User) -> dict:
    return {"username": user.username, "isAdmin": user.is_admin}


@router.get("/status")
def status_(request: Request, db: Session = Depends(get_db)) -> dict:
    """Tells the SPA whether to show signup (first run), login, or the app."""
    s = get_settings()
    current = get_current_user(request, db)
    if s.auth == "none":
        return {"authDisabled": True, "needsSetup": False,
                "user": _user_min(current) if current else None}
    users = db.scalar(select(func.count()).select_from(User))
    return {
        "authDisabled": False,
        "needsSetup": users == 0,
        "user": _user_min(current) if current else None,
    }


@router.post("/setup")
def setup(body: SetupIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """One-time first-run: create the master admin account."""
    if get_settings().auth == "none":
        raise HTTPException(400, "Authentication is disabled")
    if db.scalar(select(func.count()).select_from(User)) > 0:
        raise HTTPException(409, "Already set up")
    username = body.username.strip()
    if not username or len(body.password) < 4:
        raise HTTPException(400, "Username required and password must be at least 4 characters")
    user = User(username=username, password_hash=hash_password(body.password), is_admin=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session["uid"] = user.id
    return _user_json(user)


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    if get_settings().auth == "none":
        return {"username": "guest", "isAdmin": True, "authDisabled": True}
    user = authenticate(db, body.username, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    request.session["uid"] = user.id
    return _user_json(user)


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(user: User | None = Depends(get_current_user)) -> dict:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return _user_json(user)


@router.post("/password")
def change_password(
    body: PasswordChange, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> dict:
    if get_settings().auth == "none":
        raise HTTPException(400, "Authentication is disabled")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if len(body.new_password) < 4:
        raise HTTPException(400, "New password is too short")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
