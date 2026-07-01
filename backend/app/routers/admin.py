"""Admin endpoints: trigger and inspect library scans."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth import require_admin
from ..scanner.service import run_scan, scan_status

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/rescan")
def rescan(background: BackgroundTasks, wait: bool = False) -> dict:
    """Rescan all libraries.

    ``?wait=true`` runs synchronously and returns the summary; otherwise the
    scan runs in the background and the call returns immediately.
    """
    if wait:
        return run_scan()
    background.add_task(run_scan)
    return {"started": True}


@router.get("/scan-status")
def status() -> dict:
    return scan_status()
