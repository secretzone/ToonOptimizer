"""GET/PUT/DELETE /reports (see API.md "Reports")."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from toonopt import reports as reports_store
from toonopt.models import CharacterReport
from toonopt.reports import ReportValidationError

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports() -> list[dict]:
    return reports_store.list_reports()


@router.get("/{slug}", response_model=CharacterReport)
def get_report(slug: str) -> CharacterReport:
    report = reports_store.get(slug)
    if report is None:
        raise HTTPException(404, f"no report for {slug!r}")
    return report


@router.put("/{slug}", response_model=CharacterReport)
def put_report(slug: str, report: CharacterReport) -> CharacterReport:
    try:
        return reports_store.save(slug, report)
    except ReportValidationError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/{slug}")
def delete_report(slug: str) -> dict:
    if not reports_store.delete(slug):
        raise HTTPException(404, f"no report for {slug!r}")
    return {"ok": True}
