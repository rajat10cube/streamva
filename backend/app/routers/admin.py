"""Admin endpoints: trigger and inspect library scans."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from ..auth import require_admin
from ..bdmv import convert_all, convert_status, find_discs
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


class BdmvConvertIn(BaseModel):
    titles: list[str] | None = None  # title ids (output paths); None/empty = all


@router.get("/bdmv")
def bdmv_discs() -> dict:
    """Blu-ray (BDMV) disc folders + their un-converted titles."""
    discs = find_discs()
    return {"discs": discs, "count": len(discs), "titles": sum(len(d["titles"]) for d in discs)}


@router.post("/bdmv/convert")
def bdmv_convert(background: BackgroundTasks, body: BdmvConvertIn | None = None) -> dict:
    targets = body.titles if body and body.titles else None
    background.add_task(convert_all, targets)
    return {"started": True}


@router.get("/bdmv/status")
def bdmv_convert_status() -> dict:
    return convert_status()
