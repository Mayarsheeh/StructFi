from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


ZoneRole = Literal["management", "staff", "guest", "service", "iot"]
PolicyAction = Literal["allow", "deny", "monitor"]
SeverityLevel = Literal["info", "warning", "critical"]


class VLANProfileModel(BaseModel):
    vlan_id: int
    name: str
    zone_role: ZoneRole = "staff"
    zone: Optional[str] = None
    subnet: str = ""
    gateway: str = ""
    dhcp_enabled: bool = True
    description: str = ""
    allowed_zones: List[str] = Field(default_factory=list)
    security: str = ""


class SSIDSecurityProfileModel(BaseModel):
    ssid: str
    vlan_id: int
    security: str = "WPA3-Enterprise"
    radius_enabled: bool = True
    roaming_80211r: bool = True
    client_isolation: bool = False
    hidden: bool = False


class AccessPolicyModel(BaseModel):
    id: int
    source_role: ZoneRole
    target_zone: str
    action: PolicyAction
    description: str = ""


class AccessDecisionModel(BaseModel):
    client_id: int
    client_name: str
    role: ZoneRole
    target_zone: str
    allowed: bool
    reason: str = ""
    policy_id: Optional[int] = None


class SecurityAlertModel(BaseModel):
    id: int
    severity: SeverityLevel
    title: str
    description: str
    node_id: Optional[int] = None
    client_id: Optional[int] = None
    policy_id: Optional[int] = None
    category: Literal[
        "segmentation_violation",
        "weak_signal",
        "low_snr",
        "high_retries",
        "packet_loss",
        "latency",
        "node_failure",
        "node_degraded",
        "temperature",
        "anomaly",
        "interference",
        "roaming",
        "unknown",
    ] = "unknown"
    evidence: Dict[str, Any] = Field(default_factory=dict)
    recommendation: str = ""


class RADIUSProfileModel(BaseModel):
    enabled: bool = True
    auth_mode: Literal["WPA3-Enterprise", "WPA2-Enterprise"] = "WPA3-Enterprise"
    server_ip: str = "192.168.100.10"
    port: int = 1812
    accounting_enabled: bool = True
    shared_secret_hint: str = "configured-on-router"


class CentralizedRouterModel(BaseModel):
    enabled: bool = True
    hostname: str = "structfi-controller"
    management_ip: str = "192.168.10.1"
    controller_api_url: str = "http://127.0.0.1:8000"
    dhcp_enabled: bool = True
    nat_enabled: bool = True
    firewall_enabled: bool = True
    vlan_routing_enabled: bool = True
    monitoring_enabled: bool = True
    notes: List[str] = Field(default_factory=list)


class IDSRuleModel(BaseModel):
    id: str
    name: str
    severity: SeverityLevel = "warning"
    category: str = "unknown"
    enabled: bool = True
    description: str = ""
    threshold: Optional[float] = None
    recommendation: str = ""


class SecurityStateModel(BaseModel):
    vlan_profiles: List[VLANProfileModel] = Field(default_factory=list)
    ssid_profiles: List[SSIDSecurityProfileModel] = Field(default_factory=list)
    access_policies: List[AccessPolicyModel] = Field(default_factory=list)
    access_matrix: List[AccessDecisionModel] = Field(default_factory=list)
    alerts: List[SecurityAlertModel] = Field(default_factory=list)
    radius_profile: RADIUSProfileModel = Field(default_factory=RADIUSProfileModel)
    centralized_router: CentralizedRouterModel = Field(default_factory=CentralizedRouterModel)
    ids_rules: List[IDSRuleModel] = Field(default_factory=list)
