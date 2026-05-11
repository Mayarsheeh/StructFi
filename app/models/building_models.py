from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


ZoneType = Literal[
    "management",
    "staff",
    "guest",
    "service",
    "unknown",
]

RoomType = Literal[
    "office",
    "meeting",
    "corridor",
    "lobby",
    "reception",
    "server_room",
    "bathroom",
    "bedroom",
    "kitchen",
    "garage",
    "terrace",
    "open_area",
    "service",
    "storage",
    "unknown",
]

FloorType = Literal[
    "ground",
    "first",
    "second",
    "third",
    "upper_block",
    "lower_block",
    "unknown",
]


class Point2D(BaseModel):
    x: float
    y: float


class BuildingBounds(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    width: float
    height: float


class WallSegment(BaseModel):
    id: int
    x1: float
    y1: float
    x2: float
    y2: float
    layer: str = "unknown"
    thickness_hint: float = 0.0
    is_structural: bool = False


class DoorGap(BaseModel):
    id: int
    x: float
    y: float
    width: float = 0.0
    height: float = 0.0
    orientation: Literal["horizontal", "vertical", "unknown"] = "unknown"
    connected_room_ids: List[int] = Field(default_factory=list)
    confidence: float = 0.0


# Compatibility alias.
# بعض ملفات المشروع القديمة تستورد DoorGap
# والنسخ الجديدة من extractor تستورد DoorOrGapModel
DoorOrGapModel = DoorGap


class TextLabel(BaseModel):
    id: int
    text: str
    x: float
    y: float
    floor: FloorType = "unknown"
    confidence: float = 0.0


class RoomNeighbor(BaseModel):
    room_id: int
    shared_edge_weight: float = 0.0
    connection_type: Literal[
        "wall_adjacent",
        "door_adjacent",
        "nearby",
        "shared_wall",
        "none",
        "unknown",
    ] = "unknown"


class RoomModel(BaseModel):
    id: int
    name: str
    floor: FloorType = "unknown"

    x: float
    y: float
    width: float
    height: float
    area: float

    center_x: float
    center_y: float

    polygon: List[Point2D] = Field(default_factory=list)

    room_type: RoomType = "unknown"
    zone: ZoneType = "unknown"

    expected_clients: int = 0
    traffic_profile: Literal["low", "medium", "high", "burst", "critical"] = "medium"
    priority_weight: float = 1.0

    label_text: Optional[str] = None
    source_layer: str = "unknown"
    confidence: float = 0.0

    neighbors: List[RoomNeighbor] = Field(default_factory=list)


class FloorModel(BaseModel):
    id: int
    name: str
    floor: FloorType
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    width: float
    height: float
    rooms: List[int] = Field(default_factory=list)


class BuildingModel(BaseModel):
    file_name: str
    source_format: Literal["DXF", "DWG", "UNKNOWN"] = "UNKNOWN"

    bounds: BuildingBounds
    floors: List[FloorModel] = Field(default_factory=list)
    walls: List[WallSegment] = Field(default_factory=list)
    doors_or_gaps: List[DoorGap] = Field(default_factory=list)
    labels: List[TextLabel] = Field(default_factory=list)
    rooms: List[RoomModel] = Field(default_factory=list)

    controller_zone_candidate_room_id: Optional[int] = None
    extraction_confidence: float = 0.0