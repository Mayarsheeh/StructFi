from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class Room(BaseModel):
    id: int
    name: str
    x: float
    y: float
    width: float
    height: float


class Node(BaseModel):
    id: int
    name: str
    x: float
    y: float
    room_id: int
    channel: int
    tx_power: float
    load: int = 0
    status: Literal["active", "down", "degraded"] = "active"
    vlan_zone: Literal["guest", "staff", "management"] = "staff"


class Client(BaseModel):
    id: int
    name: str
    x: float
    y: float
    speed: float
    role: Literal["guest", "staff", "management"] = "staff"
    path: List[List[float]] = Field(default_factory=list)
    path_index: int = 0
    connected_node: Optional[int] = None
    current_rssi: Optional[float] = None
    current_snr: Optional[float] = None


class AccessPolicy(BaseModel):
    source_zone: Literal["guest", "staff", "management"]
    target_zone: Literal["guest", "staff", "management", "internet", "controller"]
    action: Literal["allow", "deny"]


class SecurityAlert(BaseModel):
    id: int
    severity: Literal["info", "warning", "critical"]
    title: str
    description: str
    node_id: Optional[int] = None
    client_id: Optional[int] = None


class SimulationEvent(BaseModel):
    type: str
    message: str
    client_id: Optional[int] = None
    node_id: Optional[int] = None


class NetworkPolicy(BaseModel):
    source_role: Literal["guest", "staff", "management"]
    target_zone: Literal["guest", "staff", "management", "internet", "controller"]
    action: Literal["allow", "deny"]


class ControllerDecision(BaseModel):
    node_id: int
    action: str
    value: str
    reason: str