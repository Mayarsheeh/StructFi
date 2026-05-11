from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import ezdxf

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

try:
    from app.models.building_models import (
        BuildingBounds,
        BuildingModel,
        DoorGap,
        FloorModel,
        Point2D,
        RoomModel,
        RoomNeighbor,
        TextLabel,
        WallSegment,
    )
except ImportError:
    from app.models.building_models import (
        BuildingBounds,
        BuildingModel,
        DoorOrGapModel as DoorGap,
        FloorModel,
        Point2D,
        RoomModel,
        RoomNeighbor,
        TextLabel,
        WallSegment,
    )


@dataclass
class _RawSegment:
    x1: float
    y1: float
    x2: float
    y2: float
    layer: str = "unknown"
    is_structural: bool = True


@dataclass
class _LoopCandidate:
    polygon: List[Point2D]
    area: float
    perimeter: float
    center_x: float
    center_y: float
    confidence: float
    source: str


class DXFRoomExtractor:
    """
    StructFi stable rollback extractor + semantic correction.

    This version is intentionally conservative:
    - Keeps the stable label-wall-ray behavior.
    - Keeps axis-grid fallback for corridors.
    - Avoids aggressive wall-mask extraction except as emergency fallback.
    - Adds semantic validation so long narrow spaces are not treated as normal rooms.
    - Adds corridor/reception circulation recovery after room extraction.
    - Writes data/parsed/cad_debug_report.json.
    """

    def __init__(self) -> None:
        self.meta_path = Path("data/meta/latest_cad.json")
        self.output_dir = Path("data/parsed")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.latest_building_output = self.output_dir / "latest_building.json"
        self.debug_report_output = self.output_dir / "cad_debug_report.json"

        self.min_segment_length = 0.16

        self.snap_tolerance_ratio = 0.0015
        self.max_snap_tolerance = 0.35
        self.min_snap_tolerance = 0.04

        self.max_gap_close = 0.42
        self.max_collinear_offset = 0.14

        self.min_room_area_absolute = 0.55
        self.max_room_area_ratio = 0.92
        self.min_room_side = 0.35
        self.duplicate_center_tolerance = 0.45

        self.ray_wall_tolerance = 0.10
        self.ray_max_room_width = 18.0
        self.ray_max_room_height = 14.0

        self.corridor_min_aspect = 2.55
        self.corridor_min_area = 1.20
        self.corridor_max_width = 2.80
        self.corridor_max_overlap_with_rooms = 0.35

        self.circulation_aspect = 2.85
        self.circulation_max_narrow_side = 3.25
        self.large_bad_room_label_count = 2
        self.max_labeled_room_area_without_special_label = 55.0
        self.min_corridor_neighbor_count = 2

        self.wall_positive_keywords = [
            "wall",
            "walls",
            "a-wall",
            "a_wall",
            "muro",
            "muro-proy",
            "muro-no sec",
            "mur",
            "partition",
            "struct",
            "structure",
            "concrete",
            "brick",
            "block",
            "column",
            "outline",
            "boundary",
            "floor",
            "plan",
            "ext",
            "external",
            "internal",
            "architectural",
            "arch",
        ]

        self.reject_layer_keywords = [
            "furn",
            "furniture",
            "mueble",
            "muebles",
            "mob",
            "chair",
            "table",
            "sofa",
            "desk",
            "bed",
            "cabinet",
            "wardrobe",
            "closet",
            "fixture",
            "fixtures",
            "sanitary",
            "toilet",
            "wc",
            "lav",
            "sink",
            "bath",
            "shower",
            "appliance",
            "symbol",
            "symbols",
            "hatch",
            "pattern",
            "dim",
            "dimension",
            "dimensions",
            "annotation",
            "anno",
            "leader",
            "title",
            "border",
            "frame",
            "axis",
            "grid",
            "center",
            "hidden",
            "door",
            "doors",
            "window",
            "windows",
            "glass",
            "stair",
            "stairs",
            "elect",
            "electric",
            "lighting",
            "hvac",
            "plumb",
            "pipe",
            "pipes",
            "plant",
            "tree",
            "car",
            "parking",
            "ceiling",
            "ceil",
        ]

    def extract_from_latest_dxf(self):
        if not self.meta_path.exists():
            return None

        try:
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        dxf_path = Path(
            meta.get("working_dxf_file_path")
            or meta.get("dxf_file_path")
            or meta.get("source_file_path")
            or ""
        )

        if not dxf_path.exists():
            return None

        source_format = str(meta.get("source_format", "DXF")).upper()
        building = self.extract_building_from_file(dxf_path, source_format=source_format)
        self._write_latest_building(building)
        return self._model_to_dict(building)

    def get_latest_building_model(self) -> Optional[BuildingModel]:
        if not self.latest_building_output.exists():
            return None

        try:
            data = json.loads(self.latest_building_output.read_text(encoding="utf-8"))
            return BuildingModel(**data)
        except Exception:
            return None

    def extract_building_from_file(self, dxf_file: Path, source_format: str = "DXF") -> BuildingModel:
        doc = ezdxf.readfile(str(dxf_file))
        msp = doc.modelspace()

        labels = self._extract_text_labels(msp)
        raw_segments = self._extract_architectural_segments(msp)
        raw_segments = self._filter_out_sheet_border_segments(raw_segments, labels)

        if not raw_segments and not labels:
            bounds = BuildingBounds(
                min_x=0.0,
                min_y=0.0,
                max_x=10.0,
                max_y=10.0,
                width=10.0,
                height=10.0,
            )
            building = BuildingModel(
                file_name=dxf_file.name,
                source_format=self._safe_source_format(source_format),
                bounds=bounds,
                floors=[],
                walls=[],
                doors_or_gaps=[],
                labels=[],
                rooms=[],
                controller_zone_candidate_room_id=None,
                extraction_confidence=0.0,
            )
            self._write_debug_report(
                building=building,
                raw_segments=[],
                final_segments=[],
                rooms=[],
                labels=[],
                extra={"note": "no raw segments and no labels"},
            )
            return building

        bounds_dict = self._compute_bounds(raw_segments, labels, pad_ratio=0.04)
        snap_tol = self._adaptive_snap_tolerance(bounds_dict)

        snapped_segments = self._snap_and_merge_segments(raw_segments, snap_tol)
        healed_segments = self._heal_wall_gaps(snapped_segments)
        healed_segments = self._snap_and_merge_segments(healed_segments, snap_tol)
        split_segments = self._split_segments_at_intersections(healed_segments, snap_tol)
        split_segments = self._remove_short_segments(split_segments, self.min_segment_length)

        rooms = self._rooms_from_label_wall_rays(split_segments, labels, bounds_dict)

        axis_loops = self._detect_simple_axis_loops(split_segments, bounds_dict)
        rooms = self._merge_axis_loop_rooms(
            base_rooms=rooms,
            loops=axis_loops,
            labels=labels,
            bounds=bounds_dict,
        )

        if len(rooms) < 3 and cv2 is not None and np is not None and split_segments:
            raster_rooms = self._fallback_raster_rooms(split_segments, labels, bounds_dict)
            rooms = self._merge_room_sets(rooms, raster_rooms)

        rooms = self._deduplicate_rooms(rooms)
        rooms = self._semantic_validate_spaces(rooms, labels)
        rooms = self._force_corridor_classification(rooms)
        rooms = self._recover_missing_corridors(
            rooms=rooms,
            segments=split_segments,
            labels=labels,
            bounds=bounds_dict,
        )
        rooms = self._force_corridor_from_room_layout(
            rooms=rooms,
            labels=labels,
            bounds=bounds_dict,
        )
        rooms = self._deduplicate_rooms(rooms)
        rooms = self._attach_room_neighbors(rooms)
        rooms = self._sort_and_reindex_rooms(rooms)
        floors = self._build_floor_models(rooms)

        walls = [
            WallSegment(
                id=i + 1,
                x1=float(s.x1),
                y1=float(s.y1),
                x2=float(s.x2),
                y2=float(s.y2),
                layer=s.layer or "wall",
                thickness_hint=0.0,
                is_structural=bool(s.is_structural),
            )
            for i, s in enumerate(split_segments)
        ]

        confidence = self._estimate_extraction_confidence(
            raw_segments=raw_segments,
            final_segments=split_segments,
            rooms=rooms,
            labels=labels,
        )

        building = BuildingModel(
            file_name=dxf_file.name,
            source_format=self._safe_source_format(source_format),
            bounds=BuildingBounds(**bounds_dict),
            floors=floors,
            walls=walls,
            doors_or_gaps=self._detect_possible_door_gaps(rooms),
            labels=labels,
            rooms=rooms,
            controller_zone_candidate_room_id=self._choose_controller_room_id(rooms),
            extraction_confidence=confidence,
        )

        self._write_debug_report(
            building=building,
            raw_segments=raw_segments,
            final_segments=split_segments,
            rooms=rooms,
            labels=labels,
            extra={
                "axis_loops_count": len(axis_loops),
                "semantic_validator": "enabled",
                "missing_corridor_recovery": "enabled",
            },
        )

        return building

    def _safe_source_format(self, source_format: str) -> str:
        source_format = str(source_format or "UNKNOWN").upper()
        if source_format in ["DXF", "DWG", "UNKNOWN"]:
            return source_format
        return "UNKNOWN"

    def _extract_architectural_segments(self, msp) -> List[_RawSegment]:
        wall_like: List[_RawSegment] = []
        fallback_linework: List[_RawSegment] = []

        for entity in msp:
            dxftype = entity.dxftype()
            layer = str(getattr(entity.dxf, "layer", "unknown") or "unknown")

            if dxftype == "INSERT":
                self._extract_insert_segments(
                    entity=entity,
                    parent_layer=layer,
                    wall_like=wall_like,
                    fallback_linework=fallback_linework,
                )
                continue

            if self._is_rejected_layer(layer):
                continue

            if dxftype in ["TEXT", "MTEXT", "HATCH", "DIMENSION", "LEADER", "MLEADER"]:
                continue

            entity_segments = self._segments_from_entity(entity)

            for x1, y1, x2, y2 in entity_segments:
                length = math.hypot(x2 - x1, y2 - y1)
                if length < self.min_segment_length:
                    continue

                seg = _RawSegment(
                    x1=float(x1),
                    y1=float(y1),
                    x2=float(x2),
                    y2=float(y2),
                    layer=layer,
                    is_structural=self._is_structural_layer(layer),
                )

                fallback_linework.append(seg)

                if self._is_wall_layer(layer):
                    wall_like.append(seg)

        if len(wall_like) >= max(8, int(len(fallback_linework) * 0.10)):
            return self._remove_symbol_like_clusters(wall_like)

        return self._remove_symbol_like_clusters(fallback_linework)

    def _extract_insert_segments(
        self,
        entity,
        parent_layer: str,
        wall_like: List[_RawSegment],
        fallback_linework: List[_RawSegment],
    ) -> None:
        try:
            virtual_entities = list(entity.virtual_entities())
        except Exception:
            return

        for virtual_entity in virtual_entities:
            try:
                dxftype = virtual_entity.dxftype()
                virtual_layer = str(getattr(virtual_entity.dxf, "layer", parent_layer) or parent_layer)

                if self._is_rejected_layer(virtual_layer):
                    continue

                if dxftype in ["TEXT", "MTEXT", "HATCH", "DIMENSION", "LEADER", "MLEADER", "INSERT"]:
                    continue

                virtual_segments = self._segments_from_entity(virtual_entity)

                for x1, y1, x2, y2 in virtual_segments:
                    length = math.hypot(x2 - x1, y2 - y1)
                    if length < self.min_segment_length:
                        continue

                    seg = _RawSegment(
                        x1=float(x1),
                        y1=float(y1),
                        x2=float(x2),
                        y2=float(y2),
                        layer=virtual_layer,
                        is_structural=self._is_structural_layer(virtual_layer),
                    )

                    fallback_linework.append(seg)

                    if self._is_wall_layer(virtual_layer):
                        wall_like.append(seg)

            except Exception:
                continue

    def _segments_from_entity(self, entity) -> List[Tuple[float, float, float, float]]:
        dxftype = entity.dxftype()
        segments: List[Tuple[float, float, float, float]] = []

        try:
            if dxftype == "LINE":
                s = entity.dxf.start
                e = entity.dxf.end
                segments.append((float(s.x), float(s.y), float(e.x), float(e.y)))

            elif dxftype == "LWPOLYLINE":
                pts = [(float(p[0]), float(p[1])) for p in entity.get_points()]
                for a, b in zip(pts, pts[1:]):
                    segments.append((a[0], a[1], b[0], b[1]))
                if bool(entity.closed) and len(pts) > 2:
                    segments.append((pts[-1][0], pts[-1][1], pts[0][0], pts[0][1]))

            elif dxftype == "POLYLINE":
                pts = []
                for v in entity.vertices:
                    loc = v.dxf.location
                    pts.append((float(loc.x), float(loc.y)))
                for a, b in zip(pts, pts[1:]):
                    segments.append((a[0], a[1], b[0], b[1]))
                if bool(entity.is_closed) and len(pts) > 2:
                    segments.append((pts[-1][0], pts[-1][1], pts[0][0], pts[0][1]))

            elif dxftype == "ARC":
                center = entity.dxf.center
                radius = float(entity.dxf.radius)
                if radius < 0.35:
                    return []

                start_angle = math.radians(float(entity.dxf.start_angle))
                end_angle = math.radians(float(entity.dxf.end_angle))

                if end_angle < start_angle:
                    end_angle += 2 * math.pi

                sweep = end_angle - start_angle
                if sweep > math.pi * 1.75:
                    return []

                steps = max(4, min(18, int(abs(sweep) / (math.pi / 14))))
                pts = []

                for i in range(steps + 1):
                    t = start_angle + sweep * i / steps
                    pts.append(
                        (
                            float(center.x) + radius * math.cos(t),
                            float(center.y) + radius * math.sin(t),
                        )
                    )

                for a, b in zip(pts, pts[1:]):
                    segments.append((a[0], a[1], b[0], b[1]))

        except Exception:
            return []

        return segments

    def _extract_text_labels(self, msp) -> List[TextLabel]:
        labels: List[TextLabel] = []
        idx = 1

        for entity in msp:
            if entity.dxftype() not in ["TEXT", "MTEXT"]:
                continue

            try:
                raw_text = str(entity.dxf.text) if entity.dxftype() == "TEXT" else str(entity.text)
                text = self._clean_text(raw_text)

                if not text:
                    continue

                insert = entity.dxf.insert

                labels.append(
                    TextLabel(
                        id=idx,
                        text=text,
                        x=float(insert.x),
                        y=float(insert.y),
                        floor=self._infer_floor_from_text(text),
                        confidence=0.85,
                    )
                )
                idx += 1

            except Exception:
                continue

        return labels

    def _filter_out_sheet_border_segments(
        self,
        segments: List[_RawSegment],
        labels: List[TextLabel],
    ) -> List[_RawSegment]:
        if not segments:
            return []

        if len(segments) < 8:
            return segments

        if labels:
            label_xs = [float(label.x) for label in labels]
            label_ys = [float(label.y) for label in labels]

            lx1 = min(label_xs)
            lx2 = max(label_xs)
            ly1 = min(label_ys)
            ly2 = max(label_ys)

            label_w = max(lx2 - lx1, 1.0)
            label_h = max(ly2 - ly1, 1.0)
            pad = max(label_w, label_h, 6.0) * 2.6

            crop_x1 = lx1 - pad
            crop_x2 = lx2 + pad
            crop_y1 = ly1 - pad
            crop_y2 = ly2 + pad

            cropped: List[_RawSegment] = []

            for s in segments:
                cx = (s.x1 + s.x2) / 2.0
                cy = (s.y1 + s.y2) / 2.0
                length = math.hypot(s.x2 - s.x1, s.y2 - s.y1)

                inside_crop = crop_x1 <= cx <= crop_x2 and crop_y1 <= cy <= crop_y2

                too_large_for_label_cluster = (
                    length > max(label_w, label_h, 1.0) * 4.2
                    and not inside_crop
                )

                if too_large_for_label_cluster:
                    continue

                if inside_crop:
                    cropped.append(s)

            if len(cropped) >= max(8, int(len(segments) * 0.18)):
                return cropped

        lengths = [math.hypot(s.x2 - s.x1, s.y2 - s.y1) for s in segments]
        sorted_lengths = sorted(lengths)
        median_len = sorted_lengths[len(sorted_lengths) // 2]

        if median_len <= 0:
            return segments

        max_reasonable = median_len * 18.0

        filtered = [
            s for s in segments
            if math.hypot(s.x2 - s.x1, s.y2 - s.y1) <= max_reasonable
        ]

        if len(filtered) >= max(8, int(len(segments) * 0.35)):
            return filtered

        return segments

    def _compute_bounds(
        self,
        segments: List[_RawSegment],
        labels: List[TextLabel],
        pad_ratio: float = 0.04,
    ) -> Dict[str, float]:
        xs: List[float] = []
        ys: List[float] = []

        for s in segments:
            xs.extend([s.x1, s.x2])
            ys.extend([s.y1, s.y2])

        for label in labels:
            xs.append(label.x)
            ys.append(label.y)

        if not xs or not ys:
            return {
                "min_x": 0.0,
                "min_y": 0.0,
                "max_x": 10.0,
                "max_y": 10.0,
                "width": 10.0,
                "height": 10.0,
            }

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        pad = max(width, height) * pad_ratio

        min_x -= pad
        min_y -= pad
        max_x += pad
        max_y += pad

        return {
            "min_x": float(min_x),
            "min_y": float(min_y),
            "max_x": float(max_x),
            "max_y": float(max_y),
            "width": float(max_x - min_x),
            "height": float(max_y - min_y),
        }

    def _adaptive_snap_tolerance(self, bounds: Dict[str, float]) -> float:
        diag = math.hypot(bounds["width"], bounds["height"])
        return max(self.min_snap_tolerance, min(self.max_snap_tolerance, diag * self.snap_tolerance_ratio))

    def _rooms_from_label_wall_rays(
        self,
        segments: List[_RawSegment],
        labels: List[TextLabel],
        bounds: Dict[str, float],
    ) -> List[RoomModel]:
        if not segments or not labels:
            return []

        h_segments, v_segments = self._axis_segments_for_rays(segments)
        rooms: List[RoomModel] = []
        rid = 1

        useful_labels = [label for label in labels if self._looks_like_room_label(label.text)]
        if not useful_labels:
            useful_labels = labels

        for label in useful_labels:
            box = self._find_wall_box_around_point(label.x, label.y, h_segments, v_segments, bounds)

            if box is None:
                continue

            x1, y1, x2, y2 = box
            width = x2 - x1
            height = y2 - y1
            area = width * height

            if width < self.min_room_side or height < self.min_room_side:
                continue

            if area < self.min_room_area_absolute:
                continue

            if area > bounds["width"] * bounds["height"] * self.max_room_area_ratio:
                continue

            polygon = [
                Point2D(x=x1, y=y1),
                Point2D(x=x2, y=y1),
                Point2D(x=x2, y=y2),
                Point2D(x=x1, y=y2),
            ]

            room_type = self._infer_room_type(label.text, area, width, height, polygon)
            zone = self._infer_zone(label.text, room_type)

            rooms.append(
                RoomModel(
                    id=rid,
                    name=label.text.strip() if label.text.strip() else self._fallback_room_name(room_type, rid),
                    floor=label.floor if label.floor != "unknown" else "ground",
                    x=round(x1, 4),
                    y=round(y1, 4),
                    width=round(width, 4),
                    height=round(height, 4),
                    area=round(area, 3),
                    center_x=round((x1 + x2) / 2.0, 4),
                    center_y=round((y1 + y2) / 2.0, 4),
                    polygon=polygon,
                    room_type=room_type,
                    zone=zone,
                    expected_clients=self._estimate_expected_clients(room_type, area),
                    traffic_profile=self._traffic_profile(room_type, label.text),
                    priority_weight=self._priority_weight(room_type, zone),
                    label_text=label.text,
                    source_layer="wall_ray_label_assigned",
                    confidence=0.74,
                    neighbors=[],
                )
            )
            rid += 1

        return rooms

    def _axis_segments_for_rays(
        self,
        segments: List[_RawSegment],
    ) -> Tuple[List[_RawSegment], List[_RawSegment]]:
        h_segments: List[_RawSegment] = []
        v_segments: List[_RawSegment] = []

        for s in segments:
            orientation = self._segment_orientation(s)

            if orientation == "h":
                y = (s.y1 + s.y2) / 2.0
                x1, x2 = sorted([s.x1, s.x2])
                h_segments.append(
                    _RawSegment(
                        x1=x1,
                        y1=y,
                        x2=x2,
                        y2=y,
                        layer=s.layer,
                        is_structural=s.is_structural,
                    )
                )

            elif orientation == "v":
                x = (s.x1 + s.x2) / 2.0
                y1, y2 = sorted([s.y1, s.y2])
                v_segments.append(
                    _RawSegment(
                        x1=x,
                        y1=y1,
                        x2=x,
                        y2=y2,
                        layer=s.layer,
                        is_structural=s.is_structural,
                    )
                )

        return h_segments, v_segments

    def _find_wall_box_around_point(
        self,
        px: float,
        py: float,
        h_segments: List[_RawSegment],
        v_segments: List[_RawSegment],
        bounds: Dict[str, float],
    ) -> Optional[Tuple[float, float, float, float]]:
        left_candidates = []
        right_candidates = []

        for s in v_segments:
            x = s.x1
            y1 = min(s.y1, s.y2) - self.ray_wall_tolerance
            y2 = max(s.y1, s.y2) + self.ray_wall_tolerance

            if y1 <= py <= y2:
                if x < px:
                    left_candidates.append(x)
                elif x > px:
                    right_candidates.append(x)

        bottom_candidates = []
        top_candidates = []

        for s in h_segments:
            y = s.y1
            x1 = min(s.x1, s.x2) - self.ray_wall_tolerance
            x2 = max(s.x1, s.x2) + self.ray_wall_tolerance

            if x1 <= px <= x2:
                if y < py:
                    bottom_candidates.append(y)
                elif y > py:
                    top_candidates.append(y)

        if not left_candidates or not right_candidates or not bottom_candidates or not top_candidates:
            return None

        left_candidates = sorted(set(round(x, 4) for x in left_candidates), reverse=True)
        right_candidates = sorted(set(round(x, 4) for x in right_candidates))
        bottom_candidates = sorted(set(round(y, 4) for y in bottom_candidates), reverse=True)
        top_candidates = sorted(set(round(y, 4) for y in top_candidates))

        best_box = None
        best_score = 1e18

        for lx in left_candidates[:5]:
            for rx in right_candidates[:5]:
                width = rx - lx
                if width <= self.min_room_side or width > self.ray_max_room_width:
                    continue

                for by in bottom_candidates[:5]:
                    for ty in top_candidates[:5]:
                        height = ty - by
                        if height <= self.min_room_side or height > self.ray_max_room_height:
                            continue

                        area = width * height

                        if area < self.min_room_area_absolute:
                            continue

                        vertical_ok = (
                            self._has_vertical_wall_covering(v_segments, lx, by, ty)
                            and self._has_vertical_wall_covering(v_segments, rx, by, ty)
                        )
                        horizontal_ok = (
                            self._has_horizontal_wall_covering(h_segments, by, lx, rx)
                            and self._has_horizontal_wall_covering(h_segments, ty, lx, rx)
                        )

                        if not (vertical_ok and horizontal_ok):
                            continue

                        aspect = max(width, height) / max(min(width, height), 1e-9)

                        if aspect >= self.corridor_min_aspect:
                            score = area * 0.92
                        else:
                            score = area

                        if score < best_score:
                            best_score = score
                            best_box = (lx, by, rx, ty)

        return best_box

    def _has_vertical_wall_covering(
        self,
        v_segments: List[_RawSegment],
        x: float,
        y1: float,
        y2: float,
    ) -> bool:
        need = max(0.25, (y2 - y1) * 0.42)
        covered = 0.0

        for s in v_segments:
            if abs(s.x1 - x) > 0.16:
                continue

            a = max(min(s.y1, s.y2), y1)
            b = min(max(s.y1, s.y2), y2)

            if b > a:
                covered += b - a

        return covered >= need

    def _has_horizontal_wall_covering(
        self,
        h_segments: List[_RawSegment],
        y: float,
        x1: float,
        x2: float,
    ) -> bool:
        need = max(0.25, (x2 - x1) * 0.42)
        covered = 0.0

        for s in h_segments:
            if abs(s.y1 - y) > 0.16:
                continue

            a = max(min(s.x1, s.x2), x1)
            b = min(max(s.x1, s.x2), x2)

            if b > a:
                covered += b - a

        return covered >= need

    def _detect_simple_axis_loops(
        self,
        segments: List[_RawSegment],
        bounds: Dict[str, float],
    ) -> List[_LoopCandidate]:
        h_segments, v_segments = self._axis_segments_for_rays(segments)

        xs = sorted(set(round(s.x1, 3) for s in v_segments))
        ys = sorted(set(round(s.y1, 3) for s in h_segments))

        loops: List[_LoopCandidate] = []

        if len(xs) < 2 or len(ys) < 2:
            return []

        max_area = bounds["width"] * bounds["height"] * self.max_room_area_ratio

        for i in range(len(xs) - 1):
            for j in range(len(ys) - 1):
                x1, x2 = xs[i], xs[i + 1]
                y1, y2 = ys[j], ys[j + 1]

                w = x2 - x1
                h = y2 - y1
                area = w * h

                if w < self.min_room_side or h < self.min_room_side:
                    continue

                if area < self.min_room_area_absolute or area > max_area:
                    continue

                vertical_ok = (
                    self._has_vertical_wall_covering(v_segments, x1, y1, y2)
                    and self._has_vertical_wall_covering(v_segments, x2, y1, y2)
                )
                horizontal_ok = (
                    self._has_horizontal_wall_covering(h_segments, y1, x1, x2)
                    and self._has_horizontal_wall_covering(h_segments, y2, x1, x2)
                )

                if not (vertical_ok and horizontal_ok):
                    continue

                polygon = [
                    Point2D(x=x1, y=y1),
                    Point2D(x=x2, y=y1),
                    Point2D(x=x2, y=y2),
                    Point2D(x=x1, y=y2),
                ]

                loops.append(
                    _LoopCandidate(
                        polygon=polygon,
                        area=area,
                        perimeter=2.0 * (w + h),
                        center_x=(x1 + x2) / 2.0,
                        center_y=(y1 + y2) / 2.0,
                        confidence=0.60,
                        source="axis_grid_loop",
                    )
                )

        return self._remove_outer_and_duplicate_loops(loops)

    def _merge_axis_loop_rooms(
        self,
        base_rooms: List[RoomModel],
        loops: List[_LoopCandidate],
        labels: List[TextLabel],
        bounds: Dict[str, float],
    ) -> List[RoomModel]:
        merged = list(base_rooms)
        next_id = max([r.id for r in merged], default=0) + 1

        for loop in sorted(loops, key=lambda l: l.area):
            min_x, min_y, max_x, max_y = self._polygon_bbox(loop.polygon)
            width = max_x - min_x
            height = max_y - min_y
            aspect = max(width, height) / max(min(width, height), 1e-9)

            label = self._best_label_for_polygon(labels, loop.polygon)
            label_text = label.text if label else ""

            label_room_type = self._infer_room_type(label_text, loop.area, width, height, loop.polygon) if label else "unknown"

            is_corridor_shape = (
                aspect >= self.corridor_min_aspect
                and loop.area >= self.corridor_min_area
                and min(width, height) <= self.corridor_max_width
            )

            is_service_or_bath_label = label_room_type in ["bathroom", "service", "kitchen", "server_room"]
            is_named_room_label = bool(label_text) and self._looks_like_room_label(label_text)

            should_add = False
            forced_type = "unknown"

            if is_corridor_shape:
                should_add = True
                forced_type = "corridor"
            elif is_named_room_label and is_service_or_bath_label:
                should_add = True
                forced_type = label_room_type

            if not should_add:
                continue

            temp_room = self._room_from_loop(
                loop=loop,
                rid=next_id,
                label=label,
                forced_type=forced_type,
            )

            max_overlap = 0.0
            for existing in merged:
                max_overlap = max(max_overlap, self._bbox_overlap_ratio(temp_room, existing))

            if forced_type == "corridor":
                if max_overlap > self.corridor_max_overlap_with_rooms:
                    continue
            else:
                if max_overlap > 0.55:
                    continue

            merged.append(temp_room)
            next_id += 1

        return merged

    def _room_from_loop(
        self,
        loop: _LoopCandidate,
        rid: int,
        label: Optional[TextLabel],
        forced_type: str = "unknown",
    ) -> RoomModel:
        min_x, min_y, max_x, max_y = self._polygon_bbox(loop.polygon)
        width = max_x - min_x
        height = max_y - min_y
        label_text = label.text if label else ""

        if forced_type != "unknown":
            room_type = forced_type
        else:
            room_type = self._infer_room_type(label_text, loop.area, width, height, loop.polygon)

        zone = self._infer_zone(label_text, room_type)

        return RoomModel(
            id=rid,
            name=label_text.strip() if label_text.strip() else self._fallback_room_name(room_type, rid),
            floor=label.floor if label and label.floor != "unknown" else "ground",
            x=float(min_x),
            y=float(min_y),
            width=float(width),
            height=float(height),
            area=round(float(loop.area), 3),
            center_x=float(loop.center_x),
            center_y=float(loop.center_y),
            polygon=loop.polygon,
            room_type=room_type,
            zone=zone,
            expected_clients=self._estimate_expected_clients(room_type, loop.area),
            traffic_profile=self._traffic_profile(room_type, label_text),
            priority_weight=self._priority_weight(room_type, zone),
            label_text=label_text,
            source_layer=loop.source if forced_type != "corridor" else "axis_grid_corridor",
            confidence=round(loop.confidence + (0.05 if label else 0.0), 3),
            neighbors=[],
        )

    def _remove_outer_and_duplicate_loops(self, loops: List[_LoopCandidate]) -> List[_LoopCandidate]:
        if not loops:
            return []

        total_area = max(l.area for l in loops)
        filtered = [l for l in loops if l.area < total_area * 0.985 or len(loops) <= 2]

        cleaned: List[_LoopCandidate] = []

        for loop in filtered:
            min_x, min_y, max_x, max_y = self._polygon_bbox(loop.polygon)
            w = max_x - min_x
            h = max_y - min_y

            if w < self.min_room_side or h < self.min_room_side:
                continue

            fill_ratio = loop.area / max(w * h, 1e-9)

            if fill_ratio < 0.10:
                continue

            cleaned.append(loop)

        unique: List[_LoopCandidate] = []

        for loop in sorted(cleaned, key=lambda x: x.area):
            duplicate = False

            for kept in unique:
                center_d = math.hypot(loop.center_x - kept.center_x, loop.center_y - kept.center_y)
                area_ratio = min(loop.area, kept.area) / max(loop.area, kept.area, 1e-9)

                if center_d < self.duplicate_center_tolerance and area_ratio > 0.82:
                    duplicate = True
                    break

            if not duplicate:
                unique.append(loop)

        return unique

    def _fallback_raster_rooms(
        self,
        segments: List[_RawSegment],
        labels: List[TextLabel],
        bounds: Dict[str, float],
    ) -> List[RoomModel]:
        if cv2 is None or np is None:
            return []

        scale = self._raster_scale(bounds)
        w = int(bounds["width"] * scale) + 30
        h = int(bounds["height"] * scale) + 30

        wall = np.zeros((max(80, h), max(80, w)), dtype=np.uint8)

        for s in segments:
            p1 = self._cad_to_px(s.x1, s.y1, bounds, scale)
            p2 = self._cad_to_px(s.x2, s.y2, bounds, scale)

            thickness = max(2, int(scale * 0.12))
            cv2.line(wall, p1, p2, 255, thickness, lineType=cv2.LINE_AA)

        close_kernel = max(3, int(scale * 0.16))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (close_kernel, close_kernel))
        wall = cv2.morphologyEx(wall, cv2.MORPH_CLOSE, kernel, iterations=1)

        free = np.where(wall > 0, 0, 255).astype(np.uint8)
        flood = free.copy()
        mask = np.zeros((free.shape[0] + 2, free.shape[1] + 2), dtype=np.uint8)
        cv2.floodFill(flood, mask, (0, 0), 0)

        enclosed = flood
        contours, _ = cv2.findContours(enclosed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        loops: List[_LoopCandidate] = []

        for contour in contours:
            px_area = cv2.contourArea(contour)

            if px_area < 45:
                continue

            epsilon = 0.006 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            polygon: List[Point2D] = []

            for p in approx.reshape(-1, 2):
                x, y = self._px_to_cad(int(p[0]), int(p[1]), bounds, scale)
                polygon.append(Point2D(x=x, y=y))

            polygon = self._dedupe_polygon_points(polygon)

            if len(polygon) < 3:
                continue

            area = abs(self._signed_polygon_area(polygon))
            perimeter = self._polygon_perimeter(polygon)

            if area < self.min_room_area_absolute:
                continue

            cx, cy = self._polygon_centroid(polygon)

            loops.append(
                _LoopCandidate(
                    polygon=polygon,
                    area=area,
                    perimeter=perimeter,
                    center_x=cx,
                    center_y=cy,
                    confidence=0.54,
                    source="raster_wall_fallback",
                )
            )

        loops = self._remove_outer_and_duplicate_loops(loops)

        rooms: List[RoomModel] = []
        next_id = 1
        for loop in loops:
            label = self._best_label_for_polygon(labels, loop.polygon)
            min_x, min_y, max_x, max_y = self._polygon_bbox(loop.polygon)
            width = max_x - min_x
            height = max_y - min_y
            aspect = max(width, height) / max(min(width, height), 1e-9)
            is_corridor = (
                aspect >= self.corridor_min_aspect
                and min(width, height) <= self.corridor_max_width
            )

            if label is None and not is_corridor:
                continue

            room = self._room_from_loop(
                loop=loop,
                rid=next_id,
                label=label,
                forced_type="corridor" if is_corridor else "unknown",
            )
            rooms.append(room)
            next_id += 1

        return rooms

    def _raster_scale(self, bounds: Dict[str, float]) -> float:
        longest = max(bounds["width"], bounds["height"], 1.0)
        return max(18.0, min(70.0, 1800.0 / longest))

    def _cad_to_px(self, x: float, y: float, bounds: Dict[str, float], scale: float) -> Tuple[int, int]:
        px = int(round((x - bounds["min_x"]) * scale + 12))
        py = int(round((bounds["max_y"] - y) * scale + 12))
        return px, py

    def _px_to_cad(self, px: int, py: int, bounds: Dict[str, float], scale: float) -> Tuple[float, float]:
        x = (px - 12) / scale + bounds["min_x"]
        y = bounds["max_y"] - (py - 12) / scale
        return float(x), float(y)

    def _heal_wall_gaps(self, segments: List[_RawSegment]) -> List[_RawSegment]:
        if not segments:
            return []

        healed = list(segments)
        healed.extend(self._close_collinear_endpoint_gaps(segments))
        healed.extend(self._close_near_perpendicular_junctions(segments))

        return self._remove_duplicate_segments(healed, self.min_snap_tolerance)

    def _close_collinear_endpoint_gaps(self, segments: List[_RawSegment]) -> List[_RawSegment]:
        additions: List[_RawSegment] = []
        endpoints = []

        for idx, s in enumerate(segments):
            orientation = self._segment_orientation(s)
            endpoints.append((idx, s.x1, s.y1, orientation, s.layer, s.is_structural))
            endpoints.append((idx, s.x2, s.y2, orientation, s.layer, s.is_structural))

        for i in range(len(endpoints)):
            idx1, x1, y1, o1, layer1, st1 = endpoints[i]

            if o1 not in ["h", "v"]:
                continue

            for j in range(i + 1, len(endpoints)):
                idx2, x2, y2, o2, layer2, st2 = endpoints[j]

                if idx1 == idx2:
                    continue

                if o1 != o2:
                    continue

                d = math.hypot(x2 - x1, y2 - y1)

                if d <= 0.02 or d > self.max_gap_close:
                    continue

                if o1 == "h":
                    if abs(y1 - y2) > self.max_collinear_offset:
                        continue

                    y = (y1 + y2) / 2.0
                    additions.append(
                        _RawSegment(
                            x1=min(x1, x2),
                            y1=y,
                            x2=max(x1, x2),
                            y2=y,
                            layer=layer1 or layer2 or "healed-gap",
                            is_structural=st1 or st2,
                        )
                    )

                elif o1 == "v":
                    if abs(x1 - x2) > self.max_collinear_offset:
                        continue

                    x = (x1 + x2) / 2.0
                    additions.append(
                        _RawSegment(
                            x1=x,
                            y1=min(y1, y2),
                            x2=x,
                            y2=max(y1, y2),
                            layer=layer1 or layer2 or "healed-gap",
                            is_structural=st1 or st2,
                        )
                    )

        return additions

    def _close_near_perpendicular_junctions(self, segments: List[_RawSegment]) -> List[_RawSegment]:
        additions: List[_RawSegment] = []
        endpoints = []

        for idx, s in enumerate(segments):
            orientation = self._segment_orientation(s)
            endpoints.append((idx, s.x1, s.y1, orientation, s.layer, s.is_structural))
            endpoints.append((idx, s.x2, s.y2, orientation, s.layer, s.is_structural))

        max_junction_gap = min(self.max_gap_close, 0.30)

        for i in range(len(endpoints)):
            idx1, x1, y1, o1, layer1, st1 = endpoints[i]

            if o1 not in ["h", "v"]:
                continue

            for j in range(i + 1, len(endpoints)):
                idx2, x2, y2, o2, layer2, st2 = endpoints[j]

                if idx1 == idx2:
                    continue

                if o1 == o2:
                    continue

                if o2 not in ["h", "v"]:
                    continue

                d = math.hypot(x2 - x1, y2 - y1)

                if d <= 0.02 or d > max_junction_gap:
                    continue

                additions.append(
                    _RawSegment(
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        layer=layer1 or layer2 or "healed-junction",
                        is_structural=st1 or st2,
                    )
                )

        return additions

    def _segment_orientation(self, s: _RawSegment) -> str:
        dx = abs(s.x2 - s.x1)
        dy = abs(s.y2 - s.y1)

        if dx >= dy * 3.0:
            return "h"
        if dy >= dx * 3.0:
            return "v"
        return "d"

    def _snap_and_merge_segments(self, segments: List[_RawSegment], tol: float) -> List[_RawSegment]:
        axis_snapped = [self._axis_snap_segment(s) for s in segments]
        endpoint_snapped = self._snap_near_endpoints(axis_snapped, tol)
        merged = self._merge_collinear_segments(endpoint_snapped, tol)
        return merged

    def _axis_snap_segment(self, s: _RawSegment) -> _RawSegment:
        dx = abs(s.x2 - s.x1)
        dy = abs(s.y2 - s.y1)

        ns = _RawSegment(s.x1, s.y1, s.x2, s.y2, s.layer, s.is_structural)

        if dx > 0 and dy / max(dx, 1e-9) < 0.035:
            y = (s.y1 + s.y2) / 2.0
            ns.y1 = y
            ns.y2 = y

        elif dy > 0 and dx / max(dy, 1e-9) < 0.035:
            x = (s.x1 + s.x2) / 2.0
            ns.x1 = x
            ns.x2 = x

        return ns

    def _snap_near_endpoints(self, segments: List[_RawSegment], tol: float) -> List[_RawSegment]:
        endpoints: List[Tuple[float, float]] = []

        for s in segments:
            endpoints.append((s.x1, s.y1))
            endpoints.append((s.x2, s.y2))

        clusters: List[List[Tuple[float, float]]] = []

        for p in endpoints:
            placed = False

            for cluster in clusters:
                cx = sum(q[0] for q in cluster) / len(cluster)
                cy = sum(q[1] for q in cluster) / len(cluster)

                if math.hypot(p[0] - cx, p[1] - cy) <= tol:
                    cluster.append(p)
                    placed = True
                    break

            if not placed:
                clusters.append([p])

        representatives: Dict[Tuple[int, int], Tuple[float, float]] = {}

        for cluster in clusters:
            cx = sum(q[0] for q in cluster) / len(cluster)
            cy = sum(q[1] for q in cluster) / len(cluster)

            for q in cluster:
                representatives[self._point_key(q[0], q[1], tol / 4.0)] = (cx, cy)

        snapped: List[_RawSegment] = []

        for s in segments:
            a = representatives.get(self._point_key(s.x1, s.y1, tol / 4.0), (s.x1, s.y1))
            b = representatives.get(self._point_key(s.x2, s.y2, tol / 4.0), (s.x2, s.y2))

            if math.hypot(b[0] - a[0], b[1] - a[1]) >= self.min_segment_length:
                snapped.append(_RawSegment(a[0], a[1], b[0], b[1], s.layer, s.is_structural))

        return snapped

    def _merge_collinear_segments(self, segments: List[_RawSegment], tol: float) -> List[_RawSegment]:
        horizontals: List[_RawSegment] = []
        verticals: List[_RawSegment] = []
        others: List[_RawSegment] = []

        for s in segments:
            if abs(s.y1 - s.y2) <= tol * 0.35:
                horizontals.append(s)
            elif abs(s.x1 - s.x2) <= tol * 0.35:
                verticals.append(s)
            else:
                others.append(s)

        merged: List[_RawSegment] = []
        merged.extend(self._merge_axis_segments(horizontals, horizontal=True, tol=tol))
        merged.extend(self._merge_axis_segments(verticals, horizontal=False, tol=tol))
        merged.extend(others)

        return self._remove_duplicate_segments(merged, tol)

    def _merge_axis_segments(self, segments: List[_RawSegment], horizontal: bool, tol: float) -> List[_RawSegment]:
        if not segments:
            return []

        groups: Dict[int, List[_RawSegment]] = {}

        for s in segments:
            const = (s.y1 + s.y2) / 2.0 if horizontal else (s.x1 + s.x2) / 2.0
            key = round(const / max(tol, 1e-9))
            groups.setdefault(key, []).append(s)

        merged: List[_RawSegment] = []

        for group in groups.values():
            spans = []

            for s in group:
                if horizontal:
                    a, b = sorted([s.x1, s.x2])
                    const = (s.y1 + s.y2) / 2.0
                else:
                    a, b = sorted([s.y1, s.y2])
                    const = (s.x1 + s.x2) / 2.0

                spans.append((a, b, const, s.layer, s.is_structural))

            spans.sort(key=lambda item: item[0])
            cur_a, cur_b, const, layer, structural = spans[0]

            for a, b, c, lyr, st in spans[1:]:
                if a <= cur_b + tol * 1.25:
                    cur_b = max(cur_b, b)
                    structural = structural or st
                    if self._is_wall_layer(lyr):
                        layer = lyr
                else:
                    merged.append(self._axis_segment(cur_a, cur_b, const, horizontal, layer, structural))
                    cur_a, cur_b, const, layer, structural = a, b, c, lyr, st

            merged.append(self._axis_segment(cur_a, cur_b, const, horizontal, layer, structural))

        return merged

    def _axis_segment(
        self,
        a: float,
        b: float,
        const: float,
        horizontal: bool,
        layer: str,
        structural: bool,
    ) -> _RawSegment:
        if horizontal:
            return _RawSegment(a, const, b, const, layer, structural)
        return _RawSegment(const, a, const, b, layer, structural)

    def _split_segments_at_intersections(self, segments: List[_RawSegment], tol: float) -> List[_RawSegment]:
        result: List[_RawSegment] = []
        split_points: Dict[int, List[Tuple[float, float, float]]] = {}

        for i, s in enumerate(segments):
            split_points[i] = [(0.0, s.x1, s.y1), (1.0, s.x2, s.y2)]

        for i in range(len(segments)):
            s1 = segments[i]

            for j in range(i + 1, len(segments)):
                s2 = segments[j]
                inter = self._segment_intersection(s1, s2, tol)

                if inter is None:
                    continue

                x, y, t1, t2 = inter

                if -tol <= t1 <= 1 + tol and -tol <= t2 <= 1 + tol:
                    split_points[i].append((max(0.0, min(1.0, t1)), x, y))
                    split_points[j].append((max(0.0, min(1.0, t2)), x, y))

        for i, s in enumerate(segments):
            pts = split_points[i]
            pts.sort(key=lambda item: item[0])

            cleaned: List[Tuple[float, float, float]] = []

            for p in pts:
                if not cleaned:
                    cleaned.append(p)
                else:
                    _, px, py = cleaned[-1]
                    if math.hypot(p[1] - px, p[2] - py) > tol * 0.40:
                        cleaned.append(p)

            for a, b in zip(cleaned, cleaned[1:]):
                _, x1, y1 = a
                _, x2, y2 = b

                if math.hypot(x2 - x1, y2 - y1) >= self.min_segment_length:
                    result.append(_RawSegment(x1, y1, x2, y2, s.layer, s.is_structural))

        return self._remove_duplicate_segments(result, tol)

    def _segment_intersection(
        self,
        s1: _RawSegment,
        s2: _RawSegment,
        tol: float,
    ) -> Optional[Tuple[float, float, float, float]]:
        x1, y1, x2, y2 = s1.x1, s1.y1, s1.x2, s1.y2
        x3, y3, x4, y4 = s2.x1, s2.y1, s2.x2, s2.y2

        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)

        if abs(den) < 1e-10:
            return None

        px_num = (x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)
        py_num = (x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)

        px = px_num / den
        py = py_num / den

        t1 = self._projection_t(px, py, x1, y1, x2, y2)
        t2 = self._projection_t(px, py, x3, y3, x4, y4)

        if -tol <= t1 <= 1 + tol and -tol <= t2 <= 1 + tol:
            return px, py, t1, t2

        return None

    def _projection_t(self, px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        dx = x2 - x1
        dy = y2 - y1
        denom = dx * dx + dy * dy

        if denom <= 1e-12:
            return 0.0

        return ((px - x1) * dx + (py - y1) * dy) / denom

    def _remove_short_segments(self, segments: List[_RawSegment], min_len: float) -> List[_RawSegment]:
        return [s for s in segments if math.hypot(s.x2 - s.x1, s.y2 - s.y1) >= min_len]

    def _remove_duplicate_segments(self, segments: List[_RawSegment], tol: float) -> List[_RawSegment]:
        seen: Set[Tuple[int, int, int, int]] = set()
        out: List[_RawSegment] = []

        for s in segments:
            k1 = self._point_key(s.x1, s.y1, tol / 3.0)
            k2 = self._point_key(s.x2, s.y2, tol / 3.0)
            key = (*k1, *k2) if k1 <= k2 else (*k2, *k1)

            if key in seen:
                continue

            seen.add(key)
            out.append(s)

        return out

    def _semantic_validate_spaces(self, rooms: List[RoomModel], labels: List[TextLabel]) -> List[RoomModel]:
        for room in rooms:
            text = self._normalize_text_for_matching(f"{room.name} {room.label_text or ''}")
            aspect = max(room.width, room.height) / max(min(room.width, room.height), 1e-9)
            narrow = min(room.width, room.height)
            label_count = self._count_room_labels_inside(room, labels)

            is_bath = any(k in text for k in ["bath", "bathroom", "toilet", "wc", "w c", "lav", "shower", "حمام"])
            is_service = any(k in text for k in ["store", "storage", "stor", "service", "utility", "mechanical", "electrical", "مخزن"])
            is_reception = any(k in text for k in ["reception", "lobby", "waiting", "entrance"])
            is_corridor_label = any(k in text for k in ["corridor", "corr", "hall", "hallway", "passage", "ممر"])
            is_meeting = any(k in text for k in ["meeting", "conference", "call center", "class", "lecture", "training"])

            long_narrow = (
                aspect >= self.circulation_aspect
                and narrow <= self.circulation_max_narrow_side
                and room.area >= self.corridor_min_area
            )

            if is_bath:
                room.room_type = "bathroom"
                room.zone = "service"
                room.expected_clients = 0
                room.traffic_profile = "low"
                room.priority_weight = 0.25
                room.confidence = max(room.confidence, 0.78)
                continue

            if is_service:
                room.room_type = "service"
                room.zone = "service"
                room.expected_clients = self._estimate_expected_clients("service", room.area)
                room.traffic_profile = "low"
                room.priority_weight = 0.65
                room.confidence = max(room.confidence, 0.72)
                continue

            if long_narrow:
                if is_reception:
                    room.room_type = "reception"
                    room.zone = "guest"
                    room.traffic_profile = "high"
                    room.priority_weight = 1.30
                    room.confidence = max(room.confidence, 0.74)
                    if not room.name.lower().startswith("reception"):
                        room.name = f"Reception Circulation {room.id}"
                    room.source_layer = f"{room.source_layer}+semantic_reception_circulation"
                elif is_meeting:
                    room.room_type = "meeting"
                    room.traffic_profile = "high"
                    room.priority_weight = 1.45
                    room.confidence = max(room.confidence, 0.72)
                else:
                    room.room_type = "corridor"
                    room.zone = "staff"
                    room.traffic_profile = "low"
                    room.priority_weight = 1.10
                    room.expected_clients = self._estimate_expected_clients("corridor", room.area)
                    if not is_corridor_label and not room.name.lower().startswith("corridor"):
                        room.name = f"Corridor {room.id}"
                    room.source_layer = f"{room.source_layer}+semantic_corridor"
                    room.confidence = max(room.confidence, 0.70)

            if label_count >= self.large_bad_room_label_count and room.area >= self.max_labeled_room_area_without_special_label:
                if room.room_type not in ["corridor", "reception", "open_area", "meeting"]:
                    room.confidence = min(room.confidence, 0.50)
                    room.source_layer = f"{room.source_layer}+suspicious_multi_label"

        return rooms

    def _recover_missing_corridors(
        self,
        rooms: List[RoomModel],
        segments: List[_RawSegment],
        labels: List[TextLabel],
        bounds: Dict[str, float],
    ) -> List[RoomModel]:
        if any(r.room_type == "corridor" for r in rooms):
            return rooms

        loops = self._detect_simple_axis_loops(segments, bounds)
        candidate_corridors: List[RoomModel] = []

        next_id = max([r.id for r in rooms], default=0) + 1

        for loop in loops:
            min_x, min_y, max_x, max_y = self._polygon_bbox(loop.polygon)
            width = max_x - min_x
            height = max_y - min_y
            aspect = max(width, height) / max(min(width, height), 1e-9)
            narrow = min(width, height)

            if not (
                aspect >= self.corridor_min_aspect
                and narrow <= self.corridor_max_width
                and loop.area >= self.corridor_min_area
            ):
                continue

            label = self._best_label_for_polygon(labels, loop.polygon)
            label_text = label.text if label else ""
            label_norm = self._normalize_text_for_matching(label_text)

            if any(k in label_norm for k in ["office", "bath", "bathroom", "toilet", "store", "storage", "service", "kitchen"]):
                continue

            temp = self._room_from_loop(
                loop=loop,
                rid=next_id,
                label=None,
                forced_type="corridor",
            )

            max_overlap = max([self._bbox_overlap_ratio(temp, r) for r in rooms], default=0.0)
            if max_overlap > self.corridor_max_overlap_with_rooms:
                continue

            nearby_count = self._count_nearby_rooms(temp, rooms)
            if nearby_count < self.min_corridor_neighbor_count:
                continue

            temp.name = f"Corridor {next_id}"
            temp.label_text = ""
            temp.source_layer = "recovered_missing_corridor"
            temp.confidence = max(temp.confidence, 0.68)
            candidate_corridors.append(temp)
            next_id += 1

        if not candidate_corridors:
            return rooms

        candidate_corridors.sort(key=lambda r: (r.area, self._count_nearby_rooms(r, rooms)), reverse=True)

        final_corridors: List[RoomModel] = []
        for c in candidate_corridors:
            if all(self._bbox_overlap_ratio(c, existing) < 0.45 for existing in final_corridors):
                final_corridors.append(c)

            if len(final_corridors) >= 2:
                break

        return rooms + final_corridors

    def _force_corridor_from_room_layout(
        self,
        rooms: List[RoomModel],
        labels: List[TextLabel],
        bounds: Dict[str, float],
    ) -> List[RoomModel]:
        """
        Final demo-safe corridor recovery.

        Some CAD files do not contain a clean closed corridor polygon. The normal
        extractor can then detect all offices/rooms but miss the circulation path.
        This method tries two safe fallbacks:

        1. Build a corridor polygon from narrow empty gaps between detected rooms.
        2. If no empty gap is usable, reclassify the best corridor-like room.

        The goal is not to invent many rooms. It only guarantees a visible
        corridor when the current extraction has zero corridor rooms.
        """
        if not rooms:
            return rooms

        if any(r.room_type == "corridor" for r in rooms):
            return rooms

        synthetic = self._build_corridor_from_room_gaps(rooms, labels, bounds)
        if synthetic is not None:
            synthetic.id = max([r.id for r in rooms], default=0) + 1
            return rooms + [synthetic]

        # Last fallback: if a room is clearly long/narrow or corridor-labeled but
        # was classified as office/open_area/reception, reclassify it instead of
        # increasing the extracted count with a fake room.
        best_room = None
        best_score = -1e9

        for room in rooms:
            if room.room_type in ["bathroom", "server_room", "storage", "service", "kitchen"]:
                continue

            w = max(float(room.width), 0.1)
            h = max(float(room.height), 0.1)
            area = max(float(room.area), 0.1)
            aspect = max(w, h) / max(min(w, h), 0.1)
            narrow = min(w, h)
            text = self._normalize_text_for_matching(room.name + " " + (room.label_text or ""))
            nearby = self._count_nearby_rooms(room, rooms)

            score = 0.0
            if any(k in text for k in ["corridor", "corr", "hall", "hallway", "ممر"]):
                score += 100.0
            if aspect >= 2.20:
                score += 30.0 + min(aspect, 7.0) * 4.0
            if narrow <= 3.80:
                score += 25.0
            if nearby >= 2:
                score += nearby * 8.0
            if room.room_type in ["open_area", "reception", "lobby", "unknown"]:
                score += 12.0
            if area < self.corridor_min_area:
                score -= 50.0

            if score > best_score:
                best_score = score
                best_room = room

        if best_room is not None and best_score >= 42.0:
            best_room.room_type = "corridor"
            best_room.zone = "staff"
            best_room.traffic_profile = "low"
            best_room.priority_weight = 1.10
            best_room.expected_clients = self._estimate_expected_clients("corridor", best_room.area)
            best_room.confidence = max(best_room.confidence, 0.64)
            best_room.source_layer = f"{best_room.source_layer}+forced_corridor_layout"
            if not str(best_room.name).lower().startswith("corridor"):
                best_room.name = f"Corridor {best_room.id}"
            if not best_room.label_text:
                best_room.label_text = best_room.name

        return rooms

    def _build_corridor_from_room_gaps(
        self,
        rooms: List[RoomModel],
        labels: List[TextLabel],
        bounds: Dict[str, float],
    ) -> Optional[RoomModel]:
        candidates: List[Tuple[float, float, float, float, float]] = []

        useful_rooms = [
            r for r in rooms
            if r.room_type not in ["corridor"]
            and float(r.width) > 0.05
            and float(r.height) > 0.05
        ]

        # Horizontal corridors: gap between lower and upper rooms.
        for lower in useful_rooms:
            for upper in useful_rooms:
                if lower.id == upper.id:
                    continue

                gap_y1 = float(lower.y + lower.height)
                gap_y2 = float(upper.y)
                gap = gap_y2 - gap_y1

                if gap <= 0.25 or gap > 4.20:
                    continue

                overlap_x1 = max(float(lower.x), float(upper.x))
                overlap_x2 = min(float(lower.x + lower.width), float(upper.x + upper.width))
                overlap = overlap_x2 - overlap_x1

                if overlap < 1.20:
                    continue

                length = overlap
                narrow = gap
                aspect = length / max(narrow, 0.1)

                if aspect < 1.45:
                    continue

                x1, y1, x2, y2 = overlap_x1, gap_y1, overlap_x2, gap_y2
                score = self._corridor_gap_score(x1, y1, x2, y2, rooms, labels, bounds)
                candidates.append((score, x1, y1, x2, y2))

        # Vertical corridors: gap between left and right rooms.
        for left in useful_rooms:
            for right in useful_rooms:
                if left.id == right.id:
                    continue

                gap_x1 = float(left.x + left.width)
                gap_x2 = float(right.x)
                gap = gap_x2 - gap_x1

                if gap <= 0.25 or gap > 4.20:
                    continue

                overlap_y1 = max(float(left.y), float(right.y))
                overlap_y2 = min(float(left.y + left.height), float(right.y + right.height))
                overlap = overlap_y2 - overlap_y1

                if overlap < 1.20:
                    continue

                length = overlap
                narrow = gap
                aspect = length / max(narrow, 0.1)

                if aspect < 1.45:
                    continue

                x1, y1, x2, y2 = gap_x1, overlap_y1, gap_x2, overlap_y2
                score = self._corridor_gap_score(x1, y1, x2, y2, rooms, labels, bounds)
                candidates.append((score, x1, y1, x2, y2))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)

        for score, x1, y1, x2, y2 in candidates[:12]:
            width = x2 - x1
            height = y2 - y1
            area = width * height

            if score < 18.0 or area < self.corridor_min_area:
                continue

            if self._bbox_overlap_any(x1, y1, x2, y2, rooms) > 0.08:
                continue

            polygon = [
                Point2D(x=round(x1, 4), y=round(y1, 4)),
                Point2D(x=round(x2, 4), y=round(y1, 4)),
                Point2D(x=round(x2, 4), y=round(y2, 4)),
                Point2D(x=round(x1, 4), y=round(y2, 4)),
            ]

            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0

            return RoomModel(
                id=0,
                name="Corridor",
                floor="ground",
                x=round(x1, 4),
                y=round(y1, 4),
                width=round(width, 4),
                height=round(height, 4),
                area=round(area, 3),
                center_x=round(cx, 4),
                center_y=round(cy, 4),
                polygon=polygon,
                room_type="corridor",
                zone="staff",
                expected_clients=self._estimate_expected_clients("corridor", area),
                traffic_profile="low",
                priority_weight=1.10,
                label_text="Corridor",
                source_layer="synthetic_corridor_from_room_gaps",
                confidence=0.62,
                neighbors=[],
            )

        return None

    def _corridor_gap_score(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        rooms: List[RoomModel],
        labels: List[TextLabel],
        bounds: Dict[str, float],
    ) -> float:
        width = max(x2 - x1, 0.1)
        height = max(y2 - y1, 0.1)
        length = max(width, height)
        narrow = min(width, height)
        area = width * height
        aspect = length / max(narrow, 0.1)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        nearby = 0
        for room in rooms:
            d = self._distance_point_to_bbox(cx, cy, room.x, room.y, room.x + room.width, room.y + room.height)
            if d <= max(narrow * 1.4, 0.8):
                nearby += 1

        label_penalty = 0.0
        for label in labels:
            if x1 <= label.x <= x2 and y1 <= label.y <= y2:
                text = self._normalize_text_for_matching(label.text)
                if any(k in text for k in ["bath", "toilet", "wc", "kitchen", "office", "bedroom", "meeting"]):
                    label_penalty += 30.0
                if any(k in text for k in ["corridor", "hall", "hallway", "ممر"]):
                    nearby += 4

        score = 0.0
        score += min(area, 30.0) * 0.8
        score += min(aspect, 8.0) * 6.0
        score += nearby * 7.0
        score -= max(0.0, narrow - 3.2) * 12.0
        score -= label_penalty

        # Prefer candidates inside the CAD bounds, not at the outer border.
        if x1 <= bounds.get("min_x", x1) + 0.1 or x2 >= bounds.get("max_x", x2) - 0.1:
            score -= 8.0
        if y1 <= bounds.get("min_y", y1) + 0.1 or y2 >= bounds.get("max_y", y2) - 0.1:
            score -= 8.0

        return score

    def _bbox_overlap_any(self, x1: float, y1: float, x2: float, y2: float, rooms: List[RoomModel]) -> float:
        area = max((x2 - x1) * (y2 - y1), 1e-9)
        worst = 0.0

        for room in rooms:
            rx1 = float(room.x)
            ry1 = float(room.y)
            rx2 = float(room.x + room.width)
            ry2 = float(room.y + room.height)

            ix1 = max(x1, rx1)
            iy1 = max(y1, ry1)
            ix2 = min(x2, rx2)
            iy2 = min(y2, ry2)

            if ix2 <= ix1 or iy2 <= iy1:
                continue

            overlap = (ix2 - ix1) * (iy2 - iy1)
            worst = max(worst, overlap / area)

        return worst

    def _distance_point_to_bbox(self, x: float, y: float, x1: float, y1: float, x2: float, y2: float) -> float:
        dx = max(x1 - x, 0.0, x - x2)
        dy = max(y1 - y, 0.0, y - y2)
        return math.hypot(dx, dy)

    def _count_nearby_rooms(self, corridor: RoomModel, rooms: List[RoomModel]) -> int:
        count = 0
        for room in rooms:
            if room.room_type in ["corridor"]:
                continue

            weight, _ = self._room_adjacency(corridor, room)
            if weight > 0:
                count += 1
                continue

            d = math.hypot(corridor.center_x - room.center_x, corridor.center_y - room.center_y)
            if d <= max(corridor.width, corridor.height, 2.0):
                count += 1

        return count

    def _count_room_labels_inside(self, room: RoomModel, labels: List[TextLabel]) -> int:
        count = 0
        for label in labels:
            if self._looks_like_room_label(label.text) and self._point_in_polygon(label.x, label.y, room.polygon):
                count += 1
        return count

    def _merge_room_sets(self, base: List[RoomModel], extra: List[RoomModel]) -> List[RoomModel]:
        merged = list(base)
        next_id = max([r.id for r in merged], default=0) + 1

        for room in extra:
            max_overlap = 0.0
            for existing in merged:
                max_overlap = max(max_overlap, self._bbox_overlap_ratio(room, existing))

            if max_overlap > 0.58:
                continue

            room.id = next_id
            merged.append(room)
            next_id += 1

        return merged

    def _force_corridor_classification(self, rooms: List[RoomModel]) -> List[RoomModel]:
        for room in rooms:
            aspect = max(room.width, room.height) / max(min(room.width, room.height), 1e-9)
            narrow_side = min(room.width, room.height)
            t = self._normalize_text_for_matching(room.name + " " + (room.label_text or ""))

            is_reception_like = any(k in t for k in ["reception", "lobby", "waiting", "entrance"])
            is_meeting_like = any(k in t for k in ["call center", "meeting", "conference", "class", "lecture"])
            is_bath_service = any(k in t for k in ["bath", "bathroom", "toilet", "wc", "store", "storage", "service", "kitchen"])

            if "corridor" in t or "corr" in t or "hall" in t or "ممر" in t:
                room.room_type = "corridor"
                room.zone = "staff"
                room.traffic_profile = "low"
                room.priority_weight = 1.10
                room.expected_clients = self._estimate_expected_clients("corridor", room.area)
                room.confidence = max(room.confidence, 0.72)

            elif (
                aspect >= self.corridor_min_aspect
                and narrow_side <= self.corridor_max_width
                and room.area >= self.corridor_min_area
                and not is_reception_like
                and not is_meeting_like
                and not is_bath_service
            ):
                room.room_type = "corridor"
                if not room.name.lower().startswith("corridor"):
                    room.name = f"Corridor {room.id}"
                room.zone = "staff"
                room.traffic_profile = "low"
                room.priority_weight = 1.10
                room.expected_clients = self._estimate_expected_clients("corridor", room.area)
                room.confidence = max(room.confidence, 0.66)

        return rooms

    def _deduplicate_rooms(self, rooms: List[RoomModel]) -> List[RoomModel]:
        kept: List[RoomModel] = []

        for room in sorted(rooms, key=lambda r: r.area):
            duplicate = False

            for other in kept:
                center_d = math.hypot(room.center_x - other.center_x, room.center_y - other.center_y)
                area_ratio = min(room.area, other.area) / max(room.area, other.area, 1e-9)

                same_label = (
                    self._normalize_text_for_matching(room.label_text or "")
                    == self._normalize_text_for_matching(other.label_text or "")
                    and bool(room.label_text)
                )

                bbox_overlap = self._bbox_overlap_ratio(room, other)

                if center_d < self.duplicate_center_tolerance and area_ratio > 0.72:
                    duplicate = True
                    break

                if same_label and bbox_overlap > 0.55:
                    duplicate = True
                    break

                if bbox_overlap > 0.86:
                    duplicate = True
                    break

            if not duplicate:
                kept.append(room)

        return kept

    def _bbox_overlap_ratio(self, a: RoomModel, b: RoomModel) -> float:
        ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.width, a.y + a.height
        bx1, by1, bx2, by2 = b.x, b.y, b.x + b.width, b.y + b.height

        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)

        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0

        inter = (ix2 - ix1) * (iy2 - iy1)
        smaller = min(a.area, b.area)

        return inter / max(smaller, 1e-9)

    def _attach_room_neighbors(self, rooms: List[RoomModel]) -> List[RoomModel]:
        for room in rooms:
            room.neighbors = []

        for i in range(len(rooms)):
            a = rooms[i]

            for j in range(i + 1, len(rooms)):
                b = rooms[j]
                weight, ctype = self._room_adjacency(a, b)

                if weight > 0:
                    a.neighbors.append(
                        RoomNeighbor(
                            room_id=b.id,
                            shared_edge_weight=round(weight, 3),
                            connection_type=ctype,
                        )
                    )
                    b.neighbors.append(
                        RoomNeighbor(
                            room_id=a.id,
                            shared_edge_weight=round(weight, 3),
                            connection_type=ctype,
                        )
                    )

        return rooms

    def _room_adjacency(self, a: RoomModel, b: RoomModel) -> Tuple[float, str]:
        ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.width, a.y + a.height
        bx1, by1, bx2, by2 = b.x, b.y, b.x + b.width, b.y + b.height

        x_overlap = max(0.0, min(ax2, bx2) - max(ax1, bx1))
        y_overlap = max(0.0, min(ay2, by2) - max(ay1, by1))

        horizontal_touch = min(abs(ay2 - by1), abs(by2 - ay1))
        vertical_touch = min(abs(ax2 - bx1), abs(bx2 - ax1))

        if horizontal_touch <= 0.35 and x_overlap > 0.35:
            return x_overlap, "wall_adjacent"

        if vertical_touch <= 0.35 and y_overlap > 0.35:
            return y_overlap, "wall_adjacent"

        center_d = math.hypot(a.center_x - b.center_x, a.center_y - b.center_y)

        if center_d <= 2.2:
            return max(0.1, 2.2 - center_d), "nearby"

        return 0.0, "unknown"

    def _sort_and_reindex_rooms(self, rooms: List[RoomModel]) -> List[RoomModel]:
        sorted_rooms = sorted(rooms, key=lambda r: (str(r.floor), -r.y, r.x, r.area))
        old_to_new: Dict[int, int] = {}

        for new_id, room in enumerate(sorted_rooms, start=1):
            old_to_new[room.id] = new_id
            room.id = new_id

        for room in sorted_rooms:
            updated_neighbors = []

            for n in room.neighbors:
                if n.room_id in old_to_new:
                    updated_neighbors.append(
                        RoomNeighbor(
                            room_id=old_to_new[n.room_id],
                            shared_edge_weight=n.shared_edge_weight,
                            connection_type=n.connection_type,
                        )
                    )

            room.neighbors = updated_neighbors

        return sorted_rooms

    def _build_floor_models(self, rooms: List[RoomModel]) -> List[FloorModel]:
        if not rooms:
            return []

        by_floor: Dict[str, List[RoomModel]] = {}

        for room in rooms:
            floor = room.floor or "ground"
            if floor == "unknown":
                floor = "ground"
                room.floor = "ground"
            by_floor.setdefault(floor, []).append(room)

        floors: List[FloorModel] = []

        for idx, (floor_name, floor_rooms) in enumerate(sorted(by_floor.items()), start=1):
            min_x = min(r.x for r in floor_rooms)
            min_y = min(r.y for r in floor_rooms)
            max_x = max(r.x + r.width for r in floor_rooms)
            max_y = max(r.y + r.height for r in floor_rooms)

            floors.append(
                FloorModel(
                    id=idx,
                    name=str(floor_name).replace("_", " ").title(),
                    floor=floor_name,
                    min_x=float(min_x),
                    min_y=float(min_y),
                    max_x=float(max_x),
                    max_y=float(max_y),
                    width=float(max_x - min_x),
                    height=float(max_y - min_y),
                    rooms=[r.id for r in floor_rooms],
                )
            )

        return floors

    def _detect_possible_door_gaps(self, rooms: List[RoomModel]) -> List[Any]:
        gaps: List[Any] = []
        gid = 1

        corridors = [r for r in rooms if r.room_type == "corridor"]

        for corridor in corridors:
            for n in corridor.neighbors:
                other = next((r for r in rooms if r.id == n.room_id), None)

                if other is None:
                    continue

                x = (corridor.center_x + other.center_x) / 2.0
                y = (corridor.center_y + other.center_y) / 2.0

                gaps.append(
                    DoorGap(
                        id=gid,
                        x=float(x),
                        y=float(y),
                        width=0.9,
                        height=2.1,
                        orientation="unknown",
                        confidence=0.42,
                    )
                )
                gid += 1

        return gaps

    def _best_label_for_polygon(self, labels: List[TextLabel], polygon: List[Point2D]) -> Optional[TextLabel]:
        if not labels:
            return None

        cx, cy = self._polygon_centroid(polygon)
        best: Optional[TextLabel] = None
        best_score = -1.0

        for label in labels:
            if not self._point_in_polygon(label.x, label.y, polygon):
                continue

            d = math.hypot(label.x - cx, label.y - cy)
            score = 1.0 / (1.0 + d)

            if self._looks_like_room_label(label.text):
                score += 0.15

            if score > best_score:
                best = label
                best_score = score

        return best

    def _infer_room_type(
        self,
        text: str,
        area: float,
        width: float,
        height: float,
        polygon: List[Point2D],
    ) -> str:
        t = self._normalize_text_for_matching(text)
        aspect = max(width, height) / max(min(width, height), 1e-9) if width > 0 and height > 0 else 1.0
        compactness = self._compactness(polygon) if polygon else 0.7

        if any(k in t for k in ["bath", "bathroom", "toilet", "wc", "w c", "lav", "shower", "حمام"]):
            return "bathroom"

        if any(k in t for k in ["corridor", "corr", "hallway", "hall", "passage", "ممر"]):
            return "corridor"

        if any(k in t for k in ["store", "storage", "stor", "مخزن"]):
            return "service"

        if any(k in t for k in ["service", "utility", "mechanical", "electrical", "elec", "janitor"]):
            return "service"

        if any(k in t for k in ["server", "rack", "data", "network", "it room", "control"]):
            return "server_room"

        if any(k in t for k in ["meeting", "conference", "class", "lecture", "training", "call center"]):
            return "meeting"

        if any(k in t for k in ["reception", "waiting", "lobby", "entrance"]):
            return "reception"

        if any(k in t for k in ["office", "offices", "staff", "admin", "manager", "doctor", "dr", "work", "room"]):
            return "office"

        if any(k in t for k in ["kitchen", "pantry"]):
            return "kitchen"

        if aspect >= self.corridor_min_aspect and area >= self.corridor_min_area and compactness < 0.78:
            return "corridor"

        if area <= 5.0 and aspect <= 2.2:
            return "service"

        if area >= 75.0:
            return "open_area"

        return "office"

    def _infer_zone(self, text: str, room_type: str) -> str:
        t = self._normalize_text_for_matching(text)

        if room_type in ["server_room"]:
            return "management"

        if any(k in t for k in ["admin", "manager", "management", "control", "server"]):
            return "management"

        if any(k in t for k in ["guest", "visitor", "reception", "lobby", "waiting"]):
            return "guest"

        if room_type in ["bathroom", "service", "kitchen"]:
            return "service"

        return "staff"

    def _estimate_expected_clients(self, room_type: str, area: float) -> int:
        if room_type == "bathroom":
            return 0
        if room_type == "corridor":
            return max(1, int(round(area / 20.0)))
        if room_type == "server_room":
            return max(1, int(round(area / 25.0)))
        if room_type == "meeting":
            return max(4, int(round(area / 2.8)))
        if room_type == "reception":
            return max(3, int(round(area / 4.5)))
        if room_type == "open_area":
            return max(8, int(round(area / 4.0)))
        if room_type in ["service", "kitchen"]:
            return max(0, int(round(area / 18.0)))
        return max(1, int(round(area / 7.0)))

    def _traffic_profile(self, room_type: str, text: str) -> str:
        if room_type in ["server_room"]:
            return "critical"
        if room_type in ["meeting", "open_area", "reception"]:
            return "high"
        if room_type in ["corridor", "bathroom", "service"]:
            return "low"
        return "medium"

    def _priority_weight(self, room_type: str, zone: str) -> float:
        base = {
            "server_room": 2.00,
            "meeting": 1.45,
            "open_area": 1.40,
            "reception": 1.30,
            "office": 1.20,
            "corridor": 1.10,
            "kitchen": 0.85,
            "service": 0.65,
            "bathroom": 0.25,
        }.get(room_type, 1.0)

        if zone == "management":
            base += 0.20
        elif zone == "guest":
            base -= 0.05
        elif zone == "service":
            base -= 0.10

        return round(max(0.15, base), 2)

    def _fallback_room_name(self, room_type: str, rid: int) -> str:
        names = {
            "bathroom": "Bathroom",
            "corridor": "Corridor",
            "service": "Service Room",
            "server_room": "Server Room",
            "meeting": "Meeting Room",
            "reception": "Reception",
            "open_area": "Open Area",
            "office": "Room",
            "kitchen": "Kitchen",
        }
        return f"{names.get(room_type, 'Room')} {rid}"

    def _estimate_extraction_confidence(
        self,
        raw_segments: List[_RawSegment],
        final_segments: List[_RawSegment],
        rooms: List[RoomModel],
        labels: List[TextLabel],
    ) -> float:
        if not raw_segments and not labels:
            return 0.0

        score = 35.0

        if final_segments:
            score += min(15.0, len(final_segments) * 0.12)

        if rooms:
            score += min(30.0, len(rooms) * 2.4)

        if labels:
            matched_labels = 0
            for label in labels:
                if any(self._point_in_polygon(label.x, label.y, r.polygon) for r in rooms):
                    matched_labels += 1
            score += min(15.0, 15.0 * matched_labels / max(len(labels), 1))

        if any(r.room_type == "corridor" for r in rooms):
            score += 3.0

        if any(r.room_type in ["bathroom", "service"] for r in rooms):
            score += 2.0

        if not rooms:
            score = min(score, 42.0)

        return round(max(0.0, min(99.0, score)), 2)

    def _choose_controller_room_id(self, rooms: List[RoomModel]) -> Optional[int]:
        if not rooms:
            return None

        preferred = ["server_room", "service", "office", "reception"]

        for room_type in preferred:
            candidates = [r for r in rooms if r.room_type == room_type]

            if candidates:
                candidates.sort(key=lambda r: (r.priority_weight, r.area), reverse=True)
                return candidates[0].id

        return rooms[0].id

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""

        s = str(text)
        s = s.replace("\\P", " ")
        s = s.replace("\\p", " ")
        s = s.replace("\\~", " ")

        s = re.sub(r"\{\\f[^;]*;", "", s)
        s = re.sub(r"\{\\[^;]*;", "", s)
        s = re.sub(r"\\[A-Za-z]+\d*\.?\d*", " ", s)
        s = re.sub(r"\\[{}]", " ", s)

        s = s.replace("{", " ").replace("}", " ")
        s = s.replace("|", " ")
        s = s.replace(";", " ")

        s = re.sub(r"\s+", " ", s).strip()

        if len(s) > 80:
            s = s[:80].strip()

        return s

    def _normalize_text_for_matching(self, text: str) -> str:
        s = self._clean_text(text).lower()
        s = s.replace("_", " ").replace("-", " ").replace("/", " ")
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _looks_like_room_label(self, text: str) -> bool:
        t = self._normalize_text_for_matching(text)

        if not t:
            return False

        keywords = [
            "office",
            "offices",
            "room",
            "meeting",
            "corridor",
            "hall",
            "bath",
            "bathroom",
            "toilet",
            "wc",
            "storage",
            "store",
            "service",
            "server",
            "reception",
            "lobby",
            "kitchen",
            "class",
            "admin",
            "call center",
            "مكتب",
            "غرفة",
            "حمام",
            "ممر",
            "مخزن",
        ]

        return any(k in t for k in keywords) or bool(re.match(r"^[a-zA-Z]*\s*\d{1,4}$", t))

    def _infer_floor_from_text(self, text: str) -> str:
        t = self._normalize_text_for_matching(text)

        if any(k in t for k in ["ground", "g f", "gf", "level 0"]):
            return "ground"
        if any(k in t for k in ["first", "1st", "level 1"]):
            return "first"
        if any(k in t for k in ["second", "2nd", "level 2"]):
            return "second"
        if any(k in t for k in ["third", "3rd", "level 3"]):
            return "third"

        return "unknown"

    def _is_rejected_layer(self, layer: str) -> bool:
        l = str(layer or "").lower().replace("_", "-")
        return any(k in l for k in self.reject_layer_keywords)

    def _is_wall_layer(self, layer: str) -> bool:
        if self._is_rejected_layer(layer):
            return False

        l = str(layer or "").lower().replace("_", "-")
        return any(k in l for k in self.wall_positive_keywords)

    def _is_structural_layer(self, layer: str) -> bool:
        l = str(layer or "").lower().replace("_", "-")
        return any(k in l for k in ["struct", "concrete", "column", "bearing", "external", "ext", "wall", "muro"])

    def _remove_symbol_like_clusters(self, segments: List[_RawSegment]) -> List[_RawSegment]:
        if not segments:
            return []

        lengths = [math.hypot(s.x2 - s.x1, s.y2 - s.y1) for s in segments]
        sorted_lengths = sorted(lengths)
        median = sorted_lengths[len(sorted_lengths) // 2]
        min_keep = max(self.min_segment_length, min(0.75, median * 0.20))

        kept: List[_RawSegment] = []

        for s, length in zip(segments, lengths):
            if length >= min_keep:
                kept.append(s)

        return kept

    def _point_key(self, x: float, y: float, grid: float) -> Tuple[int, int]:
        g = max(grid, 1e-9)
        return round(x / g), round(y / g)

    def _signed_polygon_area(self, polygon: List[Point2D]) -> float:
        if len(polygon) < 3:
            return 0.0

        area = 0.0

        for i, p in enumerate(polygon):
            q = polygon[(i + 1) % len(polygon)]
            area += p.x * q.y - q.x * p.y

        return area / 2.0

    def _polygon_perimeter(self, polygon: List[Point2D]) -> float:
        if len(polygon) < 2:
            return 0.0

        per = 0.0

        for i, p in enumerate(polygon):
            q = polygon[(i + 1) % len(polygon)]
            per += math.hypot(q.x - p.x, q.y - p.y)

        return per

    def _polygon_centroid(self, polygon: List[Point2D]) -> Tuple[float, float]:
        if len(polygon) < 3:
            if not polygon:
                return 0.0, 0.0
            return (
                sum(p.x for p in polygon) / len(polygon),
                sum(p.y for p in polygon) / len(polygon),
            )

        area = self._signed_polygon_area(polygon)

        if abs(area) < 1e-9:
            return (
                sum(p.x for p in polygon) / len(polygon),
                sum(p.y for p in polygon) / len(polygon),
            )

        cx = 0.0
        cy = 0.0

        for i, p in enumerate(polygon):
            q = polygon[(i + 1) % len(polygon)]
            cross = p.x * q.y - q.x * p.y
            cx += (p.x + q.x) * cross
            cy += (p.y + q.y) * cross

        cx /= 6.0 * area
        cy /= 6.0 * area

        return float(cx), float(cy)

    def _polygon_bbox(self, polygon: List[Point2D]) -> Tuple[float, float, float, float]:
        xs = [p.x for p in polygon]
        ys = [p.y for p in polygon]
        return min(xs), min(ys), max(xs), max(ys)

    def _point_in_polygon(self, x: float, y: float, polygon: List[Point2D]) -> bool:
        if len(polygon) < 3:
            return False

        inside = False
        j = len(polygon) - 1

        for i in range(len(polygon)):
            xi, yi = polygon[i].x, polygon[i].y
            xj, yj = polygon[j].x, polygon[j].y

            intersects = ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            )

            if intersects:
                inside = not inside

            j = i

        return inside

    def _dedupe_polygon_points(self, polygon: List[Point2D]) -> List[Point2D]:
        if not polygon:
            return []

        out: List[Point2D] = []

        for p in polygon:
            if not out:
                out.append(p)
                continue

            if math.hypot(p.x - out[-1].x, p.y - out[-1].y) > 1e-6:
                out.append(p)

        if len(out) > 2 and math.hypot(out[0].x - out[-1].x, out[0].y - out[-1].y) <= 1e-6:
            out.pop()

        return out

    def _compactness(self, polygon: List[Point2D]) -> float:
        area = abs(self._signed_polygon_area(polygon))
        perimeter = self._polygon_perimeter(polygon)

        if perimeter <= 1e-9:
            return 0.0

        return max(0.0, min(1.0, 4.0 * math.pi * area / (perimeter * perimeter)))

    def _write_debug_report(
        self,
        building: BuildingModel,
        raw_segments: List[_RawSegment],
        final_segments: List[_RawSegment],
        rooms: List[RoomModel],
        labels: List[TextLabel],
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            layer_counts: Dict[str, int] = {}
            for s in raw_segments:
                layer_counts[s.layer] = layer_counts.get(s.layer, 0) + 1

            report = {
                "file_name": building.file_name,
                "source_format": building.source_format,
                "raw_segments_count": len(raw_segments),
                "final_wall_segments_count": len(final_segments),
                "labels_count": len(labels),
                "rooms_count": len(rooms),
                "corridors_count": len([r for r in rooms if r.room_type == "corridor"]),
                "reception_count": len([r for r in rooms if r.room_type == "reception"]),
                "bathrooms_count": len([r for r in rooms if r.room_type == "bathroom"]),
                "service_count": len([r for r in rooms if r.room_type == "service"]),
                "extraction_confidence": building.extraction_confidence,
                "layers_seen": dict(sorted(layer_counts.items(), key=lambda x: -x[1])[:80]),
                "room_summary": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "type": r.room_type,
                        "area": r.area,
                        "x": r.x,
                        "y": r.y,
                        "width": r.width,
                        "height": r.height,
                        "source": r.source_layer,
                        "confidence": r.confidence,
                    }
                    for r in rooms
                ],
            }

            if extra:
                report.update(extra)

            self.debug_report_output.write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _write_latest_building(self, building: BuildingModel) -> None:
        data = self._model_to_dict(building)
        self.latest_building_output.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _model_to_dict(self, model):
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()


DXFExtractor = DXFRoomExtractor
StructFiDXFRoomExtractor = DXFRoomExtractor
CADRoomExtractor = DXFRoomExtractor