from pathlib import Path
from datetime import datetime
import ezdxf


class DXFManager:
    def __init__(self):
        self.upload_dir = Path("data/uploads")
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save_dxf(self, file_bytes: bytes, original_filename: str):
        extension = Path(original_filename).suffix.lower()
        if extension != ".dxf":
            raise ValueError("Only DXF files are supported in this step")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"cad_floorplan_{timestamp}{extension}"
        file_path = self.upload_dir / safe_name

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        summary = self.parse_dxf(file_path)

        return {
            "file_name": safe_name,
            "file_path": str(file_path).replace("\\", "/"),
            "summary": summary,
        }

    def get_latest_dxf(self):
        files = sorted(
            list(self.upload_dir.glob("*.dxf")),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if not files:
            return None

        latest = files[0]
        summary = self.parse_dxf(latest)

        return {
            "file_name": latest.name,
            "file_path": str(latest).replace("\\", "/"),
            "summary": summary,
        }

    def parse_dxf(self, file_path: Path):
        doc = ezdxf.readfile(str(file_path))
        msp = doc.modelspace()

        entities = []
        counts = {
            "LINE": 0,
            "LWPOLYLINE": 0,
            "POLYLINE": 0,
            "TEXT": 0,
            "MTEXT": 0,
            "CIRCLE": 0,
            "ARC": 0,
            "OTHER": 0,
        }

        for entity in msp:
            dxftype = entity.dxftype()

            if dxftype in counts:
                counts[dxftype] += 1
            else:
                counts["OTHER"] += 1

            parsed = self._parse_entity(entity)
            if parsed is not None:
                entities.append(parsed)

        return {
            "entity_counts": counts,
            "total_entities": len(entities),
            "entities": entities[:1500]
        }

    def _parse_entity(self, entity):
        dxftype = entity.dxftype()

        try:
            if dxftype == "LINE":
                return {
                    "type": "LINE",
                    "layer": entity.dxf.layer,
                    "start": [float(entity.dxf.start.x), float(entity.dxf.start.y)],
                    "end": [float(entity.dxf.end.x), float(entity.dxf.end.y)],
                }

            if dxftype == "LWPOLYLINE":
                points = []
                for p in entity.get_points():
                    points.append([float(p[0]), float(p[1])])
                return {
                    "type": "LWPOLYLINE",
                    "layer": entity.dxf.layer,
                    "closed": bool(entity.closed),
                    "points": points,
                }

            if dxftype == "POLYLINE":
                points = []
                for v in entity.vertices:
                    points.append([float(v.dxf.location.x), float(v.dxf.location.y)])
                return {
                    "type": "POLYLINE",
                    "layer": entity.dxf.layer,
                    "closed": bool(entity.is_closed),
                    "points": points,
                }

            if dxftype == "TEXT":
                insert = entity.dxf.insert
                return {
                    "type": "TEXT",
                    "layer": entity.dxf.layer,
                    "text": entity.dxf.text,
                    "insert": [float(insert.x), float(insert.y)],
                }

            if dxftype == "MTEXT":
                insert = entity.dxf.insert
                return {
                    "type": "MTEXT",
                    "layer": entity.dxf.layer,
                    "text": entity.text,
                    "insert": [float(insert.x), float(insert.y)],
                }

            if dxftype == "CIRCLE":
                center = entity.dxf.center
                return {
                    "type": "CIRCLE",
                    "layer": entity.dxf.layer,
                    "center": [float(center.x), float(center.y)],
                    "radius": float(entity.dxf.radius),
                }

            if dxftype == "ARC":
                center = entity.dxf.center
                return {
                    "type": "ARC",
                    "layer": entity.dxf.layer,
                    "center": [float(center.x), float(center.y)],
                    "radius": float(entity.dxf.radius),
                    "start_angle": float(entity.dxf.start_angle),
                    "end_angle": float(entity.dxf.end_angle),
                }

            return {
                "type": dxftype,
                "layer": getattr(entity.dxf, "layer", "UNKNOWN"),
            }

        except Exception:
            return None