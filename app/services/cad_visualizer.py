from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.services.rf_engine import RFPropagationEngine
from app.services.wall_materials import WallMaterialManager

os.environ["MPLBACKEND"] = "Agg"

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Arc, Polygon as MplPolygon


class CADVisualizer:
    """
    StructFi CAD visualizer.

    Stable demo version:
    - Uses CAD walls as base.
    - Renders rooms and node plan.
    - Renders clean RF heatmap with more natural gradual coloring.
    - Avoids slow per-pixel wall intersection checks.
    - Supports plan keys: nodes, node_plan, planned_nodes, node_plans.
    """

    def __init__(self) -> None:
        self.parsed_dir = Path("data/parsed")
        self.rendered_dir = Path("data/rendered")
        self.rendered_dir.mkdir(parents=True, exist_ok=True)

        self.latest_building_path = self.parsed_dir / "latest_building.json"
        self.latest_plan_path = self.parsed_dir / "latest_plan.json"
        self.rf_engine = RFPropagationEngine()
        self.wall_material_manager = WallMaterialManager()

    # ------------------------------------------------------------------
    # Public API expected by app/main.py
    # ------------------------------------------------------------------

    def render_extract_rooms_from_latest(self) -> Dict[str, Any]:
        building = self._load_json(self.latest_building_path, required=True)
        return self.render_rooms_overlay(building=building)

    def render_rooms_from_latest(self) -> Dict[str, Any]:
        return self.render_extract_rooms_from_latest()

    def render_plan_from_latest(self) -> Dict[str, Any]:
        building = self._load_json(self.latest_building_path, required=True)
        plan = self._load_json(self.latest_plan_path, required=False)
        return self.render_plan_with_nodes(plan or {}, building=building)

    def render_heatmap_from_latest(self) -> Dict[str, Any]:
        building = self._load_json(self.latest_building_path, required=True)
        plan = self._load_json(self.latest_plan_path, required=False)
        return self.render_heatmap(plan or {}, building=building)

    def render_rooms_overlay(self, building: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if building is None:
            building = self._load_json(self.latest_building_path, required=True)

        fig, ax = self._new_figure(building)

        self._draw_exact_walls(ax, building, linewidth=1.45)
        self._draw_room_overlays(ax, building)
        self._draw_room_outlines(ax, building)
        self._draw_room_labels(ax, building, compact=False)
        self._finish_axes(ax, building, "Extracted Rooms - CAD Wall Overlay")

        out = self.rendered_dir / "cad_extract_rooms.png"
        fig.savefig(out, dpi=175, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        return {
            "file_name": out.name,
            "file_path": str(out).replace("\\", "/"),
            "url": f"/cad/rendered/{out.name}",
            "kind": "extract_rooms",
        }

    def render_plan_with_nodes(
        self,
        plan: Dict[str, Any],
        building: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if building is None:
            building = self._building_from_plan_or_latest(plan)

        fig, ax = self._new_figure(building)

        self._draw_exact_walls(ax, building, linewidth=1.45)
        self._draw_room_overlays(ax, building)
        self._draw_room_outlines(ax, building)
        self._draw_room_labels(ax, building, compact=False)
        self._draw_nodes(ax, plan)
        self._finish_axes(ax, building, "Interactive CAD Simulation Overlay")

        out = self.rendered_dir / "cad_plan_nodes.png"
        fig.savefig(out, dpi=175, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        return {
            "file_name": out.name,
            "file_path": str(out).replace("\\", "/"),
            "url": f"/cad/rendered/{out.name}",
            "kind": "plan",
        }

    def render_heatmap(
        self,
        plan: Dict[str, Any],
        building: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if building is None:
            building = self._building_from_plan_or_latest(plan)

        nodes = self._extract_nodes(plan)
        if not nodes:
            raise ValueError("No nodes found. Run AI Planning before rendering heatmap.")

        fig, ax = self._new_figure(building)

        self._draw_heatmap_field(ax, building, plan)
        self._draw_exact_walls(ax, building, linewidth=1.50)
        self._draw_room_outlines(ax, building)
        self._draw_room_labels(ax, building, compact=True)
        self._draw_nodes(ax, plan)
        self._finish_axes(ax, building, "Unified RF Coverage Heatmap")

        out = self.rendered_dir / "cad_heatmap.png"
        fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        return {
            "file_name": out.name,
            "file_path": str(out).replace("\\", "/"),
            "url": f"/cad/rendered/{out.name}",
            "kind": "heatmap",
        }

    # ------------------------------------------------------------------
    # Compatibility aliases
    # ------------------------------------------------------------------

    def render_plan(self, *args, **kwargs):
        return self.render_plan_from_latest()

    def render_default_heatmap(self, *args, **kwargs):
        return self.render_heatmap_from_latest()

    def render_rooms(self, *args, **kwargs):
        building = kwargs.get("building")

        if building is None and args:
            if isinstance(args[0], dict) and "bounds" in args[0]:
                building = args[0]

        return self.render_rooms_overlay(building=building)

    def render_extracted_rooms(self, *args, **kwargs):
        return self.render_rooms(*args, **kwargs)

    def render_room_extraction(self, *args, **kwargs):
        return self.render_rooms(*args, **kwargs)

    def render_building_rooms(self, *args, **kwargs):
        return self.render_rooms(*args, **kwargs)

    def render_building(self, *args, **kwargs):
        return self.render_rooms(*args, **kwargs)

    def render_latest_rooms(self, *args, **kwargs):
        return self.render_extract_rooms_from_latest()

    # ------------------------------------------------------------------
    # Figure setup
    # ------------------------------------------------------------------

    def _new_figure(self, building: Dict[str, Any]):
        bounds = building.get("bounds", {})
        width = max(float(bounds.get("width", 10.0)), 1.0)
        height = max(float(bounds.get("height", 10.0)), 1.0)

        aspect = width / max(height, 1e-9)
        fig_w = 12.8
        fig_h = max(5.5, min(9.2, fig_w / max(aspect, 0.55)))

        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        ax.set_facecolor("white")
        return fig, ax

    def _finish_axes(self, ax, building: Dict[str, Any], title: str) -> None:
        bounds = building.get("bounds", {})
        min_x = float(bounds.get("min_x", 0.0))
        min_y = float(bounds.get("min_y", 0.0))
        max_x = float(bounds.get("max_x", 10.0))
        max_y = float(bounds.get("max_y", 10.0))

        pad_x = max((max_x - min_x) * 0.02, 0.25)
        pad_y = max((max_y - min_y) * 0.02, 0.25)

        ax.set_xlim(min_x - pad_x, max_x + pad_x)
        ax.set_ylim(min_y - pad_y, max_y + pad_y)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(title, fontsize=10)
        ax.grid(True, linewidth=0.25, alpha=0.16)

    # ------------------------------------------------------------------
    # Walls / rooms / labels
    # ------------------------------------------------------------------

    def _draw_exact_walls(self, ax, building: Dict[str, Any], linewidth: float = 1.35) -> None:
        walls = building.get("walls", []) or []

        for wall in walls:
            try:
                x1 = float(wall.get("x1", 0.0))
                y1 = float(wall.get("y1", 0.0))
                x2 = float(wall.get("x2", 0.0))
                y2 = float(wall.get("y2", 0.0))
            except Exception:
                continue

            if math.hypot(x2 - x1, y2 - y1) < 0.01:
                continue

            layer = str(wall.get("layer", "")).lower()
            lw = linewidth

            if "healed" in layer:
                lw = max(0.75, linewidth * 0.72)

            if "door" in layer or "window" in layer:
                lw = max(0.60, linewidth * 0.65)

            ax.plot(
                [x1, x2],
                [y1, y2],
                color="#111111",
                linewidth=lw,
                solid_capstyle="round",
                zorder=30,
            )

    def _draw_room_overlays(self, ax, building: Dict[str, Any]) -> None:
        for room in building.get("rooms", []) or []:
            pts = self._polygon_points(room.get("polygon", []) or [])

            if len(pts) < 3:
                continue

            room_type = str(room.get("room_type", "unknown")).lower()
            alpha = 0.07

            if room_type == "corridor":
                alpha = 0.10
            elif room_type in ["bathroom", "service", "storage"]:
                alpha = 0.09
            elif room_type in ["reception", "meeting", "open_area"]:
                alpha = 0.085

            patch = MplPolygon(
                pts,
                closed=True,
                facecolor=self._room_fill(room_type),
                edgecolor="none",
                linewidth=0.0,
                alpha=alpha,
                zorder=4,
            )
            ax.add_patch(patch)

    def _draw_room_outlines(self, ax, building: Dict[str, Any]) -> None:
        for room in building.get("rooms", []) or []:
            pts = self._polygon_points(room.get("polygon", []) or [])

            if len(pts) < 3:
                continue

            room_type = str(room.get("room_type", "unknown")).lower()

            patch = MplPolygon(
                pts,
                closed=True,
                facecolor="none",
                edgecolor=self._room_edge(room_type),
                linewidth=0.65,
                alpha=0.42,
                zorder=20,
            )
            ax.add_patch(patch)

    def _draw_room_labels(self, ax, building: Dict[str, Any], compact: bool = False) -> None:
        rooms = building.get("rooms", []) or []
        placed: List[Tuple[float, float]] = []

        sorted_rooms = sorted(
            rooms,
            key=lambda r: float(r.get("area", 0.0) or 0.0),
            reverse=True,
        )

        for room in sorted_rooms:
            name = str(room.get("label_text") or room.get("name") or "")
            room_type = str(room.get("room_type") or "unknown")
            expected = room.get("expected_clients", 0)

            if not name and compact:
                continue

            cx = float(room.get("center_x", room.get("x", 0.0)) or 0.0)
            cy = float(room.get("center_y", room.get("y", 0.0)) or 0.0)

            threshold = 0.34 if compact else 0.20
            if self._label_collides(cx, cy, placed, threshold=threshold):
                continue

            placed.append((cx, cy))

            if compact:
                text = self._short_label(name, room_type)
                fontsize = 5.8
                box_alpha = 0.62
            else:
                text = self._format_room_label(name, room_type, expected)
                fontsize = 5.8
                box_alpha = 0.66

            ax.text(
                cx,
                cy,
                text,
                ha="center",
                va="center",
                fontsize=fontsize,
                color="#202020",
                zorder=45,
                bbox=dict(
                    boxstyle="round,pad=0.13",
                    facecolor="white",
                    edgecolor="none",
                    alpha=box_alpha,
                ),
            )

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _draw_nodes(self, ax, plan: Dict[str, Any]) -> None:
        nodes = self._extract_nodes(plan)

        for idx, node in enumerate(nodes, start=1):
            x = self._node_x(node)
            y = self._node_y(node)

            if x is None or y is None:
                continue

            node_id = node.get("node_id") or node.get("id") or idx
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
                    node.get("beam_width_deg", 80.0),
                )
                or 80.0
            )

            ax.scatter(
                [x],
                [y],
                s=102,
                marker="o",
                color="#0B3D91",
                edgecolors="white",
                linewidths=1.25,
                zorder=70,
            )

            ax.text(
                x,
                y,
                "N",
                color="white",
                fontsize=6.4,
                ha="center",
                va="center",
                fontweight="bold",
                zorder=75,
            )

            self._draw_three_beam_arcs(ax, x, y, direction, beamwidth)

            display_id = str(node_id)
            if display_id.startswith("SF-N"):
                display_id = display_id.replace("SF-N", "N")

            label = f"Node {display_id}"

            if room_id != "":
                label += f"\nR{room_id}"

            if tx_power != "":
                label += f"\n{tx_power} dBm"

            ax.text(
                x + 0.12,
                y + 0.12,
                label,
                fontsize=5.1,
                color="#0B1F3A",
                ha="left",
                va="bottom",
                zorder=76,
                bbox=dict(
                    boxstyle="round,pad=0.12",
                    facecolor="white",
                    edgecolor="#C8D3E5",
                    alpha=0.84,
                ),
            )

    def _draw_three_beam_arcs(
        self,
        ax,
        x: float,
        y: float,
        direction: float,
        beamwidth: float,
    ) -> None:
        start = direction - beamwidth / 2.0
        end = direction + beamwidth / 2.0

        for radius, lw, alpha in [
            (0.55, 1.0, 0.85),
            (0.90, 1.0, 0.70),
            (1.25, 1.0, 0.55),
        ]:
            arc = Arc(
                (x, y),
                width=radius * 2,
                height=radius * 2,
                angle=0,
                theta1=start,
                theta2=end,
                linewidth=lw,
                color="#1464C0",
                alpha=alpha,
                zorder=68,
            )
            ax.add_patch(arc)

    # ------------------------------------------------------------------
    # Fast clean RF heatmap with improved gradual coloring
    # ------------------------------------------------------------------

    def _draw_heatmap_field(self, ax, building: Dict[str, Any], plan: Dict[str, Any]) -> None:
        bounds = building.get("bounds", {})
        min_x = float(bounds.get("min_x", 0.0))
        min_y = float(bounds.get("min_y", 0.0))
        max_x = float(bounds.get("max_x", 10.0))
        max_y = float(bounds.get("max_y", 10.0))

        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)

        nodes = self._prepare_nodes(plan)
        if not nodes:
            raise ValueError("No valid node coordinates found for heatmap rendering.")

        # Slightly higher than the old working version, but still safe.
        nx = 220
        ny = max(90, min(190, int(nx * height / max(width, 1e-9))))

        xs = [min_x + width * i / (nx - 1) for i in range(nx)]
        ys = [min_y + height * j / (ny - 1) for j in range(ny)]

        rooms = building.get("rooms", []) or []
        values: List[List[float]] = []

        for y in ys:
            row = []
            for x in xs:
                room = self._room_containing_point_fast(x, y, rooms)

                if room is None:
                    row.append(float("nan"))
                    continue

                quality = self._coverage_quality_at(x, y, nodes, room)
                row.append(quality)

            values.append(row)

        cmap = LinearSegmentedColormap.from_list(
            "structfi_rf_gradual",
            [
                (0.00, "#c94f4f"),
                (0.18, "#e98264"),
                (0.34, "#f2bd72"),
                (0.50, "#f3e394"),
                (0.64, "#cde99b"),
                (0.78, "#8bd097"),
                (0.90, "#55b982"),
                (1.00, "#238b5d"),
            ],
        )
        cmap.set_bad(alpha=0.0)

        image = ax.imshow(
            values,
            extent=[min_x, max_x, min_y, max_y],
            origin="lower",
            cmap=cmap,
            alpha=0.78,
            zorder=1,
            vmin=0.0,
            vmax=1.0,
            interpolation="bicubic",
        )

        cbar = ax.figure.colorbar(image, ax=ax, fraction=0.026, pad=0.012)
        cbar.set_label("Calibrated RF Quality (RSSI/SNR + Design Margin)", fontsize=8)
        cbar.ax.tick_params(labelsize=7)

    def _prepare_nodes(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        prepared = []

        for node in self._extract_nodes(plan):
            x = self._node_x(node)
            y = self._node_y(node)

            if x is None or y is None:
                continue

            tx_power = float(node.get("tx_power_dbm", node.get("tx_power", 16.0)) or 16.0)

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
                    node.get("beam_width_deg", 80.0),
                )
                or 80.0
            )

            hardware = node.get("hardware_profile", {}) if isinstance(node.get("hardware_profile"), dict) else {}
            prepared.append(
                {
                    "x": float(x),
                    "y": float(y),
                    "room_id": node.get("room_id"),
                    "tx_power": tx_power,
                    "direction": direction,
                    "beamwidth": beamwidth,
                    "antenna_gain_dbi": float(hardware.get("antenna_gain_dbi", 8.0) or 8.0),
                    "channel_width_mhz": int(hardware.get("channel_width_mhz", 40) or 40),
                }
            )

        return prepared

    def _coverage_quality_at(
        self,
        x: float,
        y: float,
        nodes: List[Dict[str, Any]],
        room: Dict[str, Any],
    ) -> float:
        """
        Point-based calibrated RF quality for the heatmap.

        The previous heatmap combined all received powers, which could make most
        rooms appear solid green whenever every room had a planned node. This
        version evaluates each grid point using the strongest practical link,
        then applies planning margins for indoor fading, room size, antenna
        effective radius, beam alignment, and room-boundary transitions.
        """
        point_room_id = room.get("id")
        point_room_type = str(room.get("room_type", "unknown")).lower()
        material_config = self.wall_material_manager.current_config()
        default_material = material_config.get("default_material", self.rf_engine.default_material)
        interior_material = material_config.get("interior_wall_material", default_material)

        adjusted_links: List[Tuple[float, float, Any]] = []

        for node in nodes:
            nx = float(node["x"])
            ny = float(node["y"])
            tx_power = float(node["tx_power"])
            direction = float(node["direction"])
            beamwidth = max(float(node["beamwidth"]), 25.0)
            antenna_gain = float(node.get("antenna_gain_dbi", 8.0) or 8.0)

            distance = max(0.5, math.hypot(x - nx, y - ny))
            same_room = point_room_id is not None and node.get("room_id") == point_room_id
            wall_count = 0 if same_room else self._estimated_room_barriers(distance, point_room_type)
            heatmap_wall_material = default_material if same_room else interior_material

            rf_link = self.rf_engine.estimate_link(
                node_x=nx,
                node_y=ny,
                target_x=x,
                target_y=y,
                tx_power_dbm=tx_power,
                beam_direction_deg=direction,
                beamwidth_deg=beamwidth,
                room_type=point_room_type,
                wall_count=wall_count,
                wall_segments=None,
                antenna_gain_dbi=antenna_gain,
                default_material=heatmap_wall_material,
                interference_penalty_db=0.0,
            )

            # Planning calibration margin: indoor Wi-Fi surveys usually design
            # against fades, furniture, people, client-device variability, and
            # antenna mounting imperfections. Without this margin, simulated
            # RSSI can look unrealistically green everywhere.
            design_margin_db = self._heatmap_design_margin_db(
                distance_m=distance,
                room=room,
                node=node,
                same_room=same_room,
            )
            radius_penalty_db = self._effective_radius_penalty_db(distance, node, room)
            beam_penalty_db = self._beam_alignment_penalty_db(x, y, node)
            local_shadow_db = self._local_shadowing_penalty_db(x, y, room)

            calibrated_rssi = (
                rf_link.rssi_dbm
                - design_margin_db
                - radius_penalty_db
                - beam_penalty_db
                - local_shadow_db
            )
            calibrated_snr = calibrated_rssi - rf_link.noise_floor_dbm
            adjusted_links.append((calibrated_rssi, calibrated_snr, rf_link))

        if not adjusted_links:
            return 0.0

        adjusted_links.sort(key=lambda item: item[0], reverse=True)
        best_rssi, best_snr, _best_link = adjusted_links[0]

        # Small diversity benefit if another node is close enough, but do not
        # sum all AP powers. Summing every node made the map look overly green.
        diversity_bonus = 0.0
        if len(adjusted_links) > 1:
            second_rssi = adjusted_links[1][0]
            if second_rssi >= best_rssi - 6.0:
                diversity_bonus = 0.045
            elif second_rssi >= best_rssi - 10.0:
                diversity_bonus = 0.025

        quality = self._rssi_snr_to_heatmap_quality(best_rssi, best_snr) + diversity_bonus
        quality *= self._room_edge_gradient_factor(x, y, room)

        return max(0.0, min(1.0, quality))

    def _rssi_snr_to_heatmap_quality(self, rssi_dbm: float, snr_db: float) -> float:
        """Map calibrated RSSI/SNR into visual quality bands.

        Bands are intentionally stricter than raw simulated RSSI:
        - >= -55 dBm: excellent
        - around -60 dBm: good
        - around -67 dBm: usable/target edge
        - around -72 dBm: weak
        - <= -82 dBm: very poor
        """
        rssi = float(rssi_dbm)
        bands = [
            (-95.0, 0.00),
            (-82.0, 0.08),
            (-75.0, 0.22),
            (-72.0, 0.34),
            (-67.0, 0.55),
            (-60.0, 0.76),
            (-55.0, 0.90),
            (-45.0, 1.00),
        ]

        if rssi <= bands[0][0]:
            quality = bands[0][1]
        elif rssi >= bands[-1][0]:
            quality = bands[-1][1]
        else:
            quality = 0.0
            for (x0, q0), (x1, q1) in zip(bands, bands[1:]):
                if x0 <= rssi <= x1:
                    t = (rssi - x0) / max(x1 - x0, 1e-9)
                    quality = q0 + (q1 - q0) * t
                    break

        # SNR correction keeps strong RSSI but noisy links from looking perfect.
        if snr_db < 18:
            quality *= 0.68
        elif snr_db < 25:
            quality *= 0.86
        elif snr_db > 35:
            quality = min(1.0, quality + 0.035)

        return max(0.0, min(1.0, quality))

    def _heatmap_design_margin_db(
        self,
        *,
        distance_m: float,
        room: Dict[str, Any],
        node: Dict[str, Any],
        same_room: bool,
    ) -> float:
        """Indoor fade/design margin used only for visual RF planning.

        This prevents the simulation from treating ideal line-of-sight values as
        guaranteed real deployment values. Larger rooms and non-same-room links
        receive a stronger margin.
        """
        room_type = str(room.get("room_type", "unknown")).lower()
        area = max(float(room.get("area", 0.0) or 0.0), 1.0)
        margin = 7.5

        if distance_m > 4.0:
            margin += min(5.0, (distance_m - 4.0) * 0.55)
        if area > 30.0:
            margin += min(4.0, (area - 30.0) / 30.0)
        if not same_room:
            margin += 2.5
        if room_type in ["call_center", "meeting", "open_area"] or "call" in str(room.get("name", "")).lower():
            margin += 1.5
        if room_type in ["storage", "service", "kitchen"]:
            margin += 0.8

        return margin

    def _effective_radius_penalty_db(self, distance_m: float, node: Dict[str, Any], room: Dict[str, Any]) -> float:
        """Penalize points outside the realistic effective sector radius."""
        tx = float(node.get("tx_power", 16.0) or 16.0)
        gain = float(node.get("antenna_gain_dbi", 8.0) or 8.0)
        beamwidth = max(float(node.get("beamwidth", 80.0) or 80.0), 25.0)
        room_type = str(room.get("room_type", "unknown")).lower()

        radius = 4.0
        radius += max(0.0, tx - 12.0) * 0.22
        radius += max(0.0, gain - 6.0) * 0.28
        radius += min(1.2, beamwidth / 120.0)

        if room_type == "corridor":
            radius *= 1.45
        elif room_type in ["open_area", "reception", "meeting"]:
            radius *= 1.15
        elif room_type in ["storage", "service", "kitchen"]:
            radius *= 0.82

        if distance_m <= radius:
            return 0.0
        return min(12.0, (distance_m - radius) * 1.85)

    def _beam_alignment_penalty_db(self, x: float, y: float, node: Dict[str, Any]) -> float:
        nx = float(node.get("x", 0.0))
        ny = float(node.get("y", 0.0))
        direction = float(node.get("direction", 0.0) or 0.0)
        beamwidth = max(float(node.get("beamwidth", 80.0) or 80.0), 25.0)
        angle = math.degrees(math.atan2(y - ny, x - nx))
        delta = abs((angle - direction + 180.0) % 360.0 - 180.0)
        half = beamwidth / 2.0

        if delta <= half:
            return 0.0
        if delta <= beamwidth:
            return min(6.0, (delta - half) / max(half, 1.0) * 4.0)
        return min(14.0, 6.0 + (delta - beamwidth) / 90.0 * 8.0)

    def _local_shadowing_penalty_db(self, x: float, y: float, room: Dict[str, Any]) -> float:
        """Deterministic tiny variation to avoid perfectly flat colored blocks."""
        rx = float(room.get("x", 0.0))
        ry = float(room.get("y", 0.0))
        rw = max(float(room.get("width", 1.0)), 0.1)
        rh = max(float(room.get("height", 1.0)), 0.1)
        nx = (x - rx) / rw
        ny = (y - ry) / rh
        wave = math.sin((nx * 7.1 + ny * 3.7) * math.pi) * 0.5 + 0.5
        return 0.0 + wave * 1.6

    def _estimated_room_barriers(self, distance_m: float, room_type: str) -> int:
        """Fast barrier estimate for point heatmaps between different rooms."""
        room_type = str(room_type or "unknown").lower()
        if room_type == "corridor":
            return 1
        if distance_m > 12.0:
            return 2
        return 1

    def _room_edge_gradient_factor(self, x: float, y: float, room: Dict[str, Any]) -> float:
        rx = float(room.get("x", 0.0))
        ry = float(room.get("y", 0.0))
        rw = max(float(room.get("width", 0.0)), 0.1)
        rh = max(float(room.get("height", 0.0)), 0.1)

        left = abs(x - rx)
        right = abs((rx + rw) - x)
        bottom = abs(y - ry)
        top = abs((ry + rh) - y)

        nearest_edge = min(left, right, bottom, top)
        scale = max(min(rw, rh) * 0.22, 0.35)

        factor = 0.88 + 0.12 * min(1.0, nearest_edge / scale)
        return max(0.82, min(1.0, factor))

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _room_containing_point_fast(
        self,
        x: float,
        y: float,
        rooms: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        for room in rooms:
            rx = float(room.get("x", 0.0))
            ry = float(room.get("y", 0.0))
            rw = float(room.get("width", 0.0))
            rh = float(room.get("height", 0.0))

            if not (rx <= x <= rx + rw and ry <= y <= ry + rh):
                continue

            polygon = room.get("polygon", []) or []
            pts = self._polygon_points(polygon)

            if len(pts) < 3:
                return room

            if self._point_in_polygon(x, y, pts):
                return room

        return None

    def _point_in_polygon(
        self,
        x: float,
        y: float,
        polygon: List[Tuple[float, float]],
    ) -> bool:
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

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _building_from_plan_or_latest(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(plan, dict) and isinstance(plan.get("building"), dict):
            return plan["building"]

        if self.latest_building_path.exists():
            return self._load_json(self.latest_building_path, required=True)

        if isinstance(plan, dict):
            rooms = plan.get("rooms", [])
            if rooms:
                return self._building_from_rooms_only(rooms)

        raise FileNotFoundError("No latest_building.json available. Run Extract Rooms first.")

    def _building_from_rooms_only(self, rooms: List[Dict[str, Any]]) -> Dict[str, Any]:
        xs = []
        ys = []

        for room in rooms:
            x = float(room.get("x", 0.0))
            y = float(room.get("y", 0.0))
            width = float(room.get("width", 0.0))
            height = float(room.get("height", 0.0))

            xs.extend([x, x + width])
            ys.extend([y, y + height])

        if not xs:
            xs = [0.0, 10.0]
            ys = [0.0, 10.0]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        return {
            "bounds": {
                "min_x": min_x,
                "min_y": min_y,
                "max_x": max_x,
                "max_y": max_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
            },
            "walls": [],
            "rooms": rooms,
            "labels": [],
        }

    def _load_json(self, path: Path, required: bool = True) -> Dict[str, Any]:
        if not path.exists():
            if required:
                raise FileNotFoundError(f"{path} was not found.")
            return {}

        return json.loads(path.read_text(encoding="utf-8"))

    def _extract_nodes(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(plan, dict):
            return []

        for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
            if isinstance(plan.get(key), list):
                return plan[key]

        result = plan.get("result")
        if isinstance(result, dict):
            for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
                if isinstance(result.get(key), list):
                    return result[key]

        data = plan.get("data")
        if isinstance(data, dict):
            for key in ["node_plan", "nodes", "planned_nodes", "node_plans"]:
                if isinstance(data.get(key), list):
                    return data[key]

        return []

    def _node_x(self, node: Dict[str, Any]) -> Optional[float]:
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

    def _node_y(self, node: Dict[str, Any]) -> Optional[float]:
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

    def _polygon_points(self, polygon: List[Any]) -> List[Tuple[float, float]]:
        pts: List[Tuple[float, float]] = []

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

    # ------------------------------------------------------------------
    # Label / colors
    # ------------------------------------------------------------------

    def _format_room_label(self, name: str, room_type: str, expected: Any) -> str:
        clean = name.strip()

        if not clean:
            clean = room_type.replace("_", " ").title()

        clean = clean.replace("_", " ")

        if len(clean) > 28:
            clean = clean[:26] + "..."

        return f"{clean}\n[{room_type}]\nExp {expected}"

    def _short_label(self, name: str, room_type: str) -> str:
        clean = name.strip() or room_type.replace("_", " ").title()
        clean = clean.replace("_", " ")

        if len(clean) > 18:
            clean = clean[:16] + "..."

        return clean

    def _label_collides(
        self,
        x: float,
        y: float,
        placed: List[Tuple[float, float]],
        threshold: float,
    ) -> bool:
        for px, py in placed:
            if math.hypot(x - px, y - py) < threshold:
                return True

        return False

    def _room_fill(self, room_type: str) -> str:
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

    def _room_edge(self, room_type: str) -> str:
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


CADVisualizerService = CADVisualizer
StructFiCADVisualizer = CADVisualizer
Visualizer = CADVisualizer