from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.security_models import (
    AccessDecisionModel,
    AccessPolicyModel,
    SecurityAlertModel,
    SecurityStateModel,
    VLANProfileModel,
    RADIUSProfileModel,
)


class SecurityEngine:
    """
    StructFi security and IDS engine.

    Demo goals:
    - Centralized router/controller policy enforcement.
    - VLAN segmentation for management, staff, and guest zones.
    - IDS-style monitoring from live simulation telemetry.
    - Clear alerts for the dashboard, report, and future mobile app.

    This is intentionally rule-based for graduation demo stability.
    """

    def __init__(self) -> None:
        self.alert_counter = 1

    # ------------------------------------------------------------------
    # Public API used by older files
    # ------------------------------------------------------------------

    def build_alert(
        self,
        severity: str,
        title: str,
        description: str,
        node_id: Optional[int] = None,
        client_id: Optional[int] = None,
        policy_id: Optional[int] = None,
        category: str = "unknown",
    ) -> Dict[str, Any]:
        alert = SecurityAlertModel(
            id=self.alert_counter,
            severity=self._safe_severity(severity),
            title=title,
            description=description,
            node_id=node_id,
            client_id=client_id,
            policy_id=policy_id,
            category=self._safe_category(category),
        )
        self.alert_counter += 1
        return alert.model_dump()

    def analyze_access_matrix(self, access_matrix: List[Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []

        for item in access_matrix or []:
            data = self._to_dict(item)
            role = data.get("role", "unknown")
            target = data.get("target_zone", "unknown")
            allowed = bool(data.get("allowed", False))
            client_id = data.get("client_id")
            client_name = data.get("client_name", f"Client-{client_id}")

            if role == "guest" and target in ["management", "controller"] and not allowed:
                alerts.append(
                    self.build_alert(
                        severity="critical",
                        title="Guest Isolation Enforcement",
                        description=f"{client_name} was blocked from accessing {target}. Guest VLAN isolation is active.",
                        client_id=client_id,
                        category="segmentation_violation",
                    )
                )

            elif role == "staff" and target in ["management", "controller"] and not allowed:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Restricted Staff Access",
                        description=f"{client_name} attempted to access {target}, but policy blocks this path.",
                        client_id=client_id,
                        category="segmentation_violation",
                    )
                )

        return alerts

    def analyze_node_health(self, nodes: List[Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []

        for node_obj in nodes or []:
            node = self._to_dict(node_obj)
            node_id = node.get("id")
            name = node.get("name", f"Node-{node_id}")
            status = str(node.get("status", "unknown")).lower()

            radio = node.get("radio", {}) or {}
            environment = node.get("environment", {}) or {}

            current_load = int(node.get("current_load", node.get("connected_clients", 0)) or 0)
            rssi = float(radio.get("rssi_avg", radio.get("rssi", -45.0)) or -45.0)
            snr = float(radio.get("snr_avg", radio.get("snr", 35.0)) or 35.0)
            retries = float(radio.get("retry_rate_pct", 0.0) or 0.0)
            loss = float(radio.get("packet_loss_pct", 0.0) or 0.0)
            throughput = float(radio.get("throughput_mbps", 0.0) or 0.0)
            latency = float(radio.get("latency_ms", 0.0) or 0.0)
            temp = float(environment.get("temperature_c", 0.0) or 0.0)

            if status in ["offline", "down"]:
                alerts.append(
                    self.build_alert(
                        severity="critical",
                        title="Node Offline",
                        description=f"{name} is offline. Check power, uplink, and controller connectivity.",
                        node_id=node_id,
                        category="node_failure",
                    )
                )
                continue

            if status == "degraded":
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Node Degraded",
                        description=f"{name} is degraded. Inspect RF interference and load conditions.",
                        node_id=node_id,
                        category="node_failure",
                    )
                )

            if current_load >= 9:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="High Node Load",
                        description=f"{name} is serving {current_load} clients. Consider load balancing or adding a nearby node.",
                        node_id=node_id,
                        category="anomaly",
                    )
                )

            if rssi < -74.0:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Weak Signal Average",
                        description=f"{name} average RSSI is {rssi:.1f} dBm. Coverage may be weak in this zone.",
                        node_id=node_id,
                        category="weak_signal",
                    )
                )

            if snr < 18.0:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Low SNR",
                        description=f"{name} SNR is {snr:.1f} dB. Noise or interference may affect users.",
                        node_id=node_id,
                        category="interference",
                    )
                )

            if retries > 18.0:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="High Retry Rate",
                        description=f"{name} retry rate is {retries:.1f}%. Channel interference or weak coverage is likely.",
                        node_id=node_id,
                        category="high_retries",
                    )
                )

            if loss > 10.0:
                alerts.append(
                    self.build_alert(
                        severity="critical" if loss > 18.0 else "warning",
                        title="Packet Loss Detected",
                        description=f"{name} packet loss is {loss:.1f}%. User experience may be affected.",
                        node_id=node_id,
                        category="packet_loss",
                    )
                )

            if latency > 95.0:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="High Latency",
                        description=f"{name} average latency is {latency:.1f} ms. Roaming or congestion should be inspected.",
                        node_id=node_id,
                        category="anomaly",
                    )
                )

            if throughput < 12.0 and current_load > 0:
                alerts.append(
                    self.build_alert(
                        severity="info",
                        title="Low Throughput",
                        description=f"{name} throughput is {throughput:.1f} Mbps while serving clients.",
                        node_id=node_id,
                        category="anomaly",
                    )
                )

            if temp >= 55.0:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Node Temperature Warning",
                        description=f"{name} temperature is {temp:.1f} C. Check enclosure ventilation.",
                        node_id=node_id,
                        category="anomaly",
                    )
                )

        return alerts

    def inspect(self, nodes: List[Any], access_matrix: List[Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        alerts.extend(self.analyze_access_matrix(access_matrix))
        alerts.extend(self.analyze_node_health(nodes))
        return alerts

    # ------------------------------------------------------------------
    # Full security state builder for new backend flow
    # ------------------------------------------------------------------

    def build_security_state(
        self,
        clients: List[Any],
        nodes: List[Any],
        access_matrix: Optional[List[Any]] = None,
    ) -> SecurityStateModel:
        matrix = access_matrix or self.build_access_matrix(clients)
        alerts = []
        alerts.extend(self.analyze_access_matrix(matrix))
        alerts.extend(self.analyze_node_health(nodes))
        alerts.extend(self.analyze_client_sessions(clients))

        return SecurityStateModel(
            vlan_profiles=self.default_vlan_profiles(),
            access_policies=self.default_access_policies(),
            access_matrix=[AccessDecisionModel(**self._to_dict(item)) for item in matrix],
            alerts=[SecurityAlertModel(**self._to_dict(alert)) for alert in alerts],
            radius_profile=RADIUSProfileModel(
                enabled=True,
                auth_mode="WPA3-Enterprise",
                server_ip="192.168.100.10",
                port=1812,
                accounting_enabled=True,
            ),
        )

    def build_access_matrix(self, clients: List[Any]) -> List[Dict[str, Any]]:
        matrix: List[Dict[str, Any]] = []
        targets = ["internet", "staff", "management", "controller"]

        for client_obj in clients or []:
            client = self._to_dict(client_obj)
            client_id = client.get("id")
            client_name = client.get("name", f"Client-{client_id}")
            role = str(client.get("role", "guest"))

            for target in targets:
                allowed = self.is_allowed(role, target)
                reason = self._access_reason(role, target, allowed)
                matrix.append(
                    {
                        "client_id": client_id,
                        "client_name": client_name,
                        "role": self._safe_role(role),
                        "target_zone": target,
                        "allowed": allowed,
                        "reason": reason,
                    }
                )

        return matrix

    def analyze_client_sessions(self, clients: List[Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []

        for client_obj in clients or []:
            client = self._to_dict(client_obj)
            client_id = client.get("id")
            name = client.get("name", f"Client-{client_id}")
            role = str(client.get("role", "unknown"))
            rssi = client.get("current_rssi")
            snr = client.get("current_snr")
            roaming = int(client.get("roaming_count", 0) or 0)
            packet_loss = float(client.get("current_packet_loss_pct", 0.0) or 0.0)
            retry = float(client.get("current_retry_rate_pct", 0.0) or 0.0)
            latency = float(client.get("current_latency_ms", 0.0) or 0.0)

            if rssi is not None and float(rssi) < -78.0:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Client Weak Signal",
                        description=f"{name} has weak RSSI ({float(rssi):.1f} dBm).",
                        client_id=client_id,
                        category="weak_signal",
                    )
                )

            if snr is not None and float(snr) < 15.0:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Client Low SNR",
                        description=f"{name} has low SNR ({float(snr):.1f} dB).",
                        client_id=client_id,
                        category="interference",
                    )
                )

            if packet_loss > 12.0:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Client Packet Loss",
                        description=f"{name} packet loss is {packet_loss:.1f}%.",
                        client_id=client_id,
                        category="packet_loss",
                    )
                )

            if retry > 20.0:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Client High Retries",
                        description=f"{name} retry rate is {retry:.1f}%.",
                        client_id=client_id,
                        category="high_retries",
                    )
                )

            if latency > 120.0:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Client High Latency",
                        description=f"{name} latency is {latency:.1f} ms.",
                        client_id=client_id,
                        category="anomaly",
                    )
                )

            if roaming >= 4:
                alerts.append(
                    self.build_alert(
                        severity="info",
                        title="Frequent Roaming",
                        description=f"{name} roamed {roaming} times. Validate roaming thresholds and node overlap.",
                        client_id=client_id,
                        category="anomaly",
                    )
                )

            if role == "guest" and client.get("connected_node") is None:
                alerts.append(
                    self.build_alert(
                        severity="info",
                        title="Guest Client Not Associated",
                        description=f"{name} is not currently associated with any node.",
                        client_id=client_id,
                        category="unknown",
                    )
                )

        return alerts

    # ------------------------------------------------------------------
    # Centralized router/controller security config
    # ------------------------------------------------------------------

    def centralized_router_config(self) -> Dict[str, Any]:
        return {
            "controller_name": "StructFi-Central-Controller",
            "management_ip": "192.168.100.1",
            "uplink_mode": "single_wan_demo",
            "dhcp_server": True,
            "dns_forwarding": True,
            "nat_enabled": True,
            "firewall_enabled": True,
            "radius_server_ip": "192.168.100.10",
            "radius_ports": {"auth": 1812, "accounting": 1813},
            "vlans": [v.model_dump() for v in self.default_vlan_profiles()],
            "ssid_to_vlan_map": [
                {"ssid": "StructFi-Management", "vlan_id": 10, "security": "WPA3-Enterprise", "hidden": True},
                {"ssid": "StructFi-Enterprise", "vlan_id": 20, "security": "WPA3-Enterprise", "hidden": False},
                {"ssid": "StructFi-Guest", "vlan_id": 30, "security": "Captive Portal / isolated", "hidden": False},
            ],
            "firewall_rules": [p.model_dump() for p in self.default_access_policies()],
            "ids_rules": self.ids_rule_catalog(),
            "notes": [
                "This configuration is demo-oriented and suitable for a low-cost graduation prototype.",
                "ESP32-S3 nodes are treated as monitored distributed nodes, not full enterprise AP replacements.",
                "The centralized controller simulates enterprise-like VLAN, policy, and IDS behavior.",
            ],
        }

    def ids_rule_catalog(self) -> List[Dict[str, Any]]:
        return [
            {"id": "IDS-001", "name": "Node Offline", "severity": "critical", "condition": "node.status in offline/down"},
            {"id": "IDS-002", "name": "High Retry Rate", "severity": "warning", "condition": "retry_rate_pct > 18"},
            {"id": "IDS-003", "name": "Packet Loss", "severity": "warning/critical", "condition": "packet_loss_pct > 10"},
            {"id": "IDS-004", "name": "Weak Signal", "severity": "warning", "condition": "rssi_avg < -74"},
            {"id": "IDS-005", "name": "Low SNR", "severity": "warning", "condition": "snr_avg < 18"},
            {"id": "IDS-006", "name": "Guest Isolation", "severity": "critical", "condition": "guest access to management/controller blocked"},
            {"id": "IDS-007", "name": "High Latency", "severity": "warning", "condition": "latency_ms > 95"},
            {"id": "IDS-008", "name": "Thermal Warning", "severity": "warning", "condition": "temperature_c >= 55"},
        ]

    # ------------------------------------------------------------------
    # Default policies
    # ------------------------------------------------------------------

    def default_vlan_profiles(self) -> List[VLANProfileModel]:
        return [
            VLANProfileModel(
                vlan_id=10,
                name="Management",
                zone_role="management",
                subnet="192.168.10.0/24",
                gateway="192.168.10.1",
                dhcp_enabled=True,
            ),
            VLANProfileModel(
                vlan_id=20,
                name="Staff",
                zone_role="staff",
                subnet="192.168.20.0/24",
                gateway="192.168.20.1",
                dhcp_enabled=True,
            ),
            VLANProfileModel(
                vlan_id=30,
                name="Guest",
                zone_role="guest",
                subnet="192.168.30.0/24",
                gateway="192.168.30.1",
                dhcp_enabled=True,
            ),
        ]

    def default_access_policies(self) -> List[AccessPolicyModel]:
        return [
            AccessPolicyModel(id=1, source_role="guest", target_zone="internet", action="allow", description="Guests may access internet only."),
            AccessPolicyModel(id=2, source_role="guest", target_zone="staff", action="deny", description="Guests are isolated from staff VLAN."),
            AccessPolicyModel(id=3, source_role="guest", target_zone="management", action="deny", description="Guests are blocked from management VLAN."),
            AccessPolicyModel(id=4, source_role="guest", target_zone="controller", action="deny", description="Guests cannot access controller services."),
            AccessPolicyModel(id=5, source_role="staff", target_zone="internet", action="allow", description="Staff may access internet."),
            AccessPolicyModel(id=6, source_role="staff", target_zone="staff", action="allow", description="Staff may access internal staff services."),
            AccessPolicyModel(id=7, source_role="staff", target_zone="management", action="deny", description="Staff cannot access management VLAN directly."),
            AccessPolicyModel(id=8, source_role="staff", target_zone="controller", action="deny", description="Staff cannot access controller admin services."),
            AccessPolicyModel(id=9, source_role="management", target_zone="internet", action="allow", description="Management may access internet."),
            AccessPolicyModel(id=10, source_role="management", target_zone="staff", action="allow", description="Management may access staff zone."),
            AccessPolicyModel(id=11, source_role="management", target_zone="management", action="allow", description="Management has full management VLAN access."),
            AccessPolicyModel(id=12, source_role="management", target_zone="controller", action="allow", description="Management can administer controller."),
        ]

    def is_allowed(self, source_role: str, target_zone: str) -> bool:
        source_role = self._safe_role(source_role)
        for policy in self.default_access_policies():
            if policy.source_role == source_role and policy.target_zone == target_zone:
                return policy.action == "allow"
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _access_reason(self, role: str, target: str, allowed: bool) -> str:
        if allowed:
            return f"Policy allows {role} access to {target}."
        return f"Policy blocks {role} access to {target}."

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        if obj is None:
            return {}
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        return dict(getattr(obj, "__dict__", {}))

    def _safe_role(self, role: str) -> str:
        role = str(role or "guest").lower()
        if role in ["management", "staff", "guest"]:
            return role
        return "guest"

    def _safe_severity(self, severity: str) -> str:
        severity = str(severity or "info").lower()
        if severity in ["info", "warning", "critical"]:
            return severity
        return "info"

    def _safe_category(self, category: str) -> str:
        category = str(category or "unknown").lower()
        allowed = {
            "segmentation_violation",
            "weak_signal",
            "high_retries",
            "packet_loss",
            "node_failure",
            "anomaly",
            "interference",
            "unknown",
        }
        return category if category in allowed else "unknown"


class IDSEngine:
    """
    Compatibility wrapper.

    Existing code may import IDSEngine from app.services.ids_engine.
    This class delegates to SecurityEngine so IDS and Security stay consistent.
    """

    def __init__(self) -> None:
        self.security = SecurityEngine()

    def inspect(self, nodes: List[Any], access_matrix: List[Any]) -> List[Dict[str, Any]]:
        return self.security.inspect(nodes, access_matrix)

    def inspect_clients(self, clients: List[Any]) -> List[Dict[str, Any]]:
        return self.security.analyze_client_sessions(clients)

    def ids_rule_catalog(self) -> List[Dict[str, Any]]:
        return self.security.ids_rule_catalog()
