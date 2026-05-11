from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from app.core.config import settings
except Exception:
    # Fallback keeps this module import-safe during isolated tests.
    class _FallbackSettings:
        VLAN_PROFILES = [
            {
                "vlan_id": 10,
                "name": "Management",
                "zone_role": "management",
                "zone": "management",
                "subnet": "192.168.10.0/24",
                "gateway": "192.168.10.1",
                "dhcp_enabled": True,
                "description": "Controller and admin devices.",
            },
            {
                "vlan_id": 20,
                "name": "Staff",
                "zone_role": "staff",
                "zone": "staff",
                "subnet": "192.168.20.0/24",
                "gateway": "192.168.20.1",
                "dhcp_enabled": True,
                "description": "Trusted staff users.",
            },
            {
                "vlan_id": 30,
                "name": "Guest",
                "zone_role": "guest",
                "zone": "guest",
                "subnet": "192.168.30.0/24",
                "gateway": "192.168.30.1",
                "dhcp_enabled": True,
                "description": "Internet-only guest access.",
            },
        ]
        ACCESS_POLICIES = [
            {"id": 1, "source_role": "guest", "target_zone": "internet", "action": "allow", "description": "Guest internet access."},
            {"id": 2, "source_role": "guest", "target_zone": "staff", "action": "deny", "description": "Guest isolation."},
            {"id": 3, "source_role": "guest", "target_zone": "management", "action": "deny", "description": "Guest cannot access management."},
            {"id": 4, "source_role": "guest", "target_zone": "controller", "action": "deny", "description": "Guest cannot access controller."},
            {"id": 5, "source_role": "staff", "target_zone": "internet", "action": "allow", "description": "Staff internet access."},
            {"id": 6, "source_role": "staff", "target_zone": "staff", "action": "allow", "description": "Staff internal access."},
            {"id": 7, "source_role": "staff", "target_zone": "management", "action": "deny", "description": "Staff management blocked."},
            {"id": 8, "source_role": "staff", "target_zone": "controller", "action": "deny", "description": "Staff controller blocked."},
            {"id": 9, "source_role": "management", "target_zone": "internet", "action": "allow", "description": "Management internet access."},
            {"id": 10, "source_role": "management", "target_zone": "staff", "action": "allow", "description": "Management staff access."},
            {"id": 11, "source_role": "management", "target_zone": "management", "action": "allow", "description": "Management VLAN access."},
            {"id": 12, "source_role": "management", "target_zone": "controller", "action": "allow", "description": "Management controller access."},
        ]
        SSID_PROFILES = []
        RADIUS_PROFILE = {"enabled": True, "auth_mode": "WPA3-Enterprise", "server_ip": "192.168.10.10", "port": 1812, "accounting_enabled": True}
        CENTRAL_ROUTER = {"name": "StructFi Central Controller", "management_ip": "192.168.10.1"}

    settings = _FallbackSettings()

try:
    from app.models.security_models import (
        AccessDecisionModel,
        AccessPolicyModel,
        RADIUSProfileModel,
        SecurityStateModel,
        VLANProfileModel,
    )
except Exception:
    AccessDecisionModel = None
    AccessPolicyModel = None
    RADIUSProfileModel = None
    SecurityStateModel = None
    VLANProfileModel = None


class NetworkSegmentation:
    """
    StructFi network segmentation service.

    Purpose:
    - Keep VLAN, SSID, RADIUS, and access policies centralized in config.py.
    - Provide backward-compatible methods used by main.py, controller.py, and simulator.py.
    - Return simple dictionaries so the dashboard and mobile app can parse results easily.

    Demo policy model:
    - Guest: internet only.
    - Staff: internet + staff resources, no controller/management access by default.
    - Management: full administrative access.
    """

    def __init__(self) -> None:
        self.vlan_profiles = self._load_vlan_profiles()
        self.access_policies = self._load_access_policies()
        self.ssid_profiles = self._load_ssid_profiles()
        self.radius_profile = self._load_radius_profile()
        self.central_router = dict(getattr(settings, "CENTRAL_ROUTER", {}) or {})

    # ------------------------------------------------------------------
    # Public API used by app/main.py and legacy services
    # ------------------------------------------------------------------

    def get_policies(self) -> List[Dict[str, Any]]:
        return [dict(policy) for policy in self.access_policies]

    def get_vlan_profiles(self) -> List[Dict[str, Any]]:
        return [dict(vlan) for vlan in self.vlan_profiles]

    def get_ssid_profiles(self) -> List[Dict[str, Any]]:
        return [dict(ssid) for ssid in self.ssid_profiles]

    def get_radius_profile(self) -> Dict[str, Any]:
        return dict(self.radius_profile)

    def get_controller_profile(self) -> Dict[str, Any]:
        return dict(self.central_router)

    def is_allowed(self, source_role: str, target_zone: str) -> bool:
        return self.get_action(source_role, target_zone) == "allow"

    def get_action(self, source_role: str, target_zone: str) -> str:
        source = self._normalize_role(source_role)
        target = self._normalize_target(target_zone)

        for policy in self.access_policies:
            if policy.get("source_role") == source and policy.get("target_zone") == target:
                return str(policy.get("action", "deny")).lower()

        # Fail closed: this is safer and easier to explain in the defense.
        return "deny"

    def get_policy_for(self, source_role: str, target_zone: str) -> Optional[Dict[str, Any]]:
        source = self._normalize_role(source_role)
        target = self._normalize_target(target_zone)

        for policy in self.access_policies:
            if policy.get("source_role") == source and policy.get("target_zone") == target:
                return dict(policy)

        return None

    def evaluate_access(self, clients: List[Any], targets: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Build an access matrix for clients.

        Accepts either Pydantic client objects or plain dictionaries.
        """
        if targets is None:
            targets = ["internet", "staff", "management", "controller"]

        decisions: List[Dict[str, Any]] = []

        for client in clients or []:
            client_id = self._get_value(client, "id", 0)
            client_name = self._get_value(client, "name", f"Client-{client_id}")
            role = self._normalize_role(self._get_value(client, "role", "staff"))

            for target in targets:
                target_zone = self._normalize_target(target)
                policy = self.get_policy_for(role, target_zone)
                allowed = bool(policy and policy.get("action") == "allow")
                reason = self._decision_reason(role, target_zone, allowed, policy)

                decisions.append(
                    {
                        "client_id": int(client_id) if self._is_int_like(client_id) else client_id,
                        "client_name": str(client_name),
                        "role": role,
                        "target_zone": target_zone,
                        "allowed": allowed,
                        "reason": reason,
                        "policy_id": policy.get("id") if policy else None,
                    }
                )

        return decisions

    def evaluate_client_access(self, client: Any, targets: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        return self.evaluate_access([client], targets=targets)

    def build_access_matrix(self, clients: List[Any], targets: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        return self.evaluate_access(clients, targets=targets)

    def get_security_state(self, clients: Optional[List[Any]] = None) -> Dict[str, Any]:
        return {
            "vlan_profiles": self.get_vlan_profiles(),
            "access_policies": self.get_policies(),
            "access_matrix": self.evaluate_access(clients or []),
            "alerts": [],
            "radius_profile": self.get_radius_profile(),
            "ssid_profiles": self.get_ssid_profiles(),
            "central_router": self.get_controller_profile(),
        }

    def get_security_state_model(self, clients: Optional[List[Any]] = None):
        """
        Return Pydantic SecurityStateModel when models are available.
        Fallback to plain dict if model validation is not available.
        """
        state = self.get_security_state(clients)

        if SecurityStateModel is None:
            return state

        try:
            vlan_models = []
            if VLANProfileModel is not None:
                for vlan in state["vlan_profiles"]:
                    vlan_models.append(
                        VLANProfileModel(
                            vlan_id=int(vlan.get("vlan_id", 0)),
                            name=str(vlan.get("name", "Unknown")),
                            zone_role=self._normalize_role(vlan.get("zone_role", vlan.get("zone", "staff"))),
                            subnet=str(vlan.get("subnet", "0.0.0.0/24")),
                            gateway=str(vlan.get("gateway", "0.0.0.1")),
                            dhcp_enabled=bool(vlan.get("dhcp_enabled", True)),
                        )
                    )

            policy_models = []
            if AccessPolicyModel is not None:
                for policy in state["access_policies"]:
                    policy_models.append(
                        AccessPolicyModel(
                            id=int(policy.get("id", 0)),
                            source_role=self._normalize_role(policy.get("source_role", "staff")),
                            target_zone=self._normalize_target(policy.get("target_zone", "internet")),
                            action=str(policy.get("action", "deny")).lower(),
                            description=str(policy.get("description", "")),
                        )
                    )

            decision_models = []
            if AccessDecisionModel is not None:
                for decision in state["access_matrix"]:
                    decision_models.append(
                        AccessDecisionModel(
                            client_id=int(decision.get("client_id", 0)),
                            client_name=str(decision.get("client_name", "Client")),
                            role=self._normalize_role(decision.get("role", "staff")),
                            target_zone=str(decision.get("target_zone", "internet")),
                            allowed=bool(decision.get("allowed", False)),
                            reason=str(decision.get("reason", "")),
                        )
                    )

            radius_model = None
            if RADIUSProfileModel is not None:
                radius = state["radius_profile"]
                radius_model = RADIUSProfileModel(
                    enabled=bool(radius.get("enabled", True)),
                    auth_mode=str(radius.get("auth_mode", "WPA3-Enterprise")),
                    server_ip=str(radius.get("server_ip", "192.168.10.10")),
                    port=int(radius.get("port", 1812)),
                    accounting_enabled=bool(radius.get("accounting_enabled", True)),
                )

            kwargs = {
                "vlan_profiles": vlan_models,
                "access_policies": policy_models,
                "access_matrix": decision_models,
                "alerts": [],
            }
            if radius_model is not None:
                kwargs["radius_profile"] = radius_model

            return SecurityStateModel(**kwargs)
        except Exception:
            return state

    # ------------------------------------------------------------------
    # Helpers for dashboard/mobile documentation
    # ------------------------------------------------------------------

    def describe_policy_matrix(self) -> Dict[str, Any]:
        roles = ["guest", "staff", "management"]
        targets = ["internet", "staff", "management", "controller"]

        matrix: Dict[str, Dict[str, bool]] = {}
        for role in roles:
            matrix[role] = {}
            for target in targets:
                matrix[role][target] = self.is_allowed(role, target)

        return {
            "roles": roles,
            "targets": targets,
            "matrix": matrix,
            "explanation": {
                "guest": "Internet-only isolated access.",
                "staff": "Internal staff access without management/controller privileges.",
                "management": "Administrative access to controller and management VLAN.",
            },
        }

    def get_role_vlan(self, role: str) -> Dict[str, Any]:
        normalized = self._normalize_role(role)
        for vlan in self.vlan_profiles:
            if vlan.get("zone_role") == normalized or vlan.get("zone") == normalized:
                return dict(vlan)
        return dict(self.vlan_profiles[1]) if len(self.vlan_profiles) > 1 else {}

    def get_client_network_profile(self, role: str) -> Dict[str, Any]:
        normalized = self._normalize_role(role)
        vlan = self.get_role_vlan(normalized)
        ssids = [
            ssid for ssid in self.ssid_profiles
            if int(ssid.get("vlan_id", -1)) == int(vlan.get("vlan_id", -2))
        ]

        return {
            "role": normalized,
            "vlan": vlan,
            "ssid_profiles": ssids,
            "allowed_targets": [
                target for target in ["internet", "staff", "management", "controller"]
                if self.is_allowed(normalized, target)
            ],
            "blocked_targets": [
                target for target in ["internet", "staff", "management", "controller"]
                if not self.is_allowed(normalized, target)
            ],
        }

    # ------------------------------------------------------------------
    # Internal loading helpers
    # ------------------------------------------------------------------

    def _load_vlan_profiles(self) -> List[Dict[str, Any]]:
        profiles = []
        for item in getattr(settings, "VLAN_PROFILES", []) or []:
            vlan = dict(item)
            role = self._normalize_role(vlan.get("zone_role", vlan.get("zone", "staff")))
            vlan["zone_role"] = role
            vlan["zone"] = role
            profiles.append(vlan)
        return profiles

    def _load_access_policies(self) -> List[Dict[str, Any]]:
        policies = []
        for idx, item in enumerate(getattr(settings, "ACCESS_POLICIES", []) or [], start=1):
            policy = dict(item)
            policy["id"] = int(policy.get("id", idx))
            policy["source_role"] = self._normalize_role(policy.get("source_role", "staff"))
            policy["target_zone"] = self._normalize_target(policy.get("target_zone", "internet"))
            policy["action"] = str(policy.get("action", "deny")).lower()
            policy["description"] = str(policy.get("description", ""))
            policies.append(policy)
        return policies

    def _load_ssid_profiles(self) -> List[Dict[str, Any]]:
        profiles = []
        for item in getattr(settings, "SSID_PROFILES", []) or []:
            profiles.append(dict(item))
        return profiles

    def _load_radius_profile(self) -> Dict[str, Any]:
        return dict(getattr(settings, "RADIUS_PROFILE", {}) or {})

    def _normalize_role(self, role: Any) -> str:
        value = str(role or "staff").strip().lower()

        aliases = {
            "admin": "management",
            "administrator": "management",
            "mgmt": "management",
            "manager": "management",
            "employee": "staff",
            "teacher": "staff",
            "student": "staff",
            "visitor": "guest",
            "public": "guest",
            "iot": "staff",
            "service": "staff",
            "unknown": "staff",
        }

        value = aliases.get(value, value)

        if value not in ["management", "staff", "guest"]:
            return "staff"

        return value

    def _normalize_target(self, target: Any) -> str:
        value = str(target or "internet").strip().lower()

        aliases = {
            "wan": "internet",
            "web": "internet",
            "online": "internet",
            "mgmt": "management",
            "admin": "management",
            "router": "controller",
            "central_controller": "controller",
            "centralized_router": "controller",
            "staff_vlan": "staff",
            "management_vlan": "management",
            "guest_vlan": "guest",
        }

        value = aliases.get(value, value)

        allowed_targets = ["management", "staff", "guest", "internet", "controller"]
        if value not in allowed_targets:
            return value

        return value

    def _decision_reason(
        self,
        role: str,
        target: str,
        allowed: bool,
        policy: Optional[Dict[str, Any]],
    ) -> str:
        if policy and policy.get("description"):
            prefix = "Allowed" if allowed else "Blocked"
            return f"{prefix} by policy {policy.get('id')}: {policy.get('description')}"

        if allowed:
            return f"Policy allows {role} access to {target}."

        return f"Policy blocks {role} access to {target}."

    def _get_value(self, obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _is_int_like(self, value: Any) -> bool:
        try:
            int(value)
            return True
        except Exception:
            return False
