"""
SENTINEL-AI: Master SIH 2026 Compliance REST Routes
Exposes the 12-Pillar Section 75 Self-Test and Architectural Integrity Audit.
"""

from fastapi import APIRouter
from typing import Dict, Any

from backend.system.sih_compliance import sih_compliance_auditor

router = APIRouter(prefix="/api/system/sih-compliance", tags=["Master SIH 2026 Compliance"])

@router.get("/audit")
def run_compliance_audit() -> Dict[str, Any]:
    """Executes full automated self-test across all 12 Section 75 core value propositions."""
    return sih_compliance_auditor.run_compliance_audit()
