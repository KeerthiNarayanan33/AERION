import hmac
import time
import json
import base64
import hashlib
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from pydantic import BaseModel

from backend.config import get_settings
from backend.logger import logger

settings = get_settings()

ROLE_LEVELS = {
    "OBSERVER": 1,
    "OPERATOR": 2,
    "COMMANDER": 3
}

class TokenRequestPayload(BaseModel):
    role: str = "COMMANDER"  # COMMANDER, OPERATOR, OBSERVER
    user_id: str = "officer_01"

def create_tactical_token(role: str, user_id: str, secret_key: Optional[str] = None) -> str:
    """Generates an HMAC-SHA256 authenticated tactical bearer token."""
    key = (secret_key or settings.SECRET_KEY).encode("utf-8")
    role = role.upper()
    if role not in ROLE_LEVELS:
        role = "OPERATOR"

    payload = {
        "user_id": user_id,
        "role": role,
        "created_at": time.time(),
        "exp": time.time() + (settings.DEFAULT_TOKEN_EXPIRY_HOURS * 3600)
    }

    raw_data = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    sig = hmac.new(key, raw_data.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"SENTINEL.{raw_data}.{sig}"

def verify_tactical_token(token: str, secret_key: Optional[str] = None) -> Dict[str, Any]:
    """Verifies HMAC signature and expiration for a tactical token."""
    key = (secret_key or settings.SECRET_KEY).encode("utf-8")
    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] != "SENTINEL":
        raise ValueError("Invalid tactical token format")

    raw_data, sig = parts[1], parts[2]
    expected_sig = hmac.new(key, raw_data.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Token signature verification failed - possible tampering")

    try:
        payload_bytes = base64.urlsafe_b64decode(raw_data.encode("utf-8"))
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise ValueError("Token payload could not be decoded")

    if payload.get("exp", 0) < time.time():
        raise ValueError("Token has expired")

    return payload

def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_sentinel_token: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    FastAPI dependency extracting active operator context.
    If SECURITY_AUTH_ENABLED is False, defaults to COMMANDER for seamless demonstration.
    """
    if not settings.SECURITY_AUTH_ENABLED:
        return {
            "user_id": "tactical_evaluator",
            "role": "COMMANDER",
            "auth_bypassed": True
        }

    token_str = None
    if authorization and authorization.lower().startswith("bearer "):
        token_str = authorization[7:].strip()
    elif x_sentinel_token:
        token_str = x_sentinel_token.strip()
    elif "token" in request.query_params:
        token_str = request.query_params["token"]

    if not token_str:
        raise HTTPException(status_code=401, detail="Tactical authentication token required (X-Sentinel-Token or Bearer)")

    try:
        return verify_tactical_token(token_str)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

def require_role(min_role: str):
    """Factory creating dependency to assert operator role meets minimum clearance."""
    min_level = ROLE_LEVELS.get(min_role.upper(), 1)

    def role_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = user.get("role", "OBSERVER").upper()
        user_level = ROLE_LEVELS.get(user_role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: Clearance [{user_role}] insufficient for operation requiring [{min_role.upper()}]"
            )
        return user

    return role_checker

router = APIRouter(prefix="/api/auth", tags=["Tactical Security & RBAC"])

@router.post("/token")
def issue_tactical_token(payload: TokenRequestPayload):
    """
    Issues an HMAC-SHA256 authenticated military bearer token for command evaluation (Section 53).
    """
    token = create_tactical_token(role=payload.role, user_id=payload.user_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": payload.role.upper(),
        "user_id": payload.user_id,
        "expires_in_hours": settings.DEFAULT_TOKEN_EXPIRY_HOURS
    }

@router.get("/roles")
def list_role_permissions():
    """Returns access control hierarchy and capability matrix."""
    return {
        "security_auth_enabled": settings.SECURITY_AUTH_ENABLED,
        "roles": {
            "COMMANDER": {
                "level": 3,
                "permissions": ["SYSTEM_CONFIG_MUTATE", "SCENARIOS_EXECUTE", "UAV_DISPATCH", "VAULT_EXPORT", "EVENTS_ACKNOWLEDGE", "EVENTS_RESOLVE"]
            },
            "OPERATOR": {
                "level": 2,
                "permissions": ["EVENTS_ACKNOWLEDGE", "EVENTS_RESOLVE", "EVIDENCE_REVIEW", "ANPR_SEARCH", "MANUAL_DETECT"]
            },
            "OBSERVER": {
                "level": 1,
                "permissions": ["TELEMETRY_VIEW", "RADAR_SWEEP_MONITOR", "CAMERA_STREAM_VIEW"]
            }
        }
    }

@router.get("/verify")
def verify_current_identity(user: Dict[str, Any] = Depends(get_current_user)):
    """Validates the active operator bearer token."""
    return {
        "status": "AUTHENTICATED",
        "user": user
    }
