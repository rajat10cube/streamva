"""Authentication: multi-user with hashed passwords + cookie sessions.

Current user is resolved from the session cookie (set by the login page) or an
HTTP Basic header (API/CLI). 401 is returned *without* WWW-Authenticate so the
browser never shows its native popup. With ``auth=none`` everyone acts as the
bootstrap admin (single-user mode).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal, get_db
from .models import User

_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    if user and verify_password(password, user.password_hash):
        return user
    return None


def ensure_admin() -> None:
    """Seed an admin only when explicitly configured, or in single-user mode.

    Default (no ``STREAMVA_AUTH_PASS``): leave the user table empty so the first
    visit shows a one-time signup that creates the master admin in the UI.
    """
    import secrets as _secrets

    s = get_settings()
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return
        if s.auth == "none":
            # single-user mode still needs a user row for progress; login is disabled
            password = _secrets.token_hex(16)
            db.add(User(username=s.auth_user or "admin",
                        password_hash=hash_password(password), is_admin=True))
            db.commit()
        elif s.auth_pass:
            # operator-preset admin (e.g. Docker/automation) -> skip signup
            db.add(User(username=s.auth_user or "admin",
                        password_hash=hash_password(s.auth_pass), is_admin=True))
            db.commit()
        # else: leave empty -> first-run signup via the UI


def _basic_user(db: Session, header: str | None) -> User | None:
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    username, _, password = decoded.partition(":")
    return authenticate(db, username, password)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("uid")
    if uid is not None:
        user = db.get(User, uid)
        if user:
            return user
    user = _basic_user(db, request.headers.get("Authorization"))
    if user:
        return user
    if get_settings().auth == "none":
        return db.scalar(select(User).order_by(User.id))  # single-user mode
    return None


def require_auth(user: User | None = Depends(get_current_user)) -> None:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")


def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if get_settings().auth != "none" and not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user
