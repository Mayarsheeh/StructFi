from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class AdvancedCADPlanner:
    """
    StructFi CAD Planner

    Compatible with existing main.py methods:
    - plan_from_latest_dxf()
    - plan_from_latest_building()
    - plan_nodes_from_latest_building()
    - generate_plan_from_latest_building()
    - plan_latest()
    - plan_nodes()
    - get_latest_plan()
    - get_latest_plan_model()

    StructFi rules:
    - Every non-bathroom room gets at least one node.
    - Bathroom gets no node.
    - Bathroom is covered from corridor/nearest node.
    - Corridors get backbone nodes.
    - Large rooms may get multiple nodes.
    - Nodes are corner/wall-based, not center-based.
    - Nodes include TX power, beam direction, channel, RSSI/SNR, capacity, telemetry, AI decision.
    """

    def __init__(self) -> None:
        self.parsed_dir = Path("data/parsed")
        self.parsed_dir.mkdir(parents=True, exist_ok=True)

        self.latest_building_path = self.parsed_dir / "latest_building.json"
        self.latest_plan_path = self.parsed_dir / "latest_plan.json"

        self.reference_rssi_dbm = -39.0
        self.reference_tx_power_dbm = 15.0
        self.noise_floor_dbm = -92.0

        self.min_tx_power_dbm = 8.0
        self.default_tx_power_dbm = 15.0
        self.max_tx_power_dbm = 20.0

        self.minimum_acceptable_rssi_dbm = -72.0
        self.target_room_rssi_dbm = -62.0

        self.path_loss_exponent_room = 2.15
        self.path_loss_exponent_corridor = 1.85
        self.path_loss_exponent_obstructed = 2.75
        self.wall_loss_db = 7.5

        self.normal_node_area_capacity_m2 = 42.0
        self.max_single_node_diagonal_m = 9.5
        self.large_room_area_multiplier = 1.55

        self.base_node_capacity_mbps = 110.0
        self.max_clients_per_node_normal = 18
        self.max_clients_per_node_corridor = 28

        self.packet_loss_target_percent = 3.0
        self.roaming_latency_target_ms = 100.0

        self.default_beamwidth_deg = 70.0
        self.corridor_beamwidth_deg = 55.0
        self.open_area_beamwidth_deg = 90.0
        self.service_beamwidth_deg = 65.0

        self.channels_5ghz = [36, 40, 44, 48, 149, 153, 157, 161]

    # ------------------------------------------------------------------
    # Public API / compatibility with main.py
    # ------------------------------------------------------------------

    def plan_from_latest_dxf(self) -> Dict[str, Any]:
        """
        Required by your current app/main.py.
        The name says DXF, but practically it reads latest_building.json produced by extractor.
        """
        return self.plan_from_latest_building()

    def plan_from_latest_building(self) -> Dict[str, Any]:
        building = self._load_latest_building()
        result = self.plan_building(building)
        self._save_latest_plan(result)
        return result

    def plan_nodes_from_latest_building(self) -> Dict[str, Any]:
        return self.plan_from_latest_building()

    def generate_plan_from_latest_building(self) -> Dict[str, Any]:
        return self.plan_from_latest_building()

    def plan_latest(self) -> Dict[str, Any]:
        return self.plan_from_latest_building()

    def plan_nodes(self, building: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if building is None:
            return self.plan_from_latest_building()

        result = self.plan_building(building)
        self._save_latest_plan(result)
        return result

    def get_latest_plan(self) -> Optional[Dict[str, Any]]:
        if not self.latest_plan_path.exists():
            return None

        try:
            return json.loads(self.latest_plan_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def get_latest_plan_model(self) -> Optional[Dict[str, Any]]:
        """
        Required by your current app/main.py.
        """
        return self.get_latest_plan()

    def get_latest_plan_dict(self) -> Optional[Dict[str, Any]]:
        return self.get_latest_plan()

    def load_latest_plan(self) -> Optional[Dict[str, Any]]:
        return self.get_latest_plan()

    # ------------------------------------------------------------------
    # Main planning
    # ------------------------------------------------------------------

    def plan_building(self, building: Dict[str, Any]) -> Dict[str, Any]:
        rooms = self._normalize_rooms(list(building.get("rooms", [])))
        walls = list(building.get("walls", []))
        bounds = dict(building.get("bounds", {}))
        labels = list(building.get("labels", []))

        if not rooms:
            result = self._empty_plan(
                building,
                reason=(
                    "No rooms were extracted. Run Extract Rooms first. "
                    "If this continues, extractor produced zero rooms from latest_building.json."
                ),
            )
            self._save_latest_plan(result)
            return result

        avg_room_area = self._average_normal_room_area(rooms)
        nodes: List[Dict[str, Any]] = []

        for room in rooms:
            room_type = self._room_type(room)

            if room_type == "bathroom":
                continue

            if room_type == "corridor":
                nodes.extend(self._plan_corridor_nodes(room, rooms, walls, avg_room_area))
                continue

            count = self._nodes_required_for_room(room, avg_room_area)
            nodes.extend(self._plan_room_nodes(room, rooms, walls, count))

        nodes = self._ensure_corridor_backbone_node(nodes, rooms, walls, avg_room_area)
        nodes = self._assign_channels(nodes)
        nodes = self._attach_coverage_and_telemetry(nodes, rooms, walls)
        nodes = self._assign_bathroom_coverage(nodes, rooms)
        nodes = self._calculate_upgrade_degrade_status(nodes)
        nodes = self._normalize_plan_nodes_output(nodes)

        vlan_plan = self._build_vlan_profiles()
        ssid_profiles = self._build_ssid_profiles()
        summary = self._build_summary(building, rooms, nodes)
        file_name = building.get("file_name", "unknown")

        result = {
            "project": "StructFi",
            "planner_version": "unified-backend-demo-v4",
            "file_name": file_name,
            "source_file": file_name,
            "source_format": building.get("source_format", "UNKNOWN"),
            "building": building,
            "bounds": bounds,
            "rooms_count": len(rooms),
            "nodes_count": len(nodes),
            "rooms": rooms,
            "node_plan": nodes,
            "nodes": nodes,
            "walls": walls,
            "labels": labels,
            "cable_routes": self._build_cable_routes(nodes, building),
            "ssid_profiles": ssid_profiles,
            "vlan_plan": vlan_plan,
            "vlan_profiles": vlan_plan,
            "summary": summary,
            "constraints": {
                "coverage_target_percent": "95-99",
                "packet_loss_target_percent": self.packet_loss_target_percent,
                "throughput_target_mbps": "90-110",
                "node_power_limit_watts": "<10",
                "roaming_latency_target_ms": self.roaming_latency_target_ms,
                "placement_rule": "Every non-bathroom room gets at least one corner-based directional node.",
                "bathroom_rule": "Bathrooms get no node and are covered from corridor/nearest node.",
                "corridor_rule": "Corridors are planned as backbone coverage zones.",
            },
            "status": "ok",
        }

        self._save_latest_plan(result)
        return result


    def _ensure_corridor_backbone_node(
        self,
        nodes: List[Dict[str, Any]],
        rooms: List[Dict[str, Any]],
        walls: List[Dict[str, Any]],
        avg_room_area: float,
    ) -> List[Dict[str, Any]]:
        """
        Demo safety rule:
        Ensure at least one corridor/backbone node exists.

        This helps when the extractor classifies a corridor-like space as
        reception/open_area/staff instead of corridor.
        """
        if not rooms:
            return nodes

        corridor_room_ids = set()
        for room in rooms:
            if self._room_type(room) == "corridor":
                corridor_room_ids.add(room.get("id"))

        for node in nodes:
            node_role = str(node.get("node_role", "")).lower()
            if node.get("room_id") in corridor_room_ids:
                return nodes
            if node_role == "corridor_backbone_node":
                return nodes

        candidates: List[Tuple[float, Dict[str, Any]]] = []

        for room in rooms:
            room_type = self._room_type(room)
            if room_type == "bathroom":
                continue

            w = max(float(room.get("width", 0.0)), 0.1)
            h = max(float(room.get("height", 0.0)), 0.1)
            area = max(float(room.get("area", w * h)), 0.1)
            aspect = max(w, h) / max(min(w, h), 0.1)
            name_text = str(room.get("name", "") or room.get("label_text", "")).lower()

            score = 0.0
            if room_type == "corridor":
                score += 120.0
            if "corridor" in name_text or "hall" in name_text or "lobby" in name_text:
                score += 85.0
            if room_type in ["reception", "open_area"]:
                score += 25.0
            if aspect >= 2.3:
                score += 38.0
            if min(w, h) <= 3.6:
                score += 25.0
            if area >= 4.0:
                score += min(area, 40.0) * 0.45

            candidates.append((score, room))

        if not candidates:
            return nodes

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_room = candidates[0]

        if best_score < 38.0:
            return nodes

        extra_nodes = self._plan_corridor_nodes(
            corridor=best_room,
            all_rooms=rooms,
            walls=walls,
            avg_room_area=avg_room_area,
        )

        if not extra_nodes:
            return nodes

        extra_node = extra_nodes[0]
        extra_node["node_role"] = "corridor_backbone_node"
        extra_node["placement_type"] = "hallway_edge"
        extra_node["placement_reason"] = (
            "Guaranteed corridor/backbone node added for circulation coverage, roaming support, "
            "and bathroom/transition-zone coverage."
        )

        nodes.append(extra_node)

        for idx, node in enumerate(nodes, start=1):
            node["id"] = idx
            node["node_id"] = f"SF-N{idx:03d}"
            node["name"] = f"Node SF-N{idx:03d}"

        return nodes

    # ------------------------------------------------------------------
    # Node planning
    # ------------------------------------------------------------------

    def _plan_room_nodes(
        self,
        room: Dict[str, Any],
        all_rooms: List[Dict[str, Any]],
        walls: List[Dict[str, Any]],
        nodes_needed: int,
    ) -> List[Dict[str, Any]]:
        """
        Plan normal room nodes.

        Demo tuning:
        - Small/Exp1 rooms get one balanced wall/corner node with wider beamwidth,
          so the visual coverage represents the whole room instead of only one corner.
        - Larger rooms still use spread corner placement.
        """
        corners = self._room_corners(room)
        if not corners:
            corners = self._fallback_corners(room)

        ranked = self._rank_room_corners(room, corners, all_rooms, walls)

        if nodes_needed <= 1:
            selected = ranked[:1]
        else:
            selected = self._select_spread_corners(ranked, nodes_needed)

        nodes = []
        center_x, center_y = self._room_center(room)

        for index, corner in enumerate(selected, start=1):
            if nodes_needed <= 1:
                x, y = self._balanced_single_room_node_position(room, corner[0], corner[1])
            else:
                x, y = self._move_point_inside_room(room, corner[0], corner[1], inset_ratio=0.08)

            direction = self._angle_degrees(x, y, center_x, center_y)
            beamwidth = self._beamwidth_for_room(room)

            if nodes_needed <= 1:
                beamwidth = self._single_node_room_beamwidth(room, beamwidth)

            tx_power = self._fit_tx_power_for_room(room, x, y, walls)

            nodes.append(
                self._make_node(
                    room=room,
                    x=x,
                    y=y,
                    sequence=index,
                    node_role="room_node",
                    beam_direction_deg=direction,
                    beamwidth_deg=beamwidth,
                    tx_power_dbm=tx_power,
                    placement_reason=self._placement_reason(room, tx_power, nodes_needed),
                )
            )

        return nodes

    def _plan_corridor_nodes(
        self,
        corridor: Dict[str, Any],
        all_rooms: List[Dict[str, Any]],
        walls: List[Dict[str, Any]],
        avg_room_area: float,
    ) -> List[Dict[str, Any]]:
        """
        Corridor planning for this demo:
        - Treat the corridor as one coverage zone, like a room.
        - Add exactly one backbone node.
        - Place it near the corridor edge, not in the visual center, so it still
          matches the hidden in-wall / wall-side installation concept.
        """
        x = float(corridor.get("x", 0.0))
        y = float(corridor.get("y", 0.0))
        w = max(float(corridor.get("width", 1.0)), 0.1)
        h = max(float(corridor.get("height", 1.0)), 0.1)

        long_axis = "x" if w >= h else "y"
        length = max(w, h)

        if long_axis == "x":
            # One node around the first third, aimed along the corridor length.
            px = x + w * 0.34
            py = y + h * 0.50
            direction = 0.0
        else:
            px = x + w * 0.50
            py = y + h * 0.34
            direction = 90.0

        px, py = self._clamp_point_to_room(corridor, px, py)

        # Keep corridor usable with one node, without over-powering the whole map.
        tx_power = min(self.max_tx_power_dbm, max(16.0, 13.0 + length * 0.38))
        beamwidth = max(115.0, min(150.0, self.corridor_beamwidth_deg + 65.0))

        return [
            self._make_node(
                room=corridor,
                x=px,
                y=py,
                sequence=1,
                node_role="corridor_backbone_node",
                beam_direction_deg=direction,
                beamwidth_deg=beamwidth,
                tx_power_dbm=tx_power,
                placement_reason=(
                    "Single corridor/backbone node. The corridor is treated as one room-like "
                    "coverage zone for clean demo distribution, roaming support, and transition-zone coverage."
                ),
            )
        ]

    def _nodes_required_for_room(self, room: Dict[str, Any], avg_room_area: float) -> int:
        room_type = self._room_type(room)
        area = max(float(room.get("area", 0.0)), 0.1)
        w = max(float(room.get("width", 0.0)), 0.1)
        h = max(float(room.get("height", 0.0)), 0.1)
        diagonal = math.hypot(w, h)

        if room_type == "bathroom":
            return 0

        if room_type == "corridor":
            return 1

        if room_type in ["storage", "service", "kitchen"] and area <= 18.0:
            return 1

        effective_capacity = self.normal_node_area_capacity_m2

        if room_type == "open_area":
            effective_capacity *= 0.78
        elif room_type == "meeting":
            effective_capacity *= 0.72
        elif room_type == "server_room":
            effective_capacity *= 0.85

        by_area = math.ceil(area / max(effective_capacity, 1.0))
        by_diagonal = math.ceil(diagonal / self.max_single_node_diagonal_m)

        by_average = 1
        if avg_room_area > 0 and area > avg_room_area * self.large_room_area_multiplier:
            by_average = math.ceil(area / max(avg_room_area * 1.20, 1.0))

        required = max(1, by_area, by_diagonal, by_average)

        if room_type == "open_area":
            required = max(required, 2)

        return min(required, 6)

    # ------------------------------------------------------------------
    # Placement scoring
    # ------------------------------------------------------------------

    def _rank_room_corners(
        self,
        room: Dict[str, Any],
        corners: List[Tuple[float, float]],
        all_rooms: List[Dict[str, Any]],
        walls: List[Dict[str, Any]],
    ) -> List[Tuple[float, float]]:
        scored = []

        for corner in corners:
            px, py = self._move_point_inside_room(room, corner[0], corner[1], inset_ratio=0.08)
            score = self._corner_score(room, px, py, all_rooms, walls)
            scored.append((score, corner))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [corner for score, corner in scored]

    def _corner_score(
        self,
        room: Dict[str, Any],
        px: float,
        py: float,
        all_rooms: List[Dict[str, Any]],
        walls: List[Dict[str, Any]],
    ) -> float:
        samples = self._sample_points_in_room(room, target_count=20)
        room_type = self._room_type(room)
        rssis = []

        for sx, sy in samples:
            distance = max(math.hypot(sx - px, sy - py), 0.5)
            wall_count = self._count_walls_between(px, py, sx, sy, walls)
            rssis.append(
                self._predict_rssi(
                    distance_m=distance,
                    tx_power_dbm=self.default_tx_power_dbm,
                    wall_count=wall_count,
                    room_type=room_type,
                    angle_penalty_db=0.0,
                )
            )

        avg_rssi = sum(rssis) / max(len(rssis), 1)
        worst_rssi = min(rssis) if rssis else -90.0
        coverage_ratio = sum(1 for rssi in rssis if rssi >= self.minimum_acceptable_rssi_dbm) / max(len(rssis), 1)

        leakage_penalty = self._estimate_leakage_penalty(room, px, py, all_rooms)
        corridor_bonus = self._corridor_or_doorway_bonus(room, px, py, all_rooms)

        score = 0.0
        score += coverage_ratio * 45.0
        score += max(0.0, avg_rssi + 80.0) * 0.8
        score += max(0.0, worst_rssi + 85.0) * 0.7
        score -= leakage_penalty * 8.0
        score += corridor_bonus * 6.0

        return score

    def _select_spread_corners(self, corners: List[Tuple[float, float]], count: int) -> List[Tuple[float, float]]:
        if not corners:
            return []

        selected = [corners[0]]

        while len(selected) < min(count, len(corners)):
            best = None
            best_distance = -1.0

            for corner in corners:
                if corner in selected:
                    continue

                distance = min(math.hypot(corner[0] - s[0], corner[1] - s[1]) for s in selected)

                if distance > best_distance:
                    best_distance = distance
                    best = corner

            if best is None:
                break

            selected.append(best)

        return selected

    # ------------------------------------------------------------------
    # RF + telemetry
    # ------------------------------------------------------------------

    def _attach_coverage_and_telemetry(
        self,
        nodes: List[Dict[str, Any]],
        rooms: List[Dict[str, Any]],
        walls: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        for node in nodes:
            room = self._find_room_by_id(rooms, node.get("room_id"))
            if not room:
                continue

            samples = self._sample_points_in_room(room, target_count=36)
            rssis = []
            snrs = []

            for sx, sy in samples:
                angle_penalty = self._directional_angle_penalty(
                    node_x=node["x"],
                    node_y=node["y"],
                    target_x=sx,
                    target_y=sy,
                    beam_direction_deg=node["beam_direction_deg"],
                    beamwidth_deg=node["beamwidth_deg"],
                )

                distance = max(math.hypot(sx - node["x"], sy - node["y"]), 0.5)
                wall_count = self._count_walls_between(node["x"], node["y"], sx, sy, walls)

                rssi = self._predict_rssi(
                    distance_m=distance,
                    tx_power_dbm=node["tx_power_dbm"],
                    wall_count=wall_count,
                    room_type=self._room_type(room),
                    angle_penalty_db=angle_penalty,
                )
                snr = rssi - self.noise_floor_dbm

                rssis.append(rssi)
                snrs.append(snr)

            avg_rssi = sum(rssis) / max(len(rssis), 1)
            worst_rssi = min(rssis) if rssis else -95.0
            avg_snr = sum(snrs) / max(len(snrs), 1)
            coverage_ratio = sum(1 for rssi in rssis if rssi >= self.minimum_acceptable_rssi_dbm) / max(len(rssis), 1)

            expected_clients = int(room.get("expected_clients", 1))
            capacity = self._estimate_capacity(room, avg_rssi, avg_snr, expected_clients)
            packet_loss = self._estimate_packet_loss(avg_rssi, avg_snr, capacity["utilization_percent"])
            latency = self._estimate_latency_ms(avg_snr, capacity["utilization_percent"])
            throughput = self._estimate_throughput_mbps(avg_rssi, avg_snr, capacity["utilization_percent"])

            node["coverage_metrics"] = {
                "sample_points": len(samples),
                "coverage_ratio": round(coverage_ratio, 4),
                "coverage_percent": round(coverage_ratio * 100.0, 2),
                "avg_rssi_dbm": round(avg_rssi, 2),
                "worst_rssi_dbm": round(worst_rssi, 2),
                "avg_snr_db": round(avg_snr, 2),
                "target_rssi_dbm": self.target_room_rssi_dbm,
                "minimum_acceptable_rssi_dbm": self.minimum_acceptable_rssi_dbm,
            }

            node["capacity_metrics"] = capacity
            node["telemetry"] = {
                "rssi_dbm": round(avg_rssi, 2),
                "snr_db": round(avg_snr, 2),
                "throughput_mbps": round(throughput, 2),
                "latency_ms": round(latency, 2),
                "packet_loss_percent": round(packet_loss, 2),
                "connected_clients": expected_clients,
                "channel_utilization_percent": capacity["utilization_percent"],
                "tx_power_dbm": node["tx_power_dbm"],
                "estimated_power_watts": self._estimate_power_watts(node["tx_power_dbm"]),
                "temperature_c": self._estimate_node_temperature(capacity["utilization_percent"]),
                "humidity_percent": self._estimate_humidity(room),
            }

        return nodes

    def _predict_rssi(
        self,
        distance_m: float,
        tx_power_dbm: float,
        wall_count: int,
        room_type: str,
        angle_penalty_db: float,
    ) -> float:
        distance_m = max(distance_m, 0.5)

        if room_type == "corridor":
            exponent = self.path_loss_exponent_corridor
        elif wall_count > 0:
            exponent = self.path_loss_exponent_obstructed
        else:
            exponent = self.path_loss_exponent_room

        path_loss = 10.0 * exponent * math.log10(distance_m)
        wall_loss = wall_count * self.wall_loss_db

        rssi = (
            self.reference_rssi_dbm
            + (tx_power_dbm - self.reference_tx_power_dbm)
            - path_loss
            - wall_loss
            - angle_penalty_db
        )

        return max(-95.0, min(-35.0, rssi))

    def _fit_tx_power_for_room(
        self,
        room: Dict[str, Any],
        node_x: float,
        node_y: float,
        walls: List[Dict[str, Any]],
    ) -> float:
        room_type = self._room_type(room)
        samples = self._sample_points_in_room(room, target_count=25)

        for power in [8, 10, 12, 14, 16, 18, 20]:
            rssis = []
            for sx, sy in samples:
                distance = max(math.hypot(sx - node_x, sy - node_y), 0.5)
                wall_count = self._count_walls_between(node_x, node_y, sx, sy, walls)
                rssis.append(
                    self._predict_rssi(
                        distance_m=distance,
                        tx_power_dbm=float(power),
                        wall_count=wall_count,
                        room_type=room_type,
                        angle_penalty_db=0.0,
                    )
                )

            coverage = sum(1 for rssi in rssis if rssi >= self.minimum_acceptable_rssi_dbm) / max(len(rssis), 1)
            worst = min(rssis) if rssis else -95.0

            if coverage >= 0.96 and worst >= self.minimum_acceptable_rssi_dbm:
                return float(power)

        return self.max_tx_power_dbm

    def _directional_angle_penalty(
        self,
        node_x: float,
        node_y: float,
        target_x: float,
        target_y: float,
        beam_direction_deg: float,
        beamwidth_deg: float,
    ) -> float:
        angle = self._angle_degrees(node_x, node_y, target_x, target_y)
        delta = abs((angle - beam_direction_deg + 180.0) % 360.0 - 180.0)
        half = beamwidth_deg / 2.0

        if delta <= half:
            return 0.0

        return min(22.0, (delta - half) / 90.0 * 18.0)

    def _estimate_capacity(
        self,
        room: Dict[str, Any],
        avg_rssi: float,
        avg_snr: float,
        expected_clients: int,
    ) -> Dict[str, Any]:
        room_type = self._room_type(room)

        if room_type == "corridor":
            max_clients = self.max_clients_per_node_corridor
        elif room_type in ["meeting", "open_area"]:
            max_clients = 22
        elif room_type == "server_room":
            max_clients = 10
        else:
            max_clients = self.max_clients_per_node_normal

        snr_factor = max(0.35, min(1.15, avg_snr / 35.0))
        rssi_factor = max(0.40, min(1.10, (avg_rssi + 85.0) / 28.0))
        effective_capacity = self.base_node_capacity_mbps * snr_factor * rssi_factor

        utilization = max(0.0, min(135.0, 100.0 * expected_clients / max(max_clients, 1)))

        return {
            "base_capacity_mbps": round(self.base_node_capacity_mbps, 2),
            "effective_capacity_mbps": round(effective_capacity, 2),
            "max_clients": max_clients,
            "expected_clients": expected_clients,
            "utilization_percent": round(utilization, 2),
            "capacity_state": self._capacity_state(utilization),
        }

    def _capacity_state(self, utilization: float) -> str:
        if utilization < 45:
            return "underutilized"
        if utilization < 75:
            return "normal"
        if utilization < 95:
            return "high_load"
        if utilization < 115:
            return "overloaded"
        return "critical"

    def _estimate_packet_loss(self, avg_rssi: float, avg_snr: float, utilization: float) -> float:
        loss = 0.4

        if avg_rssi < -72:
            loss += (-72 - avg_rssi) * 0.35
        if avg_snr < 20:
            loss += (20 - avg_snr) * 0.18
        if utilization > 80:
            loss += (utilization - 80) * 0.045

        return max(0.1, min(12.0, loss))

    def _estimate_latency_ms(self, avg_snr: float, utilization: float) -> float:
        latency = 12.0

        if avg_snr < 25:
            latency += (25 - avg_snr) * 1.2
        if utilization > 70:
            latency += (utilization - 70) * 0.65

        return max(5.0, min(180.0, latency))

    def _estimate_throughput_mbps(self, avg_rssi: float, avg_snr: float, utilization: float) -> float:
        quality = 1.0

        if avg_rssi < -60:
            quality -= min(0.45, (-60 - avg_rssi) / 45.0)
        if avg_snr < 30:
            quality -= min(0.35, (30 - avg_snr) / 45.0)
        if utilization > 65:
            quality -= min(0.35, (utilization - 65) / 100.0)

        return max(8.0, min(130.0, self.base_node_capacity_mbps * quality))

    def _estimate_power_watts(self, tx_power_dbm: float) -> float:
        normalized = (tx_power_dbm - self.min_tx_power_dbm) / max(self.max_tx_power_dbm - self.min_tx_power_dbm, 1.0)
        return round(3.2 + normalized * 4.6, 2)

    def _estimate_node_temperature(self, utilization: float) -> float:
        return round(36.0 + max(0.0, utilization - 35.0) * 0.09, 2)

    def _estimate_humidity(self, room: Dict[str, Any]) -> float:
        room_type = self._room_type(room)

        if room_type == "bathroom":
            return 62.0
        if room_type == "kitchen":
            return 55.0
        if room_type == "server_room":
            return 42.0

        return 46.0

    # ------------------------------------------------------------------
    # AI decisions
    # ------------------------------------------------------------------

    def _calculate_upgrade_degrade_status(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for node in nodes:
            cov = node.get("coverage_metrics", {})
            cap = node.get("capacity_metrics", {})
            tel = node.get("telemetry", {})

            coverage = float(cov.get("coverage_percent", 0.0))
            worst_rssi = float(cov.get("worst_rssi_dbm", -95.0))
            utilization = float(cap.get("utilization_percent", 0.0))
            packet_loss = float(tel.get("packet_loss_percent", 0.0))
            throughput = float(tel.get("throughput_mbps", 0.0))

            actions = []
            state = "normal"

            if coverage < 95.0 or worst_rssi < self.minimum_acceptable_rssi_dbm:
                actions.append("increase_tx_power_or_add_node")
                state = "coverage_degraded"

            if utilization >= 95.0:
                actions.append("upgrade_capacity_or_split_clients")
                state = "capacity_degraded"

            if packet_loss > self.packet_loss_target_percent:
                actions.append("reduce_interference_or_change_channel")
                state = "quality_degraded"

            if throughput < 90.0 and node.get("node_role") != "corridor_backbone_node":
                actions.append("check_channel_load_and_client_density")
                if state == "normal":
                    state = "throughput_warning"

            if not actions and utilization < 35.0 and coverage > 98.0:
                actions.append("possible_tx_power_reduction")
                state = "can_optimize_down"

            if not actions:
                actions.append("no_action_required")

            node["ai_decision"] = {
                "health_state": state,
                "recommended_actions": actions,
                "capacity_upgrade_required": utilization >= 95.0,
                "capacity_downgrade_possible": state == "can_optimize_down",
                "tx_power_adjustment": self._recommended_power_adjustment(node),
                "channel_adjustment": "monitor" if state == "normal" else "re-evaluate",
            }

        return nodes

    def _recommended_power_adjustment(self, node: Dict[str, Any]) -> str:
        cov = node.get("coverage_metrics", {})
        coverage = float(cov.get("coverage_percent", 0.0))
        worst = float(cov.get("worst_rssi_dbm", -95.0))
        tx = float(node.get("tx_power_dbm", self.default_tx_power_dbm))

        if coverage < 95.0 or worst < self.minimum_acceptable_rssi_dbm:
            if tx < self.max_tx_power_dbm:
                return "increase"
            return "add_node_required"

        if coverage > 99.0 and worst > -58.0 and tx > self.min_tx_power_dbm:
            return "decrease_to_reduce_leakage"

        return "keep"

    def _assign_bathroom_coverage(self, nodes: List[Dict[str, Any]], rooms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bathrooms = [r for r in rooms if self._room_type(r) == "bathroom"]

        for bathroom in bathrooms:
            bx, by = self._room_center(bathroom)
            best_node = None
            best_score = -1e9

            for node in nodes:
                node_room = self._find_room_by_id(rooms, node.get("room_id"))
                if not node_room:
                    continue

                d = math.hypot(node["x"] - bx, node["y"] - by)
                score = -d

                if self._room_type(node_room) == "corridor":
                    score += 8.0
                if node.get("node_role") == "corridor_backbone_node":
                    score += 4.0

                if score > best_score:
                    best_score = score
                    best_node = node

            if best_node:
                best_node.setdefault("secondary_coverage_rooms", [])
                best_node["secondary_coverage_rooms"].append(
                    {
                        "room_id": bathroom.get("id"),
                        "room_name": bathroom.get("name", "Bathroom"),
                        "room_type": "bathroom",
                        "coverage_reason": "Bathroom has no internal node; coverage is assigned from corridor/nearest StructFi node.",
                    }
                )

        return nodes

    def _normalize_plan_nodes_output(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Make planner output stable for dashboard, simulator, mobile API, and Pydantic models.

        Canonical fields:
        - id: int
        - node_id: string display id
        - name
        - x/y
        - tx_power
        - antenna_beamwidth
        - channel
        Extra legacy fields are kept for compatibility.
        """
        normalized: List[Dict[str, Any]] = []

        for idx, node in enumerate(nodes, start=1):
            original_display_id = node.get("node_id") or node.get("id") or f"SF-N{idx:03d}"
            display_id = str(original_display_id)
            if not display_id.startswith("SF-N"):
                display_id = f"SF-N{idx:03d}"

            tx_power = int(round(float(node.get("tx_power", node.get("tx_power_dbm", self.default_tx_power_dbm)) or self.default_tx_power_dbm)))
            beamwidth = int(round(float(node.get("antenna_beamwidth", node.get("beamwidth_deg", node.get("beam_width_deg", self.default_beamwidth_deg))) or self.default_beamwidth_deg)))
            direction = float(node.get("beam_direction_deg", node.get("antenna_direction_deg", node.get("direction_deg", 0.0))) or 0.0)

            placement_type = node.get("placement_type")
            if placement_type not in ["corner", "wall_mid", "ceiling_like", "hallway_edge", "fallback"]:
                placement_type = "hallway_edge" if str(node.get("node_role", "")).lower() == "corridor_backbone_node" else "corner"

            antenna_direction = "sectorized"
            if beamwidth >= 300:
                antenna_direction = "omni_balanced"
            elif abs(direction % 180.0) < 30.0:
                antenna_direction = "horizontal_bias"
            elif abs((direction - 90.0) % 180.0) < 30.0:
                antenna_direction = "vertical_bias"

            node["id"] = idx
            node["node_id"] = display_id
            node["name"] = f"Node {display_id}"
            node["tx_power"] = tx_power
            node["tx_power_dbm"] = tx_power
            node["antenna_beamwidth"] = beamwidth
            node["beamwidth_deg"] = beamwidth
            node["beam_width_deg"] = beamwidth
            node["beam_direction_deg"] = round(direction % 360.0, 2)
            node["antenna_direction_deg"] = round(direction % 360.0, 2)
            node["placement_type"] = placement_type
            node["antenna_direction"] = antenna_direction
            node["status"] = "planned"

            coverage_metrics = node.get("coverage_metrics", {}) or {}
            capacity_metrics = node.get("capacity_metrics", {}) or {}
            telemetry = node.get("telemetry", {}) or {}

            node["coverage"] = {
                "room_coverage_score": round(float(coverage_metrics.get("coverage_percent", 0.0)), 2),
                "nearby_overlap_score": round(float(node.get("overlap_score", 0.0) or 0.0), 2),
                "estimated_rssi_center": round(float(coverage_metrics.get("avg_rssi_dbm", telemetry.get("rssi_dbm", -65.0))), 2),
                "estimated_snr_center": round(float(coverage_metrics.get("avg_snr_db", telemetry.get("snr_db", 25.0))), 2),
            }
            node["capacity"] = {
                "projected_clients": int(capacity_metrics.get("expected_clients", telemetry.get("connected_clients", 0)) or 0),
                "projected_capacity_mbps": round(float(capacity_metrics.get("effective_capacity_mbps", 0.0) or 0.0), 2),
                "projected_utilization_pct": round(float(capacity_metrics.get("utilization_percent", 0.0) or 0.0), 2),
                "retry_risk_score": round(float(telemetry.get("packet_loss_percent", 0.0) or 0.0), 2),
            }
            node["interference"] = {
                "channel_cost": 0.0,
                "interference_score": round(float(telemetry.get("packet_loss_percent", 0.0) or 0.0), 2),
                "cochannel_risk": 0.0,
                "adjacent_channel_risk": 0.0,
            }
            node["cable_route"] = {
                "path_type": "corridor_route" if str(node.get("node_role", "")).lower() == "corridor_backbone_node" else "direct",
                "length_m": 0.0,
                "estimated_cost": 0.0,
                "path_points": [],
            }
            node["placement_score"] = round(float(coverage_metrics.get("coverage_percent", 85.0) or 85.0), 2)
            node["notes"] = [node.get("placement_reason", "StructFi planned node.")]

            normalized.append(node)

        return normalized

    # ------------------------------------------------------------------
    # Profiles / routes / summary
    # ------------------------------------------------------------------

    def _assign_channels(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for i, node in enumerate(nodes):
            node["channel"] = self.channels_5ghz[i % len(self.channels_5ghz)]
            node["band"] = "5GHz"
            node["wifi_standard"] = "IEEE 802.11ax/ac"
            node["roaming"] = {
                "enabled": True,
                "standard": "IEEE 802.11r",
                "target_handover_latency_ms": self.roaming_latency_target_ms,
            }
        return nodes

    def _build_vlan_profiles(self) -> List[Dict[str, Any]]:
        return [
            {
                "vlan_id": 10,
                "name": "Management",
                "zone": "management",
                "zone_role": "management",
                "subnet": "192.168.10.0/24",
                "gateway": "192.168.10.1",
                "dhcp_enabled": True,
                "access_level": "admin",
                "description": "Controller, admins, monitoring dashboard, IDS, and privileged devices.",
                "allowed_zones": ["management", "staff", "service"],
                "security": "WPA3-Enterprise + RADIUS",
            },
            {
                "vlan_id": 20,
                "name": "Staff",
                "zone": "staff",
                "zone_role": "staff",
                "subnet": "192.168.20.0/24",
                "gateway": "192.168.20.1",
                "dhcp_enabled": True,
                "access_level": "staff",
                "description": "Internal staff and trusted lab/classroom devices.",
                "allowed_zones": ["staff", "service"],
                "security": "WPA3-Enterprise + RADIUS",
            },
            {
                "vlan_id": 30,
                "name": "Guest",
                "zone": "guest",
                "zone_role": "guest",
                "subnet": "192.168.30.0/24",
                "gateway": "192.168.30.1",
                "dhcp_enabled": True,
                "access_level": "guest",
                "description": "Internet-only isolated guest access.",
                "allowed_zones": ["internet", "guest", "reception", "corridor"],
                "security": "Captive portal / isolated VLAN",
            },
        ]

    def _build_ssid_profiles(self) -> List[Dict[str, Any]]:
        return [
            {
                "ssid_name": "StructFi-Staff",
                "ssid": "StructFi-Staff",
                "security_mode": "WPA3-Enterprise",
                "security": "WPA3-Enterprise",
                "vlan_id": 20,
                "fast_roaming_enabled": True,
                "radius_enabled": True,
                "roaming_80211r": True,
            },
            {
                "ssid_name": "StructFi-Management",
                "ssid": "StructFi-Management",
                "security_mode": "WPA3-Enterprise",
                "security": "WPA3-Enterprise",
                "vlan_id": 10,
                "fast_roaming_enabled": True,
                "radius_enabled": True,
                "roaming_80211r": True,
                "hidden": True,
            },
            {
                "ssid_name": "StructFi-Guest",
                "ssid": "StructFi-Guest",
                "security_mode": "Open",
                "security": "Captive Portal",
                "vlan_id": 30,
                "fast_roaming_enabled": False,
                "radius_enabled": False,
                "client_isolation": True,
            },
        ]

    def _build_cable_routes(self, nodes: List[Dict[str, Any]], building: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not nodes:
            return []

        rooms = building.get("rooms", [])
        controller_room = self._find_room_by_id(rooms, building.get("controller_zone_candidate_room_id"))

        if controller_room:
            cx, cy = self._room_center(controller_room)
        else:
            bounds = building.get("bounds", {})
            cx = float(bounds.get("min_x", 0.0)) + float(bounds.get("width", 10.0)) * 0.5
            cy = float(bounds.get("min_y", 0.0)) + float(bounds.get("height", 10.0)) * 0.5

        routes = []

        for node in nodes:
            length = math.hypot(node["x"] - cx, node["y"] - cy)
            routes.append(
                {
                    "node_id": node["id"],
                    "from": "central_controller",
                    "to": node["id"],
                    "controller_x": round(cx, 3),
                    "controller_y": round(cy, 3),
                    "node_x": round(node["x"], 3),
                    "node_y": round(node["y"], 3),
                    "estimated_cable_length_m": round(length * 1.18, 2),
                    "medium": "PoE Ethernet",
                    "standard": "IEEE 802.3af/at",
                }
            )

        return routes

    def _build_summary(self, building: Dict[str, Any], rooms: List[Dict[str, Any]], nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not nodes:
            return {
                "status": "failed",
                "target_met": False,
                "reason": "No nodes planned.",
                "warnings": ["No nodes planned."],
            }

        coverage_values = [float(n.get("coverage_metrics", {}).get("coverage_percent", 0.0)) for n in nodes]
        rssi_values = [float(n.get("coverage_metrics", {}).get("avg_rssi_dbm", -95.0)) for n in nodes]
        loss_values = [float(n.get("telemetry", {}).get("packet_loss_percent", 10.0)) for n in nodes]
        throughput_values = [float(n.get("telemetry", {}).get("throughput_mbps", 0.0)) for n in nodes]
        utilization_values = [float(n.get("capacity_metrics", {}).get("utilization_percent", 0.0)) for n in nodes]

        bathrooms = [r for r in rooms if self._room_type(r) == "bathroom"]
        corridors = [r for r in rooms if self._room_type(r) == "corridor"]
        non_bathroom = [r for r in rooms if self._room_type(r) != "bathroom"]

        rooms_with_nodes = {int(n.get("room_id")) for n in nodes if n.get("room_id") is not None}

        missing_node_rooms = [
            {
                "room_id": r.get("id"),
                "room_name": r.get("name"),
                "room_type": self._room_type(r),
            }
            for r in non_bathroom
            if int(r.get("id")) not in rooms_with_nodes
        ]

        degraded_nodes = [
            n["id"]
            for n in nodes
            if n.get("ai_decision", {}).get("health_state") not in ["normal", "can_optimize_down"]
        ]

        avg_coverage = sum(coverage_values) / max(len(coverage_values), 1)
        avg_rssi = sum(rssi_values) / max(len(rssi_values), 1)
        avg_loss = sum(loss_values) / max(len(loss_values), 1)
        avg_throughput = sum(throughput_values) / max(len(throughput_values), 1)
        avg_utilization = sum(utilization_values) / max(len(utilization_values), 1)

        target_met = (
            avg_coverage >= 95.0
            and avg_loss <= self.packet_loss_target_percent
            and avg_throughput >= 90.0
            and len(missing_node_rooms) == 0
        )

        warnings = []
        if avg_coverage < 95.0:
            warnings.append("Average coverage is below StructFi target 95-99%.")
        if avg_loss > self.packet_loss_target_percent:
            warnings.append("Average packet loss exceeds target <3%.")
        if avg_throughput < 90.0:
            warnings.append("Average throughput is below target 90-110 Mbps.")
        if missing_node_rooms:
            warnings.append("Some non-bathroom rooms do not have nodes.")
        if degraded_nodes:
            warnings.append("Some nodes are degraded and require review.")
        if not warnings:
            warnings.append("Planning output meets the main StructFi constraints.")

        coverage_score = round(avg_coverage, 2)
        speed_score = round(max(0.0, min(100.0, avg_throughput / 110.0 * 100.0)), 2)
        placement_score = round(max(0.0, min(100.0, coverage_score - len(missing_node_rooms) * 8.0 - len(degraded_nodes) * 4.0)), 2)
        wall_penalty_score = round(max(0.0, min(100.0, 100.0 - max(0.0, -62.0 - avg_rssi) * 2.0)), 2)
        channel_reuse_score = round(max(0.0, min(100.0, 100.0 - max(0, len(nodes) - len(set(n.get("channel") for n in nodes))) * 4.0)), 2)
        capacity_score = round(max(0.0, min(100.0, 100.0 - max(0.0, avg_utilization - 75.0) * 1.2)), 2)
        estimated_dead_zones = len(missing_node_rooms) + sum(1 for v in coverage_values if v < 90.0)

        return {
            "status": "ok" if target_met else "needs_review",
            "target_met": target_met,
            "building_file": building.get("file_name", "unknown"),
            "node_count": len(nodes),
            "nodes_planned": len(nodes),
            "total_rooms": len(rooms),
            "non_bathroom_rooms": len(non_bathroom),
            "bathrooms": len(bathrooms),
            "corridors": len(corridors),
            "coverage_score": coverage_score,
            "speed_score": speed_score,
            "placement_score": placement_score,
            "wall_penalty_score": wall_penalty_score,
            "channel_reuse_score": channel_reuse_score,
            "capacity_score": capacity_score,
            "estimated_dead_zones": estimated_dead_zones,
            "room_node_rule": "Every non-bathroom room must have at least one node.",
            "bathroom_rule": "Bathrooms have no node and are covered by corridor/nearest nodes.",
            "avg_coverage_percent": round(avg_coverage, 2),
            "avg_rssi_dbm": round(avg_rssi, 2),
            "avg_packet_loss_percent": round(avg_loss, 2),
            "avg_throughput_mbps": round(avg_throughput, 2),
            "avg_utilization_percent": round(avg_utilization, 2),
            "missing_node_rooms": missing_node_rooms,
            "degraded_nodes": degraded_nodes,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Node builder
    # ------------------------------------------------------------------

    def _make_node(
        self,
        room: Dict[str, Any],
        x: float,
        y: float,
        sequence: int,
        node_role: str,
        beam_direction_deg: float,
        beamwidth_deg: float,
        tx_power_dbm: float,
        placement_reason: str,
    ) -> Dict[str, Any]:
        room_id = int(room.get("id", 0))
        node_id = f"SF-N{room_id:03d}-{sequence}"

        return {
            "id": node_id,
            "node_id": node_id,
            "name": f"StructFi Node {room_id}-{sequence}",
            "room_id": room_id,
            "room_name": room.get("name", f"Room {room_id}"),
            "room_type": self._room_type(room),
            "zone": room.get("zone", "staff"),
            "node_role": node_role,
            "hardware_profile": "ESP32-S3 embedded directional StructFi node",
            "x": round(float(x), 4),
            "y": round(float(y), 4),
            "mounting": {
                "type": "in-wall-corner",
                "height_m": 1.6,
                "housing_size_cm": "15x15",
                "installation_note": "Node is placed near wall/corner, not at room center.",
            },
            "antenna": {
                "type": "directional",
                "beam_direction_deg": round(float(beam_direction_deg) % 360.0, 2),
                "beamwidth_deg": round(float(beamwidth_deg), 2),
                "polarization": "vertical",
            },
            "beam_direction_deg": round(float(beam_direction_deg) % 360.0, 2),
            "beamwidth_deg": round(float(beamwidth_deg), 2),
            "tx_power_dbm": round(float(tx_power_dbm), 2),
            "placement_reason": placement_reason,
            "secondary_coverage_rooms": [],
        }

    def _placement_reason(self, room: Dict[str, Any], tx_power: float, nodes_needed: int) -> str:
        text = (
            "Corner-based directional placement selected to cover the room interior "
            "while reducing leakage outside the room."
        )

        if nodes_needed > 1:
            text += " Room is large/long enough to require multiple nodes."

        if self._room_type(room) == "server_room":
            text += " Server/control room has higher reliability priority."

        text += f" Estimated fitted TX power: {tx_power:.1f} dBm."
        return text

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _room_type(self, room: Dict[str, Any]) -> str:
        return str(room.get("room_type", "unknown") or "unknown").lower().strip()

    def _room_center(self, room: Dict[str, Any]) -> Tuple[float, float]:
        if room.get("center_x") is not None and room.get("center_y") is not None:
            return float(room.get("center_x")), float(room.get("center_y"))

        x = float(room.get("x", 0.0))
        y = float(room.get("y", 0.0))
        w = float(room.get("width", 1.0))
        h = float(room.get("height", 1.0))
        return x + w / 2.0, y + h / 2.0

    def _room_corners(self, room: Dict[str, Any]) -> List[Tuple[float, float]]:
        polygon = room.get("polygon") or []
        points = []

        for p in polygon:
            try:
                points.append((float(p.get("x", 0.0)), float(p.get("y", 0.0))))
            except Exception:
                pass

        if len(points) >= 3:
            return points

        return self._fallback_corners(room)

    def _fallback_corners(self, room: Dict[str, Any]) -> List[Tuple[float, float]]:
        x = float(room.get("x", 0.0))
        y = float(room.get("y", 0.0))
        w = max(float(room.get("width", 1.0)), 0.1)
        h = max(float(room.get("height", 1.0)), 0.1)

        return [
            (x, y),
            (x + w, y),
            (x + w, y + h),
            (x, y + h),
        ]

    def _balanced_single_room_node_position(self, room: Dict[str, Any], corner_x: float, corner_y: float) -> Tuple[float, float]:
        """
        For small/one-node rooms, avoid placing the node too tightly in the corner.
        This makes the visual and calculated coverage represent the full room area better.
        """
        room_type = self._room_type(room)
        area = max(float(room.get("area", 0.0) or 0.0), 0.1)
        expected = int(room.get("expected_clients", 0) or 0)
        w = max(float(room.get("width", 1.0)), 0.1)
        h = max(float(room.get("height", 1.0)), 0.1)

        if room_type in ["corridor", "open_area", "meeting"]:
            inset_ratio = 0.10
        elif expected <= 1 or area <= 14.0 or min(w, h) <= 2.4:
            inset_ratio = 0.20
        else:
            inset_ratio = 0.12

        return self._move_point_inside_room(room, corner_x, corner_y, inset_ratio=inset_ratio)

    def _single_node_room_beamwidth(self, room: Dict[str, Any], default_beamwidth: float) -> float:
        """
        Give one-node rooms a slightly wider sector so Exp1/small rooms are covered
        visually and numerically as a whole room, not as a tiny corner sector.
        """
        room_type = self._room_type(room)
        area = max(float(room.get("area", 0.0) or 0.0), 0.1)
        expected = int(room.get("expected_clients", 0) or 0)
        w = max(float(room.get("width", 1.0)), 0.1)
        h = max(float(room.get("height", 1.0)), 0.1)
        aspect = max(w, h) / max(min(w, h), 0.1)

        if room_type == "corridor":
            return 130.0
        if room_type in ["open_area", "meeting"]:
            return max(default_beamwidth, 105.0)
        if expected <= 1 or area <= 14.0 or min(w, h) <= 2.4:
            return max(default_beamwidth, 115.0)
        if aspect >= 2.0:
            return max(default_beamwidth, 100.0)

        return max(default_beamwidth, 90.0)

    def _move_point_inside_room(self, room: Dict[str, Any], x: float, y: float, inset_ratio: float = 0.08) -> Tuple[float, float]:
        cx, cy = self._room_center(room)
        w = max(float(room.get("width", 1.0)), 0.1)
        h = max(float(room.get("height", 1.0)), 0.1)
        inset = max(0.15, min(w, h) * inset_ratio)

        dx = cx - x
        dy = cy - y
        length = max(math.hypot(dx, dy), 1e-9)

        nx = x + dx / length * inset
        ny = y + dy / length * inset

        return self._clamp_point_to_room(room, nx, ny)

    def _clamp_point_to_room(self, room: Dict[str, Any], x: float, y: float) -> Tuple[float, float]:
        rx = float(room.get("x", 0.0))
        ry = float(room.get("y", 0.0))
        rw = max(float(room.get("width", 1.0)), 0.1)
        rh = max(float(room.get("height", 1.0)), 0.1)

        margin = min(0.20, rw * 0.15, rh * 0.15)
        x = max(rx + margin, min(rx + rw - margin, x))
        y = max(ry + margin, min(ry + rh - margin, y))

        return float(x), float(y)

    def _sample_points_in_room(self, room: Dict[str, Any], target_count: int = 25) -> List[Tuple[float, float]]:
        x = float(room.get("x", 0.0))
        y = float(room.get("y", 0.0))
        w = max(float(room.get("width", 1.0)), 0.1)
        h = max(float(room.get("height", 1.0)), 0.1)

        grid = max(3, int(math.sqrt(target_count)))
        samples = []

        for i in range(grid):
            for j in range(grid):
                px = x + w * (i + 0.5) / grid
                py = y + h * (j + 0.5) / grid

                if self._point_inside_room(room, px, py):
                    samples.append((px, py))

        if not samples:
            samples.append(self._room_center(room))

        return samples

    def _point_inside_room(self, room: Dict[str, Any], px: float, py: float) -> bool:
        polygon = room.get("polygon") or []

        if len(polygon) >= 3:
            points = []
            for p in polygon:
                points.append((float(p.get("x", 0.0)), float(p.get("y", 0.0))))
            return self._point_in_polygon(px, py, points)

        x = float(room.get("x", 0.0))
        y = float(room.get("y", 0.0))
        w = float(room.get("width", 1.0))
        h = float(room.get("height", 1.0))

        return x <= px <= x + w and y <= py <= y + h

    def _point_in_polygon(self, x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
        if len(polygon) < 3:
            return False

        inside = False
        j = len(polygon) - 1

        for i in range(len(polygon)):
            xi, yi = polygon[i]
            xj, yj = polygon[j]

            if ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            ):
                inside = not inside

            j = i

        return inside

    def _angle_degrees(self, x1: float, y1: float, x2: float, y2: float) -> float:
        return (math.degrees(math.atan2(y2 - y1, x2 - x1)) + 360.0) % 360.0

    def _beamwidth_for_room(self, room: Dict[str, Any]) -> float:
        room_type = self._room_type(room)

        if room_type == "corridor":
            return self.corridor_beamwidth_deg
        if room_type == "open_area":
            return self.open_area_beamwidth_deg
        if room_type in ["storage", "service", "server_room"]:
            return self.service_beamwidth_deg
        if room_type == "meeting":
            return 80.0

        return self.default_beamwidth_deg

    def _count_walls_between(self, x1: float, y1: float, x2: float, y2: float, walls: List[Dict[str, Any]]) -> int:
        count = 0

        for wall in walls:
            wx1 = float(wall.get("x1", 0.0))
            wy1 = float(wall.get("y1", 0.0))
            wx2 = float(wall.get("x2", 0.0))
            wy2 = float(wall.get("y2", 0.0))

            if self._segments_intersect(x1, y1, x2, y2, wx1, wy1, wx2, wy2):
                count += 1

        return min(count, 6)

    def _segments_intersect(
        self,
        ax: float,
        ay: float,
        bx: float,
        by: float,
        cx: float,
        cy: float,
        dx: float,
        dy: float,
    ) -> bool:
        def orient(px, py, qx, qy, rx, ry):
            return (qy - py) * (rx - qx) - (qx - px) * (ry - qy)

        o1 = orient(ax, ay, bx, by, cx, cy)
        o2 = orient(ax, ay, bx, by, dx, dy)
        o3 = orient(cx, cy, dx, dy, ax, ay)
        o4 = orient(cx, cy, dx, dy, bx, by)

        return (o1 * o2 < 0) and (o3 * o4 < 0)

    def _estimate_leakage_penalty(self, room: Dict[str, Any], px: float, py: float, all_rooms: List[Dict[str, Any]]) -> float:
        penalty = 0.0
        room_id = room.get("id")

        for other in all_rooms:
            if other.get("id") == room_id:
                continue

            ox, oy = self._room_center(other)
            distance = max(math.hypot(px - ox, py - oy), 0.5)

            if distance < 4.0:
                penalty += (4.0 - distance) / 4.0

            if self._room_type(other) in ["bathroom", "service", "storage"]:
                penalty *= 0.8

        return penalty

    def _corridor_or_doorway_bonus(self, room: Dict[str, Any], px: float, py: float, all_rooms: List[Dict[str, Any]]) -> float:
        bonus = 0.0

        for other in all_rooms:
            if other.get("id") == room.get("id"):
                continue

            if self._room_type(other) != "corridor":
                continue

            ox, oy = self._room_center(other)
            distance = math.hypot(px - ox, py - oy)

            if distance < 4.0:
                bonus += (4.0 - distance) / 4.0

        return bonus

    def _count_nearby_bathrooms(self, corridor: Dict[str, Any], rooms: List[Dict[str, Any]]) -> int:
        cx, cy = self._room_center(corridor)
        count = 0

        for room in rooms:
            if self._room_type(room) != "bathroom":
                continue

            rx, ry = self._room_center(room)

            if math.hypot(cx - rx, cy - ry) <= 8.0:
                count += 1

        return count

    def _count_nearby_non_bathroom_rooms(self, corridor: Dict[str, Any], rooms: List[Dict[str, Any]]) -> int:
        cx, cy = self._room_center(corridor)
        count = 0

        for room in rooms:
            if room.get("id") == corridor.get("id"):
                continue

            if self._room_type(room) == "bathroom":
                continue

            rx, ry = self._room_center(room)

            if math.hypot(cx - rx, cy - ry) <= 10.0:
                count += 1

        return count

    # ------------------------------------------------------------------
    # Room normalization
    # ------------------------------------------------------------------

    def _normalize_rooms(self, rooms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []

        for room in rooms:
            r = dict(room)

            if not r.get("area"):
                r["area"] = float(r.get("width", 1.0)) * float(r.get("height", 1.0))

            if r.get("center_x") is None:
                r["center_x"] = float(r.get("x", 0.0)) + float(r.get("width", 1.0)) / 2.0

            if r.get("center_y") is None:
                r["center_y"] = float(r.get("y", 0.0)) + float(r.get("height", 1.0)) / 2.0

            if not r.get("room_type"):
                r["room_type"] = "office"

            if not r.get("zone"):
                r["zone"] = "staff"

            if r.get("expected_clients") is None:
                r["expected_clients"] = self._default_expected_clients(r)

            normalized.append(r)

        return normalized

    def _average_normal_room_area(self, rooms: List[Dict[str, Any]]) -> float:
        areas = [
            float(r.get("area", 0.0))
            for r in rooms
            if self._room_type(r) not in ["bathroom", "corridor"]
            and float(r.get("area", 0.0)) > 0
        ]

        if not areas:
            return 25.0

        return sum(areas) / len(areas)

    def _default_expected_clients(self, room: Dict[str, Any]) -> int:
        area = max(float(room.get("area", 0.0)), 0.1)
        room_type = self._room_type(room)

        if room_type == "bathroom":
            return 0
        if room_type == "corridor":
            return max(1, int(round(area / 20.0)))
        if room_type == "meeting":
            return max(4, int(round(area / 3.0)))
        if room_type == "open_area":
            return max(8, int(round(area / 4.5)))
        if room_type in ["storage", "service"]:
            return max(0, int(round(area / 18.0)))

        return max(1, int(round(area / 7.0)))

    def _find_room_by_id(self, rooms: List[Dict[str, Any]], room_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rid = int(room_id)
        except Exception:
            return None

        for room in rooms:
            try:
                if int(room.get("id")) == rid:
                    return room
            except Exception:
                continue

        return None

    # ------------------------------------------------------------------
    # File IO
    # ------------------------------------------------------------------

    def _load_latest_building(self) -> Dict[str, Any]:
        if not self.latest_building_path.exists():
            raise FileNotFoundError(
                "latest_building.json was not found. Run Extract Rooms before AI Planning."
            )

        return json.loads(self.latest_building_path.read_text(encoding="utf-8"))

    def _save_latest_plan(self, result: Dict[str, Any]) -> None:
        self.latest_plan_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _empty_plan(self, building: Dict[str, Any], reason: str) -> Dict[str, Any]:
        file_name = building.get("file_name", "unknown")
        vlan_plan = self._build_vlan_profiles()
        ssid_profiles = self._build_ssid_profiles()

        return {
            "project": "StructFi",
            "planner_version": "unified-backend-demo-v4",
            "file_name": file_name,
            "source_file": file_name,
            "source_format": building.get("source_format", "UNKNOWN"),
            "building": building,
            "bounds": building.get("bounds", {}),
            "rooms_count": 0,
            "nodes_count": 0,
            "node_plan": [],
            "nodes": [],
            "rooms": [],
            "walls": building.get("walls", []),
            "labels": building.get("labels", []),
            "cable_routes": [],
            "ssid_profiles": ssid_profiles,
            "vlan_plan": vlan_plan,
            "vlan_profiles": vlan_plan,
            "summary": {
                "status": "failed",
                "target_met": False,
                "node_count": 0,
                "coverage_score": 0.0,
                "speed_score": 0.0,
                "placement_score": 0.0,
                "wall_penalty_score": 0.0,
                "channel_reuse_score": 0.0,
                "capacity_score": 0.0,
                "estimated_dead_zones": 0,
                "reason": reason,
                "warnings": [reason],
            },
            "status": "failed",
        }


CADPlanner = AdvancedCADPlanner
StructFiCADPlanner = AdvancedCADPlanner
StructFiPlanner = AdvancedCADPlanner