"""Admin endpoints: trigger and inspect library scans."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from ..auth import require_admin
from ..bdmv import convert_all, convert_status, delete_outputs, find_discs
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
    """Blu-ray (BDMV) disc folders + their titles (converted ones flagged)."""
    discs = find_discs()
    titles = [t for d in discs for t in d["titles"]]
    return {
        "discs": discs,
        "count": len(discs),
        "pending": sum(1 for t in titles if not t["converted"]),
        "converted": sum(1 for t in titles if t["converted"]),
    }


@router.post("/bdmv/convert")
def bdmv_convert(background: BackgroundTasks, body: BdmvConvertIn | None = None) -> dict:
    targets = body.titles if body and body.titles else None
    background.add_task(convert_all, targets)
    return {"started": True}


@router.post("/bdmv/delete")
def bdmv_delete(body: BdmvConvertIn) -> dict:
    """Delete already-converted MP4 outputs by title id."""
    return {"deleted": delete_outputs(body.titles or [])}


@router.get("/bdmv/status")
def bdmv_convert_status() -> dict:
    return convert_status()
