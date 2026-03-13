from __future__ import annotations


def handle_workflow_progress_event(app, payload: dict[str, object], ts_text: str) -> None:
    trigger = app._sanitize_inline_text(str(payload.get("trigger", ""))) or "-"
    reason = app._sanitize_inline_text(str(payload.get("reason", "")))
    from_node_id = app._sanitize_inline_text(str(payload.get("from_node_id", "")))
    jump_node_id = app._sanitize_inline_text(str(payload.get("jump_node_id", "")))
    cursor_node_id = app._sanitize_inline_text(str(payload.get("cursor_node_id", "")))
    route_node_id = app._sanitize_inline_text(str(payload.get("route_node_id", "")))
    content_node_id = app._sanitize_inline_text(str(payload.get("content_node_id", "")))
    matched_label = app._sanitize_inline_text(str(payload.get("matched_label", "")))
    intents_value = payload.get("intents", [])
    intents = [app._sanitize_inline_text(str(item)) for item in intents_value if str(item).strip()] if isinstance(intents_value, list) else []
    advanced = bool(payload.get("advanced", False))

    highlighted = False
    for candidate in (jump_node_id, content_node_id, cursor_node_id, route_node_id):
        if app._highlight_flow_monitor_node(candidate):
            highlighted = True
            break

    active_node = app._flow_active_node_id or content_node_id or cursor_node_id or route_node_id or "-"
    summary_parts = [
        f"当前节点={active_node}",
        f"trigger={trigger}",
        f"advanced={advanced}",
    ]
    if from_node_id:
        summary_parts.append(f"from={from_node_id}")
    if jump_node_id:
        summary_parts.append(f"jump={jump_node_id}")
    if matched_label:
        summary_parts.append(f"label={matched_label}")
    if intents:
        summary_parts.append(f"intents={','.join(intents)}")
    if reason:
        summary_parts.append(f"reason={reason}")
    if not highlighted and app.flow_monitor_canvas and app.flow_monitor_canvas.nodes:
        summary_parts.append("warning=目标节点未在图中找到")
    app.flow_summary_var.set(" | ".join(summary_parts))
    app._append_line(
        app.log_text,
        f"[{ts_text}] [FLOW_TRACK] {' | '.join(summary_parts)}",
    )
