from app.core.config import settings
from app.services.floorplan_parser import FloorplanParser


class PlacementPlanner:
    def __init__(self, floorplan_path="data/floorplan.json"):
        self.floorplan_path = floorplan_path
        self.parser = FloorplanParser(floorplan_path)

    def generate_candidate_points(self, room):
        x = room["x"]
        y = room["y"]
        w = room["width"]
        h = room["height"]

        offset = 0.5

        return [
            {"x": x + offset, "y": y + offset, "label": "top_left"},
            {"x": x + w - offset, "y": y + offset, "label": "top_right"},
            {"x": x + offset, "y": y + h - offset, "label": "bottom_left"},
            {"x": x + w - offset, "y": y + h - offset, "label": "bottom_right"}
        ]

    def score_point(self, point, room):
        score = 0

        score += 30

        room_area = room["width"] * room["height"]
        if room_area >= 20:
            score += 20

        if room["zone"] == "management":
            score += 15
        elif room["zone"] == "staff":
            score += 10
        elif room["zone"] == "guest":
            score += 5

        if point["label"] in ["top_right", "bottom_right"]:
            score += 5

        return score

    def suggest_nodes(self):
        rooms = self.parser.get_rooms()
        suggestions = []

        for room in rooms:
            candidates = self.generate_candidate_points(room)

            best_point = None
            best_score = -1

            for point in candidates:
                score = self.score_point(point, room)
                if score > best_score:
                    best_score = score
                    best_point = point

            suggestions.append({
                "id": room["id"],
                "name": f"Node-{room['id']}",
                "room_id": room["id"],
                "room_name": room["name"],
                "zone": room["zone"],
                "x": best_point["x"],
                "y": best_point["y"],
                "channel": settings.DEFAULT_CHANNELS_24GHZ[(room["id"] - 1) % 3],
                "tx_power": settings.DEFAULT_TX_POWER,
                "score": best_score,
                "selected_corner": best_point["label"]
            })

        return suggestions