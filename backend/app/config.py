"""Application configuration.

Scalar settings come from environment variables (prefix ``STREAMVA_``) and an
optional ``.env`` file. Library roots come from a YAML file (``STREAMVA_CONFIG``)
or, as a single-root fallback, from ``STREAMVA_COURSES_DIR``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LibraryConfig(BaseModel):
    """One scanned library root."""

    path: str
    # "auto" -> detect per library (recommended; survives reorganizing).
    # 0 -> each top-level folder is a course.
    # 1 -> top-level folder is a provider/category, course is one level down.
    group_depth: int | str = "auto"
    name: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STREAMVA_", env_file=".env", extra="ignore"
    )

    # --- storage ---
    config: str | None = None            # path to streamva.yaml (libraries)
    data_dir: Path = Path("./data")      # sqlite + caches
    database_url: str | None = None

    # --- single-root fallback (used when no YAML config given) ---
    courses_dir: str | None = None

    # --- scanning ---
    scan_on_start: bool = True
    watch: bool = False
    section_max_depth: int = 2
    min_video_bytes: int = 1_000_000

    # --- media ---
    ffmpeg: str = "auto"                 # auto|on|off
    transcode: str = "on-demand"         # off|on-demand|pre-pass
    remux_cache_mb: int = 10240          # size cap for the .mkv->.mp4 remux cache (LRU)
    hwaccel: str = "none"                # none|vaapi|qsv (Intel Quick Sync via /dev/dri)
    hwaccel_device: str = "/dev/dri/renderD128"
    # binaries + VA driver dir — point these at jellyfin-ffmpeg for a modern,
    # HW-accel-ready ffmpeg with bundled Intel drivers (e.g. /usr/lib/jellyfin-ffmpeg).
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    libva_drivers_path: str = ""         # LIBVA_DRIVERS_PATH for hardware transcoding

    # --- auth ---
    auth: str = "basic"                  # none|basic (basic = require login)
    auth_user: str = "admin"
    auth_pass: str = ""                   # empty -> first-run signup creates the admin in the UI
    secret_key: str | None = None        # session signing key (auto-persisted if unset)

    # --- serving ---
    base_path: str = "/"
    dev_cors: bool = True                # allow the Vite dev origin (localhost:5173)

    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(self.data_dir / 'streamva.db').as_posix()}"

    def session_secret(self) -> str:
        """Stable signing key for session cookies (persisted so logins survive restarts)."""
        import secrets as _secrets

        if self.secret_key:
            return self.secret_key
        self.data_dir.mkdir(parents=True, exist_ok=True)
        f = self.data_dir / "secret.key"
        if f.exists():
            return f.read_text(encoding="utf-8").strip()
        value = _secrets.token_hex(32)
        f.write_text(value, encoding="utf-8")
        try:
            f.chmod(0o600)
        except OSError:
            pass
        return value

    def libraries(self) -> list[LibraryConfig]:
        if self.config:
            raw = yaml.safe_load(Path(self.config).read_text(encoding="utf-8")) or {}
            return [LibraryConfig(**lib) for lib in raw.get("libraries", [])]
        if self.courses_dir:
            return [LibraryConfig(path=self.courses_dir, group_depth=0)]
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
