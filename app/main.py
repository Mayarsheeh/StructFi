from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ["MPLBACKEND"] = "Agg"

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from app.core.config import settings
except Exception:
    class _FallbackSettings:
        APP_NAME = "StructFi Simulator"
        APP_VERSION = "0.2.0-demo"
        PROJECT_NAME = "StructFi"
        PROJECT_FULL_NAME = "Low-Cost Enterprise Wi-Fi System Prototype"
        API_BASE_URL = "http://127.0.0.1:8000"
        CORS_ALLOWED_ORIGINS = ["*"]
        CENTRAL_ROUTER = {"name": "StructFi Central Controller", "management_ip": "192.168.10.1"}
        VLAN_PROFILES = []
        SSID_PROFILES = []
        RADIUS_PROFILE = {}
        ACCESS_POLICIES = []
        IDS_RULES = []
        IDS_THRESHOLDS = {}
        AI_THRESHOLDS = {}
        AI_RECOMMENDATION_POLICY = {}
        ESP32_NODE_PROFILE = {}
        SIMULATION = {}
        MOBILE_API = {}
        RENDERING = {}
    settings = _FallbackSettings()

from app.services.planner import PlacementPlanner
from app.services.simulator import StructiFiSimulator
from app.services.segmentation import NetworkSegmentation
from app.services.reporting import ReportGenerator
from app.services.floorplan_manager import FloorplanManager
from app.services.dxf_room_extractor import DXFRoomExtractor
from app.services.advanced_cad_planner import AdvancedCADPlanner
from app.services.cad_visualizer import CADVisualizer
from app.services.cad_file_manager import CADFileManager
from app.services.runtime_reset import RuntimeResetService

try:
    from app.services.ids_engine import IDSEngine
except Exception:
    IDSEngine = None

try:
    from app.services.security import SecurityEngine
except Exception:
    SecurityEngine = None


app = FastAPI(
    title="StructFi Simulator",
    version=getattr(settings, "APP_VERSION", "0.2.0-demo"),
    description="Backend API for the StructFi low-cost enterprise Wi-Fi graduation project prototype.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(settings, "CORS_ALLOWED_ORIGINS", ["*"]) or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------
# Services
# -------------------------------------------------------------------

simulator = StructiFiSimulator()
segmentation = NetworkSegmentation()
reporter = ReportGenerator()
floorplan_manager = FloorplanManager()
dxf_room_extractor = DXFRoomExtractor()
advanced_cad_planner = AdvancedCADPlanner()
cad_visualizer = CADVisualizer()
cad_file_manager = CADFileManager()
runtime_reset_service = RuntimeResetService()
ids_engine = IDSEngine() if IDSEngine else None
security_engine = SecurityEngine() if SecurityEngine else None


# -------------------------------------------------------------------
# Request models
# -------------------------------------------------------------------

class NodeStatusUpdate(BaseModel):
    node_id: int
    status: str


class AccessCheckRequest(BaseModel):
    source_role: str
    target_zone: str


class MobileClientConfig(BaseModel):
    base_url: Optional[str] = None


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------

def _model_to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list):
        return [_model_to_dict(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return obj


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _latest_building_dict() -> Optional[Dict[str, Any]]:
    model = None
    try:
        model = dxf_room_extractor.get_latest_building_model()
    except Exception:
        model = None

    if model:
        return _model_to_dict(model)

    path = Path("data/parsed/latest_building.json")
    data = _read_json(path)
    return data if isinstance(data, dict) else None


def _get_latest_plan_model_or_dict() -> Optional[Dict[str, Any]]:
    try:
        if hasattr(advanced_cad_planner, "get_latest_plan_model"):
            result = advanced_cad_planner.get_latest_plan_model()
            if result:
                return _model_to_dict(result)
    except Exception:
        pass

    try:
        if hasattr(advanced_cad_planner, "get_latest_plan"):
            result = advanced_cad_planner.get_latest_plan()
            if result:
                return _model_to_dict(result)
    except Exception:
        pass

    data = _read_json(Path("data/parsed/latest_plan.json"))
    return data if isinstance(data, dict) else None


def _plan_from_latest_building_or_dxf() -> Optional[Dict[str, Any]]:
    try:
        if hasattr(advanced_cad_planner, "plan_from_latest_building"):
            result = advanced_cad_planner.plan_from_latest_building()
            if result:
                return _model_to_dict(result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Planning failed in plan_from_latest_building: {str(e)}",
        )

    try:
        if hasattr(advanced_cad_planner, "plan_from_latest_dxf"):
            result = advanced_cad_planner.plan_from_latest_dxf()
            if result:
                return _model_to_dict(result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Planning failed in plan_from_latest_dxf: {str(e)}",
        )

    return None


def _get_or_create_latest_plan() -> Dict[str, Any]:
    plan = _get_latest_plan_model_or_dict()
    if plan:
        return plan

    plan = _plan_from_latest_building_or_dxf()
    if not plan:
        raise HTTPException(status_code=404, detail="No valid CAD planning result available")

    return plan


def _extract_plan_nodes(plan: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(plan, dict):
        return []

    for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
        value = plan.get(key)
        if isinstance(value, list):
            return value

    result = plan.get("result")
    if isinstance(result, dict):
        return _extract_plan_nodes(result)

    data = plan.get("data")
    if isinstance(data, dict):
        return _extract_plan_nodes(data)

    return []


def _render_response(message: str, image: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "message": message,
        "image": image,
        "result": image,
    }


def _safe_call_visualizer_method(method_names, *args, **kwargs):
    last_error = None

    for name in method_names:
        if not hasattr(cad_visualizer, name):
            continue

        try:
            method = getattr(cad_visualizer, name)
            return method(*args, **kwargs)
        except TypeError:
            try:
                method = getattr(cad_visualizer, name)
                return method()
            except Exception as e:
                last_error = e
        except Exception as e:
            last_error = e

    if last_error:
        raise last_error

    raise AttributeError(f"None of these CADVisualizer methods exist: {method_names}")


def _rendered_image_payload(file_name: str, kind: str) -> Optional[Dict[str, Any]]:
    path = Path("data/rendered") / file_name
    if not path.exists():
        return None
    return {
        "file_name": file_name,
        "file_path": str(path).replace("\\", "/"),
        "url": f"/cad/rendered/{file_name}",
        "kind": kind,
    }


def _current_images() -> Dict[str, Optional[Dict[str, Any]]]:
    return {
        "extract_rooms": _rendered_image_payload("cad_extract_rooms.png", "extract_rooms"),
        "plan": _rendered_image_payload("cad_plan_nodes.png", "plan"),
        "heatmap": _rendered_image_payload("cad_heatmap.png", "heatmap"),
    }


def _state_dict() -> Dict[str, Any]:
    try:
        state = simulator.get_state()
        if isinstance(state, dict):
            return state
        return _model_to_dict(state) or {}
    except Exception:
        return {}


def _project_config_payload() -> Dict[str, Any]:
    return {
        "project": {
            "name": getattr(settings, "PROJECT_NAME", "StructFi"),
            "full_name": getattr(settings, "PROJECT_FULL_NAME", "Low-Cost Enterprise Wi-Fi System Prototype"),
            "mode": getattr(settings, "PROJECT_MODE", "graduation_demo"),
            "app_name": getattr(settings, "APP_NAME", "StructFi Simulator"),
            "version": getattr(settings, "APP_VERSION", "0.2.0-demo"),
        },
        "api": {
            "base_url": getattr(settings, "API_BASE_URL", "http://127.0.0.1:8000"),
            "dashboard_url": getattr(settings, "DASHBOARD_URL", "http://127.0.0.1:8501"),
        },
        "central_router": getattr(settings, "CENTRAL_ROUTER", {}),
        "esp32_node_profile": getattr(settings, "ESP32_NODE_PROFILE", {}),
        "simulation": getattr(settings, "SIMULATION", {}),
        "mobile_api": getattr(settings, "MOBILE_API", {}),
    }


# -------------------------------------------------------------------
# Startup
# -------------------------------------------------------------------

@app.on_event("startup")
def reset_runtime_on_startup():
    global simulator

    # Keep startup safe for the dashboard. Do not delete uploaded CAD files.
    try:
        runtime_reset_service.reset_all_runtime_state()
    except Exception:
        pass

    simulator = StructiFiSimulator()


# -------------------------------------------------------------------
# Health / project info
# -------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "StructFi backend is running",
        "project": getattr(settings, "PROJECT_FULL_NAME", "StructFi"),
        "version": getattr(settings, "APP_VERSION", "0.2.0-demo"),
    }


@app.get("/health")
def health_check():
    return {
        "ok": True,
        "backend": "online",
        "project": getattr(settings, "PROJECT_NAME", "StructFi"),
        "version": getattr(settings, "APP_VERSION", "0.2.0-demo"),
        "latest_cad": cad_file_manager.get_latest_cad() is not None,
        "latest_building": _latest_building_dict() is not None,
        "latest_plan": _get_latest_plan_model_or_dict() is not None,
    }


@app.get("/project/info")
def project_info():
    return _project_config_payload()


@app.get("/config/all")
def get_all_config():
    return {
        **_project_config_payload(),
        "network": {
            "vlans": getattr(settings, "VLAN_PROFILES", []),
            "ssids": getattr(settings, "SSID_PROFILES", []),
            "radius": getattr(settings, "RADIUS_PROFILE", {}),
            "access_policies": getattr(settings, "ACCESS_POLICIES", []),
        },
        "ai": {
            "thresholds": getattr(settings, "AI_THRESHOLDS", {}),
            "recommendation_policy": getattr(settings, "AI_RECOMMENDATION_POLICY", {}),
        },
        "ids": {
            "thresholds": getattr(settings, "IDS_THRESHOLDS", {}),
            "rules": getattr(settings, "IDS_RULES", []),
        },
        "rendering": getattr(settings, "RENDERING", {}),
    }


# -------------------------------------------------------------------
# Basic planner / simulation
# -------------------------------------------------------------------

@app.get("/planner/nodes")
def planner_nodes():
    planner = PlacementPlanner()
    return {
        "message": "Suggested node placement generated successfully",
        "nodes": planner.suggest_nodes(),
    }


@app.get("/simulation/state")
def simulation_state():
    return simulator.get_state()


@app.get("/simulation/summary")
def simulation_summary():
    state = _state_dict()
    return {
        "simulation_source": state.get("simulation_source", "unknown"),
        "step": state.get("step", 0),
        "timestamp": state.get("timestamp", ""),
        "rooms_count": len((state.get("building") or {}).get("rooms", [])) if isinstance(state.get("building"), dict) else 0,
        "planned_nodes_count": len(state.get("node_plan", []) or []),
        "runtime_nodes_count": len(state.get("node_runtime", []) or []),
        "clients_count": len(state.get("clients", []) or []),
        "alerts_count": len((state.get("security_state") or {}).get("alerts", []) or []),
        "ai_status": ((state.get("ai_output") or {}).get("health_summary") or {}).get("status", "unknown"),
    }


@app.post("/simulation/step")
def simulation_step():
    simulator.step()
    return simulator.get_state()


@app.post("/simulation/run-steps/{steps}")
def simulation_run_steps(steps: int):
    steps = max(1, min(int(steps), 100))
    for _ in range(steps):
        simulator.step()
    return simulator.get_state()


@app.post("/simulation/reset")
def simulation_reset():
    global simulator

    try:
        runtime_reset_service.reset_all_runtime_state()
    except Exception:
        pass

    simulator = StructiFiSimulator()

    return {
        "message": "Simulation reset successfully",
        "state": simulator.get_state(),
    }


@app.post("/simulation/apply-cad-plan")
def apply_cad_plan_to_simulation():
    plan = _get_or_create_latest_plan()

    try:
        simulator.load_cad_plan(plan)
        return {
            "message": "CAD plan applied to simulation successfully",
            "state": simulator.get_state(),
            "plan_summary": plan.get("summary", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply CAD plan: {str(e)}")


@app.get("/simulation/nodes")
def simulation_nodes():
    return {"nodes": _state_dict().get("node_runtime", [])}


@app.get("/simulation/clients")
def simulation_clients():
    return {"clients": _state_dict().get("clients", [])}


@app.get("/simulation/events")
def simulation_events(limit: int = 50):
    events = _state_dict().get("events", []) or []
    return {"events": events[-max(1, min(limit, 200)):]}


@app.get("/simulation/telemetry")
def simulation_telemetry(limit: int = 120):
    history = _state_dict().get("telemetry_history", []) or []
    return {"telemetry_history": history[-max(1, min(limit, 500)):]}


@app.post("/nodes/set-status")
def set_node_status(payload: NodeStatusUpdate):
    try:
        simulator.set_node_status(payload.node_id, payload.status)
        return {
            "message": f"Node-{payload.node_id} updated to {payload.status}",
            "state": simulator.get_state(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------------------------------------------------
# Network / centralized router / security / IDS / AI
# -------------------------------------------------------------------

@app.get("/router/config")
def router_config():
    return {"central_router": getattr(settings, "CENTRAL_ROUTER", {})}


@app.get("/router/status")
def router_status():
    state = _state_dict()
    controller = state.get("controller_state", {}) or {}
    return {
        "central_router": getattr(settings, "CENTRAL_ROUTER", {}),
        "controller_state": controller,
        "managed_nodes_count": controller.get("managed_nodes_count", len(state.get("node_runtime", []) or [])),
        "node_config_sync_ok": controller.get("node_config_sync_ok", True),
        "unified_ssid_enabled": controller.get("unified_ssid_enabled", True),
        "roaming_80211r_enabled": controller.get("roaming_80211r_enabled", True),
    }


@app.get("/network/profiles")
def network_profiles():
    return {
        "central_router": getattr(settings, "CENTRAL_ROUTER", {}),
        "vlans": segmentation.get_vlan_profiles() if hasattr(segmentation, "get_vlan_profiles") else getattr(settings, "VLAN_PROFILES", []),
        "ssids": segmentation.get_ssid_profiles() if hasattr(segmentation, "get_ssid_profiles") else getattr(settings, "SSID_PROFILES", []),
        "radius": segmentation.get_radius_profile() if hasattr(segmentation, "get_radius_profile") else getattr(settings, "RADIUS_PROFILE", {}),
        "access_policies": segmentation.get_policies(),
    }


@app.get("/network/vlans")
def network_vlans():
    return {"vlans": segmentation.get_vlan_profiles() if hasattr(segmentation, "get_vlan_profiles") else getattr(settings, "VLAN_PROFILES", [])}


@app.get("/network/ssids")
def network_ssids():
    return {"ssids": segmentation.get_ssid_profiles() if hasattr(segmentation, "get_ssid_profiles") else getattr(settings, "SSID_PROFILES", [])}


@app.get("/network/radius")
def network_radius():
    return {"radius": segmentation.get_radius_profile() if hasattr(segmentation, "get_radius_profile") else getattr(settings, "RADIUS_PROFILE", {})}


@app.get("/security/policies")
def security_policies():
    return {"policies": segmentation.get_policies()}


@app.post("/security/check-access")
def security_check_access(payload: AccessCheckRequest):
    allowed = segmentation.is_allowed(payload.source_role, payload.target_zone)
    policy = None
    if hasattr(segmentation, "get_policy_for"):
        policy = segmentation.get_policy_for(payload.source_role, payload.target_zone)
    return {
        "source_role": payload.source_role,
        "target_zone": payload.target_zone,
        "allowed": allowed,
        "policy": policy,
        "reason": "Policy allows access" if allowed else "Policy blocks access",
    }


@app.get("/security/access-matrix")
def security_access_matrix():
    state = _state_dict()
    matrix = (state.get("security_state") or {}).get("access_matrix", [])
    if not matrix and hasattr(segmentation, "evaluate_access"):
        matrix = segmentation.evaluate_access(state.get("clients", []) or [])
    return {"access_matrix": matrix}


@app.get("/security/alerts")
def security_alerts():
    state = _state_dict()
    return {"alerts": (state.get("security_state") or {}).get("alerts", [])}


@app.get("/ids/rules")
def ids_rules():
    return {
        "rules": getattr(settings, "IDS_RULES", []),
        "thresholds": getattr(settings, "IDS_THRESHOLDS", {}),
    }


@app.get("/ids/alerts")
def ids_alerts():
    return security_alerts()


@app.get("/ids/inspect")
def ids_inspect():
    state = _state_dict()
    nodes = state.get("node_runtime", []) or []
    matrix = (state.get("security_state") or {}).get("access_matrix", []) or []

    if ids_engine and hasattr(ids_engine, "inspect"):
        try:
            return {"alerts": ids_engine.inspect(nodes, matrix)}
        except Exception as e:
            return {"alerts": [], "detail": str(e)}

    if security_engine:
        alerts = []
        try:
            alerts.extend(security_engine.analyze_access_matrix(matrix))
            alerts.extend(security_engine.analyze_node_health(nodes))
        except Exception as e:
            return {"alerts": alerts, "detail": str(e)}
        return {"alerts": alerts}

    return {"alerts": []}


@app.get("/ai/summary")
def ai_summary():
    state = _state_dict()
    return state.get("ai_output", {})


@app.get("/ai/recommendations")
def ai_recommendations():
    ai = _state_dict().get("ai_output", {}) or {}
    return {"recommendations": ai.get("recommendations", [])}


@app.get("/ai/config")
def ai_config():
    return {
        "thresholds": getattr(settings, "AI_THRESHOLDS", {}),
        "recommendation_policy": getattr(settings, "AI_RECOMMENDATION_POLICY", {}),
    }


# -------------------------------------------------------------------
# Export
# -------------------------------------------------------------------

@app.get("/export/excel")
def export_excel():
    try:
        path = reporter.export_excel(simulator.get_state())
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=Path(path).name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel export failed: {str(e)}")


@app.get("/export/pdf")
def export_pdf():
    try:
        path = reporter.export_pdf(simulator.get_state())
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=Path(path).name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {str(e)}")


# -------------------------------------------------------------------
# Floorplan legacy image upload
# -------------------------------------------------------------------

@app.post("/floorplan/upload")
async def upload_floorplan(file: UploadFile = File(...)):
    content = await file.read()

    try:
        saved = floorplan_manager.save_floorplan(content, file.filename)
        return {
            "message": "Floorplan uploaded successfully",
            "floorplan": saved,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/floorplan/latest")
def get_latest_floorplan():
    result = floorplan_manager.get_latest_floorplan()
    if not result:
        return {"floorplan": None}
    return {"floorplan": result}


@app.get("/floorplan/image/{file_name}")
def get_floorplan_image(file_name: str):
    file_path = Path("data/uploads") / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Floorplan image not found")
    return FileResponse(file_path)


# -------------------------------------------------------------------
# CAD upload / latest
# -------------------------------------------------------------------

@app.post("/cad/upload")
async def upload_cad(file: UploadFile = File(...)):
    global simulator

    content = await file.read()

    try:
        try:
            runtime_reset_service.reset_derived_state_for_new_upload()
        except Exception:
            runtime_reset_service.reset_all_runtime_state()

        simulator = StructiFiSimulator()
        saved = cad_file_manager.save_cad_file(content, file.filename)

        return {
            "message": "CAD file uploaded successfully",
            "cad": saved,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CAD upload failed: {str(e)}")


@app.get("/cad/latest")
def get_latest_cad():
    result = cad_file_manager.get_latest_cad()
    if not result:
        return {"cad": None}
    return {"cad": result}


@app.get("/cad/latest-dxf")
def get_latest_dxf():
    result = cad_file_manager.get_latest_cad()
    if not result:
        return {"dxf": None}

    return {
        "dxf": {
            "file_name": result.get("working_dxf_file_name"),
            "file_path": result.get("working_dxf_file_path"),
            "summary": result.get("summary", {}),
        }
    }


# -------------------------------------------------------------------
# CAD room extraction
# -------------------------------------------------------------------

@app.post("/cad/extract-rooms")
def extract_rooms_from_latest_dxf():
    result = dxf_room_extractor.extract_from_latest_dxf()
    if not result:
        raise HTTPException(status_code=404, detail="No CAD/DXF uploaded yet")

    rooms = result.get("rooms", []) or []
    room_type_counts: Dict[str, int] = {}

    for room in rooms:
        rt = room.get("room_type", "unknown")
        room_type_counts[rt] = room_type_counts.get(rt, 0) + 1

    return {
        "message": "Smart room extraction completed successfully",
        "result": result,
        "debug": {
            "room_count": len(rooms),
            "room_type_counts": room_type_counts,
            "label_count": len(result.get("labels", []) or []),
            "wall_count": len(result.get("walls", []) or []),
            "floor_count": len(result.get("floors", []) or []),
            "extraction_confidence": result.get("extraction_confidence", 0.0),
        },
    }


@app.get("/cad/latest-rooms")
def get_latest_rooms():
    result = _latest_building_dict()
    if not result:
        return {"rooms_result": None}

    return {"rooms_result": result}


@app.get("/cad/rooms")
def cad_rooms():
    building = _latest_building_dict()
    if not building:
        return {"rooms": [], "count": 0}
    rooms = building.get("rooms", []) or []
    return {"rooms": rooms, "count": len(rooms)}


# -------------------------------------------------------------------
# CAD planning
# -------------------------------------------------------------------

@app.post("/cad/plan-nodes")
def plan_nodes_from_latest_dxf():
    result = _plan_from_latest_building_or_dxf()
    if not result:
        raise HTTPException(status_code=404, detail="No valid CAD/DXF rooms available")

    return {
        "message": "Advanced CAD planning completed successfully",
        "result": result,
    }


@app.get("/cad/latest-plan")
def get_latest_plan():
    result = _get_latest_plan_model_or_dict()
    if not result:
        return {"plan_result": None}

    return {"plan_result": result}


@app.get("/cad/plan-nodes")
def get_plan_nodes_only():
    plan = _get_latest_plan_model_or_dict()
    nodes = _extract_plan_nodes(plan)
    return {"nodes": nodes, "count": len(nodes), "summary": (plan or {}).get("summary", {}) if isinstance(plan, dict) else {}}


# -------------------------------------------------------------------
# CAD rendering
# -------------------------------------------------------------------

@app.post("/cad/render-extract-rooms")
def render_extract_rooms_from_latest():
    building_model = _latest_building_dict()
    if not building_model:
        raise HTTPException(status_code=404, detail="No extracted rooms available. Run Extract Rooms first.")

    try:
        image = _safe_call_visualizer_method(
            [
                "render_extract_rooms_from_latest",
                "render_rooms_from_latest",
                "render_latest_rooms",
                "render_rooms_overlay",
                "render_extracted_rooms",
                "render_room_extraction",
                "render_rooms",
            ]
        )
        return _render_response("Rendered extracted rooms successfully", image)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extract rooms rendering failed: {str(e)}")


@app.post("/cad/render-rooms")
def render_rooms_from_latest():
    return render_extract_rooms_from_latest()


@app.post("/cad/render-room-extraction")
def render_room_extraction_from_latest():
    return render_extract_rooms_from_latest()


@app.post("/cad/render-plan")
def render_plan_from_latest():
    plan = _get_or_create_latest_plan()

    try:
        if hasattr(cad_visualizer, "render_plan_from_latest"):
            image = cad_visualizer.render_plan_from_latest()
        else:
            image = cad_visualizer.render_plan_with_nodes(plan)

        return _render_response("Rendered plan with nodes successfully", image)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plan rendering failed: {str(e)}")


@app.post("/cad/render-heatmap")
def render_heatmap_from_latest():
    plan = _get_or_create_latest_plan()

    try:
        if hasattr(cad_visualizer, "render_heatmap_from_latest"):
            image = cad_visualizer.render_heatmap_from_latest()
        else:
            image = cad_visualizer.render_heatmap(plan)

        return _render_response("Rendered heatmap successfully", image)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Heatmap rendering failed: {str(e)}")


@app.get("/cad/rendered")
def list_rendered_images():
    return {"images": _current_images()}


@app.get("/cad/rendered/{file_name}")
def get_rendered_image(file_name: str):
    file_path = Path("data/rendered") / file_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Rendered image not found")

    return FileResponse(file_path)


# -------------------------------------------------------------------
# Mobile app endpoints
# -------------------------------------------------------------------

@app.get("/mobile/bootstrap")
def mobile_bootstrap():
    state = _state_dict()
    plan = _get_latest_plan_model_or_dict()
    building = _latest_building_dict()

    return {
        "project": _project_config_payload(),
        "state_summary": {
            "simulation_source": state.get("simulation_source", "unknown"),
            "step": state.get("step", 0),
            "nodes": len(state.get("node_runtime", []) or []),
            "clients": len(state.get("clients", []) or []),
            "alerts": len((state.get("security_state") or {}).get("alerts", []) or []),
            "ai_status": ((state.get("ai_output") or {}).get("health_summary") or {}).get("status", "unknown"),
        },
        "building_available": building is not None,
        "plan_available": plan is not None,
        "images": _current_images(),
        "network": {
            "vlans": getattr(settings, "VLAN_PROFILES", []),
            "ssids": getattr(settings, "SSID_PROFILES", []),
            "radius": getattr(settings, "RADIUS_PROFILE", {}),
        },
    }


@app.get("/mobile/dashboard")
def mobile_dashboard():
    state = _state_dict()
    return {
        "state": state,
        "summary": simulation_summary(),
        "images": _current_images(),
        "ai": state.get("ai_output", {}),
        "alerts": (state.get("security_state") or {}).get("alerts", []),
        "router": router_status(),
    }


@app.get("/mobile/images")
def mobile_images():
    return {"images": _current_images()}


@app.get("/mobile/nodes")
def mobile_nodes():
    return simulation_nodes()


@app.get("/mobile/clients")
def mobile_clients():
    return simulation_clients()


@app.get("/mobile/alerts")
def mobile_alerts():
    return security_alerts()


# -------------------------------------------------------------------
# Debug helpers
# -------------------------------------------------------------------

@app.get("/cad/debug-report")
def get_cad_debug_report():
    path = Path("data/parsed/cad_debug_report.json")
    if not path.exists():
        return {"debug_report": None}

    try:
        return {"debug_report": json.loads(path.read_text(encoding="utf-8"))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read debug report: {str(e)}")


@app.post("/cad/reset")
def reset_cad_runtime():
    global simulator

    try:
        runtime_reset_service.reset_all_runtime_state()
        simulator = StructiFiSimulator()

        return {
            "message": "CAD/runtime state reset successfully",
            "state": simulator.get_state(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CAD reset failed: {str(e)}")
