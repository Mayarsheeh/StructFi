import json
from pathlib import Path


class FloorplanParser:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def load(self):
        with open(self.file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_rooms(self):
        data = self.load()
        return data.get("rooms", [])

    def get_clients(self):
        data = self.load()
        return data.get("clients", [])