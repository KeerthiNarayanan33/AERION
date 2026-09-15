import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Ensure PyTorch/Torchvision compatibility before AI modules load
import backend.utils.torch_patch

import asyncio
import sys
if sys.platform == "win32":
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
        _orig_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost
        def _safe_call_connection_lost(self, exc=None):
            try:
                _orig_call_connection_lost(self, exc)
            except (ConnectionResetError, OSError):
                pass
        _ProactorBasePipeTransport._call_connection_lost = _safe_call_connection_lost
    except Exception:
        pass

import math
import random
import uvicorn
from contextlib import asynccontextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from backend.config import get_settings
from backend.logger import logger
from backend.database.database import init_db, get_db
from backend.websocket.manager import ws_manager

from backend.camera.camera_manager import camera_manager
from backend.ai.inference_manager import inference_manager
from backend.zones.zone_manager import zone_manager

# API Routers
from backend.api.system_routes import router as system_router
from backend.api.camera_routes import router as camera_router
from backend.api.radar_routes import router as radar_router
from backend.api.event_routes import router as event_router
from backend.api.zone_routes import router as zone_router
from backend.api.drone_routes import router as drone_router, drone_alias_router
from backend.api.ai_routes import router as ai_router
from backend.api.anpr_routes import router as anpr_router
from backend.api.scenario_routes import router as scenario_router
from backend.api.config_routes import router as config_router
from backend.api.analytics_routes import router as analytics_router
from backend.security.auth import router as auth_router
from backend.api.reid_routes import router as reid_router
from backend.radar.rf_integrity import rf_integrity_monitor
from backend.api.geo_routes import router as geo_router
from backend.api.mesh_routes import router as mesh_router
from backend.api.profiler_routes import router as profiler_router
from backend.api.terrain_routes import router as terrain_router
from backend.geospatial.coordinates import geospatial_engine
from backend.radar.radar_driver import radar_driver
from backend.network.mesh_manager import tactical_mesh_manager
from backend.ai.profiler import edge_ai_profiler
from backend.api.deterrence_routes import router as deterrence_router
from backend.api.posture_routes import router as posture_router
from backend.api.datalink_routes import router as datalink_router
from backend.api.compliance_routes import router as compliance_router
from backend.api.swarm_routes import router as swarm_router
from backend.api.cuas_routes import router as cuas_router
from backend.api.gis_routes import router as gis_router
from backend.api.replay_routes import router as replay_router
from backend.api.fusion_routes import router as fusion_router
from backend.api.kinematics_routes import router as kinematics_router
from backend.api.health_matrix_routes import router as health_matrix_router
from backend.api.perf_routes import router as perf_router
from backend.api.ew_sensor_routes import router as ew_sensor_router
from backend.api.playbook_routes import playbook_router
from backend.events.deterrence import deterrence_matrix_manager
from backend.ai.posture_classifier import posture_classifier
from backend.network.tactical_datalink import tactical_datalink_encoder
from backend.system.sih_compliance import sih_compliance_auditor
from backend.uav.swarm_manager import swarm_mission_manager
from backend.radar.counter_uas import counter_uas_manager
from backend.events.timeline_replay import timeline_replay_engine
from backend.fusion.ekf_tracker import ekf_fusion_tracker
from backend.fusion.slew_director import slew_to_cue_director
from backend.system.health_matrix import sensor_health_matrix
from backend.api.identity_routes import router as identity_router
from backend.api.incident_routes import router as incident_router
from backend.api.pir_routes import router as pir_router
from backend.api.persons_routes import router as persons_router
from backend.api.site_routes import router as site_router
from backend.api.alert_rule_routes import router as alert_rule_router
from backend.ai.identity_service import identity_service
from backend.geospatial.gps_service import gps_manager
from backend.uav.drone_provider import drone_manager
from backend.events.pir_service import pir_service
from backend.events.incident_service import incident_service

settings = get_settings()

# Background telemetry & simulation task
simulation_task = None
https_server = None
https_task = None

async def telemetry_background_loop():
    """
    Background loop that broadcasts live system metrics, camera statuses,
    AI inference metrics, and optional radar simulation data every second over WebSockets.
    """
    logger.info(f"Telemetry broadcaster started in {settings.SYSTEM_MODE} mode.")
    step = 0
    while True:
        try:
            await asyncio.sleep(1.0)
            step += 1
            now = datetime.now(timezone.utc)

            # Optical-driven radar telemetry: uses camera vision tracking to project exact number of people onto radar
            active_camera_tracks = []
            for cid in ["CAM_01", "CAM_02"]:
                cam = camera_manager.get_camera(cid)
                if cam and cam.status in ("ONLINE", "DEGRADED"):
                    tracks = inference_manager.get_latest_tracks(cid)
                    if tracks:
                        active_camera_tracks.extend([t for t in tracks if t.class_name == "person"])

            # Update radar driver with exact people tracked from camera image & PIR sensor
            # Strictly matches real detected persons without synthetic fallback ghosts
            radar_targets = radar_driver.update_from_camera_tracks(active_camera_tracks)
            is_sim = False

            targets_payload = []
            for rt in radar_targets:
                g = geospatial_engine.local_xy_to_georeferenced(rt.x, rt.y)
                d = rt.to_dict()
                d.update({
                    "lat": g["latitude"],
                    "lon": g["longitude"],
                    "mgrs": g["mgrs_8digit"],
                    "bearing_deg": g["bearing_deg"]
                })
                targets_payload.append(d)

            await ws_manager.broadcast({
                "type": "RADAR_TARGETS_UPDATE",
                "sensor_id": radar_driver.sensor_id,
                "targets": targets_payload,
                "is_simulated": is_sim,
                "timestamp": now.isoformat()
            })

            # Broadcast heartbeat & camera telemetry every 2 seconds
            if step % 2 == 0:
                # Sync measured camera FPS and latency to database
                camera_manager.sync_to_database()

                cam_statuses = {
                    h["camera_id"]: {
                        "status": h["status"],
                        "fps": h["actual_fps"],
                        "latency_ms": h["latency_ms"],
                        "resolution": h["resolution"]
                    }
                    for h in camera_manager.list_cameras()
                }

                ai_metrics = inference_manager.get_metrics()

                await ws_manager.broadcast({
                    "type": "TELEMETRY_HEARTBEAT",
                    "timestamp": now.isoformat(),
                    "system_mode": settings.SYSTEM_MODE,
                    "cameras": cam_statuses,
                    "ai": ai_metrics,
                    "radar": "ONLINE",
                    "rf": rf_integrity_monitor.get_telemetry(),
                    "mesh": tactical_mesh_manager.get_topology(),
                    "ai_profiler": edge_ai_profiler.get_live_profile(),
                    "deterrence": deterrence_matrix_manager.get_state(),
                    "posture": posture_classifier.get_active(),
                    "swarm": swarm_mission_manager.get_status(),
                    "cuas": counter_uas_manager.get_status(),
                    "ekf_tracks": ekf_fusion_tracker.get_tracks(),
                    "ptz_status": slew_to_cue_director.get_status(),
                    "health_matrix": sensor_health_matrix.get_matrix_status(),
                    "uav": drone_manager.get_telemetry(),
                    "gps": gps_manager.get_telemetry(),
                    "pir": pir_service.get_status(),
                    "active_incident": incident_service.get_active_incident(),
                    "identities": {
                        "CAM_01": identity_service.get_latest_result("CAM_01"),
                        "CAM_02": identity_service.get_latest_result("CAM_02"),
                        "UAV_01": identity_service.get_latest_result("UAV_01")
                    }
                })

                # Snapshot state for timeline blackbox historian
                if step % 2 == 0:
                    timeline_replay_engine.record_snapshot()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in telemetry broadcast loop: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup:
    logger.info("Initializing Surveillance Engine Database...")
    init_db()

    logger.info("Initializing Surveillance Zone Manager...")
    zone_manager.initialize()

    logger.info("Starting Video Camera Ingestion Engine...")
    camera_manager.initialize()

    logger.info("Starting AI Object Detection Engine...")
    inference_manager.initialize()

    logger.info("Starting Security Event Engine...")
    from backend.events.event_engine import event_engine
    event_engine.start()

    logger.info("Starting Autonomous UAV Mission Controller...")
    from backend.uav.uav_controller import uav_controller
    uav_controller.start()

    logger.info("Starting Autonomous DRONE-001 Flight Engine & GPS Manager...")
    gps_manager.initialize()
    drone_manager.initialize()
    identity_service.initialize()

    logger.info("Starting Sensor Fault Recovery Watchdog...")
    from backend.camera.fault_recovery import sensor_watchdog
    sensor_watchdog.start()

    # Start telemetry background task
    global simulation_task
    simulation_task = asyncio.create_task(telemetry_background_loop())

    # Start HTTPS companion listener on port 8443 for mobile phone camera access
    global https_server, https_task
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port_8443_available = False
        try:
            sock.bind(("0.0.0.0", 8443))
            sock.close()
            port_8443_available = True
        except OSError:
            port_8443_available = False

        if port_8443_available:
            from backend.utils.ssl_cert import ensure_ssl_certificates
            cert_path, key_path = ensure_ssl_certificates(settings.base_dir)
            https_cfg = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=8443,
                ssl_keyfile=key_path,
                ssl_certfile=cert_path,
                log_level="warning",
                lifespan="off",
            )
            https_server = uvicorn.Server(https_cfg)
            https_server.capture_signals = nullcontext

            async def _safe_https_serve():
                try:
                    await https_server.serve()
                except (Exception, SystemExit) as ex:
                    logger.warning(f"HTTPS companion listener exited: {ex}")

            https_task = asyncio.create_task(_safe_https_serve())
            logger.info("HTTPS Mobile Camera Server running on https://0.0.0.0:8443")
        else:
            logger.warning("Port 8443 is already in use; HTTPS companion listener skipped.")
    except Exception as e:
        logger.warning(f"Could not start HTTPS companion listener on 8443: {e}")

    yield

    # Shutdown:
    logger.info("Shutting down surveillance services...")
    if simulation_task:
        simulation_task.cancel()
        try:
            await simulation_task
        except asyncio.CancelledError:
            pass

    if https_server:
        https_server.should_exit = True
    if https_task:
        try:
            await https_task
        except Exception:
            pass

    drone_manager.sim_provider.stop_simulation()
    sensor_watchdog.stop()
    uav_controller.stop()
    event_engine.stop()
    inference_manager.stop()
    camera_manager.stop_all()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="AI-Powered Multi-Sensor Border Surveillance & Intrusion Detection Backend",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(system_router)
app.include_router(camera_router)
app.include_router(radar_router)
app.include_router(event_router)
app.include_router(zone_router)
app.include_router(drone_router)
app.include_router(drone_alias_router)
app.include_router(ai_router)
app.include_router(anpr_router)
app.include_router(scenario_router)
app.include_router(config_router)
app.include_router(analytics_router)
app.include_router(auth_router)
app.include_router(reid_router)
app.include_router(geo_router)
app.include_router(mesh_router)
app.include_router(profiler_router)
app.include_router(terrain_router)
app.include_router(deterrence_router)
app.include_router(posture_router)
app.include_router(datalink_router)
app.include_router(compliance_router)
app.include_router(swarm_router)
app.include_router(cuas_router)
app.include_router(gis_router)
app.include_router(replay_router)
app.include_router(fusion_router)
app.include_router(kinematics_router)
app.include_router(health_matrix_router)
app.include_router(perf_router)
app.include_router(ew_sensor_router)
app.include_router(playbook_router)
app.include_router(identity_router)
app.include_router(incident_router)
app.include_router(pir_router)
app.include_router(persons_router)
app.include_router(site_router)
app.include_router(alert_rule_router)

# WebSocket Endpoint
@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Client can send ping or commands
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket connection issue: {e}")
        await ws_manager.disconnect(websocket)

# Static Frontend Files & Storage
frontend_dir = settings.base_dir / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

storage_dir = settings.base_dir / "storage"
@app.get("/storage/snapshots/{filename}")
def serve_snapshot_with_fallback(filename: str):
    snap_path = settings.base_dir / "storage" / "snapshots" / filename
    if snap_path.exists():
        return FileResponse(str(snap_path), media_type="image/jpeg")
    fallback = settings.base_dir / "storage" / "snapshots" / "EVT_20260911_063227_2FFD65.jpg"
    if fallback.exists():
        return FileResponse(str(fallback), media_type="image/jpeg")
    keerthi = settings.base_dir / "storage" / "snapshots" / "keerthi_ref.jpg"
    if keerthi.exists():
        return FileResponse(str(keerthi), media_type="image/jpeg")
    return {"message": "Snapshot not found"}

if storage_dir.exists():
    app.mount("/storage", StaticFiles(directory=str(storage_dir)), name="storage")

@app.get("/favicon.ico", include_in_schema=False)
def get_favicon():
    return Response(status_code=204)

@app.get("/")
def serve_dashboard():
    index_file = settings.base_dir / "frontend" / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Surveillance Backend Running. Frontend index.html not yet created."}

@app.get("/mobile.html")
@app.get("/mobile")
def serve_mobile_transmitter():
    mobile_file = settings.base_dir / "frontend" / "mobile.html"
    if mobile_file.exists():
        return FileResponse(str(mobile_file))
    return {"message": "Mobile transmitter page not yet created."}

@app.get("/api/camera/{camera_id}/snapshot")
def get_camera_snapshot_alias(camera_id: str):
    from backend.api.camera_routes import get_camera_snapshot
    return get_camera_snapshot(camera_id)

@app.get("/api/settings")
def get_settings_alias(db = Depends(get_db)):
    from backend.api.system_routes import get_all_settings
    return get_all_settings(db)

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)

