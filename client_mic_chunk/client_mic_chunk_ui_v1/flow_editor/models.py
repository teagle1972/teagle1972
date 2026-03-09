from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeType(str, Enum):
    START_END = "start_end"
    PROCESS = "process"
    DECISION = "decision"
    INPUT_OUTPUT = "input_output"

    @property
    def display_name(self) -> str:
        if self is NodeType.START_END:
            return "开始/结束"
        if self is NodeType.PROCESS:
            return "处理"
        if self is NodeType.DECISION:
            return "判断"
        return "输入/输出"


DEFAULT_LABELS = {
    NodeType.START_END: "开始/结束",
    NodeType.PROCESS: "处理步骤",
    NodeType.DECISION: "条件",
    NodeType.INPUT_OUTPUT: "输入/输出",
}

DEFAULT_SIZE = {
    NodeType.START_END: (130.0, 70.0),
    NodeType.PROCESS: (140.0, 80.0),
    NodeType.DECISION: (140.0, 90.0),
    NodeType.INPUT_OUTPUT: (150.0, 80.0),
}


@dataclass
class Node:
    id: str
    node_type: NodeType
    x: float
    y: float
    width: float
    height: float
    text: str
    task_notes: str = ""
    shape_item_id: int | None = field(default=None, repr=False)
    text_item_id: int | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.node_type.value,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "text": self.text,
            "task_notes": self.task_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Node":
        node_type = NodeType(data["type"])
        return cls(
            id=data["id"],
            node_type=node_type,
            x=float(data["x"]),
            y=float(data["y"]),
            width=float(data.get("width", DEFAULT_SIZE[node_type][0])),
            height=float(data.get("height", DEFAULT_SIZE[node_type][1])),
            text=str(data.get("text", DEFAULT_LABELS[node_type])),
            task_notes=str(data.get("task_notes", "")),
        )


@dataclass
class Edge:
    id: str
    source_id: str
    target_id: str
    text: str = ""
    route_points: list[tuple[float, float]] = field(default_factory=list)
    source_anchor: str | None = None
    target_anchor: str | None = None
    line_item_id: int | None = field(default=None, repr=False)
    text_item_id: int | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "text": self.text,
            "route_points": [[x, y] for x, y in self.route_points],
            "source_anchor": self.source_anchor,
            "target_anchor": self.target_anchor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Edge":
        raw_points = data.get("route_points", [])
        route_points: list[tuple[float, float]] = []
        if isinstance(raw_points, list):
            for item in raw_points:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    route_points.append((float(item[0]), float(item[1])))
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            text=str(data.get("text", "")),
            route_points=route_points,
            source_anchor=str(data.get("source_anchor", "")).strip() or None,
            target_anchor=str(data.get("target_anchor", "")).strip() or None,
        )
