from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.analytics.threat_heatmap import threat_heatmap_engine
from backend.analytics.shift_report import shift_report_generator

router = APIRouter(prefix="/api/analytics", tags=["Tactical Analytics & Heatmapping"])

@router.get("/threat-heatmap")
def get_threat_heatmap(
    grid_size: int = Query(25, ge=10, le=50, description="Spatial grid dimension (NxN)"),
    db: Session = Depends(get_db)
):
    """
    Returns 2D Gaussian breach density heatmap, corridor vulnerability rankings,
    and 24-hour temporal infiltration distribution (Sections 35 & 48).
    """
    return threat_heatmap_engine.generate_heatmap(db, grid_size=grid_size)

@router.get("/shift-report")
def get_shift_intelligence_report(db: Session = Depends(get_db)):
    """
    Returns structured operational KPIs, sensor uptimes, and threat distributions for 24h watch (Section 40).
    """
    return shift_report_generator.generate_shift_data(db)

@router.get("/shift-report/html", response_class=HTMLResponse)
def get_shift_intelligence_report_html(db: Session = Depends(get_db)):
    """
    Renders an official, print-ready, high-contrast Commander Briefing document for the active shift.
    """
    return HTMLResponse(content=shift_report_generator.generate_shift_report_html(db), status_code=200)

