from __future__ import annotations

from typing import Any, List, Optional

from app.models.simulation_models import (
    AIHealthSummaryModel,
    AIOutputModel,
    AIRecommendationModel,
)
from app.models.telemetry_models import NodeRuntimeModel
from app.models.security_models import SecurityAlertModel


class StructiFiAIEngine:
    """
    StructFi AI monitoring and recommendation engine.

    Purpose for the graduation demo:
    - Analyze live node telemetry from the simulator.
    - Explain Wi-Fi health in a simple AI summary.
    - Recommend actions for channel interference, weak signal, packet loss,
      overload, node failure, and security isolation events.
    - Stay compatible with Pydantic models and dict payloads.
    """

    def __init__(self) -> None:
        self.high_load_threshold = 7
        self.warning_load_threshold = 5
        self.weak_rssi_threshold = -72.0
        self.poor_snr_threshold = 18.0
        self.high_retry_threshold = 18.0
        self.high_packet_loss_threshold = 10.0
        self.high_latency_threshold = 90.0
        self.low_throughput_threshold = 25.0

    def evaluate(
        self,
        nodes: List[NodeRuntimeModel],
        alerts: List[SecurityAlertModel],
    ) -> AIOutputModel:
        health = self._build_health_summary(nodes, alerts)
        recommendations = self._build_recommendations(nodes, alerts, health)
        recommendations = self._dedupe_recommendations(recommendations)

        return AIOutputModel(
            health_summary=health,
            recommendations=recommendations[:12],
        )

    # ------------------------------------------------------------------
    # Health summary
    # ------------------------------------------------------------------

    def _build_health_summary(
        self,
        nodes: List[NodeRuntimeModel],
        alerts: List[SecurityAlertModel],
    ) -> AIHealthSummaryModel:
        critical_alerts = sum(1 for a in alerts if self._get(a, "severity", "") == "critical")
        warning_alerts = sum(1 for a in alerts if self._get(a, "severity", "") == "warning")

        down_nodes = 0
        degraded_nodes = 0
        high_load_nodes = 0
        weak_signal_nodes = 0
        quality_problem_nodes = 0

        for node in nodes:
            status = str(self._get(node, "status", "unknown")).lower()
            load = int(self._get(node, "current_load", 0) or 0)
            radio = self._get(node, "radio", {}) or {}

            rssi = float(self._get(radio, "rssi_avg", -45.0) or -45.0)
            snr = float(self._get(radio, "snr_avg", 35.0) or 35.0)
            retry = float(self._get(radio, "retry_rate_pct", 0.0) or 0.0)
            packet_loss = float(self._get(radio, "packet_loss_pct", 0.0) or 0.0)
            latency = float(self._get(radio, "latency_ms", 0.0) or 0.0)

            if status in ["offline", "down"]:
                down_nodes += 1
            elif status == "degraded":
                degraded_nodes += 1

            if load >= self.high_load_threshold:
                high_load_nodes += 1

            if rssi <= self.weak_rssi_threshold or snr <= self.poor_snr_threshold:
                weak_signal_nodes += 1

            if (
                retry >= self.high_retry_threshold
                or packet_loss >= self.high_packet_loss_threshold
                or latency >= self.high_latency_threshold
            ):
                quality_problem_nodes += 1

        anomaly_score = 0.0
        anomaly_score += critical_alerts * 22.0
        anomaly_score += warning_alerts * 8.0
        anomaly_score += down_nodes * 24.0
        anomaly_score += degraded_nodes * 13.0
        anomaly_score += high_load_nodes * 8.5
        anomaly_score += weak_signal_nodes * 7.0
        anomaly_score += quality_problem_nodes * 9.0

        anomaly_score = min(100.0, round(anomaly_score, 2))

        if anomaly_score >= 60.0 or critical_alerts > 0 or down_nodes > 0:
            status = "critical"
        elif anomaly_score >= 25.0 or warning_alerts > 0 or degraded_nodes > 0:
            status = "warning"
        else:
            status = "stable"

        return AIHealthSummaryModel(
            status=status,
            anomaly_score=anomaly_score,
            critical_alerts=critical_alerts,
            warning_alerts=warning_alerts,
            high_load_nodes=high_load_nodes,
            down_nodes=down_nodes,
            degraded_nodes=degraded_nodes,
        )

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _build_recommendations(
        self,
        nodes: List[NodeRuntimeModel],
        alerts: List[SecurityAlertModel],
        health: AIHealthSummaryModel,
    ) -> List[AIRecommendationModel]:
        recs: List[AIRecommendationModel] = []

        for node in nodes:
            recs.extend(self._node_recommendations(node))

        recs.extend(self._security_recommendations(alerts))

        if not recs:
            recs.append(
                AIRecommendationModel(
                    type="observation",
                    message=(
                        "Network is stable. Centralized router, managed nodes, VLAN segmentation, "
                        "and roaming telemetry are operating within expected demo thresholds."
                    ),
                    confidence=0.92,
                )
            )
        else:
            if health.status == "critical":
                recs.insert(
                    0,
                    AIRecommendationModel(
                        type="security_action",
                        message=(
                            "Critical network state detected. Prioritize offline/degraded nodes, "
                            "segmentation alerts, and high packet-loss areas before capacity tuning."
                        ),
                        confidence=0.95,
                    ),
                )
            elif health.status == "warning":
                recs.insert(
                    0,
                    AIRecommendationModel(
                        type="observation",
                        message=(
                            "Warning state detected. The AI controller should monitor roaming, retry rate, "
                            "client load, and RF quality before applying automatic channel or TX changes."
                        ),
                        confidence=0.88,
                    ),
                )

        return recs

    def _node_recommendations(self, node: Any) -> List[AIRecommendationModel]:
        recs: List[AIRecommendationModel] = []

        node_id = self._get(node, "id")
        node_name = self._get(node, "name", f"Node-{node_id}")
        room_id = self._get(node, "room_id")
        room_name = self._get(node, "room_name", "this area")
        status = str(self._get(node, "status", "unknown")).lower()
        load = int(self._get(node, "current_load", 0) or 0)
        connected = int(self._get(node, "connected_clients", load) or 0)
        radio = self._get(node, "radio", {}) or {}

        rssi = float(self._get(radio, "rssi_avg", -45.0) or -45.0)
        snr = float(self._get(radio, "snr_avg", 35.0) or 35.0)
        retry = float(self._get(radio, "retry_rate_pct", 0.0) or 0.0)
        packet_loss = float(self._get(radio, "packet_loss_pct", 0.0) or 0.0)
        throughput = float(self._get(radio, "throughput_mbps", 0.0) or 0.0)
        latency = float(self._get(radio, "latency_ms", 0.0) or 0.0)
        tx_power = float(self._get(radio, "tx_power_dbm", 18.0) or 18.0)
        channel = self._get(radio, "current_channel", "-")

        if status in ["offline", "down"]:
            recs.append(
                AIRecommendationModel(
                    type="security_action",
                    message=(
                        f"{node_name} is offline. Check power, PoE adapter, uplink cable, "
                        "and centralized router registration."
                    ),
                    node_id=node_id,
                    room_id=room_id,
                    confidence=0.96,
                )
            )
            return recs

        if status == "degraded":
            recs.append(
                AIRecommendationModel(
                    type="node_reposition",
                    message=(
                        f"{node_name} is degraded in {room_name}. Inspect obstruction, wall loss, "
                        "antenna direction, and local interference."
                    ),
                    node_id=node_id,
                    room_id=room_id,
                    confidence=0.86,
                )
            )

        if load >= self.high_load_threshold or connected >= self.high_load_threshold:
            recs.append(
                AIRecommendationModel(
                    type="add_node",
                    message=(
                        f"{node_name} is overloaded with {connected} connected clients. "
                        "Add a nearby node or rebalance clients through the centralized controller."
                    ),
                    node_id=node_id,
                    room_id=room_id,
                    confidence=0.88,
                )
            )
        elif load >= self.warning_load_threshold:
            recs.append(
                AIRecommendationModel(
                    type="observation",
                    message=(
                        f"{node_name} has medium-high load. Continue monitoring before adding hardware; "
                        "roaming steering may be enough."
                    ),
                    node_id=node_id,
                    room_id=room_id,
                    confidence=0.74,
                )
            )

        if rssi <= self.weak_rssi_threshold:
            if tx_power < 20:
                recs.append(
                    AIRecommendationModel(
                        type="tx_power_adjustment",
                        message=(
                            f"Weak RSSI detected on {node_name} ({rssi:.1f} dBm). "
                            "Increase TX power slightly or widen the beam for this room."
                        ),
                        node_id=node_id,
                        room_id=room_id,
                        confidence=0.84,
                    )
                )
            else:
                recs.append(
                    AIRecommendationModel(
                        type="add_node",
                        message=(
                            f"Weak RSSI detected on {node_name} while TX power is already high. "
                            "Add a node or reposition the device closer to the weak area."
                        ),
                        node_id=node_id,
                        room_id=room_id,
                        confidence=0.87,
                    )
                )

        if snr <= self.poor_snr_threshold or retry >= self.high_retry_threshold:
            recs.append(
                AIRecommendationModel(
                    type="channel_change",
                    message=(
                        f"Interference risk on {node_name}: channel {channel}, SNR {snr:.1f} dB, "
                        f"retry rate {retry:.1f}%. Reassign channel or reduce overlap with nearby nodes."
                    ),
                    node_id=node_id,
                    room_id=room_id,
                    confidence=0.85,
                )
            )

        if packet_loss >= self.high_packet_loss_threshold:
            recs.append(
                AIRecommendationModel(
                    type="node_reposition",
                    message=(
                        f"Packet loss on {node_name} is {packet_loss:.1f}%. Check wall attenuation, "
                        "node orientation, and client distance."
                    ),
                    node_id=node_id,
                    room_id=room_id,
                    confidence=0.82,
                )
            )

        if latency >= self.high_latency_threshold and connected > 0:
            recs.append(
                AIRecommendationModel(
                    type="observation",
                    message=(
                        f"Latency on {node_name} reached {latency:.1f} ms. This is usually caused by "
                        "load, retries, or weak roaming conditions."
                    ),
                    node_id=node_id,
                    room_id=room_id,
                    confidence=0.76,
                )
            )

        if throughput > 0 and throughput <= self.low_throughput_threshold and connected > 0:
            recs.append(
                AIRecommendationModel(
                    type="channel_change",
                    message=(
                        f"Low throughput detected on {node_name} ({throughput:.1f} Mbps). "
                        "Try channel reassignment and verify client steering rules."
                    ),
                    node_id=node_id,
                    room_id=room_id,
                    confidence=0.78,
                )
            )

        return recs

    def _security_recommendations(self, alerts: List[SecurityAlertModel]) -> List[AIRecommendationModel]:
        recs: List[AIRecommendationModel] = []

        for alert in alerts:
            severity = str(self._get(alert, "severity", "info")).lower()
            category = str(self._get(alert, "category", "unknown")).lower()
            title = self._get(alert, "title", "Security alert")
            node_id = self._get(alert, "node_id")
            description = self._get(alert, "description", "")

            if category == "segmentation_violation":
                recs.append(
                    AIRecommendationModel(
                        type="security_action",
                        message=(
                            f"Segmentation alert: {title}. Keep guest/staff/management VLAN isolation enforced. "
                            f"Detail: {description}"
                        ),
                        node_id=node_id,
                        confidence=0.91 if severity in ["warning", "critical"] else 0.78,
                    )
                )
            elif category in ["packet_loss", "weak_signal", "high_retries", "interference"]:
                rec_type = "channel_change" if category in ["high_retries", "interference"] else "node_reposition"
                recs.append(
                    AIRecommendationModel(
                        type=rec_type,
                        message=f"RF quality alert: {title}. {description}",
                        node_id=node_id,
                        confidence=0.82,
                    )
                )
            elif category == "node_failure":
                recs.append(
                    AIRecommendationModel(
                        type="security_action",
                        message=f"Node health alert: {title}. {description}",
                        node_id=node_id,
                        confidence=0.90,
                    )
                )

        return recs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dedupe_recommendations(self, recs: List[AIRecommendationModel]) -> List[AIRecommendationModel]:
        seen = set()
        unique: List[AIRecommendationModel] = []

        priority = {
            "security_action": 0,
            "add_node": 1,
            "channel_change": 2,
            "tx_power_adjustment": 3,
            "node_reposition": 4,
            "observation": 5,
        }

        recs = sorted(
            recs,
            key=lambda r: (
                priority.get(self._get(r, "type", "observation"), 99),
                -float(self._get(r, "confidence", 0.0) or 0.0),
            ),
        )

        for rec in recs:
            key = (
                self._get(rec, "type", "observation"),
                self._get(rec, "node_id", None),
                self._get(rec, "room_id", None),
                str(self._get(rec, "message", ""))[:80],
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(rec)

        return unique

    def _get(self, obj: Any, key: str, default: Any = None) -> Any:
        if obj is None:
            return default

        if isinstance(obj, dict):
            return obj.get(key, default)

        return getattr(obj, key, default)
