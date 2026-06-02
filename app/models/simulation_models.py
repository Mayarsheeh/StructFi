from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field

from app.models.building_models import BuildingModel
from app.models.planning_models import NodePlanModel, PlanningSummaryModel
from app.models.telemetry_models import NodeRuntimeModel, TelemetryHistoryPoint
from app.models.security_models import SecurityStateModel


class ClientMovementPoint(BaseModel):
    x: float
    y: float


class ClientModel(BaseModel):
    id: int
    name: str
    role: Literal["management", "staff", "guest"]

    # Sprint 6 client and traffic profile fields.
    # role remains the security/segmentation role, while client_type and
    # traffic_profile describe the realistic user/device behavior.
    client_type: Literal[
        "admin",
        "staff",
        "guest",
        "call_center_agent",
        "meeting_user",
        "iot_sensor",
        "maintenance",
    ] = "staff"
    traffic_profile: Literal[
        "network_admin",
        "web_cloud",
        "guest_browsing",
        "voip",
        "video_call",
        "iot_telemetry",
        "maintenance_tools",
    ] = "web_cloud"
    vlan_id: int = 20
    ssid: str = "StructFi-Staff"
    qos_priority: Literal["low", "normal", "high", "critical"] = "normal"
    required_bandwidth_mbps: float = 5.0
    max_latency_ms: float = 150.0
    packet_loss_tolerance_pct: float = 5.0
    mobility_pattern: Literal["stationary", "slow_walk", "walk", "roaming", "iot_static"] = "walk"
    handover_threshold_dbm: float = -67.0
    sticky_client: bool = False
    qos_state: Literal["not_evaluated", "ok", "warning", "violated"] = "not_evaluated"

    x: float
    y: float
    floor: str = "unknown"
    room_id: Optional[int] = None
    room_name: Optional[str] = None

    speed: float = 0.0
    allowed_zones: List[str] = Field(default_factory=list)

    path: List[ClientMovementPoint] = Field(default_factory=list)
    path_index: int = 0

    connected_node: Optional[int] = None
    current_rssi: Optional[float] = None
    current_snr: Optional[float] = None
    current_throughput_mbps: float = 0.0
    current_packet_loss_pct: float = 0.0
    current_retry_rate_pct: float = 0.0
    current_latency_ms: float = 0.0
    roaming_count: int = 0
    handover_latency_ms: float = 0.0
    last_handover_status: Literal["none", "fast", "slow", "failed"] = "none"
    packets_sent: int = 0
    packets_received: int = 0


class ControllerDecisionModel(BaseModel):
    id: int
    node_id: Optional[int] = None
    action: Literal[
        "change_channel",
        "change_tx_power",
        "mark_degraded",
        "mark_down",
        "raise_alert",
        "rebalance_load",
        "none",
    ] = "none"
    value: str = ""
    reason: str = ""
    severity: Literal["info", "warning", "critical"] = "info"


class SimulationEventModel(BaseModel):
    type: Literal[
        "handover",
        "disconnect",
        "node_status_change",
        "policy_violation",
        "channel_change",
        "tx_power_change",
        "anomaly_detected",
        "cad_plan_applied",
        "client_update",
        "ids_alert",
        "info",
    ]
    message: str
    client_id: Optional[int] = None
    node_id: Optional[int] = None
    severity: Literal["info", "warning", "critical"] = "info"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AIHealthSummaryModel(BaseModel):
    status: Literal["stable", "warning", "critical"] = "stable"
    anomaly_score: float = 0.0
    critical_alerts: int = 0
    warning_alerts: int = 0
    high_load_nodes: int = 0
    down_nodes: int = 0
    degraded_nodes: int = 0
    weak_signal_clients: int = 0
    high_retry_nodes: int = 0
    packet_loss_nodes: int = 0
    avg_network_quality_score: float = 100.0


class AIRecommendationModel(BaseModel):
    type: Literal[
        "channel_change",
        "tx_power_adjustment",
        "node_reposition",
        "add_node",
        "security_action",
        "controller_action",
        "observation",
    ] = "observation"
    message: str
    node_id: Optional[int] = None
    room_id: Optional[int] = None
    confidence: float = 0.0
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    expected_impact: str = ""


class AIOutputModel(BaseModel):
    health_summary: AIHealthSummaryModel = Field(default_factory=AIHealthSummaryModel)
    recommendations: List[AIRecommendationModel] = Field(default_factory=list)
    model_name: str = "StructFi Rule-Based AI Engine"
    generated_at: str = ""


class ControllerStateModel(BaseModel):
    unified_ssid_enabled: bool = True
    roaming_80211r_enabled: bool = True
    managed_nodes_count: int = 0
    node_config_sync_ok: bool = True
    centralized_router_online: bool = True
    controller_ip: str = "192.168.10.1"
    decisions: List[ControllerDecisionModel] = Field(default_factory=list)


class SimulationStateModel(BaseModel):
    step: int = 0
    timestamp: str = ""

    simulation_source: Literal["json_default", "cad_plan", "manual", "unknown"] = "unknown"
    is_live: bool = False

    building: Optional[BuildingModel] = None
    node_plan: List[NodePlanModel] = Field(default_factory=list)
    node_runtime: List[NodeRuntimeModel] = Field(default_factory=list)
    planning_summary: PlanningSummaryModel = Field(default_factory=PlanningSummaryModel)

    clients: List[ClientModel] = Field(default_factory=list)
    controller_state: ControllerStateModel = Field(default_factory=ControllerStateModel)
    security_state: SecurityStateModel = Field(default_factory=SecurityStateModel)
    ai_output: AIOutputModel = Field(default_factory=AIOutputModel)

    events: List[SimulationEventModel] = Field(default_factory=list)
    telemetry_history: List[TelemetryHistoryPoint] = Field(default_factory=list)
    mobile_summary: Dict[str, Any] = Field(default_factory=dict)
