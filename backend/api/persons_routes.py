"""
Authorized Persons Management API
Full CRUD + image upload + activity tracking for authorized personnel registry.
"""
import json
import base64
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session
import numpy as np
import cv2

from backend.database.database import get_db
from backend.database.models import AuthorizedPersonModel, EventModel
from backend.ai.identity_service import identity_service
from backend.websocket.manager import ws_manager
from backend.config import get_settings
from backend.logger import logger

router = APIRouter(prefix="/api/persons", tags=["Authorized Persons Management"])
settings = get_settings()


# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class PersonCreate(BaseModel):
    person_id: str = Field(..., min_length=3, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    employee_id: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    access_level: str = "STANDARD"  # VISITOR, STANDARD, ELEVATED, ADMIN
    status: str = "AUTHORIZED"
    allowed_zones: List[str] = ["ZONE_A", "ZONE_B"]
    valid_from: Optional[str] = None   # ISO datetime string
    valid_until: Optional[str] = None  # ISO datetime string
    notes: Optional[str] = None
    image_base64: Optional[str] = None  # base64-encoded reference image


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    employee_id: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    access_level: Optional[str] = None
    status: Optional[str] = None
    allowed_zones: Optional[List[str]] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    notes: Optional[str] = None
    image_base64: Optional[str] = None


def _parse_dt(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _person_to_dict(p: AuthorizedPersonModel) -> Dict[str, Any]:
    try:
        zones = json.loads(p.allowed_zones) if p.allowed_zones else []
    except Exception:
        zones = []

    return {
        "person_id": p.person_id,
        "name": p.name,
        "employee_id": p.employee_id,
        "department": p.department,
        "role": p.role,
        "phone": p.phone,
        "email": p.email,
        "access_level": p.access_level or "STANDARD",
        "status": p.status,
        "allowed_zones": zones,
        "valid_from": p.valid_from.isoformat() if p.valid_from else None,
        "valid_until": p.valid_until.isoformat() if p.valid_until else None,
        "reference_image_path": p.reference_image_path,
        "has_face_embedding": p.reference_embedding is not None,
        "detection_count": p.detection_count or 0,
        "last_detected_at": p.last_detected_at.isoformat() if p.last_detected_at else None,
        "last_detected_zone": p.last_detected_zone,
        "notes": p.notes,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _decode_base64_image(b64_str: str) -> Optional[np.ndarray]:
    try:
        raw = base64.b64decode(b64_str.split(",")[-1])
        arr = np.frombuffer(raw, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.warning(f"[PERSONS] Failed to decode base64 image: {e}")
        return None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("")
def list_persons(
    status: Optional[str] = None,
    department: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all authorized persons with optional filtering."""
    q = db.query(AuthorizedPersonModel)
    if status:
        q = q.filter(AuthorizedPersonModel.status == status.upper())
    if department:
        q = q.filter(AuthorizedPersonModel.department == department)
    if search:
        term = f"%{search}%"
        q = q.filter(
            (AuthorizedPersonModel.name.ilike(term)) |
            (AuthorizedPersonModel.person_id.ilike(term)) |
            (AuthorizedPersonModel.employee_id.ilike(term)) |
            (AuthorizedPersonModel.department.ilike(term)) |
            (AuthorizedPersonModel.role.ilike(term))
        )
    persons = q.order_by(AuthorizedPersonModel.name).all()
    return {
        "count": len(persons),
        "persons": [_person_to_dict(p) for p in persons]
    }


@router.get("/{person_id}")
def get_person(person_id: str, db: Session = Depends(get_db)):
    """Get a single authorized person by ID."""
    p = db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == person_id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found.")
    return _person_to_dict(p)


@router.post("")
async def create_person(payload: PersonCreate, db: Session = Depends(get_db)):
    """Create a new authorized person and enroll face in identity service."""
    # Check uniqueness
    existing = db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == payload.person_id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Person ID '{payload.person_id}' already exists.")

    # Decode image if provided
    image_np = None
    if payload.image_base64:
        image_np = _decode_base64_image(payload.image_base64)

    # Save snapshot and extract embedding
    snap_path = None
    embedding_json = None
    if image_np is not None:
        snap_dir = settings.snapshots_dir
        snap_file = f"person_{payload.person_id}_{int(time.time())}.jpg"
        snap_full = snap_dir / snap_file
        cv2.imwrite(str(snap_full), image_np)
        snap_path = f"/storage/snapshots/{snap_file}"
        embedding = identity_service._extract_raw_embedding(image_np)
        if embedding is not None:
            embedding_json = json.dumps(embedding.tolist())

    person = AuthorizedPersonModel(
        person_id=payload.person_id,
        name=payload.name,
        employee_id=payload.employee_id,
        department=payload.department,
        role=payload.role,
        phone=payload.phone,
        email=payload.email,
        access_level=payload.access_level,
        status=payload.status,
        allowed_zones=json.dumps(payload.allowed_zones),
        valid_from=_parse_dt(payload.valid_from),
        valid_until=_parse_dt(payload.valid_until),
        notes=payload.notes,
        reference_image_path=snap_path,
        reference_embedding=embedding_json,
        detection_count=0,
    )
    db.add(person)
    db.commit()
    db.refresh(person)

    # Refresh identity service gallery
    identity_service.refresh_gallery()
    logger.info(f"[PERSONS] Created person {payload.person_id} ({payload.name})")

    await ws_manager.broadcast({
        "type": "PERSON_ENROLLED",
        "person_id": payload.person_id,
        "name": payload.name,
        "status": payload.status
    })

    return {"status": "CREATED", "person": _person_to_dict(person)}


@router.put("/{person_id}")
async def update_person(person_id: str, payload: PersonUpdate, db: Session = Depends(get_db)):
    """Update an authorized person's profile."""
    p = db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == person_id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found.")

    if payload.name is not None:
        p.name = payload.name
    if payload.employee_id is not None:
        p.employee_id = payload.employee_id
    if payload.department is not None:
        p.department = payload.department
    if payload.role is not None:
        p.role = payload.role
    if payload.phone is not None:
        p.phone = payload.phone
    if payload.email is not None:
        p.email = payload.email
    if payload.access_level is not None:
        p.access_level = payload.access_level
    if payload.status is not None:
        p.status = payload.status.upper()
    if payload.allowed_zones is not None:
        p.allowed_zones = json.dumps(payload.allowed_zones)
    if payload.valid_from is not None:
        p.valid_from = _parse_dt(payload.valid_from)
    if payload.valid_until is not None:
        p.valid_until = _parse_dt(payload.valid_until)
    if payload.notes is not None:
        p.notes = payload.notes

    # Handle image update
    if payload.image_base64:
        image_np = _decode_base64_image(payload.image_base64)
        if image_np is not None:
            snap_dir = settings.snapshots_dir
            snap_file = f"person_{person_id}_{int(time.time())}.jpg"
            cv2.imwrite(str(snap_dir / snap_file), image_np)
            p.reference_image_path = f"/storage/snapshots/{snap_file}"
            embedding = identity_service._extract_raw_embedding(image_np)
            if embedding is not None:
                p.reference_embedding = json.dumps(embedding.tolist())

    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(p)

    identity_service.refresh_gallery()
    logger.info(f"[PERSONS] Updated person {person_id}")

    await ws_manager.broadcast({
        "type": "PERSON_UPDATED",
        "person_id": person_id,
        "status": p.status
    })

    return {"status": "UPDATED", "person": _person_to_dict(p)}


@router.post("/{person_id}/disable")
async def disable_person(person_id: str, db: Session = Depends(get_db)):
    """Disable an authorized person (revoke access)."""
    p = db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == person_id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found.")
    p.status = "DISABLED"
    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    identity_service.refresh_gallery()
    await ws_manager.broadcast({"type": "PERSON_DISABLED", "person_id": person_id})
    return {"status": "DISABLED", "person_id": person_id}


@router.post("/{person_id}/enable")
async def enable_person(person_id: str, db: Session = Depends(get_db)):
    """Re-enable a disabled authorized person."""
    p = db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == person_id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found.")
    p.status = "AUTHORIZED"
    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    identity_service.refresh_gallery()
    await ws_manager.broadcast({"type": "PERSON_ENABLED", "person_id": person_id})
    return {"status": "AUTHORIZED", "person_id": person_id}


@router.delete("/{person_id}")
async def delete_person(person_id: str, db: Session = Depends(get_db)):
    """Remove a person from registry permanently."""
    p = db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == person_id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found.")
    db.delete(p)
    db.commit()
    identity_service.refresh_gallery()
    logger.info(f"[PERSONS] Deleted person {person_id}")
    await ws_manager.broadcast({"type": "PERSON_DELETED", "person_id": person_id})
    return {"status": "DELETED", "person_id": person_id}


@router.get("/{person_id}/activity")
def get_person_activity(person_id: str, db: Session = Depends(get_db)):
    """Get detection activity history for a person."""
    p = db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == person_id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found.")

    # Pull related security events from events table
    events = db.query(EventModel).filter(
        EventModel.description.ilike(f"%{p.name}%") |
        EventModel.object_id.ilike(f"%{person_id}%")
    ).order_by(EventModel.start_time.desc()).limit(50).all()

    activity = [
        {
            "event_id": e.id,
            "event_type": e.event_type,
            "severity": e.severity,
            "zone_id": e.zone_id,
            "camera_id": e.camera_id,
            "confidence": e.confidence,
            "timestamp": e.start_time.isoformat() if e.start_time else None,
            "status": e.status,
        }
        for e in events
    ]

    return {
        "person_id": person_id,
        "name": p.name,
        "detection_count": p.detection_count or 0,
        "last_detected_at": p.last_detected_at.isoformat() if p.last_detected_at else None,
        "last_detected_zone": p.last_detected_zone,
        "activity": activity
    }


@router.get("/stats/summary")
def get_persons_summary(db: Session = Depends(get_db)):
    """Get summary statistics for the authorized persons registry."""
    all_persons = db.query(AuthorizedPersonModel).all()
    now = datetime.now(timezone.utc)

    authorized = sum(1 for p in all_persons if p.status == "AUTHORIZED")
    disabled = sum(1 for p in all_persons if p.status == "DISABLED")
    expired = sum(1 for p in all_persons if p.valid_until and p.valid_until < now)

    return {
        "total": len(all_persons),
        "authorized": authorized,
        "disabled": disabled,
        "expired": expired,
        "with_face": sum(1 for p in all_persons if p.reference_embedding is not None),
    }
