from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


HealthState = Literal["online", "offline", "degraded", "unknown"]


class RadioTelemetryModel(BaseModel):
    rssi_avg: float = 0.0
    snr_avg: float = 0.0
    current_channel: int = 1
    tx_power_dbm: int = 18
    retry_rate_pct: float = 0.0
    packet_loss_pct: float = 0.0
    throughput_mbps: float = 0.0
    latency_ms: float = 0.0
    channel_utilization_pct: float = 0.0
    noise_floor_dbm: float = -92.0
    cochannel_interference_score: float = 0.0


class EnvironmentTelemetryModel(BaseModel):
    temperature_c: float = 0.0
    humidity_pct: float = 0.0
    room_pressure_score: float = 0.0
    occupancy_estimate: int = 0
    enclosure_heat_risk: str = "normal"


class ClientSessionTelemetryModel(BaseModel):
    client_id: int
    client_name: str
    role: Literal["management", "staff", "guest"]
    connected_node_id: Optional[int] = None
    current_rssi: Optional[float] = None
    current_snr: Optional[float] = None
    current_throughput_mbps: float = 0.0
    current_packet_loss_pct: float = 0.0
    current_retry_rate_pct: float = 0.0
    current_latency_ms: float = 0.0
    roaming_events: int = 0
    packets_sent: int = 0
    packets_received: int = 0


class NodeRuntimeModel(BaseModel):
    id: int
    name: str
    node_id: Optional[str] = None
    room_id: Optional[int] = None
    room_name: Optional[str] = None
    room_type: str = "unknown"
    floor: str = "unknown"

    x: float = 0.0
    y: float = 0.0
    node_role: str = "room_node"
    placement_type: str = "corner"

    status: HealthState = "unknown"
    uptime_seconds: int = 0
    software_version: str = "unknown"
    firmware_version: str = "node-fw-1.0"
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    last_seen: Optional[str] = None

    connected_clients: int = 0
    current_load: int = 0
    max_clients: int = 18

    radio: RadioTelemetryModel = Field(default_factory=RadioTelemetryModel)
    environment: EnvironmentTelemetryModel = Field(default_factory=EnvironmentTelemetryModel)
    client_sessions: List[ClientSessionTelemetryModel] = Field(default_factory=list)

    ai_health_state: str = "normal"
    ai_notes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TelemetryHistoryPoint(BaseModel):
    step: int
    timestamp: str
    node_id: int
    rssi_avg: float = 0.0
    snr_avg: float = 0.0
    retry_rate_pct: float = 0.0
    throughput_mbps: float = 0.0
    packet_loss_pct: float = 0.0
    latency_ms: float = 0.0
    connected_clients: int = 0
    channel_utilization_pct: float = 0.0
    temperature_c: float = 0.0
    humidity_pct: float = 0.0
    ai_health_state: str = "normal"
