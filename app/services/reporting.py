from pathlib import Path
from datetime import datetime

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


class ReportGenerator:
    def __init__(self):
        self.output_dir = Path("data/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_excel(self, state: dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = self.output_dir / f"structifi_report_{timestamp}.xlsx"

        rooms_df = pd.DataFrame(state.get("rooms", []))
        nodes_df = pd.DataFrame(state.get("nodes", []))
        clients_df = pd.DataFrame(state.get("clients", []))
        alerts_df = pd.DataFrame(state.get("alerts", []))
        decisions_df = pd.DataFrame(state.get("decisions", []))
        events_df = pd.DataFrame(state.get("events", []))
        access_df = pd.DataFrame(state.get("access_matrix", []))

        ai = state.get("ai_output", {})
        health_summary = ai.get("health_summary", {})
        recommendations = ai.get("recommendations", [])

        summary_df = pd.DataFrame([{
            "simulation_source": state.get("simulation_source", "unknown"),
            "rooms_count": len(state.get("rooms", [])),
            "nodes_count": len(state.get("nodes", [])),
            "clients_count": len(state.get("clients", [])),
            "alerts_count": len(state.get("alerts", [])),
            "events_count": len(state.get("events", [])),
            "ai_status": health_summary.get("status", "unknown"),
            "anomaly_score": health_summary.get("anomaly_score", 0),
            "critical_alerts": health_summary.get("critical_alerts", 0),
            "warning_alerts": health_summary.get("warning_alerts", 0),
            "high_load_nodes": health_summary.get("high_load_nodes", 0),
            "down_nodes": health_summary.get("down_nodes", 0),
            "degraded_nodes": health_summary.get("degraded_nodes", 0),
        }])

        recommendations_df = pd.DataFrame(recommendations)

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            summary_df.to_excel(writer, index=False, sheet_name="Summary")
            rooms_df.to_excel(writer, index=False, sheet_name="Rooms")
            nodes_df.to_excel(writer, index=False, sheet_name="Nodes")
            clients_df.to_excel(writer, index=False, sheet_name="Clients")
            alerts_df.to_excel(writer, index=False, sheet_name="Alerts")
            decisions_df.to_excel(writer, index=False, sheet_name="Decisions")
            events_df.to_excel(writer, index=False, sheet_name="Events")
            access_df.to_excel(writer, index=False, sheet_name="AccessMatrix")
            recommendations_df.to_excel(writer, index=False, sheet_name="AI_Recs")

        return str(file_path).replace("\\", "/")

    def export_pdf(self, state: dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = self.output_dir / f"structifi_report_{timestamp}.pdf"

        c = canvas.Canvas(str(file_path), pagesize=A4)
        width, height = A4

        ai = state.get("ai_output", {})
        health = ai.get("health_summary", {})

        y = height - 50
        line_gap = 18

        def write_line(text, bold=False):
            nonlocal y
            if y < 60:
                c.showPage()
                y = height - 50
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
            c.drawString(40, y, str(text))
            y -= line_gap

        write_line("StructiFi Report", bold=True)
        write_line(f"Generated: {timestamp}")
        write_line("")

        write_line("System Summary", bold=True)
        write_line(f"Simulation Source: {state.get('simulation_source', 'unknown')}")
        write_line(f"Rooms: {len(state.get('rooms', []))}")
        write_line(f"Nodes: {len(state.get('nodes', []))}")
        write_line(f"Clients: {len(state.get('clients', []))}")
        write_line(f"Alerts: {len(state.get('alerts', []))}")
        write_line(f"Events: {len(state.get('events', []))}")
        write_line("")

        write_line("AI Summary", bold=True)
        write_line(f"Status: {health.get('status', 'unknown')}")
        write_line(f"Anomaly Score: {health.get('anomaly_score', 0)}")
        write_line(f"Critical Alerts: {health.get('critical_alerts', 0)}")
        write_line(f"Warning Alerts: {health.get('warning_alerts', 0)}")
        write_line(f"High Load Nodes: {health.get('high_load_nodes', 0)}")
        write_line(f"Down Nodes: {health.get('down_nodes', 0)}")
        write_line(f"Degraded Nodes: {health.get('degraded_nodes', 0)}")
        write_line("")

        write_line("Top Nodes", bold=True)
        for node in state.get("nodes", [])[:10]:
            write_line(
                f'{node.get("name")} | Ch {node.get("channel")} | '
                f'Status {node.get("status")} | Load {node.get("load", 0)}'
            )

        write_line("")
        write_line("AI Recommendations", bold=True)
        recs = ai.get("recommendations", [])
        if not recs:
            write_line("No recommendations available.")
        else:
            for rec in recs[:12]:
                write_line(f'- {rec.get("type", "info").upper()}: {rec.get("message", "")}')

        c.save()
        return str(file_path).replace("\\", "/")