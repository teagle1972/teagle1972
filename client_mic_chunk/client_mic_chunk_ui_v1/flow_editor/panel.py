from __future__ import annotations

import json
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from typing import Callable

from .canvas_view import FlowCanvas
from .models import NodeType
from .storage import load_flowchart, save_flowchart

UI_FONT_FAMILY = "微软雅黑"
UI_FONT_SIZE = 10


class DisplaySettingsDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        font_family: str,
        font_size: int,
        line_thickness: float,
        node_text_color: str,
        edge_text_color: str,
        ui_font: tuple[str, int],
    ) -> None:
        self._ui_font = ui_font
        self._font_family = tk.StringVar(value=font_family)
        self._font_size = tk.StringVar(value=str(font_size))
        self._line_thickness = tk.StringVar(value=f"{line_thickness:.1f}")
        self._node_text_color = tk.StringVar(value=node_text_color)
        self._edge_text_color = tk.StringVar(value=edge_text_color)
        self._font_combo: ttk.Combobox | None = None
        self._node_color_preview: tk.Label | None = None
        self._edge_color_preview: tk.Label | None = None
        super().__init__(parent, title="显示设置")

    def body(self, master: tk.Misc) -> tk.Widget | None:
        master.columnconfigure(1, weight=1)

        ttk.Label(master, text="显示字体", font=self._ui_font).grid(row=0, column=0, sticky="w", padx=(12, 8), pady=(12, 6))
        families = sorted(set(tkfont.families(master.winfo_toplevel())))
        self._font_combo = ttk.Combobox(master, textvariable=self._font_family, values=families, state="readonly", width=26)
        self._font_combo.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 6))

        ttk.Label(master, text="显示字号", font=self._ui_font).grid(row=1, column=0, sticky="w", padx=(12, 8), pady=6)
        ttk.Entry(master, textvariable=self._font_size, width=10).grid(row=1, column=1, sticky="w", padx=(0, 12), pady=6)

        ttk.Label(master, text="线条粗细", font=self._ui_font).grid(row=2, column=0, sticky="w", padx=(12, 8), pady=6)
        ttk.Entry(master, textvariable=self._line_thickness, width=10).grid(row=2, column=1, sticky="w", padx=(0, 12), pady=6)

        ttk.Label(master, text="图元文字颜色", font=self._ui_font).grid(row=3, column=0, sticky="w", padx=(12, 8), pady=6)
        node_color_row = ttk.Frame(master)
        node_color_row.grid(row=3, column=1, sticky="w", padx=(0, 12), pady=6)
        ttk.Entry(node_color_row, textvariable=self._node_text_color, width=14).pack(side=tk.LEFT)
        ttk.Button(node_color_row, text="选择", command=lambda: self._choose_color(self._node_text_color, self._node_color_preview)).pack(side=tk.LEFT, padx=(6, 0))
        self._node_color_preview = tk.Label(node_color_row, width=3, relief="solid", bd=1, bg=self._node_text_color.get())
        self._node_color_preview.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(master, text="连线文字颜色", font=self._ui_font).grid(row=4, column=0, sticky="w", padx=(12, 8), pady=(6, 12))
        edge_color_row = ttk.Frame(master)
        edge_color_row.grid(row=4, column=1, sticky="w", padx=(0, 12), pady=(6, 12))
        ttk.Entry(edge_color_row, textvariable=self._edge_text_color, width=14).pack(side=tk.LEFT)
        ttk.Button(edge_color_row, text="选择", command=lambda: self._choose_color(self._edge_text_color, self._edge_color_preview)).pack(side=tk.LEFT, padx=(6, 0))
        self._edge_color_preview = tk.Label(edge_color_row, width=3, relief="solid", bd=1, bg=self._edge_text_color.get())
        self._edge_color_preview.pack(side=tk.LEFT, padx=(8, 0))
        return self._font_combo

    def apply(self) -> None:
        family = self._font_family.get().strip()
        try:
            font_size = max(7, int(float(self._font_size.get())))
        except Exception:  # noqa: BLE001
            font_size = UI_FONT_SIZE
        try:
            line_thickness = max(1.0, float(self._line_thickness.get()))
        except Exception:  # noqa: BLE001
            line_thickness = 2.0
        self.result = {
            "font_family": family or UI_FONT_FAMILY,
            "font_size": font_size,
            "line_thickness": line_thickness,
            "node_text_color": self._sanitize_color(self._node_text_color.get(), "#111827"),
            "edge_text_color": self._sanitize_color(self._edge_text_color.get(), "#374151"),
        }

    def _choose_color(self, target_var: tk.StringVar, preview_label: tk.Label | None) -> None:
        chosen = colorchooser.askcolor(color=target_var.get(), parent=self)
        if not chosen or not chosen[1]:
            return
        target_var.set(chosen[1])
        if preview_label is not None:
            preview_label.configure(bg=chosen[1])

    @staticmethod
    def _sanitize_color(raw: str, fallback: str) -> str:
        value = str(raw).strip()
        if len(value) == 7 and value.startswith("#"):
            return value
        return fallback


class FlowEditorPanel(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.ui_scale = 1.0
        self.base_font_size = UI_FONT_SIZE
        self.ui_font_size = UI_FONT_SIZE
        self.button_font_size = UI_FONT_SIZE
        self._configure_dpi_ui()


        self.current_file: Path | None = None
        self.dirty = False
        self.palette_drag_type: NodeType | None = None
        self.connect_mode = False
        self.view_mode_var = tk.StringVar(value="diagram")
        self.zoom_ratio_var = tk.StringVar(value="缩放：100%")
        self.loaded_script_text: str | None = None
        self.default_display_settings: dict[str, float | int | str] = {}

        self._build_ui()
        self.default_display_settings = dict(self.canvas.get_display_settings())
        self._bind_shortcuts()
        self._update_title()

    def _configure_dpi_ui(self) -> None:
        dpi = float(self.winfo_fpixels("1i"))
        self.ui_scale = max(1.0, min(2.6, dpi / 96.0))
        self.tk.call("tk", "scaling", self.ui_scale)

        self.base_font_size = UI_FONT_SIZE
        self.ui_font_size = UI_FONT_SIZE
        self.button_font_size = UI_FONT_SIZE

        self.option_add("*Font", (UI_FONT_FAMILY, self.ui_font_size))
        self.option_add("*Menu*Font", (UI_FONT_FAMILY, self.ui_font_size))

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        elif "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure(
            "TButton",
            font=(UI_FONT_FAMILY, self.button_font_size),
            padding=(self._px(3), self._px(1)),
        )
        style.configure("TRadiobutton", font=(UI_FONT_FAMILY, self.button_font_size))
        style.configure("Toolbar.TLabel", font=(UI_FONT_FAMILY, self.button_font_size))
        style.configure("Mode.TLabel", font=(UI_FONT_FAMILY, self.button_font_size))
        style.configure("Mode.TRadiobutton", font=(UI_FONT_FAMILY, self.button_font_size))
        style.configure("Zoom.TLabel", font=(UI_FONT_FAMILY, self.button_font_size))
        self.option_add("*TButton*Font", (UI_FONT_FAMILY, self.button_font_size))
        self.option_add("*TRadiobutton*Font", (UI_FONT_FAMILY, self.button_font_size))
        style.configure("TLabel", font=(UI_FONT_FAMILY, self.ui_font_size))

    def _px(self, value: int | float) -> int:
        return max(1, int(round(float(value) * self.ui_scale)))

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(self._px(4), self._px(3)))
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        toolbar.columnconfigure(15, weight=1)

        btn_pad = self._px(1)
        ttk.Button(toolbar, text="新建", command=self.new_file).grid(row=0, column=0, padx=btn_pad)
        ttk.Button(toolbar, text="打开", command=self.open_file).grid(row=0, column=1, padx=btn_pad)
        ttk.Button(toolbar, text="保存", command=self.save_file).grid(row=0, column=2, padx=btn_pad)
        ttk.Button(toolbar, text="另存为", command=self.save_as_file).grid(row=0, column=3, padx=btn_pad)

        self.connect_btn = ttk.Button(toolbar, text="连线模式: 关", command=self.toggle_connect_mode)
        self.connect_btn.grid(row=0, column=4, padx=(self._px(13), btn_pad))
        ttk.Button(toolbar, text="删除选中", command=self.delete_selected).grid(row=0, column=5, padx=btn_pad)
        ttk.Button(toolbar, text="清空画布", command=self.clear_canvas).grid(row=0, column=6, padx=btn_pad)
        ttk.Button(toolbar, text="放大", command=self.zoom_in).grid(row=0, column=7, padx=(self._px(13), btn_pad))
        ttk.Button(toolbar, text="缩小", command=self.zoom_out).grid(row=0, column=8, padx=btn_pad)
        ttk.Button(toolbar, text="重置缩放", command=self.reset_zoom).grid(row=0, column=9, padx=btn_pad)
        ttk.Button(toolbar, text="自动排版", command=self.auto_layout).grid(row=0, column=10, padx=btn_pad)
        ttk.Button(toolbar, text="显示设置", command=self.open_display_settings).grid(row=0, column=11, padx=btn_pad)
        ttk.Label(toolbar, text="显示模式", style="Mode.TLabel").grid(row=0, column=12, padx=(self._px(13), btn_pad))
        ttk.Radiobutton(
            toolbar,
            text="流程图",
            value="diagram",
            variable=self.view_mode_var,
            style="Mode.TRadiobutton",
            command=self._on_view_mode_changed,
        ).grid(row=0, column=13, padx=btn_pad)
        ttk.Radiobutton(
            toolbar,
            text="文本",
            value="text",
            variable=self.view_mode_var,
            style="Mode.TRadiobutton",
            command=self._on_view_mode_changed,
        ).grid(row=0, column=14, padx=btn_pad)
        ttk.Label(toolbar, textvariable=self.zoom_ratio_var, style="Zoom.TLabel").grid(
            row=0,
            column=16,
            padx=(self._px(16), self._px(6)),
            sticky="e",
        )

        palette = ttk.Frame(self, padding=self._px(10), relief="ridge")
        palette.grid(row=1, column=0, sticky="ns")
        ttk.Label(
            palette,
            text="图元面板",
            font=(UI_FONT_FAMILY, self.ui_font_size, "bold"),
        ).pack(anchor="w", pady=(0, self._px(10)))
        ttk.Label(palette, text="按住并拖动到画布", foreground="#4b5563").pack(anchor="w", pady=(0, self._px(8)))

        for node_type in NodeType:
            lbl = tk.Label(
                palette,
                text=node_type.display_name,
                bg="#ffffff",
                relief="groove",
                bd=2,
                width=6,
                height=1,
                cursor="hand2",
                font=(UI_FONT_FAMILY, self.button_font_size),
            )
            lbl.pack(fill="x", pady=self._px(6))
            lbl.bind("<ButtonPress-1>", lambda e, nt=node_type: self._on_palette_press(e, nt))
            lbl.bind("<B1-Motion>", self._on_palette_motion)
            lbl.bind("<ButtonRelease-1>", self._on_palette_release)

        canvas_wrap = ttk.Frame(self, padding=(0, 0, self._px(8), self._px(8)))
        canvas_wrap.grid(row=1, column=1, sticky="nsew")
        canvas_wrap.columnconfigure(0, weight=1)
        canvas_wrap.rowconfigure(0, weight=1)

        self.diagram_frame = ttk.Frame(canvas_wrap)
        self.diagram_frame.grid(row=0, column=0, sticky="nsew")
        self.diagram_frame.columnconfigure(0, weight=1)
        self.diagram_frame.rowconfigure(0, weight=1)

        self.text_frame = ttk.Frame(canvas_wrap)
        self.text_frame.grid(row=0, column=0, sticky="nsew")
        self.text_frame.columnconfigure(0, weight=1)
        self.text_frame.rowconfigure(0, weight=1)

        self.canvas = FlowCanvas(
            self.diagram_frame,
            ui_scale=self.ui_scale,
            font_family=UI_FONT_FAMILY,
            font_size=self.ui_font_size,
            status_callback=self.set_status,
            changed_callback=self.mark_dirty,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self._update_zoom_ratio_display()

        v_scrollbar = ttk.Scrollbar(self.diagram_frame, orient="vertical", command=self.canvas.yview)
        h_scrollbar = ttk.Scrollbar(self.diagram_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")

        self.text_view = tk.Text(
            self.text_frame,
            wrap="word",
            state="disabled",
            font=(UI_FONT_FAMILY, self.ui_font_size),
            padx=self._px(12),
            pady=self._px(10),
            background="#ffffff",
        )
        self.text_view.grid(row=0, column=0, sticky="nsew")
        text_scrollbar = ttk.Scrollbar(self.text_frame, orient="vertical", command=self.text_view.yview)
        self.text_view.configure(yscrollcommand=text_scrollbar.set)
        text_scrollbar.grid(row=0, column=1, sticky="ns")

        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(
            self,
            textvariable=self.status_var,
            anchor="w",
            padding=(self._px(10), self._px(5)),
        )
        status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")

        self._apply_view_mode()

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="新建", command=self.new_file, accelerator="Ctrl+N")
        file_menu.add_command(label="打开...", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="保存", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="另存为...", command=self.save_as_file, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.on_close)
        menubar.add_cascade(label="文件", menu=file_menu)
        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="显示设置...", command=self.open_display_settings)
        menubar.add_cascade(label="视图", menu=view_menu)
        self.config(menu=menubar)

    def _bind_shortcuts(self) -> None:
        root = self.winfo_toplevel()

        def _guard(action: Callable[[], None]):
            def _handler(_event: tk.Event) -> str | None:
                if not self.winfo_ismapped():
                    return None
                action()
                return "break"
            return _handler

        root.bind("<Control-n>", _guard(self.new_file), add="+")
        root.bind("<Control-o>", _guard(self.open_file), add="+")
        root.bind("<Control-s>", _guard(self.save_file), add="+")
        root.bind("<Control-S>", _guard(self.save_as_file), add="+")
        root.bind("<Control-plus>", _guard(self.zoom_in), add="+")
        root.bind("<Control-equal>", _guard(self.zoom_in), add="+")
        root.bind("<Control-minus>", _guard(self.zoom_out), add="+")
        root.bind("<Control-0>", _guard(self.reset_zoom), add="+")

    def _on_palette_press(self, event: tk.Event, node_type: NodeType) -> None:
        self.palette_drag_type = node_type
        event.widget.configure(bg="#dbeafe")
        self.set_status(f"拖动 {node_type.display_name} 到画布并松开鼠标。")

    def _on_palette_motion(self, _event: tk.Event) -> None:
        if self.palette_drag_type:
            self.winfo_toplevel().configure(cursor="hand2")

    def _on_palette_release(self, event: tk.Event) -> None:
        self.winfo_toplevel().configure(cursor="")
        widget = event.widget
        widget.configure(bg="#ffffff")
        if not self.palette_drag_type:
            return

        pointer_x = widget.winfo_pointerx()
        pointer_y = widget.winfo_pointery()
        in_canvas = (
            self.canvas.winfo_rootx() <= pointer_x <= self.canvas.winfo_rootx() + self.canvas.winfo_width()
            and self.canvas.winfo_rooty() <= pointer_y <= self.canvas.winfo_rooty() + self.canvas.winfo_height()
        )
        if in_canvas:
            cx = self.canvas.canvasx(pointer_x - self.canvas.winfo_rootx())
            cy = self.canvas.canvasy(pointer_y - self.canvas.winfo_rooty())
            self.canvas.add_node(self.palette_drag_type, cx, cy)
            self.set_status(f"已创建：{self.palette_drag_type.display_name}")
        else:
            self.set_status("未拖放到画布，已取消。")
        self.palette_drag_type = None

    def toggle_connect_mode(self) -> None:
        self.connect_mode = not self.connect_mode
        self.canvas.set_connect_mode(self.connect_mode)
        self.connect_btn.configure(text=f"连线模式: {'开' if self.connect_mode else '关'}")

    def delete_selected(self) -> None:
        self.canvas.delete_selected()

    def zoom_in(self) -> None:
        self.canvas.zoom_in()
        self._update_zoom_ratio_display()

    def zoom_out(self) -> None:
        self.canvas.zoom_out()
        self._update_zoom_ratio_display()

    def reset_zoom(self) -> None:
        self.canvas.reset_zoom()
        self._update_zoom_ratio_display()

    def auto_layout(self) -> None:
        self.canvas.auto_layout()

    def open_display_settings(self) -> None:
        current = self.canvas.get_display_settings()
        dialog = DisplaySettingsDialog(
            self,
            font_family=str(current.get("font_family", UI_FONT_FAMILY)),
            font_size=int(current.get("font_size", self.ui_font_size)),
            line_thickness=float(current.get("line_thickness", 2.0)),
            node_text_color=str(current.get("node_text_color", "#111827")),
            edge_text_color=str(current.get("edge_text_color", "#374151")),
            ui_font=(UI_FONT_FAMILY, self.ui_font_size),
        )
        if dialog.result is None:
            return
        payload = dialog.result
        self.canvas.apply_display_settings(
            line_thickness=float(payload["line_thickness"]),
            font_family=str(payload["font_family"]),
            font_size=int(payload["font_size"]),
            node_text_color=str(payload["node_text_color"]),
            edge_text_color=str(payload["edge_text_color"]),
        )
        self.text_view.configure(font=(str(payload["font_family"]), int(payload["font_size"])))
        self.set_status("显示设置已应用。")

    def clear_canvas(self) -> None:
        if not self.canvas.nodes and not self.canvas.edges:
            return
        if not messagebox.askyesno("确认", "确定要清空当前画布吗？", parent=self.winfo_toplevel()):
            return
        self.canvas.clear()
        self._update_zoom_ratio_display()
        self.mark_dirty()
        self.set_status("画布已清空。")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def mark_dirty(self) -> None:
        self.dirty = True
        self._update_title()
        self._refresh_text_view_if_needed()

    def _mark_clean(self) -> None:
        self.dirty = False
        self._update_title()

    def _update_title(self) -> None:
        # Embedded panel should not override the host window title.
        return

    def new_file(self) -> None:
        if not self._confirm_discard_changes():
            return
        self.canvas.clear()
        self._update_zoom_ratio_display()
        self.current_file = None
        self.loaded_script_text = None
        self._mark_clean()
        self._refresh_text_view_if_needed()
        self.set_status("新建文件。")

    def open_file(self) -> None:
        if not self._confirm_discard_changes():
            return
        path = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="打开流程图",
            filetypes=[("Flowchart JSON", "*.flow.json *.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            nodes, edges, display_settings, view_state = load_flowchart(path)
            self.canvas.load_data(nodes, edges)
            self._apply_loaded_display_settings(display_settings)
            self.canvas.apply_view_state(view_state)
            self._update_zoom_ratio_display()
            self.current_file = Path(path)
            self.loaded_script_text = self.current_file.read_text(encoding="utf-8")
            self._mark_clean()
            self._refresh_text_view_if_needed()
            self.set_status(f"已打开：{self.current_file}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("打开失败", f"无法打开文件：\n{exc}", parent=self.winfo_toplevel())

    def save_file(self) -> None:
        if self.current_file is None:
            self.save_as_file()
            return
        self._save_to_path(self.current_file)

    def save_as_file(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="保存流程图",
            defaultextension=".flow.json",
            filetypes=[("Flowchart JSON", "*.flow.json"), ("JSON", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        self._save_to_path(Path(path))

    def _save_to_path(self, path: Path) -> None:
        try:
            save_flowchart(
                path,
                self.canvas.get_nodes(),
                self.canvas.get_edges(),
                self.canvas.get_display_settings(),
                self.canvas.get_view_state(),
            )
            self.current_file = path
            self.loaded_script_text = path.read_text(encoding="utf-8")
            self._mark_clean()
            self._refresh_text_view_if_needed()
            self.set_status(f"已保存：{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", f"无法保存文件：\n{exc}", parent=self.winfo_toplevel())

    def _on_view_mode_changed(self) -> None:
        self._apply_view_mode()

    def _apply_view_mode(self) -> None:
        if self.view_mode_var.get() == "text":
            self.diagram_frame.grid_remove()
            self.text_frame.grid()
            self._refresh_text_view()
            self.set_status("已切换到文本模式。")
            return
        self.text_frame.grid_remove()
        self.diagram_frame.grid()
        self.set_status("已切换到流程图模式。")

    def _refresh_text_view_if_needed(self) -> None:
        if self.view_mode_var.get() == "text":
            self._refresh_text_view()

    def _refresh_text_view(self) -> None:
        script_text = self._get_script_text_for_view()
        self.text_view.configure(state="normal")
        self.text_view.delete("1.0", "end")
        self.text_view.insert("1.0", script_text)
        self.text_view.configure(state="disabled")

    def _get_script_text_for_view(self) -> str:
        if not self.dirty and self.loaded_script_text:
            return self.loaded_script_text
        payload = {
            "version": 1,
            "nodes": [node.to_dict() for node in self.canvas.get_nodes()],
            "edges": [edge.to_dict() for edge in self.canvas.get_edges()],
            "display_settings": self.canvas.get_display_settings(),
            "view_state": self.canvas.get_view_state(),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _apply_loaded_display_settings(self, settings: dict[str, object] | None) -> None:
        merged = dict(self.default_display_settings)
        if settings:
            merged.update(settings)

        default_line_thickness = float(self.default_display_settings.get("line_thickness", 2.0))
        default_node_color = str(self.default_display_settings.get("node_text_color", "#111827"))
        default_edge_color = str(self.default_display_settings.get("edge_text_color", "#374151"))

        font_family = UI_FONT_FAMILY
        font_size = UI_FONT_SIZE
        try:
            line_thickness = max(1.0, float(merged.get("line_thickness", default_line_thickness)))
        except Exception:  # noqa: BLE001
            line_thickness = default_line_thickness
        node_color = str(merged.get("node_text_color", default_node_color)).strip() or default_node_color
        edge_color = str(merged.get("edge_text_color", default_edge_color)).strip() or default_edge_color

        self.canvas.apply_display_settings(
            line_thickness=line_thickness,
            font_family=font_family,
            font_size=font_size,
            node_text_color=node_color,
            edge_text_color=edge_color,
        )
        self.text_view.configure(font=(font_family, font_size))

    def _update_zoom_ratio_display(self) -> None:
        ratio = getattr(self.canvas, "zoom_ratio", 1.0)
        self.zoom_ratio_var.set(f"缩放：{int(round(ratio * 100))}%")

    def _confirm_discard_changes(self) -> bool:
        if not self.dirty:
            return True
        result = messagebox.askyesnocancel(
            "未保存更改",
            "当前内容尚未保存，是否先保存？",
            parent=self.winfo_toplevel(),
        )
        if result is None:
            return False
        if result:
            self.save_file()
            return not self.dirty
        return True

    def on_close(self) -> bool:
        return self._confirm_discard_changes()

    def confirm_close(self) -> bool:
        return self._confirm_discard_changes()
