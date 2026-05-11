from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal, Tuple
from pydantic import BaseModel, Field


NodeStatus = Literal["planned", "active", "online", "degraded", "down", "offline", "unknown"]
PlacementType = Literal["corner", "wall_mid", "ceiling_like", "hallway_edge", "corridor_backbone", "fallback"]
AntennaDirection = Literal["omni_balanced", "horizontal_bias", "vertical_bias", "sectorized"]
CablePathType = Literal["direct", "corridor_route", "cabinet_route", "unknown"]


class CableRouteModel(BaseModel):
    path_type: CablePathType = "unknown"
    length_m: float = 0.0
    estimated_cost: float = 0.0
    path_points: List[Tuple[float, float]] = Field(default_factory=list)


class CoverageMetrics(BaseModel):
    room_coverage_score: float = 0.0
    nearby_overlap_score: float = 0.0
    estimated_rssi_center: float = 0.0
    estimated_snr_center: float = 0.0

    sample_points: int = 0
    coverage_ratio: float = 0.0
    coverage_percent: float = 0.0
    avg_rssi_dbm: float = 0.0
    worst_rssi_dbm: float = 0.0
    avg_snr_db: float = 0.0
    target_rssi_dbm: float = -62.0
    minimum_acceptable_rssi_dbm: float = -72.0


class CapacityMetrics(BaseModel):
    projected_clients: int = 0
    projected_capacity_mbps: float = 0.0
    projected_utilization_pct: float = 0.0
    retry_risk_score: float = 0.0

    base_capacity_mbps: float = 0.0
    effective_capacity_mbps: float = 0.0
    max_clients: int = 0
    expected_clients: int = 0
    utilization_percent: float = 0.0
    capacity_state: str = "unknown"


class InterferenceMetrics(BaseModel):
    channel_cost: float = 0.0
    interference_score: float = 0.0
    cochannel_risk: float = 0.0
    adjacent_channel_risk: float = 0.0


class NodePlanModel(BaseModel):
    id: int
    name: str
    node_id: Optional[str] = None

    room_id: Optional[int] = None
    room_name: Optional[str] = None
    room_type: str = "unknown"
    floor: str = "unknown"

    x: float
    y: float

    placement_type: PlacementType = "corner"
    node_role: str = "room_node"
    placement_reason: str = ""

    antenna_direction: AntennaDirection = "omni_balanced"
    antenna_beamwidth: int = 360
    beam_direction_deg: float = 0.0
    beamwidth_deg: float = 360.0

    tx_power: int = 18
    tx_power_dbm: float = 18.0
    channel: int = 1
    band: str = "5GHz"
    wifi_standard: str = "IEEE 802.11ax/ac"
    status: NodeStatus = "planned"

    coverage: CoverageMetrics = Field(default_factory=CoverageMetrics)
    capacity: CapacityMetrics = Field(default_factory=CapacityMetrics)
    interference: InterferenceMetrics = Field(default_factory=InterferenceMetrics)
    cable_route: CableRouteModel = Field(default_factory=CableRouteModel)

    coverage_metrics: Dict[str, Any] = Field(default_factory=dict)
    capacity_metrics: Dict[str, Any] = Field(default_factory=dict)
    telemetry: Dict[str, Any] = Field(default_factory=dict)
    ai_decision: Dict[str, Any] = Field(default_factory=dict)
    secondary_coverage_rooms: List[Dict[str, Any]] = Field(default_factory=list)
    roaming: Dict[str, Any] = Field(default_factory=dict)

    placement_score: float = 0.0
    notes: List[str] = Field(default_factory=list)


class VLANPlanModel(BaseModel):
    vlan_id: int
    name: str
    zone: Literal["management", "staff", "guest", "service", "iot"] = "staff"
    zone_role: Optional[str] = None
    subnet: str = ""
    gateway: str = ""
    dhcp_enabled: bool = True
    access_level: str = ""
    description: str = ""
    allowed_zones: List[str] = Field(default_factory=list)
    security: str = ""


class SSIDProfileModel(BaseModel):
    ssid_name: str = ""
    ssid: Optional[str] = None
    security_mode: Literal["WPA3-Enterprise", "WPA2-Enterprise", "WPA2-PSK", "WPA2/WPA3 Enterprise", "Captive Portal", "Open"] = "WPA3-Enterprise"
    security: Optional[str] = None
    vlan_id: int = 20
    fast_roaming_enabled: bool = True
    roaming_80211r: bool = True
    radius_enabled: bool = True
    client_isolation: bool = False
    hidden: bool = False


class PlanningSummaryModel(BaseModel):
    node_count: int = 0
    nodes_planned: int = 0
    rooms_count: int = 0
    corridor_nodes: int = 0

    coverage_score: float = 0.0
    speed_score: float = 0.0
    placement_score: float = 0.0
    wall_penalty_score: float = 0.0
    channel_reuse_score: float = 0.0
    capacity_score: float = 0.0
    estimated_dead_zones: int = 0

    avg_coverage_percent: float = 0.0
    avg_rssi_dbm: float = 0.0
    avg_snr_db: float = 0.0
    estimated_total_capacity_mbps: float = 0.0
    estimated_clients_supported: int = 0


class PlanningResultModel(BaseModel):
    file_name: str = "unknown"
    source_file: str = "unknown"
    source_format: str = "UNKNOWN"
    project: str = "StructFi"
    planner_version: str = "unknown"
    status: str = "ok"

    bounds: Dict[str, Any] = Field(default_factory=dict)
    building: Optional[Dict[str, Any]] = None
    rooms: List[Dict[str, Any]] = Field(default_factory=list)
    walls: List[Dict[str, Any]] = Field(default_factory=list)
    labels: List[Dict[str, Any]] = Field(default_factory=list)

    node_plan: List[NodePlanModel] = Field(default_factory=list)
    nodes: List[NodePlanModel] = Field(default_factory=list)
    nodes_count: int = 0
    rooms_count: int = 0

    vlan_plan: List[VLANPlanModel] = Field(default_factory=list)
    vlan_profiles: List[VLANPlanModel] = Field(default_factory=list)
    ssid_profiles: List[SSIDProfileModel] = Field(default_factory=list)
    cable_routes: List[Dict[str, Any]] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)

    summary: PlanningSummaryModel = Field(default_factory=PlanningSummaryModel)
