from __future__ import annotations

from collections import defaultdict, deque
import tkinter as tk
from tkinter import simpledialog, ttk
from typing import Callable
from uuid import uuid4

from .models import DEFAULT_LABELS, DEFAULT_SIZE, Edge, Node, NodeType

UI_FONT_FAMILY = "微软雅黑"
UI_FONT_SIZE = 10


class NodeEditDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        node_text: str,
        task_notes: str,
        ui_font: tuple[str, int],
    ) -> None:
        self._ui_font = ui_font
        self._text_var = tk.StringVar(value=node_text)
        self._initial_task_notes = task_notes
        self._notes_text: tk.Text | None = None
        super().__init__(parent, title="编辑节点")

    def body(self, master: tk.Misc) -> tk.Widget | None:
        master.columnconfigure(1, weight=1)

        tk.Label(master, text="节点文本：", font=self._ui_font).grid(
            row=0, column=0, sticky="w", padx=(12, 6), pady=(12, 6)
        )
        entry = tk.Entry(master, textvariable=self._text_var, font=self._ui_font, width=32)
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 6))

        tk.Label(master, text="任务/动作（多行）：", font=self._ui_font).grid(
            row=1, column=0, sticky="nw", padx=(12, 6), pady=(0, 6)
        )
        self._notes_text = tk.Text(master, width=44, height=8, wrap="word", font=self._ui_font)
        self._notes_text.grid(row=1, column=1, sticky="nsew", padx=(0, 12), pady=(0, 12))
        self._notes_text.insert("1.0", self._initial_task_notes)

        return entry

    def apply(self) -> None:
        notes = ""
        if self._notes_text is not None:
            notes = self._notes_text.get("1.0", "end-1c").strip()
        self.result = {"text": self._text_var.get().strip(), "task_notes": notes}

    def buttonbox(self) -> None:
        box = ttk.Frame(self)
        ok_btn = ttk.Button(box, text="确定", command=self.ok)
        cancel_btn = ttk.Button(box, text="取消", command=self.cancel)
        ok_btn.pack(side=tk.LEFT, padx=6, pady=8)
        cancel_btn.pack(side=tk.LEFT, padx=6, pady=8)
        self.bind("<Escape>", self.cancel)
        box.pack()


class FlowCanvas(tk.Canvas):
    def __init__(
        self,
        master: tk.Misc,
        *,
        ui_scale: float = 1.0,
        font_family: str = UI_FONT_FAMILY,
        font_size: int = UI_FONT_SIZE,
        status_callback: Callable[[str], None] | None = None,
        changed_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, background="#f8f9fb", highlightthickness=0)
        self.ui_scale = max(1.0, float(ui_scale))

        self.font_family = font_family
        self.base_font_size = max(8, int(font_size))
        self.display_font_family = font_family
        self.display_font_size = max(8, int(font_size))
        self.line_thickness = 2.0
        self.node_text_color = "#111827"
        self.edge_text_color = "#374151"
        self.zoom_ratio = 1.0
        self.min_zoom_ratio = 0.5
        self.max_zoom_ratio = 2.4

        self.base_line_width = 2
        self.selected_line_width = 3
        self.text_font = (self.font_family, self.base_font_size)
        self.edge_label_offset = 14.0 * self.ui_scale

        self.status_callback = status_callback
        self.changed_callback = changed_callback

        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}
        self.item_to_node: dict[int, str] = {}
        self.item_to_edge: dict[int, str] = {}

        self.selected_node_id: str | None = None
        self.selected_edge_id: str | None = None
        self.dragging_node_id: str | None = None
        self.dragging_resize_handle: tuple[str, str] | None = None
        self.dragging_edge_id: str | None = None
        self.dragging_edge_handle: tuple[str, int] | None = None
        self.dragging_edge_source_id: str | None = None
        self.dragging_edge_target_id: str | None = None
        self.dragging_edge_target_preview_id: int | None = None
        self.dragging_edge_target_preview_line_marker_id: int | None = None
        self.dragging_edge_target_preview_node_marker_id: int | None = None
        self.last_drag_pos: tuple[float, float] | None = None
        self.drag_moved = False

        self.connect_mode = False
        self.connect_source_id: str | None = None
        self.edge_handle_items: dict[int, tuple[str, int]] = {}
        self.edge_handles_by_edge: dict[str, list[int]] = {}
        self.edge_source_handle_items: dict[int, str] = {}
        self.edge_source_handles_by_edge: dict[str, int] = {}
        self.edge_target_handle_items: dict[int, str] = {}
        self.edge_target_handles_by_edge: dict[str, int] = {}
        self.node_resize_handle_items: dict[int, tuple[str, str]] = {}
        self.node_resize_handles_by_node: dict[str, list[int]] = {}

        self._refresh_visual_metrics()

        self.bind("<ButtonPress-1>", self._on_left_press)
        self.bind("<B1-Motion>", self._on_mouse_drag)
        self.bind("<ButtonRelease-1>", self._on_left_release)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Delete>", self._on_delete)
        self.bind("<Enter>", self._on_enter_canvas)
        self.bind("<MouseWheel>", self._on_mouse_wheel)
        self.bind("<Shift-MouseWheel>", self._on_shift_mouse_wheel)
        self.bind("<Button-4>", self._on_mouse_wheel_linux)
        self.bind("<Button-5>", self._on_mouse_wheel_linux)
        self.bind("<Shift-Button-4>", self._on_shift_mouse_wheel_linux)
        self.bind("<Shift-Button-5>", self._on_shift_mouse_wheel_linux)

        self._refresh_scrollregion()

    def set_connect_mode(self, enabled: bool) -> None:
        self.connect_mode = enabled
        self.connect_source_id = None
        self._sync_selection_styles()
        if enabled:
            self._notify("连线模式开启：先点起点，再点终点。")
        else:
            self._notify("连线模式已关闭。")

    def get_display_settings(self) -> dict[str, float | int | str]:
        return {
            "line_thickness": self.line_thickness,
            "font_family": self.display_font_family,
            "font_size": self.display_font_size,
            "node_text_color": self.node_text_color,
            "edge_text_color": self.edge_text_color,
        }

    def get_view_state(self) -> dict[str, float]:
        x_first = 0.0
        y_first = 0.0
        x_view = self.xview()
        y_view = self.yview()
        if x_view:
            x_first = float(x_view[0])
        if y_view:
            y_first = float(y_view[0])
        return {
            "zoom_ratio": float(self.zoom_ratio),
            "xview": x_first,
            "yview": y_first,
        }

    def apply_view_state(self, state: dict[str, object] | None) -> None:
        if not state:
            return

        zoom_raw = state.get("zoom_ratio")
        try:
            zoom_ratio = float(zoom_raw)
        except Exception:  # noqa: BLE001
            zoom_ratio = self.zoom_ratio
        zoom_ratio = min(self.max_zoom_ratio, max(self.min_zoom_ratio, zoom_ratio))

        x_raw = state.get("xview")
        y_raw = state.get("yview")
        try:
            x_first = float(x_raw)
        except Exception:  # noqa: BLE001
            x_first = 0.0
        try:
            y_first = float(y_raw)
        except Exception:  # noqa: BLE001
            y_first = 0.0
        x_first = max(0.0, min(1.0, x_first))
        y_first = max(0.0, min(1.0, y_first))

        self.zoom_ratio = zoom_ratio
        self._refresh_visual_metrics()
        for node in self.nodes.values():
            self._update_node_geometry(node)
        for edge in self.edges.values():
            self._update_edge_geometry(edge)
        self._refresh_scrollregion()
        self._sync_selection_styles()

        def _restore_view() -> None:
            self.xview_moveto(x_first)
            self.yview_moveto(y_first)

        self.after_idle(_restore_view)

    def apply_display_settings(
        self,
        *,
        line_thickness: float | None = None,
        font_family: str | None = None,
        font_size: int | None = None,
        node_text_color: str | None = None,
        edge_text_color: str | None = None,
    ) -> None:
        if line_thickness is not None:
            self.line_thickness = max(1.0, float(line_thickness))
        if font_family is not None and font_family.strip():
            self.display_font_family = font_family.strip()
        if font_size is not None:
            self.display_font_size = max(7, int(font_size))
        if node_text_color is not None and node_text_color.strip():
            self.node_text_color = node_text_color.strip()
        if edge_text_color is not None and edge_text_color.strip():
            self.edge_text_color = edge_text_color.strip()

        self._refresh_visual_metrics()
        for node in self.nodes.values():
            self._update_node_geometry(node)
        for edge in self.edges.values():
            self._update_edge_geometry(edge)
        self._refresh_scrollregion()
        self._sync_selection_styles()

    def zoom_in(self) -> bool:
        return self._apply_zoom(1.15)

    def zoom_out(self) -> bool:
        return self._apply_zoom(1 / 1.15)

    def reset_zoom(self) -> bool:
        if abs(self.zoom_ratio - 1.0) < 1e-6:
            return False
        return self._apply_zoom(1.0 / self.zoom_ratio)

    def auto_layout(self) -> bool:
        if not self.nodes:
            self._notify("当前没有节点可排版。")
            return False

        outgoing: dict[str, list[str]] = defaultdict(list)
        indegree: dict[str, int] = {node_id: 0 for node_id in self.nodes}

        for edge in self.edges.values():
            if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
                continue
            outgoing[edge.source_id].append(edge.target_id)
            indegree[edge.target_id] += 1

        queue = deque(
            sorted((node_id for node_id, degree in indegree.items() if degree == 0), key=self._node_sort_key)
        )
        topo_order: list[str] = []
        left_indegree = dict(indegree)

        while queue:
            node_id = queue.popleft()
            topo_order.append(node_id)
            for nxt in sorted(outgoing.get(node_id, []), key=self._node_sort_key):
                left_indegree[nxt] -= 1
                if left_indegree[nxt] == 0:
                    queue.append(nxt)

        known = set(topo_order)
        for node_id in sorted(self.nodes.keys(), key=self._node_sort_key):
            if node_id not in known:
                topo_order.append(node_id)

        layer: dict[str, int] = {node_id: 0 for node_id in self.nodes}
        for node_id in topo_order:
            base = layer[node_id]
            for nxt in outgoing.get(node_id, []):
                layer[nxt] = max(layer[nxt], base + 1)

        grouped: dict[int, list[str]] = defaultdict(list)
        for node_id, layer_index in layer.items():
            grouped[layer_index].append(node_id)
        for node_ids in grouped.values():
            node_ids.sort(key=self._node_sort_key)

        max_width = max((node.width for node in self.nodes.values()), default=160.0)
        max_height = max((node.height for node in self.nodes.values()), default=90.0)
        x_gap = max_width + 170.0 * self.ui_scale
        y_gap = max_height + 95.0 * self.ui_scale

        base_x = 180.0 * self.ui_scale
        base_y = 140.0 * self.ui_scale
        max_rows = max((len(v) for v in grouped.values()), default=1)

        for layer_index in sorted(grouped.keys()):
            node_ids = grouped[layer_index]
            start_y = base_y + (max_rows - len(node_ids)) * y_gap / 2
            x = base_x + layer_index * x_gap
            for row, node_id in enumerate(node_ids):
                node = self.nodes[node_id]
                node.x = x
                node.y = start_y + row * y_gap
                self._update_node_geometry(node)

        for edge in self.edges.values():
            edge.route_points = []
            self._update_edge_geometry(edge)

        self._refresh_scrollregion()
        self._sync_selection_styles()
        self._changed()
        self._notify("已自动排版。")
        return True

    def add_node(self, node_type: NodeType, x: float, y: float) -> str:
        base_width, base_height = DEFAULT_SIZE[node_type]
        width = base_width * self.ui_scale * self.zoom_ratio
        height = base_height * self.ui_scale * self.zoom_ratio
        node = Node(
            id=f"node-{uuid4().hex[:8]}",
            node_type=node_type,
            x=x,
            y=y,
            width=width,
            height=height,
            text=DEFAULT_LABELS[node_type],
        )
        self._render_node(node)
        self.nodes[node.id] = node
        self._refresh_scrollregion()
        self._select_node(node.id)
        self._changed()
        return node.id

    def add_edge(self, source_id: str, target_id: str) -> str | None:
        if source_id == target_id:
            self._notify("不能把节点连接到自身。")
            return None
        for edge in self.edges.values():
            if edge.source_id == source_id and edge.target_id == target_id:
                self._notify("该连线已存在。")
                return None

        source = self.nodes.get(source_id)
        target = self.nodes.get(target_id)
        if not source or not target:
            return None

        edge = Edge(id=f"edge-{uuid4().hex[:8]}", source_id=source_id, target_id=target_id)
        self._render_edge(edge)
        self.edges[edge.id] = edge
        self._refresh_scrollregion()
        self._select_edge(edge.id)
        self._changed()
        return edge.id

    def get_nodes(self) -> list[Node]:
        return [self._clone_node(node) for node in self.nodes.values()]

    def get_edges(self) -> list[Edge]:
        return [
            Edge(
                id=edge.id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                text=edge.text,
                route_points=list(edge.route_points),
                source_anchor=edge.source_anchor,
                target_anchor=edge.target_anchor,
            )
            for edge in self.edges.values()
        ]

    def load_data(self, nodes: list[Node], edges: list[Edge]) -> None:
        self.clear()
        self.zoom_ratio = 1.0
        self._refresh_visual_metrics()

        for node in nodes:
            self._render_node(node)
            self.nodes[node.id] = node
        for edge in edges:
            source = self.nodes.get(edge.source_id)
            target = self.nodes.get(edge.target_id)
            if not source or not target:
                continue
            self._render_edge(edge)
            self.edges[edge.id] = edge

        self._refresh_scrollregion()
        self._notify("已加载流程图。")

    def clear(self) -> None:
        self.delete("all")
        self.nodes.clear()
        self.edges.clear()
        self.item_to_node.clear()
        self.item_to_edge.clear()
        self.edge_handle_items.clear()
        self.edge_handles_by_edge.clear()
        self.edge_source_handle_items.clear()
        self.edge_source_handles_by_edge.clear()
        self.edge_target_handle_items.clear()
        self.edge_target_handles_by_edge.clear()
        self.node_resize_handle_items.clear()
        self.node_resize_handles_by_node.clear()
        self.selected_node_id = None
        self.selected_edge_id = None
        self.dragging_node_id = None
        self.dragging_resize_handle = None
        self.dragging_edge_id = None
        self.dragging_edge_handle = None
        self.dragging_edge_source_id = None
        self.dragging_edge_target_id = None
        self._clear_dragging_edge_target_preview()
        self.last_drag_pos = None
        self.connect_source_id = None
        self._refresh_scrollregion()

    def delete_selected(self) -> None:
        if self.selected_node_id:
            self._delete_node(self.selected_node_id)
            self.selected_node_id = None
            self._changed()
            return
        if self.selected_edge_id:
            self._delete_edge(self.selected_edge_id)
            self.selected_edge_id = None
            self._changed()

    def _on_left_press(self, event: tk.Event) -> None:
        self._clear_dragging_edge_target_preview()
        self.focus_set()
        x = self.canvasx(event.x)
        y = self.canvasy(event.y)
        item = self._current_item_id()
        handle_info = self.edge_handle_items.get(item) if item else None
        source_handle_edge_id = self.edge_source_handle_items.get(item) if item else None
        target_handle_edge_id = self.edge_target_handle_items.get(item) if item else None
        resize_handle_info = self.node_resize_handle_items.get(item) if item else None
        node_id = self.item_to_node.get(item) if item else None
        edge_id = self.item_to_edge.get(item) if item else None

        if source_handle_edge_id and not self.connect_mode:
            self._select_edge(source_handle_edge_id)
            self.dragging_node_id = None
            self.dragging_resize_handle = None
            self.dragging_edge_id = None
            self.dragging_edge_handle = None
            self.dragging_edge_source_id = source_handle_edge_id
            self.dragging_edge_target_id = None
            self.last_drag_pos = (x, y)
            self.drag_moved = False
            edge = self.edges.get(source_handle_edge_id)
            if edge:
                self._start_dragging_edge_target_preview(edge, x, y, mode="source")
            self._notify("拖动到新的起点图元并松开，可重连起点。")
            return

        if target_handle_edge_id and not self.connect_mode:
            self._select_edge(target_handle_edge_id)
            self.dragging_node_id = None
            self.dragging_resize_handle = None
            self.dragging_edge_id = None
            self.dragging_edge_handle = None
            self.dragging_edge_source_id = None
            self.dragging_edge_target_id = target_handle_edge_id
            self.last_drag_pos = (x, y)
            self.drag_moved = False
            edge = self.edges.get(target_handle_edge_id)
            if edge:
                self._start_dragging_edge_target_preview(edge, x, y, mode="target")
            self._notify("拖动到目标图元并松开，可重连终点。")
            return

        if resize_handle_info and not self.connect_mode:
            node_id, handle_name = resize_handle_info
            self._select_node(node_id)
            self.dragging_node_id = None
            self.dragging_resize_handle = (node_id, handle_name)
            self.dragging_edge_id = None
            self.dragging_edge_handle = None
            self.dragging_edge_source_id = None
            self.dragging_edge_target_id = None
            self.last_drag_pos = (x, y)
            self.drag_moved = False
            return

        if handle_info and not self.connect_mode:
            self._select_edge(handle_info[0])
            self.dragging_node_id = None
            self.dragging_resize_handle = None
            self.dragging_edge_id = None
            self.dragging_edge_handle = handle_info
            self.dragging_edge_source_id = None
            self.dragging_edge_target_id = None
            self.last_drag_pos = (x, y)
            self.drag_moved = False
            return

        if self.connect_mode:
            self._handle_connect_click(node_id)
            return

        if node_id:
            self._select_node(node_id)
            self.dragging_node_id = node_id
            self.dragging_resize_handle = None
            self.dragging_edge_id = None
            self.dragging_edge_handle = None
            self.dragging_edge_source_id = None
            self.dragging_edge_target_id = None
            self.last_drag_pos = (x, y)
            self.drag_moved = False
            return
        if edge_id:
            self._select_edge(edge_id)
            self.dragging_node_id = None
            self.dragging_resize_handle = None
            self.dragging_edge_handle = None
            self.dragging_edge_id = edge_id
            self.dragging_edge_source_id = None
            self.dragging_edge_target_id = None
            self.last_drag_pos = (x, y)
            self.drag_moved = False
            return

        self.dragging_node_id = None
        self.dragging_resize_handle = None
        self.dragging_edge_id = None
        self.dragging_edge_handle = None
        self.dragging_edge_source_id = None
        self.dragging_edge_target_id = None
        self.last_drag_pos = None
        self.drag_moved = False
        self._clear_selection()

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if self.connect_mode:
            return

        x = self.canvasx(event.x)
        y = self.canvasy(event.y)

        if self.dragging_edge_source_id:
            edge = self.edges.get(self.dragging_edge_source_id)
            if edge:
                self._update_dragging_edge_target_preview(edge, x, y, mode="source")
            self.drag_moved = True
            self.last_drag_pos = (x, y)
            return

        if self.dragging_edge_target_id:
            edge = self.edges.get(self.dragging_edge_target_id)
            if edge:
                self._update_dragging_edge_target_preview(edge, x, y, mode="target")
            self.drag_moved = True
            self.last_drag_pos = (x, y)
            return

        if self.dragging_resize_handle:
            node_id, handle_name = self.dragging_resize_handle
            node = self.nodes.get(node_id)
            if not node:
                return
            if self._resize_node_with_handle(node, handle_name, x, y):
                self.drag_moved = True
                self._update_edges_for_node(node.id)
                self._sync_selection_styles()
            self.last_drag_pos = (x, y)
            return

        if self.dragging_edge_handle and self.last_drag_pos:
            edge_id, bend_index = self.dragging_edge_handle
            edge = self.edges.get(edge_id)
            if not edge:
                return
            self._ensure_edge_route_points(edge)
            if bend_index >= len(edge.route_points):
                return
            x_candidates, y_candidates = self._build_snap_candidates(edge, skip_index=bend_index)
            snapped_x = self._snap_value(x, x_candidates)
            snapped_y = self._snap_value(y, y_candidates)
            edge.route_points[bend_index] = (snapped_x, snapped_y)
            self.last_drag_pos = (x, y)
            self.drag_moved = True
            self._update_edge_geometry(edge)
            self._sync_selection_styles()
            return

        if self.dragging_edge_id and self.last_drag_pos:
            edge = self.edges.get(self.dragging_edge_id)
            if not edge:
                return
            self._ensure_edge_route_points(edge)
            dx = x - self.last_drag_pos[0]
            dy = y - self.last_drag_pos[1]
            if dx == 0 and dy == 0:
                return
            moved_route_points = [(px + dx, py + dy) for px, py in edge.route_points]
            x_candidates, y_candidates = self._build_snap_candidates(edge, include_route_points=False)
            if moved_route_points:
                ref_x, ref_y = moved_route_points[0]
                snapped_ref_x = self._snap_value(ref_x, x_candidates)
                snapped_ref_y = self._snap_value(ref_y, y_candidates)
                delta_x = snapped_ref_x - ref_x
                delta_y = snapped_ref_y - ref_y
                moved_route_points = [(px + delta_x, py + delta_y) for px, py in moved_route_points]
            edge.route_points = moved_route_points
            self.last_drag_pos = (x, y)
            self.drag_moved = True
            self._update_edge_geometry(edge)
            self._sync_selection_styles()
            return

        if not self.dragging_node_id or not self.last_drag_pos:
            return
        node = self.nodes.get(self.dragging_node_id)
        if not node:
            return
        dx = x - self.last_drag_pos[0]
        dy = y - self.last_drag_pos[1]
        if dx == 0 and dy == 0:
            return

        self.move(node.shape_item_id, dx, dy)
        self.move(node.text_item_id, dx, dy)
        node.x += dx
        node.y += dy
        self.last_drag_pos = (x, y)
        self.drag_moved = True
        self._update_edges_for_node(node.id)

    def _on_left_release(self, event: tk.Event) -> None:
        if self.dragging_edge_source_id:
            edge = self.edges.get(self.dragging_edge_source_id)
            if edge:
                source_reconnected = False
                drop_x = self.canvasx(event.x)
                drop_y = self.canvasy(event.y)
                new_source_id = self._node_id_at_canvas_point(drop_x, drop_y)
                if new_source_id:
                    if new_source_id == edge.target_id:
                        self._notify("起点不能与终点相同。")
                    elif new_source_id != edge.source_id:
                        duplicate = any(
                            other.id != edge.id and other.source_id == new_source_id and other.target_id == edge.target_id
                            for other in self.edges.values()
                        )
                        if duplicate:
                            self._notify("该起点连线已存在。")
                        else:
                            source_node = self.nodes.get(new_source_id)
                            edge.source_id = new_source_id
                            edge.source_anchor = self._target_anchor_from_drop(source_node, drop_x, drop_y) if source_node else None
                            edge.route_points = []
                            self._update_edge_geometry(edge)
                            side_name = {
                                "left": "左边",
                                "right": "右边",
                                "top": "上边",
                                "bottom": "下边",
                            }.get(edge.source_anchor or "", "自动")
                            self._notify(f"起点已重新连接（{side_name}）。")
                            source_reconnected = True
                    else:
                        source_node = self.nodes.get(new_source_id)
                        edge.source_anchor = self._target_anchor_from_drop(source_node, drop_x, drop_y) if source_node else edge.source_anchor
                        edge.route_points = []
                        self._update_edge_geometry(edge)
                        side_name = {
                            "left": "左边",
                            "right": "右边",
                            "top": "上边",
                            "bottom": "下边",
                        }.get(edge.source_anchor or "", "自动")
                        self._notify(f"起点连接边已更新（{side_name}）。")
                        source_reconnected = True
                if source_reconnected:
                    self.drag_moved = True
                elif self.drag_moved:
                    self.drag_moved = False
                    self._notify("未命中新起点，连线保持不变。")

        if self.dragging_edge_target_id:
            edge = self.edges.get(self.dragging_edge_target_id)
            if edge:
                target_reconnected = False
                drop_x = self.canvasx(event.x)
                drop_y = self.canvasy(event.y)
                new_target_id = self._node_id_at_canvas_point(drop_x, drop_y)
                if new_target_id:
                    if new_target_id == edge.source_id:
                        self._notify("终点不能与起点相同。")
                    elif new_target_id != edge.target_id:
                        duplicate = any(
                            other.id != edge.id and other.source_id == edge.source_id and other.target_id == new_target_id
                            for other in self.edges.values()
                        )
                        if duplicate:
                            self._notify("该终点连线已存在。")
                        else:
                            target_node = self.nodes.get(new_target_id)
                            edge.target_id = new_target_id
                            edge.target_anchor = self._target_anchor_from_drop(target_node, drop_x, drop_y) if target_node else None
                            edge.route_points = []
                            self._update_edge_geometry(edge)
                            side_name = {
                                "left": "左边",
                                "right": "右边",
                                "top": "上边",
                                "bottom": "下边",
                            }.get(edge.target_anchor or "", "自动")
                            self._notify(f"终点已重新连接（{side_name}）。")
                            target_reconnected = True
                    else:
                        target_node = self.nodes.get(new_target_id)
                        edge.target_anchor = self._target_anchor_from_drop(target_node, drop_x, drop_y) if target_node else edge.target_anchor
                        edge.route_points = []
                        self._update_edge_geometry(edge)
                        side_name = {
                            "left": "左边",
                            "right": "右边",
                            "top": "上边",
                            "bottom": "下边",
                        }.get(edge.target_anchor or "", "自动")
                        self._notify(f"终点连接边已更新（{side_name}）。")
                        target_reconnected = True
                if target_reconnected:
                    self.drag_moved = True
                elif self.drag_moved:
                    self.drag_moved = False
                    self._notify("未命中新终点，连线保持不变。")
        self._clear_dragging_edge_target_preview()

        edge_to_refine: Edge | None = None
        if self.drag_moved:
            if self.dragging_edge_id:
                edge_to_refine = self.edges.get(self.dragging_edge_id)
            elif self.dragging_edge_handle:
                edge_to_refine = self.edges.get(self.dragging_edge_handle[0])

        if edge_to_refine is not None:
            self._auto_refine_edge(edge_to_refine)
            self._update_edge_geometry(edge_to_refine)
            self._sync_selection_styles()

        if (
            self.dragging_node_id
            or self.dragging_resize_handle
            or self.dragging_edge_id
            or self.dragging_edge_handle
            or self.dragging_edge_source_id
            or self.dragging_edge_target_id
        ) and self.drag_moved:
            self._refresh_scrollregion()
            self._changed()
        self.dragging_node_id = None
        self.dragging_resize_handle = None
        self.dragging_edge_id = None
        self.dragging_edge_handle = None
        self.dragging_edge_source_id = None
        self.dragging_edge_target_id = None
        self.last_drag_pos = None
        self.drag_moved = False

    def _on_double_click(self, _event: tk.Event) -> None:
        item = self._current_item_id()
        if not item:
            return

        node_id = self.item_to_node.get(item)
        if node_id:
            node = self.nodes.get(node_id)
            if not node:
                return
            dialog = NodeEditDialog(
                self.winfo_toplevel(),
                node_text=node.text,
                task_notes=node.task_notes,
                ui_font=(self.display_font_family, self.display_font_size),
            )
            if dialog.result is None:
                return
            payload = dialog.result
            new_text = str(payload.get("text", "")).strip()
            node.task_notes = str(payload.get("task_notes", "")).strip()
            node.text = new_text or DEFAULT_LABELS[node.node_type]
            self.itemconfigure(node.text_item_id, text=node.text)
            self._changed()
            return

        edge_id = self.item_to_edge.get(item)
        if not edge_id:
            return
        edge = self.edges.get(edge_id)
        if not edge:
            return
        new_text = simpledialog.askstring(
            "编辑连线条件",
            "请输入连线条件（如：Y/N）：",
            initialvalue=edge.text,
            parent=self.winfo_toplevel(),
        )
        if new_text is None:
            return
        edge.text = new_text.strip()
        self._update_edge_geometry(edge)
        self._refresh_scrollregion()
        self._sync_selection_styles()
        self._changed()

    def _on_delete(self, _event: tk.Event) -> str:
        self.delete_selected()
        return "break"

    def _handle_connect_click(self, node_id: str | None) -> None:
        if not node_id:
            return
        if self.connect_source_id is None:
            self.connect_source_id = node_id
            self.selected_node_id = None
            self.selected_edge_id = None
            self._notify("已选择起点，请点击终点节点。")
            self._sync_selection_styles()
            return
        if node_id == self.connect_source_id:
            self._notify("请点击另一个节点作为终点。")
            return
        edge_id = self.add_edge(self.connect_source_id, node_id)
        if edge_id:
            self._notify("连线已创建。")
        self.connect_source_id = None
        self._sync_selection_styles()

    def _render_node(self, node: Node) -> None:
        if node.node_type is NodeType.START_END:
            shape_id = self.create_oval(0, 0, 0, 0, width=self.base_line_width, outline="#2f3136", fill="#ffffff")
        elif node.node_type is NodeType.PROCESS:
            shape_id = self.create_rectangle(
                0,
                0,
                0,
                0,
                width=self.base_line_width,
                outline="#2f3136",
                fill="#ffffff",
            )
        else:
            shape_id = self.create_polygon(
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                width=self.base_line_width,
                outline="#2f3136",
                fill="#ffffff",
            )

        text_id = self.create_text(node.x, node.y, text=node.text, font=self.text_font, width=max(20.0, node.width - 12 * self.ui_scale))

        node.shape_item_id = shape_id
        node.text_item_id = text_id
        self.item_to_node[shape_id] = node.id
        self.item_to_node[text_id] = node.id
        self.addtag_withtag("node", shape_id)
        self.addtag_withtag("node", text_id)
        self._update_node_geometry(node)

    def _update_node_geometry(self, node: Node) -> None:
        if node.shape_item_id is None or node.text_item_id is None:
            return

        left = node.x - node.width / 2
        top = node.y - node.height / 2
        right = node.x + node.width / 2
        bottom = node.y + node.height / 2

        if node.node_type is NodeType.START_END or node.node_type is NodeType.PROCESS:
            self.coords(node.shape_item_id, left, top, right, bottom)
        elif node.node_type is NodeType.DECISION:
            points = [node.x, top, right, node.y, node.x, bottom, left, node.y]
            self.coords(node.shape_item_id, *points)
        else:
            shift = node.width * 0.16
            points = [left + shift, top, right, top, right - shift, bottom, left, bottom]
            self.coords(node.shape_item_id, *points)

        self.itemconfigure(node.shape_item_id, width=self.base_line_width)
        self.coords(node.text_item_id, node.x, node.y)
        self.itemconfigure(
            node.text_item_id,
            width=max(20.0, node.width - 12 * self.ui_scale),
            font=self.text_font,
            fill=self.node_text_color,
        )

    def _delete_node(self, node_id: str) -> None:
        node = self.nodes.pop(node_id, None)
        if not node:
            return
        self._clear_node_resize_handles(node_id)
        if node.shape_item_id:
            self.item_to_node.pop(node.shape_item_id, None)
            self.delete(node.shape_item_id)
        if node.text_item_id:
            self.item_to_node.pop(node.text_item_id, None)
            self.delete(node.text_item_id)
        to_remove = [edge.id for edge in self.edges.values() if edge.source_id == node_id or edge.target_id == node_id]
        for edge_id in to_remove:
            self._delete_edge(edge_id)
        self._refresh_scrollregion()

    def _delete_edge(self, edge_id: str) -> None:
        edge = self.edges.pop(edge_id, None)
        if not edge:
            return
        self._clear_edge_handles(edge_id)
        if edge.line_item_id:
            self.item_to_edge.pop(edge.line_item_id, None)
            self.delete(edge.line_item_id)
        if edge.text_item_id:
            self.item_to_edge.pop(edge.text_item_id, None)
            self.delete(edge.text_item_id)
        self._refresh_scrollregion()

    def _update_edges_for_node(self, node_id: str) -> None:
        for edge in self.edges.values():
            if edge.source_id != node_id and edge.target_id != node_id:
                continue
            source = self.nodes.get(edge.source_id)
            target = self.nodes.get(edge.target_id)
            if not source or not target or not edge.line_item_id:
                continue
            self._update_edge_geometry(edge)

    def _clear_selection(self) -> None:
        self.selected_node_id = None
        self.selected_edge_id = None
        self._sync_selection_styles()

    def _select_node(self, node_id: str) -> None:
        self.selected_node_id = node_id
        self.selected_edge_id = None
        self._sync_selection_styles()

    def _select_edge(self, edge_id: str) -> None:
        self.selected_edge_id = edge_id
        self.selected_node_id = None
        self._sync_selection_styles()

    def _sync_selection_styles(self) -> None:
        for node in self.nodes.values():
            if not node.shape_item_id:
                continue
            outline = "#2f3136"
            width = self.base_line_width
            if node.id == self.selected_node_id:
                outline = "#1d4ed8"
                width = self.selected_line_width
            elif node.id == self.connect_source_id:
                outline = "#d97706"
                width = self.selected_line_width
            self.itemconfigure(node.shape_item_id, outline=outline, width=width)

        for edge in self.edges.values():
            if not edge.line_item_id:
                continue
            color = "#2f3136"
            width = self.base_line_width
            if edge.id == self.selected_edge_id:
                color = "#1d4ed8"
                width = self.selected_line_width
            self.itemconfigure(edge.line_item_id, fill=color, width=width)
            if edge.text_item_id:
                self.itemconfigure(edge.text_item_id, fill=self.edge_text_color, font=self.text_font)
        self._refresh_selected_node_resize_handles()
        self._refresh_selected_edge_handles()

    def _current_item_id(self) -> int | None:
        items = self.find_withtag("current")
        if not items:
            return None
        return items[-1]

    def _node_id_at_canvas_point(self, x: float, y: float) -> str | None:
        items = self.find_overlapping(x - 1, y - 1, x + 1, y + 1)
        for item_id in reversed(items):
            node_id = self.item_to_node.get(item_id)
            if node_id:
                return node_id
        return None

    def _target_anchor_from_drop(self, target: Node, drop_x: float, drop_y: float) -> str:
        left = target.x - target.width / 2
        right = target.x + target.width / 2
        top = target.y - target.height / 2
        bottom = target.y + target.height / 2

        distances = {
            "left": abs(drop_x - left),
            "right": abs(drop_x - right),
            "top": abs(drop_y - top),
            "bottom": abs(drop_y - bottom),
        }
        return min(distances, key=distances.get)

    def _start_dragging_edge_target_preview(self, edge: Edge, cursor_x: float, cursor_y: float, *, mode: str) -> None:
        points, dock_point, line_point = self._preview_retarget_points(edge, cursor_x, cursor_y, mode=mode)
        if not points:
            return
        if self.dragging_edge_target_preview_id is None:
            self.dragging_edge_target_preview_id = self.create_line(
                *points,
                arrow=tk.LAST,
                width=max(1, self.base_line_width),
                fill="#16a34a",
                dash=(8, 6),
                tags=("edge_retarget_preview",),
            )
        else:
            self.coords(self.dragging_edge_target_preview_id, *points)
            self.itemconfigure(
                self.dragging_edge_target_preview_id,
                width=max(1, self.base_line_width),
                fill="#16a34a",
            )
        self.tag_raise(self.dragging_edge_target_preview_id)
        self._update_dragging_edge_target_preview_markers(line_point, dock_point)

    def _update_dragging_edge_target_preview(self, edge: Edge, cursor_x: float, cursor_y: float, *, mode: str) -> None:
        if self.dragging_edge_target_preview_id is None:
            self._start_dragging_edge_target_preview(edge, cursor_x, cursor_y, mode=mode)
            return
        points, dock_point, line_point = self._preview_retarget_points(edge, cursor_x, cursor_y, mode=mode)
        if not points:
            return
        self.coords(self.dragging_edge_target_preview_id, *points)
        self.tag_raise(self.dragging_edge_target_preview_id)
        self._update_dragging_edge_target_preview_markers(line_point, dock_point)

    def _clear_dragging_edge_target_preview(self) -> None:
        if self.dragging_edge_target_preview_id is not None:
            self.delete(self.dragging_edge_target_preview_id)
            self.dragging_edge_target_preview_id = None
        if self.dragging_edge_target_preview_line_marker_id is not None:
            self.delete(self.dragging_edge_target_preview_line_marker_id)
            self.dragging_edge_target_preview_line_marker_id = None
        if self.dragging_edge_target_preview_node_marker_id is not None:
            self.delete(self.dragging_edge_target_preview_node_marker_id)
            self.dragging_edge_target_preview_node_marker_id = None

    def _preview_retarget_points(
        self,
        edge: Edge,
        cursor_x: float,
        cursor_y: float,
        *,
        mode: str,
    ) -> tuple[list[float], tuple[float, float] | None, tuple[float, float] | None]:
        source = self.nodes.get(edge.source_id)
        target = self.nodes.get(edge.target_id)
        if not source or not target:
            return [], None, None

        hovered_node_id = self._node_id_at_canvas_point(cursor_x, cursor_y)
        dock_point: tuple[float, float] | None = None
        if hovered_node_id:
            hovered_node = self.nodes.get(hovered_node_id)
            if hovered_node:
                anchor = self._target_anchor_from_drop(hovered_node, cursor_x, cursor_y)
                dock_point = self._anchor_point(hovered_node, anchor)

        if mode == "target":
            end_x, end_y = dock_point if dock_point else (cursor_x, cursor_y)
            start_x, start_y = self._source_anchor_to_point(
                source,
                end_x,
                end_y,
                preferred_anchor=edge.source_anchor,
            )
            line_point = (end_x, end_y)
        else:
            start_x, start_y = dock_point if dock_point else (cursor_x, cursor_y)
            end_x, end_y = self._target_anchor_to_point(
                target,
                start_x,
                start_y,
                preferred_anchor=edge.target_anchor,
            )
            line_point = (start_x, start_y)

        dx = end_x - start_x
        dy = end_y - start_y
        if abs(dx) >= abs(dy):
            mid_x = (start_x + end_x) / 2
            if abs(dy) < 2:
                return [start_x, start_y, end_x, end_y], dock_point, line_point
            return [start_x, start_y, mid_x, start_y, mid_x, end_y, end_x, end_y], dock_point, line_point

        mid_y = (start_y + end_y) / 2
        if abs(dx) < 2:
            return [start_x, start_y, end_x, end_y], dock_point, line_point
        return [start_x, start_y, start_x, mid_y, end_x, mid_y, end_x, end_y], dock_point, line_point

    def _update_dragging_edge_target_preview_markers(
        self,
        line_point: tuple[float, float] | None,
        dock_point: tuple[float, float] | None,
    ) -> None:
        if dock_point is None or line_point is None:
            if self.dragging_edge_target_preview_line_marker_id is not None:
                self.delete(self.dragging_edge_target_preview_line_marker_id)
                self.dragging_edge_target_preview_line_marker_id = None
            if self.dragging_edge_target_preview_node_marker_id is not None:
                self.delete(self.dragging_edge_target_preview_node_marker_id)
                self.dragging_edge_target_preview_node_marker_id = None
            return

        line_x, line_y = line_point
        line_radius = max(3.0, 3.0 * self.ui_scale)
        dock_radius = max(6.0, 6.0 * self.ui_scale)
        if self.dragging_edge_target_preview_line_marker_id is None:
            self.dragging_edge_target_preview_line_marker_id = self.create_oval(
                line_x - line_radius,
                line_y - line_radius,
                line_x + line_radius,
                line_y + line_radius,
                fill="#22c55e",
                outline="#16a34a",
                width=max(1, int(round(self.base_line_width * 0.75))),
                tags=("edge_retarget_marker",),
            )
        else:
            self.coords(
                self.dragging_edge_target_preview_line_marker_id,
                line_x - line_radius,
                line_y - line_radius,
                line_x + line_radius,
                line_y + line_radius,
            )

        dock_x, dock_y = dock_point
        if self.dragging_edge_target_preview_node_marker_id is None:
            self.dragging_edge_target_preview_node_marker_id = self.create_oval(
                dock_x - dock_radius,
                dock_y - dock_radius,
                dock_x + dock_radius,
                dock_y + dock_radius,
                fill="",
                outline="#22c55e",
                width=max(1, int(round(self.base_line_width))),
                tags=("edge_retarget_marker",),
            )
        else:
            self.coords(
                self.dragging_edge_target_preview_node_marker_id,
                dock_x - dock_radius,
                dock_y - dock_radius,
                dock_x + dock_radius,
                dock_y + dock_radius,
            )

        self.tag_raise(self.dragging_edge_target_preview_line_marker_id)
        self.tag_raise(self.dragging_edge_target_preview_node_marker_id)

    @staticmethod
    def _source_anchor_to_point(
        source: Node,
        target_x: float,
        target_y: float,
        *,
        preferred_anchor: str | None = None,
    ) -> tuple[float, float]:
        anchor = (preferred_anchor or "").lower()
        if anchor == "left":
            return source.x - source.width / 2, source.y
        if anchor == "right":
            return source.x + source.width / 2, source.y
        if anchor == "top":
            return source.x, source.y - source.height / 2
        if anchor == "bottom":
            return source.x, source.y + source.height / 2

        dx = target_x - source.x
        dy = target_y - source.y
        if abs(dx) >= abs(dy):
            start_x = source.x + source.width / 2 if dx >= 0 else source.x - source.width / 2
            return start_x, source.y
        start_y = source.y + source.height / 2 if dy >= 0 else source.y - source.height / 2
        return source.x, start_y

    @staticmethod
    def _target_anchor_to_point(
        target: Node,
        source_x: float,
        source_y: float,
        *,
        preferred_anchor: str | None = None,
    ) -> tuple[float, float]:
        anchor = (preferred_anchor or "").lower()
        if anchor == "left":
            return target.x - target.width / 2, target.y
        if anchor == "right":
            return target.x + target.width / 2, target.y
        if anchor == "top":
            return target.x, target.y - target.height / 2
        if anchor == "bottom":
            return target.x, target.y + target.height / 2

        dx = target.x - source_x
        dy = target.y - source_y
        if abs(dx) >= abs(dy):
            end_x = target.x - target.width / 2 if dx >= 0 else target.x + target.width / 2
            return end_x, target.y
        end_y = target.y - target.height / 2 if dy >= 0 else target.y + target.height / 2
        return target.x, end_y

    @staticmethod
    def _anchor_point(node: Node, anchor: str) -> tuple[float, float]:
        key = (anchor or "").lower()
        if key == "left":
            return node.x - node.width / 2, node.y
        if key == "right":
            return node.x + node.width / 2, node.y
        if key == "top":
            return node.x, node.y - node.height / 2
        if key == "bottom":
            return node.x, node.y + node.height / 2
        return node.x, node.y

    def _on_enter_canvas(self, _event: tk.Event) -> None:
        self.focus_set()

    def _on_mouse_wheel(self, event: tk.Event) -> str:
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return "break"
        step = -1 if delta > 0 else 1
        self.yview_scroll(step, "units")
        return "break"

    def _on_shift_mouse_wheel(self, event: tk.Event) -> str:
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return "break"
        step = -1 if delta > 0 else 1
        self.xview_scroll(step, "units")
        return "break"

    def _on_mouse_wheel_linux(self, event: tk.Event) -> str:
        num = getattr(event, "num", 0)
        if num == 4:
            self.yview_scroll(-1, "units")
        elif num == 5:
            self.yview_scroll(1, "units")
        return "break"

    def _on_shift_mouse_wheel_linux(self, event: tk.Event) -> str:
        num = getattr(event, "num", 0)
        if num == 4:
            self.xview_scroll(-1, "units")
        elif num == 5:
            self.xview_scroll(1, "units")
        return "break"

    def _refresh_scrollregion(self) -> None:
        bbox = self.bbox("all")
        pad = 180.0 * self.ui_scale
        min_width = 2200.0 * self.ui_scale
        min_height = 1400.0 * self.ui_scale

        if bbox:
            x1, y1, x2, y2 = bbox
            left = min(x1 - pad, -pad)
            top = min(y1 - pad, -pad)
            right = max(x2 + pad, min_width)
            bottom = max(y2 + pad, min_height)
        else:
            left, top, right, bottom = -pad, -pad, min_width, min_height

        self.configure(scrollregion=(left, top, right, bottom))

    def _notify(self, msg: str) -> None:
        if self.status_callback:
            self.status_callback(msg)

    def _changed(self) -> None:
        if self.changed_callback:
            self.changed_callback()

    @staticmethod
    def _clone_node(node: Node) -> Node:
        return Node(
            id=node.id,
            node_type=node.node_type,
            x=node.x,
            y=node.y,
            width=node.width,
            height=node.height,
            text=node.text,
            task_notes=node.task_notes,
        )

    def _render_edge(self, edge: Edge) -> None:
        edge.line_item_id = self.create_line(
            0,
            0,
            0,
            0,
            arrow=tk.LAST,
            width=self.base_line_width,
            fill="#2f3136",
            smooth=False,
            tags=("edge", edge.id),
        )
        self.tag_lower(edge.line_item_id)
        self.item_to_edge[edge.line_item_id] = edge.id
        self._update_edge_geometry(edge)

    def _update_edge_geometry(self, edge: Edge) -> None:
        source = self.nodes.get(edge.source_id)
        target = self.nodes.get(edge.target_id)
        if not source or not target or not edge.line_item_id:
            return

        points = self._route_edge_points(edge, source, target)
        self.coords(edge.line_item_id, *points)

        label_x, label_y = self._edge_label_position(points)
        if edge.text:
            if edge.text_item_id is None:
                edge.text_item_id = self.create_text(
                    label_x,
                    label_y,
                    text=edge.text,
                    fill=self.edge_text_color,
                    font=self.text_font,
                    tags=("edge_label", edge.id),
                )
                self.item_to_edge[edge.text_item_id] = edge.id
            else:
                self.coords(edge.text_item_id, label_x, label_y)
                self.itemconfigure(edge.text_item_id, text=edge.text, font=self.text_font, fill=self.edge_text_color)
        elif edge.text_item_id is not None:
            self.item_to_edge.pop(edge.text_item_id, None)
            self.delete(edge.text_item_id)
            edge.text_item_id = None
        if edge.id == self.selected_edge_id:
            self._refresh_selected_edge_handles()

    def _route_edge_points(self, edge: Edge, source: Node, target: Node) -> list[float]:
        if edge.route_points:
            start_x, start_y, end_x, end_y = self._edge_endpoints(edge, source, target)
            raw_points = [(start_x, start_y), *edge.route_points, (end_x, end_y)]
            raw_points = self._enforce_endpoint_alignment(edge, raw_points)
            orth_points = self._orthogonalize_points(raw_points)
            return [coord for point in orth_points for coord in point]
        return self._default_edge_points(edge, source, target)

    def _default_edge_points(self, edge: Edge, source: Node, target: Node) -> list[float]:
        start_x, start_y, end_x, end_y = self._edge_endpoints(edge, source, target)
        source_anchor = (edge.source_anchor or "").lower()
        target_anchor = (edge.target_anchor or "").lower()

        source_horizontal = source_anchor in {"left", "right"}
        source_vertical = source_anchor in {"top", "bottom"}
        target_horizontal = target_anchor in {"left", "right"}
        target_vertical = target_anchor in {"top", "bottom"}

        if not (source_horizontal or source_vertical):
            source_horizontal = abs(end_x - start_x) >= abs(end_y - start_y)
            source_vertical = not source_horizontal
        if not (target_horizontal or target_vertical):
            target_horizontal = abs(end_x - start_x) >= abs(end_y - start_y)
            target_vertical = not target_horizontal

        if source_horizontal and target_horizontal:
            bend_x = (start_x + end_x) / 2
            return [start_x, start_y, bend_x, start_y, bend_x, end_y, end_x, end_y]
        if source_vertical and target_vertical:
            bend_y = (start_y + end_y) / 2
            return [start_x, start_y, start_x, bend_y, end_x, bend_y, end_x, end_y]
        if source_horizontal and target_vertical:
            return [start_x, start_y, end_x, start_y, end_x, end_y]
        return [start_x, start_y, start_x, end_y, end_x, end_y]

    def _edge_endpoints(self, edge: Edge, source: Node, target: Node) -> tuple[float, float, float, float]:
        dx = target.x - source.x
        dy = target.y - source.y

        source_anchor = (edge.source_anchor or "").lower()
        if source_anchor == "left":
            start_x = source.x - source.width / 2
            start_y = source.y
        elif source_anchor == "right":
            start_x = source.x + source.width / 2
            start_y = source.y
        elif source_anchor == "top":
            start_x = source.x
            start_y = source.y - source.height / 2
        elif source_anchor == "bottom":
            start_x = source.x
            start_y = source.y + source.height / 2
        else:
            if abs(dx) >= abs(dy):
                if dx >= 0:
                    start_x = source.x + source.width / 2
                    start_y = source.y
                else:
                    start_x = source.x - source.width / 2
                    start_y = source.y
            else:
                if dy >= 0:
                    start_x = source.x
                    start_y = source.y + source.height / 2
                else:
                    start_x = source.x
                    start_y = source.y - source.height / 2

        target_anchor = (edge.target_anchor or "").lower()
        if target_anchor == "left":
            end_x = target.x - target.width / 2
            end_y = target.y
        elif target_anchor == "right":
            end_x = target.x + target.width / 2
            end_y = target.y
        elif target_anchor == "top":
            end_x = target.x
            end_y = target.y - target.height / 2
        elif target_anchor == "bottom":
            end_x = target.x
            end_y = target.y + target.height / 2
        else:
            if abs(dx) >= abs(dy):
                if dx >= 0:
                    end_x = target.x - target.width / 2
                    end_y = target.y
                else:
                    end_x = target.x + target.width / 2
                    end_y = target.y
            else:
                if dy >= 0:
                    end_x = target.x
                    end_y = target.y - target.height / 2
                else:
                    end_x = target.x
                    end_y = target.y + target.height / 2
        return start_x, start_y, end_x, end_y

    def _ensure_edge_route_points(self, edge: Edge) -> None:
        if edge.route_points:
            return
        source = self.nodes.get(edge.source_id)
        target = self.nodes.get(edge.target_id)
        if not source or not target:
            return
        points = self._default_edge_points(edge, source, target)
        route_points = self._extract_route_points(points)
        if not route_points:
            sx, sy, ex, ey = points[0], points[1], points[-2], points[-1]
            if abs(ex - sx) >= abs(ey - sy):
                mid_x = (sx + ex) / 2
                route_points = [(mid_x, sy), (mid_x, ey)]
            else:
                mid_y = (sy + ey) / 2
                route_points = [(sx, mid_y), (ex, mid_y)]
        edge.route_points = route_points

    def _auto_refine_edge(self, edge: Edge) -> None:
        self._ensure_edge_route_points(edge)
        if not edge.route_points:
            return

        x_candidates, y_candidates = self._build_snap_candidates(edge)
        edge.route_points = [
            (
                self._snap_value(px, x_candidates),
                self._snap_value(py, y_candidates),
            )
            for px, py in edge.route_points
        ]
        self._normalize_edge_route(edge)

    def _normalize_edge_route(self, edge: Edge) -> None:
        source = self.nodes.get(edge.source_id)
        target = self.nodes.get(edge.target_id)
        if not source or not target:
            return

        start_x, start_y, end_x, end_y = self._edge_endpoints(edge, source, target)
        points = [(start_x, start_y), *edge.route_points, (end_x, end_y)]
        if len(points) <= 2:
            edge.route_points = []
            return

        points = self._enforce_endpoint_alignment(edge, points)
        normalized = self._orthogonalize_points(points)
        edge.route_points = normalized[1:-1] if len(normalized) > 2 else []

    def _effective_route_points(self, edge: Edge) -> list[tuple[float, float]]:
        if edge.route_points:
            return list(edge.route_points)
        source = self.nodes.get(edge.source_id)
        target = self.nodes.get(edge.target_id)
        if not source or not target:
            return []
        return self._extract_route_points(self._default_edge_points(edge, source, target))

    def _enforce_endpoint_alignment(self, edge: Edge, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(points) <= 2:
            return points

        adjusted = list(points)
        start_x, start_y = adjusted[0]
        end_x, end_y = adjusted[-1]

        source_anchor = (edge.source_anchor or "").lower()
        if source_anchor in {"left", "right"}:
            adjusted[1] = (adjusted[1][0], start_y)
        elif source_anchor in {"top", "bottom"}:
            adjusted[1] = (start_x, adjusted[1][1])

        target_anchor = (edge.target_anchor or "").lower()
        if target_anchor in {"left", "right"}:
            adjusted[-2] = (adjusted[-2][0], end_y)
        elif target_anchor in {"top", "bottom"}:
            adjusted[-2] = (end_x, adjusted[-2][1])

        return adjusted

    @staticmethod
    def _extract_route_points(points: list[float]) -> list[tuple[float, float]]:
        if len(points) <= 4:
            return []
        route_points: list[tuple[float, float]] = []
        for i in range(2, len(points) - 2, 2):
            route_points.append((points[i], points[i + 1]))
        return route_points

    def _orthogonalize_points(self, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(points) <= 2:
            return points

        epsilon = 1e-3
        normalized: list[tuple[float, float]] = [points[0]]
        for next_x, next_y in points[1:]:
            cur_x, cur_y = normalized[-1]
            if abs(next_x - cur_x) <= epsilon and abs(next_y - cur_y) <= epsilon:
                continue
            if abs(next_x - cur_x) <= epsilon or abs(next_y - cur_y) <= epsilon:
                normalized.append((next_x, next_y))
                continue

            if len(normalized) >= 2:
                prev_x, prev_y = normalized[-2]
                prev_is_horizontal = abs(cur_y - prev_y) <= abs(cur_x - prev_x)
                mid = (next_x, cur_y) if prev_is_horizontal else (cur_x, next_y)
            else:
                mid = (next_x, cur_y) if abs(next_x - cur_x) >= abs(next_y - cur_y) else (cur_x, next_y)

            if abs(mid[0] - cur_x) > epsilon or abs(mid[1] - cur_y) > epsilon:
                normalized.append(mid)
            normalized.append((next_x, next_y))

        return self._simplify_polyline_points(normalized)

    @staticmethod
    def _simplify_polyline_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(points) <= 2:
            return points

        epsilon = 1e-3
        compact: list[tuple[float, float]] = []
        for x, y in points:
            if compact and abs(compact[-1][0] - x) <= epsilon and abs(compact[-1][1] - y) <= epsilon:
                continue
            compact.append((x, y))

        changed = True
        while changed and len(compact) > 2:
            changed = False
            refined = [compact[0]]
            for i in range(1, len(compact) - 1):
                prev_x, prev_y = refined[-1]
                cur_x, cur_y = compact[i]
                next_x, next_y = compact[i + 1]
                same_x = abs(prev_x - cur_x) <= epsilon and abs(cur_x - next_x) <= epsilon
                same_y = abs(prev_y - cur_y) <= epsilon and abs(cur_y - next_y) <= epsilon
                if same_x or same_y:
                    changed = True
                    continue
                refined.append((cur_x, cur_y))
            refined.append(compact[-1])
            compact = refined
        return compact

    def _build_snap_candidates(
        self,
        edge: Edge,
        *,
        skip_index: int | None = None,
        include_route_points: bool = True,
    ) -> tuple[list[float], list[float]]:
        source = self.nodes.get(edge.source_id)
        target = self.nodes.get(edge.target_id)
        if not source or not target:
            return [], []

        start_x, start_y, end_x, end_y = self._edge_endpoints(edge, source, target)
        x_candidates = [start_x, end_x, source.x, target.x]
        y_candidates = [start_y, end_y, source.y, target.y]

        for node in self.nodes.values():
            x_candidates.append(node.x)
            y_candidates.append(node.y)

        if include_route_points:
            for idx, (px, py) in enumerate(edge.route_points):
                if skip_index is not None and idx == skip_index:
                    continue
                x_candidates.append(px)
                y_candidates.append(py)

        return x_candidates, y_candidates

    def _snap_value(self, value: float, candidates: list[float]) -> float:
        threshold = self._snap_threshold()
        snapped_value = value
        best_diff = threshold + 1.0

        for candidate in candidates:
            diff = abs(candidate - value)
            if diff <= threshold and diff < best_diff:
                best_diff = diff
                snapped_value = candidate

        grid = self._snap_grid_size()
        if grid > 0:
            grid_candidate = round(value / grid) * grid
            grid_diff = abs(grid_candidate - value)
            if grid_diff <= threshold and grid_diff < best_diff:
                snapped_value = grid_candidate

        return snapped_value

    def _snap_threshold(self) -> float:
        return max(8.0, 12.0 * self.ui_scale * (0.8 + self.zoom_ratio * 0.25))

    def _snap_grid_size(self) -> float:
        return max(12.0, 20.0 * self.ui_scale)

    def _edge_label_position(self, points: list[float]) -> tuple[float, float]:
        if len(points) < 4:
            return 0.0, 0.0

        segments: list[tuple[float, float, float, float, float]] = []
        total_length = 0.0
        for i in range(0, len(points) - 2, 2):
            x1 = points[i]
            y1 = points[i + 1]
            x2 = points[i + 2]
            y2 = points[i + 3]
            length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            if length < 1e-6:
                continue
            segments.append((x1, y1, x2, y2, length))
            total_length += length

        if not segments:
            return points[0], points[1]

        target_length = total_length / 2
        walked = 0.0
        for x1, y1, x2, y2, length in segments:
            if walked + length >= target_length:
                ratio = (target_length - walked) / length
                mx = x1 + (x2 - x1) * ratio
                my = y1 + (y2 - y1) * ratio
                ux = (x2 - x1) / length
                uy = (y2 - y1) / length
                px = -uy
                py = ux
                return mx + px * self.edge_label_offset, my + py * self.edge_label_offset
            walked += length

        x1, y1, x2, y2, length = segments[-1]
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        ux = (x2 - x1) / length
        uy = (y2 - y1) / length
        px = -uy
        py = ux
        return mx + px * self.edge_label_offset, my + py * self.edge_label_offset

    def _resize_node_with_handle(self, node: Node, handle_name: str, pointer_x: float, pointer_y: float) -> bool:
        old_width = node.width
        old_height = node.height

        min_width = max(56.0 * self.ui_scale, 36.0 * self.zoom_ratio)
        min_height = max(36.0 * self.ui_scale, 24.0 * self.zoom_ratio)

        if handle_name == "nw":
            width = max(min_width, (node.x - pointer_x) * 2)
            height = max(min_height, (node.y - pointer_y) * 2)
        elif handle_name == "ne":
            width = max(min_width, (pointer_x - node.x) * 2)
            height = max(min_height, (node.y - pointer_y) * 2)
        elif handle_name == "sw":
            width = max(min_width, (node.x - pointer_x) * 2)
            height = max(min_height, (pointer_y - node.y) * 2)
        else:
            width = max(min_width, (pointer_x - node.x) * 2)
            height = max(min_height, (pointer_y - node.y) * 2)

        node.width = width
        node.height = height
        self._update_node_geometry(node)
        return abs(node.width - old_width) > 1e-6 or abs(node.height - old_height) > 1e-6

    def _refresh_selected_node_resize_handles(self) -> None:
        self._clear_node_resize_handles()
        if not self.selected_node_id:
            return

        node = self.nodes.get(self.selected_node_id)
        if not node or not node.shape_item_id:
            return

        left = node.x - node.width / 2
        top = node.y - node.height / 2
        right = node.x + node.width / 2
        bottom = node.y + node.height / 2
        radius = max(4.0, 4.0 * self.ui_scale * (0.8 + self.zoom_ratio * 0.25))

        handle_specs = {
            "nw": (left, top),
            "ne": (right, top),
            "sw": (left, bottom),
            "se": (right, bottom),
        }
        handle_ids: list[int] = []
        for name, (x, y) in handle_specs.items():
            item_id = self.create_rectangle(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill="#ffffff",
                outline="#2563eb",
                width=max(1, int(round(self.base_line_width * 0.75))),
                tags=("node_resize_handle", node.id),
            )
            self.tag_raise(item_id)
            handle_ids.append(item_id)
            self.node_resize_handle_items[item_id] = (node.id, name)
        self.node_resize_handles_by_node[node.id] = handle_ids

    def _clear_node_resize_handles(self, node_id: str | None = None) -> None:
        if node_id is not None:
            handle_ids = self.node_resize_handles_by_node.pop(node_id, [])
            for item_id in handle_ids:
                self.node_resize_handle_items.pop(item_id, None)
                self.delete(item_id)
            return

        all_handle_ids: list[int] = []
        for _, handle_ids in self.node_resize_handles_by_node.items():
            all_handle_ids.extend(handle_ids)
        self.node_resize_handles_by_node.clear()
        for item_id in all_handle_ids:
            self.node_resize_handle_items.pop(item_id, None)
            self.delete(item_id)

    def _refresh_selected_edge_handles(self) -> None:
        self._clear_edge_handles()
        if not self.selected_edge_id:
            return
        edge = self.edges.get(self.selected_edge_id)
        if not edge or not edge.line_item_id:
            return

        route_points = self._effective_route_points(edge)

        radius = max(4.0, 4.0 * self.ui_scale * (0.8 + self.zoom_ratio * 0.25))
        handles: list[int] = []
        for idx, (x, y) in enumerate(route_points):
            item_id = self.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill="#ffffff",
                outline="#2563eb",
                width=max(1, int(round(self.base_line_width * 0.75))),
                tags=("edge_handle", edge.id),
            )
            handles.append(item_id)
            self.edge_handle_items[item_id] = (edge.id, idx)
            self.tag_raise(item_id)
        if handles:
            self.edge_handles_by_edge[edge.id] = handles

        source = self.nodes.get(edge.source_id)
        target = self.nodes.get(edge.target_id)
        if source and target:
            start_x, start_y, end_x, end_y = self._edge_endpoints(edge, source, target)
            source_handle_id = self.create_rectangle(
                start_x - radius * 1.2,
                start_y - radius * 1.2,
                start_x + radius * 1.2,
                start_y + radius * 1.2,
                fill="#dbeafe",
                outline="#1d4ed8",
                width=max(1, int(round(self.base_line_width * 0.75))),
                tags=("edge_source_handle", edge.id),
            )
            self.edge_source_handle_items[source_handle_id] = edge.id
            self.edge_source_handles_by_edge[edge.id] = source_handle_id
            self.tag_raise(source_handle_id)

            target_handle_id = self.create_rectangle(
                end_x - radius * 1.2,
                end_y - radius * 1.2,
                end_x + radius * 1.2,
                end_y + radius * 1.2,
                fill="#fef3c7",
                outline="#b45309",
                width=max(1, int(round(self.base_line_width * 0.75))),
                tags=("edge_target_handle", edge.id),
            )
            self.edge_target_handle_items[target_handle_id] = edge.id
            self.edge_target_handles_by_edge[edge.id] = target_handle_id
            self.tag_raise(target_handle_id)

    def _clear_edge_handles(self, edge_id: str | None = None) -> None:
        if edge_id is not None:
            handle_ids = self.edge_handles_by_edge.pop(edge_id, [])
            for item_id in handle_ids:
                self.edge_handle_items.pop(item_id, None)
                self.delete(item_id)
            source_handle_id = self.edge_source_handles_by_edge.pop(edge_id, None)
            if source_handle_id is not None:
                self.edge_source_handle_items.pop(source_handle_id, None)
                self.delete(source_handle_id)
            target_handle_id = self.edge_target_handles_by_edge.pop(edge_id, None)
            if target_handle_id is not None:
                self.edge_target_handle_items.pop(target_handle_id, None)
                self.delete(target_handle_id)
            return

        all_handle_ids: list[int] = []
        for _, handle_ids in self.edge_handles_by_edge.items():
            all_handle_ids.extend(handle_ids)
        self.edge_handles_by_edge.clear()
        for item_id in all_handle_ids:
            self.edge_handle_items.pop(item_id, None)
            self.delete(item_id)
        all_source_handle_ids = list(self.edge_source_handles_by_edge.values())
        self.edge_source_handles_by_edge.clear()
        for item_id in all_source_handle_ids:
            self.edge_source_handle_items.pop(item_id, None)
            self.delete(item_id)
        all_target_handle_ids = list(self.edge_target_handles_by_edge.values())
        self.edge_target_handles_by_edge.clear()
        for item_id in all_target_handle_ids:
            self.edge_target_handle_items.pop(item_id, None)
            self.delete(item_id)

    def _apply_zoom(self, factor: float) -> bool:
        old_ratio = self.zoom_ratio
        new_ratio = min(self.max_zoom_ratio, max(self.min_zoom_ratio, old_ratio * factor))
        if abs(new_ratio - old_ratio) < 1e-6:
            self._notify(f"缩放已到边界：{int(round(old_ratio * 100))}%")
            return False

        actual = new_ratio / old_ratio
        center_x = self.canvasx(self.winfo_width() / 2)
        center_y = self.canvasy(self.winfo_height() / 2)

        self.zoom_ratio = new_ratio
        self._refresh_visual_metrics()

        for node in self.nodes.values():
            node.x = center_x + (node.x - center_x) * actual
            node.y = center_y + (node.y - center_y) * actual
            node.width *= actual
            node.height *= actual
            self._update_node_geometry(node)

        for edge in self.edges.values():
            if edge.route_points:
                edge.route_points = [
                    (
                        center_x + (px - center_x) * actual,
                        center_y + (py - center_y) * actual,
                    )
                    for px, py in edge.route_points
                ]
            self._update_edge_geometry(edge)

        self._refresh_scrollregion()
        self._sync_selection_styles()
        self._changed()
        self._notify(f"缩放：{int(round(self.zoom_ratio * 100))}%")
        return True

    def _refresh_visual_metrics(self) -> None:
        self.base_line_width = max(1, int(round(self.line_thickness * self.ui_scale * self.zoom_ratio)))
        self.selected_line_width = self.base_line_width + max(1, int(round(1 * self.ui_scale)))
        font_size = max(7, int(round(self.display_font_size * self.zoom_ratio)))
        self.text_font = (self.display_font_family, font_size)
        self.edge_label_offset = 10.0 * self.ui_scale * (0.75 + self.zoom_ratio * 0.25)

    def _node_sort_key(self, node_id: str) -> tuple[float, float, str]:
        node = self.nodes[node_id]
        return (node.y, node.x, node.id)
