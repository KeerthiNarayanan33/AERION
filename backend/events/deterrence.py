"""
SENTINEL-AI: Multi-Stage Non-Lethal Deterrence Escalation Matrix
Sections 22 & 75: Graduated Border Rules of Engagement (ROE), LRAD Directed Voice Warnings, and Strobe Control.

Implements a 4-stage graduated deterrence state machine:
Stage 1: Optical 20Hz Strobe / Visual Advisory
Stage 2: LRAD Directed Multilingual Voice Warning (Hindi, Punjabi, English)
Stage 3: 115 dB Directional Acoustic Siren
Stage 4: Tactical Quick Reaction Team (QRT) Ground Intercept Directive
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from backend.logger import logger
from backend.websocket.manager import ws_manager

STAGES = {
    1: {
        "stage_id": 1,
        "code": "STAGE_1_OPTICAL_STROBE",
        "title": "Stage 1: 20 Hz Boundary Optical Strobe",
        "output_type": "OPTICAL_DAZZLER",
        "decibels": 0,
        "duration_seconds": 15,
        "description": "High-intensity optical strobe at 20 Hz flashes toward perimeter boundary for visual disorientation and sector marking.",
        "action": "Optical Strobe Activated (20 Hz pulsed)"
    },
    2: {
        "stage_id": 2,
        "code": "STAGE_2_DIRECTIONAL_VOICE",
        "title": "Stage 2: LRAD Directed Multilingual Voice Warning",
        "output_type": "ACOUSTIC_DIRECTIONAL_VOICE",
        "decibels": 95,
        "duration_seconds": 25,
        "description": "Directional acoustic voice transmission beamed at target coordinates in Hindi, Punjabi, and English.",
        "action": "LRAD Multilingual Audio Warning Broadcast",
        "audio_scripts": {
            "hindi": "चेतावनी! आप प्रतिबंधित सीमा क्षेत्र में हैं। तुरंत पीछे हटें।",
            "hindi_phonetic": "Chetavani! Aap pratibandhit seema kshetra mein hain. Turant peeche hatein.",
            "punjabi": "ਚੇਤਾਵਨੀ! ਤੁਸੀਂ ਪਾਬੰਦੀਸ਼ੁਦਾ ਸੀਮਾ ਖੇਤਰ ਵਿੱਚ ਹੋ। ਤੁਰੰਤ ਪਿੱਛੇ ਹਟੋ।",
            "punjabi_phonetic": "Chetavani! Tusi pabandishuda seema kshetra vich ho. Turant picche hato.",
            "english": "Warning! You are entering a restricted border security perimeter. Stand down and turn back immediately."
        }
    },
    3: {
        "stage_id": 3,
        "code": "STAGE_3_ACOUSTIC_DISPERSION",
        "title": "Stage 3: 115 dB Directional Acoustic Dispersion Siren",
        "output_type": "ACOUSTIC_DISPERSION_TONE",
        "decibels": 115,
        "duration_seconds": 30,
        "description": "Directional high-frequency swept audio siren (2.5 kHz - 4.5 kHz) creating safe acoustic dispersion pressure.",
        "action": "115 dB High-Decibel Siren Sounding"
    },
    4: {
        "stage_id": 4,
        "code": "STAGE_4_QRT_INTERCEPT",
        "title": "Stage 4: Tactical QRT Ground Intercept Authorization",
        "output_type": "TACTICAL_APPREHENSION",
        "decibels": 0,
        "duration_seconds": 0,
        "description": "All non-lethal remote deterrence exhausted. Target non-compliant. Authorized mobile Quick Reaction Team ground intercept.",
        "action": "QRT Immediate Intercept Directive Dispatched"
    }
}

class DeterrenceMatrixManager:
    """
    Manages active deterrence escalation states, compliance response tracking,
    and evaluator demonstration scenarios.
    """
    def __init__(self):
        self.active_event_id: Optional[str] = None
        self.active_target_id: Optional[str] = None
        self.active_zone_id: str = "ZONE_C"
        self.current_stage: int = 0
        self.compliance_status: str = "STANDBY"  # "STANDBY", "ESCALATING", "INTRUDER_RETREATING", "NON_COMPLIANT"
        self.history: List[Dict[str, Any]] = []

    def get_state(self) -> Dict[str, Any]:
        """Returns the current state of the deterrence matrix."""
        stage_info = STAGES.get(self.current_stage, None)
        return {
            "status": "HEALTHY",
            "current_stage": self.current_stage,
            "stage_info": stage_info,
            "compliance_status": self.compliance_status,
            "active_target_id": self.active_target_id or "NONE",
            "active_zone_id": self.active_zone_id,
            "all_stages": list(STAGES.values()),
            "total_escalations_logged": len(self.history),
            "recent_actions": self.history[-8:]
        }

    async def escalate_stage(
        self,
        event_id: str = "EVT_BREACH_ZONE_C",
        target_id: str = "GLOBAL_TARGET_001",
        zone_id: str = "ZONE_C",
        operator: str = "COMMAND_WATCH_01"
    ) -> Dict[str, Any]:
        """
        Escalates deterrence to the next operational stage (1 -> 2 -> 3 -> 4).
        """
        self.active_event_id = event_id
        self.active_target_id = target_id
        self.active_zone_id = zone_id

        if self.current_stage < 4:
            self.current_stage += 1
        
        stage_def = STAGES[self.current_stage]
        now = datetime.now(timezone.utc).isoformat()
        
        # Simulate compliance behavior based on stage
        if self.current_stage in (1, 2):
            self.compliance_status = "MONITORING_RESPONSE"
        elif self.current_stage == 3:
            self.compliance_status = "NON_COMPLIANT_ESCALATION"
        else:
            self.compliance_status = "QRT_GROUND_INTERCEPT_AUTHORIZED"

        action_entry = {
            "timestamp": now,
            "stage_id": self.current_stage,
            "code": stage_def["code"],
            "title": stage_def["title"],
            "decibels": stage_def["decibels"],
            "target_id": target_id,
            "zone_id": zone_id,
            "operator": operator,
            "compliance": self.compliance_status
        }
        self.history.append(action_entry)
        logger.warning(f"DETERRENCE ESCALATION: [{stage_def['code']}] activated by {operator} for {target_id}")

        await ws_manager.broadcast({
            "type": "DETERRENCE_STAGE_UPDATED",
            "stage_id": self.current_stage,
            "stage_info": stage_def,
            "target_id": target_id,
            "zone_id": zone_id,
            "compliance_status": self.compliance_status,
            "timestamp": now
        })

        return {
            "status": "STAGE_ACTIVATED",
            "current_stage": self.current_stage,
            "stage_info": stage_def,
            "compliance_status": self.compliance_status,
            "action": stage_def["action"]
        }

    async def reset_deterrence(self) -> Dict[str, Any]:
        """Resets deterrence to baseline standby state."""
        self.current_stage = 0
        self.compliance_status = "STANDBY"
        self.active_target_id = None
        now = datetime.now(timezone.utc).isoformat()
        
        await ws_manager.broadcast({
            "type": "DETERRENCE_RESET",
            "status": "STANDBY",
            "timestamp": now
        })

        return {
            "status": "RESET_COMPLETED",
            "current_stage": 0,
            "compliance_status": "STANDBY"
        }

# Global singleton
deterrence_matrix_manager = DeterrenceMatrixManager()
