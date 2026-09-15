import math
from typing import List, Tuple, Optional
import cv2
import numpy as np

from backend.ai.detector_interface import Detection
from backend.ai.tracker_interface import TrackedObject

# Tactical HUD Palette (BGR format for OpenCV)
COLOR_PERSON = (118, 230, 0)         # Cyber Emerald #00e676
COLOR_VEHICLE = (255, 229, 0)        # Electric Cyan #00e5ff
COLOR_ALERT_CRITICAL = (68, 23, 255) # Critical Red #ff1744
COLOR_ALERT_WARNING = (0, 171, 255)  # Warning Amber #ffab00
COLOR_ALERT_APPROACH = (0, 214, 255) # Approaching Yellow #ffd600
COLOR_TEXT_BG = (10, 15, 20)         # Dark HUD slate
COLOR_WHITE = (240, 244, 248)

def draw_trajectory_trail(
    image: np.ndarray,
    trajectory: List[Tuple[int, int]],
    color: Tuple[int, int, int]
) -> None:
    """Draws fading breadcrumb trajectory lines showing movement path."""
    n_points = len(trajectory)
    if n_points < 2:
        return

    for i in range(1, n_points):
        pt1 = trajectory[i - 1]
        pt2 = trajectory[i]
        alpha = float(i) / float(n_points)
        thickness = max(1, int(round(alpha * 2.5)))
        cv2.line(image, pt1, pt2, color, thickness, cv2.LINE_AA)

def draw_tactical_box(
    image: np.ndarray,
    box: Tuple[int, int, int, int],
    center: Tuple[int, int],
    class_name: str,
    confidence: float,
    track_id: Optional[int] = None,
    speed: Optional[float] = None,
    zone_label: Optional[str] = None,
    intrusion_state: Optional[str] = "NORMAL",
    plate_text: Optional[str] = None,
    identity: Optional[str] = None,
    identity_conf: Optional[float] = None,
    authorization: Optional[str] = None
) -> np.ndarray:
    """Draws a tactical HUD bounding box with corner brackets, state label, and identity/authorization tags."""
    x1, y1, x2, y2 = box

    # Color priority by authorization or intrusion state
    if authorization in ("UNAUTHORIZED", "NOT_AUTHORIZED_FOR_ZONE"):
        color = COLOR_ALERT_CRITICAL
    elif authorization == "AUTHORIZED":
        color = COLOR_PERSON
    elif authorization == "UNVERIFIED":
        color = COLOR_ALERT_WARNING
    elif intrusion_state in ("RESTRICTED_ENTRY", "ACTIVE_EVENT"):
        color = COLOR_ALERT_CRITICAL
    elif intrusion_state == "WARNING":
        color = COLOR_ALERT_WARNING
    elif intrusion_state == "APPROACHING":
        color = COLOR_ALERT_APPROACH
    else:
        color = COLOR_PERSON if class_name == "person" else COLOR_VEHICLE

    # 1. Subtle semi-transparent box fill
    overlay = image.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(overlay, 0.08, image, 0.92, 0, image)

    # 2. Bounding rectangle
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 1)

    # 3. Tactical Corner Brackets
    bracket_len = min(16, max(6, (x2 - x1) // 5))
    # Top-Left
    cv2.line(image, (x1, y1), (x1 + bracket_len, y1), color, 2)
    cv2.line(image, (x1, y1), (x1, y1 + bracket_len), color, 2)
    # Top-Right
    cv2.line(image, (x2, y1), (x2 - bracket_len, y1), color, 2)
    cv2.line(image, (x2, y1), (x2, y1 + bracket_len), color, 2)
    # Bottom-Left
    cv2.line(image, (x1, y2), (x1 + bracket_len, y2), color, 2)
    cv2.line(image, (x1, y2), (x1, y2 - bracket_len), color, 2)
    # Bottom-Right
    cv2.line(image, (x2, y2), (x2 - bracket_len, y2), color, 2)
    cv2.line(image, (x2, y2), (x2 - bracket_len, y2), color, 2)

    # 4. Center Crosshair Dot
    cx, cy = center
    cv2.circle(image, (cx, cy), 3, color, -1)

    # 5. Label text
    id_str = f" #{track_id:02d}" if track_id is not None else ""
    speed_str = f" | {int(speed)}px/s" if speed and speed > 2.0 else ""
    state_str = f" [{intrusion_state}]" if intrusion_state and intrusion_state != "NORMAL" else ""
    label = f"{class_name.upper()}{id_str} {int(confidence * 100)}%{speed_str}{state_str}"
    if zone_label:
        label += f" | {zone_label}"

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.38
    thickness = 1
    (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, thickness)

    # Header label background
    bg_y1 = max(0, y1 - text_h - 6)
    bg_y2 = y1
    cv2.rectangle(image, (x1, bg_y1), (x1 + text_w + 6, bg_y2), color, -1)
    # Label text in high contrast dark text
    cv2.putText(
        image,
        label,
        (x1 + 3, y1 - 4),
        font,
        font_scale,
        COLOR_TEXT_BG,
        thickness,
        cv2.LINE_AA
    )

    # 6. Identity & Authorization badge (Section 12) - High Visibility Rendering
    if identity and class_name == "person":
        id_conf_pct = int((identity_conf or 0.90) * 100)
        font_scale_id = 0.52
        thick_id = 2

        if authorization == "AUTHORIZED":
            auth_label = f"  AUTHORIZED: {identity.upper()} ({id_conf_pct}%)  "
            badge_bg = (0, 190, 60)        # Vibrant Green
            badge_border = (255, 255, 255)
            text_color = (255, 255, 255)    # High-contrast bold white
        elif authorization in ("UNAUTHORIZED", "NOT_AUTHORIZED_FOR_ZONE"):
            auth_label = f"  UNAUTHORIZED: {identity.upper()} ({id_conf_pct}%)  "
            badge_bg = (30, 30, 220)       # Vivid Red
            badge_border = (255, 255, 255)
            text_color = (255, 255, 255)
        else:
            auth_label = f"  VERIFYING: {identity.upper()} ({id_conf_pct}%)  "
            badge_bg = (0, 160, 240)       # Amber
            badge_border = (255, 255, 255)
            text_color = (15, 15, 15)

        (auth_w, auth_h), auth_base = cv2.getTextSize(auth_label, font, font_scale_id, thick_id)

        # Place identity banner above the box (or just below top header) to avoid clipping at bottom of frame
        auth_y2 = max(auth_h + 8, bg_y1 - 2)
        auth_y1 = max(0, auth_y2 - auth_h - 8)

        # Draw tactile drop shadow & glow
        cv2.rectangle(image, (x1 - 1, auth_y1 - 1), (x1 + auth_w + 5, auth_y2 + 1), (0, 0, 0), -1)
        cv2.rectangle(image, (x1, auth_y1), (x1 + auth_w + 4, auth_y2), badge_bg, -1)
        cv2.rectangle(image, (x1, auth_y1), (x1 + auth_w + 4, auth_y2), badge_border, 1)
        cv2.putText(image, auth_label, (x1 + 2, auth_y2 - 5), font, font_scale_id, text_color, thick_id, cv2.LINE_AA)

        # In restricted zone, display clearance approval badge
        if authorization == "AUTHORIZED" and ("RESTRICTED" in str(zone_label or "").upper() or intrusion_state in ("RESTRICTED_ENTRY", "ACTIVE_EVENT")):
            clear_label = " [CLEARANCE: RESTRICTED ZONE PERMITTED] "
            (c_w, c_h), _ = cv2.getTextSize(clear_label, font, 0.40, 1)
            c_y1 = auth_y2 + 2
            c_y2 = min(image.shape[0] - 2, c_y1 + c_h + 6)
            cv2.rectangle(image, (x1, c_y1), (x1 + c_w + 4, c_y2), (0, 140, 40), -1)
            cv2.rectangle(image, (x1, c_y1), (x1 + c_w + 4, c_y2), (255, 255, 255), 1)
            cv2.putText(image, clear_label, (x1 + 2, c_y2 - 3), font, 0.40, (255, 255, 255), 1, cv2.LINE_AA)


    # 7. License plate badge for vehicles under the bounding box
    if plate_text and plate_text != "PLATE_NOT_READABLE":
        clean_p = plate_text.split("(")[0].strip()
        p_font = cv2.FONT_HERSHEY_SIMPLEX
        p_scale = 0.38
        p_thick = 1
        (p_w, p_h), _ = cv2.getTextSize(clean_p, p_font, p_scale, p_thick)
        badge_x = x1
        badge_y = min(image.shape[0] - 4, y2 + p_h + 8)
        # White HSRP badge background
        cv2.rectangle(image, (badge_x, y2 + 2), (badge_x + p_w + 26, badge_y), (255, 255, 255), -1)
        cv2.rectangle(image, (badge_x, y2 + 2), (badge_x + p_w + 26, badge_y), (20, 20, 20), 1)
        # Blue 'IND' badge
        cv2.rectangle(image, (badge_x, y2 + 2), (badge_x + 15, badge_y), (200, 70, 0), -1)
        cv2.putText(image, "IND", (badge_x + 1, badge_y - 3), p_font, 0.22, (255, 255, 255), 1, cv2.LINE_AA)
        # Black plate text
        cv2.putText(image, clean_p, (badge_x + 18, badge_y - 3), p_font, p_scale, (10, 10, 10), p_thick, cv2.LINE_AA)

    return image

def annotate_frame(
    image: np.ndarray,
    detections: List[Detection],
    fps: Optional[float] = None
) -> np.ndarray:
    """Annotates frame using raw detections (prior to tracking)."""
    annotated = image.copy()
    for d in detections:
        draw_tactical_box(
            annotated,
            box=d.box,
            center=d.center,
            class_name=d.class_name,
            confidence=d.confidence
        )

    if fps is not None:
        fps_text = f"AI INFERENCE: {fps:.1f} FPS"
        cv2.putText(annotated, fps_text, (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 229, 255), 1, cv2.LINE_AA)

    return annotated

def draw_surveillance_zones(image: np.ndarray) -> None:
    """Draws polygonal boundary overlays for defined zones (ZONE_A, ZONE_B, ZONE_C)."""
    try:
        from backend.zones.zone_manager import zone_manager
        zones = zone_manager.get_zones()
        h, w = image.shape[:2]
        for z in zones:
            if not z.coordinates or len(z.coordinates) < 3:
                continue
            pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in z.coordinates], np.int32)
            pts = pts.reshape((-1, 1, 2))

            if z.zone_type == "RESTRICTED":
                color = COLOR_ALERT_CRITICAL
                # Light translucent fill
                overlay = image.copy()
                cv2.fillPoly(overlay, [pts], color)
                cv2.addWeighted(overlay, 0.10, image, 0.90, 0, image)
                cv2.polylines(image, [pts], True, color, 2, cv2.LINE_AA)
                lbl_x = max(10, min(pts[:, 0, 0]) + 10)
                lbl_y = max(20, min(pts[:, 0, 1]) + 20)
                cv2.putText(image, f"{z.name.upper()} [RESTRICTED]", (lbl_x, lbl_y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)
            elif z.zone_type == "WARNING":
                color = COLOR_ALERT_WARNING
                cv2.polylines(image, [pts], True, color, 1, cv2.LINE_AA)
                lbl_x = max(10, min(pts[:, 0, 0]) + 10)
                lbl_y = max(20, min(pts[:, 0, 1]) + 20)
                cv2.putText(image, f"{z.name.upper()} [WARNING]", (lbl_x, lbl_y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)
            else:
                color = (0, 180, 80)
                cv2.polylines(image, [pts], True, color, 1, cv2.LINE_AA)
    except Exception:
        pass

def annotate_tracked_frame(
    image: np.ndarray,
    tracks: List[TrackedObject],
    fps: Optional[float] = None,
    camera_label: Optional[str] = None
) -> np.ndarray:
    """
    Annotates frame with multi-object persistent Track IDs,
    movement trajectory history trails, zone boundaries, and critical intrusion banners.
    """
    annotated = image.copy()

    # 1. Draw Surveillance Zone boundaries
    draw_surveillance_zones(annotated)

    # 2. Draw Trajectory Trails first (colored by intrusion severity)
    for trk in tracks:
        if trk.intrusion_state in ("RESTRICTED_ENTRY", "ACTIVE_EVENT"):
            trail_color = COLOR_ALERT_CRITICAL
        elif trk.intrusion_state == "WARNING":
            trail_color = COLOR_ALERT_WARNING
        elif trk.intrusion_state == "APPROACHING":
            trail_color = COLOR_ALERT_APPROACH
        else:
            trail_color = COLOR_PERSON if trk.class_name == "person" else COLOR_VEHICLE

        draw_trajectory_trail(annotated, trk.trajectory, trail_color)

    # 3. Draw Bounding Boxes with Track IDs, Identity, and Zone States
    for trk in tracks:
        draw_tactical_box(
            annotated,
            box=trk.box,
            center=trk.center,
            class_name=trk.class_name,
            confidence=trk.confidence,
            track_id=trk.track_id,
            speed=trk.speed,
            zone_label=trk.zone_name or trk.zone_id,
            intrusion_state=trk.intrusion_state,
            plate_text=getattr(trk, "plate_text", None),
            identity=getattr(trk, "identity", None),
            identity_conf=getattr(trk, "identity_confidence", None),
            authorization=getattr(trk, "authorization", None)
        )

    # 4. Breach Banner: ONLY for UNAUTHORIZED targets
    unauthorized_breaches = [
        t for t in tracks
        if t.intrusion_state in ("RESTRICTED_ENTRY", "ACTIVE_EVENT")
        and getattr(t, "authorization", None) != "AUTHORIZED"
    ]
    authorized_in_restricted = [
        t for t in tracks
        if getattr(t, "authorization", None) == "AUTHORIZED"
        and ("RESTRICTED" in str(t.zone_name or "").upper() or t.intrusion_state in ("RESTRICTED_ENTRY", "ACTIVE_EVENT") or t.zone_id == "ZONE_C")
    ]

    h, w = annotated.shape[:2]
    if unauthorized_breaches:
        banner_overlay = annotated.copy()
        cv2.rectangle(banner_overlay, (0, 0), (w, 34), (0, 0, 190), -1)
        cv2.addWeighted(banner_overlay, 0.85, annotated, 0.15, 0, annotated)
        cv2.rectangle(annotated, (0, 0), (w, 34), (0, 0, 255), 2)
        b_names = ", ".join([f"{t.class_name.upper()} #{t.track_id:02d}" for t in unauthorized_breaches])
        alert_text = f"CRITICAL ALARM: RESTRICTED ZONE BREACH - [{b_names}]"
        cv2.putText(annotated, alert_text, (15, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2, cv2.LINE_AA)
    elif authorized_in_restricted:
        banner_overlay = annotated.copy()
        cv2.rectangle(banner_overlay, (0, 0), (w, 34), (10, 120, 40), -1)
        cv2.addWeighted(banner_overlay, 0.85, annotated, 0.15, 0, annotated)
        cv2.rectangle(annotated, (0, 0), (w, 34), (0, 230, 80), 2)
        a_names = ", ".join([f"{getattr(t, 'identity', 'STAFF')}" for t in authorized_in_restricted])
        auth_text = f"✓ ACCESS GRANTED: [{a_names.upper()}] - AUTHORIZED IN RESTRICTED PERIMETER"
        cv2.putText(annotated, auth_text, (15, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 2, cv2.LINE_AA)
    elif fps is not None or camera_label is not None:
        text = f"{camera_label or 'CAM_01'} | AI: {fps:.1f} FPS | TRACKS: {len(tracks)}"
        cv2.putText(annotated, text, (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 229, 255), 1, cv2.LINE_AA)

    return annotated
