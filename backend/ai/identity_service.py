import os
import json
import time
import math
import threading
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import cv2
import numpy as np

from backend.config import get_settings
from backend.database.database import get_db_context
from backend.database.models import AuthorizedPersonModel
from backend.logger import logger

settings = get_settings()

class IdentityService:
    """
    AERION Person Identification & Authorization Engine.
    Implements:
    Camera Frame -> Person Crop -> Face Detection (YuNet) -> Quality Check ->
    Feature Extraction (SFace) -> Cosine Similarity Matching -> Confidence Check ->
    Zone-Based Authorization Validation.
    """
    _instance: Optional['IdentityService'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(IdentityService, cls).__new__(cls)
                cls._instance._detector = None
                cls._instance._recognizer = None
                cls._instance._gallery: Dict[str, Dict[str, Any]] = {}
                cls._instance._latest_results: Dict[str, Dict[str, Any]] = {}
                cls._instance._simulated_overrides: Dict[str, Dict[str, Any]] = {}
                cls._instance._initialized = False
            return cls._instance

    def initialize(self) -> None:
        """Initializes face detector and recognizer models and preloads authorized gallery."""
        with self._lock:
            if self._initialized:
                return

            logger.info("Initializing IdentityService (YuNet + SFace)...")
            models_dir = settings.base_dir / "models"
            models_dir.mkdir(parents=True, exist_ok=True)

            yunet_path = str(models_dir / "face_detection_yunet_2023mar.onnx")
            sface_path = str(models_dir / "face_recognition_sface_2021dec.onnx")

            try:
                if os.path.exists(yunet_path) and os.path.exists(sface_path):
                    self._detector = cv2.FaceDetectorYN.create(yunet_path, "", (320, 320), 0.6, 0.3, 5000)
                    self._recognizer = cv2.FaceRecognizerSF.create(sface_path, "")
                    logger.info("OpenCV YuNet & SFace models successfully initialized.")
                else:
                    logger.warning(f"Face models not found locally at {models_dir}. Operating with feature fallback.")
            except Exception as e:
                logger.error(f"Error loading face models: {e}. Fallback enabled.", exc_info=True)

            self.refresh_gallery()
            self._initialized = True
            logger.info(f"IdentityService initialized with {len(self._gallery)} enrolled persons.")

    def refresh_gallery(self) -> None:
        """Reloads authorized persons from SQLite database into memory."""
        try:
            with get_db_context() as db:
                persons = db.query(AuthorizedPersonModel).all()
                if not persons:
                    from backend.database.database import init_db
                    init_db()
                    persons = db.query(AuthorizedPersonModel).all()

                new_gallery = {}
                for p in persons:
                    try:
                        allowed = json.loads(p.allowed_zones) if p.allowed_zones else []
                    except Exception:
                        allowed = ["ZONE_A", "ZONE_B"]

                    embedding = None
                    if p.reference_embedding:
                        try:
                            embedding = np.array(json.loads(p.reference_embedding), dtype=np.float32)
                        except Exception:
                            embedding = None

                    # If no embedding in DB but a reference image exists, extract and save embedding
                    if embedding is None and p.reference_image_path:
                        full_path = settings.base_dir / p.reference_image_path.lstrip("/\\")
                        if full_path.exists():
                            img = cv2.imread(str(full_path))
                            if img is not None:
                                embedding = self._extract_raw_embedding(img)
                                if embedding is not None:
                                    p.reference_embedding = json.dumps(embedding.tolist())
                                    db.commit()

                    new_gallery[p.person_id] = {
                        "person_id": p.person_id,
                        "name": p.name,
                        "status": p.status,
                        "allowed_zones": allowed,
                        "embedding": embedding,
                        "valid_from": p.valid_from.isoformat() if p.valid_from else None,
                        "valid_until": p.valid_until.isoformat() if p.valid_until else None,
                        "created_at": p.created_at.isoformat() if p.created_at else None
                    }

                self._gallery = new_gallery
                logger.info(f"[IDENTITY] Enrolled gallery refreshed with {len(self._gallery)} persons: {list(self._gallery.keys())}")
        except Exception as e:
            logger.error(f"[IDENTITY] Failed to refresh gallery: {e}", exc_info=True)

    def _extract_raw_embedding(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Extracts 128-D facial feature embedding vector from an image using YuNet + SFace."""
        if image is None or image.size == 0:
            return None

        if not self._initialized or self._detector is None or self._recognizer is None:
            self.initialize()

        h, w = image.shape[:2]
        if self._detector is not None and self._recognizer is not None:
            try:
                # Try direct detection on input image
                self._detector.setInputSize((w, h))
                _, faces = self._detector.detect(image)
                if faces is not None and len(faces) > 0:
                    aligned = self._recognizer.alignCrop(image, faces[0])
                    feat = self._recognizer.feature(aligned)
                    norm = np.linalg.norm(feat)
                    if norm > 0:
                        feat = feat / norm
                    return feat.flatten()

                # Multi-scale detection fallback for high-res enrollment photos
                for scale_w, scale_h in [(320, 320), (640, 640), (480, 640)]:
                    if w > scale_w or h > scale_h:
                        scaled = cv2.resize(image, (scale_w, scale_h))
                        self._detector.setInputSize((scale_w, scale_h))
                        _, s_faces = self._detector.detect(scaled)
                        if s_faces is not None and len(s_faces) > 0:
                            aligned = self._recognizer.alignCrop(scaled, s_faces[0])
                            feat = self._recognizer.feature(aligned)
                            norm = np.linalg.norm(feat)
                            if norm > 0:
                                feat = feat / norm
                            return feat.flatten()
            except Exception as ex:
                logger.debug(f"[IDENTITY] Model extraction fallback: {ex}")

        # Deterministic lightweight fallback embedding (color histogram + gradient statistics)
        try:
            resized = cv2.resize(image, (64, 64))
            hist = cv2.calcHist([resized], [0, 1, 2], None, [4, 4, 4], [0, 256, 0, 256, 0, 256]).flatten()
            norm = np.linalg.norm(hist)
            if norm > 0:
                hist = hist / norm
            return hist[:128]
        except Exception:
            return None

    def enroll_person(
        self,
        person_id: str,
        name: str,
        allowed_zones: List[str],
        image: np.ndarray,
        save_snapshot: bool = True
    ) -> bool:
        """Enrolls a new authorized person with reference facial embedding."""
        embedding = self._extract_raw_embedding(image)
        snap_path = None

        if save_snapshot and image is not None:
            snap_dir = settings.snapshots_dir
            snap_file = f"person_{person_id}_{int(time.time())}.jpg"
            snap_full = snap_dir / snap_file
            cv2.imwrite(str(snap_full), image)
            snap_path = f"/storage/snapshots/{snap_file}"

        with get_db_context() as db:
            existing = db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == person_id).first()
            if existing:
                existing.name = name
                existing.allowed_zones = json.dumps(allowed_zones)
                if embedding is not None:
                    existing.reference_embedding = json.dumps(embedding.tolist())
                if snap_path:
                    existing.reference_image_path = snap_path
            else:
                db.add(AuthorizedPersonModel(
                    person_id=person_id,
                    name=name,
                    status="AUTHORIZED",
                    allowed_zones=json.dumps(allowed_zones),
                    reference_image_path=snap_path,
                    reference_embedding=json.dumps(embedding.tolist()) if embedding is not None else None
                ))
            db.commit()

        self.refresh_gallery()
        return True

    def delete_person(self, person_id: str) -> bool:
        """Removes a person from registry."""
        with get_db_context() as db:
            p = db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == person_id).first()
            if p:
                db.delete(p)
                db.commit()
                self.refresh_gallery()
                return True
        return False

    def list_persons(self) -> List[Dict[str, Any]]:
        """Returns all enrolled persons in registry."""
        if not self._initialized or not self._gallery:
            self.initialize()
        return [
            {
                "person_id": p["person_id"],
                "name": p["name"],
                "status": p["status"],
                "allowed_zones": p["allowed_zones"],
                "has_embedding": p["embedding"] is not None,
                "created_at": p["created_at"]
            }
            for p in self._gallery.values()
        ]

    def _normalize_zone(self, zone_id: Optional[str]) -> str:
        """Normalizes zone aliases (e.g. ZONE-002 <-> ZONE_B, ZONE-003 <-> ZONE_C)."""
        if not zone_id:
            return "ZONE_B"
        z = zone_id.upper().strip()
        alias_map = {
            "ZONE-001": "ZONE_A", "ZONE-01": "ZONE_A", "ZONE-1": "ZONE_A",
            "ZONE-002": "ZONE_B", "ZONE-02": "ZONE_B", "ZONE-2": "ZONE_B",
            "ZONE-003": "ZONE_C", "ZONE-03": "ZONE_C", "ZONE-3": "ZONE_C",
            "ZONE_01": "ZONE_A", "ZONE_02": "ZONE_B", "ZONE_03": "ZONE_C"
        }
        return alias_map.get(z, z)

    def _is_zone_allowed(self, current_zone: str, allowed_zones: List[str]) -> bool:
        """Checks if current zone is permitted in the allowed zones list."""
        curr_norm = self._normalize_zone(current_zone)
        for az in allowed_zones:
            if curr_norm == self._normalize_zone(az) or current_zone == az:
                return True
        return False

    def simulate_identity(
        self,
        camera_id: str,
        identity: str,
        confidence: float,
        authorization: str,
        duration: float = 30.0,
        zone_id: Optional[str] = None
    ) -> None:
        """Injects a simulated identity verification result for demonstrations."""
        expires_at = time.time() + duration
        resolved_zone = zone_id or ("ZONE_C" if camera_id == "CAM_02" else "ZONE_B")
        self._simulated_overrides[camera_id] = {
            "identity": identity,
            "confidence": round(float(confidence), 2),
            "authorization": authorization.upper(),
            "expires_at": expires_at,
            "zone_id": resolved_zone
        }
        self._latest_results[camera_id] = {
            "identity": identity,
            "confidence": round(float(confidence), 2),
            "authorization": authorization.upper(),
            "camera_id": camera_id,
            "zone_id": resolved_zone,
            "track_id": 999,
            "face_detected": True,
            "timestamp": time.time(),
            "is_simulated": True
        }
        logger.info(f"[IDENTITY] Simulated override applied for {camera_id}: {identity} ({authorization})")

    def clear_simulation(self, camera_id: Optional[str] = None) -> None:
        """Clears simulated override."""
        if camera_id:
            self._simulated_overrides.pop(camera_id, None)
        else:
            self._simulated_overrides.clear()

    def verify_person(
        self,
        frame: np.ndarray,
        person_box: Tuple[int, int, int, int],
        camera_id: str = "CAM_01",
        zone_id: str = "ZONE_B",
        track_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes identity verification pipeline for a detected person.
        Returns identity, confidence, and authorization status.
        """
        now = time.time()

        # 1. Check for active simulation override
        if camera_id in self._simulated_overrides:
            override = self._simulated_overrides[camera_id]
            if now < override["expires_at"]:
                res = {
                    "identity": override["identity"],
                    "confidence": override["confidence"],
                    "authorization": override["authorization"],
                    "camera_id": camera_id,
                    "zone_id": zone_id,
                    "track_id": track_id,
                    "face_detected": True,
                    "timestamp": now,
                    "is_simulated": True
                }
                self._latest_results[camera_id] = res
                return res
            else:
                self._simulated_overrides.pop(camera_id, None)

        if not self._initialized:
            self.initialize()

        # 2. Crop Person Bounding Box
        x1, y1, x2, y2 = person_box
        h_frame, w_frame = frame.shape[:2]
        x1 = max(0, min(w_frame - 1, x1))
        y1 = max(0, min(h_frame - 1, y1))
        x2 = max(0, min(w_frame, x2))
        y2 = max(0, min(h_frame, y2))

        crop_w = x2 - x1
        crop_h = y2 - y1

        if crop_w < 30 or crop_h < 30:
            res = {
                "identity": "UNVERIFIED",
                "confidence": 0.40,
                "authorization": "UNVERIFIED",
                "camera_id": camera_id,
                "zone_id": zone_id,
                "track_id": track_id,
                "face_detected": False,
                "reason": "Person crop too small for facial recognition",
                "timestamp": now
            }
            self._latest_results[camera_id] = res
            return res

        person_crop = frame[y1:y2, x1:x2]

        # 3. Face Detection & Feature Extraction directly from Landmarks
        face_detected = False
        face_crop = None
        face_confidence = 0.0
        feature = None

        # Look in upper body first (top 65% of person crop)
        upper_body_h = int(crop_h * 0.65)
        upper_body = person_crop[0:upper_body_h, :]
        ub_h, ub_w = upper_body.shape[:2]

        if self._detector is not None and self._recognizer is not None and ub_w >= 24 and ub_h >= 24:
            try:
                self._detector.setInputSize((ub_w, ub_h))
                _, faces = self._detector.detect(upper_body)
                if faces is not None and len(faces) > 0:
                    best_face = faces[0]
                    fx, fy, fw, fh = int(best_face[0]), int(best_face[1]), int(best_face[2]), int(best_face[3])
                    face_confidence = float(best_face[-1])
                    fx1 = max(0, fx)
                    fy1 = max(0, fy)
                    fx2 = min(ub_w, fx + fw)
                    fy2 = min(ub_h, fy + fh)
                    if (fx2 - fx1) >= 16 and (fy2 - fy1) >= 16:
                        face_crop = upper_body[fy1:fy2, fx1:fx2]
                        face_detected = True
                        aligned = self._recognizer.alignCrop(upper_body, best_face)
                        feat = self._recognizer.feature(aligned)
                        norm = np.linalg.norm(feat)
                        if norm > 0:
                            feature = (feat / norm).flatten()
            except Exception as ex:
                logger.debug(f"[IDENTITY] Face detector in upper body: {ex}")

        # If not detected in upper body, try full person crop
        if not face_detected and self._detector is not None and self._recognizer is not None and crop_w >= 30 and crop_h >= 30:
            try:
                self._detector.setInputSize((crop_w, crop_h))
                _, faces = self._detector.detect(person_crop)
                if faces is not None and len(faces) > 0:
                    best_face = faces[0]
                    face_confidence = float(best_face[-1])
                    face_detected = True
                    aligned = self._recognizer.alignCrop(person_crop, best_face)
                    feat = self._recognizer.feature(aligned)
                    norm = np.linalg.norm(feat)
                    if norm > 0:
                        feature = (feat / norm).flatten()
            except Exception as ex:
                logger.debug(f"[IDENTITY] Face detector in person crop: {ex}")

        # Fallback feature extraction if not yet extracted
        if feature is None and (face_detected or face_crop is not None):
            target_img = face_crop if face_crop is not None else person_crop
            feature = self._extract_raw_embedding(target_img)

        # 4. Face Quality Check (sharpness, size, illumination)
        if face_crop is not None:
            gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            lap_var = cv2.Laplacian(gray_face, cv2.CV_64F).var()
            mean_brightness = float(np.mean(gray_face))
            if lap_var < 8.0 or mean_brightness < 12.0 or mean_brightness > 248.0:
                # Poor quality face -> do not trigger false alarm
                res = {
                    "identity": "UNVERIFIED",
                    "confidence": 0.52,
                    "authorization": "UNVERIFIED",
                    "camera_id": camera_id,
                    "zone_id": zone_id,
                    "track_id": track_id,
                    "face_detected": True,
                    "reason": "Low face quality / motion blur / poor lighting",
                    "timestamp": now
                }
                self._latest_results[camera_id] = res
                return res

        # 5. Compare with Gallery & Determine Authorization
        best_match_id = None
        best_match_name = "UNKNOWN"
        best_sim = 0.0
        threshold = getattr(settings, "IDENTITY_CONFIDENCE_THRESHOLD", 0.38)

        if feature is not None and self._gallery:
            for pid, person in self._gallery.items():
                p_feat = person.get("embedding")
                if p_feat is not None:
                    embeddings_list = [p_feat] if isinstance(p_feat, np.ndarray) and p_feat.ndim == 1 else (p_feat if isinstance(p_feat, list) else [p_feat])
                    for ef in embeddings_list:
                        ef_arr = np.array(ef, dtype=np.float32) if not isinstance(ef, np.ndarray) else ef
                        if len(ef_arr) == len(feature):
                            sim = float(np.dot(feature, ef_arr) / (np.linalg.norm(feature) * np.linalg.norm(ef_arr) + 1e-7))
                            if sim > best_sim:
                                best_sim = sim
                                best_match_id = pid
                                best_match_name = person["name"]

        if best_match_id and best_sim >= threshold:
            # Recognized authorized or enrolled person
            matched_person = self._gallery[best_match_id]
            person_status = matched_person.get("status", "AUTHORIZED")

            # Map cosine score [threshold, 0.70] to normalized UI confidence [82%, 99%]
            norm_factor = min(1.0, max(0.0, (best_sim - threshold) / (0.70 - threshold + 1e-5)))
            conf = round(0.82 + norm_factor * 0.17, 2)

            if person_status in ("DISABLED", "SUSPENDED", "REVOKED"):
                identity = best_match_name
                authorization = "UNAUTHORIZED"
            else:
                is_authorized_zone = self._is_zone_allowed(zone_id, matched_person["allowed_zones"])
                authorization = "AUTHORIZED" if is_authorized_zone else "NOT_AUTHORIZED_FOR_ZONE"
                identity = best_match_name

                # Update detection count and last detected zone in DB
                try:
                    from datetime import datetime as _dt, timezone as _tz
                    with get_db_context() as _db:
                        from backend.database.models import AuthorizedPersonModel as _APM
                        _p = _db.query(_APM).filter(_APM.person_id == best_match_id).first()
                        if _p:
                            _p.detection_count = (_p.detection_count or 0) + 1
                            _p.last_detected_at = _dt.now(_tz.utc)
                            _p.last_detected_zone = zone_id
                            _db.commit()
                except Exception as _ex:
                    logger.debug(f"[IDENTITY] Detection tracking update failed: {_ex}")

        elif face_detected:
            # Confirmed unknown face
            identity = "UNKNOWN"
            conf = round(max(0.88, best_sim if best_sim > 0 else 0.88), 2)
            authorization = "UNAUTHORIZED"
        else:
            # Person detected but face not clearly visible
            identity = "UNVERIFIED"
            conf = 0.50
            authorization = "UNVERIFIED"

        result = {
            "identity": identity,
            "confidence": conf,
            "authorization": authorization,
            "camera_id": camera_id,
            "zone_id": zone_id,
            "track_id": track_id,
            "face_detected": face_detected,
            "matched_person_id": best_match_id if identity not in ("UNKNOWN", "UNVERIFIED", "STANDBY") else None,
            "timestamp": now,
            "is_simulated": False
        }

        self._latest_results[camera_id] = result
        return result

    def get_latest_result(self, camera_id: str) -> Dict[str, Any]:
        """Returns the latest identity verification result for a camera."""
        if camera_id in self._latest_results:
            return self._latest_results[camera_id]
        return {
            "identity": "STANDBY",
            "confidence": 0.0,
            "authorization": "NORMAL",
            "camera_id": camera_id,
            "zone_id": "ZONE_B",
            "face_detected": False,
            "timestamp": time.time()
        }

identity_service = IdentityService()
