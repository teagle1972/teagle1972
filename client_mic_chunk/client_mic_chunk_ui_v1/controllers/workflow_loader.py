from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox


def render_flow_monitor_graph(app, payload: dict[str, object]) -> None:
    if not app.flow_monitor_canvas:
        return
    app._hide_flow_tooltip()
    nodes, edges, display_settings, view_state = app._build_flow_graph_models(payload)
    app.flow_monitor_canvas.load_data(nodes, edges)
    if display_settings:
        line_thickness = max(1.0, app._to_float(display_settings.get("line_thickness"), 2.0))
        font_family = str(getattr(app, "_ui_font_family", "微软雅黑") or "微软雅黑")
        try:
            font_size = int(getattr(app, "_ui_font_size", 9))
        except Exception:
            font_size = 9
        node_text_color = str(display_settings.get("node_text_color") or "#111827").strip() or "#111827"
        edge_text_color = str(display_settings.get("edge_text_color") or "#374151").strip() or "#374151"
        app.flow_monitor_canvas.apply_display_settings(
            line_thickness=line_thickness,
            font_family=font_family,
            font_size=font_size,
            node_text_color=node_text_color,
            edge_text_color=edge_text_color,
        )
    if view_state:
        app.flow_monitor_canvas.apply_view_state(view_state)
    app.flow_monitor_canvas.selected_node_id = None
    app.flow_monitor_canvas.selected_edge_id = None
    if hasattr(app.flow_monitor_canvas, "_sync_selection_styles"):
        app.flow_monitor_canvas._sync_selection_styles()  # type: ignore[attr-defined]
    app._flow_active_node_id = ""


def load_workflow_json_file(app) -> None:
    path = filedialog.askopenfilename(
        title="选择流程文件",
        filetypes=[("JSON", "*.json"), ("All files", "*.*")],
    )
    if not path:
        return
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except Exception as exc:
        messagebox.showerror("读取失败", str(exc))
        return
    try:
        payload = json.loads(raw)
    except Exception as exc:
        messagebox.showerror("JSON无效", f"文件不是有效JSON：{exc}")
        return
    if not isinstance(payload, dict):
        messagebox.showerror("结构无效", "流程文件根节点必须是 JSON 对象。")
        return
    try:
        app._render_flow_monitor_graph(payload)
    except Exception as exc:
        messagebox.showerror("结构无效", str(exc))
        return
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    nodes_count = len(nodes) if isinstance(nodes, list) else 0
    edges_count = len(edges) if isinstance(edges, list) else 0
    pretty = json.dumps(payload, ensure_ascii=False, indent=2)
    app._loaded_workflow_payload = payload
    app._loaded_workflow_json_text = pretty
    app._loaded_workflow_json_path = str(Path(path))
    app._loaded_workflow_json_nodes = nodes_count
    app._loaded_workflow_json_edges = edges_count
    app._flow_active_node_id = ""
    app.flow_path_var.set(app._loaded_workflow_json_path)
    app.flow_summary_var.set(f"已加载流程图，nodes={nodes_count} edges={edges_count}，等待执行信号。")
    app._set_text_content(app.flow_json_text, pretty)
    ts_text = datetime.now().strftime("%H:%M:%S")
    app._append_line(
        app.log_text,
        f"[{ts_text}] [FLOW] loaded path={app._loaded_workflow_json_path} nodes={nodes_count} edges={edges_count}",
    )


def clear_loaded_workflow_json(app) -> None:
    app._loaded_workflow_json_text = ""
    app._loaded_workflow_json_path = ""
    app._loaded_workflow_json_nodes = 0
    app._loaded_workflow_json_edges = 0
    app._loaded_workflow_payload = None
    app._flow_active_node_id = ""
    app._hide_flow_tooltip()
    app.flow_path_var.set("未加载")
    app.flow_summary_var.set("未加载流程文件")
    app._set_text_content(app.flow_json_text, "未加载流程文件。点击“加载流程文件”选择 workflow_json。")
    if app.flow_monitor_canvas:
        app.flow_monitor_canvas.clear()
