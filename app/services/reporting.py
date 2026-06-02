from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import math

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


class ReportGenerator:
    """
    StructFi dashboard report generator.

    The Excel export is intentionally designed as a complete engineering report
    for the current simulation experiment, not as a raw dump. It produces one
    workbook focused on simulation evidence: node justification, RF/hardware
    details, clients/QoS, detections, decisions, handover, telemetry, and charts.
    """

    def __init__(self):
        self.output_dir = Path("data/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public exports
    # ------------------------------------------------------------------

    def export_excel(self, state: dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = self.output_dir / f"structfi_digital_twin_report_{timestamp}.xlsx"
        data = self._prepare_report_data(state or {})

        # xlsxwriter is used because it gives the best embedded chart/layout
        # control for a simulation-experiment Excel report.
        with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
            workbook = writer.book
            formats = self._build_formats(workbook)

            # Hidden source data must be written before visible charts are inserted.
            # The first visible sheet is now a simulation-results chart board, not a
            # generic dashboard or explanation page.
            self._write_hidden_chart_data(writer, workbook, formats, data)
            self._write_simulation_charts_sheet(writer, workbook, formats, data)

            self._write_dataframe_sheet(writer, "01_Node_Evidence", data["node_evidence_df"], formats, freeze=(1, 2))
            self._write_dataframe_sheet(writer, "02_Node_Performance", data["node_performance_df"], formats, freeze=(1, 2))
            self._write_dataframe_sheet(writer, "03_Telemetry_Timeline", data["telemetry_df"], formats, freeze=(1, 2))
            self._write_dataframe_sheet(writer, "04_RF_Hardware", data["rf_hardware_df"], formats, freeze=(1, 2))
            self._write_dataframe_sheet(writer, "05_Clients_Traffic_QoS", data["clients_df"], formats, freeze=(1, 2))
            self._write_dataframe_sheet(writer, "06_Security_Detections", data["alerts_df"], formats, freeze=(1, 2))
            self._write_dataframe_sheet(writer, "07_Controller_Decisions", data["decisions_df"], formats, freeze=(1, 2))
            self._write_dataframe_sheet(writer, "08_Handover_Mobility", data["handover_df"], formats, freeze=(1, 2))
            self._write_dataframe_sheet(writer, "09_Access_Matrix", data["access_df"], formats, freeze=(1, 2))
            self._write_dataframe_sheet(writer, "10_Rooms_Coverage", data["rooms_df"], formats, freeze=(1, 2))
            self._write_dataframe_sheet(writer, "11_Materials_Assumptions", data["wall_materials_df"], formats, freeze=(1, 1))
            self._add_sheet_level_charts(writer, workbook, data)

        return str(file_path).replace("\\", "/")

    def export_pdf(self, state: dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = self.output_dir / f"structfi_digital_twin_report_{timestamp}.pdf"
        data = self._prepare_report_data(state or {})

        c = canvas.Canvas(str(file_path), pagesize=A4)
        width, height = A4
        y = height - 45
        line_gap = 16

        def page_if_needed(extra=0):
            nonlocal y
            if y < 70 + extra:
                c.showPage()
                y = height - 45

        def write_line(text, bold=False, size=10):
            nonlocal y
            page_if_needed()
            c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            c.drawString(38, y, str(text)[:112])
            y -= line_gap

        def section(title):
            nonlocal y
            y -= 4
            write_line(title, bold=True, size=12)
            c.line(38, y + 5, width - 38, y + 5)
            y -= 8

        overview = data["overview"]
        write_line("StructFi Digital Twin Simulation Report", bold=True, size=15)
        write_line(f"Generated: {timestamp}")
        write_line("Scope: CAD planning, RF propagation, hardware twin, live simulation, security, QoS, and handover.")

        section("Executive Summary")
        for key in [
            "simulation_source", "step", "rooms_count", "planned_nodes_count", "runtime_nodes_count",
            "clients_count", "alerts_count", "decisions_count", "handover_events_count",
            "avg_rssi_dbm", "avg_snr_db", "avg_throughput_mbps", "avg_packet_loss_pct", "network_grade",
        ]:
            write_line(f"{key}: {overview.get(key, '-')}")

        section("Node Evidence Highlights")
        node_df = data["node_evidence_df"]
        if node_df.empty:
            write_line("No node evidence available. Apply the CAD plan to simulation first.")
        else:
            for _, row in node_df.head(12).iterrows():
                write_line(
                    f"{row.get('node_name', '-')}: {row.get('room_name', '-')} | "
                    f"RSSI {row.get('rssi_avg_dbm', '-')} dBm | Clients {row.get('connected_clients', '-')} | "
                    f"Alerts {row.get('alert_count', 0)} | {row.get('suggested_reason', '-') }"
                )

        section("Security / Detection Summary")
        alerts_df = data["alerts_df"]
        if alerts_df.empty:
            write_line("No active detections in this simulation snapshot.")
        else:
            for _, row in alerts_df.head(15).iterrows():
                write_line(f"{row.get('severity', '-').upper()} | {row.get('title', '-')} | Node {row.get('node_id', '-')}: {row.get('description', '-')}")


        c.save()
        return str(file_path).replace("\\", "/")

    # ------------------------------------------------------------------
    # Report data model
    # ------------------------------------------------------------------

    def _prepare_report_data(self, raw_state: Dict[str, Any]) -> Dict[str, Any]:
        sim = raw_state.get("simulation_state") if isinstance(raw_state.get("simulation_state"), dict) else raw_state
        latest_plan = self._unwrap(raw_state.get("latest_plan")) or self._unwrap(sim.get("latest_plan")) or {}
        latest_building = raw_state.get("latest_building") or sim.get("building") or {}
        project = raw_state.get("project_config") or {}
        wall_material_config = raw_state.get("wall_material_config") or {}
        material_library = raw_state.get("material_library") or {}
        images = raw_state.get("images") or {}

        rooms = self._list_from(latest_building, "rooms") or self._list_from(sim.get("building") or {}, "rooms")
        planned_nodes = self._extract_nodes(latest_plan) or sim.get("node_plan", []) or []
        runtime_nodes = sim.get("node_runtime", []) or []
        clients = sim.get("clients", []) or []
        security = sim.get("security_state", {}) or {}
        controller = sim.get("controller_state", {}) or {}
        alerts = security.get("alerts", []) or []
        decisions = controller.get("decisions", []) or []
        access = security.get("access_matrix", []) or []
        events = sim.get("events", []) or []
        telemetry = sim.get("telemetry_history", []) or []
        ai = sim.get("ai_output", {}) or {}
        ai_health = ai.get("health_summary", {}) or {}
        recommendations = ai.get("recommendations", []) or []

        node_performance_rows = self._build_node_performance_rows(planned_nodes, runtime_nodes, telemetry, alerts, decisions, clients)
        node_performance_df = pd.DataFrame(node_performance_rows)
        node_evidence_df = pd.DataFrame(self._build_node_evidence_rows(node_performance_rows, alerts, decisions, clients, telemetry))
        telemetry_df = self._safe_dataframe(telemetry)
        rf_hardware_df = pd.DataFrame(self._build_rf_hardware_rows(planned_nodes, runtime_nodes))
        clients_df = pd.DataFrame(self._build_client_rows(clients))
        alerts_df = self._safe_dataframe(alerts)
        decisions_df = self._safe_dataframe(decisions)
        handover_df = pd.DataFrame(self._build_handover_rows(events))
        access_df = self._safe_dataframe(access)
        wall_materials_df = pd.DataFrame(self._build_wall_material_rows(wall_material_config, material_library))
        rooms_df = self._safe_dataframe(rooms)

        overview = self._build_overview(
            sim=sim,
            rooms=rooms,
            planned_nodes=planned_nodes,
            runtime_nodes=runtime_nodes,
            clients=clients,
            alerts=alerts,
            decisions=decisions,
            events=events,
            telemetry=telemetry,
            ai_health=ai_health,
            node_performance_df=node_performance_df,
        )
        overview_df = pd.DataFrame([overview])

        methodology_df = pd.DataFrame([
            {"Item": "Report purpose", "Description": "One-click dashboard-generated engineering report for the current StructFi simulation run."},
            {"Item": "Node placement evidence", "Description": "The Node Evidence sheet explains why each node was suggested: room, role, placement type, placement score, projected clients, RF quality, telemetry count, alerts, decisions, and coverage evidence."},
            {"Item": "RF model", "Description": "RF metrics are digital-twin estimates from point-based indoor propagation: path loss, wall/material attenuation, directional antenna gain, noise floor, and fade margin."},
            {"Item": "Hardware digital twin", "Description": "Each node is represented as a low-cost physical unit with firmware, antenna, PoE/backhaul, mounting, TX power, and client capacity."},
            {"Item": "Live simulation", "Description": "Runtime values are generated after Apply CAD Plan to Simulation and after advancing simulation steps."},
            {"Item": "QoS", "Description": "Client traffic profiles include required bandwidth, latency tolerance, packet-loss tolerance, VLAN, SSID, priority, and QoS status."},
            {"Item": "Handover", "Description": "Handover rows document roaming between nodes, latency, speed, RF quality, and fast/slow classification."},
            {"Item": "Security", "Description": "Detections are intentionally curated: only meaningful node, RF, QoS, roaming, and controller conditions appear to avoid alert spam."},
            {"Item": "Field validation", "Description": "This report supports project discussion and simulation validation. Physical deployment still requires a real RF survey and hardware test."},
        ])

        return {
            "overview": overview,
            "overview_df": overview_df,
            "node_evidence_df": node_evidence_df,
            "node_performance_df": node_performance_df,
            "telemetry_df": telemetry_df,
            "rf_hardware_df": rf_hardware_df,
            "clients_df": clients_df,
            "alerts_df": alerts_df,
            "decisions_df": decisions_df,
            "handover_df": handover_df,
            "access_df": access_df,
            "wall_materials_df": wall_materials_df,
            "rooms_df": rooms_df,
            "methodology_df": methodology_df,
            "ai_recs_df": self._safe_dataframe(recommendations),
            "raw": {
                "simulation_state": sim,
                "latest_plan": latest_plan,
                "latest_building": latest_building,
                "project_config": project,
                "wall_material_config": wall_material_config,
                "images": images,
            },
        }

    def _build_overview(self, **kwargs) -> Dict[str, Any]:
        sim = kwargs["sim"]
        telemetry = kwargs["telemetry"]
        node_df = kwargs["node_performance_df"]
        ai_health = kwargs["ai_health"]

        avg_rssi = self._avg([t.get("rssi_avg") for t in telemetry])
        avg_snr = self._avg([t.get("snr_avg") for t in telemetry])
        avg_tp = self._avg([t.get("throughput_mbps") for t in telemetry])
        avg_loss = self._avg([t.get("packet_loss_pct") for t in telemetry])

        if avg_rssi is None and not node_df.empty and "rssi_avg_dbm" in node_df:
            avg_rssi = self._avg(node_df["rssi_avg_dbm"].tolist())
        if avg_snr is None and not node_df.empty and "snr_avg_db" in node_df:
            avg_snr = self._avg(node_df["snr_avg_db"].tolist())
        if avg_tp is None and not node_df.empty and "throughput_mbps" in node_df:
            avg_tp = self._avg(node_df["throughput_mbps"].tolist())
        if avg_loss is None and not node_df.empty and "packet_loss_pct" in node_df:
            avg_loss = self._avg(node_df["packet_loss_pct"].tolist())

        grade = self._network_grade(avg_rssi, avg_snr, avg_loss, len(kwargs["alerts"]))

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "simulation_source": sim.get("simulation_source", "unknown"),
            "is_live": sim.get("is_live", False),
            "step": sim.get("step", 0),
            "timestamp": sim.get("timestamp", ""),
            "rooms_count": len(kwargs["rooms"]),
            "planned_nodes_count": len(kwargs["planned_nodes"]),
            "runtime_nodes_count": len(kwargs["runtime_nodes"]),
            "clients_count": len(kwargs["clients"]),
            "alerts_count": len(kwargs["alerts"]),
            "decisions_count": len(kwargs["decisions"]),
            "events_count": len(kwargs["events"]),
            "handover_events_count": len([e for e in kwargs["events"] if str(e.get("type", "")).lower() == "handover"]),
            "telemetry_points": len(telemetry),
            "ai_status": ai_health.get("status", "unknown"),
            "anomaly_score": ai_health.get("anomaly_score", 0),
            "critical_alerts": ai_health.get("critical_alerts", 0),
            "warning_alerts": ai_health.get("warning_alerts", 0),
            "avg_rssi_dbm": self._round(avg_rssi),
            "avg_snr_db": self._round(avg_snr),
            "avg_throughput_mbps": self._round(avg_tp),
            "avg_packet_loss_pct": self._round(avg_loss),
            "network_grade": grade,
        }

    # ------------------------------------------------------------------
    # Table builders
    # ------------------------------------------------------------------

    def _build_node_performance_rows(self, planned_nodes, runtime_nodes, telemetry, alerts, decisions, clients) -> List[Dict[str, Any]]:
        planned_by_id = {self._node_id(n): n for n in planned_nodes if self._node_id(n) is not None}
        runtime_by_id = {self._node_id(n): n for n in runtime_nodes if self._node_id(n) is not None}
        node_ids = sorted(set(planned_by_id) | set(runtime_by_id), key=lambda x: (str(type(x)), x))

        telemetry_by_node = defaultdict(list)
        for t in telemetry or []:
            nid = self._safe_int(t.get("node_id"))
            if nid is not None:
                telemetry_by_node[nid].append(t)

        alerts_by_node = Counter(self._safe_int(a.get("node_id")) for a in alerts or [] if self._safe_int(a.get("node_id")) is not None)
        decisions_by_node = Counter(self._safe_int(d.get("node_id")) for d in decisions or [] if self._safe_int(d.get("node_id")) is not None)
        clients_by_node = Counter(self._safe_int(c.get("connected_node")) for c in clients or [] if self._safe_int(c.get("connected_node")) is not None)
        qos_by_node = defaultdict(Counter)
        for c in clients or []:
            nid = self._safe_int(c.get("connected_node"))
            if nid is not None:
                qos_by_node[nid][str(c.get("qos_state", "not_evaluated"))] += 1

        rows = []
        for nid in node_ids:
            p = planned_by_id.get(nid, {}) or {}
            r = runtime_by_id.get(nid, {}) or {}
            radio = r.get("radio", {}) if isinstance(r.get("radio"), dict) else {}
            env = r.get("environment", {}) if isinstance(r.get("environment"), dict) else {}
            cov = p.get("coverage_metrics", {}) if isinstance(p.get("coverage_metrics"), dict) else {}
            cap = p.get("capacity_metrics", {}) if isinstance(p.get("capacity_metrics"), dict) else {}
            coverage = p.get("coverage", {}) if isinstance(p.get("coverage"), dict) else {}
            capacity = p.get("capacity", {}) if isinstance(p.get("capacity"), dict) else {}
            rf = p.get("rf_profile", {}) if isinstance(p.get("rf_profile"), dict) else {}
            hw = p.get("hardware_profile", {}) if isinstance(p.get("hardware_profile"), dict) else {}
            ts = telemetry_by_node.get(nid, [])

            rssi = radio.get("rssi_avg", cov.get("avg_rssi_dbm", coverage.get("estimated_rssi_center")))
            snr = radio.get("snr_avg", cov.get("avg_snr_db", coverage.get("estimated_snr_center")))
            throughput = radio.get("throughput_mbps")
            packet_loss = radio.get("packet_loss_pct")
            retry = radio.get("retry_rate_pct")
            latency = radio.get("latency_ms")
            grade = self._node_grade(rssi, snr, packet_loss, alerts_by_node.get(nid, 0))

            notes = p.get("notes", [])
            if isinstance(notes, list):
                notes_text = " | ".join(str(x) for x in notes[:5])
            else:
                notes_text = str(notes or "")

            suggested_reason = p.get("placement_reason") or notes_text or (
                f"Suggested in {p.get('room_name') or r.get('room_name') or 'room'} because this location supports "
                f"{p.get('placement_type', 'planned')} placement, expected client demand "
                f"{capacity.get('projected_clients', cap.get('expected_clients', '-'))}, placement score "
                f"{p.get('placement_score', '-')}, and estimated RF/capacity coverage."
            )

            rows.append({
                "node_id": nid,
                "node_name": r.get("name") or p.get("name") or p.get("node_id") or f"Node-{nid}",
                "room_id": r.get("room_id") or p.get("room_id"),
                "room_name": r.get("room_name") or p.get("room_name"),
                "room_type": r.get("room_type") or p.get("room_type"),
                "node_role": p.get("node_role", r.get("node_role", "room_node")),
                "placement_type": p.get("placement_type"),
                "x": r.get("x", p.get("x")),
                "y": r.get("y", p.get("y")),
                "status": r.get("status", p.get("status", "planned")),
                "channel": radio.get("current_channel", p.get("channel")),
                "tx_power_dbm": radio.get("tx_power_dbm", p.get("tx_power", p.get("tx_power_dbm"))),
                "connected_clients": r.get("connected_clients", clients_by_node.get(nid, 0)),
                "current_load": r.get("current_load", clients_by_node.get(nid, 0)),
                "max_clients": r.get("max_clients", hw.get("max_clients", "")),
                "rssi_avg_dbm": self._round(rssi),
                "snr_avg_db": self._round(snr),
                "throughput_mbps": self._round(throughput),
                "packet_loss_pct": self._round(packet_loss),
                "retry_rate_pct": self._round(retry),
                "latency_ms": self._round(latency),
                "temperature_c": env.get("temperature_c"),
                "humidity_pct": env.get("humidity_pct"),
                "coverage_percent": cov.get("coverage_percent", coverage.get("room_coverage_score")),
                "projected_clients": capacity.get("projected_clients", cap.get("expected_clients")),
                "projected_capacity_mbps": capacity.get("projected_capacity_mbps", cap.get("effective_capacity_mbps")),
                "placement_score": p.get("placement_score"),
                "alert_count": alerts_by_node.get(nid, 0),
                "decision_count": decisions_by_node.get(nid, 0),
                "telemetry_count": len(ts),
                "qos_ok_clients": qos_by_node[nid].get("ok", 0),
                "qos_warning_clients": qos_by_node[nid].get("warning", 0),
                "qos_violated_clients": qos_by_node[nid].get("violated", 0),
                "health_grade": grade,
                "dominant_wall_material": rf.get("dominant_wall_material") or cov.get("dominant_wall_material"),
                "avg_wall_loss_db": rf.get("avg_wall_loss_db") or cov.get("avg_wall_loss_db"),
                "avg_path_loss_db": rf.get("avg_path_loss_db") or cov.get("avg_path_loss_db"),
                "antenna": hw.get("antenna_type"),
                "antenna_gain_dbi": hw.get("antenna_gain_dbi"),
                "device": hw.get("device_type") or hw.get("physical_node_model"),
                "firmware": hw.get("firmware"),
                "poe": hw.get("poe_standard"),
                "backhaul": hw.get("backhaul_type"),
                "mount": hw.get("mount_type"),
                "suggested_reason": suggested_reason,
            })
        return rows

    def _build_node_evidence_rows(self, node_rows, alerts, decisions, clients, telemetry) -> List[Dict[str, Any]]:
        alert_by_node = defaultdict(list)
        for a in alerts or []:
            nid = self._safe_int(a.get("node_id"))
            if nid is not None:
                alert_by_node[nid].append(a)

        decision_by_node = defaultdict(list)
        for d in decisions or []:
            nid = self._safe_int(d.get("node_id"))
            if nid is not None:
                decision_by_node[nid].append(d)

        clients_by_node = defaultdict(list)
        for c in clients or []:
            nid = self._safe_int(c.get("connected_node"))
            if nid is not None:
                clients_by_node[nid].append(c)

        telemetry_by_node = Counter()
        for t in telemetry or []:
            nid = self._safe_int(t.get("node_id"))
            if nid is not None:
                telemetry_by_node[nid] += 1

        rows = []
        for row in node_rows:
            nid = row.get("node_id")
            node_alerts = alert_by_node.get(nid, [])
            node_decisions = decision_by_node.get(nid, [])
            node_clients = clients_by_node.get(nid, [])
            traffic_mix = Counter(str(c.get("traffic_profile", c.get("application", "unknown"))) for c in node_clients)
            qos_mix = Counter(str(c.get("qos_state", "not_evaluated")) for c in node_clients)
            detection_summary = "; ".join(
                f"{a.get('severity', 'info').upper()}:{a.get('title', a.get('category', 'alert'))}"
                for a in node_alerts[:4]
            ) or "No active detection"
            decisions_summary = "; ".join(
                f"{d.get('action', 'none')}={d.get('value', '')}" for d in node_decisions[:4]
            ) or "No active controller action"

            rows.append({
                "node_id": nid,
                "node_name": row.get("node_name"),
                "room_name": row.get("room_name"),
                "node_role": row.get("node_role"),
                "why_suggested_here": row.get("suggested_reason"),
                "placement_score": row.get("placement_score"),
                "coverage_percent": row.get("coverage_percent"),
                "projected_clients": row.get("projected_clients"),
                "connected_clients": row.get("connected_clients"),
                "telemetry_readings": telemetry_by_node.get(nid, row.get("telemetry_count", 0)),
                "rssi_avg_dbm": row.get("rssi_avg_dbm"),
                "snr_avg_db": row.get("snr_avg_db"),
                "throughput_mbps": row.get("throughput_mbps"),
                "packet_loss_pct": row.get("packet_loss_pct"),
                "retry_rate_pct": row.get("retry_rate_pct"),
                "latency_ms": row.get("latency_ms"),
                "wall_material": row.get("dominant_wall_material"),
                "wall_loss_db": row.get("avg_wall_loss_db"),
                "device": row.get("device"),
                "antenna": row.get("antenna"),
                "tx_power_dbm": row.get("tx_power_dbm"),
                "channel": row.get("channel"),
                "traffic_mix": self._counter_text(traffic_mix),
                "qos_mix": self._counter_text(qos_mix),
                "detections_on_node": detection_summary,
                "controller_actions": decisions_summary,
                "health_grade": row.get("health_grade"),
            })
        return rows

    def _build_rf_hardware_rows(self, planned_nodes, runtime_nodes) -> List[Dict[str, Any]]:
        runtime_by_id = {self._node_id(n): n for n in runtime_nodes or [] if self._node_id(n) is not None}
        rows = []
        for n in planned_nodes or []:
            nid = self._node_id(n)
            r = runtime_by_id.get(nid, {}) or {}
            radio = r.get("radio", {}) if isinstance(r.get("radio"), dict) else {}
            hw = n.get("hardware_profile", {}) if isinstance(n.get("hardware_profile"), dict) else {}
            rf = n.get("rf_profile", {}) if isinstance(n.get("rf_profile"), dict) else {}
            cov = n.get("coverage_metrics", {}) if isinstance(n.get("coverage_metrics"), dict) else {}
            rows.append({
                "node_id": nid,
                "node_name": n.get("name") or n.get("node_id"),
                "room": n.get("room_name"),
                "role": n.get("node_role"),
                "device": hw.get("device_type") or hw.get("physical_node_model"),
                "firmware": hw.get("firmware"),
                "antenna": hw.get("antenna_type"),
                "antenna_gain_dbi": hw.get("antenna_gain_dbi"),
                "tx_power_dbm": radio.get("tx_power_dbm") or hw.get("tx_power_dbm") or n.get("tx_power") or n.get("tx_power_dbm"),
                "channel": radio.get("current_channel") or hw.get("channel") or n.get("channel"),
                "channel_width_mhz": hw.get("channel_width_mhz"),
                "poe": hw.get("poe_standard"),
                "backhaul": hw.get("backhaul_type"),
                "mount": hw.get("mount_type"),
                "mount_height_m": hw.get("mount_height_m"),
                "max_clients": hw.get("max_clients"),
                "power_w": hw.get("estimated_power_watts"),
                "rf_model": rf.get("model") or rf.get("rf_model") or cov.get("rf_model"),
                "avg_path_loss_db": rf.get("avg_path_loss_db") or cov.get("avg_path_loss_db"),
                "avg_wall_loss_db": rf.get("avg_wall_loss_db") or cov.get("avg_wall_loss_db"),
                "avg_directional_gain_db": rf.get("avg_directional_gain_db") or cov.get("avg_directional_gain_db"),
                "dominant_wall_material": rf.get("dominant_wall_material") or cov.get("dominant_wall_material"),
                "noise_floor_dbm": rf.get("noise_floor_dbm") or cov.get("noise_floor_dbm"),
                "coverage_percent": cov.get("coverage_percent"),
            })
        return rows

    def _build_client_rows(self, clients) -> List[Dict[str, Any]]:
        rows = []
        for c in clients or []:
            rows.append({
                "client_id": c.get("id"),
                "name": c.get("name"),
                "client_type": c.get("client_type", c.get("role")),
                "role": c.get("role"),
                "traffic_profile": c.get("traffic_profile"),
                "application": c.get("application"),
                "vlan_id": c.get("vlan_id"),
                "ssid": c.get("ssid"),
                "qos_priority": c.get("qos_priority"),
                "qos_state": c.get("qos_state", "not_evaluated"),
                "required_bandwidth_mbps": c.get("required_bandwidth_mbps"),
                "max_latency_ms": c.get("max_latency_ms"),
                "packet_loss_tolerance_pct": c.get("packet_loss_tolerance_pct"),
                "mobility_pattern": c.get("mobility_pattern"),
                "sticky_client": c.get("sticky_client"),
                "speed_mps": c.get("speed"),
                "x": c.get("x"),
                "y": c.get("y"),
                "floor": c.get("floor"),
                "connected_node": c.get("connected_node"),
                "rssi_dbm": c.get("current_rssi"),
                "snr_db": c.get("current_snr"),
                "throughput_mbps": c.get("current_throughput_mbps"),
                "packet_loss_pct": c.get("current_packet_loss_pct"),
                "retry_rate_pct": c.get("current_retry_rate_pct"),
                "latency_ms": c.get("current_latency_ms"),
                "roaming_count": c.get("roaming_count"),
                "last_handover_latency_ms": c.get("handover_latency_ms"),
                "last_handover_status": c.get("last_handover_status"),
                "packets_sent": c.get("packets_sent"),
                "packets_received": c.get("packets_received"),
            })
        return rows

    def _build_handover_rows(self, events) -> List[Dict[str, Any]]:
        rows = []
        for e in events or []:
            if str(e.get("type", "")).lower() != "handover":
                continue
            m = e.get("metadata", {}) if isinstance(e.get("metadata"), dict) else {}
            rows.append({
                "event_type": e.get("type"),
                "severity": e.get("severity"),
                "client_id": e.get("client_id"),
                "new_node_id": e.get("node_id") or m.get("new_node_id"),
                "previous_node_id": m.get("previous_node_id"),
                "handover_latency_ms": m.get("handover_latency_ms"),
                "target_latency_ms": m.get("target_latency_ms"),
                "client_speed_mps": m.get("client_speed_mps"),
                "rssi_dbm": m.get("rssi_dbm"),
                "snr_db": m.get("snr_db"),
                "packet_loss_pct": m.get("packet_loss_pct"),
                "status": m.get("status"),
                "message": e.get("message"),
            })
        return rows

    def _build_wall_material_rows(self, config, library) -> List[Dict[str, Any]]:
        config = config or {}
        library = library or {}
        rows = []
        mapping = [
            ("default_material", "Default CAD wall"),
            ("interior_wall_material", "Interior room partitions"),
            ("facade_material", "Facade / exterior walls"),
            ("window_material", "Windows / glass partitions"),
            ("door_material", "Doors"),
            ("structural_wall_material", "Structural walls"),
        ]
        for key, label in mapping:
            material = config.get(key, "-")
            details = library.get(material, {}) if isinstance(library, dict) else {}
            rows.append({
                "element": label,
                "config_key": key,
                "material": material,
                "attenuation_db": details.get("attenuation_db"),
                "typical_use": details.get("typical_use"),
                "notes": details.get("notes", ""),
            })
        return rows

    # ------------------------------------------------------------------
    # Excel styling/charting
    # ------------------------------------------------------------------

    def _build_formats(self, workbook):
        return {
            "title": workbook.add_format({"bold": True, "font_size": 22, "font_color": "#1D1D1F"}),
            "subtitle": workbook.add_format({"font_size": 10, "font_color": "#5F6368"}),
            "section": workbook.add_format({"bold": True, "font_size": 12, "font_color": "#FFFFFF", "bg_color": "#0B3D91", "border": 1, "align": "center"}),
            "card_label": workbook.add_format({"bold": True, "font_color": "#5F6368", "font_size": 9, "bg_color": "#EAF1FB", "border": 1, "align": "center"}),
            "card_value": workbook.add_format({"bold": True, "font_size": 15, "font_color": "#1D1D1F", "bg_color": "#FFFFFF", "border": 1, "align": "center"}),
            "header": workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "border": 1, "text_wrap": True, "valign": "vcenter"}),
            "body": workbook.add_format({"border": 1, "valign": "top"}),
            "body_wrap": workbook.add_format({"border": 1, "valign": "top", "text_wrap": True}),
            "note": workbook.add_format({"text_wrap": True, "font_color": "#333333", "bg_color": "#FFF8E5", "border": 1, "valign": "top"}),
            "good": workbook.add_format({"bg_color": "#DFF5E1", "font_color": "#176B2C"}),
            "warn": workbook.add_format({"bg_color": "#FFF1CC", "font_color": "#8A5A00"}),
            "bad": workbook.add_format({"bg_color": "#FDE2E0", "font_color": "#A4262C"}),
            "num": workbook.add_format({"border": 1, "num_format": "0.00"}),
            "int": workbook.add_format({"border": 1, "num_format": "0"}),
        }


    def _write_hidden_chart_data(self, writer, workbook, formats, data):
        """
        Write compact hidden source tables for the workbook charts.

        This method is intentionally kept internal and hidden from the final
        report. The visible report starts at 00_Simulation_Run, while this sheet
        provides stable ranges for all dashboard charts. It prevents chart code
        from depending on row positions in detailed evidence sheets.
        """
        sheet = "_chart_data"
        ws = workbook.add_worksheet(sheet)
        writer.sheets[sheet] = ws
        ws.hide()

        ranges = {}
        row = 0

        def safe_num(value, default=0.0):
            try:
                if value in [None, "", "-"]:
                    return default
                return float(value)
            except Exception:
                return default

        def write_table(title, headers, records):
            nonlocal row
            start = row
            ws.write(row, 0, title)
            row += 1
            for col, header in enumerate(headers):
                ws.write(row, col, header)
            row += 1
            for record in records:
                for col, value in enumerate(record):
                    ws.write(row, col, value)
                row += 1
            length = len(records)
            row += 2
            return start, length

        # 1) Node-level chart data.
        node_df = data.get("node_performance_df")
        if isinstance(node_df, pd.DataFrame) and not node_df.empty:
            node_records = []
            for _, n in node_df.iterrows():
                node_records.append([
                    str(n.get("node_name", n.get("node_id", "Node"))),
                    safe_num(n.get("rssi_avg_dbm")),
                    safe_num(n.get("snr_avg_db")),
                    safe_num(n.get("throughput_mbps")),
                    safe_num(n.get("packet_loss_pct")),
                    safe_num(n.get("connected_clients")),
                    safe_num(n.get("alert_count")),
                    safe_num(n.get("decision_count")),
                    safe_num(n.get("retry_rate_pct")),
                    safe_num(n.get("latency_ms")),
                    safe_num(n.get("telemetry_count", n.get("telemetry_readings"))),
                ])
            start, length = write_table(
                "Node chart data",
                ["Node", "RSSI", "SNR", "Throughput", "Loss", "Clients", "Alerts", "Decisions", "Retry", "Latency", "Telemetry"],
                node_records,
            )
            ranges["node_start"] = start + 1
            ranges["node_len"] = length
        else:
            ranges["node_start"] = row
            ranges["node_len"] = 0

        # 2) Alert severity distribution.
        alerts_df = data.get("alerts_df")
        alert_records = []
        if isinstance(alerts_df, pd.DataFrame) and not alerts_df.empty and "severity" in alerts_df.columns:
            counts = alerts_df["severity"].fillna("unknown").astype(str).value_counts()
            alert_records = [[k, int(v)] for k, v in counts.items()]
        start, length = write_table("Alerts by severity", ["Severity", "Count"], alert_records)
        ranges["alerts_start"] = start + 1
        ranges["alerts_len"] = length

        # 3) QoS state distribution.
        clients_df = data.get("clients_df")
        qos_records = []
        if isinstance(clients_df, pd.DataFrame) and not clients_df.empty:
            qos_col = "qos_state" if "qos_state" in clients_df.columns else None
            if qos_col:
                counts = clients_df[qos_col].fillna("not_evaluated").astype(str).value_counts()
                qos_records = [[k, int(v)] for k, v in counts.items()]
        start, length = write_table("QoS states", ["QoS State", "Count"], qos_records)
        ranges["qos_start"] = start + 1
        ranges["qos_len"] = length

        # 4) Traffic profile mix.
        traffic_records = []
        if isinstance(clients_df, pd.DataFrame) and not clients_df.empty:
            traffic_col = "traffic_profile" if "traffic_profile" in clients_df.columns else ("application" if "application" in clients_df.columns else None)
            if traffic_col:
                counts = clients_df[traffic_col].fillna("unknown").astype(str).value_counts()
                traffic_records = [[k, int(v)] for k, v in counts.items()]
        start, length = write_table("Traffic profiles", ["Traffic", "Count"], traffic_records)
        ranges["traffic_start"] = start + 1
        ranges["traffic_len"] = length

        # 5) Controller decision action types.
        decisions_df = data.get("decisions_df")
        decision_records = []
        if isinstance(decisions_df, pd.DataFrame) and not decisions_df.empty and "action" in decisions_df.columns:
            counts = decisions_df["action"].fillna("none").astype(str).value_counts()
            decision_records = [[k, int(v)] for k, v in counts.items()]
        start, length = write_table("Controller decisions", ["Action", "Count"], decision_records)
        ranges["decisions_start"] = start + 1
        ranges["decisions_len"] = length

        # 6) Telemetry trend aggregated by simulation step.
        telemetry_df = data.get("telemetry_df")
        telemetry_records = []
        if isinstance(telemetry_df, pd.DataFrame) and not telemetry_df.empty and "step" in telemetry_df.columns:
            for step, group in telemetry_df.groupby("step", dropna=False):
                telemetry_records.append([
                    safe_num(step),
                    safe_num(group["rssi_avg"].mean()) if "rssi_avg" in group.columns else 0,
                    safe_num(group["snr_avg"].mean()) if "snr_avg" in group.columns else 0,
                    safe_num(group["throughput_mbps"].mean()) if "throughput_mbps" in group.columns else 0,
                    safe_num(group["packet_loss_pct"].mean()) if "packet_loss_pct" in group.columns else 0,
                ])
        start, length = write_table("Telemetry by step", ["Step", "Avg RSSI", "Avg SNR", "Avg Throughput", "Avg Loss"], telemetry_records)
        ranges["telemetry_start"] = start + 1
        ranges["telemetry_len"] = length

        # 7) Handover latency and mobility.
        handover_df = data.get("handover_df")
        handover_records = []
        if isinstance(handover_df, pd.DataFrame) and not handover_df.empty:
            for idx, h in handover_df.iterrows():
                label = f"C{h.get('client_id', idx + 1)}"
                handover_records.append([
                    label,
                    safe_num(h.get("handover_latency_ms")),
                    safe_num(h.get("client_speed_mps")),
                ])
        start, length = write_table("Handover", ["Client", "Latency", "Speed"], handover_records)
        ranges["handover_start"] = start + 1
        ranges["handover_len"] = length

        data["_chart_ranges"] = ranges

    def _write_simulation_charts_sheet(self, writer, workbook, formats, data):
        sheet = "00_Simulation_Run"
        ws = workbook.add_worksheet(sheet)
        writer.sheets[sheet] = ws
        ws.hide_gridlines(2)
        ws.freeze_panes(5, 0)
        ws.set_zoom(85)
        ws.set_column("A:A", 3)
        ws.set_column("B:M", 16)
        ws.set_column("N:N", 3)

        overview = data["overview"]
        ws.merge_range("B2:M2", "StructFi Simulation Run Evidence Board", formats["title"])
        ws.merge_range("B3:M3", "This sheet summarizes the actual simulation experiment: RF quality, traffic/QoS, handover behavior, controller actions, security detections, and telemetry trends.", formats["subtitle"])

        kpis = [
            ("Step", overview.get("step")),
            ("Rooms", overview.get("rooms_count")),
            ("Planned Nodes", overview.get("planned_nodes_count")),
            ("Runtime Nodes", overview.get("runtime_nodes_count")),
            ("Clients", overview.get("clients_count")),
            ("Alerts", overview.get("alerts_count")),
            ("Decisions", overview.get("decisions_count")),
            ("Handovers", overview.get("handover_events_count")),
            ("Telemetry Points", overview.get("telemetry_points")),
            ("Avg RSSI", overview.get("avg_rssi_dbm")),
            ("Avg SNR", overview.get("avg_snr_db")),
            ("Network Grade", overview.get("network_grade")),
        ]
        cells = [
            ("B5", "C5"), ("D5", "E5"), ("F5", "G5"), ("H5", "I5"), ("J5", "K5"), ("L5", "M5"),
            ("B7", "C7"), ("D7", "E7"), ("F7", "G7"), ("H7", "I7"), ("J7", "K7"), ("L7", "M7"),
        ]
        for (label, value), (label_cell, value_cell) in zip(kpis, cells):
            ws.merge_range(label_cell, label, formats["card_label"])
            ws.merge_range(value_cell, value, formats["card_value"])

        # A compact top-node table gives immediate evidence without adding a prose/methodology page.
        node_df = data["node_performance_df"].copy()
        if not node_df.empty:
            cols = [c for c in [
                "node_name", "room_name", "rssi_avg_dbm", "snr_avg_db", "throughput_mbps", "packet_loss_pct",
                "connected_clients", "alert_count", "decision_count", "telemetry_count", "health_grade"
            ] if c in node_df.columns]
            top_table = self._make_excel_safe(node_df[cols].head(14))
            startrow = 9
            top_table.to_excel(writer, sheet_name=sheet, startrow=startrow, startcol=1, index=False)
            for c, col in enumerate(top_table.columns, start=1):
                ws.write(startrow, c, col, formats["header"])
                ws.set_column(c, c, 15)

        self._insert_simulation_run_charts(workbook, ws, data)

    def _insert_simulation_run_charts(self, workbook, ws, data):
        ranges = data.get("_chart_ranges") or {}
        sheet = "_chart_data"
        node_len = ranges.get("node_len", 0)

        if node_len:
            rf_chart = workbook.add_chart({"type": "column"})
            rf_chart.add_series({"name": "RSSI dBm", "categories": [sheet, 1, 0, node_len, 0], "values": [sheet, 1, 1, node_len, 1]})
            rf_chart.add_series({"name": "SNR dB", "categories": [sheet, 1, 0, node_len, 0], "values": [sheet, 1, 2, node_len, 2]})
            rf_chart.set_title({"name": "RF Quality by Node"})
            rf_chart.set_x_axis({"name": "Node"})
            rf_chart.set_y_axis({"name": "dB / dBm"})
            rf_chart.set_legend({"position": "bottom"})
            rf_chart.set_size({"width": 520, "height": 280})
            ws.insert_chart("B26", rf_chart)

            perf_chart = workbook.add_chart({"type": "line"})
            perf_chart.add_series({"name": "Throughput Mbps", "categories": [sheet, 1, 0, node_len, 0], "values": [sheet, 1, 3, node_len, 3]})
            perf_chart.add_series({"name": "Packet Loss %", "categories": [sheet, 1, 0, node_len, 0], "values": [sheet, 1, 4, node_len, 4]})
            perf_chart.add_series({"name": "Retry %", "categories": [sheet, 1, 0, node_len, 0], "values": [sheet, 1, 8, node_len, 8]})
            perf_chart.set_title({"name": "Throughput / Loss / Retry by Node"})
            perf_chart.set_x_axis({"name": "Node"})
            perf_chart.set_legend({"position": "bottom"})
            perf_chart.set_size({"width": 520, "height": 280})
            ws.insert_chart("H26", perf_chart)

            load_chart = workbook.add_chart({"type": "bar"})
            load_chart.add_series({"name": "Connected Clients", "categories": [sheet, 1, 0, node_len, 0], "values": [sheet, 1, 5, node_len, 5]})
            load_chart.add_series({"name": "Alerts", "categories": [sheet, 1, 0, node_len, 0], "values": [sheet, 1, 6, node_len, 6]})
            load_chart.add_series({"name": "Decisions", "categories": [sheet, 1, 0, node_len, 0], "values": [sheet, 1, 7, node_len, 7]})
            load_chart.set_title({"name": "Clients / Alerts / Decisions by Node"})
            load_chart.set_legend({"position": "bottom"})
            load_chart.set_size({"width": 520, "height": 280})
            ws.insert_chart("B42", load_chart)

            latency_chart = workbook.add_chart({"type": "column"})
            latency_chart.add_series({"name": "Latency ms", "categories": [sheet, 1, 0, node_len, 0], "values": [sheet, 1, 9, node_len, 9]})
            latency_chart.add_series({"name": "Telemetry Readings", "categories": [sheet, 1, 0, node_len, 0], "values": [sheet, 1, 10, node_len, 10]})
            latency_chart.set_title({"name": "Latency and Evidence Volume"})
            latency_chart.set_legend({"position": "bottom"})
            latency_chart.set_size({"width": 520, "height": 280})
            ws.insert_chart("H42", latency_chart)

        alert_len = ranges.get("alerts_len", 0)
        alert_start = ranges.get("alerts_start", 0)
        if alert_len:
            pie = workbook.add_chart({"type": "doughnut"})
            pie.add_series({"name": "Alerts by Severity", "categories": [sheet, alert_start + 1, 0, alert_start + alert_len, 0], "values": [sheet, alert_start + 1, 1, alert_start + alert_len, 1]})
            pie.set_title({"name": "Alerts by Severity"})
            pie.set_legend({"position": "right"})
            pie.set_size({"width": 360, "height": 260})
            ws.insert_chart("B58", pie)

        qos_len = ranges.get("qos_len", 0)
        qos_start = ranges.get("qos_start", 0)
        if qos_len:
            qos = workbook.add_chart({"type": "doughnut"})
            qos.add_series({"name": "QoS State", "categories": [sheet, qos_start + 1, 0, qos_start + qos_len, 0], "values": [sheet, qos_start + 1, 1, qos_start + qos_len, 1]})
            qos.set_title({"name": "QoS State Distribution"})
            qos.set_legend({"position": "right"})
            qos.set_size({"width": 360, "height": 260})
            ws.insert_chart("F58", qos)

        traffic_len = ranges.get("traffic_len", 0)
        traffic_start = ranges.get("traffic_start", 0)
        if traffic_len:
            traffic = workbook.add_chart({"type": "pie"})
            traffic.add_series({"name": "Traffic Mix", "categories": [sheet, traffic_start + 1, 0, traffic_start + traffic_len, 0], "values": [sheet, traffic_start + 1, 1, traffic_start + traffic_len, 1]})
            traffic.set_title({"name": "Traffic Profile Mix"})
            traffic.set_legend({"position": "right"})
            traffic.set_size({"width": 360, "height": 260})
            ws.insert_chart("J58", traffic)

        decision_len = ranges.get("decisions_len", 0)
        decision_start = ranges.get("decisions_start", 0)
        if decision_len:
            decision = workbook.add_chart({"type": "bar"})
            decision.add_series({"name": "Controller Actions", "categories": [sheet, decision_start + 1, 0, decision_start + decision_len, 0], "values": [sheet, decision_start + 1, 1, decision_start + decision_len, 1]})
            decision.set_title({"name": "Controller Decision Types"})
            decision.set_legend({"none": True})
            decision.set_size({"width": 520, "height": 280})
            ws.insert_chart("B74", decision)

        telemetry_len = ranges.get("telemetry_len", 0)
        telemetry_start = ranges.get("telemetry_start", 0)
        if telemetry_len:
            telem = workbook.add_chart({"type": "line"})
            telem.add_series({"name": "Avg RSSI", "categories": [sheet, telemetry_start + 1, 0, telemetry_start + telemetry_len, 0], "values": [sheet, telemetry_start + 1, 1, telemetry_start + telemetry_len, 1]})
            telem.add_series({"name": "Avg Throughput", "categories": [sheet, telemetry_start + 1, 0, telemetry_start + telemetry_len, 0], "values": [sheet, telemetry_start + 1, 3, telemetry_start + telemetry_len, 3]})
            telem.add_series({"name": "Avg Packet Loss", "categories": [sheet, telemetry_start + 1, 0, telemetry_start + telemetry_len, 0], "values": [sheet, telemetry_start + 1, 4, telemetry_start + telemetry_len, 4]})
            telem.set_title({"name": "Simulation Telemetry Trend by Step"})
            telem.set_x_axis({"name": "Simulation Step"})
            telem.set_legend({"position": "bottom"})
            telem.set_size({"width": 520, "height": 280})
            ws.insert_chart("H74", telem)

        handover_len = ranges.get("handover_len", 0)
        handover_start = ranges.get("handover_start", 0)
        if handover_len:
            handover = workbook.add_chart({"type": "column"})
            handover.add_series({"name": "Handover Latency ms", "categories": [sheet, handover_start + 1, 0, handover_start + handover_len, 0], "values": [sheet, handover_start + 1, 1, handover_start + handover_len, 1]})
            handover.add_series({"name": "Client Speed m/s", "categories": [sheet, handover_start + 1, 0, handover_start + handover_len, 0], "values": [sheet, handover_start + 1, 2, handover_start + handover_len, 2]})
            handover.set_title({"name": "Handover Latency and Mobility"})
            handover.set_legend({"position": "bottom"})
            handover.set_size({"width": 520, "height": 280})
            ws.insert_chart("B90", handover)

    def _add_sheet_level_charts(self, writer, workbook, data):
        # Add useful charts inside detailed sheets, not just dashboard.
        telemetry_df = data["telemetry_df"]
        if not telemetry_df.empty and {"step", "rssi_avg", "throughput_mbps"}.issubset(set(telemetry_df.columns)):
            ws = writer.sheets.get("03_Telemetry_Timeline")
            if ws:
                n = len(telemetry_df)
                cols = {name: idx for idx, name in enumerate(telemetry_df.columns)}
                chart = workbook.add_chart({"type": "line"})
                chart.add_series({
                    "name": "RSSI Avg",
                    "categories": ["03_Telemetry_Timeline", 1, cols["step"], n, cols["step"]],
                    "values": ["03_Telemetry_Timeline", 1, cols["rssi_avg"], n, cols["rssi_avg"]],
                })
                chart.add_series({
                    "name": "Throughput Mbps",
                    "categories": ["03_Telemetry_Timeline", 1, cols["step"], n, cols["step"]],
                    "values": ["03_Telemetry_Timeline", 1, cols["throughput_mbps"], n, cols["throughput_mbps"]],
                })
                chart.set_title({"name": "Telemetry Timeline"})
                chart.set_legend({"position": "bottom"})
                chart.set_size({"width": 720, "height": 320})
                ws.insert_chart("L2", chart)

        evidence_df = data["node_evidence_df"]
        if not evidence_df.empty and {"node_name", "telemetry_readings", "alert_count"}.issubset(set(evidence_df.columns)):
            ws = writer.sheets.get("01_Node_Evidence")
            if ws:
                n = len(evidence_df)
                cols = {name: idx for idx, name in enumerate(evidence_df.columns)}
                chart = workbook.add_chart({"type": "column"})
                chart.add_series({
                    "name": "Telemetry Readings",
                    "categories": ["01_Node_Evidence", 1, cols["node_name"], n, cols["node_name"]],
                    "values": ["01_Node_Evidence", 1, cols["telemetry_readings"], n, cols["telemetry_readings"]],
                })
                chart.add_series({
                    "name": "Alert Count",
                    "categories": ["01_Node_Evidence", 1, cols["node_name"], n, cols["node_name"]],
                    "values": ["01_Node_Evidence", 1, cols["alert_count"], n, cols["alert_count"]],
                })
                chart.set_title({"name": "Evidence Volume by Node"})
                chart.set_legend({"position": "bottom"})
                chart.set_size({"width": 720, "height": 320})
                ws.insert_chart("AA2", chart)

    def _write_dataframe_sheet(self, writer, sheet_name: str, df: pd.DataFrame, formats, freeze=(1, 0)):
        df = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
        if df.empty:
            df = pd.DataFrame([{"note": "No data available for this section in the current simulation snapshot."}])
        df = self._make_excel_safe(df)
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)
        workbook = writer.book
        ws = writer.sheets[sheet_name]
        ws.freeze_panes(*freeze)
        ws.hide_gridlines(2)
        ws.autofilter(0, 0, len(df), max(0, len(df.columns) - 1))

        for c, col in enumerate(df.columns):
            ws.write(0, c, col, formats["header"])
            max_width = max([len(str(col))] + [len(str(v)) for v in df[col].head(80).tolist()])
            if any(x in str(col).lower() for x in ["reason", "description", "message", "evidence", "summary", "actions", "detections", "mix"]):
                width = min(max(max_width + 2, 22), 58)
            else:
                width = min(max(max_width + 2, 10), 24)
            ws.set_column(c, c, width)

        # Apply subtle conditional formatting where it matters.
        cols = {str(c).lower(): idx for idx, c in enumerate(df.columns)}
        for name in ["health_grade", "network_grade", "qos_state", "severity"]:
            if name in cols:
                col = cols[name]
                ws.conditional_format(1, col, len(df), col, {"type": "text", "criteria": "containing", "value": "excellent", "format": formats["good"]})
                ws.conditional_format(1, col, len(df), col, {"type": "text", "criteria": "containing", "value": "ok", "format": formats["good"]})
                ws.conditional_format(1, col, len(df), col, {"type": "text", "criteria": "containing", "value": "warning", "format": formats["warn"]})
                ws.conditional_format(1, col, len(df), col, {"type": "text", "criteria": "containing", "value": "violated", "format": formats["bad"]})
                ws.conditional_format(1, col, len(df), col, {"type": "text", "criteria": "containing", "value": "critical", "format": formats["bad"]})

    # ------------------------------------------------------------------
    # Utility functions
    # ------------------------------------------------------------------

    def _unwrap(self, obj):
        if not isinstance(obj, dict):
            return obj
        for key in ["plan_result", "result", "data"]:
            if isinstance(obj.get(key), dict):
                return self._unwrap(obj[key])
        return obj

    def _extract_nodes(self, plan):
        plan = self._unwrap(plan) or {}
        if not isinstance(plan, dict):
            return []
        for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
            if isinstance(plan.get(key), list):
                return plan[key]
        return []

    def _list_from(self, obj, key):
        return obj.get(key, []) if isinstance(obj, dict) and isinstance(obj.get(key), list) else []

    def _safe_dataframe(self, rows):
        if not isinstance(rows, list):
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def _make_excel_safe(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for col in out.columns:
            out[col] = out[col].apply(self._safe_cell)
        return out

    def _safe_cell(self, value):
        if value is None:
            return ""
        if isinstance(value, (dict, list, tuple)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return ""
        return value

    def _node_id(self, node) -> Optional[int]:
        if not isinstance(node, dict):
            return None
        return self._safe_int(node.get("id", node.get("node_id")))

    def _safe_int(self, value):
        try:
            if value in [None, "", "-"]:
                return None
            text = str(value)
            digits = "".join(ch for ch in text if ch.isdigit())
            if digits and not text.strip().replace(".", "", 1).isdigit():
                return int(digits)
            return int(float(value))
        except Exception:
            return None

    def _safe_float(self, value):
        try:
            if value in [None, "", "-"]:
                return None
            return float(value)
        except Exception:
            return None

    def _avg(self, values):
        nums = [self._safe_float(v) for v in values if self._safe_float(v) is not None]
        if not nums:
            return None
        return sum(nums) / len(nums)

    def _round(self, value, digits=2):
        value = self._safe_float(value)
        if value is None:
            return ""
        return round(value, digits)

    def _network_grade(self, rssi, snr, loss, alerts_count):
        rssi = self._safe_float(rssi)
        snr = self._safe_float(snr)
        loss = self._safe_float(loss)
        score = 100
        if rssi is not None:
            if rssi < -70:
                score -= 25
            elif rssi < -62:
                score -= 12
        if snr is not None:
            if snr < 20:
                score -= 25
            elif snr < 28:
                score -= 10
        if loss is not None:
            if loss > 5:
                score -= 18
            elif loss > 1.5:
                score -= 8
        score -= min(25, int(alerts_count or 0) * 3)
        if score >= 88:
            return "Excellent"
        if score >= 75:
            return "Good"
        if score >= 60:
            return "Warning"
        return "Critical"

    def _node_grade(self, rssi, snr, loss, alert_count):
        rssi = self._safe_float(rssi)
        snr = self._safe_float(snr)
        loss = self._safe_float(loss)
        score = 100
        if rssi is not None:
            if rssi < -72:
                score -= 28
            elif rssi < -64:
                score -= 14
        if snr is not None:
            if snr < 18:
                score -= 28
            elif snr < 26:
                score -= 12
        if loss is not None:
            if loss > 5:
                score -= 18
            elif loss > 1.5:
                score -= 8
        score -= min(18, int(alert_count or 0) * 4)
        if score >= 88:
            return "Excellent"
        if score >= 75:
            return "Good"
        if score >= 60:
            return "Warning"
        return "Critical"

    def _counter_text(self, counter: Counter):
        if not counter:
            return "-"
        return ", ".join(f"{k}:{v}" for k, v in counter.most_common())
