import time
import math
from typing import List, Tuple, Optional, Dict
import numpy as np

from backend.ai.detector_interface import Detection
from backend.ai.tracker_interface import TrackerInterface, TrackedObject
from backend.logger import logger

def compute_iou(box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]) -> float:
    """Computes Intersection over Union (IoU) between two bounding boxes (x1, y1, x2, y2)."""
    xx1 = max(box1[0], box2[0])
    yy1 = max(box1[1], box2[1])
    xx2 = min(box1[2], box2[2])
    yy2 = min(box1[3], box2[3])

    w = max(0, xx2 - xx1)
    h = max(0, yy2 - yy1)
    intersection = w * h

    area1 = max(1, (box1[2] - box1[0]) * (box1[3] - box1[1]))
    area2 = max(1, (box2[2] - box2[0]) * (box2[3] - box2[1]))
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0

class Track:
    """Internal state for a tracked object."""
    def __init__(self, track_id: int, detection: Detection, timestamp: float):
        self.track_id = track_id
        self.class_id = detection.class_id
        self.class_name = detection.class_name
        self.confidence = detection.confidence
        self.box = detection.box
        self.center = detection.center
        self.first_seen = timestamp
        self.last_seen = timestamp
        self.time_since_update = 0
        self.hits = 1
        self.age = 1
        self.confirmed = False
        self.plate_text: Optional[str] = None
        self.identity: Optional[str] = None
        self.identity_confidence: Optional[float] = None
        self.authorization: Optional[str] = None

        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.speed = 0.0
        self.trajectory: List[Tuple[int, int]] = [detection.center]

    def predicted_box(self, timestamp: float) -> Tuple[int, int, int, int]:
        """Predicts expected box position based on current velocity and elapsed time."""
        dt = min(0.5, max(0.0, timestamp - self.last_seen))
        dx = int(round(self.velocity_x * dt))
        dy = int(round(self.velocity_y * dt))
        x1, y1, x2, y2 = self.box
        return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)

    def predicted_center(self, timestamp: float) -> Tuple[int, int]:
        """Predicts expected center position based on current velocity and elapsed time."""
        dt = min(0.5, max(0.0, timestamp - self.last_seen))
        dx = int(round(self.velocity_x * dt))
        dy = int(round(self.velocity_y * dt))
        cx, cy = self.center
        return (cx + dx, cy + dy)

    def update(self, detection: Detection, timestamp: float) -> None:
        dt = max(0.01, timestamp - self.last_seen)
        old_cx, old_cy = self.center
        new_cx, new_cy = detection.center

        # Velocity smoothing (exponential moving average)
        inst_vx = (new_cx - old_cx) / dt
        inst_vy = (new_cy - old_cy) / dt
        self.velocity_x = round(0.7 * self.velocity_x + 0.3 * inst_vx, 1)
        self.velocity_y = round(0.7 * self.velocity_y + 0.3 * inst_vy, 1)
        self.speed = round(math.sqrt(self.velocity_x**2 + self.velocity_y**2), 1)

        # Coordinate smoothing to eliminate box boundary jitter
        old_x1, old_y1, old_x2, old_y2 = self.box
        new_x1, new_y1, new_x2, new_y2 = detection.box
        self.box = (
            int(round(0.75 * new_x1 + 0.25 * old_x1)),
            int(round(0.75 * new_y1 + 0.25 * old_y1)),
            int(round(0.75 * new_x2 + 0.25 * old_x2)),
            int(round(0.75 * new_y2 + 0.25 * old_y2))
        )
        self.center = detection.center
        self.confidence = detection.confidence
        self.last_seen = timestamp
        self.time_since_update = 0
        self.hits += 1
        self.age += 1

        if self.hits >= 2:
            self.confirmed = True

        # Append to trajectory (retain last 30 positions)
        self.trajectory.append((new_cx, new_cy))
        if len(self.trajectory) > 30:
            self.trajectory.pop(0)

    def mark_missed(self) -> None:
        self.time_since_update += 1
        self.age += 1

    @property
    def smoothed_center(self) -> Tuple[int, int]:
        return self.center

    def to_model(self) -> TrackedObject:
        return TrackedObject(
            track_id=self.track_id,
            class_id=self.class_id,
            class_name=self.class_name,
            confidence=self.confidence,
            box=self.box,
            center=self.center,
            velocity_x=self.velocity_x,
            velocity_y=self.velocity_y,
            speed=self.speed,
            trajectory=list(self.trajectory),
            first_seen=self.first_seen,
            last_seen=self.last_seen,
            time_since_update=self.time_since_update,
            hits=self.hits,
            age=self.age,
            confirmed=self.confirmed,
            plate_text=self.plate_text,
            identity=self.identity,
            identity_confidence=self.identity_confidence,
            authorization=self.authorization
        )

class TacticalTracker(TrackerInterface):
    """
    Multi-Object Tactical Tracker utilizing velocity-predicted IoU overlap
    and spatial proximity cost matching.
    Provides stable IDs, velocity estimation, jitter-free smoothing, and trajectory paths.
    """
    def __init__(self, max_age: int = 20, min_hits: int = 1, iou_threshold: float = 0.20):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self._next_id = 1
        self._tracks: List[Track] = []

    def update(self, detections: List[Detection], timestamp: Optional[float] = None) -> List[TrackedObject]:
        ts = timestamp if timestamp is not None else time.time()

        if not self._tracks:
            # Initialize all detections as new tracks
            for d in detections:
                new_track = Track(self._next_id, d, ts)
                self._next_id += 1
                self._tracks.append(new_track)
            return [t.to_model() for t in self._tracks if t.confirmed or self.min_hits <= 1]

        if not detections:
            # Mark all tracks as missed
            for t in self._tracks:
                t.mark_missed()
            # Purge expired tracks
            self._tracks = [t for t in self._tracks if t.time_since_update <= self.max_age]
            return [t.to_model() for t in self._tracks if t.confirmed]

        num_tracks = len(self._tracks)
        num_dets = len(detections)

        # -------------------------------------------------------------
        # STAGE 1: Velocity-Predicted IoU Association Matrix
        # -------------------------------------------------------------
        iou_matrix = np.zeros((num_tracks, num_dets), dtype=np.float32)

        for i, trk in enumerate(self._tracks):
            pred_box = trk.predicted_box(ts)
            for j, det in enumerate(detections):
                if trk.class_name == det.class_name:
                    # Test both predicted box and current box to handle sudden stops or starts
                    iou_pred = compute_iou(pred_box, det.box)
                    iou_curr = compute_iou(trk.box, det.box)
                    iou_matrix[i, j] = max(iou_pred, iou_curr)
                else:
                    iou_matrix[i, j] = 0.0

        # Greedy matching by highest IoU
        matched_track_indices = set()
        matched_det_indices = set()

        flat_indices = np.argsort(-iou_matrix, axis=None)
        for idx in flat_indices:
            trk_idx = int(idx // num_dets)
            det_idx = int(idx % num_dets)
            score = iou_matrix[trk_idx, det_idx]

            if score < self.iou_threshold:
                break
            if trk_idx in matched_track_indices or det_idx in matched_det_indices:
                continue

            self._tracks[trk_idx].update(detections[det_idx], ts)
            matched_track_indices.add(trk_idx)
            matched_det_indices.add(det_idx)

        # -------------------------------------------------------------
        # STAGE 2: Spatial Proximity / Centroid Fallback Association
        # Handles rapid movement, low frame rate, and post-occlusion reacquisition
        # -------------------------------------------------------------
        unmatched_tracks = [i for i in range(num_tracks) if i not in matched_track_indices]
        unmatched_dets = [j for j in range(num_dets) if j not in matched_det_indices]

        if unmatched_tracks and unmatched_dets:
            proximity_matches = []
            for trk_idx in unmatched_tracks:
                trk = self._tracks[trk_idx]
                pred_cx, pred_cy = trk.predicted_center(ts)
                curr_cx, curr_cy = trk.center
                trk_w = max(40, trk.box[2] - trk.box[0])
                trk_h = max(40, trk.box[3] - trk.box[1])
                char_dim = max(trk_w, trk_h)
                # Maximum allowable association distance based on target scale
                max_allowable_dist = max(130.0, char_dim * 1.6)

                for det_idx in unmatched_dets:
                    det = detections[det_idx]
                    if trk.class_name != det.class_name:
                        continue

                    dist_pred = math.hypot(det.center[0] - pred_cx, det.center[1] - pred_cy)
                    dist_curr = math.hypot(det.center[0] - curr_cx, det.center[1] - curr_cy)
                    min_dist = min(dist_pred, dist_curr)

                    if min_dist <= max_allowable_dist:
                        proximity_matches.append((min_dist, trk_idx, det_idx))

            # Sort candidate proximity matches by closest Euclidean distance
            proximity_matches.sort(key=lambda x: x[0])
            for dist, trk_idx, det_idx in proximity_matches:
                if trk_idx in matched_track_indices or det_idx in matched_det_indices:
                    continue

                self._tracks[trk_idx].update(detections[det_idx], ts)
                matched_track_indices.add(trk_idx)
                matched_det_indices.add(det_idx)

        # -------------------------------------------------------------
        # STAGE 3: Handle Unmatched Tracks & Detections
        # -------------------------------------------------------------
        # Unmatched existing tracks -> mark missed
        for i, trk in enumerate(self._tracks):
            if i not in matched_track_indices:
                trk.mark_missed()

        # Unmatched detections -> spawn new persistent track
        for j, det in enumerate(detections):
            if j not in matched_det_indices:
                new_track = Track(self._next_id, det, ts)
                self._next_id += 1
                self._tracks.append(new_track)

        # Purge stale tracks that exceeded max_age
        self._tracks = [t for t in self._tracks if t.time_since_update <= self.max_age]

        # Return active tracks
        return [t.to_model() for t in self._tracks if (t.confirmed or t.hits >= self.min_hits)]

    def get_active_tracks(self) -> List[TrackedObject]:
        """Returns list of active confirmed or hit tracks."""
        return [t.to_model() for t in self._tracks if (t.confirmed or t.hits >= self.min_hits)]

    def get_track(self, track_id: int) -> Optional[Track]:
        """Retrieves internal track instance by ID."""
        for t in self._tracks:
            if t.track_id == track_id:
                return t
        return None

    def set_track_identity(self, track_id: int, identity: str, confidence: float, authorization: str) -> None:
        """Sets recognized identity information directly on the track."""
        trk = self.get_track(track_id)
        if trk:
            trk.identity = identity
            trk.identity_confidence = confidence
            trk.authorization = authorization

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

# Default singleton instance
tracker = TacticalTracker()
