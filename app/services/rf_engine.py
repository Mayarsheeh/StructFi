from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class RFLinkResult:
    """Calculated RF values for one node-to-point link."""

    rssi_dbm: float
    snr_db: float
    path_loss_db: float
    wall_loss_db: float
    directional_gain_db: float
    antenna_gain_dbi: float
    interference_penalty_db: float
    noise_floor_dbm: float
    frequency_ghz: float
    wall_material: str
    wall_count: int
    path_loss_exponent: float
    quality_score: float

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, float):
                data[key] = round(value, 2)
        return data


class RFPropagationEngine:
    """
    Realistic RF propagation helper used by the StructFi digital twin.

    The model combines:
    - log-distance path loss
    - wall/material attenuation
    - directional antenna gain/penalty
    - noise floor and SNR
    - utilization/interference penalties for packet loss and throughput estimates

    It is still a simulation model, not a replacement for a field RF survey.
    """

    MATERIAL_ATTENUATION_DB: Dict[str, float] = {
        "drywall": 4.0,
        "glass": 4.0,
        "low_e_glass": 8.0,
        "wood": 5.0,
        "door_wood": 5.0,
        "partition": 6.0,
        "brick": 10.0,
        "concrete": 16.0,
        "reinforced_concrete": 18.0,
        "metal": 22.0,
        "unknown": 7.5,
    }

    def __init__(
        self,
        *,
        reference_rssi_dbm: float = -39.0,
        reference_tx_power_dbm: float = 15.0,
        noise_floor_dbm: float = -92.0,
        frequency_ghz: float = 5.0,
        default_material: str = "reinforced_concrete",
    ) -> None:
        self.reference_rssi_dbm = reference_rssi_dbm
        self.reference_tx_power_dbm = reference_tx_power_dbm
        self.noise_floor_dbm = noise_floor_dbm
        self.frequency_ghz = frequency_ghz
        self.default_material = default_material

    def assumptions(self) -> Dict[str, Any]:
        return {
            "model": "log-distance path loss + wall/material attenuation + directional antenna gain",
            "frequency_ghz": self.frequency_ghz,
            "noise_floor_dbm": self.noise_floor_dbm,
            "reference_rssi_dbm_at_1m": self.reference_rssi_dbm,
            "reference_tx_power_dbm": self.reference_tx_power_dbm,
            "default_wall_material": self.default_material,
            "default_wall_attenuation_db": self.material_loss_db(self.default_material),
            "material_attenuation_db": dict(self.MATERIAL_ATTENUATION_DB),
            "note": "Simulation model for planning and digital-twin validation before field deployment.",
        }

    def material_loss_db(self, material: Optional[str]) -> float:
        key = str(material or self.default_material).lower().strip().replace(" ", "_").replace("-", "_")
        return float(self.MATERIAL_ATTENUATION_DB.get(key, self.MATERIAL_ATTENUATION_DB["unknown"]))

    def infer_wall_material(self, wall: Optional[Dict[str, Any]]) -> str:
        if not isinstance(wall, dict):
            return self.default_material

        for key in ["material", "wall_material", "type", "layer"]:
            value = str(wall.get(key, "") or "").lower()
            if not value:
                continue
            if "low" in value and "glass" in value:
                return "low_e_glass"
            if "glass" in value or "window" in value:
                return "glass"
            if "door" in value or "wood" in value:
                return "door_wood"
            if "brick" in value:
                return "brick"
            if "reinforced" in value or "concrete" in value or "struct" in value or "wall" in value:
                return "reinforced_concrete"
            if "metal" in value or "steel" in value:
                return "metal"
            if "dry" in value or "gypsum" in value or "partition" in value:
                return "drywall"
        return self.default_material

    def wall_loss_db(
        self,
        *,
        wall_count: int = 0,
        wall_segments: Optional[Iterable[Dict[str, Any]]] = None,
        default_material: Optional[str] = None,
    ) -> float:
        if wall_segments is not None:
            total = 0.0
            count = 0
            for wall in wall_segments:
                count += 1
                if isinstance(wall, dict) and wall.get("attenuation_db") is not None:
                    try:
                        total += float(wall.get("attenuation_db"))
                        continue
                    except Exception:
                        pass
                material = self.infer_wall_material(wall)
                total += self.material_loss_db(material)
            if count > 0:
                return total

        material = default_material or self.default_material
        return max(0, int(wall_count)) * self.material_loss_db(material)

    def path_loss_exponent(self, room_type: str, wall_count: int = 0) -> float:
        room_type = str(room_type or "unknown").lower()
        if room_type == "corridor":
            return 1.85
        if room_type in ["open_area", "reception", "meeting"]:
            return 2.08 if wall_count <= 0 else 2.45
        if wall_count > 0:
            return 2.75
        return 2.15

    def path_loss_db(self, distance_m: float, room_type: str, wall_count: int = 0) -> float:
        distance_m = max(float(distance_m), 0.5)
        exponent = self.path_loss_exponent(room_type, wall_count)
        return 10.0 * exponent * math.log10(distance_m)

    def directional_gain_db(
        self,
        *,
        node_x: float,
        node_y: float,
        target_x: float,
        target_y: float,
        beam_direction_deg: float,
        beamwidth_deg: float,
        antenna_gain_dbi: float = 8.0,
    ) -> float:
        angle = math.degrees(math.atan2(target_y - node_y, target_x - node_x))
        delta = abs((angle - beam_direction_deg + 180.0) % 360.0 - 180.0)
        half = max(float(beamwidth_deg), 1.0) / 2.0

        # The hardware gain is normalized around 8 dBi so typical GP1 nodes
        # remain close to the old output while higher-gain profiles improve coverage.
        hardware_gain_adjustment = max(-2.0, min(3.0, float(antenna_gain_dbi) - 8.0))

        if delta <= half:
            return 4.5 + hardware_gain_adjustment
        if delta <= max(float(beamwidth_deg), half + 1.0):
            return 0.0 + hardware_gain_adjustment * 0.45
        return -7.5 + hardware_gain_adjustment * 0.25

    def estimate_link(
        self,
        *,
        node_x: float,
        node_y: float,
        target_x: float,
        target_y: float,
        tx_power_dbm: float,
        beam_direction_deg: float,
        beamwidth_deg: float,
        room_type: str,
        wall_count: int = 0,
        wall_segments: Optional[Iterable[Dict[str, Any]]] = None,
        antenna_gain_dbi: float = 8.0,
        interference_penalty_db: float = 0.0,
        default_material: Optional[str] = None,
    ) -> RFLinkResult:
        distance_m = max(0.5, math.hypot(float(target_x) - float(node_x), float(target_y) - float(node_y)))
        wall_segments_list = list(wall_segments or [])
        effective_wall_count = len(wall_segments_list) if wall_segments_list else int(wall_count or 0)
        material = self.infer_wall_material(wall_segments_list[0]) if wall_segments_list else (default_material or self.default_material)
        path_loss = self.path_loss_db(distance_m, room_type, effective_wall_count)
        wall_loss = self.wall_loss_db(
            wall_count=effective_wall_count,
            wall_segments=wall_segments_list if wall_segments_list else None,
            default_material=material,
        )
        directional_gain = self.directional_gain_db(
            node_x=node_x,
            node_y=node_y,
            target_x=target_x,
            target_y=target_y,
            beam_direction_deg=beam_direction_deg,
            beamwidth_deg=beamwidth_deg,
            antenna_gain_dbi=antenna_gain_dbi,
        )
        rssi = (
            self.reference_rssi_dbm
            + (float(tx_power_dbm) - self.reference_tx_power_dbm)
            + directional_gain
            - path_loss
            - wall_loss
            - float(interference_penalty_db or 0.0)
        )
        rssi = max(-95.0, min(-35.0, rssi))
        snr = rssi - self.noise_floor_dbm
        quality = max(0.0, min(1.0, (rssi + 82.0) / 34.0)) ** 1.08

        return RFLinkResult(
            rssi_dbm=rssi,
            snr_db=snr,
            path_loss_db=path_loss,
            wall_loss_db=wall_loss,
            directional_gain_db=directional_gain,
            antenna_gain_dbi=float(antenna_gain_dbi),
            interference_penalty_db=float(interference_penalty_db or 0.0),
            noise_floor_dbm=self.noise_floor_dbm,
            frequency_ghz=self.frequency_ghz,
            wall_material=material,
            wall_count=effective_wall_count,
            path_loss_exponent=self.path_loss_exponent(room_type, effective_wall_count),
            quality_score=quality,
        )

    def estimate_packet_loss_percent(self, *, rssi_dbm: float, snr_db: float, utilization_percent: float, interference_score: float = 0.0) -> float:
        loss = 0.35
        if rssi_dbm < -72:
            loss += (-72.0 - rssi_dbm) * 0.34
        if snr_db < 20:
            loss += (20.0 - snr_db) * 0.18
        if utilization_percent > 80:
            loss += (utilization_percent - 80.0) * 0.045
        loss += float(interference_score or 0.0) * 0.08
        return max(0.1, min(12.0, loss))

    def estimate_throughput_mbps(
        self,
        *,
        rssi_dbm: float,
        snr_db: float,
        utilization_percent: float,
        channel_width_mhz: int = 40,
        base_capacity_mbps: float = 110.0,
    ) -> float:
        quality = 1.0
        if rssi_dbm < -60:
            quality -= min(0.45, (-60.0 - rssi_dbm) / 45.0)
        if snr_db < 30:
            quality -= min(0.35, (30.0 - snr_db) / 45.0)
        if utilization_percent > 65:
            quality -= min(0.35, (utilization_percent - 65.0) / 100.0)
        width_factor = max(0.45, min(1.15, int(channel_width_mhz or 40) / 40.0))
        return max(8.0, min(160.0, base_capacity_mbps * quality * width_factor))
