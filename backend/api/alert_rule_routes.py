"""
Alert Rules Management API
Configurable IF-THEN alert rules for security event generation.
"""
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.database.models import AlertRuleModel
from backend.websocket.manager import ws_manager
from backend.logger import logger

router = APIRouter(prefix="/api/alert-rules", tags=["Alert Rules"])


class AlertRuleCondition(BaseModel):
    person_type: Optional[str] = None      # UNKNOWN, AUTHORIZED, UNVERIFIED, ANY
    zone_type: Optional[str] = None        # NORMAL, WARNING, RESTRICTED, ANY
    zone_access: Optional[str] = None      # PERMITTED, DENIED, ANY
    zone_id: Optional[str] = None          # specific zone ID or None for any


class AlertRuleAction(BaseModel):
    severity: str = "HIGH"                 # INFO, LOW, MEDIUM, HIGH, CRITICAL
    create_event: bool = True
    tracking: bool = False
    uav_assistance: bool = False
    operator_alert: bool = True


class AlertRulePayload(BaseModel):
    rule_id: str = Field(..., min_length=3, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    condition: AlertRuleCondition
    action: AlertRuleAction
    enabled: bool = True
    priority: int = Field(3, ge=1, le=5)


def _rule_to_dict(r: AlertRuleModel) -> Dict[str, Any]:
    try:
        condition = json.loads(r.condition_json)
    except Exception:
        condition = {}
    try:
        action = json.loads(r.action_json)
    except Exception:
        action = {}
    return {
        "rule_id": r.rule_id,
        "name": r.name,
        "description": r.description,
        "condition": condition,
        "action": action,
        "enabled": r.enabled,
        "priority": r.priority,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("")
def list_alert_rules(db: Session = Depends(get_db)):
    """List all configured alert rules ordered by priority."""
    rules = db.query(AlertRuleModel).order_by(AlertRuleModel.priority).all()
    return {"count": len(rules), "rules": [_rule_to_dict(r) for r in rules]}


@router.get("/{rule_id}")
def get_alert_rule(rule_id: str, db: Session = Depends(get_db)):
    r = db.query(AlertRuleModel).filter(AlertRuleModel.rule_id == rule_id).first()
    if not r:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")
    return _rule_to_dict(r)


@router.post("")
async def create_alert_rule(payload: AlertRulePayload, db: Session = Depends(get_db)):
    existing = db.query(AlertRuleModel).filter(AlertRuleModel.rule_id == payload.rule_id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Rule ID '{payload.rule_id}' already exists.")

    r = AlertRuleModel(
        rule_id=payload.rule_id,
        name=payload.name,
        description=payload.description,
        condition_json=json.dumps(payload.condition.model_dump(exclude_none=True)),
        action_json=json.dumps(payload.action.model_dump()),
        enabled=payload.enabled,
        priority=payload.priority,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    logger.info(f"[ALERT-RULES] Created rule {payload.rule_id}: {payload.name}")
    await ws_manager.broadcast({"type": "ALERT_RULE_CREATED", "rule_id": payload.rule_id})
    return {"status": "CREATED", "rule": _rule_to_dict(r)}


@router.put("/{rule_id}")
async def update_alert_rule(rule_id: str, payload: AlertRulePayload, db: Session = Depends(get_db)):
    r = db.query(AlertRuleModel).filter(AlertRuleModel.rule_id == rule_id).first()
    if not r:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")

    r.name = payload.name
    r.description = payload.description
    r.condition_json = json.dumps(payload.condition.model_dump(exclude_none=True))
    r.action_json = json.dumps(payload.action.model_dump())
    r.enabled = payload.enabled
    r.priority = payload.priority
    r.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(r)
    logger.info(f"[ALERT-RULES] Updated rule {rule_id}")
    await ws_manager.broadcast({"type": "ALERT_RULE_UPDATED", "rule_id": rule_id})
    return {"status": "UPDATED", "rule": _rule_to_dict(r)}


@router.post("/{rule_id}/toggle")
async def toggle_alert_rule(rule_id: str, db: Session = Depends(get_db)):
    """Enable or disable an alert rule."""
    r = db.query(AlertRuleModel).filter(AlertRuleModel.rule_id == rule_id).first()
    if not r:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")
    r.enabled = not r.enabled
    r.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ENABLED" if r.enabled else "DISABLED", "rule_id": rule_id, "enabled": r.enabled}


@router.delete("/{rule_id}")
async def delete_alert_rule(rule_id: str, db: Session = Depends(get_db)):
    r = db.query(AlertRuleModel).filter(AlertRuleModel.rule_id == rule_id).first()
    if not r:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")
    db.delete(r)
    db.commit()
    logger.info(f"[ALERT-RULES] Deleted rule {rule_id}")
    await ws_manager.broadcast({"type": "ALERT_RULE_DELETED", "rule_id": rule_id})
    return {"status": "DELETED", "rule_id": rule_id}
