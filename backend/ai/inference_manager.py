import time
import threading
import queue
from typing import Optional, Dict, Any, List
import numpy as np

from backend.ai.detector_interface import DetectorInterface, Detection, DetectionResult
from backend.ai.tracker_interface import TrackerInterface, TrackedObject
from backend.ai.yolo_detector import YOLODetector
from backend.ai.tracker import TacticalTracker
from backend.ai.annotator import annotate_tracked_frame
from backend.camera.camera_manager import camera_manager
from backend.zones.zone_manager import zone_manager
from backend.config import get_settings
from backend.logger import logger
from backend.websocket.manager import ws_manager

settings = get_settings()

class InferenceManager:
    """
    Decoupled AI Inference & Multi-Object Tracking Pipeline.
    Runs YOLO detection and TacticalTracker on a dedicated worker thread,
    enforcing controlled AI inference FPS and producing persistent tracking IDs and trajectories.
    """
    _instance: Optional['InferenceManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(InferenceManager, cls).__new__(cls)
                cls._instance._detector: Optional[DetectorInterface] = None
                cls._instance._trackers: Dict[str, TrackerInterface] = {}
                cls._instance._running = False
                cls._instance._thread: Optional[threading.Thread] = None
                cls._instance._latest_results: Dict[str, DetectionResult] = {}
                cls._instance._latest_tracks: Dict[str, List[TrackedObject]] = {}
                cls._instance._latest_annotated_frames: Dict[str, np.ndarray] = {}
                cls._instance.actual_inference_fps = 0.0
                cls._instance.avg_latency_ms = 0.0
                cls._instance.dropped_inference_frames = 0
                cls._instance._fps_timestamps: list = []
                cls._instance._latency_history: list = []
            return cls._instance

    def initialize(
        self,
        detector: Optional[DetectorInterface] = None,
        tracker_factory: Optional[Any] = None
    ) -> None:
        """Initializes detector and launches decoupled inference and tracking worker thread."""
        with self._lock:
            if self._running:
                return

            logger.info("Initializing InferenceManager with Multi-Object Tracking...")
            self._detector = detector or YOLODetector(
                model_name=settings.YOLO_MODEL_NAME,
                confidence_threshold=settings.DETECTION_CONFIDENCE
            )
            # Pre-create tracker for CAM_01
            self._trackers["CAM_01"] = TacticalTracker(max_age=20, min_hits=1, iou_threshold=0.25)

            # Load model weights in thread
            threading.Thread(target=self._detector.load, name="ModelLoader", daemon=True).start()

            self._running = True
            self._thread = threading.Thread(
                target=self._run_inference_loop,
                name="AI-InferenceWorker",
                daemon=True
            )
            self._thread.start()
            logger.info("InferenceManager worker started.")

    def _get_tracker(self, camera_id: str) -> TrackerInterface:
        if camera_id not in self._trackers:
            self._trackers[camera_id] = TacticalTracker(max_age=20, min_hits=1, iou_threshold=0.25)
        return self._trackers[camera_id]

    def _run_inference_loop(self) -> None:
        """Main inference and tracking loop regulated by AdaptiveFPSGovernor."""
        from backend.ai.fps_governor import fps_governor
        from backend.ai.hw_accelerator import hw_accelerator

        logger.info(f"AI inference worker started with AdaptiveFPSGovernor.")

        while self._running:
            t_loop_start = time.time()
            now = time.time()

            # Dynamic FPS regulation: check for active threat conditions
            has_threats = False
            for cid_tracks in self._latest_tracks.values():
                for t in cid_tracks:
                    if getattr(t, "intrusion_state", None) in ("WARNING", "RESTRICTED_ENTRY", "ACTIVE_EVENT") or getattr(t, "threat_score", 0.0) > 0.35:
                        has_threats = True
                        break
                if has_threats:
                    break
            if not has_threats:
                try:
                    from backend.radar.radar_manager import radar_manager
                    if radar_manager.get_active_tracks():
                        has_threats = True
                except Exception:
                    pass

            target_fps = fps_governor.get_target_fps(active_threats_present=has_threats)
            target_interval = 1.0 / max(1.0, target_fps)

            # Poll all active online cameras (CAM_01, CAM_02, UAV_01, etc.)
            active_cams = [cid for cid in ["CAM_01", "CAM_02", "UAV_01"] if camera_manager.get_camera(cid) and camera_manager.get_camera(cid).status == "ONLINE"]
            if not active_cams:
                active_cams = ["CAM_01"]

            for cid in active_cams:
                cam = camera_manager.get_camera(cid)
                if cam is None or cam.status != "ONLINE":
                    continue

                t_cap_start = time.time()
                frame = cam.get_frame()
                t_cap_ms = max(1.0, (time.time() - t_cap_start) * 1000.0)

                if frame is not None:
                    # 1. Execute Object Detection
                    if self._detector and self._detector.is_ready():
                        result = self._detector.detect(frame, settings.DETECTION_CONFIDENCE)
                    else:
                        result = DetectionResult(
                            detections=[],
                            inference_time_ms=0.0,
                            model_name=settings.YOLO_MODEL_NAME,
                            device="warming_up",
                            timestamp=now
                        )

                    self._latest_results[cid] = result

                    # 2. Multi-Object Tracking & Trajectories
                    t_trk_start = time.time()
                    tracker = self._get_tracker(cid)
                    tracks = tracker.update(result.detections, timestamp=now)

                    # 3. Track Processing: Identity, ANPR, and Zone Intrusion
                    h, w = frame.shape[:2]
                    for t in tracks:
                        # Step A: Check if track is a candidate vehicle requiring ANPR inspection
                        try:
                            from backend.ai.anpr_engine import anpr_engine
                            if anpr_engine.is_candidate_vehicle(t.class_name, t.box):
                                anpr_res = anpr_engine.process_vehicle(
                                    frame=frame,
                                    bbox=t.box,
                                    vehicle_track_id=t.track_id,
                                    camera_id=cid
                                )
                                if anpr_res and anpr_res.get("is_readable"):
                                    t.plate_text = anpr_res.get("clean_plate") or anpr_res.get("plate_text")
                                    cached_p = anpr_engine.get_plate_for_track(t.track_id)
                                    if cached_p:
                                        t.plate_text = cached_p.get("clean_plate") or cached_p.get("plate_text")
                        except Exception as anpr_err:
                            logger.debug(f"[ANPR] Inspection bypass: {anpr_err}")

                        # Step B: Person Identification & Authorization Verification (AERION Sections 7-12)
                        is_authorized_person = False
                        if t.class_name == "person":
                            try:
                                from backend.ai.identity_service import identity_service
                                id_res = identity_service.verify_person(
                                    frame=frame,
                                    person_box=t.box,
                                    camera_id=cid,
                                    zone_id=t.zone_id or "ZONE_B",
                                    track_id=t.track_id
                                )
                                t.identity = id_res.get("identity")
                                t.identity_confidence = id_res.get("confidence")
                                t.authorization = id_res.get("authorization")

                                if t.authorization == "AUTHORIZED":
                                    is_authorized_person = True
                                    tracker.set_track_identity(
                                        t.track_id,
                                        identity=t.identity,
                                        confidence=t.identity_confidence or 0.95,
                                        authorization=t.authorization
                                    )
                                elif t.authorization in ("UNAUTHORIZED", "NOT_AUTHORIZED_FOR_ZONE"):
                                    try:
                                        from backend.events.incident_service import incident_service
                                        incident_service.process_unauthorized_detection(
                                            camera_id=cid,
                                            zone_id=t.zone_id or "ZONE_B",
                                            track_id=t.track_id,
                                            identity=t.identity or "UNKNOWN",
                                            confidence=t.identity_confidence or 0.90,
                                            authorization=t.authorization
                                        )
                                    except Exception as inc_err:
                                        logger.debug(f"[INCIDENT] Incident trigger bypass: {inc_err}")
                            except Exception as id_err:
                                logger.debug(f"[IDENTITY] Verification bypass: {id_err}")

                        # Step C: Zone Intrusion Evaluation for each track (suppressing alarms for authorized personnel)
                        eval_res = zone_manager.evaluate_camera_track(
                            track_id=t.track_id,
                            center_px=t.center,
                            frame_shape=(h, w),
                            velocity_px=(t.velocity_x, t.velocity_y),
                            object_class=t.class_name,
                            camera_id=cid,
                            is_authorized=is_authorized_person,
                            identity=t.identity
                        )
                        t.zone_id = eval_res["zone_id"]
                        t.zone_name = eval_res["zone_name"]
                        t.intrusion_state = eval_res["state"]

                        # Step D: Threat & Loitering Profiling (Phase 10)
                        try:
                            from backend.ai.threat_profiler import threat_profiler
                            zone_type = "RESTRICTED" if t.zone_id == "ZONE_C" else ("WARNING" if t.zone_id == "ZONE_B" else "NORMAL")
                            score, loitering = threat_profiler.evaluate_track_threat(t, zone_type=zone_type, now=now)
                            t.threat_score = 0.0 if is_authorized_person else score
                            t.is_loitering = False if is_authorized_person else loitering
                        except Exception as threat_err:
                            logger.debug(f"[THREAT] Profiler bypass: {threat_err}")

                    self._latest_tracks[cid] = tracks

                    # Optical ray fusion into EKF tracker
                    try:
                        from backend.fusion.ekf_tracker import ekf_fusion_tracker
                        for t in tracks:
                            norm_u = t.center[0] / max(1.0, float(w))
                            norm_v = t.center[1] / max(1.0, float(h))
                            ekf_fusion_tracker.process_camera_detection(
                                camera_track_id=f"{cid}_TRK_{t.track_id}",
                                norm_u=norm_u,
                                norm_v=norm_v,
                                class_name=t.class_name,
                                confidence=t.confidence
                            )
                    except Exception:
                        pass

                    t_trk_ms = max(0.5, (time.time() - t_trk_start) * 1000.0)

                    # Privacy Blurring if enabled in settings (Section 46)
                    render_frame = frame
                    if settings.PRIVACY_BLUR_ENABLED:
                        try:
                            from backend.ai.threat_profiler import threat_profiler
                            render_frame = threat_profiler.apply_privacy_blur(frame, tracks)
                        except Exception as blur_err:
                            logger.debug(f"[PRIVACY] Blur bypass: {blur_err}")

                    # 4. Annotate Frame with Track IDs, Zone States & Trajectory Trails
                    annotated = annotate_tracked_frame(
                        render_frame,
                        tracks,
                        fps=self.actual_inference_fps,
                        camera_label=cam.name
                    )
                    self._latest_annotated_frames[cid] = annotated

                    # 5. Telemetry (Rolling FPS & Latency)
                    self._fps_timestamps.append(now)
                    cutoff = now - 1.0
                    self._fps_timestamps = [t for t in self._fps_timestamps if t >= cutoff]
                    self.actual_inference_fps = round(float(len(self._fps_timestamps)), 1)

                    self._latency_history.append(result.inference_time_ms)
                    if len(self._latency_history) > 30:
                        self._latency_history.pop(0)
                    self.avg_latency_ms = round(sum(self._latency_history) / max(1, len(self._latency_history)), 1)

                    # 6. Broadcast Real-Time Tracking Telemetry over WebSocket
                    t_net_start = time.time()
                    if tracks:
                        ws_manager.broadcast_sync({
                            "type": "AI_TRACKS_UPDATE",
                            "camera_id": cid,
                            "count": len(tracks),
                            "inference_ms": result.inference_time_ms,
                            "tracks": [
                                {
                                    "track_id": t.track_id,
                                    "class_name": t.class_name,
                                    "confidence": t.confidence,
                                    "box": t.box,
                                    "center": t.center,
                                    "speed": t.speed,
                                    "zone_id": t.zone_id,
                                    "zone_name": t.zone_name,
                                    "intrusion_state": t.intrusion_state,
                                    "identity": getattr(t, "identity", None),
                                    "identity_confidence": getattr(t, "identity_confidence", None),
                                    "authorization": getattr(t, "authorization", None),
                                    "trajectory": t.trajectory[-15:]  # Send last 15 points
                                }
                                for t in tracks
                            ],
                            "timestamp": now
                        })
                    t_net_ms = max(0.5, (time.time() - t_net_start) * 1000.0)

                    # Update hardware acceleration latency decomposition
                    hw_accelerator.update_stage_latencies(
                        capture_ms=t_cap_ms,
                        inference_ms=result.inference_time_ms if result.inference_time_ms > 0 else 25.0,
                        tracking_ms=t_trk_ms,
                        network_ms=t_net_ms
                    )
                    fps_governor.record_frame_processed()

            # Regulate to dynamic target AI FPS
            elapsed = time.time() - t_loop_start
            sleep_time = target_interval - elapsed
            if sleep_time > 0.001:
                time.sleep(sleep_time)
            else:
                fps_governor.record_frame_dropped()
                self.dropped_inference_frames += 1

    def get_latest_detections(self, camera_id: str = "CAM_01") -> Optional[DetectionResult]:
        """Retrieves most recent raw detections for a camera."""
        return self._latest_results.get(camera_id)

    def get_latest_tracks(self, camera_id: str = "CAM_01") -> List[TrackedObject]:
        """Retrieves active tracked objects with trajectories."""
        return self._latest_tracks.get(camera_id, [])

    def get_annotated_frame(self, camera_id: str = "CAM_01") -> Optional[np.ndarray]:
        """Retrieves the most recent frame annotated with bounding boxes and trajectory trails."""
        return self._latest_annotated_frames.get(camera_id)

    def get_metrics(self) -> Dict[str, Any]:
        """Returns diagnostic metrics for AI inference and tracking."""
        from backend.ai.fps_governor import fps_governor
        from backend.ai.hw_accelerator import hw_accelerator
        active_tracks = sum(len(trks) for trks in self._latest_tracks.values())
        gov_status = fps_governor.get_status()
        hw_status = hw_accelerator.get_status()
        return {
            "is_ready": self._detector.is_ready() if self._detector else False,
            "model_name": settings.YOLO_MODEL_NAME,
            "device": getattr(self._detector, "device", "cpu"),
            "target_fps": gov_status["current_target_fps"],
            "actual_fps": self.actual_inference_fps,
            "avg_latency_ms": self.avg_latency_ms,
            "active_tracks": active_tracks,
            "confidence_threshold": settings.DETECTION_CONFIDENCE,
            "dropped_frames": self.dropped_inference_frames,
            "governor": gov_status,
            "hardware": hw_status
        }

    def stop(self) -> None:
        """Stops the inference worker thread."""
        logger.info("Stopping InferenceManager...")
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._latest_results.clear()
        self._latest_tracks.clear()
        self._latest_annotated_frames.clear()

inference_manager = InferenceManager()
