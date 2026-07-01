# Contributing to Streamva

Thanks for your interest! Streamva is a self-hosted course player — point it at a
folder of downloaded courses and browse/play them like Udemy. This guide covers
local setup, conventions, and how to propose changes.

> **License of contributions:** Streamva is licensed under **AGPL-3.0**. By
> submitting a contribution you agree it is licensed under the same terms (see
> [LICENSE](LICENSE)).

## Project layout
```
backend/    FastAPI app, SQLAlchemy models, Alembic, scanner, tests
frontend/   React + TypeScript SPA (Vite) — builds into backend/app/static
deploy/     Proxmox LXC install scripts
docs/       deployment guide
```
The backend is small and modular — `backend/app/scanner/` (filesystem → courses),
`routers/` (API), `streaming.py`/`transcode.py` (media). Read those plus the API
docs at `/docs` to understand the design.

## Dev setup

**Backend** (Python 3.12+):
```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate        # Windows;  .venv/bin/activate on Linux/macOS
pip install -r requirements-dev.txt
cp .env.example .env            # set STREAMVA_CONFIG or STREAMVA_COURSES_DIR
uvicorn app.main:app --reload   # http://localhost:8000  (API docs at /docs)
```

**Frontend** (Node 20+):
```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api -> :8000)
```
The dev server proxies `/api` to the backend; for production the SPA builds into
`backend/app/static` and is served by FastAPI.

## Before you open a PR

Run these and make sure they're green:
```bash
# backend
cd backend && pytest && ruff check .
# frontend (type-check + production build)
cd frontend && npm run build
```

- **Add tests** for new backend behavior (see `backend/tests/`). Scanner logic in
  particular should have a unit test against a temp fixture tree.
- **Keep the style of the surrounding code.** Backend: ruff-clean, type hints,
  small focused modules. Frontend: TypeScript strict, no `any` unless unavoidable.
- **Don't commit** secrets or generated artifacts — `.env`, `streamva.yaml`,
  `data/`, `node_modules/`, `.venv/`, and `backend/app/static/` are git-ignored.
- If you change the data model, generate a migration:
  `cd backend && alembic revision --autogenerate -m "..."`.

## Pull requests
- Branch from `main`; keep PRs focused and reasonably small.
- Describe **what** changed and **why**; reference any issue.
- Note if you validated against real course folders (structure varies a lot —
  the scanner is designed to adapt; new layouts are welcome as test fixtures).
- CI/maintainer review must pass before merge.

## Reporting bugs / requesting features
Open a GitHub issue with:
- what you expected vs. what happened,
- for scanner issues, a sketch of the folder layout (a `tree` snippet is ideal),
- relevant logs (`journalctl -u streamva` for LXC, or the uvicorn console).

## Good first contributions
- ffmpeg-generated cover thumbnails + ffprobe durations (Phase 4 optional).
- HLS segmenting for seekable `.mkv`/`.ts` (current remux is progressive).
- Notes/bookmarks per lecture; keyboard shortcuts; PWA.

Thanks for helping make Streamva better! 🎓
