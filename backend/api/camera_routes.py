from datetime import datetime, timezone
from typing import List, Optional
import cv2
import numpy as np
import re
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database.database import get_db
from backend.database.models import CameraModel
from backend.camera.camera_manager import camera_manager
from backend.websocket.manager import ws_manager

router = APIRouter(prefix="/api/cameras", tags=["Cameras"])

class CameraConfigUpdate(BaseModel):
    name: Optional[str] = None
    source: Optional[str] = None
    zone_id: Optional[str] = None
    enabled: Optional[bool] = None

class CameraStatusUpdate(BaseModel):
    status: str
    error_message: Optional[str] = None

@router.get("")
def list_cameras(db: Session = Depends(get_db)):
    """Returns all surveillance cameras with live measured FPS and latency metrics."""
    cams = db.query(CameraModel).all()
    live_health = {h["camera_id"]: h for h in camera_manager.list_cameras()}

    result = []
    for c in cams:
        health = live_health.get(c.id, {})
        result.append({
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "source": c.source,
            "status": health.get("status", c.status),
            "resolution": health.get("resolution", c.resolution),
            "fps": health.get("actual_fps", c.fps),
            "latency_ms": health.get("latency_ms", c.latency_ms),
            "frame_count": health.get("frame_count", 0),
            "dropped_frames": health.get("dropped_frames", 0),
            "zone_id": c.zone_id,
            "enabled": c.enabled,
            "last_frame_at": c.last_frame_at.isoformat() if c.last_frame_at else None,
            "error_message": health.get("error_message", c.error_message),
            "is_simulated": health.get("is_simulated", False)
        })
    return result

def get_local_ip() -> str:
    """Detects primary outbound local LAN IP address."""
    from backend.utils.ssl_cert import get_outbound_ip
    return get_outbound_ip()

def generate_qr_svg(url: str) -> str:
    """Generates a clean SVG QR code string for the given URL."""
    try:
        import qrcode
        import qrcode.image.svg
        import io
        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(url, image_factory=factory, box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode('utf-8')
    except Exception as e:
        # Fallback minimal SVG placeholder if qrcode fails
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200"><rect width="200" height="200" fill="#030712"/><text x="100" y="100" fill="#38bdf8" font-size="12" text-anchor="middle">QR Unavailable ({e})</text></svg>'

@router.get("/network/info")
def get_network_info(selected_ip: Optional[str] = None):
    """Returns local network LAN IP, all available IPs, mobile URLs, and QR code."""
    from backend.utils.ssl_cert import get_all_local_ips
    available_ips = get_all_local_ips()
    
    # Use selected_ip if valid and in available_ips, otherwise primary IP
    if selected_ip and selected_ip in available_ips:
        local_ip = selected_ip
    else:
        local_ip = available_ips[0] if available_ips else "127.0.0.1"

    port = 8000
    https_port = 8443
    https_url = f"https://{local_ip}:{https_port}/mobile.html"
    http_url = f"http://{local_ip}:{port}/mobile.html"
    qr_svg = generate_qr_svg(https_url)

    return {
        "local_ip": local_ip,
        "available_ips": available_ips,
        "port": port,
        "https_port": https_port,
        "mobile_stream_url": https_url,
        "mobile_stream_url_https": https_url,
        "mobile_stream_url_http": http_url,
        "qr_target": https_url,
        "qr_svg": qr_svg
    }

@router.get("/network/qr")
def get_network_qr(target: Optional[str] = None, ip: Optional[str] = None, mode: str = "https"):
    """Returns SVG QR code image directly for browser embedding."""
    if not target:
        from backend.utils.ssl_cert import get_all_local_ips
        available_ips = get_all_local_ips()
        selected_ip = ip if (ip and ip in available_ips) else (available_ips[0] if available_ips else "127.0.0.1")
        if mode == "http":
            target = f"http://{selected_ip}:8000/mobile.html"
        else:
            target = f"https://{selected_ip}:8443/mobile.html"

    svg_content = generate_qr_svg(target)
    return Response(content=svg_content, media_type="image/svg+xml")


@router.get("/{camera_id}")
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    """Retrieves specific camera status and live telemetry."""
    c = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Camera not found")

    cam_inst = camera_manager.get_camera(camera_id)
    health = cam_inst.get_health() if cam_inst else {}

    return {
        "id": c.id,
        "name": c.name,
        "type": c.type,
        "source": c.source,
        "status": health.get("status", c.status),
        "resolution": health.get("resolution", c.resolution),
        "fps": health.get("actual_fps", c.fps),
        "latency_ms": health.get("latency_ms", c.latency_ms),
        "frame_count": health.get("frame_count", 0),
        "dropped_frames": health.get("dropped_frames", 0),
        "zone_id": c.zone_id,
        "enabled": c.enabled,
        "last_frame_at": c.last_frame_at.isoformat() if c.last_frame_at else None,
        "error_message": health.get("error_message", c.error_message),
        "is_simulated": health.get("is_simulated", False)
    }

@router.get("/{camera_id}/stream")
def stream_camera_feed(camera_id: str, max_frames: Optional[int] = None):
    """
    Live multipart/x-mixed-replace MJPEG video stream.
    Can be directly embedded in <img> tags in any web browser.
    """
    cam = camera_manager.get_camera(camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera [{camera_id}] not found")

    return StreamingResponse(
        cam.generate_mjpeg_stream(max_frames=max_frames),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, pre-check=0, post-check=0, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close"
        }
    )

@router.get("/{camera_id}/snapshot")
def get_camera_snapshot(camera_id: str):
    """Retrieves the latest captured frame as a JPEG image."""
    cam = camera_manager.get_camera(camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera [{camera_id}] not found")

    jpeg_bytes = cam.get_jpeg()
    if not jpeg_bytes:
        raise HTTPException(status_code=503, detail="Camera frame unavailable")

    return Response(content=jpeg_bytes, media_type="image/jpeg")

@router.put("/{camera_id}")
async def update_camera_config(camera_id: str, payload: CameraConfigUpdate, db: Session = Depends(get_db)):
    """Configures camera source (e.g., webcam index or smartphone IP stream URL)."""
    c = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Camera not found")

    if payload.name is not None:
        c.name = payload.name
    if payload.source is not None:
        c.source = payload.source
        # Notify CameraManager to restart capture with new source
        camera_manager.update_camera_source(camera_id, payload.source)
    if payload.zone_id is not None:
        c.zone_id = payload.zone_id
    if payload.enabled is not None:
        c.enabled = payload.enabled

    db.commit()

    await ws_manager.broadcast({
        "type": "CAMERA_CONFIG_UPDATED",
        "camera_id": c.id,
        "name": c.name,
        "source": c.source,
        "status": c.status,
        "zone_id": c.zone_id,
        "enabled": c.enabled
    })

    return {"message": "Camera updated", "camera_id": c.id}

@router.put("/{camera_id}/status")
async def update_camera_status(camera_id: str, payload: CameraStatusUpdate, db: Session = Depends(get_db)):
    """Updates camera operational status (ONLINE/OFFLINE/DEGRADED)."""
    c = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Camera not found")

    c.status = payload.status
    c.error_message = payload.error_message
    db.commit()

    await ws_manager.broadcast({
        "type": "CAMERA_STATUS_CHANGED",
        "camera_id": c.id,
        "status": c.status,
        "error_message": c.error_message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    return {"message": "Camera status updated", "camera_id": c.id, "status": c.status}

class TestConnectionRequest(BaseModel):
    source: str

@router.post("/{camera_id}/push-frame")
async def push_camera_frame(camera_id: str, request: Request):
    """
    Receives live raw JPEG or base64 frames directly from a smartphone browser via HTML5 canvas.
    Ingests frames into the camera's rolling buffer and sets camera status to ONLINE.
    """
    raw_data = await request.body()
    if not raw_data or len(raw_data) < 10:
        raise HTTPException(status_code=400, detail="Empty or invalid image payload")

    cam = camera_manager.get_camera(camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera [{camera_id}] not found")

    try:
        # Check if incoming data is raw binary JPEG or base64 data URL
        if raw_data.startswith(b"data:image"):
            import base64
            header, base64_str = raw_data.split(b",", 1)
            raw_bytes = base64.b64decode(base64_str)
        else:
            raw_bytes = raw_data

        nparr = np.frombuffer(raw_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            raise HTTPException(status_code=400, detail="Failed to decode JPEG frame")

        cam.source = "MOBILE_WEB"
        cam.ingest_frame(frame)

        return {
            "status": "ONLINE",
            "camera_id": camera_id,
            "frame_count": cam.frame_count,
            "fps": cam.actual_fps,
            "resolution": cam.resolution
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Frame ingestion error: {e}")

@router.post("/{camera_id}/test-connection")
def test_camera_connection(camera_id: str, payload: TestConnectionRequest):
    """
    Tests connectivity to an external RTSP/HTTP smartphone camera stream.
    Validates frame capture without disrupting active surveillance streams.
    Auto-normalizes common IP Webcam omissions (such as missing /video).
    """
    source = payload.source.strip()
    auto_appended = False

    # Auto-normalize IP Webcam URLs: if someone types e.g. http://10.146.49.50:8080 or http://10.146.49.50:8080/
    if re.match(r"^https?://[0-9a-zA-Z\.\-]+:[0-9]+/?$", source):
        source = source.rstrip("/") + "/video"
        auto_appended = True

    cap_src = int(source) if source.isdigit() else source

    try:
        # Fast socket pre-check for network streams to avoid long OpenCV timeouts
        if isinstance(cap_src, str) and (cap_src.startswith("http://") or cap_src.startswith("https://") or cap_src.startswith("rtsp://")):
            from urllib.parse import urlparse
            import socket
            parsed = urlparse(cap_src)
            host = parsed.hostname
            port = parsed.port or (80 if parsed.scheme == "http" else (554 if parsed.scheme == "rtsp" else 443))
            if host:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1.8)
                    s.connect((host, port))
                    s.close()
                except Exception as net_err:
                    local_ip = get_local_ip()
                    advice = f"Host unreachable ({host}:{port}). Make sure your phone and laptop are on the same Wi-Fi network (Laptop IP is {local_ip})."
                    if auto_appended:
                        advice += " (Tested with auto-appended /video path)"
                    return {
                        "reachable": False,
                        "error": advice,
                        "source": source
                    }

        cap = cv2.VideoCapture(cap_src)
        if not cap.isOpened():
            return {
                "reachable": False,
                "error": f"Failed to open video stream at {source}. If using IP Webcam app, verify server is running.",
                "source": source
            }

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None or frame.size == 0:
            return {
                "reachable": False,
                "error": "Stream opened, but frame capture timed out.",
                "source": source
            }

        h, w = frame.shape[:2]
        msg = f"Connection verified! Active resolution: {w}x{h}"
        if auto_appended:
            msg += " (Auto-appended '/video' to your IP Webcam URL)"

        return {
            "reachable": True,
            "resolution": f"{w}x{h}",
            "message": msg,
            "source": source
        }
    except Exception as e:
        return {
            "reachable": False,
            "error": str(e),
            "source": source
        }
