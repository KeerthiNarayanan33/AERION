"""
SENTINEL-AI: JDL Level 1 & 2 Extended Kalman Filter (EKF) Sensor Fusion Tracker
Sections 20, 21, & 47: Asynchronous mmWave Radar & Camera Ray Fusion,
Continuous White Noise Acceleration Process Model, and Chi-Squared Mahalanobis Distance Gating.

Fuses polar radar observations [r, theta, r_dot] with normalized camera optical rays [u]
into a unified 4D Cartesian kinematic state vector [x, y, vx, vy]^T with full error covariance P.
"""

import time
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from backend.logger import logger

CHI2_95_2DOF = 5.991   # Chi-squared 95% confidence gate for 2 DOF
CHI2_95_3DOF = 7.815   # Chi-squared 95% confidence gate for 3 DOF

class EKFTrackState:
    """
    Individual 4D Extended Kalman Filter state vector and covariance matrix.
    State: [x, y, vx, vy]^T (meters, meters, m/s, m/s)
    """
    def __init__(self, track_id: str, init_x: float, init_y: float, init_vx: float = 0.0, init_vy: float = -0.8):
        self.track_id: str = track_id
        self.class_name: str = "person"
        self.confidence: float = 0.85
        self.camera_track_id: Optional[str] = None
        self.radar_target_id: Optional[int] = None
        self.last_update_epoch: float = time.time()
        self.confirmed: bool = False
        self.hit_count: int = 1
        self.miss_count: int = 0

        # State vector: [x, y, vx, vy]
        self.x: float = float(init_x)
        self.y: float = float(init_y)
        self.vx: float = float(init_vx)
        self.vy: float = float(init_vy)

        # 4x4 Error Covariance Matrix P (Diagonal initialization)
        self.P: List[List[float]] = [
            [0.25, 0.00, 0.00, 0.00],
            [0.00, 0.25, 0.00, 0.00],
            [0.00, 0.00, 0.50, 0.00],
            [0.00, 0.00, 0.00, 0.50]
        ]

    def predict(self, dt: float, q_spectral: float = 0.5) -> None:
        """
        Constant Velocity (CV) process prediction with continuous white noise acceleration Q.
        """
        dt = max(0.001, min(dt, 2.0))
        # 1. State prediction: x_k|k-1 = F * x_k-1
        self.x += self.vx * dt
        self.y += self.vy * dt

        # 2. Covariance prediction: P_k|k-1 = F * P * F^T + Q
        # Compute F * P * F^T analytically for efficiency:
        p00, p01, p02, p03 = self.P[0]
        p10, p11, p12, p13 = self.P[1]
        p20, p21, p22, p23 = self.P[2]
        p30, p31, p32, p33 = self.P[3]

        # Process noise Q
        q_dt3_3 = q_spectral * (dt ** 3) / 3.0
        q_dt2_2 = q_spectral * (dt ** 2) / 2.0
        q_dt = q_spectral * dt

        new_P = [
            [
                p00 + dt * (p20 + p02 + dt * p22) + q_dt3_3,
                p01 + dt * (p21 + p03 + dt * p23),
                p02 + dt * p22 + q_dt2_2,
                p03 + dt * p23
            ],
            [
                p10 + dt * (p30 + p12 + dt * p32),
                p11 + dt * (p31 + p13 + dt * p33) + q_dt3_3,
                p12 + dt * p32,
                p13 + dt * p33 + q_dt2_2
            ],
            [
                p20 + dt * p22 + q_dt2_2,
                p21 + dt * p23,
                p22 + q_dt,
                p23
            ],
            [
                p30 + dt * p32,
                p31 + dt * p33 + q_dt2_2,
                p32,
                p33 + q_dt
            ]
        ]
        self.P = new_P

    def update_radar(self, r_meas: float, theta_meas: float, rdot_meas: float) -> Tuple[bool, float]:
        """
        EKF non-linear update for polar radar measurement: [r, theta, r_dot].
        Returns (is_accepted, mahalanobis_d2).
        """
        r_pred = math.sqrt(self.x * self.x + self.y * self.y)
        if r_pred < 0.05:
            r_pred = 0.05
        theta_pred = math.atan2(self.x, self.y)
        rdot_pred = (self.x * self.vx + self.y * self.vy) / r_pred

        # Innovation: y = z - h(x)
        y0 = r_meas - r_pred
        y1 = theta_meas - theta_pred
        # Normalize angle innovation to [-pi, pi]
        while y1 > math.pi: y1 -= 2 * math.pi
        while y1 < -math.pi: y1 += 2 * math.pi
        y2 = rdot_meas - rdot_pred

        # Measurement Jacobian H_r (3x4)
        r2 = r_pred * r_pred
        r3 = r2 * r_pred
        H0 = [self.x / r_pred, self.y / r_pred, 0.0, 0.0]
        H1 = [self.y / r2, -self.x / r2, 0.0, 0.0]
        H2 = [
            (self.vx / r_pred) - (self.x * (self.x * self.vx + self.y * self.vy) / r3),
            (self.vy / r_pred) - (self.y * (self.x * self.vx + self.y * self.vy) / r3),
            self.x / r_pred,
            self.y / r_pred
        ]

        # Radar noise R
        R0 = 0.0225  # sigma_r = 0.15m -> 0.0225
        R1 = 0.0012  # sigma_theta = 0.035 rad (~2 deg) -> 0.0012
        R2 = 0.0100  # sigma_rdot = 0.10 m/s -> 0.0100

        # Innovation covariance S = H * P * H^T + R (3x3)
        # Compute H * P (3x4)
        HP = []
        for H_row in [H0, H1, H2]:
            hp_row = [
                sum(H_row[k] * self.P[k][col] for k in range(4))
                for col in range(4)
            ]
            HP.append(hp_row)

        S = [
            [sum(HP[i][k] * [H0, H1, H2][j][k] for k in range(4)) + (R0 if i == 0 else (R1 if i == 1 else R2) if i == j else 0.0) for j in range(3)]
            for i in range(3)
        ]

        # Invert S (3x3) using analytic determinant and adjugate
        det_S = (
            S[0][0] * (S[1][1] * S[2][2] - S[1][2] * S[2][1])
            - S[0][1] * (S[1][0] * S[2][2] - S[1][2] * S[2][0])
            + S[0][2] * (S[1][0] * S[2][1] - S[1][1] * S[2][0])
        )

        if abs(det_S) < 1e-9:
            return False, 999.0

        inv_det = 1.0 / det_S
        inv_S = [
            [
                (S[1][1] * S[2][2] - S[1][2] * S[2][1]) * inv_det,
                (S[0][2] * S[2][1] - S[0][1] * S[2][2]) * inv_det,
                (S[0][1] * S[1][2] - S[0][2] * S[1][1]) * inv_det
            ],
            [
                (S[1][2] * S[2][0] - S[1][0] * S[2][2]) * inv_det,
                (S[0][0] * S[2][2] - S[0][2] * S[2][0]) * inv_det,
                (S[0][2] * S[1][0] - S[0][0] * S[1][2]) * inv_det
            ],
            [
                (S[1][0] * S[2][1] - S[1][1] * S[2][0]) * inv_det,
                (S[0][1] * S[2][0] - S[0][0] * S[2][1]) * inv_det,
                (S[0][0] * S[1][1] - S[0][1] * S[1][0]) * inv_det
            ]
        ]

        # Mahalanobis distance squared: D_M^2 = y^T * inv_S * y
        y = [y0, y1, y2]
        d_m2 = sum(y[i] * inv_S[i][j] * y[j] for i in range(3) for j in range(3))

        # Chi-squared gating at 95% (3 DOF)
        if d_m2 > CHI2_95_3DOF:
            return False, d_m2

        # Kalman Gain: K = P * H^T * inv_S (4x3)
        # First compute P * H^T (4x3)
        P_HT = [
            [sum(self.P[i][k] * [H0, H1, H2][j][k] for k in range(4)) for j in range(3)]
            for i in range(4)
        ]

        K = [
            [sum(P_HT[i][k] * inv_S[k][j] for k in range(3)) for j in range(3)]
            for i in range(4)
        ]

        # State update: x = x + K * y
        dx = [sum(K[i][j] * y[j] for j in range(3)) for i in range(4)]
        self.x += dx[0]
        self.y += dx[1]
        self.vx += dx[2]
        self.vy += dx[3]

        # Covariance update: P = (I - K * H) * P
        KH = [
            [sum(K[i][k] * [H0, H1, H2][k][j] for k in range(3)) for j in range(4)]
            for i in range(4)
        ]

        I_KH = [
            [(1.0 if i == j else 0.0) - KH[i][j] for j in range(4)]
            for i in range(4)
        ]

        new_P = [
            [sum(I_KH[i][k] * self.P[k][j] for k in range(4)) for j in range(4)]
            for i in range(4)
        ]
        self.P = new_P
        self.hit_count += 1
        self.miss_count = 0
        self.last_update_epoch = time.time()
        if self.hit_count >= 3:
            self.confirmed = True

        return True, d_m2

    def update_camera(self, u_meas: float, hfov_deg: float = 70.0) -> Tuple[bool, float]:
        """
        EKF update with optical camera horizontal ray observation u in [0, 1].
        """
        hfov_rad = math.radians(hfov_deg)
        theta_pred = math.atan2(self.x, self.y)
        u_pred = 0.5 + (theta_pred / hfov_rad)

        y = u_meas - u_pred
        r2 = self.x * self.x + self.y * self.y
        if r2 < 0.01: r2 = 0.01

        # H_c (1x4)
        H = [(self.y / r2) / hfov_rad, (-self.x / r2) / hfov_rad, 0.0, 0.0]
        R = 0.000625  # sigma_u = 0.025 (2.5% viewport width)

        # S = H * P * H^T + R (scalar)
        HP = [sum(H[k] * self.P[k][col] for k in range(4)) for col in range(4)]
        S = sum(HP[k] * H[k] for k in range(4)) + R

        if S <= 0:
            return False, 999.0

        d_m2 = (y * y) / S
        if d_m2 > CHI2_95_2DOF:
            return False, d_m2

        inv_S = 1.0 / S
        # K = P * H^T * inv_S (4x1)
        P_HT = [sum(self.P[i][k] * H[k] for k in range(4)) for i in range(4)]
        K = [P_HT[i] * inv_S for i in range(4)]

        # State update
        self.x += K[0] * y
        self.y += K[1] * y
        self.vx += K[2] * y
        self.vy += K[3] * y

        # Covariance update: P = (I - K*H)*P
        for i in range(4):
            for j in range(4):
                self.P[i][j] -= K[i] * sum(H[k] * self.P[k][j] for k in range(4))

        self.hit_count += 1
        self.miss_count = 0
        self.last_update_epoch = time.time()
        return True, d_m2

    def get_error_ellipse_95(self) -> Dict[str, float]:
        """
        Derives 95% spatial error ellipse from 2D position covariance submatrix.
        Returns semi_major_m, semi_minor_m, orientation_deg.
        """
        p00 = max(0.001, self.P[0][0])
        p11 = max(0.001, self.P[1][1])
        p01 = self.P[0][1]

        # Eigenvalues of 2x2 matrix
        avg = (p00 + p11) / 2.0
        diff = (p00 - p11) / 2.0
        disc = math.sqrt(max(0.0, diff * diff + p01 * p01))
        lambda1 = max(0.0001, avg + disc)
        lambda2 = max(0.0001, avg - disc)

        # 95% scale factor sqrt(5.991) ~ 2.4477
        semi_major = 2.4477 * math.sqrt(lambda1)
        semi_minor = 2.4477 * math.sqrt(lambda2)
        orientation_rad = 0.5 * math.atan2(2.0 * p01, p00 - p11)

        return {
            "semi_major_m": round(semi_major, 3),
            "semi_minor_m": round(semi_minor, 3),
            "orientation_deg": round(math.degrees(orientation_rad), 1)
        }

    def to_dict(self) -> Dict[str, Any]:
        speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
        distance = math.sqrt(self.x * self.x + self.y * self.y)
        heading = math.degrees(math.atan2(self.vx, self.vy))
        ellipse = self.get_error_ellipse_95()

        return {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "confirmed": self.confirmed,
            "position": {
                "x_m": round(self.x, 3),
                "y_m": round(self.y, 3),
                "distance_m": round(distance, 2)
            },
            "velocity": {
                "vx_mps": round(self.vx, 3),
                "vy_mps": round(self.vy, 3),
                "speed_mps": round(speed, 2),
                "heading_deg": round(heading, 1)
            },
            "error_ellipse_95": ellipse,
            "radar_id": self.radar_target_id,
            "camera_track_id": self.camera_track_id,
            "hit_count": self.hit_count,
            "last_updated": datetime.fromtimestamp(self.last_update_epoch, tz=timezone.utc).isoformat()
        }


class EKFFusionTracker:
    """
    Coordinates multi-target Extended Kalman Filtering across Radar and Camera streams.
    """
    def __init__(self):
        self.tracks: Dict[str, EKFTrackState] = {}
        self.last_predict_time: float = time.time()

    def process_radar_target(
        self,
        radar_id: int,
        x_m: float,
        y_m: float,
        speed_mps: float,
        distance_m: float
    ) -> Dict[str, Any]:
        """
        Fuses a radar observation into the nearest existing EKF track or spawns a new one.
        """
        now = time.time()
        dt = now - self.last_predict_time
        self.last_predict_time = now

        # Run process prediction across all active tracks
        for track in self.tracks.values():
            track.predict(dt)

        theta = math.atan2(x_m, y_m)
        r = distance_m if distance_m > 0.05 else math.sqrt(x_m*x_m + y_m*y_m)
        rdot = speed_mps

        # Try to associate with existing track via Mahalanobis distance
        best_track = None
        lowest_d2 = 999.0

        for track in self.tracks.values():
            # Spatial pre-filter
            if math.hypot(track.x - x_m, track.y - y_m) < 2.5:
                accepted, d2 = track.update_radar(r, theta, rdot)
                if accepted and d2 < lowest_d2:
                    lowest_d2 = d2
                    best_track = track

        if best_track:
            best_track.radar_target_id = radar_id
            return {"status": "TRACK_UPDATED", "track": best_track.to_dict(), "mahalanobis_d2": round(lowest_d2, 2)}

        # Otherwise create new track
        track_id = f"EKF_TRK_{len(self.tracks) + 1:02d}"
        new_track = EKFTrackState(track_id=track_id, init_x=x_m, init_y=y_m, init_vx=0.0, init_vy=speed_mps)
        new_track.radar_target_id = radar_id
        self.tracks[track_id] = new_track
        logger.info(f"[EKF FUSION] Initiated new fused track {track_id} at ({x_m:.2f}m, {y_m:.2f}m)")

        return {"status": "TRACK_INITIATED", "track": new_track.to_dict(), "mahalanobis_d2": 0.0}

    def process_camera_detection(
        self,
        camera_track_id: str,
        norm_u: float,
        norm_v: float,
        class_name: str = "person",
        confidence: float = 0.85
    ) -> Dict[str, Any]:
        """
        Fuses a camera optical ray observation into the best matching EKF track.
        """
        now = time.time()
        best_track = None
        lowest_d2 = 999.0

        for track in self.tracks.values():
            accepted, d2 = track.update_camera(norm_u)
            if accepted and d2 < lowest_d2:
                lowest_d2 = d2
                best_track = track

        if best_track:
            best_track.camera_track_id = camera_track_id
            best_track.class_name = class_name
            best_track.confidence = confidence
            return {"status": "CAMERA_FUSED", "track": best_track.to_dict(), "mahalanobis_d2": round(lowest_d2, 2)}

        return {"status": "CAMERA_UNASSOCIATED", "norm_u": norm_u}

    def get_tracks(self) -> List[Dict[str, Any]]:
        """Returns all active EKF tracks with 95% error ellipses and velocities."""
        # Prune dead tracks older than 10 seconds
        now = time.time()
        active = {}
        for tid, t in self.tracks.items():
            if now - t.last_update_epoch < 10.0:
                active[tid] = t
        self.tracks = active
        return [t.to_dict() for t in self.tracks.values()]

    def reset(self) -> None:
        """Clears all active EKF tracks."""
        self.tracks.clear()
        self.last_predict_time = time.time()

# Global singleton
ekf_fusion_tracker = EKFFusionTracker()
