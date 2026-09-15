"""
Site Configuration API
Manages the physical surveillance site location, coordinates, and metadata.
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.database.models import SiteConfigModel
from backend.websocket.manager import ws_manager
from backend.logger import logger

router = APIRouter(prefix="/api/site", tags=["Site Configuration"])


class SiteConfigPayload(BaseModel):
    site_id: str = "SITE-001"
    site_name: str = Field(..., min_length=1, max_length=200)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    description: Optional[str] = None
    map_provider: str = "OFFLINE"  # OFFLINE, OPENSTREETMAP, CUSTOM
    map_api_key: Optional[str] = None


def _site_to_dict(s: SiteConfigModel) -> dict:
    return {
        "site_id": s.site_id,
        "site_name": s.site_name,
        "address": s.address,
        "city": s.city,
        "state": s.state,
        "country": s.country,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "description": s.description,
        "map_provider": s.map_provider,
        "has_api_key": s.map_api_key is not None and len(s.map_api_key) > 0,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("")
@router.get("/config")
def get_site_config(db: Session = Depends(get_db)):
    """Get the current site configuration."""
    site = db.query(SiteConfigModel).first()
    if not site:
        return {"configured": False, "site": None}
    return {"configured": True, "site": _site_to_dict(site)}


@router.post("")
async def save_site_config(payload: SiteConfigPayload, db: Session = Depends(get_db)):
    """Create or update the site configuration."""
    site = db.query(SiteConfigModel).filter(SiteConfigModel.site_id == payload.site_id).first()

    if site:
        site.site_name = payload.site_name
        site.address = payload.address
        site.city = payload.city
        site.state = payload.state
        site.country = payload.country
        site.latitude = payload.latitude
        site.longitude = payload.longitude
        site.description = payload.description
        site.map_provider = payload.map_provider
        if payload.map_api_key:
            site.map_api_key = payload.map_api_key
        site.updated_at = datetime.now(timezone.utc)
        action = "UPDATED"
    else:
        site = SiteConfigModel(
            site_id=payload.site_id,
            site_name=payload.site_name,
            address=payload.address,
            city=payload.city,
            state=payload.state,
            country=payload.country,
            latitude=payload.latitude,
            longitude=payload.longitude,
            description=payload.description,
            map_provider=payload.map_provider,
            map_api_key=payload.map_api_key,
        )
        db.add(site)
        action = "CREATED"

    db.commit()
    db.refresh(site)
    logger.info(f"[SITE] Site configuration {action}: {site.site_name}")

    await ws_manager.broadcast({
        "type": "SITE_CONFIG_UPDATED",
        "site_id": site.site_id,
        "site_name": site.site_name,
        "latitude": site.latitude,
        "longitude": site.longitude,
    })

    return {"status": action, "site": _site_to_dict(site)}


@router.delete("")
async def reset_site_config(db: Session = Depends(get_db)):
    """Reset the site configuration to defaults."""
    sites = db.query(SiteConfigModel).all()
    for s in sites:
        db.delete(s)
    db.commit()
    logger.info("[SITE] Site configuration reset.")
    return {"status": "RESET"}
