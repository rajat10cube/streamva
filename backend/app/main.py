"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .config import get_settings
from .db import init_db
from .routers import (
    admin,
    auth,
    courses,
    health,
    lectures,
    libraries,
    media,
    notes,
    progress,
    search,
    users,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # also seeds the first admin (from configured creds) on first run
    from .scanner.service import run_scan, seed_libraries_from_config

    seed_libraries_from_config()  # first-run import from config/env, if any
    if settings.scan_on_start:
        # don't block startup; scan in a worker thread
        asyncio.get_event_loop().run_in_executor(None, run_scan)
    yield


def create_app() -> FastAPI:
    root_path = settings.base_path.rstrip("/") if settings.base_path not in ("", "/") else ""
    app = FastAPI(title="Streamva", version=__version__, lifespan=lifespan, root_path=root_path)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret(),
        same_site="lax",
        https_only=False,
        max_age=60 * 60 * 24 * 30,  # 30-day login
    )

    if settings.dev_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(courses.router, prefix="/api")
    app.include_router(lectures.router, prefix="/api")
    app.include_router(libraries.router, prefix="/api")
    app.include_router(media.router, prefix="/api")
    app.include_router(progress.router, prefix="/api")
    app.include_router(notes.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(users.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")

    # Serve the built SPA in production (single container). In dev, Vite serves it.
    # A catch-all returns index.html for client routes so a hard refresh on
    # /course/... doesn't 404; real asset files are served directly.
    spa_dir = (Path(__file__).resolve().parent / "static").resolve()
    index_file = spa_dir / "index.html"
    if index_file.is_file():

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            candidate = (spa_dir / full_path).resolve()
            if full_path and candidate.is_file() and spa_dir in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(index_file)

    return app


app = create_app()
