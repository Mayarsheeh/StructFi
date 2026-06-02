from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.building_models import BuildingModel
from app.models.planning_models import (
    CapacityMetrics,
    CableRouteModel,
    CoverageMetrics,
    InterferenceMetrics,
    NodePlanModel,
    PlanningResultModel,
    PlanningSummaryModel,
    SSIDProfileModel,
    VLANPlanModel,
)
from app.models.security_models import (
    AccessDecisionModel,
    AccessPolicyModel,
    RADIUSProfileModel,
    SecurityAlertModel,
    SecurityStateModel,
    VLANProfileModel,
)
from app.models.simulation_models import (
    AIOutputModel,
    ClientModel,
    ClientMovementPoint,
    ControllerDecisionModel,
    ControllerStateModel,
    SimulationEventModel,
    SimulationStateModel,
)
from app.models.telemetry_models import (
    ClientSessionTelemetryModel,
    EnvironmentTelemetryModel,
    NodeRuntimeModel,
    RadioTelemetryModel,
    TelemetryHistoryPoint,
)
from app.services.ai_engine import StructiFiAIEngine


class StructiFiSimulator:
    """
    Live demo simulator for StructFi.

    Design goals:
    - Keep the API compatible with the existing FastAPI app.
    - Accept old and new planner outputs: node_plan, nodes, vlan_plan, vlan_profiles, ssid_profiles.
    - Simulate live movement, roaming, signal quality, telemetry, alerts, AI output, and controller decisions.
    - Keep it realistic enough for a graduation demo without pretending ESP32-S3 nodes are commercial APs.
    """

    def __init__(self):
        self.ai_engine = StructiFiAIEngine()
        self.noise_floor_dbm = -92.0
        self.max_history_points = 360

        # Alert calibration thresholds used by the polished reporting /
        # detection layer. Keep these attributes explicit so Apply CAD Plan
        # can safely recompute alerts immediately after loading a plan.
        self.weak_client_rssi_dbm = -72.0
        self.weak_client_snr_db = 18.0
        self.node_rssi_watch_dbm = -68.0
        self.node_snr_watch_db = 24.0
        self.retry_watch_pct = 10.0
        self.packet_loss_watch_pct = 2.0
        self.latency_watch_ms = 65.0

        self.state = self._build_default_state()

    # ------------------------------------------------------------------
    # Public API used by app/main.py
    # ------------------------------------------------------------------

    def get_state(self):
        return self.state.model_dump()

    def load_cad_plan(self, plan_dict: dict):
        normalized = self._normalize_plan_dict(plan_dict)
        plan = PlanningResultModel(**normalized)

        building = self._load_latest_building_from_plan_context()
        if building is None:
            building_payload = normalized.get("building")
            if isinstance(building_payload, dict):
                building = BuildingModel(**building_payload)

        if building is None:
            raise ValueError("No building model available. Run Extract Rooms before applying the CAD plan.")

        node_runtime = [self._runtime_from_plan_node(node) for node in plan.node_plan]
        clients = self._generate_clients_from_building(building)

        self.state = SimulationStateModel(
            step=0,
            timestamp=self._now(),
            simulation_source="cad_plan",
            building=building,
            node_plan=plan.node_plan,
            node_runtime=node_runtime,
            planning_summary=plan.summary,
            clients=clients,
            controller_state=ControllerStateModel(
                unified_ssid_enabled=True,
                roaming_80211r_enabled=True,
                managed_nodes_count=len(plan.node_plan),
                node_config_sync_ok=True,
                decisions=[],
            ),
            security_state=SecurityStateModel(
                vlan_profiles=self._vlans_from_plan_or_default(normalized),
                access_policies=self._default_policies(),
                access_matrix=[],
                alerts=[],
                radius_profile=RADIUSProfileModel(
                    enabled=True,
                    auth_mode="WPA3-Enterprise",
                    server_ip="192.168.100.10",
                    port=1812,
                    accounting_enabled=True,
                ),
            ),
            ai_output=AIOutputModel(),
            events=[
                SimulationEventModel(
                    type="cad_plan_applied",
                    message="CAD plan applied successfully. Live simulation is ready.",
                )
            ],
            telemetry_history=[],
        )

        self._initial_connect_clients()
        self._recompute_all()

    def step(self):
        self.state.step += 1
        self.state.timestamp = self._now()

        if self.state.simulation_source != "cad_plan" or not self.state.node_plan:
            self.state.events.append(
                SimulationEventModel(
                    type="info",
                    message="No CAD plan applied yet. Upload CAD, extract rooms, run planning, then apply CAD plan.",
                )
            )
            return

        for client in self.state.clients:
            previous_node_id = client.connected_node
            self._move_client(client)
            best_node = self._best_node_for_client(client)

            if best_node is None:
                if previous_node_id is not None:
                    self.state.events.append(
                        SimulationEventModel(
                            type="disconnect",
                            message=f"{client.name} disconnected because no online node can serve it.",
                            client_id=client.id,
                        )
                    )
                self._mark_client_disconnected(client)
                continue

            client.connected_node = best_node.id
            self._update_client_signal(client, best_node)

            if previous_node_id is not None and previous_node_id != best_node.id:
                client.roaming_count += 1
                self.state.events.append(
                    SimulationEventModel(
                        type="handover",
                        message=f"{client.name} roamed from Node-{previous_node_id} to Node-{best_node.id}.",
                        client_id=client.id,
                        node_id=best_node.id,
                    )
                )

        self._simulate_environment_drift()
        self._recompute_all()
        self._trim_events()

    def set_node_status(self, node_id: int, status: str):
        allowed = ["online", "offline", "degraded", "unknown"]
        if status not in allowed:
            raise ValueError(f"Status must be one of {allowed}")

        runtime = self._runtime_for_node(node_id)
        if runtime is None:
            raise ValueError(f"Node {node_id} not found")

        runtime.status = status
        runtime.last_seen = self._now()

        self.state.events.append(
            SimulationEventModel(
                type="node_status_change",
                message=f"{runtime.name} changed to {status}.",
                node_id=node_id,
            )
        )

        if status == "offline":
            for client in self.state.clients:
                if client.connected_node == node_id:
                    self._mark_client_disconnected(client)

        self._recompute_all()

    # ------------------------------------------------------------------
    # Plan normalization
    # ------------------------------------------------------------------

    def _normalize_plan_dict(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("Planning result must be a dictionary.")

        plan = dict(raw)

        node_items = self._extract_node_items(plan)
        normalized_nodes = [self._normalize_node_item(item, idx) for idx, item in enumerate(node_items, start=1)]

        summary = self._normalize_summary(plan.get("summary", {}), normalized_nodes)
        vlan_plan = self._normalize_vlan_plan(plan)
        ssid_profiles = self._normalize_ssid_profiles(plan)

        return {
            "file_name": plan.get("file_name") or plan.get("source_file") or "latest_building.json",
            "node_plan": normalized_nodes,
            "vlan_plan": vlan_plan,
            "ssid_profiles": ssid_profiles,
            "summary": summary,
            "building": plan.get("building"),
        }

    def _extract_node_items(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
            value = plan.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        result = plan.get("result")
        if isinstance(result, dict):
            for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
                value = result.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

        data = plan.get("data")
        if isinstance(data, dict):
            for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

        return []

    def _normalize_node_item(self, node: Dict[str, Any], idx: int) -> Dict[str, Any]:
        node_id = self._safe_int(node.get("id"), idx)
        name = str(node.get("name") or node.get("node_id") or f"Node SF-N{node_id:03d}")

        x = self._safe_float(
            node.get("x", node.get("node_x", node.get("placement_x", node.get("center_x", 0.0)))),
            0.0,
        )
        y = self._safe_float(
            node.get("y", node.get("node_y", node.get("placement_y", node.get("center_y", 0.0)))),
            0.0,
        )

        placement_type = str(node.get("placement_type") or "corner")
        if placement_type not in ["corner", "wall_mid", "ceiling_like", "hallway_edge", "fallback"]:
            placement_type = "hallway_edge" if "corridor" in str(node.get("node_role", "")).lower() else "corner"

        antenna_beamwidth = self._safe_int(
            node.get("antenna_beamwidth", node.get("beamwidth_deg", node.get("beam_width_deg", 360))),
            360,
        )

        tx_power = self._safe_int(node.get("tx_power", node.get("tx_power_dbm", 18)), 18)
        channel = self._safe_int(node.get("channel", 1), 1)

        coverage = node.get("coverage") if isinstance(node.get("coverage"), dict) else {}
        coverage_metrics = node.get("coverage_metrics") if isinstance(node.get("coverage_metrics"), dict) else {}

        capacity = node.get("capacity") if isinstance(node.get("capacity"), dict) else {}
        capacity_metrics = node.get("capacity_metrics") if isinstance(node.get("capacity_metrics"), dict) else {}

        interference = node.get("interference") if isinstance(node.get("interference"), dict) else {}
        cable_route = node.get("cable_route") if isinstance(node.get("cable_route"), dict) else {}

        notes = list(node.get("notes", [])) if isinstance(node.get("notes", []), list) else []
        if node.get("placement_reason"):
            notes.append(str(node.get("placement_reason")))
        if node.get("node_role"):
            notes.append(f"role={node.get('node_role')}")

        return {
            "id": node_id,
            "name": name,
            "room_id": node.get("room_id"),
            "room_name": node.get("room_name"),
            "floor": str(node.get("floor", "unknown")),
            "x": x,
            "y": y,
            "placement_type": placement_type,
            "antenna_direction": self._antenna_direction_label(node),
            "antenna_beamwidth": antenna_beamwidth,
            "tx_power": tx_power,
            "channel": channel,
            "status": "planned",
            "coverage": {
                "room_coverage_score": self._safe_float(
                    coverage.get("room_coverage_score", coverage_metrics.get("coverage_percent", 0.0)),
                    0.0,
                ),
                "nearby_overlap_score": self._safe_float(coverage.get("nearby_overlap_score", 0.0), 0.0),
                "estimated_rssi_center": self._safe_float(
                    coverage.get("estimated_rssi_center", coverage_metrics.get("avg_rssi_dbm", -58.0)),
                    -58.0,
                ),
                "estimated_snr_center": self._safe_float(
                    coverage.get("estimated_snr_center", coverage_metrics.get("avg_snr_db", 32.0)),
                    32.0,
                ),
            },
            "capacity": {
                "projected_clients": self._safe_int(
                    capacity.get("projected_clients", capacity_metrics.get("expected_clients", 0)),
                    0,
                ),
                "projected_capacity_mbps": self._safe_float(
                    capacity.get("projected_capacity_mbps", capacity_metrics.get("effective_capacity_mbps", 110.0)),
                    110.0,
                ),
                "projected_utilization_pct": self._safe_float(
                    capacity.get("projected_utilization_pct", capacity_metrics.get("utilization_percent", 0.0)),
                    0.0,
                ),
                "retry_risk_score": self._safe_float(capacity.get("retry_risk_score", 0.0), 0.0),
            },
            "interference": {
                "channel_cost": self._safe_float(interference.get("channel_cost", 0.0), 0.0),
                "interference_score": self._safe_float(interference.get("interference_score", 0.0), 0.0),
                "cochannel_risk": self._safe_float(interference.get("cochannel_risk", 0.0), 0.0),
                "adjacent_channel_risk": self._safe_float(interference.get("adjacent_channel_risk", 0.0), 0.0),
            },
            "cable_route": {
                "path_type": cable_route.get("path_type", "unknown"),
                "length_m": self._safe_float(cable_route.get("length_m", 0.0), 0.0),
                "estimated_cost": self._safe_float(cable_route.get("estimated_cost", 0.0), 0.0),
                "path_points": cable_route.get("path_points", []),
            },
            "placement_score": self._safe_float(node.get("placement_score", 85.0), 85.0),
            "notes": notes,
        }

    def _normalize_summary(self, raw_summary: Any, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary = raw_summary if isinstance(raw_summary, dict) else {}
        node_count = self._safe_int(summary.get("node_count", summary.get("nodes_planned", len(nodes))), len(nodes))
        return {
            "node_count": node_count,
            "coverage_score": self._safe_float(summary.get("coverage_score", 92.0), 92.0),
            "speed_score": self._safe_float(summary.get("speed_score", 88.0), 88.0),
            "placement_score": self._safe_float(summary.get("placement_score", 85.0), 85.0),
            "wall_penalty_score": self._safe_float(summary.get("wall_penalty_score", 74.0), 74.0),
            "channel_reuse_score": self._safe_float(summary.get("channel_reuse_score", 82.0), 82.0),
            "capacity_score": self._safe_float(summary.get("capacity_score", 86.0), 86.0),
            "estimated_dead_zones": self._safe_int(summary.get("estimated_dead_zones", 0), 0),
        }

    def _normalize_vlan_plan(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = plan.get("vlan_plan") or plan.get("vlan_profiles") or []
        output = []

        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                zone = item.get("zone") or item.get("zone_role") or item.get("access_level") or "staff"
                if zone not in ["management", "staff", "guest"]:
                    zone = "staff"
                output.append(
                    {
                        "vlan_id": self._safe_int(item.get("vlan_id", 20), 20),
                        "name": str(item.get("name", zone.title())),
                        "zone": zone,
                        "subnet": str(item.get("subnet", self._subnet_for_zone(zone))),
                        "dhcp_enabled": bool(item.get("dhcp_enabled", True)),
                    }
                )

        if output:
            return output

        return [
            {"vlan_id": 10, "name": "Management", "zone": "management", "subnet": "192.168.10.0/24", "dhcp_enabled": True},
            {"vlan_id": 20, "name": "Staff", "zone": "staff", "subnet": "192.168.20.0/24", "dhcp_enabled": True},
            {"vlan_id": 30, "name": "Guest", "zone": "guest", "subnet": "192.168.30.0/24", "dhcp_enabled": True},
        ]

    def _normalize_ssid_profiles(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = plan.get("ssid_profiles") or []
        output = []

        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                name = item.get("ssid_name") or item.get("ssid") or item.get("name") or "StructFi-Staff"
                security_mode = item.get("security_mode") or item.get("security") or "WPA3-Enterprise"
                if security_mode not in ["WPA3-Enterprise", "WPA2-PSK", "Open"]:
                    security_mode = "WPA3-Enterprise" if "Enterprise" in str(security_mode) else "WPA2-PSK"
                output.append(
                    {
                        "ssid_name": str(name),
                        "security_mode": security_mode,
                        "vlan_id": self._safe_int(item.get("vlan_id", 20), 20),
                        "fast_roaming_enabled": bool(item.get("fast_roaming_enabled", item.get("roaming_80211r", True))),
                    }
                )

        if output:
            return output

        return [
            {"ssid_name": "StructFi-Enterprise", "security_mode": "WPA3-Enterprise", "vlan_id": 20, "fast_roaming_enabled": True},
            {"ssid_name": "StructFi-Management", "security_mode": "WPA3-Enterprise", "vlan_id": 10, "fast_roaming_enabled": True},
            {"ssid_name": "StructFi-Guest", "security_mode": "Open", "vlan_id": 30, "fast_roaming_enabled": False},
        ]

    # ------------------------------------------------------------------
    # Runtime generation
    # ------------------------------------------------------------------

    def _runtime_from_plan_node(self, node: NodePlanModel) -> NodeRuntimeModel:
        base_rssi = node.coverage.estimated_rssi_center if node.coverage else -55.0
        base_snr = node.coverage.estimated_snr_center if node.coverage else 34.0

        return NodeRuntimeModel(
            id=node.id,
            name=node.name,
            room_id=node.room_id,
            room_name=node.room_name,
            floor=node.floor,
            status="online",
            uptime_seconds=0,
            software_version="esp32s3-node-fw-1.0-demo",
            ip_address=f"192.168.10.{100 + node.id}",
            last_seen=self._now(),
            connected_clients=0,
            current_load=0,
            radio=RadioTelemetryModel(
                rssi_avg=round(base_rssi, 2),
                snr_avg=round(base_snr, 2),
                current_channel=node.channel,
                tx_power_dbm=node.tx_power,
                retry_rate_pct=0.0,
                packet_loss_pct=0.0,
                throughput_mbps=0.0,
                latency_ms=0.0,
            ),
            environment=EnvironmentTelemetryModel(
                temperature_c=27.0,
                humidity_pct=45.0,
                room_pressure_score=0.0,
                occupancy_estimate=0,
            ),
            client_sessions=[],
        )

    def _generate_clients_from_building(self, building: BuildingModel) -> List[ClientModel]:
        clients: List[ClientModel] = []
        client_id = 1

        for room in building.rooms:
            count = self._client_count_for_room(room)
            if count <= 0:
                continue

            roles = self._roles_for_room(room)
            points = self._client_path_for_room(room, count)

            for idx in range(count):
                base = points[idx % len(points)]
                path = self._build_movement_path(room, base[0], base[1], idx)
                role = roles[idx % len(roles)]

                clients.append(
                    ClientModel(
                        id=client_id,
                        name=f"Client-{client_id}",
                        role=role,
                        x=path[0].x,
                        y=path[0].y,
                        floor=room.floor,
                        speed=round(0.18 + (idx % 4) * 0.07, 2),
                        allowed_zones=self._allowed_zones_for_role(role),
                        path=path,
                        path_index=0,
                    )
                )
                client_id += 1

        return clients

    def _client_count_for_room(self, room) -> int:
        room_type = str(room.room_type)
        expected = int(room.expected_clients or 0)

        if room_type in ["bathroom", "storage", "service"]:
            return max(0, min(2, expected))
        if room_type == "corridor":
            return max(1, min(4, expected or 2))
        if room_type in ["meeting", "open_area", "reception"]:
            return max(2, min(8, expected or 4))
        return max(1, min(5, expected or 2))

    def _client_path_for_room(self, room, count: int) -> List[tuple[float, float]]:
        margin_x = min(max(room.width * 0.18, 0.25), max(room.width * 0.45, 0.25))
        margin_y = min(max(room.height * 0.18, 0.25), max(room.height * 0.45, 0.25))

        x1 = room.x + margin_x
        x2 = room.x + max(room.width - margin_x, margin_x)
        y1 = room.y + margin_y
        y2 = room.y + max(room.height - margin_y, margin_y)

        candidates = [
            (x1, y1),
            (x2, y1),
            (x1, y2),
            (x2, y2),
            (room.center_x, room.center_y),
        ]

        return candidates[: max(1, min(len(candidates), count))]

    def _build_movement_path(self, room, start_x: float, start_y: float, idx: int) -> List[ClientMovementPoint]:
        dx = min(max(room.width * 0.18, 0.35), 1.2)
        dy = min(max(room.height * 0.18, 0.35), 1.2)

        direction = 1 if idx % 2 == 0 else -1

        points = [
            (start_x, start_y),
            (start_x + direction * dx, start_y),
            (start_x + direction * dx, start_y + dy),
            (start_x, start_y + dy),
        ]

        path = []
        for px, py in points:
            cx = min(max(px, room.x + 0.15), room.x + max(room.width - 0.15, 0.15))
            cy = min(max(py, room.y + 0.15), room.y + max(room.height - 0.15, 0.15))
            path.append(ClientMovementPoint(x=round(cx, 3), y=round(cy, 3)))

        return path

    def _roles_for_room(self, room) -> List[str]:
        zone = str(room.zone)
        room_type = str(room.room_type)

        if zone == "management" or room_type == "server_room":
            return ["management", "staff"]
        if zone == "guest" or room_type == "reception":
            return ["guest", "guest", "staff"]
        if room_type in ["meeting", "open_area", "corridor"]:
            return ["staff", "staff", "guest"]
        return ["staff", "staff", "staff"]

    def _allowed_zones_for_role(self, role: str) -> List[str]:
        if role == "management":
            return ["internet", "staff", "management", "controller"]
        if role == "guest":
            return ["internet"]
        return ["internet", "staff"]

    # ------------------------------------------------------------------
    # Live simulation math
    # ------------------------------------------------------------------

    def _initial_connect_clients(self):
        for client in self.state.clients:
            best_node = self._best_node_for_client(client)
            if best_node is None:
                self._mark_client_disconnected(client)
            else:
                client.connected_node = best_node.id
                self._update_client_signal(client, best_node)

    def _move_client(self, client: ClientModel):
        if not client.path:
            return

        # Deterministic movement: one waypoint per simulation step.
        client.path_index = (client.path_index + 1) % len(client.path)
        next_point = client.path[client.path_index]
        client.x = next_point.x
        client.y = next_point.y

    def _best_node_for_client(self, client: ClientModel) -> Optional[NodePlanModel]:
        candidates = [n for n in self.state.node_plan if n.floor == client.floor]
        if not candidates:
            candidates = list(self.state.node_plan)

        best_node = None
        best_score = -1e9

        for node in candidates:
            runtime = self._runtime_for_node(node.id)
            if runtime and runtime.status == "offline":
                continue

            rssi = self._estimate_rssi(client.x, client.y, node)
            load_penalty = 0.0 if not runtime else runtime.current_load * 1.7
            degraded_penalty = 8.0 if runtime and runtime.status == "degraded" else 0.0
            same_room_bonus = 5.0 if node.room_id is not None and self._client_room_id(client) == node.room_id else 0.0
            channel_penalty = node.interference.interference_score * 0.12

            score = rssi + same_room_bonus - load_penalty - degraded_penalty - channel_penalty

            if score > best_score:
                best_score = score
                best_node = node

        return best_node

    def _update_client_signal(self, client: ClientModel, node: NodePlanModel):
        runtime = self._runtime_for_node(node.id)
        rssi = self._estimate_rssi(client.x, client.y, node)
        snr = max(4.0, rssi - self.noise_floor_dbm)

        interference = node.interference.interference_score
        connected_before = runtime.current_load if runtime else 0
        utilization_factor = min(1.0, connected_before / 14.0)

        if runtime and runtime.status == "degraded":
            rssi -= 5.0
            snr = max(4.0, snr - 6.0)
            utilization_factor = min(1.0, utilization_factor + 0.20)

        phy_rate = self._throughput_from_snr(snr)
        throughput = phy_rate * max(0.35, 1.0 - utilization_factor * 0.38)
        throughput -= interference * 0.75
        throughput = max(3.0, min(145.0, throughput))

        retry = self._retry_from_rssi_snr(rssi, snr) + utilization_factor * 5.5 + interference * 0.15
        loss = self._loss_from_rssi_snr(rssi, snr) + utilization_factor * 2.2 + max(0.0, retry - 14.0) * 0.18
        latency = 6.0 + utilization_factor * 18.0 + loss * 1.4 + retry * 0.25

        client.current_rssi = round(rssi, 2)
        client.current_snr = round(snr, 2)
        client.current_throughput_mbps = round(max(0.0, throughput), 2)
        client.current_packet_loss_pct = round(max(0.0, min(35.0, loss)), 2)
        client.current_retry_rate_pct = round(max(0.0, min(45.0, retry)), 2)
        client.current_latency_ms = round(max(2.0, min(220.0, latency)), 2)

    def _estimate_rssi(self, x: float, y: float, node: NodePlanModel) -> float:
        distance = max(0.55, math.hypot(x - node.x, y - node.y))
        tx_power = float(node.tx_power)

        # Low-cost indoor approximation. This is a simulated educational model.
        rssi = -39.0 + (tx_power - 15.0) - (22.5 * math.log10(distance))

        # Directional node effect based on antenna category. The model only has label+beamwidth,
        # so use a soft penalty instead of requiring exact azimuth.
        if node.antenna_beamwidth <= 90:
            rssi += 2.0
        elif node.antenna_beamwidth >= 300:
            rssi -= 0.5

        # Room mismatch attenuation: avoids every node covering everything equally.
        client_room_id = self._room_id_at_point(x, y)
        if client_room_id is not None and node.room_id is not None and client_room_id != node.room_id:
            rssi -= 6.0

        rssi -= node.interference.interference_score * 0.08
        return max(-95.0, min(-35.0, rssi))

    def _throughput_from_snr(self, snr: float) -> float:
        if snr >= 38:
            return 145.0
        if snr >= 32:
            return 125.0
        if snr >= 26:
            return 95.0
        if snr >= 20:
            return 68.0
        if snr >= 14:
            return 38.0
        if snr >= 8:
            return 16.0
        return 5.0

    def _retry_from_rssi_snr(self, rssi: float, snr: float) -> float:
        retry = 1.0
        if rssi < -72:
            retry += (-72 - rssi) * 0.65
        if snr < 22:
            retry += (22 - snr) * 0.55
        return retry

    def _loss_from_rssi_snr(self, rssi: float, snr: float) -> float:
        loss = 0.2
        if rssi < -75:
            loss += (-75 - rssi) * 0.45
        if snr < 18:
            loss += (18 - snr) * 0.38
        return loss

    # ------------------------------------------------------------------
    # Recompute telemetry / controller / security / AI
    # ------------------------------------------------------------------

    def _recompute_all(self):
        self._refresh_node_runtime()
        self._compute_controller_decisions()
        self._compute_access_matrix()
        self._compute_alerts()
        self._compute_ai_summary()
        self._append_telemetry_history()

    def _refresh_node_runtime(self):
        for runtime in self.state.node_runtime:
            connected = [c for c in self.state.clients if c.connected_node == runtime.id]
            runtime.connected_clients = len(connected)
            runtime.current_load = len(connected)
            runtime.last_seen = self._now()

            if runtime.status != "offline":
                runtime.uptime_seconds += 5

            if connected:
                avg_rssi = sum((c.current_rssi or -90.0) for c in connected) / len(connected)
                avg_snr = sum((c.current_snr or 4.0) for c in connected) / len(connected)
                avg_tp = sum(c.current_throughput_mbps for c in connected)
                avg_loss = sum(c.current_packet_loss_pct for c in connected) / len(connected)
                avg_retry = sum(c.current_retry_rate_pct for c in connected) / len(connected)
                avg_latency = sum(c.current_latency_ms for c in connected) / len(connected)
            else:
                plan_node = self._plan_node_for_runtime(runtime.id)
                avg_rssi = plan_node.coverage.estimated_rssi_center if plan_node else -58.0
                avg_snr = plan_node.coverage.estimated_snr_center if plan_node else 30.0
                avg_tp = 0.0
                avg_loss = 0.0
                avg_retry = 0.0
                avg_latency = 0.0

            runtime.radio.rssi_avg = round(avg_rssi, 2)
            runtime.radio.snr_avg = round(avg_snr, 2)
            runtime.radio.throughput_mbps = round(avg_tp, 2)
            runtime.radio.packet_loss_pct = round(avg_loss, 2)
            runtime.radio.retry_rate_pct = round(avg_retry, 2)
            runtime.radio.latency_ms = round(avg_latency, 2)

            runtime.environment.occupancy_estimate = len(connected)
            runtime.environment.room_pressure_score = round(min(100.0, len(connected) * 12.0), 2)
            runtime.environment.temperature_c = round(27.0 + len(connected) * 0.85 + max(0, runtime.radio.tx_power_dbm - 15) * 0.12, 2)
            runtime.environment.humidity_pct = round(44.0 + (self.state.step % 9) * 0.45 + len(connected) * 0.35, 2)

            runtime.client_sessions = [
                ClientSessionTelemetryModel(
                    client_id=c.id,
                    client_name=c.name,
                    role=c.role,
                    connected_node_id=runtime.id,
                    current_rssi=c.current_rssi,
                    current_snr=c.current_snr,
                    current_throughput_mbps=c.current_throughput_mbps,
                    roaming_events=c.roaming_count,
                    packets_sent=max(0, self.state.step * 12 + c.id * 5),
                    packets_received=max(0, self.state.step * 12 + c.id * 5 - int(c.current_packet_loss_pct or 0)),
                )
                for c in connected
            ]

    def _compute_controller_decisions(self):
        decisions: List[ControllerDecisionModel] = []
        decision_id = 1

        # Keep the controller realistic: not every observation becomes an action.
        # Only meaningful runtime conditions create decisions, with a small cap so
        # the demo/report stays readable.
        for runtime in self.state.node_runtime:
            if runtime.status == "offline":
                decisions.append(
                    ControllerDecisionModel(
                        id=decision_id,
                        node_id=runtime.id,
                        action="raise_alert",
                        value="offline",
                        reason="Node is offline; clients should roam to the nearest available node.",
                        severity="critical",
                    )
                )
                decision_id += 1
                continue

            load_ratio = 0.0
            try:
                load_ratio = float(runtime.connected_clients or runtime.current_load or 0) / max(float(getattr(runtime, "max_clients", 14) or 14), 1.0)
            except Exception:
                load_ratio = 0.0

            if runtime.current_load >= 6 or load_ratio >= 0.65:
                decisions.append(
                    ControllerDecisionModel(
                        id=decision_id,
                        node_id=runtime.id,
                        action="rebalance_load",
                        value="prefer_neighbor_nodes",
                        reason="Client density is approaching the configured capacity threshold.",
                        severity="warning",
                    )
                )
                decision_id += 1

            if runtime.radio.retry_rate_pct > 8:
                new_channel = self._next_channel(runtime.radio.current_channel)
                decisions.append(
                    ControllerDecisionModel(
                        id=decision_id,
                        node_id=runtime.id,
                        action="change_channel",
                        value=str(new_channel),
                        reason="Retry rate indicates possible channel contention or interference.",
                        severity="warning",
                    )
                )
                decision_id += 1

            if runtime.radio.rssi_avg < -62 and runtime.radio.tx_power_dbm < 20:
                decisions.append(
                    ControllerDecisionModel(
                        id=decision_id,
                        node_id=runtime.id,
                        action="change_tx_power",
                        value="+2 dBm",
                        reason="Average RSSI is below the planning comfort target for active clients.",
                        severity="warning",
                    )
                )
                decision_id += 1

            if runtime.radio.packet_loss_pct > 2.0:
                decisions.append(
                    ControllerDecisionModel(
                        id=decision_id,
                        node_id=runtime.id,
                        action="mark_degraded",
                        value="quality_degraded",
                        reason="Packet loss exceeded the simulation quality threshold.",
                        severity="warning",
                    )
                )
                decision_id += 1

            if len(decisions) >= 10:
                break

        if not decisions:
            # One stable decision is useful for the report because it documents
            # that the controller inspected the runtime state and found no action.
            decisions.append(
                ControllerDecisionModel(
                    id=1,
                    action="none",
                    value="stable",
                    reason="Controller inspected node load, RF quality, retry rate, packet loss, and latency; no active corrective action was required.",
                    severity="info",
                )
            )

        self.state.controller_state.decisions = decisions
        self.state.controller_state.managed_nodes_count = len(self.state.node_runtime)
        self.state.controller_state.node_config_sync_ok = not any(n.status == "offline" for n in self.state.node_runtime)

    def _compute_access_matrix(self):
        decisions: List[AccessDecisionModel] = []

        for client in self.state.clients:
            for target in ["internet", "staff", "management", "controller"]:
                allowed = self._is_allowed(client.role, target)
                decisions.append(
                    AccessDecisionModel(
                        client_id=client.id,
                        client_name=client.name,
                        role=client.role,
                        target_zone=target,
                        allowed=allowed,
                        reason="Policy allows access" if allowed else "Policy blocks access",
                    )
                )

        self.state.security_state.access_matrix = decisions

    def _compute_alerts(self):
        alerts: List[SecurityAlertModel] = []
        alert_id = 1

        def add_alert(severity, title, description, category="unknown", node_id=None, client_id=None, evidence=None, recommendation=""):
            nonlocal alert_id
            alerts.append(
                SecurityAlertModel(
                    id=alert_id,
                    severity=severity,
                    title=title,
                    description=description,
                    node_id=node_id,
                    client_id=client_id,
                    category=category,
                    evidence=evidence or {},
                    recommendation=recommendation,
                )
            )
            alert_id += 1

        # Node-level detections. Thresholds are intentionally planning-oriented:
        # they do not spam the dashboard, but they also do not hide every issue
        # when the simulated network is merely "mostly fine".
        node_candidates = []
        for runtime in self.state.node_runtime:
            if runtime.status == "offline":
                node_candidates.append((100, runtime, "critical", "Node Offline", "node_failure", "Power/uplink loss. Clients must roam."))
                continue
            if runtime.status == "degraded":
                node_candidates.append((90, runtime, "warning", "Node Degraded", "node_degraded", "Runtime status is degraded."))

            rssi = float(runtime.radio.rssi_avg or -90.0)
            snr = float(runtime.radio.snr_avg or 0.0)
            retry = float(runtime.radio.retry_rate_pct or 0.0)
            loss = float(runtime.radio.packet_loss_pct or 0.0)
            latency = float(runtime.radio.latency_ms or 0.0)
            load = int(runtime.current_load or runtime.connected_clients or 0)

            if rssi < -62:
                node_candidates.append((70 + abs(rssi + 62), runtime, "warning", "Weak RF Margin", "weak_signal", f"Average RSSI is {rssi} dBm, below the comfort target."))
            if snr < 30 and load > 0:
                node_candidates.append((55 + max(0, 30 - snr), runtime, "warning", "Reduced SNR", "low_snr", f"Average SNR is {snr} dB under active load."))
            if retry > 8:
                node_candidates.append((60 + retry, runtime, "warning", "Retry Rate Elevated", "high_retries", f"Retry rate is {retry}%, indicating contention or RF instability."))
            if loss > 1.2:
                node_candidates.append((65 + loss * 4, runtime, "warning", "Packet Loss Detected", "packet_loss", f"Packet loss is {loss}% during this simulation run."))
            if latency > 35:
                node_candidates.append((50 + latency / 2, runtime, "warning", "Latency Pressure", "latency", f"Average latency is {latency} ms."))
            if load >= 4:
                node_candidates.append((48 + load * 3, runtime, "info", "Load Watch", "anomaly", f"Node is currently serving {load} clients."))

        # Pick the strongest signal per node/category and cap total node alerts.
        unique = {}
        for score, runtime, severity, title, category, description in node_candidates:
            key = (runtime.id, category)
            if key not in unique or score > unique[key][0]:
                unique[key] = (score, runtime, severity, title, category, description)

        for score, runtime, severity, title, category, description in sorted(unique.values(), key=lambda x: x[0], reverse=True)[:8]:
            add_alert(
                severity=severity,
                title=title,
                description=f"{runtime.name}: {description}",
                node_id=runtime.id,
                category=category,
                evidence={
                    "rssi_avg": runtime.radio.rssi_avg,
                    "snr_avg": runtime.radio.snr_avg,
                    "retry_rate_pct": runtime.radio.retry_rate_pct,
                    "packet_loss_pct": runtime.radio.packet_loss_pct,
                    "latency_ms": runtime.radio.latency_ms,
                    "connected_clients": runtime.connected_clients,
                },
                recommendation="Review node placement, RF material assumptions, channel plan, and client distribution." if severity != "info" else "Monitor this node during additional simulation steps.",
            )

        # Client/QoS detections, capped separately so reports remain readable.
        client_candidates = []
        for client in self.state.clients:
            qos_state = str(getattr(client, "qos_state", "not_evaluated"))
            rssi = getattr(client, "current_rssi", None)
            snr = getattr(client, "current_snr", None)
            latency = getattr(client, "current_latency_ms", 0.0)
            loss = getattr(client, "current_packet_loss_pct", 0.0)
            if qos_state == "violated":
                client_candidates.append((80, client, "warning", "QoS Violation", "anomaly", "Client traffic requirement is not currently satisfied."))
            elif qos_state == "warning":
                client_candidates.append((55, client, "info", "QoS Watch", "anomaly", "Client is close to its QoS threshold."))
            if rssi is not None and rssi < self.weak_client_rssi_dbm:
                client_candidates.append((65, client, "warning", "Client Roaming Risk", "roaming", f"Client RSSI is {rssi} dBm."))
            if snr is not None and snr < self.weak_client_snr_db:
                client_candidates.append((60, client, "warning", "Client Low SNR", "low_snr", f"Client SNR is {snr} dB."))
            if latency and latency > 60:
                client_candidates.append((50, client, "warning", "Client Latency Pressure", "latency", f"Client latency is {latency} ms."))
            if loss and loss > 2.0:
                client_candidates.append((55, client, "warning", "Client Packet Loss", "packet_loss", f"Client packet loss is {loss}%."))

        seen_clients = set()
        for _, client, severity, title, category, description in sorted(client_candidates, key=lambda x: x[0], reverse=True):
            if client.id in seen_clients:
                continue
            seen_clients.add(client.id)
            add_alert(
                severity=severity,
                title=title,
                description=f"{client.name}: {description}",
                client_id=client.id,
                node_id=client.connected_node,
                category=category,
                evidence={
                    "traffic_profile": getattr(client, "traffic_profile", None),
                    "qos_state": getattr(client, "qos_state", None),
                    "rssi": getattr(client, "current_rssi", None),
                    "snr": getattr(client, "current_snr", None),
                    "throughput_mbps": getattr(client, "current_throughput_mbps", None),
                    "latency_ms": getattr(client, "current_latency_ms", None),
                    "packet_loss_pct": getattr(client, "current_packet_loss_pct", None),
                },
                recommendation="Check client association, handover behavior, and QoS profile requirements.",
            )
            if len(seen_clients) >= 4:
                break

        # Do not turn the full access matrix into dozens of alerts. Only surface
        # a tiny proof that segmentation is being enforced when relevant.
        blocked_guest_management = [
            d for d in self.state.security_state.access_matrix
            if not d.allowed and d.role == "guest" and d.target_zone in ["management", "controller"]
        ]
        if blocked_guest_management and len(alerts) < 10:
            sample = blocked_guest_management[0]
            add_alert(
                severity="info",
                title="Segmentation Enforcement Verified",
                description=f"Guest access to {sample.target_zone} was blocked as expected.",
                client_id=sample.client_id,
                category="segmentation_violation",
                evidence={"role": sample.role, "target_zone": sample.target_zone, "allowed": sample.allowed},
                recommendation="Keep guest isolation enabled; this is expected security behavior, not a failure.",
            )

        # Final cap keeps the UI/report sane: enough detections to prove the IDS
        # is alive, not a wall of repeated alerts.
        self.state.security_state.alerts = alerts[:12]

    def _compute_ai_summary(self):
        self.state.ai_output = self.ai_engine.evaluate(
            nodes=self.state.node_runtime,
            alerts=self.state.security_state.alerts,
        )

    def _append_telemetry_history(self):
        for runtime in self.state.node_runtime:
            self.state.telemetry_history.append(
                TelemetryHistoryPoint(
                    step=self.state.step,
                    timestamp=self.state.timestamp,
                    node_id=runtime.id,
                    rssi_avg=runtime.radio.rssi_avg,
                    snr_avg=runtime.radio.snr_avg,
                    retry_rate_pct=runtime.radio.retry_rate_pct,
                    throughput_mbps=runtime.radio.throughput_mbps,
                    packet_loss_pct=runtime.radio.packet_loss_pct,
                    connected_clients=runtime.connected_clients,
                    temperature_c=runtime.environment.temperature_c,
                    humidity_pct=runtime.environment.humidity_pct,
                )
            )

        if len(self.state.telemetry_history) > self.max_history_points:
            self.state.telemetry_history = self.state.telemetry_history[-self.max_history_points:]

    # ------------------------------------------------------------------
    # Defaults: centralized router, VLANs, policies
    # ------------------------------------------------------------------

    def _vlans_from_plan_or_default(self, plan: Dict[str, Any]) -> List[VLANProfileModel]:
        vlans = []
        raw = plan.get("vlan_plan") or []
        for item in raw:
            zone = item.get("zone", "staff")
            vlans.append(
                VLANProfileModel(
                    vlan_id=self._safe_int(item.get("vlan_id", 20), 20),
                    name=str(item.get("name", zone.title())),
                    zone_role=zone if zone in ["management", "staff", "guest"] else "staff",
                    subnet=str(item.get("subnet", self._subnet_for_zone(zone))),
                    gateway=self._gateway_for_zone(zone),
                    dhcp_enabled=bool(item.get("dhcp_enabled", True)),
                )
            )
        return vlans or self._default_vlans()

    def _default_vlans(self) -> List[VLANProfileModel]:
        return [
            VLANProfileModel(vlan_id=10, name="Management", zone_role="management", subnet="192.168.10.0/24", gateway="192.168.10.1"),
            VLANProfileModel(vlan_id=20, name="Staff", zone_role="staff", subnet="192.168.20.0/24", gateway="192.168.20.1"),
            VLANProfileModel(vlan_id=30, name="Guest", zone_role="guest", subnet="192.168.30.0/24", gateway="192.168.30.1"),
        ]

    def _default_policies(self) -> List[AccessPolicyModel]:
        return [
            AccessPolicyModel(id=1, source_role="management", target_zone="management", action="allow", description="Management devices can access management services."),
            AccessPolicyModel(id=2, source_role="management", target_zone="staff", action="allow", description="Management can access staff resources."),
            AccessPolicyModel(id=3, source_role="management", target_zone="controller", action="allow", description="Management can access the controller."),
            AccessPolicyModel(id=4, source_role="management", target_zone="internet", action="allow", description="Management can access internet."),
            AccessPolicyModel(id=5, source_role="staff", target_zone="staff", action="allow", description="Staff can access staff resources."),
            AccessPolicyModel(id=6, source_role="staff", target_zone="internet", action="allow", description="Staff can access internet."),
            AccessPolicyModel(id=7, source_role="staff", target_zone="management", action="deny", description="Staff cannot access management VLAN."),
            AccessPolicyModel(id=8, source_role="staff", target_zone="controller", action="deny", description="Staff cannot access controller management."),
            AccessPolicyModel(id=9, source_role="guest", target_zone="internet", action="allow", description="Guests can access internet only."),
            AccessPolicyModel(id=10, source_role="guest", target_zone="staff", action="deny", description="Guests are isolated from staff VLAN."),
            AccessPolicyModel(id=11, source_role="guest", target_zone="management", action="deny", description="Guests are isolated from management VLAN."),
            AccessPolicyModel(id=12, source_role="guest", target_zone="controller", action="deny", description="Guests cannot access controller."),
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_default_state(self) -> SimulationStateModel:
        return SimulationStateModel(
            step=0,
            timestamp=self._now(),
            simulation_source="json_default",
            building=None,
            node_plan=[],
            node_runtime=[],
            planning_summary=PlanningSummaryModel(),
            clients=[],
            controller_state=ControllerStateModel(
                unified_ssid_enabled=True,
                roaming_80211r_enabled=True,
                managed_nodes_count=0,
                node_config_sync_ok=True,
                decisions=[],
            ),
            security_state=SecurityStateModel(
                vlan_profiles=self._default_vlans(),
                access_policies=self._default_policies(),
                access_matrix=[],
                alerts=[],
                radius_profile=RADIUSProfileModel(),
            ),
            ai_output=AIOutputModel(),
            events=[],
            telemetry_history=[],
        )

    def _load_latest_building_from_plan_context(self) -> Optional[BuildingModel]:
        try:
            latest_path = Path("data/parsed/latest_building.json")
            if latest_path.exists():
                return BuildingModel(**json.loads(latest_path.read_text(encoding="utf-8")))
        except Exception:
            pass

        try:
            from app.services.dxf_room_extractor import DXFRoomExtractor

            extractor = DXFRoomExtractor()
            return extractor.get_latest_building_model()
        except Exception:
            return None

    def _simulate_environment_drift(self):
        # Currently deterministic, enough to make values feel live without random instability.
        pass

    def _mark_client_disconnected(self, client: ClientModel):
        client.connected_node = None
        client.current_rssi = None
        client.current_snr = None
        client.current_throughput_mbps = 0.0
        client.current_packet_loss_pct = 0.0
        client.current_retry_rate_pct = 0.0
        client.current_latency_ms = 0.0

    def _runtime_for_node(self, node_id: int) -> Optional[NodeRuntimeModel]:
        for runtime in self.state.node_runtime:
            if runtime.id == node_id:
                return runtime
        return None

    def _plan_node_for_runtime(self, node_id: int) -> Optional[NodePlanModel]:
        for node in self.state.node_plan:
            if node.id == node_id:
                return node
        return None

    def _client_room_id(self, client: ClientModel) -> Optional[int]:
        return self._room_id_at_point(client.x, client.y)

    def _room_id_at_point(self, x: float, y: float) -> Optional[int]:
        building = self.state.building
        if building is None:
            return None
        for room in building.rooms:
            if room.x <= x <= room.x + room.width and room.y <= y <= room.y + room.height:
                return room.id
        return None

    def _is_allowed(self, role: str, target_zone: str) -> bool:
        for policy in self.state.security_state.access_policies:
            if policy.source_role == role and policy.target_zone == target_zone:
                return policy.action == "allow"
        return False

    def _next_channel(self, current: int) -> int:
        channels = [36, 40, 44, 48, 149, 153, 157, 161]
        if current not in channels:
            return channels[0]
        return channels[(channels.index(current) + 1) % len(channels)]

    def _subnet_for_zone(self, zone: str) -> str:
        return {
            "management": "192.168.10.0/24",
            "staff": "192.168.20.0/24",
            "guest": "192.168.30.0/24",
        }.get(zone, "192.168.20.0/24")

    def _gateway_for_zone(self, zone: str) -> str:
        return {
            "management": "192.168.10.1",
            "staff": "192.168.20.1",
            "guest": "192.168.30.1",
        }.get(zone, "192.168.20.1")

    def _antenna_direction_label(self, node: Dict[str, Any]) -> str:
        beam = self._safe_int(node.get("antenna_beamwidth", node.get("beamwidth_deg", node.get("beam_width_deg", 360))), 360)
        role = str(node.get("node_role", "")).lower()
        if beam >= 300:
            return "omni_balanced"
        if "corridor" in role:
            return "horizontal_bias"
        if beam <= 90:
            return "sectorized"
        return "omni_balanced"

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            return int(float(value))
        except Exception:
            return default

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _trim_events(self):
        if len(self.state.events) > 80:
            self.state.events = self.state.events[-80:]

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")
