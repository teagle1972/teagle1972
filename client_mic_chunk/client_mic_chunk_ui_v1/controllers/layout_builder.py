from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import BOTH, LEFT, RIGHT, X, Y, ttk
from tkinter.scrolledtext import ScrolledText
try:
    from .ui_widgets import TtlScrolledText
except Exception:
    from ui_widgets import TtlScrolledText

def build_layout(
    self,
    *,
    FlowCanvas,
    FlowEditorPanel,
    UI_FONT_FAMILY: str,
    UI_FONT_SIZE: int,
) -> None:
    bg = "#eaf0f7"
    card_bg = "#ffffff"
    panel_bg = "#f3f7fc"
    sidebar_bg = "#e8f0fa"
    accent = "#0b6fc2"
    accent_hover = "#085c9f"
    danger = "#ef4444"
    danger_hover = "#dc2626"
    soft_bg = "#e5edf8"
    soft_hover = "#d8e3f2"
    border = "#c8d6e5"
    text_primary = "#0f1f35"
    text_secondary = "#4f647e"
    text_muted = "#7a8ea8"

    self.configure(bg=bg)
    style = ttk.Style(self)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=bg, foreground=text_primary)
    style.configure("TLabel", background=bg, foreground=text_primary)
    style.configure("App.TFrame", background=bg)
    style.configure("Card.TFrame", background=card_bg, borderwidth=1, relief="solid", bordercolor=border)
    style.configure("Panel.TFrame", background=panel_bg)
    style.configure("Toolbar.TFrame", background=panel_bg)
    style.configure("Sidebar.TFrame", background=sidebar_bg)
    style.configure("Muted.TLabel", background=panel_bg, foreground=text_muted)
    style.configure("SidebarTitle.TLabel", background=sidebar_bg, foreground=text_secondary)

    style.configure("App.TNotebook", background=bg, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure(
        "App.TNotebook.Tab",
        padding=(12, 4),
        background="#dbe6f3",
        foreground=text_secondary,
        borderwidth=0,
        font=("微软雅黑", 9),
    )
    style.map(
        "App.TNotebook.Tab",
        background=[("selected", accent), ("active", "#cfddef")],
        foreground=[("selected", "#ffffff"), ("active", "#1e293b")],
    )

    style.configure("Section.TLabelframe", background=card_bg, borderwidth=1, relief="solid", bordercolor=border)
    style.configure(
        "Section.TLabelframe.Label",
        background=card_bg,
        foreground="#1e293b",
        font=(UI_FONT_FAMILY, UI_FONT_SIZE, "bold"),
    )
    style.configure("ThinCard.TFrame", background=card_bg, borderwidth=1, relief="flat", bordercolor="#d6e2ef")
    style.configure("ThinSection.TLabelframe", background=card_bg, borderwidth=1, relief="flat", bordercolor="#d6e2ef")
    style.configure(
        "ThinSection.TLabelframe.Label",
        background=card_bg,
        foreground="#1e293b",
        font=(UI_FONT_FAMILY, UI_FONT_SIZE, "bold"),
    )
    style.configure("DarkSection.TLabelframe", background="#0b1220", borderwidth=1, relief="solid")
    style.configure("DarkSection.TLabelframe.Label", background="#0b1220", foreground="#e5e7eb")
    style.configure(
        "TButton",
        padding=(8, 4),
        borderwidth=0,
        relief="flat",
        font=("微软雅黑", 9),
    )
    style.configure("Primary.TButton", background=accent, foreground="#ffffff")
    style.map("Primary.TButton", background=[("active", accent_hover), ("pressed", accent_hover)])
    style.configure("Danger.TButton", background=danger, foreground="#ffffff")
    style.map("Danger.TButton", background=[("active", danger_hover), ("pressed", danger_hover)])
    style.configure("Soft.TButton", background=soft_bg, foreground="#1e293b")
    style.map("Soft.TButton", background=[("active", soft_hover), ("pressed", soft_hover)])
    style.configure("SidebarActive.TButton", background=accent, foreground="#ffffff", padding=(10, 8))
    style.map("SidebarActive.TButton", background=[("active", accent_hover), ("pressed", accent_hover)])
    style.configure("Sidebar.TButton", background=soft_bg, foreground="#223247", padding=(10, 8))
    style.map("Sidebar.TButton", background=[("active", soft_hover), ("pressed", soft_hover)])
    style.configure(
        "TEntry",
        fieldbackground="#ffffff",
        foreground=text_primary,
        bordercolor=border,
        lightcolor=border,
        darkcolor=border,
        padding=(8, 6),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", accent)],
        lightcolor=[("focus", accent)],
        darkcolor=[("focus", accent)],
    )
    style.configure("TRadiobutton", background=panel_bg, foreground=text_secondary, padding=(2, 0))
    style.configure("TCheckbutton", background=panel_bg, foreground=text_secondary, padding=(2, 0))
    profile_font_size = UI_FONT_SIZE
    profile_font = tkfont.Font(family=UI_FONT_FAMILY, size=profile_font_size)
    profile_rowheight = max(24, profile_font.metrics("linespace") + 8)
    style.configure(
        "Profile.Treeview",
        background="#ffffff",
        fieldbackground="#ffffff",
        foreground=text_primary,
        rowheight=profile_rowheight,
        borderwidth=0,
        relief="flat",
        font=(UI_FONT_FAMILY, profile_font_size),
    )
    style.configure(
        "Profile.Treeview.Heading",
        background="#e2e8f0",
        foreground="#0f172a",
        relief="flat",
        font=(UI_FONT_FAMILY, profile_font_size, "bold"),
        padding=(10, 8),
    )
    style.map(
        "Profile.Treeview",
        background=[("selected", "#dbeafe")],
        foreground=[("selected", "#0f172a")],
    )
    style.map("Profile.Treeview.Heading", background=[("active", "#dbe5f4")])
    style.layout("Profile.Treeview.Heading", [])
    # ── Unified vertical scrollbar style ─────────────────────────────────
    style.configure(
        "App.Vertical.TScrollbar",
        gripcount=0,
        background="#b8c8db",
        darkcolor="#b8c8db",
        lightcolor="#b8c8db",
        troughcolor="#e8f0fa",
        bordercolor="#e8f0fa",
        arrowcolor="#7a8ea8",
        relief="flat",
        width=10,
        arrowsize=10,
    )
    style.map(
        "App.Vertical.TScrollbar",
        background=[("active", "#0b6fc2"), ("pressed", "#085c9f"), ("disabled", "#dce6f0")],
    )
    style.configure(
        "CallRecord.Treeview",
        background="#ffffff",
        fieldbackground="#ffffff",
        foreground=text_primary,
        rowheight=profile_rowheight,
        borderwidth=0,
        relief="flat",
        font=(UI_FONT_FAMILY, profile_font_size),
    )
    style.configure(
        "CallRecord.Treeview.Heading",
        background="#dbe6f3",
        foreground="#0f172a",
        relief="flat",
        font=(UI_FONT_FAMILY, profile_font_size, "bold"),
        padding=(10, 8),
    )
    style.map(
        "CallRecord.Treeview",
        background=[("selected", "#dbeafe")],
        foreground=[("selected", "#0f172a")],
    )
    style.map("CallRecord.Treeview.Heading", background=[("active", "#cfddef")])

    root = ttk.Frame(self, style="App.TFrame", padding=(0, 0, 0, 0))
    root.pack(fill=BOTH, expand=True)

    body = ttk.Frame(root, style="App.TFrame")
    body.pack(fill=BOTH, expand=True)

    notebook = ttk.Notebook(body, style="App.TNotebook")
    notebook.pack(fill=BOTH, expand=True)
    self._main_notebook = notebook

    settings_tab = ttk.Frame(notebook, style="App.TFrame")
    flow_tab = ttk.Frame(notebook, style="App.TFrame")
    flow_editor_tab = ttk.Frame(notebook, style="App.TFrame")
    conversation_tab = ttk.Frame(notebook, style="App.TFrame")
    timelog_tab = ttk.Frame(notebook, style="App.TFrame")
    notebook.add(settings_tab, text="设置")
    notebook.add(flow_tab, text="Flow")
    notebook.add(flow_editor_tab, text="流程编辑")
    notebook.add(conversation_tab, text="催收")
    notebook.add(timelog_tab, text="Time log")
    notebook.select(conversation_tab)
    notebook.bind("<ButtonPress-1>", self._on_main_notebook_tab_click, add="+")
    notebook.bind("<<NotebookTabChanged>>", self._on_main_notebook_tab_changed, add="+")

    settings_shell = ttk.Frame(settings_tab, style="Card.TFrame", padding=0)
    settings_shell.pack(fill=BOTH, expand=True, padx=0, pady=0)

    settings_controls = ttk.Frame(settings_shell, style="Toolbar.TFrame", padding=(12, 8, 12, 8))
    settings_controls.pack(fill=X, pady=(0, 10))
    create_tab_wrap = ttk.Frame(settings_controls, style="Panel.TFrame")
    create_tab_wrap.pack(side=LEFT, fill=X, expand=True)
    ttk.Label(create_tab_wrap, text="新对话TAB:", background=panel_bg, foreground="#334155").pack(side=LEFT)
    ttk.Entry(create_tab_wrap, textvariable=self.create_conversation_tab_name_var, width=20).pack(
        side=LEFT, padx=(6, 6)
    )
    ttk.Button(
        create_tab_wrap,
        text="创建",
        command=self._create_conversation_tab_from_settings,
        style="Primary.TButton",
    ).pack(side=LEFT)
    ttk.Button(
        create_tab_wrap,
        text="网络",
        command=self._request_network_probe_from_settings,
        style="Soft.TButton",
    ).pack(side=RIGHT)
    ttk.Button(
        create_tab_wrap,
        text="Whoami",
        command=self._request_whoami_from_settings,
        style="Soft.TButton",
    ).pack(side=RIGHT, padx=(6, 0))

    settings_split = ttk.Panedwindow(settings_shell, orient=tk.VERTICAL)
    settings_split.pack(fill=BOTH, expand=True)

    tab_registry_panel = ttk.Frame(settings_split, style="Card.TFrame")
    tab_registry_box = ttk.Frame(tab_registry_panel, style="Panel.TFrame")
    tab_registry_box.pack(fill=BOTH, expand=True)
    tab_registry_toolbar = ttk.Frame(tab_registry_box, style="Panel.TFrame")
    tab_registry_toolbar.pack(fill=X, pady=(0, 6))
    ttk.Button(
        tab_registry_toolbar,
        text="删除选中TAB",
        command=self._delete_selected_conversation_tab_from_settings,
        style="Danger.TButton",
    ).pack(side=LEFT)
    ttk.Button(
        tab_registry_toolbar,
        text="刷新列表",
        command=self._refresh_conversation_tab_registry_view,
        style="Soft.TButton",
    ).pack(side=LEFT, padx=(8, 0))
    tab_registry_wrap = ttk.Frame(tab_registry_box, style="Panel.TFrame")
    tab_registry_wrap.pack(fill=BOTH, expand=True)
    tab_registry_wrap.columnconfigure(0, weight=1)
    tab_registry_wrap.rowconfigure(0, weight=1)
    self._conversation_tab_registry_tree = ttk.Treeview(
        tab_registry_wrap,
        columns=("tab_name", "data_dir"),
        show="headings",
        style="CallRecord.Treeview",
    )
    self._conversation_tab_registry_tree.heading("tab_name", text="TAB名称")
    self._conversation_tab_registry_tree.heading("data_dir", text="数据目录")
    self._conversation_tab_registry_tree.column("tab_name", width=220, anchor="w", stretch=False)
    self._conversation_tab_registry_tree.column("data_dir", width=780, anchor="w", stretch=True)
    tab_registry_scroll_y = ttk.Scrollbar(
        tab_registry_wrap,
        orient=tk.VERTICAL,
        command=self._conversation_tab_registry_tree.yview,
        style="App.Vertical.TScrollbar",
    )
    self._conversation_tab_registry_tree.configure(yscrollcommand=tab_registry_scroll_y.set)
    self._conversation_tab_registry_tree.grid(row=0, column=0, sticky="nsew")
    tab_registry_scroll_y.grid(row=0, column=1, sticky="ns")

    settings_main = ttk.Frame(settings_split, style="App.TFrame")
    settings_main.columnconfigure(0, weight=1)
    settings_main.rowconfigure(0, weight=1)
    settings_split.add(tab_registry_panel, weight=1)
    settings_split.add(settings_main, weight=3)
    self.after_idle(lambda: settings_split.sashpos(0, 230))

    config_canvas_wrap = ttk.Frame(settings_main, style="App.TFrame")
    config_canvas_wrap.grid(row=0, column=0, sticky="nsew")
    config_canvas_wrap.columnconfigure(0, weight=1)
    config_canvas_wrap.rowconfigure(0, weight=1)
    config_canvas = tk.Canvas(config_canvas_wrap, bg=bg, highlightthickness=0, bd=0, relief="flat")
    config_scroll_y = ttk.Scrollbar(config_canvas_wrap, orient=tk.VERTICAL, command=config_canvas.yview, style="App.Vertical.TScrollbar")
    config_canvas.configure(yscrollcommand=config_scroll_y.set)
    config_canvas.grid(row=0, column=0, sticky="nsew")
    config_scroll_y.grid(row=0, column=1, sticky="ns")
    config_container = ttk.Frame(config_canvas, style="App.TFrame")
    config_window_id = config_canvas.create_window((0, 0), window=config_container, anchor="nw")
    config_container.bind("<Configure>", lambda _event: config_canvas.configure(scrollregion=config_canvas.bbox("all")))
    config_canvas.bind(
        "<Configure>",
        lambda event: config_canvas.itemconfigure(
            config_window_id,
            width=max(1, int(getattr(event, "width", 0) or config_canvas.winfo_width() or 1)),
        ),
    )
    def _on_config_mousewheel(event=None) -> str | None:
        if event is None:
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        if delta == 0:
            mouse_num = int(getattr(event, "num", 0) or 0)
            if mouse_num == 4:
                delta = 120
            elif mouse_num == 5:
                delta = -120
        if delta == 0:
            return None
        step = max(1, int(abs(delta) / 120))
        config_canvas.yview_scroll(-step if delta > 0 else step, "units")
        return "break"
    config_canvas.bind("<MouseWheel>", _on_config_mousewheel, add="+")
    config_canvas.bind("<Button-4>", _on_config_mousewheel, add="+")
    config_canvas.bind("<Button-5>", _on_config_mousewheel, add="+")
    config_container.bind("<MouseWheel>", _on_config_mousewheel, add="+")
    config_container.bind("<Button-4>", _on_config_mousewheel, add="+")
    config_container.bind("<Button-5>", _on_config_mousewheel, add="+")
    config_box = ttk.LabelFrame(
        config_container,
        text="参数配置（启动项 + ASR/AEC关键参数）",
        style="Section.TLabelframe",
        padding=(10, 8),
    )
    config_box.pack(fill=BOTH, expand=True)
    config_box.columnconfigure(1, weight=1)
    config_row = 0

    ttk.Label(config_box, text="固定启动命令", background=card_bg, foreground="#334155").grid(
        row=config_row, column=0, sticky="w", padx=(0, 8), pady=(0, 6)
    )
    ttk.Label(
        config_box,
        text="python mic_chunk_client.py（命令已固定，不需要手动填写）",
        background=card_bg,
        foreground="#475569",
    ).grid(row=config_row, column=1, sticky="w", pady=(0, 6))
    config_row += 1

    startup_opts = ttk.Frame(config_box, style="Panel.TFrame")
    startup_opts.grid(row=config_row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    ttk.Checkbutton(
        startup_opts,
        text="启用 Strict WebRTC 预检",
        variable=self.strict_webrtc_required_var,
        style="TCheckbutton",
    ).pack(side=LEFT)
    ttk.Label(startup_opts, text="AEC模式", background=panel_bg, foreground="#334155").pack(side=LEFT, padx=(16, 6))
    profile_combo = ttk.Combobox(
        startup_opts,
        textvariable=self.aec_profile_var,
        values=("asr_first", "aggressive"),
        width=16,
        state="readonly",
    )
    profile_combo.pack(side=LEFT)
    config_row += 1

    ttk.Separator(config_box, orient="horizontal").grid(row=config_row, column=0, columnspan=2, sticky="ew", pady=(2, 8))
    config_row += 1

    parameter_rows = (
        ("chunk_ms", "分片时长", "ms", "10 ~ 60", "麦克风音频切片长度；越小响应越快，但CPU和网络开销更高。"),
        ("queue_size", "队列容量", "chunks", "64 ~ 512", "发送队列缓存上限；过小易丢包，过大增加堆积时延。"),
        ("aec_ref_delay_ms", "AEC参考延迟", "ms", "0 ~ 500", "扬声器参考信号相对麦克风的延迟补偿，影响回声对齐精度。"),
        ("aec_max_suppress_gain", "最大抑制增益", "ratio", "1.0 ~ 3.0", "回声抑制强度上限；过大可能误伤人声。"),
        ("aec_near_end_protect_ratio", "近端保护比", "ratio", "1.0 ~ 1.5", "保护近端说话人语音不被过度抑制，值越大保护越强。"),
        ("aec_tts_warmup_mute_ms", "TTS起播静音窗口", "ms", "0 ~ 300", "TTS刚开始播放时短暂静音窗口，用于稳定AEC初始状态。"),
        ("aec_tts_ref_wait_mute_ms", "参考等待静音窗口", "ms", "200 ~ 3000", "等待参考信号稳定期间的静音时长，降低回声误触发。"),
        ("aec_auto_delay_min_score", "自动延迟最低评分", "ratio", "0.0 ~ 1.0", "自动估计延迟生效的最低相关性评分阈值。"),
        ("aec_search_span_ms", "延迟搜索跨度", "ms", "0 ~ 1000", "自动延迟估计时，围绕当前点搜索的时间范围。"),
        ("aec_auto_delay_interval_chunks", "自动延迟更新间隔", "chunks", "1 ~ 32", "每隔多少个音频分片执行一次自动延迟更新。"),
        ("aec_adapt_alpha", "延迟自适应平滑系数", "ratio", "0.0 ~ 1.0", "新估计延迟与历史延迟融合权重；越大跟随越快。"),
        ("aec_ref_min_rms", "参考信号最小能量", "rms", "0 ~ 5000", "参考信号能量低于阈值时，不执行自动延迟更新。"),
    )
    for key, title, unit, limit_text, desc_text in parameter_rows:
        value_var = getattr(self, f"audio_{key}_var", None)
        if not isinstance(value_var, tk.StringVar):
            continue
        ttk.Label(config_box, text=f"{title} ({unit})", background=card_bg, foreground="#334155").grid(
            row=config_row, column=0, sticky="w", padx=(0, 8), pady=(0, 6)
        )
        row_wrap = ttk.Frame(config_box, style="App.TFrame")
        row_wrap.grid(row=config_row, column=1, sticky="ew", pady=(0, 6))
        row_wrap.columnconfigure(0, weight=1)
        ttk.Entry(row_wrap, textvariable=value_var).grid(row=0, column=0, sticky="ew")
        ttk.Label(row_wrap, text=f"范围: {limit_text}", background=bg, foreground="#64748b").grid(
            row=0, column=1, sticky="w", padx=(10, 0)
        )
        ttk.Label(
            row_wrap,
            text=desc_text,
            background=bg,
            foreground="#64748b",
            justify="left",
            wraplength=680,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        config_row += 1

    config_action = ttk.Frame(config_box, style="Panel.TFrame")
    config_action.grid(row=config_row, column=0, columnspan=2, sticky="ew", pady=(2, 4))
    ttk.Button(
        config_action,
        text="从当前命令回填",
        command=self._load_audio_config_from_current_command,
        style="Soft.TButton",
    ).pack(side=LEFT)
    ttk.Button(
        config_action,
        text="恢复默认值",
        command=self._reset_audio_config_defaults,
        style="Soft.TButton",
    ).pack(side=LEFT, padx=(8, 0))
    ttk.Button(
        config_action,
        text="应用参数并保存",
        command=self._apply_audio_config_to_commands,
        style="Primary.TButton",
    ).pack(side=LEFT, padx=(8, 0))
    ttk.Button(
        config_action,
        text="仅保存配置",
        command=self._save_audio_config_from_ui,
        style="Soft.TButton",
    ).pack(side=LEFT, padx=(8, 0))
    config_row += 1

    ttk.Label(
        config_box,
        textvariable=self.audio_config_status_var,
        background=card_bg,
        foreground="#0f766e",
    ).grid(row=config_row, column=0, columnspan=2, sticky="w", pady=(2, 0))

    flow_shell = ttk.Frame(flow_tab, style="Card.TFrame", padding=0)
    flow_shell.pack(fill=BOTH, expand=True, padx=0, pady=0)
    flow_toolbar = ttk.Frame(flow_shell, style="Toolbar.TFrame", padding=(12, 10, 12, 10))
    flow_toolbar.pack(fill=X, pady=(0, 10))
    ttk.Button(
        flow_toolbar,
        text="加载流程文件",
        command=self._load_workflow_json_file,
        style="Primary.TButton",
    ).pack(side=LEFT)
    ttk.Button(
        flow_toolbar,
        text="清空",
        command=self._clear_loaded_workflow_json,
        style="Soft.TButton",
    ).pack(side=LEFT, padx=(8, 0))
    ttk.Button(
        flow_toolbar,
        text="放大",
        command=self._flow_monitor_zoom_in,
        style="Soft.TButton",
    ).pack(side=LEFT, padx=(8, 0))
    ttk.Button(
        flow_toolbar,
        text="缩小",
        command=self._flow_monitor_zoom_out,
        style="Soft.TButton",
    ).pack(side=LEFT, padx=(8, 0))
    ttk.Button(
        flow_toolbar,
        text="重置",
        command=self._flow_monitor_zoom_reset,
        style="Soft.TButton",
    ).pack(side=LEFT, padx=(8, 0))
    ttk.Checkbutton(
        flow_toolbar,
        text="显示脚本",
        variable=self.flow_show_script_var,
        command=self._toggle_flow_script_panel,
        style="TCheckbutton",
    ).pack(side=LEFT, padx=(12, 0))
    ttk.Label(flow_toolbar, text="文件:", background=panel_bg, foreground="#334155").pack(side=LEFT, padx=(18, 4))
    ttk.Label(flow_toolbar, textvariable=self.flow_path_var, background=panel_bg, foreground="#475569").pack(
        side=LEFT, fill=X, expand=True
    )

    flow_status = ttk.Frame(flow_shell, style="Toolbar.TFrame", padding=(12, 7, 12, 7))
    flow_status.pack(fill=X, pady=(0, 10))
    ttk.Label(flow_status, textvariable=self.flow_summary_var, background=panel_bg, foreground="#0f766e").pack(
        anchor="w"
    )

    flow_panes = ttk.Panedwindow(flow_shell, orient=tk.HORIZONTAL)
    flow_panes.pack(fill=BOTH, expand=True)
    self.flow_panes = flow_panes

    flow_graph_box = ttk.LabelFrame(flow_panes, text="流程图监控", style="Section.TLabelframe", padding=0)
    flow_graph_wrap = ttk.Frame(flow_graph_box, style="Panel.TFrame")
    flow_graph_wrap.pack(fill=BOTH, expand=True)
    flow_graph_wrap.columnconfigure(0, weight=1)
    flow_graph_wrap.rowconfigure(0, weight=1)
    self.flow_monitor_canvas = FlowCanvas(
        flow_graph_wrap,
        ui_scale=1.0,
        font_family=UI_FONT_FAMILY,
        font_size=UI_FONT_SIZE,
    )
    self.flow_monitor_canvas.grid(row=0, column=0, sticky="nsew")
    flow_v_scrollbar = ttk.Scrollbar(flow_graph_wrap, orient="vertical", command=self.flow_monitor_canvas.yview, style="App.Vertical.TScrollbar")
    flow_h_scrollbar = ttk.Scrollbar(flow_graph_wrap, orient="horizontal", command=self.flow_monitor_canvas.xview)
    self.flow_monitor_canvas.configure(
        yscrollcommand=flow_v_scrollbar.set,
        xscrollcommand=flow_h_scrollbar.set,
    )
    flow_v_scrollbar.grid(row=0, column=1, sticky="ns")
    flow_h_scrollbar.grid(row=1, column=0, sticky="ew")
    self._lock_flow_monitor_interactions()
    self._bind_flow_monitor_hover_events()
    flow_panes.add(flow_graph_box, weight=3)

    flow_box = ttk.LabelFrame(flow_panes, text="流程JSON", style="Section.TLabelframe", padding=0)
    self.flow_json_box = flow_box
    self.flow_json_text = TtlScrolledText(
        flow_box,
        wrap="none",
        state="disabled",
        bg="#ffffff",
        fg="#111827",
        insertbackground="#111827",
        relief="flat",
        highlightthickness=1,
        highlightbackground="#d7dee8",
    )
    self.flow_json_text.pack(fill=BOTH, expand=True)
    self._set_text_content(self.flow_json_text, "未加载流程文件。点击“加载流程文件”选择 workflow_json。")
    self.flow_json_text.configure(state="disabled")
    self._toggle_flow_script_panel()

    flow_editor_shell = ttk.Frame(flow_editor_tab, style="Card.TFrame", padding=0)
    flow_editor_shell.pack(fill=BOTH, expand=True, padx=0, pady=0)
    self.flow_editor_panel = FlowEditorPanel(flow_editor_shell)
    self.flow_editor_panel.pack(fill=BOTH, expand=True)

    _template_data_dir = self._workspace_dir / "Data" / "_template"
    _template_data_dir.mkdir(parents=True, exist_ok=True)
    self._tab_data_dir_override = _template_data_dir
    template_context = self._build_conversation_tab(
        parent=conversation_tab,
        panel_bg=panel_bg,
        tab_title="催收",
        command_value=self.conversation_command_var.get(),
        env_value=self.conversation_server_env_var.get(),
    )
    self._tab_data_dir_override = None
    self._register_conversation_tab_context(template_context, is_template=True)
    self._bind_conversation_tab_context(template_context.tab_id)
    self._refresh_conversation_tab_registry_view()
    self._load_persisted_conversation_tabs()
    self.intent_text = None
    self.intent_system_text = None
    self.intent_prompt_text = None

    log_shell = ttk.Frame(timelog_tab, style="Card.TFrame", padding=0)
    log_shell.pack(fill=BOTH, expand=True, padx=0, pady=0)
    log_toolbar = ttk.Frame(log_shell, style="Toolbar.TFrame", padding=(12, 8, 12, 8))
    log_toolbar.pack(fill=X)
    ttk.Button(
        log_toolbar,
        text="刷新",
        command=self._refresh_time_log_view,
        style="Soft.TButton",
    ).pack(side=LEFT)
    log_box = ttk.LabelFrame(log_shell, text="Time log", style="DarkSection.TLabelframe", padding=0)
    self.log_text = TtlScrolledText(
        log_box,
        wrap="word",
        state="disabled",
        bg="#0b1220",
        fg="#cbd5e1",
        insertbackground="#e5e7eb",
        relief="flat",
        highlightthickness=1,
        highlightbackground="#1f2937",
    )
    self.log_text.pack(fill=BOTH, expand=True)
    log_box.pack(fill=BOTH, expand=True)
    self._sync_server_env_from_command(self.command_var.get().strip())
    self._apply_server_env_to_command()
    self._sync_conversation_server_env_from_command(self.conversation_command_var.get().strip())
    self._apply_server_env_to_conversation_command()
    self._load_persisted_conversation_tab_snapshots()
    self._start_ui_heartbeat_monitor()

