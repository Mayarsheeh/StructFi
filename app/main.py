from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ["MPLBACKEND"] = "Agg"

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.auth import (
    AuthenticatedUser,
    LoginRequest,
    LoginResponse,
    UserPublic,
    authenticate_user,
    create_access_token,
    get_current_user,
)

try:
    from app.core.config import settings
except Exception:
    class _FallbackSettings:
        APP_NAME = "StructFi Simulator"
        APP_VERSION = "0.2.0-demo"
        PROJECT_NAME = "StructFi"
        PROJECT_FULL_NAME = "Low-Cost Enterprise Wi-Fi System Prototype"
        API_BASE_URL = "https://structfi.onrender.com"
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
from app.services.wall_materials import WallMaterialManager
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


def _csv_env(name: str, default: Any) -> List[str]:
    """
    Read a comma-separated environment variable as a list.

    Kept in main.py so Render can control CORS without changing app/core/config.py.
    """
    raw = os.getenv(name)

    if not raw:
        if isinstance(default, list):
            return default
        if isinstance(default, str):
            return [default]
        return ["*"]

    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or (default if isinstance(default, list) else [str(default)])


def _cors_allowed_origins() -> List[str]:
    configured = getattr(settings, "CORS_ALLOWED_ORIGINS", ["*"]) or ["*"]
    return _csv_env("CORS_ALLOWED_ORIGINS", configured)



app = FastAPI(
    title="StructFi Simulator",
    version=getattr(settings, "APP_VERSION", "0.2.0-demo"),
    description="Backend API for the StructFi low-cost enterprise Wi-Fi graduation project prototype.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Auth API
# -------------------------------------------------------------------

@app.post("/auth/login", response_model=LoginResponse)
def auth_login(payload: LoginRequest):
    user = authenticate_user(payload.email, payload.password)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    access_token = create_access_token(user)

    return LoginResponse(
        access_token=access_token,
        user=user.to_public(),
    )


@app.get("/auth/me", response_model=UserPublic)
def auth_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return current_user.to_public()

@app.get("/mobile/context")
def mobile_context(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    user_public = current_user.to_public()

    if hasattr(user_public, "model_dump"):
        user_payload = user_public.model_dump()
    else:
        user_payload = user_public.dict()

    return {
        "authenticated": True,
        "user": user_payload,
        "organization": {
            "id": current_user.organization_id,
            "name": current_user.organization_name,
        },
        "project": {
            "id": current_user.project_id,
            "name": current_user.project_name,
        },
        "permissions": {
            "can_view_network": True,
            "can_manage_nodes": current_user.role in ["admin", "manager"],
            "can_change_channels": current_user.role in ["admin", "manager"],
            "can_restart_nodes": current_user.role in ["admin", "manager"],
            "can_generate_reports": current_user.role in ["admin", "manager"],
        },
    }

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
wall_material_manager = WallMaterialManager()
ids_engine = IDSEngine() if IDSEngine else None
security_engine = SecurityEngine() if SecurityEngine else None

# -------------------------------------------------------------------
# Request models
# -------------------------------------------------------------------

class NodeStatusUpdate(BaseModel):
    node_id: int
    status: str


class NodeChannelUpdateRequest(BaseModel):
    channel: int
    reason: Optional[str] = None


class AccessCheckRequest(BaseModel):
    source_role: str
    target_zone: str


class MobileClientConfig(BaseModel):
    base_url: Optional[str] = None


class MobileDeviceTokenRequest(BaseModel):
    token: str
    platform: str = "ios"
    device_id: Optional[str] = None
    app_version: Optional[str] = None


class WallMaterialConfigRequest(BaseModel):
    profile: Optional[str] = None
    profile_key: Optional[str] = None
    default_material: Optional[str] = None
    interior_wall_material: Optional[str] = None
    facade_material: Optional[str] = None
    door_material: Optional[str] = None
    window_material: Optional[str] = None
    structural_wall_material: Optional[str] = None
    custom_overrides: Dict[str, Any] = {}


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



def _unwrap_plan_payload(plan: Any) -> Optional[Dict[str, Any]]:
    """
    Accept all plan shapes used across the project and return the actual planning payload.

    Supported shapes:
    - {node_plan: [...], summary: ...}
    - {nodes: [...], summary: ...}
    - {result: {...}}
    - {data: {...}}
    - {plan_result: {...}}
    - {message: ..., result: {...}}
    """
    plan = _model_to_dict(plan)

    if not isinstance(plan, dict):
        return None

    for wrapper_key in ["plan_result", "result", "data"]:
        wrapped = plan.get(wrapper_key)
        if isinstance(wrapped, dict):
            unwrapped = _unwrap_plan_payload(wrapped)
            if isinstance(unwrapped, dict):
                return unwrapped

    return plan


def _plan_has_nodes(plan: Optional[Dict[str, Any]]) -> bool:
    return len(_extract_plan_nodes(plan)) > 0


def _simulation_state_needs_plan() -> bool:
    state = _state_dict()
    node_runtime = state.get("node_runtime", []) or []
    node_plan = state.get("node_plan", []) or []
    building = state.get("building")
    return not node_runtime or not node_plan or building is None


def _apply_latest_plan_to_simulation_or_raise() -> Dict[str, Any]:
    """
    Root fix for dashboard/mobile sync:
    always load the latest real plan into the simulator, even if API responses wrap it
    under plan_result/result/data. This keeps Render simulation state in sync with the
    latest CAD planning output used by Streamlit and the mobile app.
    """
    plan = _unwrap_plan_payload(_get_or_create_latest_plan())

    if not isinstance(plan, dict) or not _plan_has_nodes(plan):
        raise HTTPException(
            status_code=404,
            detail="No node plan found. Run Extract Rooms and Run AI Planning first.",
        )

    try:
        simulator.load_cad_plan(plan)
        return simulator.get_state()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to apply CAD plan: {str(exc)}")


def _auto_apply_latest_plan_if_state_empty() -> None:
    """
    Safety net for mobile and cloud demos.

    If the simulator is empty but a latest CAD plan exists, auto-apply it before returning
    mobile/simulation state. If no plan file exists but extracted rooms exist, try to
    rebuild a plan from the latest building model.
    """
    try:
        if not _simulation_state_needs_plan():
            return

        plan = _unwrap_plan_payload(_get_latest_plan_model_or_dict())

        if not isinstance(plan, dict) or not _plan_has_nodes(plan):
            plan = _unwrap_plan_payload(_plan_from_latest_building_or_dxf())

        if isinstance(plan, dict) and _plan_has_nodes(plan):
            simulator.load_cad_plan(plan)
    except Exception:
        # Do not make read endpoints fail because auto-apply failed.
        pass


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
                return _unwrap_plan_payload(result)
    except Exception:
        pass

    try:
        if hasattr(advanced_cad_planner, "get_latest_plan"):
            result = advanced_cad_planner.get_latest_plan()
            if result:
                return _unwrap_plan_payload(result)
    except Exception:
        pass

    data = _read_json(Path("data/parsed/latest_plan.json"))
    return _unwrap_plan_payload(data)


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
    plan = _unwrap_plan_payload(_get_latest_plan_model_or_dict())
    if plan:
        return plan

    plan = _unwrap_plan_payload(_plan_from_latest_building_or_dxf())
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

    plan_result = plan.get("plan_result")
    if isinstance(plan_result, dict):
        return _extract_plan_nodes(plan_result)

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
# Mobile Admin Control Layer
# -------------------------------------------------------------------

ADMIN_ACTION_LOG: List[Dict[str, Any]] = []

ALLOWED_5GHZ_CHANNELS = {
    36, 40, 44, 48,
    52, 56, 60, 64,
    100, 104, 108, 112, 116,
    132, 136, 140,
    149, 153, 157, 161, 165,
}


def _require_network_admin(current_user: AuthenticatedUser) -> None:
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(
            status_code=403,
            detail="This action requires admin or manager permission.",
        )


def _runtime_nodes_from_simulator_memory() -> List[Any]:
    state = getattr(simulator, "state", None)
    runtime_nodes = getattr(state, "node_runtime", None)

    if isinstance(runtime_nodes, list):
        return runtime_nodes

    if isinstance(state, dict):
        runtime_nodes = state.get("node_runtime")

        if isinstance(runtime_nodes, list):
            return runtime_nodes

    state_dict = _state_dict()
    runtime_nodes = state_dict.get("node_runtime", [])

    return runtime_nodes if isinstance(runtime_nodes, list) else []


def _node_id_value(node: Any) -> Optional[int]:
    try:
        if isinstance(node, dict):
            value = node.get("id")
        else:
            value = getattr(node, "id", None)

        if value is None:
            return None

        return int(value)
    except Exception:
        return None


def _find_runtime_node(node_id: int) -> Any:
    _auto_apply_latest_plan_if_state_empty()

    for node in _runtime_nodes_from_simulator_memory():
        if _node_id_value(node) == int(node_id):
            return node

    return None


def _get_node_radio(node: Any) -> Any:
    if isinstance(node, dict):
        return node.get("radio")

    return getattr(node, "radio", None)


def _get_radio_channel(radio: Any) -> Any:
    if isinstance(radio, dict):
        return radio.get("current_channel")

    return getattr(radio, "current_channel", None)


def _set_radio_channel(radio: Any, channel: int) -> None:
    if isinstance(radio, dict):
        radio["current_channel"] = channel
        return

    setattr(radio, "current_channel", channel)


def _touch_node_last_seen(node: Any) -> None:
    try:
        last_seen_value = simulator._now() if hasattr(simulator, "_now") else int(time.time())

        if isinstance(node, dict):
            node["last_seen"] = last_seen_value
        else:
            setattr(node, "last_seen", last_seen_value)
    except Exception:
        pass


def _node_control_snapshot(node: Any) -> Dict[str, Any]:
    node_payload = _model_to_dict(node) or {}

    if not isinstance(node_payload, dict):
        node_payload = {}

    radio_payload = _model_to_dict(node_payload.get("radio") or _get_node_radio(node)) or {}

    if not isinstance(radio_payload, dict):
        radio_payload = {}

    return {
        "id": node_payload.get("id"),
        "name": node_payload.get("name"),
        "status": node_payload.get("status"),
        "room_name": node_payload.get("room_name"),
        "connected_clients": node_payload.get("connected_clients"),
        "current_load": node_payload.get("current_load"),
        "radio": {
            "current_channel": radio_payload.get("current_channel"),
            "tx_power_dbm": radio_payload.get("tx_power_dbm"),
            "rssi_avg": radio_payload.get("rssi_avg"),
            "snr_avg": radio_payload.get("snr_avg"),
            "retry_rate_pct": radio_payload.get("retry_rate_pct"),
            "packet_loss_pct": radio_payload.get("packet_loss_pct"),
            "throughput_mbps": radio_payload.get("throughput_mbps"),
            "latency_ms": radio_payload.get("latency_ms"),
        },
    }


def _append_admin_action(
    *,
    current_user: AuthenticatedUser,
    action: str,
    node_id: int,
    old_value: Any,
    new_value: Any,
    reason: Optional[str],
) -> Dict[str, Any]:
    entry = {
        "id": len(ADMIN_ACTION_LOG) + 1,
        "timestamp": int(time.time()),
        "user_id": current_user.id,
        "user_email": current_user.email,
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization_name,
        "project_id": current_user.project_id,
        "project_name": current_user.project_name,
        "action": action,
        "node_id": node_id,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason or "No reason provided.",
    }

    ADMIN_ACTION_LOG.append(entry)
    return entry


@app.post("/mobile/admin/nodes/{node_id}/channel")
def mobile_admin_set_node_channel(
    node_id: int,
    payload: NodeChannelUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    _require_network_admin(current_user)

    if payload.channel not in ALLOWED_5GHZ_CHANNELS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported 5GHz channel. Use one of: "
                + ", ".join(str(ch) for ch in sorted(ALLOWED_5GHZ_CHANNELS))
            ),
        )

    node = _find_runtime_node(node_id)

    if node is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Runtime node {node_id} was not found. "
                "Run CAD planning and apply the latest plan to the simulation first."
            ),
        )

    radio = _get_node_radio(node)

    if radio is None:
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} has no radio telemetry object.",
        )

    old_channel = _get_radio_channel(radio)
    _set_radio_channel(radio, payload.channel)
    _touch_node_last_seen(node)

    audit_entry = _append_admin_action(
        current_user=current_user,
        action="change_channel",
        node_id=node_id,
        old_value=old_channel,
        new_value=payload.channel,
        reason=payload.reason,
    )

    return {
        "success": True,
        "message": f"Node {node_id} channel changed from {old_channel} to {payload.channel}.",
        "action": audit_entry,
        "node": _node_control_snapshot(node),
    }


@app.get("/mobile/admin/actions")
def mobile_admin_actions(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    _require_network_admin(current_user)

    actions = [
        action
        for action in ADMIN_ACTION_LOG
        if action.get("organization_id") == current_user.organization_id
        and action.get("project_id") == current_user.project_id
    ]

    return {
        "count": len(actions),
        "actions": list(reversed(actions[-50:])),
    }

# -------------------------------------------------------------------
# Mobile WiFi / SSID Admin Control
# -------------------------------------------------------------------

WIFI_CONFIG_BY_PROJECT: Dict[int, Dict[str, Any]] = {}

ALLOWED_WIFI_SECURITY_MODES = {
    "WPA2/WPA3 Personal",
    "WPA3 Personal",
    "WPA2 Enterprise",
    "Open Network",
}

ALLOWED_WIFI_BAND_MODES = {
    "Dual Band",
    "5GHz Only",
    "2.4GHz Only",
}

ALLOWED_WIFI_CHANNEL_MODES = {
    "Auto Optimized",
    "Manual",
    "AI Recommended",
}

ALLOWED_CLIENT_ISOLATION_MODES = {
    "Enabled",
    "Disabled",
}


class WifiAdminConfigRequest(BaseModel):
    ssid: str
    security_mode: str
    password: Optional[str] = None
    band_mode: str = "Dual Band"
    channel_mode: str = "Auto Optimized"
    guest_network_enabled: bool = True
    guest_ssid: Optional[str] = None
    band_steering_enabled: bool = True
    fast_roaming_enabled: bool = True
    client_isolation: str = "Enabled"
    reason: Optional[str] = None


def _default_wifi_config(current_user: AuthenticatedUser) -> Dict[str, Any]:
    return {
        "ssid": "StructFi-Secure",
        "security_mode": "WPA2/WPA3 Personal",
        "password": "StructFi@v301",
        "band_mode": "Dual Band",
        "channel_mode": "Auto Optimized",
        "guest_network_enabled": True,
        "guest_ssid": "StructFi-Guest",
        "band_steering_enabled": True,
        "fast_roaming_enabled": True,
        "client_isolation": "Enabled",
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization_name,
        "project_id": current_user.project_id,
        "project_name": current_user.project_name,
        "updated_by": "system",
        "updated_by_email": None,
        "updated_at": int(time.time()),
        "version": "v3.01",
    }


def _get_wifi_config(current_user: AuthenticatedUser) -> Dict[str, Any]:
    project_id = int(current_user.project_id)

    if project_id not in WIFI_CONFIG_BY_PROJECT:
        WIFI_CONFIG_BY_PROJECT[project_id] = _default_wifi_config(current_user)

    return WIFI_CONFIG_BY_PROJECT[project_id]


def _validate_wifi_config(payload: WifiAdminConfigRequest) -> None:
    ssid = payload.ssid.strip()

    if not ssid:
        raise HTTPException(status_code=400, detail="SSID name is required.")

    if len(ssid) < 3:
        raise HTTPException(
            status_code=400,
            detail="SSID name must be at least 3 characters.",
        )

    if len(ssid) > 32:
        raise HTTPException(
            status_code=400,
            detail="SSID name must not exceed 32 characters.",
        )

    if payload.security_mode not in ALLOWED_WIFI_SECURITY_MODES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported WiFi security mode.",
        )

    if payload.band_mode not in ALLOWED_WIFI_BAND_MODES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported WiFi band mode.",
        )

    if payload.channel_mode not in ALLOWED_WIFI_CHANNEL_MODES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported WiFi channel mode.",
        )

    if payload.client_isolation not in ALLOWED_CLIENT_ISOLATION_MODES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported client isolation mode.",
        )

    if payload.security_mode != "Open Network":
        password = payload.password or ""

        if len(password) < 8:
            raise HTTPException(
                status_code=400,
                detail="WiFi password must be at least 8 characters unless the network is open.",
            )

    if payload.guest_network_enabled:
        guest_ssid = (payload.guest_ssid or "").strip()

        if not guest_ssid:
            raise HTTPException(
                status_code=400,
                detail="Guest SSID is required when guest network is enabled.",
            )

        if len(guest_ssid) > 32:
            raise HTTPException(
                status_code=400,
                detail="Guest SSID must not exceed 32 characters.",
            )


@app.get("/mobile/admin/wifi/config")
def mobile_admin_get_wifi_config(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    _require_network_admin(current_user)

    return {
        "success": True,
        "config": _get_wifi_config(current_user),
    }


@app.post("/mobile/admin/wifi/config")
def mobile_admin_update_wifi_config(
    payload: WifiAdminConfigRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    _require_network_admin(current_user)
    _validate_wifi_config(payload)

    old_config = dict(_get_wifi_config(current_user))

    new_config = {
        "ssid": payload.ssid.strip(),
        "security_mode": payload.security_mode,
        "password": payload.password or "",
        "band_mode": payload.band_mode,
        "channel_mode": payload.channel_mode,
        "guest_network_enabled": bool(payload.guest_network_enabled),
        "guest_ssid": (payload.guest_ssid or "").strip(),
        "band_steering_enabled": bool(payload.band_steering_enabled),
        "fast_roaming_enabled": bool(payload.fast_roaming_enabled),
        "client_isolation": payload.client_isolation,
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization_name,
        "project_id": current_user.project_id,
        "project_name": current_user.project_name,
        "updated_by": current_user.name,
        "updated_by_email": current_user.email,
        "updated_at": int(time.time()),
        "version": "v3.01",
    }

    WIFI_CONFIG_BY_PROJECT[int(current_user.project_id)] = new_config

    audit_entry = {
        "id": len(ADMIN_ACTION_LOG) + 1,
        "timestamp": int(time.time()),
        "user_id": current_user.id,
        "user_email": current_user.email,
        "organization_id": current_user.organization_id,
        "project_id": current_user.project_id,
        "action": "wifi_config_update",
        "node_id": None,
        "old_value": old_config,
        "new_value": new_config,
        "reason": payload.reason or "WiFi configuration updated from StructFi Mobile v3.01.",
    }

    ADMIN_ACTION_LOG.append(audit_entry)

    return {
        "success": True,
        "message": "WiFi configuration updated successfully.",
        "config": new_config,
        "action": audit_entry,
    }


# -------------------------------------------------------------------
# Mobile Security / Access Control Admin
# -------------------------------------------------------------------

SECURITY_POLICY_BY_PROJECT: Dict[int, Dict[str, Any]] = {}

ALLOWED_FIREWALL_MODES = {
    "Balanced",
    "Strict",
    "Performance",
}

ALLOWED_THREAT_LEVELS = {
    "Low",
    "Medium",
    "High",
    "Critical",
}

ALLOWED_MANAGEMENT_ACCESS_MODES = {
    "Admins Only",
    "Managers + Admins",
    "Local Network Only",
}


class SecurityPolicyRequest(BaseModel):
    firewall_mode: str = "Balanced"
    ids_ips_enabled: bool = True
    threat_level: str = "Medium"
    block_unknown_devices: bool = True
    guest_to_lan_blocked: bool = True
    malicious_domain_filtering: bool = True
    management_access_mode: str = "Admins Only"
    blocked_devices: Optional[List[str]] = None
    reason: Optional[str] = None


def _default_security_policy(current_user: AuthenticatedUser) -> Dict[str, Any]:
    return {
        "firewall_mode": "Balanced",
        "ids_ips_enabled": True,
        "threat_level": "Medium",
        "block_unknown_devices": True,
        "guest_to_lan_blocked": True,
        "malicious_domain_filtering": True,
        "management_access_mode": "Admins Only",
        "blocked_devices": [],
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization_name,
        "project_id": current_user.project_id,
        "project_name": current_user.project_name,
        "updated_by": "system",
        "updated_by_email": None,
        "updated_at": int(time.time()),
        "version": "v3.01",
    }


def _get_security_policy(current_user: AuthenticatedUser) -> Dict[str, Any]:
    project_id = int(current_user.project_id)

    if project_id not in SECURITY_POLICY_BY_PROJECT:
        SECURITY_POLICY_BY_PROJECT[project_id] = _default_security_policy(current_user)

    return SECURITY_POLICY_BY_PROJECT[project_id]


def _validate_security_policy(payload: SecurityPolicyRequest) -> None:
    if payload.firewall_mode not in ALLOWED_FIREWALL_MODES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported firewall mode.",
        )

    if payload.threat_level not in ALLOWED_THREAT_LEVELS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported threat level.",
        )

    if payload.management_access_mode not in ALLOWED_MANAGEMENT_ACCESS_MODES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported management access mode.",
        )

    blocked_devices = payload.blocked_devices or []

    if not isinstance(blocked_devices, list):
        raise HTTPException(
            status_code=400,
            detail="Blocked devices must be a list.",
        )

    if len(blocked_devices) > 100:
        raise HTTPException(
            status_code=400,
            detail="Blocked devices list is too large.",
        )


@app.get("/mobile/admin/security/policy")
def mobile_admin_get_security_policy(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    _require_network_admin(current_user)

    return {
        "success": True,
        "policy": _get_security_policy(current_user),
    }


@app.post("/mobile/admin/security/policy")
def mobile_admin_update_security_policy(
    payload: SecurityPolicyRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    _require_network_admin(current_user)
    _validate_security_policy(payload)

    old_policy = dict(_get_security_policy(current_user))

    new_policy = {
        "firewall_mode": payload.firewall_mode,
        "ids_ips_enabled": bool(payload.ids_ips_enabled),
        "threat_level": payload.threat_level,
        "block_unknown_devices": bool(payload.block_unknown_devices),
        "guest_to_lan_blocked": bool(payload.guest_to_lan_blocked),
        "malicious_domain_filtering": bool(payload.malicious_domain_filtering),
        "management_access_mode": payload.management_access_mode,
        "blocked_devices": payload.blocked_devices or [],
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization_name,
        "project_id": current_user.project_id,
        "project_name": current_user.project_name,
        "updated_by": current_user.name,
        "updated_by_email": current_user.email,
        "updated_at": int(time.time()),
        "version": "v3.01",
    }

    SECURITY_POLICY_BY_PROJECT[int(current_user.project_id)] = new_policy

    audit_entry = {
        "id": len(ADMIN_ACTION_LOG) + 1,
        "timestamp": int(time.time()),
        "user_id": current_user.id,
        "user_email": current_user.email,
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization_name,
        "project_id": current_user.project_id,
        "project_name": current_user.project_name,
        "action": "security_policy_update",
        "node_id": None,
        "old_value": old_policy,
        "new_value": new_policy,
        "reason": payload.reason or "Security policy updated from StructFi Mobile v3.01.",
    }

    ADMIN_ACTION_LOG.append(audit_entry)

    return {
        "success": True,
        "message": "Security policy updated successfully.",
        "policy": new_policy,
        "action": audit_entry,
    }

# -------------------------------------------------------------------
# Mobile VLAN / Segmentation Admin
# -------------------------------------------------------------------

VLAN_CONFIG_BY_PROJECT: Dict[int, Dict[str, Any]] = {}

ALLOWED_SEGMENTATION_MODES = {
    "Standard",
    "Strict Isolation",
    "Performance",
}

ALLOWED_INTER_VLAN_ROUTING = {
    "Disabled",
    "Controlled",
    "Open",
}


class VlanConfigRequest(BaseModel):
    segmentation_mode: str = "Standard"
    segmentation_enabled: bool = True
    default_vlan_id: int = 10
    guest_vlan_id: int = 20
    iot_vlan_id: int = 30
    voice_vlan_id: int = 40
    isolate_guest_network: bool = True
    isolate_iot_devices: bool = True
    inter_vlan_routing: str = "Controlled"
    qos_enabled: bool = True
    reason: Optional[str] = None


def _default_vlan_config(current_user: AuthenticatedUser) -> Dict[str, Any]:
    return {
        "segmentation_mode": "Standard",
        "segmentation_enabled": True,
        "default_vlan_id": 10,
        "guest_vlan_id": 20,
        "iot_vlan_id": 30,
        "voice_vlan_id": 40,
        "isolate_guest_network": True,
        "isolate_iot_devices": True,
        "inter_vlan_routing": "Controlled",
        "qos_enabled": True,
        "vlans": [
            {
                "id": 10,
                "name": "Corporate",
                "purpose": "Main company devices",
                "status": "active",
            },
            {
                "id": 20,
                "name": "Guest",
                "purpose": "Visitor internet access",
                "status": "isolated",
            },
            {
                "id": 30,
                "name": "IoT",
                "purpose": "Smart devices and sensors",
                "status": "restricted",
            },
            {
                "id": 40,
                "name": "Voice",
                "purpose": "Voice and real-time traffic",
                "status": "qos",
            },
        ],
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization_name,
        "project_id": current_user.project_id,
        "project_name": current_user.project_name,
        "updated_by": "system",
        "updated_by_email": None,
        "updated_at": int(time.time()),
        "version": "v3.01",
    }


def _get_vlan_config(current_user: AuthenticatedUser) -> Dict[str, Any]:
    project_id = int(current_user.project_id)

    if project_id not in VLAN_CONFIG_BY_PROJECT:
        VLAN_CONFIG_BY_PROJECT[project_id] = _default_vlan_config(current_user)

    return VLAN_CONFIG_BY_PROJECT[project_id]


def _validate_vlan_id(value: int, label: str) -> None:
    if value < 1 or value > 4094:
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be between 1 and 4094.",
        )


def _validate_vlan_config(payload: VlanConfigRequest) -> None:
    if payload.segmentation_mode not in ALLOWED_SEGMENTATION_MODES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported segmentation mode.",
        )

    if payload.inter_vlan_routing not in ALLOWED_INTER_VLAN_ROUTING:
        raise HTTPException(
            status_code=400,
            detail="Unsupported inter-VLAN routing mode.",
        )

    _validate_vlan_id(payload.default_vlan_id, "Default VLAN ID")
    _validate_vlan_id(payload.guest_vlan_id, "Guest VLAN ID")
    _validate_vlan_id(payload.iot_vlan_id, "IoT VLAN ID")
    _validate_vlan_id(payload.voice_vlan_id, "Voice VLAN ID")

    vlan_ids = [
        payload.default_vlan_id,
        payload.guest_vlan_id,
        payload.iot_vlan_id,
        payload.voice_vlan_id,
    ]

    if len(vlan_ids) != len(set(vlan_ids)):
        raise HTTPException(
            status_code=400,
            detail="VLAN IDs must be unique.",
        )


@app.get("/mobile/admin/vlans/config")
def mobile_admin_get_vlan_config(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    _require_network_admin(current_user)

    return {
        "success": True,
        "config": _get_vlan_config(current_user),
    }


@app.post("/mobile/admin/vlans/config")
def mobile_admin_update_vlan_config(
    payload: VlanConfigRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    _require_network_admin(current_user)
    _validate_vlan_config(payload)

    old_config = dict(_get_vlan_config(current_user))

    new_config = {
        "segmentation_mode": payload.segmentation_mode,
        "segmentation_enabled": bool(payload.segmentation_enabled),
        "default_vlan_id": int(payload.default_vlan_id),
        "guest_vlan_id": int(payload.guest_vlan_id),
        "iot_vlan_id": int(payload.iot_vlan_id),
        "voice_vlan_id": int(payload.voice_vlan_id),
        "isolate_guest_network": bool(payload.isolate_guest_network),
        "isolate_iot_devices": bool(payload.isolate_iot_devices),
        "inter_vlan_routing": payload.inter_vlan_routing,
        "qos_enabled": bool(payload.qos_enabled),
        "vlans": [
            {
                "id": int(payload.default_vlan_id),
                "name": "Corporate",
                "purpose": "Main company devices",
                "status": "active",
            },
            {
                "id": int(payload.guest_vlan_id),
                "name": "Guest",
                "purpose": "Visitor internet access",
                "status": "isolated" if payload.isolate_guest_network else "active",
            },
            {
                "id": int(payload.iot_vlan_id),
                "name": "IoT",
                "purpose": "Smart devices and sensors",
                "status": "restricted" if payload.isolate_iot_devices else "active",
            },
            {
                "id": int(payload.voice_vlan_id),
                "name": "Voice",
                "purpose": "Voice and real-time traffic",
                "status": "qos" if payload.qos_enabled else "active",
            },
        ],
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization_name,
        "project_id": current_user.project_id,
        "project_name": current_user.project_name,
        "updated_by": current_user.name,
        "updated_by_email": current_user.email,
        "updated_at": int(time.time()),
        "version": "v3.01",
    }

    VLAN_CONFIG_BY_PROJECT[int(current_user.project_id)] = new_config

    audit_entry = {
        "id": len(ADMIN_ACTION_LOG) + 1,
        "timestamp": int(time.time()),
        "user_id": current_user.id,
        "user_email": current_user.email,
        "organization_id": current_user.organization_id,
        "project_id": current_user.project_id,
        "action": "vlan_config_update",
        "node_id": None,
        "old_value": old_config,
        "new_value": new_config,
        "reason": payload.reason or "VLAN segmentation updated from StructFi Mobile v3.01.",
    }

    ADMIN_ACTION_LOG.append(audit_entry)

    return {
        "success": True,
        "message": "VLAN segmentation updated successfully.",
        "config": new_config,
        "action": audit_entry,
    }

# -------------------------------------------------------------------
# Mobile Reports Admin
# -------------------------------------------------------------------

REPORT_EXPORTS_BY_PROJECT: Dict[int, List[Dict[str, Any]]] = {}

ALLOWED_REPORT_TYPES = {
    "Executive Summary",
    "Security Report",
    "WiFi Report",
    "VLAN Segmentation Report",
    "Full Network Report",
}

ALLOWED_REPORT_FORMATS = {
    "PDF",
    "CSV",
    "JSON",
}


class ReportExportRequest(BaseModel):
    report_type: str = "Executive Summary"
    report_format: str = "PDF"
    include_actions: bool = True
    include_nodes: bool = True
    reason: Optional[str] = None


def _validate_report_request(payload: ReportExportRequest) -> None:
    if payload.report_type not in ALLOWED_REPORT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported report type.",
        )

    if payload.report_format not in ALLOWED_REPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported report format.",
        )


def _get_project_admin_actions(current_user: AuthenticatedUser) -> List[Dict[str, Any]]:
    return [
        action
        for action in ADMIN_ACTION_LOG
        if int(action.get("project_id", -1)) == int(current_user.project_id)
    ]


@app.get("/mobile/admin/reports/summary")
def mobile_admin_get_reports_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    _require_network_admin(current_user)

    project_actions = _get_project_admin_actions(current_user)
    recent_actions = project_actions[-8:][::-1]

    exports = REPORT_EXPORTS_BY_PROJECT.get(
        int(current_user.project_id),
        [],
    )

    return {
        "success": True,
        "summary": {
            "organization_id": current_user.organization_id,
            "organization_name": current_user.organization_name,
            "project_id": current_user.project_id,
            "project_name": current_user.project_name,
            "available_reports": [
                "Executive Summary",
                "Security Report",
                "WiFi Report",
                "VLAN Segmentation Report",
                "Full Network Report",
            ],
            "available_formats": [
                "PDF",
                "CSV",
                "JSON",
            ],
            "total_admin_actions": len(project_actions),
            "total_exports": len(exports),
            "last_export": exports[-1] if exports else None,
            "recent_actions": recent_actions,
            "version": "v3.01",
            "updated_at": int(time.time()),
        },
    }


@app.post("/mobile/admin/reports/export")
def mobile_admin_export_report(
    payload: ReportExportRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    _require_network_admin(current_user)
    _validate_report_request(payload)

    project_id = int(current_user.project_id)

    if project_id not in REPORT_EXPORTS_BY_PROJECT:
        REPORT_EXPORTS_BY_PROJECT[project_id] = []

    export_entry = {
        "id": len(REPORT_EXPORTS_BY_PROJECT[project_id]) + 1,
        "timestamp": int(time.time()),
        "report_type": payload.report_type,
        "report_format": payload.report_format,
        "include_actions": bool(payload.include_actions),
        "include_nodes": bool(payload.include_nodes),
        "status": "generated",
        "file_name": (
            payload.report_type.lower()
            .replace(" ", "_")
            .replace("/", "_")
            + f"_{int(time.time())}.{payload.report_format.lower()}"
        ),
        "generated_by": current_user.name,
        "generated_by_email": current_user.email,
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization_name,
        "project_id": current_user.project_id,
        "project_name": current_user.project_name,
        "version": "v3.01",
    }

    REPORT_EXPORTS_BY_PROJECT[project_id].append(export_entry)

    audit_entry = {
        "id": len(ADMIN_ACTION_LOG) + 1,
        "timestamp": int(time.time()),
        "user_id": current_user.id,
        "user_email": current_user.email,
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization_name,
        "project_id": current_user.project_id,
        "project_name": current_user.project_name,
        "action": "report_export_request",
        "node_id": None,
        "old_value": None,
        "new_value": export_entry,
        "reason": payload.reason or "Report export requested from StructFi Mobile v3.01.",
    }

    ADMIN_ACTION_LOG.append(audit_entry)

    return {
        "success": True,
        "message": "Report generated successfully.",
        "export": export_entry,
        "action": audit_entry,
    }

# -------------------------------------------------------------------
# Startup
# -------------------------------------------------------------------

@app.on_event("startup")
def reset_runtime_on_startup():
    global simulator

    # Important for Render/mobile demos:
    # Do NOT wipe uploaded CAD / parsed rooms / latest plan on every deploy.
    # Only reset persisted runtime state when this env var is explicitly enabled.
    should_reset_runtime = os.getenv("STRUCTFI_RESET_RUNTIME_ON_STARTUP", "false").lower() in {
        "1",
        "true",
        "yes",
    }

    if should_reset_runtime:
        try:
            runtime_reset_service.reset_all_runtime_state()
        except Exception:
            pass

    simulator = StructiFiSimulator()

    # If a latest CAD plan exists on disk, apply it into memory so mobile endpoints
    # recover after a Render restart without requiring Streamlit to be opened first.
    try:
        _auto_apply_latest_plan_if_state_empty()
    except Exception:
        pass


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
    _auto_apply_latest_plan_if_state_empty()
    return simulator.get_state()


@app.get("/simulation/summary")
def simulation_summary():
    _auto_apply_latest_plan_if_state_empty()
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
    _auto_apply_latest_plan_if_state_empty()
    simulator.step()
    return simulator.get_state()


@app.post("/simulation/run-steps/{steps}")
def simulation_run_steps(steps: int):
    _auto_apply_latest_plan_if_state_empty()
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
    state = _apply_latest_plan_to_simulation_or_raise()
    plan = _unwrap_plan_payload(_get_or_create_latest_plan()) or {}
    return {
        "message": "CAD plan applied to simulation successfully",
        "state": state,
        "plan_summary": plan.get("summary", {}),
        "runtime_nodes_count": len(state.get("node_runtime", []) or []),
        "clients_count": len(state.get("clients", []) or []),
    }


@app.get("/simulation/apply-cad-plan")
def apply_cad_plan_to_simulation_from_browser():
    return apply_cad_plan_to_simulation()


@app.post("/simulation/force-apply-latest-plan")
def force_apply_latest_plan_to_simulation():
    return apply_cad_plan_to_simulation()


@app.get("/simulation/force-apply-latest-plan")
def force_apply_latest_plan_to_simulation_from_browser():
    return apply_cad_plan_to_simulation()


@app.get("/simulation/nodes")
def simulation_nodes():
    _auto_apply_latest_plan_if_state_empty()
    return {"nodes": _state_dict().get("node_runtime", [])}


@app.get("/simulation/clients")
def simulation_clients():
    _auto_apply_latest_plan_if_state_empty()
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



def _build_dashboard_report_state() -> Dict[str, Any]:
    """
    Build one comprehensive snapshot for dashboard-generated reports.

    The report must represent the current simulation experiment: latest CAD,
    extracted rooms, suggested nodes, RF/material assumptions, runtime clients,
    controller decisions, alerts, handover events, telemetry, and images.
    """
    state = _state_dict()
    latest_plan = _unwrap_plan_payload(_get_latest_plan_model_or_dict()) or {}
    latest_building = _latest_building_dict() or {}

    try:
        wall_config = wall_material_manager.current_config()
    except Exception:
        wall_config = {}

    try:
        material_library = wall_material_manager.MATERIAL_LIBRARY
    except Exception:
        material_library = {}

    return {
        "simulation_state": state,
        "latest_plan": latest_plan,
        "latest_building": latest_building,
        "latest_cad": cad_file_manager.get_latest_cad(),
        "wall_material_config": wall_config,
        "material_library": material_library,
        "project_config": _project_config_payload(),
        "images": _current_images(),
        "export_context": {
            "source": "StructFi dashboard",
            "mode": "local_simulation_run",
            "note": "Generated from the current dashboard/backend state for this simulation experiment.",
        },
    }


# -------------------------------------------------------------------
# Export
# -------------------------------------------------------------------

@app.get("/export/excel")
def export_excel():
    try:
        path = reporter.export_excel(_build_dashboard_report_state())
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
        path = reporter.export_pdf(_build_dashboard_report_state())
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
# RF material assumptions
# -------------------------------------------------------------------

@app.get("/rf/material-profiles")
def get_rf_material_profiles():
    return wall_material_manager.profiles_payload()


@app.get("/rf/material-config")
def get_rf_material_config():
    return {
        "config": wall_material_manager.current_config(),
        "profiles": wall_material_manager.SCENARIO_PROFILES,
        "materials": wall_material_manager.MATERIAL_LIBRARY,
    }


@app.post("/rf/material-config")
def set_rf_material_config(request: WallMaterialConfigRequest):
    payload = request.model_dump(exclude_none=True) if hasattr(request, "model_dump") else request.dict(exclude_none=True)
    config = wall_material_manager.save_config(payload)
    apply_result = wall_material_manager.apply_to_latest_building(config)
    return {
        "message": "RF wall/material configuration saved",
        "config": config,
        "apply_result": apply_result,
    }


@app.post("/rf/apply-material-config")
def apply_rf_material_config():
    apply_result = wall_material_manager.apply_to_latest_building()
    return {
        "message": "RF wall/material configuration applied to latest building",
        "apply_result": apply_result,
    }


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

def _mobile_alerts_from_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    security_state = state.get("security_state") or {}
    alerts = security_state.get("alerts", []) or []
    return alerts if isinstance(alerts, list) else []


def _mobile_events_from_state(state: Dict[str, Any], limit: int = 50) -> List[Dict[str, Any]]:
    events = state.get("events", []) or []

    if not isinstance(events, list):
        return []

    safe_limit = max(1, min(int(limit), 200))
    return events[-safe_limit:]


def _mobile_handover_events(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    handovers = []

    for event in _mobile_events_from_state(state, limit=200):
        if not isinstance(event, dict):
            continue

        event_text = json.dumps(event, default=str).lower()
        if "handover" in event_text or "roam" in event_text or "roaming" in event_text:
            handovers.append(event)

    return handovers


def _mobile_qos_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    clients = state.get("clients", []) or []

    if not isinstance(clients, list):
        clients = []

    qos_counts: Dict[str, int] = {}
    packet_loss_warnings = 0
    latency_warnings = 0

    for client in clients:
        if not isinstance(client, dict):
            continue

        qos_state = (
            client.get("qos_state")
            or client.get("qos")
            or client.get("traffic_status")
            or "unknown"
        )
        qos_state = str(qos_state).lower()
        qos_counts[qos_state] = qos_counts.get(qos_state, 0) + 1

        try:
            packet_loss = float(
                client.get(
                    "current_packet_loss_pct",
                    client.get("packet_loss", client.get("packet_loss_percent", 0)),
                )
                or 0
            )
            if packet_loss > 3:
                packet_loss_warnings += 1
        except Exception:
            pass

        try:
            latency_ms = float(client.get("current_latency_ms", client.get("latency_ms", 0)) or 0)
            if latency_ms > 100:
                latency_warnings += 1
        except Exception:
            pass

    return {
        "qos_counts": qos_counts,
        "packet_loss_warnings": packet_loss_warnings,
        "latency_warnings": latency_warnings,
        "clients_evaluated": len(clients),
    }


def _mobile_reports_payload() -> Dict[str, Any]:
    reports_dir = Path("data/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    reports = []

    for path in sorted(reports_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.suffix.lower() not in [".xlsx", ".pdf"]:
            continue

        reports.append({
            "file_name": path.name,
            "file_type": path.suffix.lower().replace(".", ""),
            "size_bytes": path.stat().st_size,
            "modified_timestamp": path.stat().st_mtime,
            "download_url": f"/reports/{path.name}",
        })

    return {
        "reports": reports,
        "count": len(reports),
        "generate": {
            "excel_url": "/export/excel",
            "pdf_url": "/export/pdf",
        },
    }


def _mobile_device_tokens_path() -> Path:
    path = Path("data/runtime/mobile_device_tokens.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _save_mobile_device_token(payload: Dict[str, Any]) -> Dict[str, Any]:
    from datetime import datetime

    path = _mobile_device_tokens_path()
    tokens = _read_json(path, default=[])

    if not isinstance(tokens, list):
        tokens = []

    token_value = payload.get("token")
    tokens = [item for item in tokens if isinstance(item, dict) and item.get("token") != token_value]

    payload["registered_at"] = datetime.utcnow().isoformat() + "Z"
    tokens.append(payload)

    path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")

    return {
        "message": "Mobile device token registered successfully",
        "registered": True,
        "tokens_count": len(tokens),
    }


@app.get("/mobile/bootstrap")
def mobile_bootstrap():
    _auto_apply_latest_plan_if_state_empty()

    state = _state_dict()
    plan = _get_latest_plan_model_or_dict()
    building = _latest_building_dict()
    alerts = _mobile_alerts_from_state(state)
    planned_nodes = _extract_plan_nodes(plan)

    return {
        "project": _project_config_payload(),
        "building_available": building is not None,
        "plan_available": plan is not None,
        "simulation_active": bool(state.get("node_runtime")),
        "state_summary": {
            "simulation_source": state.get("simulation_source", "unknown"),
            "step": state.get("step", 0),
            "rooms": len((building or {}).get("rooms", []) or []) if isinstance(building, dict) else 0,
            "planned_nodes": len(planned_nodes),
            "runtime_nodes": len(state.get("node_runtime", []) or []),
            "clients": len(state.get("clients", []) or []) if state.get("node_runtime") else 0,
            "alerts": len(alerts) if state.get("node_runtime") else 0,
            "ai_status": ((state.get("ai_output") or {}).get("health_summary") or {}).get("status", "unknown"),
        },
        "images": _current_images(),
        "network": {
            "vlans": getattr(settings, "VLAN_PROFILES", []),
            "ssids": getattr(settings, "SSID_PROFILES", []),
            "radius": getattr(settings, "RADIUS_PROFILE", {}),
        },
    }


@app.get("/mobile/dashboard")
def mobile_dashboard():
    _auto_apply_latest_plan_if_state_empty()

    state = _state_dict()
    plan = _get_latest_plan_model_or_dict()
    building = _latest_building_dict()
    alerts = _mobile_alerts_from_state(state)

    rooms = (building or {}).get("rooms", []) if isinstance(building, dict) else []
    planned_nodes = _extract_plan_nodes(plan)
    runtime_nodes = state.get("node_runtime", []) or []
    clients = state.get("clients", []) or []
    simulation_active = bool(runtime_nodes)

    return {
        "summary": {
            "rooms": len(rooms),
            "planned_nodes": len(planned_nodes),
            "runtime_nodes": len(runtime_nodes),
            "nodes": len(runtime_nodes) if simulation_active else len(planned_nodes),
            "clients": len(clients) if simulation_active else 0,
            "alerts": len(alerts) if simulation_active else 0,
            "simulation_step": state.get("step", 0),
            "simulation_source": state.get("simulation_source", "unknown"),
            "simulation_active": simulation_active,
            "placement_score": ((plan or {}).get("summary") or {}).get("placement_score") if isinstance(plan, dict) else None,
            "ai_status": ((state.get("ai_output") or {}).get("health_summary") or {}).get("status", "unknown"),
        },
        "state": state,
        "images": _current_images(),
        "ai": state.get("ai_output", {}),
        "alerts": alerts if simulation_active else [],
        "latest_alerts": alerts[-5:] if simulation_active else [],
        "latest_events": _mobile_events_from_state(state, limit=5) if simulation_active else [],
        "router": router_status(),
    }


@app.get("/mobile/simulation")
def mobile_simulation():
    _auto_apply_latest_plan_if_state_empty()

    state = _state_dict()
    runtime_nodes = state.get("node_runtime", []) or []
    clients = state.get("clients", []) or []
    simulation_active = bool(runtime_nodes)

    return {
        "active": simulation_active,
        "step": state.get("step", 0),
        "simulation_source": state.get("simulation_source", "unknown"),
        "runtime_nodes": runtime_nodes,
        "clients": clients if simulation_active else [],
        "clients_count": len(clients) if simulation_active else 0,
        "events": _mobile_events_from_state(state, limit=50) if simulation_active else [],
        "handover_events": _mobile_handover_events(state) if simulation_active else [],
        "qos": _mobile_qos_payload(state) if simulation_active else {
            "qos_counts": {},
            "packet_loss_warnings": 0,
            "latency_warnings": 0,
            "clients_evaluated": 0,
        },
        "controller_state": state.get("controller_state", {}) if simulation_active else {},
        "telemetry_history": (state.get("telemetry_history", []) or [])[-50:] if simulation_active else [],
    }


@app.get("/mobile/images")
def mobile_images():
    return {"images": _current_images()}


@app.get("/mobile/nodes")
def mobile_nodes():
    _auto_apply_latest_plan_if_state_empty()

    state = _state_dict()
    plan = _get_latest_plan_model_or_dict()
    runtime_nodes = state.get("node_runtime", []) or []
    planned_nodes = _extract_plan_nodes(plan)

    if runtime_nodes:
        return {
            "mode": "runtime",
            "nodes": runtime_nodes,
            "count": len(runtime_nodes),
            "simulation_active": True,
        }

    return {
        "mode": "planned",
        "nodes": planned_nodes,
        "count": len(planned_nodes),
        "simulation_active": False,
    }


@app.get("/mobile/clients")
def mobile_clients():
    return simulation_clients()


@app.get("/mobile/alerts")
def mobile_alerts():
    _auto_apply_latest_plan_if_state_empty()

    state = _state_dict()
    alerts = _mobile_alerts_from_state(state)
    simulation_active = bool(state.get("node_runtime"))

    return {
        "alerts": alerts if simulation_active else [],
        "count": len(alerts) if simulation_active else 0,
        "simulation_active": simulation_active,
    }


@app.get("/mobile/reports")
def mobile_reports():
    return _mobile_reports_payload()


@app.post("/mobile/device-token")
def mobile_device_token(payload: MobileDeviceTokenRequest):
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()

    if not data.get("token"):
        raise HTTPException(status_code=400, detail="Device token is required")

    return _save_mobile_device_token(data)



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
