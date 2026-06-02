from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.entities import ControllerDecision
from app.services.segmentation import NetworkSegmentation


class NetworkController:
    """
    StructFi centralized controller helper.

    This controller is intentionally rule-based for the graduation prototype. It
    translates live telemetry into clear controller decisions that can be shown
    in the dashboard and defended in the report: rebalance clients, change
    channel, adjust TX power, mark degraded nodes, and raise operational alerts.
    """

    def __init__(self):
        self.segmentation = NetworkSegmentation()
        self.high_load_threshold = 7
        self.critical_load_threshold = 10
        self.low_rssi_threshold_dbm = -72.0
        self.low_snr_threshold_db = 18.0
        self.high_retry_threshold_pct = 18.0
        self.high_packet_loss_threshold_pct = 12.0
        self.channels_5ghz = [36, 40, 44, 48, 149, 153, 157, 161]

    def analyze_nodes(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        decisions: List[Dict[str, Any]] = []

        for index, node in enumerate(nodes or [], start=1):
            node_id = self._node_id(node, index)
            status = str(node.get("status", node.get("health_state", "online"))).lower()
            channel = self._safe_int(
                node.get("channel", self._nested(node, "radio", "current_channel", default=36)),
                36,
            )
            load = self._safe_int(
                node.get("load", node.get("current_load", node.get("connected_clients", 0))),
                0,
            )
            rssi = self._safe_float(
                node.get("rssi_avg", self._nested(node, "radio", "rssi_avg", default=-60.0)),
                -60.0,
            )
            snr = self._safe_float(
                node.get("snr_avg", self._nested(node, "radio", "snr_avg", default=30.0)),
                30.0,
            )
            retry = self._safe_float(
                node.get("retry_rate_pct", self._nested(node, "radio", "retry_rate_pct", default=0.0)),
                0.0,
            )
            packet_loss = self._safe_float(
                node.get("packet_loss_pct", self._nested(node, "radio", "packet_loss_pct", default=0.0)),
                0.0,
            )
            tx_power = self._safe_float(
                node.get("tx_power_dbm", self._nested(node, "radio", "tx_power_dbm", default=18.0)),
                18.0,
            )

            if status in ["down", "offline"]:
                decisions.append(
                    self._decision(
                        node_id=node_id,
                        action="raise_alert",
                        value="offline",
                        reason="Node is offline; controller should move clients to neighboring nodes and flag maintenance.",
                    )
                )
                continue

            if load >= self.critical_load_threshold:
                decisions.append(
                    self._decision(
                        node_id=node_id,
                        action="rebalance_load",
                        value="force_neighbor_selection",
                        reason=f"Critical load detected: {load} connected clients.",
                    )
                )
            elif load >= self.high_load_threshold:
                decisions.append(
                    self._decision(
                        node_id=node_id,
                        action="rebalance_load",
                        value="prefer_neighbor_nodes",
                        reason=f"High load detected: {load} connected clients.",
                    )
                )

            if retry >= self.high_retry_threshold_pct:
                new_channel = self._next_channel(channel)
                decisions.append(
                    self._decision(
                        node_id=node_id,
                        action="change_channel",
                        value=str(new_channel),
                        reason=f"Retry rate {retry}% suggests interference or contention on channel {channel}.",
                    )
                )

            if rssi < self.low_rssi_threshold_dbm and tx_power < 20:
                decisions.append(
                    self._decision(
                        node_id=node_id,
                        action="change_tx_power",
                        value="+2 dBm",
                        reason=f"Weak average RSSI detected: {rssi} dBm.",
                    )
                )
            elif rssi > -52 and load <= 2 and tx_power > 10:
                decisions.append(
                    self._decision(
                        node_id=node_id,
                        action="change_tx_power",
                        value="-1 dBm",
                        reason="Strong RSSI with low load; reduce leakage and co-channel interference.",
                    )
                )

            if snr < self.low_snr_threshold_db:
                decisions.append(
                    self._decision(
                        node_id=node_id,
                        action="mark_degraded",
                        value="low_snr",
                        reason=f"Average SNR is below target: {snr} dB.",
                    )
                )

            if packet_loss >= self.high_packet_loss_threshold_pct:
                decisions.append(
                    self._decision(
                        node_id=node_id,
                        action="mark_degraded",
                        value="packet_loss",
                        reason=f"Packet loss is above threshold: {packet_loss}%.",
                    )
                )

        if not decisions:
            decisions.append(
                self._decision(
                    node_id=None,
                    action="none",
                    value="stable",
                    reason="All monitored nodes are within controller thresholds.",
                )
            )

        return decisions

    def evaluate_access(self, clients):
        access_results = []

        for client in clients:
            role = getattr(client, "role", None)
            client_id = getattr(client, "id", None)
            client_name = getattr(client, "name", "Client")
            targets = ["internet", "staff", "management", "controller"]

            for target in targets:
                allowed = self.segmentation.is_allowed(role, target)
                access_results.append({
                    "client_id": client_id,
                    "client_name": client_name,
                    "role": role,
                    "target_zone": target,
                    "allowed": allowed,
                    "reason": "Policy allows access" if allowed else "Policy blocks access",
                })

        return access_results

    def _decision(self, node_id: Optional[int], action: str, value: str, reason: str) -> Dict[str, Any]:
        try:
            return ControllerDecision(
                node_id=node_id,
                action=action,
                value=value,
                reason=reason,
            ).model_dump()
        except Exception:
            return {
                "node_id": node_id,
                "action": action,
                "value": value,
                "reason": reason,
            }

    def _next_channel(self, current: int) -> int:
        if current not in self.channels_5ghz:
            return self.channels_5ghz[0]
        return self.channels_5ghz[(self.channels_5ghz.index(current) + 1) % len(self.channels_5ghz)]

    def _node_id(self, node: Dict[str, Any], default: int) -> int:
        return self._safe_int(node.get("id", node.get("node_id", default)), default)

    def _nested(self, source: Dict[str, Any], parent: str, child: str, default: Any = None) -> Any:
        value = source.get(parent)
        if isinstance(value, dict):
            return value.get(child, default)
        return default

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            text = str(value)
            if text.startswith("SF-N"):
                text = text.split("N")[-1].split("-")[0]
            return int(float(text))
        except Exception:
            return default

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default
