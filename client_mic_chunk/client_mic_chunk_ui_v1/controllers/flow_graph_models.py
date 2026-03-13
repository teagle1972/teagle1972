from __future__ import annotations

try:
    from ..flow_editor.models import Edge as FlowEdge, Node as FlowNode, NodeType  # type: ignore[attr-defined]
except Exception:
    from flow_editor.models import Edge as FlowEdge, Node as FlowNode, NodeType


def to_float(value: object, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def coerce_node_type(value: object) -> str:
    raw = str(value or "").strip().lower()
    valid_types = {item.value for item in NodeType}
    if raw in valid_types:
        return raw
    return NodeType.PROCESS.value


def build_flow_graph_models(
    payload: dict[str, object],
) -> tuple[list[FlowNode], list[FlowEdge], dict[str, object], dict[str, object]]:
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError("workflow file must contain nodes(list) and edges(list)")

    nodes: list[FlowNode] = []
    node_ids: set[str] = set()
    for idx, item in enumerate(raw_nodes):
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("id") or "").strip()
        if (not node_id) or (node_id in node_ids):
            continue
        node_type = coerce_node_type(item.get("type"))
        fallback_x = 160.0 + float((idx % 4) * 220)
        fallback_y = 120.0 + float((idx // 4) * 150)
        node_payload = {
            "id": node_id,
            "type": node_type,
            "x": to_float(item.get("x"), fallback_x),
            "y": to_float(item.get("y"), fallback_y),
            "width": to_float(item.get("width"), 140.0),
            "height": to_float(item.get("height"), 84.0),
            "text": str(item.get("text") or "").strip() or node_id,
            "task_notes": str(item.get("task_notes") or ""),
        }
        try:
            node = FlowNode.from_dict(node_payload)
        except Exception:
            continue
        nodes.append(node)
        node_ids.add(node_id)

    if not nodes:
        raise ValueError("流程文件缺少有效节点。")

    edges: list[FlowEdge] = []
    edge_ids: set[str] = set()
    for idx, item in enumerate(raw_edges):
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "").strip()
        target_id = str(item.get("target_id") or "").strip()
        if (source_id not in node_ids) or (target_id not in node_ids):
            continue
        base_edge_id = str(item.get("id") or "").strip() or f"edge_{idx + 1}"
        edge_id = base_edge_id
        duplicate_idx = 1
        while edge_id in edge_ids:
            duplicate_idx += 1
            edge_id = f"{base_edge_id}_{duplicate_idx}"
        edge_payload = {
            "id": edge_id,
            "source_id": source_id,
            "target_id": target_id,
            "text": str(item.get("text") or ""),
            "route_points": item.get("route_points", []),
            "source_anchor": item.get("source_anchor"),
            "target_anchor": item.get("target_anchor"),
        }
        try:
            edge = FlowEdge.from_dict(edge_payload)
        except Exception:
            continue
        edges.append(edge)
        edge_ids.add(edge_id)

    raw_display = payload.get("display_settings")
    raw_view = payload.get("view_state")
    display_settings = raw_display if isinstance(raw_display, dict) else {}
    view_state = raw_view if isinstance(raw_view, dict) else {}
    return nodes, edges, display_settings, view_state
