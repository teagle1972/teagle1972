from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Edge, Node


def save_flowchart(
    path: str | Path,
    nodes: list[Node],
    edges: list[Edge],
    display_settings: dict[str, Any] | None = None,
    view_state: dict[str, Any] | None = None,
) -> None:
    payload = {
        "version": 1,
        "nodes": [node.to_dict() for node in nodes],
        "edges": [edge.to_dict() for edge in edges],
    }
    if display_settings:
        payload["display_settings"] = dict(display_settings)
    if view_state:
        payload["view_state"] = dict(view_state)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_flowchart(path: str | Path) -> tuple[list[Node], list[Edge], dict[str, Any], dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = [Node.from_dict(item) for item in data.get("nodes", [])]
    edges = [Edge.from_dict(item) for item in data.get("edges", [])]
    raw_settings = data.get("display_settings", {})
    raw_view_state = data.get("view_state", {})
    display_settings = raw_settings if isinstance(raw_settings, dict) else {}
    view_state = raw_view_state if isinstance(raw_view_state, dict) else {}
    return nodes, edges, display_settings, view_state
