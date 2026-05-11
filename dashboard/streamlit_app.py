import requests
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches

API_URL = st.secrets.get("API_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="StructiFi CAD Command Center",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    :root {
        --sf-bg: #f5f5f7;
        --sf-card: rgba(255, 255, 255, 0.82);
        --sf-card-solid: #ffffff;
        --sf-text: #1d1d1f;
        --sf-muted: #6e6e73;
        --sf-border: rgba(0, 0, 0, 0.08);
        --sf-blue: #007aff;
        --sf-blue-dark: #005ecb;
        --sf-green: #34c759;
        --sf-orange: #ff9f0a;
        --sf-red: #ff3b30;
        --sf-shadow: 0 18px 45px rgba(0, 0, 0, 0.08);
        --sf-shadow-soft: 0 10px 28px rgba(0, 0, 0, 0.06);
    }

    .stApp {
        background:
            radial-gradient(circle at 12% 8%, rgba(0, 122, 255, 0.14), transparent 32%),
            radial-gradient(circle at 88% 0%, rgba(52, 199, 89, 0.10), transparent 30%),
            linear-gradient(180deg, #fbfbfd 0%, #f5f5f7 44%, #eef1f5 100%);
        color: var(--sf-text);
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", sans-serif;
    }

    .block-container {
        max-width: 1760px;
        padding-top: 1.05rem;
        padding-bottom: 1.4rem;
    }

    .hero {
        position: relative;
        overflow: hidden;
        background:
            linear-gradient(135deg, rgba(255,255,255,0.94) 0%, rgba(247,249,252,0.86) 56%, rgba(232,241,255,0.88) 100%);
        color: var(--sf-text);
        border-radius: 34px;
        padding: 34px 36px;
        margin-bottom: 18px;
        border: 1px solid rgba(255,255,255,0.85);
        box-shadow: var(--sf-shadow);
        backdrop-filter: blur(24px);
    }

    .hero::after {
        content: "";
        position: absolute;
        right: -110px;
        top: -120px;
        width: 320px;
        height: 320px;
        background: radial-gradient(circle, rgba(0,122,255,0.25), transparent 62%);
        pointer-events: none;
    }

    .hero h1 {
        margin: 0;
        font-size: 3.05rem;
        font-weight: 800;
        letter-spacing: -1.8px;
        line-height: 1.02;
    }

    .hero p {
        margin-top: 12px;
        max-width: 820px;
        color: var(--sf-muted);
        font-size: 1.04rem;
        line-height: 1.55;
    }

    .hero .workflow-pill {
        display: inline-flex;
        gap: 8px;
        flex-wrap: wrap;
        align-items: center;
        margin-top: 18px;
        padding: 8px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.78);
        border: 1px solid var(--sf-border);
        color: #3a3a3c;
        font-size: 0.86rem;
        font-weight: 700;
        box-shadow: 0 8px 18px rgba(0,0,0,0.05);
    }

    .card, .export-card, .room-card, .node-card {
        background: var(--sf-card);
        color: var(--sf-text);
        border-radius: 28px;
        padding: 20px;
        border: 1px solid rgba(255,255,255,0.82);
        box-shadow: var(--sf-shadow-soft);
        backdrop-filter: blur(22px);
        margin-bottom: 14px;
    }

    .card {
        min-height: 126px;
    }

    .metric-title {
        font-size: 0.84rem;
        color: var(--sf-muted);
        margin-bottom: 12px;
        font-weight: 700;
        letter-spacing: 0.1px;
    }

    .metric-value {
        font-size: 2.18rem;
        font-weight: 800;
        color: var(--sf-text);
        line-height: 1.05;
        letter-spacing: -1px;
        word-break: break-word;
        overflow-wrap: anywhere;
    }

    .section-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: var(--sf-text);
        margin: 18px 0 12px;
        letter-spacing: -0.45px;
    }

    .subtle {
        color: var(--sf-muted);
        font-size: 0.95rem;
    }

    .room-card {
        background: rgba(255,255,255,0.72);
        border-radius: 22px;
        padding: 16px 18px;
        color: #1d1d1f;
        border: 1px solid var(--sf-border);
    }

    .node-card {
        background: linear-gradient(145deg, rgba(255,255,255,0.94) 0%, rgba(238,246,255,0.86) 100%);
        border: 1px solid rgba(0,122,255,0.18);
        color: var(--sf-text);
    }

    .status-pill {
        display: inline-block;
        padding: 7px 13px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.1px;
    }

    .status-ok {
        background: rgba(52, 199, 89, 0.14);
        color: #168a3d;
        border: 1px solid rgba(52,199,89,0.18);
    }

    .status-warn {
        background: rgba(255, 159, 10, 0.16);
        color: #a36200;
        border: 1px solid rgba(255,159,10,0.18);
    }

    .status-bad {
        background: rgba(255, 59, 48, 0.14);
        color: #c92a22;
        border: 1px solid rgba(255,59,48,0.18);
    }

    section[data-testid="stSidebar"] {
        background: rgba(255,255,255,0.72);
        border-right: 1px solid rgba(0,0,0,0.08);
        backdrop-filter: blur(26px);
    }

    section[data-testid="stSidebar"] * {
        color: var(--sf-text);
    }

    .stButton > button {
        border-radius: 999px;
        font-weight: 800;
        min-height: 44px;
        background: linear-gradient(180deg, #0a84ff 0%, #007aff 100%);
        color: white !important;
        border: 1px solid rgba(0,122,255,0.28);
        box-shadow: 0 8px 20px rgba(0,122,255,0.20);
        transition: all 0.16s ease;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        background: linear-gradient(180deg, #2795ff 0%, #007aff 100%);
        border: 1px solid rgba(0,122,255,0.45);
    }

    .stDownloadButton > button,
    .stLinkButton > a {
        border-radius: 999px !important;
        font-weight: 800 !important;
        min-height: 42px !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(255,255,255,0.64);
        padding: 8px;
        border-radius: 18px;
        border: 1px solid rgba(0,0,0,0.06);
        box-shadow: 0 6px 18px rgba(0,0,0,0.04);
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        color: #3a3a3c;
        border-radius: 14px;
        padding: 10px 16px;
        font-weight: 800;
    }

    .stTabs [aria-selected="true"] {
        background-color: white !important;
        color: #007aff !important;
        box-shadow: 0 5px 14px rgba(0,0,0,0.08);
    }

    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.70);
        border: 1px solid rgba(0,0,0,0.06);
        border-radius: 20px;
        padding: 12px 14px;
        box-shadow: 0 5px 16px rgba(0,0,0,0.04);
    }

    div[data-testid="stMetricLabel"] {
        color: var(--sf-muted);
    }

    div[data-testid="stMetricValue"] {
        color: var(--sf-text);
        font-weight: 800;
    }

    .stAlert {
        border-radius: 22px;
    }

    img {
        border-radius: 22px;
        box-shadow: 0 12px 34px rgba(0,0,0,0.08);
    }

    pre, code {
        border-radius: 18px !important;
    }
</style>
""", unsafe_allow_html=True)


def safe_get_json(url, default=None):
    try:
        r = requests.get(url, timeout=20)
        if r.headers.get("content-type", "").startswith("application/json"):
            data = r.json()
        else:
            data = {"detail": r.text}
        if not r.ok:
            return data
        return data
    except Exception as e:
        return {"detail": str(e)} if default is None else default


def safe_post_json(url, payload=None, files=None, default=None):
    try:
        if files is not None:
            r = requests.post(url, files=files, timeout=120)
        else:
            r = requests.post(url, json=payload, timeout=120)

        if r.headers.get("content-type", "").startswith("application/json"):
            data = r.json()
        else:
            data = {"detail": r.text}

        if not r.ok:
            return data
        return data
    except Exception as e:
        return {"detail": str(e)} if default is None else default


def upload_cad(file_obj):
    files = {
        "file": (file_obj.name, file_obj.getvalue(), file_obj.type or "application/octet-stream")
    }
    return safe_post_json(f"{API_URL}/cad/upload", files=files, default={})


def extract_rooms():
    return safe_post_json(f"{API_URL}/cad/extract-rooms", default={})


def plan_nodes():
    return safe_post_json(f"{API_URL}/cad/plan-nodes", default={})


def render_plan():
    return safe_post_json(f"{API_URL}/cad/render-plan", default={})


def render_heatmap():
    return safe_post_json(f"{API_URL}/cad/render-heatmap", default={})


def render_extracted_rooms_image():
    return safe_post_json(f"{API_URL}/cad/render-extract-rooms", default={})


def apply_plan_to_simulation():
    return safe_post_json(f"{API_URL}/simulation/apply-cad-plan", default={})


def next_step():
    return safe_post_json(f"{API_URL}/simulation/step", default={})


def reset_simulation():
    return safe_post_json(f"{API_URL}/simulation/reset", default={})


def get_latest_cad():
    return safe_get_json(f"{API_URL}/cad/latest", {"cad": None}).get("cad")


def get_latest_rooms():
    data = safe_get_json(f"{API_URL}/cad/latest-rooms", {"rooms_result": None})
    return data.get("rooms_result")


def get_latest_plan():
    data = safe_get_json(f"{API_URL}/cad/latest-plan", {"plan_result": None})
    return data.get("plan_result")


def get_ai_summary():
    return safe_get_json(f"{API_URL}/ai/summary", {"health_summary": {}, "recommendations": []})


def get_sim_state():
    return safe_get_json(f"{API_URL}/simulation/state", {
        "simulation_source": "unknown",
        "building": None,
        "node_plan": [],
        "node_runtime": [],
        "clients": [],
        "events": [],
        "controller_state": {"decisions": []},
        "security_state": {"alerts": [], "access_matrix": []},
        "ai_output": {"health_summary": {}, "recommendations": []},
        "planning_summary": {}
    })


def get_rendered_url(file_name):
    return f"{API_URL}/cad/rendered/{file_name}"




def _dashboard_plan_nodes(plan):
    if not isinstance(plan, dict):
        return []

    for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
        value = plan.get(key)
        if isinstance(value, list):
            return value

    result = plan.get("result")
    if isinstance(result, dict):
        for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
            value = result.get(key)
            if isinstance(value, list):
                return value

    data = plan.get("data")
    if isinstance(data, dict):
        for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


def _dashboard_summary_value(summary, keys, default=0):
    if not isinstance(summary, dict):
        return default

    for key in keys:
        value = summary.get(key)
        if value is not None:
            return value

    return default


def _dashboard_metric_number(value, default=0):
    try:
        if value is None:
            return default
        number = float(value)
        if number.is_integer():
            return int(number)
        return round(number, 2)
    except Exception:
        return value if value not in [None, ""] else default

def get_excel_export_url():
    return f"{API_URL}/export/excel"


def get_pdf_export_url():
    return f"{API_URL}/export/pdf"


def node_color(node):
    status = node.get("status", "active")
    if status in ["down", "offline"]:
        return "red"
    if status == "degraded":
        return "orange"
    return "green"


def role_color(role):
    if role == "management":
        return "purple"
    if role == "guest":
        return "brown"
    return "deepskyblue"


def render_status_badge(text):
    t = str(text).lower()
    if t in ["stable", "active", "ok", "healthy", "online"]:
        css = "status-ok"
    elif t in ["warning", "degraded", "medium"]:
        css = "status-warn"
    else:
        css = "status-bad"
    st.markdown(f'<span class="status-pill {css}">{text}</span>', unsafe_allow_html=True)


def render_interactive_plan(building_data, sim_state):
    """
    Interactive Simulation Overlay.

    This view is allowed to show nodes and clients.
    It uses the real CAD walls so it visually matches the AI Planning render,
    but it is separate from the Extracted Rooms view.
    """
    if not building_data:
        st.info("No building model available to draw.")
        return

    rooms = building_data.get("rooms", []) or []
    walls = building_data.get("walls", []) or []
    bounds = building_data.get("bounds", {}) or {}
    clients = sim_state.get("clients", []) or []

    if not rooms and not walls:
        st.info("No CAD building data available to draw.")
        return

    min_x = float(bounds.get("min_x", min([r.get("x", 0.0) for r in rooms], default=0.0)))
    min_y = float(bounds.get("min_y", min([r.get("y", 0.0) for r in rooms], default=0.0)))
    max_x = float(bounds.get("max_x", max([r.get("x", 0.0) + r.get("width", 0.0) for r in rooms], default=10.0)))
    max_y = float(bounds.get("max_y", max([r.get("y", 0.0) + r.get("height", 0.0) for r in rooms], default=10.0)))

    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    aspect = width / max(height, 1e-9)

    fig_w = 13.2
    fig_h = max(5.8, min(9.5, fig_w / max(aspect, 0.55)))

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_facecolor("white")

    _draw_dashboard_room_fills(ax, rooms)
    _draw_dashboard_cad_walls(ax, walls)
    _draw_dashboard_room_outlines_and_labels(ax, rooms)
    _draw_dashboard_planned_nodes(ax, sim_state)
    _draw_dashboard_clients(ax, clients)

    pad_x = max(width * 0.025, 0.25)
    pad_y = max(height * 0.025, 0.25)

    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("Interactive CAD Simulation Overlay", fontsize=9)
    ax.grid(True, linewidth=0.25, alpha=0.18)

    st.pyplot(fig, clear_figure=True)


def render_extracted_rooms_overlay(building_data):
    """
    Extracted Rooms preview.

    Important rule:
    This view must never draw nodes, beam arcs, clients, heatmap, or planning output.
    It is only for validating extracted rooms, corridors, labels, and CAD walls.
    """
    if not building_data:
        st.info("No extracted room model available to draw.")
        return

    rooms = building_data.get("rooms", []) or []
    walls = building_data.get("walls", []) or []
    bounds = building_data.get("bounds", {}) or {}

    if not rooms and not walls:
        st.info("No extracted rooms available to draw.")
        return

    min_x = float(bounds.get("min_x", min([r.get("x", 0.0) for r in rooms], default=0.0)))
    min_y = float(bounds.get("min_y", min([r.get("y", 0.0) for r in rooms], default=0.0)))
    max_x = float(bounds.get("max_x", max([r.get("x", 0.0) + r.get("width", 0.0) for r in rooms], default=10.0)))
    max_y = float(bounds.get("max_y", max([r.get("y", 0.0) + r.get("height", 0.0) for r in rooms], default=10.0)))

    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    aspect = width / max(height, 1e-9)

    fig_w = 13.2
    fig_h = max(5.8, min(9.5, fig_w / max(aspect, 0.55)))

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_facecolor("white")

    _draw_dashboard_room_fills(ax, rooms)
    _draw_dashboard_cad_walls(ax, walls)
    _draw_dashboard_room_outlines_and_labels(ax, rooms)

    pad_x = max(width * 0.025, 0.25)
    pad_y = max(height * 0.025, 0.25)

    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("Extracted Rooms - CAD Wall Overlay", fontsize=9)
    ax.grid(True, linewidth=0.25, alpha=0.18)

    st.pyplot(fig, clear_figure=True)


def _draw_dashboard_room_fills(ax, rooms):
    for room in rooms:
        room_type = str(room.get("room_type", "unknown")).lower()
        pts = _dashboard_polygon_points(room.get("polygon", []) or [])

        alpha = 0.075
        if room_type == "corridor":
            alpha = 0.13
        elif room_type in ["bathroom", "service", "storage"]:
            alpha = 0.095

        if len(pts) >= 3:
            patch = patches.Polygon(
                pts,
                closed=True,
                facecolor=_dashboard_room_fill(room_type),
                edgecolor="none",
                alpha=alpha,
                zorder=2,
            )
            ax.add_patch(patch)
        else:
            x = float(room.get("x", 0.0))
            y = float(room.get("y", 0.0))
            w = float(room.get("width", 0.0))
            h = float(room.get("height", 0.0))
            rect = patches.Rectangle(
                (x, y),
                w,
                h,
                facecolor=_dashboard_room_fill(room_type),
                edgecolor="none",
                alpha=alpha,
                zorder=2,
            )
            ax.add_patch(rect)


def _draw_dashboard_cad_walls(ax, walls):
    for wall in walls:
        try:
            x1 = float(wall.get("x1", 0.0))
            y1 = float(wall.get("y1", 0.0))
            x2 = float(wall.get("x2", 0.0))
            y2 = float(wall.get("y2", 0.0))
        except Exception:
            continue

        if ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 < 0.01:
            continue

        layer = str(wall.get("layer", "")).lower()
        lw = 1.45
        if "healed" in layer:
            lw = 1.0
        if "door" in layer or "window" in layer:
            lw = 0.85

        ax.plot(
            [x1, x2],
            [y1, y2],
            color="#111111",
            linewidth=lw,
            solid_capstyle="round",
            zorder=30,
        )


def _draw_dashboard_room_outlines_and_labels(ax, rooms):
    placed_labels = []

    for room in sorted(rooms, key=lambda r: float(r.get("area", 0.0) or 0.0), reverse=True):
        room_type = str(room.get("room_type", "unknown")).lower()
        pts = _dashboard_polygon_points(room.get("polygon", []) or [])

        if len(pts) >= 3:
            outline = patches.Polygon(
                pts,
                closed=True,
                facecolor="none",
                edgecolor=_dashboard_room_edge(room_type),
                linewidth=0.65,
                alpha=0.42,
                zorder=35,
            )
            ax.add_patch(outline)

        cx = float(room.get("center_x", room.get("x", 0.0)) or 0.0)
        cy = float(room.get("center_y", room.get("y", 0.0)) or 0.0)

        if _dashboard_label_collides(cx, cy, placed_labels, threshold=0.34):
            continue

        placed_labels.append((cx, cy))

        name = str(room.get("label_text") or room.get("name") or "room")
        zone = str(room.get("zone", "unknown"))
        expected = room.get("expected_clients", 0)
        label = _dashboard_short_room_label(name, room_type, zone, expected)

        ax.text(
            cx,
            cy,
            label,
            ha="center",
            va="center",
            fontsize=5.6,
            color="#202020",
            zorder=55,
            bbox=dict(
                boxstyle="round,pad=0.12",
                facecolor="white",
                edgecolor="none",
                alpha=0.70,
            ),
        )


def _draw_dashboard_planned_nodes(ax, sim_state):
    planned_nodes = _dashboard_get_planned_nodes(sim_state)

    for idx, node in enumerate(planned_nodes, start=1):
        x = _dashboard_node_x(node)
        y = _dashboard_node_y(node)

        if x is None or y is None:
            continue

        node_id = node.get("node_id") or node.get("id") or idx
        display_id = _dashboard_short_node_id(node_id, idx)
        room_id = node.get("room_id", "")
        tx_power = node.get("tx_power_dbm", node.get("tx_power", ""))

        direction = float(
            node.get(
                "beam_direction_deg",
                node.get(
                    "antenna_direction_deg",
                    node.get("direction_deg", 0.0),
                ),
            )
            or 0.0
        )
        beamwidth = float(
            node.get(
                "beamwidth_deg",
                node.get(
                    "beam_width_deg",
                    node.get("antenna_beamwidth", 80.0),
                ),
            )
            or 80.0
        )

        ax.scatter(
            [x],
            [y],
            s=96,
            marker="o",
            color="#0B3D91",
            edgecolors="white",
            linewidths=1.25,
            zorder=80,
        )
        ax.text(
            x,
            y,
            "N",
            color="white",
            fontsize=6.2,
            ha="center",
            va="center",
            fontweight="bold",
            zorder=85,
        )

        _dashboard_draw_beam_arcs(ax, x, y, direction, beamwidth)

        label = f"Node {display_id}"
        if room_id != "":
            label += f"\nR{room_id}"
        if tx_power != "":
            label += f"\n{tx_power} dBm"

        ax.text(
            x + 0.12,
            y + 0.12,
            label,
            fontsize=5.0,
            color="#0B1F3A",
            ha="left",
            va="bottom",
            zorder=86,
            bbox=dict(
                boxstyle="round,pad=0.12",
                facecolor="white",
                edgecolor="#C8D3E5",
                alpha=0.84,
            ),
        )


def _draw_dashboard_clients(ax, clients):
    for client in clients:
        try:
            cx = float(client["x"])
            cy = float(client["y"])
        except Exception:
            continue

        ax.scatter(
            [cx],
            [cy],
            marker="o",
            s=36,
            color=role_color(client.get("role", "staff")),
            edgecolors="white",
            linewidths=0.6,
            alpha=0.70,
            zorder=70,
        )


def _dashboard_get_planned_nodes(sim_state):
    nodes = sim_state.get("node_plan", []) or []
    if nodes:
        return nodes

    try:
        if latest_plan:
            for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
                value = latest_plan.get(key)
                if isinstance(value, list) and value:
                    return value
    except Exception:
        pass

    runtime_nodes = sim_state.get("node_runtime", []) or []
    if runtime_nodes:
        return runtime_nodes

    return []


def _dashboard_polygon_points(polygon):
    pts = []
    for p in polygon:
        try:
            if isinstance(p, dict):
                pts.append((float(p.get("x", 0.0)), float(p.get("y", 0.0))))
            else:
                x = getattr(p, "x", None)
                y = getattr(p, "y", None)
                if x is not None and y is not None:
                    pts.append((float(x), float(y)))
        except Exception:
            continue
    return pts


def _dashboard_node_x(node):
    for key in ["x", "node_x", "placement_x", "center_x"]:
        if key in node:
            try:
                return float(node[key])
            except Exception:
                pass

    pos = node.get("position")
    if isinstance(pos, dict) and "x" in pos:
        try:
            return float(pos["x"])
        except Exception:
            pass

    placement = node.get("placement")
    if isinstance(placement, dict) and "x" in placement:
        try:
            return float(placement["x"])
        except Exception:
            pass

    return None


def _dashboard_node_y(node):
    for key in ["y", "node_y", "placement_y", "center_y"]:
        if key in node:
            try:
                return float(node[key])
            except Exception:
                pass

    pos = node.get("position")
    if isinstance(pos, dict) and "y" in pos:
        try:
            return float(pos["y"])
        except Exception:
            pass

    placement = node.get("placement")
    if isinstance(placement, dict) and "y" in placement:
        try:
            return float(placement["y"])
        except Exception:
            pass

    return None


def _dashboard_draw_beam_arcs(ax, x, y, direction, beamwidth):
    start = direction - beamwidth / 2.0
    end = direction + beamwidth / 2.0

    for radius, lw, alpha in [
        (0.55, 1.0, 0.85),
        (0.90, 1.0, 0.70),
        (1.25, 1.0, 0.55),
    ]:
        arc = patches.Arc(
            (x, y),
            width=radius * 2,
            height=radius * 2,
            angle=0,
            theta1=start,
            theta2=end,
            linewidth=lw,
            color="#1464C0",
            alpha=alpha,
            zorder=78,
        )
        ax.add_patch(arc)


def _dashboard_short_node_id(raw_id, idx):
    text = str(raw_id)
    if text.startswith("SF-N"):
        text = text.replace("SF-N", "N")
    if len(text) > 8:
        return f"N{idx}"
    if text.upper().startswith("N"):
        return text.upper()
    return f"N{text}"


def _dashboard_short_room_label(name, room_type, zone, expected):
    clean = str(name).replace("_", " ").strip()
    if len(clean) > 18:
        clean = clean[:16] + "..."
    return f"{clean}\n[{zone}]\n{room_type}\nExp {expected}"


def _dashboard_label_collides(x, y, placed, threshold):
    for px, py in placed:
        if ((x - px) ** 2 + (y - py) ** 2) ** 0.5 < threshold:
            return True
    return False


def _dashboard_room_fill(room_type):
    return {
        "corridor": "#F6C85F",
        "bathroom": "#9DD9D2",
        "service": "#BFC7D5",
        "storage": "#BFC7D5",
        "server_room": "#FF9F80",
        "meeting": "#90CAF9",
        "reception": "#C5E1A5",
        "open_area": "#D7BDE2",
        "office": "#A7C7E7",
        "kitchen": "#FAD7A0",
    }.get(room_type, "#D6EAF8")


def _dashboard_room_edge(room_type):
    return {
        "corridor": "#B7791F",
        "bathroom": "#278A86",
        "service": "#5D6D7E",
        "storage": "#5D6D7E",
        "server_room": "#C0392B",
        "meeting": "#2471A3",
        "reception": "#558B2F",
        "open_area": "#7D3C98",
        "office": "#2E86C1",
        "kitchen": "#B9770E",
    }.get(room_type, "#2874A6")

if "extracted_img" not in st.session_state:
    st.session_state.extracted_img = None

if "plan_img" not in st.session_state:
    st.session_state.plan_img = None

if "heatmap_img" not in st.session_state:
    st.session_state.heatmap_img = None


with st.sidebar:
    st.markdown("## CAD Workflow")

    uploaded_cad = st.file_uploader(
        "Upload DXF or DWG",
        type=["dxf", "dwg"],
        key="cad_upload"
    )

    if uploaded_cad is not None and st.button("Upload CAD File", use_container_width=True):
        result = upload_cad(uploaded_cad)
        if result.get("cad"):
            st.session_state.extracted_img = None
            st.session_state.extracted_img = None
            st.session_state.plan_img = None
            st.session_state.heatmap_img = None
            st.success("CAD file uploaded successfully")
            st.rerun()
        else:
            st.error(result.get("detail", "CAD upload failed"))

    if st.button("Extract Rooms", use_container_width=True):
        result = extract_rooms()
        if result.get("result"):
            rendered = render_extracted_rooms_image()
            if rendered.get("image"):
                st.session_state.extracted_img = rendered["image"]
            else:
                # Fallback name used by CADVisualizer.render_rooms_overlay()
                st.session_state.extracted_img = {
                    "file_name": "cad_extract_rooms.png",
                    "url": "/cad/rendered/cad_extract_rooms.png",
                    "kind": "extract_rooms",
                }
            st.success("Rooms extracted")
            st.rerun()
        else:
            st.error(result.get("detail", "Extraction failed"))

    if st.button("Run AI Planning", use_container_width=True):
        result = plan_nodes()
        if result.get("result"):
            st.success("Planning completed")
            st.rerun()
        else:
            st.error(result.get("detail", "Planning failed"))

    if st.button("Render Plan Image", use_container_width=True):
        result = render_plan()
        if result.get("image"):
            st.session_state.plan_img = result["image"]
            st.success("Plan rendered")
            st.rerun()
        else:
            st.error(result.get("detail", "Render failed"))

    if st.button("Render Unified Heatmap", use_container_width=True):
        result = render_heatmap()
        if result.get("image"):
            st.session_state.heatmap_img = result["image"]
            st.success("Heatmap rendered")
            st.rerun()
        else:
            st.error(result.get("detail", "Heatmap failed"))

    st.markdown("---")

    if st.button("Apply CAD Plan to Simulation", use_container_width=True):
        result = apply_plan_to_simulation()
        if result.get("state"):
            st.success("CAD plan applied to simulation")
            st.rerun()
        else:
            st.error(result.get("detail", "Apply failed"))

    if st.button("Next Simulation Step", use_container_width=True):
        result = next_step()
        if result.get("step") is not None:
            st.success("Simulation advanced")
            st.rerun()
        else:
            st.error(result.get("detail", "Step failed"))

    if st.button("Reset Simulation", use_container_width=True):
        result = reset_simulation()
        if result.get("state"):
            st.session_state.extracted_img = None
            st.session_state.plan_img = None
            st.session_state.heatmap_img = None
            st.success("Simulation reset")
            st.rerun()
        else:
            st.error(result.get("detail", "Reset failed"))

    st.markdown("---")
    st.markdown("### Export Center")
    st.link_button("Download Excel Report", get_excel_export_url(), use_container_width=True)
    st.link_button("Download PDF Report", get_pdf_export_url(), use_container_width=True)


latest_cad = get_latest_cad()
latest_rooms = get_latest_rooms()
latest_plan = get_latest_plan()
ai_summary = get_ai_summary()
sim_state = get_sim_state()

building_data = sim_state.get("building")
if not building_data and latest_rooms:
    building_data = latest_rooms

plan_nodes_list = _dashboard_plan_nodes(latest_plan)
node_runtime = sim_state.get("node_runtime", []) or []
clients = sim_state.get("clients", []) or []
security_state = sim_state.get("security_state", {}) or {}
alerts = security_state.get("alerts", []) or []
ai_output = sim_state.get("ai_output", ai_summary) or {}
health = ai_output.get("health_summary", {}) or {}
recommendations = ai_output.get("recommendations", []) or []
controller_state = sim_state.get("controller_state", {}) or {}
decisions = controller_state.get("decisions", []) or []
summary = latest_plan.get("summary", {}) if latest_plan else {}

extracted_rooms_count = len(latest_rooms.get("rooms", [])) if latest_rooms else 0
suggested_nodes_count = 0
if latest_plan:
    suggested_nodes_count = latest_plan.get("nodes_count")
    if suggested_nodes_count is None:
        suggested_nodes_count = len(plan_nodes_list)
suggested_nodes_count = _dashboard_metric_number(suggested_nodes_count, 0)
placement = _dashboard_metric_number(
    _dashboard_summary_value(
        summary,
        ["placement_score", "coverage_score", "avg_coverage_percent", "overall_score", "nodes_planned"],
        0,
    ),
    0,
)

st.markdown("""
<div class="hero">
    <h1>StructFi Command Center</h1>
    <p>Apple-style workflow dashboard for CAD extraction, AI node planning, RF heatmap validation, live simulation, AI monitoring, IDS alerts, and mobile-ready backend outputs.</p>
    <div class="workflow-pill">Upload → Extract → Plan → Heatmap → Simulate → AI / IDS → Export</div>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# Executive metrics
# -------------------------------------------------------------------
metric_cols = st.columns(6)
with metric_cols[0]:
    st.markdown(f"""
    <div class="card">
        <div class="metric-title">CAD Source</div>
        <div class="metric-value">{latest_cad.get("source_format", "NONE") if latest_cad else "NONE"}</div>
    </div>
    """, unsafe_allow_html=True)
with metric_cols[1]:
    st.markdown(f"""
    <div class="card">
        <div class="metric-title">Rooms</div>
        <div class="metric-value">{extracted_rooms_count}</div>
    </div>
    """, unsafe_allow_html=True)
with metric_cols[2]:
    st.markdown(f"""
    <div class="card">
        <div class="metric-title">Suggested Nodes</div>
        <div class="metric-value">{suggested_nodes_count}</div>
    </div>
    """, unsafe_allow_html=True)
with metric_cols[3]:
    st.markdown(f"""
    <div class="card">
        <div class="metric-title">Placement Score</div>
        <div class="metric-value">{placement}</div>
    </div>
    """, unsafe_allow_html=True)
with metric_cols[4]:
    st.markdown(f"""
    <div class="card">
        <div class="metric-title">Clients</div>
        <div class="metric-value">{len(clients)}</div>
    </div>
    """, unsafe_allow_html=True)
with metric_cols[5]:
    st.markdown(f"""
    <div class="card">
        <div class="metric-title">Alerts</div>
        <div class="metric-value">{len(alerts)}</div>
    </div>
    """, unsafe_allow_html=True)

workflow_tabs = st.tabs([
    "1. Workflow",
    "2. Live Simulation",
    "3. AI & IDS",
    "4. Rooms & Nodes",
    "5. Backend / Export",
])

# -------------------------------------------------------------------
# 1. Workflow
# -------------------------------------------------------------------
with workflow_tabs[0]:
    st.markdown('<div class="section-title">Workflow Overview</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="export-card">
        <div class="subtle">
            This page is organized for the graduation demo: first show CAD extraction, then AI node placement, then RF heatmap, and finally live simulation.
        </div>
    </div>
    """, unsafe_allow_html=True)

    extract_col, plan_col = st.columns([1, 1])
    with extract_col:
        st.markdown('<div class="section-title">Extracted Rooms Preview</div>', unsafe_allow_html=True)
        st.caption("Rooms, corridors, labels, and CAD walls only. No nodes in this view.")
        if st.session_state.extracted_img:
            st.image(get_rendered_url(st.session_state.extracted_img["file_name"]), use_container_width=True)
        elif latest_rooms and latest_rooms.get("rooms"):
            st.image(get_rendered_url("cad_extract_rooms.png"), use_container_width=True)
        else:
            st.info("Press Extract Rooms from the sidebar to generate this preview.")

    with plan_col:
        st.markdown('<div class="section-title">AI Planning Preview</div>', unsafe_allow_html=True)
        st.caption("Planned nodes, directional beams, room labels, and CAD walls.")
        if st.session_state.plan_img:
            st.image(get_rendered_url(st.session_state.plan_img["file_name"]), use_container_width=True)
        else:
            st.info("Press Run AI Planning, then Render Plan Image.")

    st.markdown('<div class="section-title">Unified RF Heatmap</div>', unsafe_allow_html=True)
    if st.session_state.heatmap_img:
        st.image(get_rendered_url(st.session_state.heatmap_img["file_name"]), use_container_width=True)
    else:
        st.info("Press Render Unified Heatmap to view RF coverage quality.")

# -------------------------------------------------------------------
# 2. Live Simulation
# -------------------------------------------------------------------
with workflow_tabs[1]:
    top_left, top_right = st.columns([1.35, 1])

    with top_left:
        st.markdown('<div class="section-title">Interactive Simulation Overlay</div>', unsafe_allow_html=True)
        render_interactive_plan(building_data, sim_state)

    with top_right:
        st.markdown('<div class="section-title">Simulation Runtime</div>', unsafe_allow_html=True)
        st.markdown('<div class="export-card">', unsafe_allow_html=True)
        st.metric("Simulation Source", sim_state.get("simulation_source", "unknown"))
        st.metric("Step", sim_state.get("step", 0))
        st.metric("Runtime Nodes", len(node_runtime))
        st.metric("Clients", len(clients))
        st.metric("Telemetry Points", len(sim_state.get("telemetry_history", []) or []))
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Runtime Nodes</div>', unsafe_allow_html=True)
    if not node_runtime:
        st.info("Apply CAD Plan to Simulation to populate live node runtime.")
    else:
        for node in node_runtime:
            radio = node.get("radio", {}) or {}
            env = node.get("environment", {}) or {}
            st.markdown(f"""
            <div class="room-card">
                <b>{node.get("name", "Node")}</b><br>
                Status: {node.get("status", "unknown")}<br>
                Room: {node.get("room_name", "-")}<br>
                Channel: {radio.get("current_channel", "-")} | TX: {radio.get("tx_power_dbm", "-")} dBm<br>
                Load: {node.get("current_load", 0)} | Connected Clients: {node.get("connected_clients", 0)}<br>
                RSSI Avg: {radio.get("rssi_avg", 0)} dBm | SNR Avg: {radio.get("snr_avg", 0)} dB<br>
                Throughput: {radio.get("throughput_mbps", 0)} Mbps | Retry: {radio.get("retry_rate_pct", 0)}% | Packet Loss: {radio.get("packet_loss_pct", 0)}%<br>
                Latency: {radio.get("latency_ms", 0)} ms | Temp: {env.get("temperature_c", 0)} C | Humidity: {env.get("humidity_pct", 0)}%
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Live Clients</div>', unsafe_allow_html=True)
    if not clients:
        st.info("No clients yet. Apply the CAD plan to simulation.")
    else:
        client_cols = st.columns(2)
        for i, client in enumerate(clients):
            with client_cols[i % 2]:
                st.markdown(f"""
                <div class="room-card">
                    <b>{client.get("name", "Client")}</b><br>
                    Role: {client.get("role", "staff")}<br>
                    Position: ({round(float(client.get("x", 0)), 2)}, {round(float(client.get("y", 0)), 2)})<br>
                    Connected Node: {client.get("connected_node", "-")}<br>
                    RSSI: {client.get("current_rssi", "-")} dBm | SNR: {client.get("current_snr", "-")} dB<br>
                    Throughput: {client.get("current_throughput_mbps", 0)} Mbps | Roaming: {client.get("roaming_count", 0)}
                </div>
                """, unsafe_allow_html=True)

# -------------------------------------------------------------------
# 3. AI & IDS
# -------------------------------------------------------------------
with workflow_tabs[2]:
    st.markdown('<div class="section-title">AI Runtime Status</div>', unsafe_allow_html=True)
    ai_cols = st.columns(5)
    with ai_cols[0]:
        st.markdown("**Status**")
        render_status_badge(health.get("status", "stable"))
    with ai_cols[1]:
        st.metric("Anomaly Score", health.get("anomaly_score", 0))
    with ai_cols[2]:
        st.metric("Critical", health.get("critical_alerts", 0))
    with ai_cols[3]:
        st.metric("Warnings", health.get("warning_alerts", 0))
    with ai_cols[4]:
        st.metric("High Load Nodes", health.get("high_load_nodes", 0))

    rec_col, alert_col = st.columns([1, 1])
    with rec_col:
        st.markdown('<div class="section-title">AI Recommendations</div>', unsafe_allow_html=True)
        if not recommendations:
            st.info("No recommendations yet.")
        else:
            for rec in recommendations:
                st.markdown(f"""
                <div class="room-card">
                    <b>{str(rec.get("type", "observation")).upper()}</b><br>
                    {rec.get("message", "")}<br>
                    Confidence: {rec.get("confidence", 0)}
                </div>
                """, unsafe_allow_html=True)

    with alert_col:
        st.markdown('<div class="section-title">Security / IDS Alerts</div>', unsafe_allow_html=True)
        if not alerts:
            st.info("No security alerts.")
        else:
            for alert in alerts:
                st.markdown(f"""
                <div class="room-card">
                    <b>{str(alert.get("severity", "info")).upper()}</b> - {alert.get("title", "")}<br>
                    {alert.get("description", "")}<br>
                    Category: {alert.get("category", "unknown")}
                </div>
                """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Controller Decisions</div>', unsafe_allow_html=True)
    if not decisions:
        st.info("No controller decisions yet.")
    else:
        for d in decisions:
            st.markdown(f"""
            <div class="room-card">
                <b>{d.get("action", "none")}</b><br>
                Node: {d.get("node_id", "-")}<br>
                Value: {d.get("value", "")}<br>
                Reason: {d.get("reason", "")}
            </div>
            """, unsafe_allow_html=True)

# -------------------------------------------------------------------
# 4. Rooms & Nodes
# -------------------------------------------------------------------
with workflow_tabs[3]:
    rooms_col, nodes_col = st.columns([1, 1])

    with rooms_col:
        st.markdown('<div class="section-title">Extracted Rooms Inventory</div>', unsafe_allow_html=True)
        if latest_rooms and latest_rooms.get("rooms"):
            for room in latest_rooms.get("rooms", []):
                st.markdown(f"""
                <div class="room-card">
                    <b>{room.get("name", "Room")}</b><br>
                    Type: {room.get("room_type", "unknown")} | Zone: {room.get("zone", "unknown")} | Floor: {room.get("floor", "unknown")}<br>
                    Size: {round(float(room.get("width", 0)), 2)} x {round(float(room.get("height", 0)), 2)} | Area: {round(float(room.get("area", 0)), 2)}<br>
                    Expected Clients: {room.get("expected_clients", 0)} | Traffic: {room.get("traffic_profile", "medium")}<br>
                    Confidence: {room.get("confidence", 0)}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No extracted rooms yet.")

    with nodes_col:
        st.markdown('<div class="section-title">Suggested Nodes Inventory</div>', unsafe_allow_html=True)
        if plan_nodes_list:
            for node in plan_nodes_list:
                coverage = node.get("coverage", {}) or {}
                capacity = node.get("capacity", {}) or {}
                coverage_metrics = node.get("coverage_metrics", {}) or {}
                capacity_metrics = node.get("capacity_metrics", {}) or {}
                telemetry = node.get("telemetry", {}) or {}
                node_name = node.get("name") or node.get("node_id") or f"Node {node.get('id', '-') }"
                coverage_score = coverage.get("room_coverage_score", coverage_metrics.get("coverage_percent", 0))
                projected_clients = capacity.get("projected_clients", capacity_metrics.get("expected_clients", 0))
                projected_capacity = capacity.get("projected_capacity_mbps", capacity_metrics.get("effective_capacity_mbps", 0))
                tx_power = node.get("tx_power", node.get("tx_power_dbm", telemetry.get("tx_power_dbm", 0)))
                st.markdown(f"""
                <div class="node-card">
                    <b>{node_name}</b><br>
                    Room: {node.get("room_name", "-")} | Role: {node.get("node_role", "room_node")}<br>
                    Position: ({round(float(node.get("x", 0)), 2)}, {round(float(node.get("y", 0)), 2)})<br>
                    TX: {tx_power} dBm | Channel: {node.get("channel", 0)}<br>
                    Beam: {node.get("beam_direction_deg", node.get("antenna_direction", "omni"))}<br>
                    Coverage: {coverage_score} | Clients: {projected_clients} | Capacity: {projected_capacity} Mbps<br>
                    Placement Score: {node.get("placement_score", 0)}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No planned nodes yet.")

# -------------------------------------------------------------------
# 5. Backend / Export
# -------------------------------------------------------------------
with workflow_tabs[4]:
    st.markdown('<div class="section-title">Backend & Mobile Readiness</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="export-card">
        <b>Backend base URL</b><br>
        <span class="subtle">{API_URL}</span><br><br>
        <b>Mobile-ready endpoints</b><br>
        <span class="subtle">/mobile/bootstrap, /mobile/dashboard, /mobile/images, /mobile/nodes, /mobile/clients, /mobile/alerts</span><br><br>
        <b>Router / Security endpoints</b><br>
        <span class="subtle">/router/config, /network/vlans, /network/ssids, /security/policies, /ids/rules</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">CAD / Planning JSON</div>', unsafe_allow_html=True)
    info_col, json_col = st.columns([0.8, 1.2])
    with info_col:
        if latest_cad:
            st.markdown(f"""
            <div class="room-card">
                <b>CAD Info</b><br>
                Source: {latest_cad.get("source_file_name", "-")}<br>
                Format: {latest_cad.get("source_format", "-")}<br>
                Converted: {latest_cad.get("converted", False)}<br>
                Working DXF: {latest_cad.get("working_dxf_file_name", "-")}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No CAD file uploaded yet.")

    with json_col:
        with st.expander("Show latest plan JSON", expanded=False):
            st.json(latest_plan or {})
        with st.expander("Show simulation state JSON", expanded=False):
            st.json(sim_state or {})

    st.markdown('<div class="section-title">Export Center</div>', unsafe_allow_html=True)
    export_a, export_b = st.columns(2)
    with export_a:
        st.link_button("Download Excel Report", get_excel_export_url(), use_container_width=True)
    with export_b:
        st.link_button("Download PDF Report", get_pdf_export_url(), use_container_width=True)
