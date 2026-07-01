# Streamva

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

A self-hosted **video streamer** for your own downloads. Point it at folders of
videos and get a browsable, searchable library with instant playback, animated
hover previews, resume-where-you-left-off, and per-user progress — from any
browser on your home server.

> Built for the homelab/Proxmox use case: it *plays* videos you already have
> organized in folders. It is **not** an authoring platform — no re-uploading or
> re-encoding your library.

## Library layout
Two levels, nothing to configure:
- **Top-level folders** become **collections** — a folder's videos play as a list.
- **Loose videos** in the library root are **standalone items** that play instantly.

## Features
- **Scanner** — folders → collections, loose videos → standalone items; natural
  sort, title cleanup, subtitle + cover detection, per-item isolation, and a
  rescan endpoint. Auto-generated ffmpeg thumbnails + durations.
- **Hover previews** — a storyboard of frames sampled across each video, cycled
  on hover (generated once with ffmpeg, cached and content-addressed).
- **Streaming** — efficient HTTP-range (path-traversal-guarded) `.mp4` direct
  play, `.ts` via `mpegts.js`, on-the-fly `.mkv` remux (`ffmpeg -c copy`),
  SRT→WebVTT subtitles.
- **Accounts** — **first-run admin signup**, then cookie-session login with
  **multiple users**: admins manage users + libraries; each user gets their **own
  progress**; **per-library access** (admins always see all). Hashed passwords
  (PBKDF2), self-serve password change. Basic auth also works for API/CLI.
- **Libraries** — add/remove video folders from the web UI (like Jellyfin), with
  a built-in folder browser; auto-scans on add.
- **Library UI** — searchable grid (SQLite FTS5); single videos play instantly,
  collections open a player + playlist; per-item options menu; resume + a
  continue-watching row.
- **Progress** — per-video position + completion (sticky at 90%) and a percentage
  per collection.
- **Deploy** — multi-stage Docker (ffmpeg bundled) + healthcheck, SPA deep-link
  fallback, reverse-proxy / subpath support, and Proxmox LXC install scripts.

## Stack
Python 3.12 · FastAPI · SQLite (→ Postgres later) · React + TypeScript · Docker.
Playback follows Jellyfin's tiering via ffmpeg: direct-play `.mp4`, `mpegts.js`
for `.ts`, `ffmpeg -c copy` remux for `.mkv`, transcode only as a rare fallback.

## Repo layout
```
backend/    FastAPI app, SQLAlchemy models, Alembic, scanner, tests
frontend/   React + TS SPA (Vite) — builds into backend/app/static
deploy/     Proxmox LXC install scripts
docs/       deployment guide
Dockerfile, docker-compose.yml, streamva.yaml.example
```

## Dev quickstart

**Backend** (from `backend/`):
```bash
python -m venv .venv
. .venv/Scripts/activate        # Windows;  use .venv/bin/activate on Linux/macOS
pip install -r requirements-dev.txt
cp .env.example .env            # set STREAMVA_COURSES_DIR or STREAMVA_CONFIG
uvicorn app.main:app --reload   # http://localhost:8000  (docs at /docs)
pytest                          # smoke tests
```

**Frontend** (from `frontend/`):
```bash
npm install
npm run dev                     # http://localhost:5173 (proxies /api -> :8000)
```

**Generate the first DB migration** (after models settle):
```bash
cd backend && alembic revision --autogenerate -m "baseline" && alembic upgrade head
```

## Deploy

**Docker:**
```bash
cp streamva.yaml.example streamva.yaml     # edit library paths (group_depth: auto)
# edit docker-compose.yml volume paths + STREAMVA_AUTH_PASS
docker compose up --build                # http://<host>:8800
```

**Proxmox LXC (no Docker)** — run on the PVE host; it's interactive
(Default/Advanced, auto-picks the CT ID) and installs Streamva as a `systemd`
service. You add your course folders afterwards in the app:
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/rajat10cube/streamva/main/ct/streamva.sh)"
```
See **[deploy/lxc/README.md](deploy/lxc/README.md)**. Reverse proxy:
**[docs/DEPLOY.md](docs/DEPLOY.md)**. Mount course libraries read-only; app state
lives in a data volume. Put it behind your existing reverse proxy / VPN.

## Accounts
On first launch Streamva shows a **one-time signup** to create your **master admin**
account (username + password) — nothing is preconfigured. After that it's a normal
**login page** (cookie session). Admins add more users in **Settings → Users**;
each user has their own watch progress. Passwords are hashed (PBKDF2) and users
change their own in **Settings → Account**. By default every user can see all
libraries; admins can restrict a user to specific libraries via **Settings →
Users → Access** (admins always see everything).

For automation you can pre-create the admin by setting `STREAMVA_AUTH_USER` /
`STREAMVA_AUTH_PASS` (skips signup). API/CLI clients may use HTTP Basic (`curl -u`).
Set `STREAMVA_AUTH=none` to disable auth entirely (single-user, LAN/VPN only).

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, conventions, and PR guidelines.

## License
Licensed under the **GNU Affero General Public License v3.0** — see [LICENSE](LICENSE).
AGPL covers network use: if you run a modified Streamva as a network service, you
must offer its users the corresponding modified source.
