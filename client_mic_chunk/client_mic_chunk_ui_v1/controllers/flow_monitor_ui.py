from __future__ import annotations

import tkinter as tk


def toggle_flow_script_panel(app) -> None:
    panes = app.flow_panes
    flow_box = app.flow_json_box
    if not panes or not flow_box:
        return
    pane_ids = set(panes.panes())
    flow_box_id = str(flow_box)
    show_script = bool(app.flow_show_script_var.get())
    if show_script:
        if flow_box_id not in pane_ids:
            panes.add(flow_box, weight=2)
        return
    if flow_box_id in pane_ids:
        panes.forget(flow_box)


def flow_monitor_zoom_in(app) -> None:
    canvas = app.flow_monitor_canvas
    if canvas:
        canvas.zoom_in()
        app._apply_flow_monitor_active_node_style()


def flow_monitor_zoom_out(app) -> None:
    canvas = app.flow_monitor_canvas
    if canvas:
        canvas.zoom_out()
        app._apply_flow_monitor_active_node_style()


def flow_monitor_zoom_reset(app) -> None:
    canvas = app.flow_monitor_canvas
    if canvas:
        canvas.reset_zoom()
        app._apply_flow_monitor_active_node_style()


def apply_flow_monitor_active_node_style(app) -> None:
    canvas = app.flow_monitor_canvas
    active_node_id = str(app._flow_active_node_id or "").strip()
    if (not canvas) or (not active_node_id):
        return
    node = canvas.nodes.get(active_node_id)
    if not node or not node.shape_item_id:
        return
    canvas.itemconfigure(
        node.shape_item_id,
        outline="#dc2626",
        width=max(canvas.selected_line_width, canvas.base_line_width + 1),
    )


def lock_flow_monitor_interactions(app) -> None:
    if not app.flow_monitor_canvas:
        return
    for sequence in (
        "<ButtonPress-1>",
        "<B1-Motion>",
        "<ButtonRelease-1>",
        "<Double-Button-1>",
        "<Delete>",
        "<BackSpace>",
    ):
        app.flow_monitor_canvas.bind(sequence, lambda _event: "break")


def bind_flow_monitor_hover_events(app) -> None:
    if not app.flow_monitor_canvas:
        return
    app.flow_monitor_canvas.bind("<Motion>", app._on_flow_monitor_motion, add="+")
    app.flow_monitor_canvas.bind("<Leave>", app._on_flow_monitor_leave, add="+")


def restore_flow_monitor_highlight(app) -> None:
    canvas = app.flow_monitor_canvas
    active_node_id = str(app._flow_active_node_id or "").strip()
    if not canvas or not active_node_id:
        return
    if active_node_id not in canvas.nodes:
        return
    if canvas.selected_node_id == active_node_id and canvas.selected_edge_id is None:
        app._apply_flow_monitor_active_node_style()
        return
    canvas.selected_node_id = active_node_id
    canvas.selected_edge_id = None
    if hasattr(canvas, "_sync_selection_styles"):
        canvas._sync_selection_styles()  # type: ignore[attr-defined]
    app._apply_flow_monitor_active_node_style()


def flow_monitor_node_id_at(app, canvas_x: float, canvas_y: float) -> str:
    canvas = app.flow_monitor_canvas
    if not canvas:
        return ""
    item_ids = canvas.find_overlapping(canvas_x - 1, canvas_y - 1, canvas_x + 1, canvas_y + 1)
    for item_id in reversed(item_ids):
        node_id = canvas.item_to_node.get(item_id)
        if node_id:
            return str(node_id)
    return ""


def show_flow_tooltip(app, text: str, screen_x: int, screen_y: int) -> None:
    content = str(text or "").strip() or "(无 task_notes)"
    if not app._flow_tooltip_window:
        tip = tk.Toplevel(app)
        tip.withdraw()
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        label = tk.Label(
            tip,
            text=content,
            justify="left",
            anchor="nw",
            bg="#0f172a",
            fg="#f8fafc",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=6,
            wraplength=380,
        )
        label.pack(fill="both", expand=True)
        app._flow_tooltip_window = tip
        app._flow_tooltip_label = label
    if app._flow_tooltip_label:
        app._flow_tooltip_label.configure(text=content)
    if app._flow_tooltip_window:
        app._flow_tooltip_window.geometry(f"+{int(screen_x)}+{int(screen_y)}")
        app._flow_tooltip_window.deiconify()


def hide_flow_tooltip(app) -> None:
    if app._flow_tooltip_window:
        app._flow_tooltip_window.withdraw()
    app._flow_hover_node_id = ""


def on_flow_monitor_leave(app, _event) -> None:
    app._hide_flow_tooltip()
    app._restore_flow_monitor_highlight()


def on_flow_monitor_motion(app, event) -> None:
    canvas = app.flow_monitor_canvas
    if not canvas:
        return
    canvas_x = canvas.canvasx(event.x)
    canvas_y = canvas.canvasy(event.y)
    hover_node_id = app._flow_monitor_node_id_at(canvas_x, canvas_y)
    if not hover_node_id:
        app._hide_flow_tooltip()
        app._restore_flow_monitor_highlight()
        return
    node = canvas.nodes.get(hover_node_id)
    if node is None:
        app._hide_flow_tooltip()
        app._restore_flow_monitor_highlight()
        return
    app._flow_hover_node_id = hover_node_id
    app._show_flow_tooltip(
        text=f"节点ID: {hover_node_id}\n\n{str(node.task_notes or '').strip() or '(无 task_notes)'}",
        screen_x=event.x_root + 14,
        screen_y=event.y_root + 14,
    )
    app._restore_flow_monitor_highlight()


def center_flow_monitor_node(app, node_id: str) -> None:
    canvas = app.flow_monitor_canvas
    if not canvas:
        return
    node = canvas.nodes.get(node_id)
    if node is None:
        return
    canvas.update_idletasks()
    region_text = str(canvas.cget("scrollregion") or "").strip()
    if not region_text:
        return
    parts = region_text.split()
    if len(parts) != 4:
        return
    try:
        left, top, right, bottom = [float(item) for item in parts]
    except Exception:
        return
    total_width = max(1.0, right - left)
    total_height = max(1.0, bottom - top)
    view_width = max(1.0, float(canvas.winfo_width()))
    view_height = max(1.0, float(canvas.winfo_height()))
    max_x = max(1.0, total_width - view_width)
    max_y = max(1.0, total_height - view_height)
    x_target = max(0.0, min(max_x, (node.x - left) - view_width / 2.0))
    y_target = max(0.0, min(max_y, (node.y - top) - view_height / 2.0))
    canvas.xview_moveto(x_target / max_x if max_x > 0 else 0.0)
    canvas.yview_moveto(y_target / max_y if max_y > 0 else 0.0)


def highlight_flow_monitor_node(app, node_id: str, *, center: bool = True) -> bool:
    canvas = app.flow_monitor_canvas
    if not canvas:
        return False
    target_id = str(node_id or "").strip()
    if (not target_id) or (target_id not in canvas.nodes):
        return False
    canvas.selected_node_id = target_id
    canvas.selected_edge_id = None
    if hasattr(canvas, "_sync_selection_styles"):
        canvas._sync_selection_styles()  # type: ignore[attr-defined]
    if center:
        app._center_flow_monitor_node(target_id)
    app._flow_active_node_id = target_id
    app._apply_flow_monitor_active_node_style()
    return True
