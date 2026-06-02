from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class WallMaterialManager:
    """
    Stores and applies RF wall/material assumptions for the StructFi digital twin.

    The CAD/DXF extractor usually gives geometry, but not reliable material data.
    This manager lets the simulator run realistic building scenarios such as
    reinforced-concrete buildings, glass-partition offices, glass facades, and
    light drywall interiors.
    """

    MATERIAL_LIBRARY: Dict[str, Dict[str, Any]] = {
        "drywall": {
            "label": "Drywall / gypsum partition",
            "attenuation_db": 4.0,
            "typical_use": "Light interior office partitions",
        },
        "glass": {
            "label": "Glass partition / window",
            "attenuation_db": 4.0,
            "typical_use": "Interior glass walls, windows, and transparent office partitions",
        },
        "low_e_glass": {
            "label": "Low-E / coated glass",
            "attenuation_db": 8.0,
            "typical_use": "Modern coated glass facades with stronger RF attenuation",
        },
        "wood": {
            "label": "Wood panel",
            "attenuation_db": 5.0,
            "typical_use": "Wooden partitions and light panels",
        },
        "door_wood": {
            "label": "Wooden door",
            "attenuation_db": 5.0,
            "typical_use": "Interior wooden doors",
        },
        "partition": {
            "label": "Generic light partition",
            "attenuation_db": 6.0,
            "typical_use": "Unspecified light interior partitions",
        },
        "brick": {
            "label": "Brick wall",
            "attenuation_db": 10.0,
            "typical_use": "Masonry room separation",
        },
        "concrete": {
            "label": "Concrete wall",
            "attenuation_db": 16.0,
            "typical_use": "Concrete interior or structural walls",
        },
        "reinforced_concrete": {
            "label": "Reinforced concrete wall",
            "attenuation_db": 18.0,
            "typical_use": "Heavy structural walls and concrete cores",
        },
        "metal": {
            "label": "Metal / steel barrier",
            "attenuation_db": 22.0,
            "typical_use": "Metal doors, steel panels, service shafts, or equipment rooms",
        },
        "unknown": {
            "label": "Unknown / default CAD wall",
            "attenuation_db": 7.5,
            "typical_use": "Fallback value when CAD material is unknown",
        },
    }

    SCENARIO_PROFILES: Dict[str, Dict[str, Any]] = {
        "reinforced_concrete_core": {
            "name": "Reinforced Concrete Core",
            "description": "Conservative scenario for buildings dominated by concrete walls and structural cores.",
            "default_material": "reinforced_concrete",
            "interior_wall_material": "reinforced_concrete",
            "facade_material": "concrete",
            "door_material": "door_wood",
            "window_material": "glass",
        },
        "mixed_office": {
            "name": "Mixed Office Building",
            "description": "Balanced office scenario: concrete structural walls, lighter room partitions, and normal glass openings.",
            "default_material": "partition",
            "interior_wall_material": "partition",
            "facade_material": "concrete",
            "door_material": "door_wood",
            "window_material": "glass",
        },
        "glass_partitions": {
            "name": "Glass Interior Partitions",
            "description": "Modern office scenario with many glass room dividers and relatively low interior RF loss.",
            "default_material": "glass",
            "interior_wall_material": "glass",
            "facade_material": "low_e_glass",
            "door_material": "door_wood",
            "window_material": "glass",
        },
        "glass_facade": {
            "name": "Glass Facade Building",
            "description": "Scenario for buildings with glass external facades and mixed interior partitions.",
            "default_material": "partition",
            "interior_wall_material": "partition",
            "facade_material": "low_e_glass",
            "door_material": "door_wood",
            "window_material": "glass",
        },
        "light_drywall": {
            "name": "Light Drywall Interiors",
            "description": "Low-attenuation interior fit-out, useful for open offices and temporary partitions.",
            "default_material": "drywall",
            "interior_wall_material": "drywall",
            "facade_material": "concrete",
            "door_material": "door_wood",
            "window_material": "glass",
        },
        "brick_masonry": {
            "name": "Brick Masonry Building",
            "description": "Medium-heavy masonry scenario with brick interior walls.",
            "default_material": "brick",
            "interior_wall_material": "brick",
            "facade_material": "brick",
            "door_material": "door_wood",
            "window_material": "glass",
        },
    }

    DEFAULT_PROFILE_KEY = "reinforced_concrete_core"

    def __init__(self, parsed_dir: str | Path = "data/parsed") -> None:
        self.parsed_dir = Path(parsed_dir)
        self.parsed_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.parsed_dir / "wall_material_config.json"
        self.latest_building_path = self.parsed_dir / "latest_building.json"

    def material_attenuation_db(self, material: Optional[str]) -> float:
        key = self.normalize_material(material)
        return float(self.MATERIAL_LIBRARY.get(key, self.MATERIAL_LIBRARY["unknown"])["attenuation_db"])

    def normalize_material(self, material: Optional[str]) -> str:
        key = str(material or "unknown").lower().strip().replace(" ", "_").replace("-", "_")
        aliases = {
            "gypsum": "drywall",
            "dry_wall": "drywall",
            "window": "glass",
            "facade_glass": "low_e_glass",
            "rc": "reinforced_concrete",
            "reinforced": "reinforced_concrete",
            "steel": "metal",
            "wooden_door": "door_wood",
        }
        key = aliases.get(key, key)
        return key if key in self.MATERIAL_LIBRARY else "unknown"

    def default_config(self) -> Dict[str, Any]:
        profile = dict(self.SCENARIO_PROFILES[self.DEFAULT_PROFILE_KEY])
        profile["profile_key"] = self.DEFAULT_PROFILE_KEY
        profile["custom_overrides"] = {}
        return profile

    def current_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return self.default_config()
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return self.default_config()
        return self._normalize_config(data)

    def save_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        config = self._normalize_config(payload)
        self.config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        self.apply_to_latest_building(config)
        return config

    def profiles_payload(self) -> Dict[str, Any]:
        return {
            "materials": self.MATERIAL_LIBRARY,
            "profiles": self.SCENARIO_PROFILES,
            "current_config": self.current_config(),
        }

    def apply_to_latest_building(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        config = self._normalize_config(config or self.current_config())
        if not self.latest_building_path.exists():
            return {"applied": False, "reason": "latest_building.json not found", "config": config}

        try:
            building = json.loads(self.latest_building_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"applied": False, "reason": str(exc), "config": config}

        walls = list(building.get("walls", []) or [])
        applied_walls = self.apply_to_walls(walls, config)
        building["walls"] = applied_walls
        building["wall_material_config"] = config
        building["wall_material_summary"] = self.summarize_walls(applied_walls)
        self.latest_building_path.write_text(json.dumps(building, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "applied": True,
            "config": config,
            "summary": building["wall_material_summary"],
            "wall_count": len(applied_walls),
        }

    def apply_to_walls(self, walls: Iterable[Dict[str, Any]], config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        config = self._normalize_config(config or self.current_config())
        applied: List[Dict[str, Any]] = []
        for wall in walls or []:
            if not isinstance(wall, dict):
                continue
            enriched = dict(wall)
            material = self.classify_wall_material(enriched, config)
            enriched["material"] = material
            enriched["wall_material"] = material
            enriched["attenuation_db"] = self.material_attenuation_db(material)
            enriched["material_label"] = self.MATERIAL_LIBRARY[material]["label"]
            enriched["material_profile"] = config.get("profile_key", self.DEFAULT_PROFILE_KEY)
            applied.append(enriched)
        return applied

    def summarize_walls(self, walls: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        attenuation_total = 0.0
        total = 0
        for wall in walls or []:
            if not isinstance(wall, dict):
                continue
            material = self.normalize_material(wall.get("material") or wall.get("wall_material"))
            counts[material] = counts.get(material, 0) + 1
            attenuation_total += float(wall.get("attenuation_db", self.material_attenuation_db(material)) or 0.0)
            total += 1
        dominant = max(counts, key=counts.get) if counts else "unknown"
        return {
            "wall_count": total,
            "material_counts": counts,
            "dominant_material": dominant,
            "avg_attenuation_db": round(attenuation_total / max(total, 1), 2),
            "material_library": self.MATERIAL_LIBRARY,
        }

    def classify_wall_material(self, wall: Dict[str, Any], config: Dict[str, Any]) -> str:
        # Respect true CAD/user-provided material only when it was not produced by
        # a previous StructFi material-scenario pass. This allows switching scenarios
        # repeatedly without the old enriched material locking the wall forever.
        explicit = wall.get("material") or wall.get("wall_material")
        if explicit and not wall.get("material_profile"):
            normalized = self.normalize_material(str(explicit))
            if normalized != "unknown":
                return normalized

        layer_text = " ".join(
            str(wall.get(key, "") or "")
            for key in ["layer", "type", "name", "category", "source_layer"]
        ).lower()

        if any(token in layer_text for token in ["window", "glass", "glazing", "curtain"]):
            return self.normalize_material(config.get("window_material"))
        if any(token in layer_text for token in ["door", "wood"]):
            return self.normalize_material(config.get("door_material"))
        if any(token in layer_text for token in ["facade", "external", "exterior", "perimeter", "curtain"]):
            return self.normalize_material(config.get("facade_material"))
        if any(token in layer_text for token in ["struct", "column", "core", "rc", "concrete"]):
            return self.normalize_material(config.get("structural_wall_material", config.get("default_material")))
        if any(token in layer_text for token in ["partition", "interior", "wall"]):
            return self.normalize_material(config.get("interior_wall_material"))

        return self.normalize_material(config.get("default_material"))

    def _normalize_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}

        profile_key = str(payload.get("profile") or payload.get("profile_key") or self.DEFAULT_PROFILE_KEY)
        base = dict(self.SCENARIO_PROFILES.get(profile_key, self.SCENARIO_PROFILES[self.DEFAULT_PROFILE_KEY]))
        base["profile_key"] = profile_key if profile_key in self.SCENARIO_PROFILES else self.DEFAULT_PROFILE_KEY

        for key in [
            "default_material",
            "interior_wall_material",
            "facade_material",
            "door_material",
            "window_material",
            "structural_wall_material",
        ]:
            if payload.get(key):
                base[key] = self.normalize_material(payload.get(key))
            elif key not in base:
                base[key] = self.normalize_material(base.get("default_material"))
            else:
                base[key] = self.normalize_material(base.get(key))

        base["custom_overrides"] = payload.get("custom_overrides", {}) if isinstance(payload.get("custom_overrides"), dict) else {}
        return base
