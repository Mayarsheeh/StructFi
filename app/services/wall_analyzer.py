from pathlib import Path
import math
import ezdxf


class WallAnalyzer:
    def __init__(self):
        self.upload_dir = Path("data/uploads")

    def get_latest_walls(self):
        files = sorted(
            list(self.upload_dir.glob("*.dxf")),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if not files:
            return []

        return self.extract_walls_from_file(files[0])

    def extract_walls_from_file(self, file_path: Path):
        doc = ezdxf.readfile(str(file_path))
        msp = doc.modelspace()

        walls = []

        for entity in msp:
            dxftype = entity.dxftype()
            layer = getattr(entity.dxf, "layer", "").lower()

            # نعطي أولوية للـ layers التي توحي أنها walls
            likely_wall_layer = any(token in layer for token in [
                "wall", "walls", "partition", "arch", "outline", "building"
            ])

            if dxftype == "LINE":
                start = entity.dxf.start
                end = entity.dxf.end
                length = self.distance(start.x, start.y, end.x, end.y)

                if likely_wall_layer or length > 2:
                    walls.append({
                        "type": "LINE",
                        "x1": float(start.x),
                        "y1": float(start.y),
                        "x2": float(end.x),
                        "y2": float(end.y),
                        "layer": entity.dxf.layer
                    })

            elif dxftype == "LWPOLYLINE":
                points = [[float(p[0]), float(p[1])] for p in entity.get_points()]
                if len(points) >= 2 and likely_wall_layer:
                    for i in range(len(points) - 1):
                        walls.append({
                            "type": "SEGMENT",
                            "x1": points[i][0],
                            "y1": points[i][1],
                            "x2": points[i + 1][0],
                            "y2": points[i + 1][1],
                            "layer": entity.dxf.layer
                        })
                    if entity.closed:
                        walls.append({
                            "type": "SEGMENT",
                            "x1": points[-1][0],
                            "y1": points[-1][1],
                            "x2": points[0][0],
                            "y2": points[0][1],
                            "layer": entity.dxf.layer
                        })

            elif dxftype == "POLYLINE":
                if likely_wall_layer:
                    pts = []
                    for v in entity.vertices:
                        pts.append([float(v.dxf.location.x), float(v.dxf.location.y)])
                    for i in range(len(pts) - 1):
                        walls.append({
                            "type": "SEGMENT",
                            "x1": pts[i][0],
                            "y1": pts[i][1],
                            "x2": pts[i + 1][0],
                            "y2": pts[i + 1][1],
                            "layer": entity.dxf.layer
                        })
                    if entity.is_closed and len(pts) > 2:
                        walls.append({
                            "type": "SEGMENT",
                            "x1": pts[-1][0],
                            "y1": pts[-1][1],
                            "x2": pts[0][0],
                            "y2": pts[0][1],
                            "layer": entity.dxf.layer
                        })

        return walls

    def count_intersections(self, x1, y1, x2, y2, walls):
        count = 0
        for wall in walls:
            if self.segments_intersect(
                x1, y1, x2, y2,
                wall["x1"], wall["y1"], wall["x2"], wall["y2"]
            ):
                count += 1
        return count

    def distance(self, x1, y1, x2, y2):
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

    def ccw(self, ax, ay, bx, by, cx, cy):
        return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)

    def segments_intersect(self, ax, ay, bx, by, cx, cy, dx, dy):
        return (
            self.ccw(ax, ay, cx, cy, dx, dy) != self.ccw(bx, by, cx, cy, dx, dy)
            and self.ccw(ax, ay, bx, by, cx, cy) != self.ccw(ax, ay, bx, by, dx, dy)
        )