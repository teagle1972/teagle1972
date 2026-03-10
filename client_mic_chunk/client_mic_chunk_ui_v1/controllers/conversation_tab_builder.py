from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import BOTH, LEFT, RIGHT, X, ttk
from tkinter.scrolledtext import ScrolledText
try:
    from .ui_widgets import TtlScrolledText
except Exception:
    from ui_widgets import TtlScrolledText

def build_conversation_tab(
    self,
    parent: ttk.Frame,
    panel_bg: str,
    tab_title: str,
    command_value: str,
    env_value: str,
    *,
    UI_FONT_FAMILY: str,
    UI_FONT_SIZE: int,
    conversation_tab_context_cls,
):
    ConversationTabContext = conversation_tab_context_cls
    conversation_font = ("微软雅黑", 9)
    header_font = ("微软雅黑", 9)
    style = ttk.Style(self)
    # Double navigation item height via vertical padding.
    style.configure("ConversationSidebar.TButton", font=conversation_font, padding=(10, 16))
    style.configure("ConversationSidebarActive.TButton", font=conversation_font, padding=(10, 16))
    style.configure("ConversationSidebarTitle.TLabel", font=("微软雅黑", 12, "bold"))
    style.configure("ConversationHeader.TLabel", font=header_font)
    style.configure("ConversationHeader.TRadiobutton", font=header_font)
    style.configure("ConversationHeader.Primary.TButton", font=header_font)
    conversation_font_obj = tkfont.Font(family=conversation_font[0], size=conversation_font[1])
    profile_rowheight = max(24, conversation_font_obj.metrics("linespace") + 8)
    call_record_rowheight = max(26, conversation_font_obj.metrics("linespace") + 10)
    heading_padding_y = max(6, int(profile_rowheight * 0.35))
    style.configure("ConversationProfile.Treeview", font=conversation_font, rowheight=profile_rowheight)
    style.configure(
        "ConversationProfile.Treeview.Heading",
        font=("微软雅黑", 9, "bold"),
        padding=(10, heading_padding_y),
    )
    style.configure("ConversationCallRecord.Treeview", font=conversation_font, rowheight=call_record_rowheight)
    style.configure(
        "ConversationCallRecord.Treeview.Heading",
        font=("微软雅黑", 9, "bold"),
        padding=(10, heading_padding_y),
    )
    style.configure("ConversationIntent.Treeview", font=conversation_font, rowheight=max(24, profile_rowheight))
    style.configure(
        "ConversationIntent.Treeview.Heading",
        font=("微软雅黑", 9, "bold"),
        padding=(8, 6),
    )
    style.configure("ConversationBilling.Treeview", font=conversation_font, rowheight=max(24, profile_rowheight))
    style.configure(
        "ConversationBilling.Treeview.Heading",
        font=("微软雅黑", 9, "bold"),
        padding=(8, 6),
    )
    self.conversation_command_var = tk.StringVar(value=(command_value or "").strip())
    fallback_env = (self.server_env_var.get() if isinstance(self.server_env_var, tk.StringVar) else "local")
    env_text = (env_value or fallback_env or "").strip().lower()
    if env_text not in {"local", "public"}:
        env_text = "local"
    self.conversation_server_env_var = tk.StringVar(value=env_text)
    self.call_record_selected_var = tk.StringVar(value="已选记录：-")
    self._call_record_item_by_iid = {}
    self._customer_data_customer_by_iid = {}
    self._customer_data_case_cache_by_name = {}
    self._conversation_strategy_history = []
    self._conversation_customer_profile_history = []
    self._conversation_intent_generator_history = []
    self._customer_data_last_render_key = ""
    self.conversation_strategy_input_text = None
    self._conversation_page_switcher = None
    self.profile_call_btn = None

    def _new_scrolled(
        master: tk.Widget,
        *,
        state: str = "normal",
        wrap: str = "word",
        font: tuple[str, int] | None = None,
    ) -> TtlScrolledText:
        kwargs: dict[str, object] = {
            "wrap": wrap,
            "state": state,
            "font": conversation_font,
            "bg": "#ffffff",
            "fg": "#111827",
            "insertbackground": "#111827",
            "relief": "flat",
            "highlightthickness": 1,
            "highlightbackground": "#d7dee8",
        }
        if font is not None:
            kwargs["font"] = font
        return TtlScrolledText(master, **kwargs)

    conversation_shell = ttk.Frame(parent, style="Card.TFrame", padding=0)
    conversation_shell.pack(fill=BOTH, expand=True, padx=0, pady=0)
    conversation_shell.columnconfigure(0, weight=1)
    conversation_shell.rowconfigure(0, weight=1)

    conversation_h_panes = ttk.Panedwindow(conversation_shell, orient=tk.HORIZONTAL)
    conversation_h_panes.grid(row=0, column=0, sticky="nsew")

    conversation_toolbar = ttk.Frame(conversation_h_panes, style="Sidebar.TFrame", padding=(10, 10, 10, 10))
    conversation_toolbar.columnconfigure(0, weight=1)
    conversation_toolbar.rowconfigure(7, weight=1)
    ttk.Label(
        conversation_toolbar,
        text="页面导航",
        style="ConversationSidebarTitle.TLabel",
        font=("微软雅黑", 12, "bold"),
    ).grid(row=0, column=0, sticky="w", pady=(2, 8))
    ttk.Separator(conversation_toolbar, orient="horizontal").grid(row=1, column=0, sticky="ew", pady=(0, 12))

    conversation_page_wrap = ttk.Frame(conversation_h_panes, style="App.TFrame")
    conversation_page_wrap.columnconfigure(0, weight=1)
    conversation_page_wrap.rowconfigure(0, weight=1)
    conversation_h_panes.add(conversation_toolbar, weight=0)
    conversation_h_panes.add(conversation_page_wrap, weight=1)

    customer_profile_tab = ttk.Frame(conversation_page_wrap, style="App.TFrame")
    workflow_tab = ttk.Frame(conversation_page_wrap, style="App.TFrame")
    call_record_tab = ttk.Frame(conversation_page_wrap, style="App.TFrame")
    customer_data_tab = ttk.Frame(conversation_page_wrap, style="App.TFrame")
    monitor_tab = ttk.Frame(conversation_page_wrap, style="App.TFrame")
    customer_profile_tab.grid(row=0, column=0, sticky="nsew")
    workflow_tab.grid(row=0, column=0, sticky="nsew")
    call_record_tab.grid(row=0, column=0, sticky="nsew")
    customer_data_tab.grid(row=0, column=0, sticky="nsew")
    monitor_tab.grid(row=0, column=0, sticky="nsew")

    customer_profile_tab.columnconfigure(0, weight=1)
    customer_profile_tab.rowconfigure(0, weight=1)
    profile_vertical_panes = ttk.Panedwindow(customer_profile_tab, orient=tk.VERTICAL)
    profile_vertical_panes.grid(row=0, column=0, sticky="nsew")

    dialog_profile_box = ttk.Frame(profile_vertical_panes, style="Card.TFrame", padding=0)
    profile_header = ttk.Frame(dialog_profile_box, style="Panel.TFrame", padding=(8, 6, 8, 6))
    profile_header.pack(fill=X, pady=(0, 6))
    ttk.Label(
        profile_header,
        text="客户画像",
        style="ConversationHeader.TLabel",
        background=panel_bg,
        foreground="#1e293b",
        font=(conversation_font[0], conversation_font[1], "bold"),
    ).pack(side=LEFT)
    conversation_profile_status_var = tk.StringVar(value="stopped | endpoint=-")
    status_wrap = ttk.Frame(profile_header, style="Panel.TFrame")
    status_wrap.pack(side=LEFT, fill=X, expand=True, padx=(12, 4))
    ttk.Label(
        status_wrap,
        text="状态:",
        style="ConversationHeader.TLabel",
        background=panel_bg,
        foreground="#475569",
    ).pack(side=LEFT, padx=(0, 4))
    conversation_profile_status_label = tk.Label(
        status_wrap,
        textvariable=conversation_profile_status_var,
        font=conversation_font,
        bg=panel_bg,
        fg="#dc2626",
        anchor="w",
    )
    conversation_profile_status_label.pack(side=LEFT, fill=X, expand=True)
    profile_call_btn = ttk.Button(
        profile_header,
        text="开始",
        command=self._start_from_conversation_profile,
        style="ConversationHeader.Primary.TButton",
    )
    ttk.Button(
        profile_header,
        text="结束",
        command=self._stop_all_connections,
        style="ConversationHeader.Primary.TButton",
    ).pack(side=RIGHT, padx=(8, 0))
    profile_call_btn.pack(side=RIGHT, padx=(8, 0))
    ttk.Button(
        profile_header,
        text="对话总结",
        command=self._open_dialog_summary_modal,
        style="ConversationHeader.Primary.TButton",
    ).pack(side=RIGHT, padx=(8, 0))
    conversation_env_wrap = ttk.Frame(profile_header, style="Panel.TFrame")
    conversation_env_wrap.pack(side=RIGHT, padx=(8, 4))
    ttk.Radiobutton(
        conversation_env_wrap,
        text="local",
        value="local",
        variable=self.conversation_server_env_var,
        command=self._on_conversation_server_env_changed,
        style="ConversationHeader.TRadiobutton",
    ).pack(side=LEFT)
    ttk.Radiobutton(
        conversation_env_wrap,
        text="public",
        value="public",
        variable=self.conversation_server_env_var,
        command=self._on_conversation_server_env_changed,
        style="ConversationHeader.TRadiobutton",
    ).pack(side=LEFT, padx=(8, 0))

    profile_table_wrap = ttk.Frame(dialog_profile_box, style="Panel.TFrame")
    profile_table_wrap.pack(fill=BOTH, expand=True)
    profile_table_wrap.columnconfigure(0, weight=1)
    profile_table_wrap.rowconfigure(0, weight=1)
    dialog_profile_table = ttk.Treeview(
        profile_table_wrap,
        columns=("field_1", "value_1", "field_2", "value_2", "field_3", "value_3"),
        show=[],
        style="ConversationProfile.Treeview",
    )
    for col in ("field_1", "value_1", "field_2", "value_2", "field_3", "value_3"):
        dialog_profile_table.heading(col, text="")
        dialog_profile_table.column(col, minwidth=110, anchor="w", stretch=True)
    profile_scroll_y = ttk.Scrollbar(profile_table_wrap, orient=tk.VERTICAL, command=dialog_profile_table.yview, style="App.Vertical.TScrollbar")
    dialog_profile_table.configure(yscrollcommand=profile_scroll_y.set)
    dialog_profile_table.grid(row=0, column=0, sticky="nsew")
    profile_scroll_y.grid(row=0, column=1, sticky="ns")
    dialog_profile_table.tag_configure("profile_even", background="#eef1f5", foreground="#0f1f35")
    dialog_profile_table.tag_configure("profile_odd", background="#e6e9ee", foreground="#0f1f35")
    dialog_profile_table.bind("<Configure>", lambda _event, tree=dialog_profile_table: self._resize_profile_table_columns(tree))
    profile_vertical_panes.add(dialog_profile_box, weight=3)

    profile_bottom_panes = ttk.Panedwindow(profile_vertical_panes, orient=tk.HORIZONTAL)
    profile_vertical_panes.add(profile_bottom_panes, weight=2)
    self.after_idle(lambda: self._safe_set_profile_sash(profile_vertical_panes, min_top=160, min_bottom=170, force_initial=True))
    profile_vertical_panes.bind(
        "<Map>",
        lambda _event: self.after_idle(
            lambda: self._safe_set_profile_sash(
                profile_vertical_panes,
                min_top=160,
                min_bottom=170,
                force_initial=True,
            )
        ),
        add="+",
    )
    profile_vertical_panes.bind(
        "<Configure>",
        lambda _event: self.after_idle(lambda: self._safe_set_profile_sash(profile_vertical_panes, min_top=160, min_bottom=170)),
    )

    dialog_conversation_box = ttk.LabelFrame(profile_bottom_panes, text="客户与坐席对话", style="Section.TLabelframe", padding=0)
    dialog_conversation_text = _new_scrolled(dialog_conversation_box, state="normal")
    dialog_conversation_text.pack(fill=BOTH, expand=True)
    dialog_conversation_text.tag_configure(
        "dialog_customer",
        foreground="#2563eb",
        justify="left",
        lmargin1=8,
        lmargin2=8,
        rmargin=130,
        spacing1=3,
        spacing3=3,
    )
    dialog_conversation_text.tag_configure(
        "dialog_agent",
        foreground="#b45309",
        justify="left",
        lmargin1=130,
        lmargin2=130,
        rmargin=8,
        spacing1=3,
        spacing3=3,
    )
    dialog_conversation_text.tag_configure(
        "dialog_meta",
        foreground="#6b7280",
        justify="left",
        lmargin1=8,
        lmargin2=8,
        rmargin=8,
        spacing1=3,
        spacing3=3,
    )
    dialog_conversation_text.tag_configure(
        "dialog_customer_history",
        foreground="#7898c0",
        background="#f3f4f6",
        justify="left",
        lmargin1=8,
        lmargin2=8,
        rmargin=130,
        spacing1=3,
        spacing3=3,
    )
    dialog_conversation_text.tag_configure(
        "dialog_agent_history",
        foreground="#9c7850",
        background="#f3f4f6",
        justify="left",
        lmargin1=130,
        lmargin2=130,
        rmargin=8,
        spacing1=3,
        spacing3=3,
    )
    dialog_conversation_text.tag_configure(
        "dialog_meta_history",
        foreground="#9ca3af",
        background="#f3f4f6",
        justify="left",
        lmargin1=8,
        lmargin2=8,
        rmargin=8,
        spacing1=3,
        spacing3=3,
    )
    dialog_conversation_text.tag_configure("dialog_intent_inline", foreground="#dc2626")
    dialog_conversation_text.tag_configure(
        "dialog_session_sep",
        foreground="#f97316",
        background="#e5e7eb",
        justify="center",
        lmargin1=0,
        lmargin2=0,
        rmargin=0,
        spacing1=6,
        spacing3=6,
    )
    dialog_conversation_text.tag_configure(
        "dialog_session_marker",
        foreground="#000000",
        background="#e5e7eb",
        justify="center",
        lmargin1=0,
        lmargin2=0,
        rmargin=0,
        spacing1=6,
        spacing3=6,
    )

    dialog_intent_box = ttk.LabelFrame(profile_bottom_panes, text="客户意图", style="Section.TLabelframe", padding=0)
    dialog_intent_container = ttk.Frame(dialog_intent_box)
    dialog_intent_container.pack(fill=BOTH, expand=True)
    dialog_intent_container.rowconfigure(0, weight=3)
    dialog_intent_container.rowconfigure(1, weight=2)
    dialog_intent_container.columnconfigure(0, weight=1)

    dialog_intent_table_wrap = ttk.Frame(dialog_intent_container)
    dialog_intent_table_wrap.grid(row=0, column=0, sticky="nsew")
    dialog_intent_table_wrap.rowconfigure(0, weight=1)
    dialog_intent_table_wrap.columnconfigure(0, weight=1)
    dialog_intent_table = ttk.Treeview(
        dialog_intent_table_wrap,
        columns=("idx", "intent"),
        show="headings",
        style="ConversationIntent.Treeview",
    )
    dialog_intent_table.heading("idx", text="#")
    dialog_intent_table.heading("intent", text="客户意图")
    dialog_intent_table.column("idx", width=44, minwidth=40, stretch=False, anchor="center")
    dialog_intent_table.column("intent", width=240, minwidth=180, stretch=True, anchor="w")
    dialog_intent_scroll_y = ttk.Scrollbar(
        dialog_intent_table_wrap,
        orient=tk.VERTICAL,
        command=dialog_intent_table.yview,
        style="App.Vertical.TScrollbar",
    )
    dialog_intent_table.configure(yscrollcommand=dialog_intent_scroll_y.set)
    dialog_intent_table.grid(row=0, column=0, sticky="nsew")
    dialog_intent_scroll_y.grid(row=0, column=1, sticky="ns")
    dialog_intent_table.tag_configure("intent_even", background="#f7f9fc", foreground="#0f1f35")
    dialog_intent_table.tag_configure("intent_odd", background="#eef3fb", foreground="#0f1f35")
    dialog_intent_table.tag_configure("intent_empty", background="#f8fafc", foreground="#64748b")

    # Hidden legacy buffer for compatibility with existing snapshot/summary logic.
    dialog_intent_text = _new_scrolled(dialog_intent_container, state="disabled")
    dialog_intent_text.grid(row=0, column=0, sticky="nsew")
    dialog_intent_text.grid_remove()

    dialog_billing_box = ttk.LabelFrame(dialog_intent_container, text="计费信息", style="Section.TLabelframe", padding=0)
    dialog_billing_box.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
    dialog_billing_wrap = ttk.Frame(dialog_billing_box)
    dialog_billing_wrap.pack(fill=BOTH, expand=True)
    dialog_billing_wrap.rowconfigure(0, weight=1)
    dialog_billing_wrap.columnconfigure(0, weight=1)
    dialog_billing_table = ttk.Treeview(
        dialog_billing_wrap,
        columns=("item", "value"),
        show="headings",
        style="ConversationBilling.Treeview",
    )
    dialog_billing_table.heading("item", text="项目")
    dialog_billing_table.heading("value", text="数值")
    dialog_billing_table.column("item", width=180, minwidth=120, stretch=True, anchor="w")
    dialog_billing_table.column("value", width=180, minwidth=120, stretch=True, anchor="w")
    dialog_billing_scroll_y = ttk.Scrollbar(
        dialog_billing_wrap,
        orient=tk.VERTICAL,
        command=dialog_billing_table.yview,
        style="App.Vertical.TScrollbar",
    )
    dialog_billing_table.configure(yscrollcommand=dialog_billing_scroll_y.set)
    dialog_billing_table.grid(row=0, column=0, sticky="nsew")
    dialog_billing_scroll_y.grid(row=0, column=1, sticky="ns")
    dialog_billing_table.tag_configure("billing_even", background="#f8fafc", foreground="#111827")
    dialog_billing_table.tag_configure("billing_odd", background="#f1f5f9", foreground="#111827")

    def _resize_billing_table_columns(_event=None) -> None:
        try:
            total = int(dialog_billing_table.winfo_width() or 0)
        except Exception:
            total = 0
        if total <= 0:
            return
        half = max(120, int(total / 2) - 2)
        dialog_billing_table.column("item", width=half, minwidth=120, stretch=True)
        dialog_billing_table.column("value", width=half, minwidth=120, stretch=True)

    dialog_billing_table.bind("<Configure>", _resize_billing_table_columns, add="+")

    # Hidden legacy buffer for compatibility.
    dialog_billing_text = _new_scrolled(dialog_billing_box, state="disabled")
    dialog_billing_text.pack(fill=BOTH, expand=False)
    dialog_billing_text.pack_forget()
    dialog_intent_queue_text = None
    dialog_strategy_text = None
    profile_bottom_panes.add(dialog_conversation_box, weight=3)
    profile_bottom_panes.add(dialog_intent_box, weight=1)

    def _safe_set_profile_bottom_sashes(force_initial: bool = False) -> None:
        width = int(profile_bottom_panes.winfo_width() or 0)
        if width <= 0:
            return
        pane_key = str(profile_bottom_panes)
        initialized = getattr(self, "_profile_bottom_sash_initialized", None)
        if not isinstance(initialized, set):
            initialized = set()
            setattr(self, "_profile_bottom_sash_initialized", initialized)
        if (not force_initial) and (pane_key in initialized):
            return
        first = max(120, int(width * 4 / 5))
        try:
            profile_bottom_panes.sashpos(0, first)
        except tk.TclError:
            return
        initialized.add(pane_key)

    self.after_idle(lambda: _safe_set_profile_bottom_sashes(force_initial=True))
    profile_bottom_panes.bind(
        "<Map>",
        lambda _event: self.after_idle(lambda: _safe_set_profile_bottom_sashes(force_initial=True)),
        add="+",
    )

    workflow_tab.columnconfigure(0, weight=1)
    workflow_tab.rowconfigure(0, weight=1)

    # 三行两列布局，直接填充 workflow_tab，无滚动条
    workflow_h_panes = ttk.Panedwindow(workflow_tab, orient=tk.HORIZONTAL)
    workflow_h_panes.grid(row=0, column=0, sticky="nsew")
    workflow_left_panes = ttk.Panedwindow(workflow_h_panes, orient=tk.VERTICAL)
    workflow_right_panes = ttk.Panedwindow(workflow_h_panes, orient=tk.VERTICAL)
    workflow_h_panes.add(workflow_left_panes, weight=1)
    workflow_h_panes.add(workflow_right_panes, weight=1)

    def _new_workflow_panel(
        parent_panes: ttk.Panedwindow,
        *,
        title: str,
        save_command=None,
        generate_command=None,
        save_style: str = "Soft.TButton",
        generate_style: str = "Primary.TButton",
    ) -> ScrolledText:
        panel = ttk.LabelFrame(parent_panes, text="", style="Section.TLabelframe", padding=0)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        header = ttk.Frame(panel, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, background=panel_bg, foreground="#1e293b", font=("微软雅黑", 12, "bold")).grid(
            row=0,
            column=0,
            sticky="w",
        )
        btn_col = 1
        if callable(save_command):
            ttk.Button(header, text="保存", command=save_command, style=save_style).grid(
                row=0,
                column=btn_col,
                sticky="e",
                padx=(4, 4),
            )
            btn_col += 1
        if callable(generate_command):
            ttk.Button(header, text="生成", command=generate_command, style=generate_style).grid(
                row=0,
                column=btn_col,
                sticky="e",
            )
        editor = _new_scrolled(panel, state="normal")
        editor.configure(height=14)
        editor.grid(row=1, column=0, sticky="nsew")
        parent_panes.add(panel, weight=1)
        return editor

    conversation_system_instruction_text = _new_workflow_panel(
        workflow_left_panes,
        title="系统指令",
        save_command=self._save_conversation_system_instruction_from_panel,
        save_style="Primary.TButton",
    )
    self._set_text_content(conversation_system_instruction_text, "")

    conversation_intent_text = _new_workflow_panel(
        workflow_left_panes,
        title="客户意图",
        save_command=self._save_conversation_intent_from_panel,
        generate_command=self._submit_conversation_intent_from_panel,
    )
    self._set_text_content(conversation_intent_text, "")

    conversation_summary_prompt_text = _new_workflow_panel(
        workflow_left_panes,
        title="对话总结提示词",
        save_command=self._save_dialog_summary_prompt_from_panel,
    )
    self._set_text_content(conversation_summary_prompt_text, "")

    conversation_customer_profile_text = _new_workflow_panel(
        workflow_right_panes,
        title="客户个人画像",
        save_command=self._save_conversation_customer_profile_from_panel,
        generate_command=self._submit_conversation_customer_profile_from_panel,
    )
    self._set_text_content(conversation_customer_profile_text, "")

    conversation_strategy_text = _new_workflow_panel(
        workflow_right_panes,
        title="实时对话策略",
        save_command=self._save_conversation_strategy_from_panel,
        generate_command=self._submit_conversation_strategy_from_panel,
    )
    self._set_text_content(conversation_strategy_text, "")

    conversation_strategy_prompt_text = _new_workflow_panel(
        workflow_right_panes,
        title="对话策略提示词",
        save_command=self._save_dialog_strategy_prompt_from_panel,
    )
    self._set_text_content(conversation_strategy_prompt_text, "")

    conversation_strategy_history_text = None
    strategy_input_text = None

    _workflow_sash_initialized = [False]

    def _set_workflow_initial_sashes() -> None:
        if _workflow_sash_initialized[0]:
            return
        w = workflow_h_panes.winfo_width()
        left_h = workflow_left_panes.winfo_height()
        right_h = workflow_right_panes.winfo_height()
        if (w <= 1) or (left_h <= 1) or (right_h <= 1):
            workflow_h_panes.after(60, _set_workflow_initial_sashes)
            return
        _workflow_sash_initialized[0] = True
        try:
            workflow_h_panes.sashpos(0, w // 2)
            workflow_left_panes.sashpos(0, max(160, left_h // 3))
            workflow_left_panes.sashpos(1, max(320, (left_h * 2) // 3))
            workflow_right_panes.sashpos(0, max(160, right_h // 3))
            workflow_right_panes.sashpos(1, max(320, (right_h * 2) // 3))
        except tk.TclError:
            return

    workflow_h_panes.bind("<Map>", lambda _e: workflow_h_panes.after_idle(_set_workflow_initial_sashes), add="+")

    def _on_prompt_templates_edited(_event=None) -> None:
        try:
            summary_text = conversation_summary_prompt_text.get("1.0", "end-1c").strip()
        except Exception:
            summary_text = ""
        try:
            strategy_text_value = conversation_strategy_prompt_text.get("1.0", "end-1c").strip()
        except Exception:
            strategy_text_value = ""
        self._dialog_summary_prompt_template_cache = summary_text or self._dialog_summary_prompt_template_cache
        self._dialog_strategy_prompt_template_cache = strategy_text_value or self._dialog_strategy_prompt_template_cache

    for editor in (conversation_summary_prompt_text, conversation_strategy_prompt_text):
        editor.bind("<KeyRelease>", _on_prompt_templates_edited, add="+")

    for editor in (conversation_system_instruction_text, conversation_intent_text, conversation_customer_profile_text):
        editor.bind("<KeyRelease>", self._on_conversation_workflow_text_edited, add="+")

    call_record_tab.columnconfigure(0, weight=1)
    call_record_tab.rowconfigure(1, weight=1)
    call_record_toolbar = ttk.Frame(call_record_tab, style="Toolbar.TFrame", padding=(10, 8, 10, 8))
    call_record_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))

    call_record_panel = ttk.Frame(call_record_tab, style="Card.TFrame", padding=0)
    call_record_panel.grid(row=1, column=0, sticky="nsew")
    call_record_panel.columnconfigure(0, weight=1)
    call_record_panel.rowconfigure(0, weight=1)
    call_record_panes = ttk.Panedwindow(call_record_panel, orient=tk.HORIZONTAL)
    call_record_panes.grid(row=0, column=0, sticky="nsew")
    call_record_list_box = ttk.LabelFrame(call_record_panes, text="通话记录列表", style="Section.TLabelframe", padding=0)
    call_record_list_box.columnconfigure(0, weight=1)
    call_record_list_box.rowconfigure(0, weight=1)
    call_record_tree = ttk.Treeview(
        call_record_list_box,
        columns=("customer_name", "last_call_time", "call_cost", "billing_duration", "price_per_minute"),
        show="headings",
        style="ConversationCallRecord.Treeview",
    )
    call_record_tree.heading("customer_name", text="客户名称")
    call_record_tree.heading("last_call_time", text="上次通话时间")
    call_record_tree.heading("call_cost", text="通话费用")
    call_record_tree.heading("billing_duration", text="计费时长")
    call_record_tree.heading("price_per_minute", text="价格/分钟")
    call_record_tree.column("customer_name", width=220, minwidth=120, anchor="w", stretch=True)
    call_record_tree.column("last_call_time", width=180, minwidth=120, anchor="w", stretch=True)
    call_record_tree.column("call_cost", width=110, minwidth=90, anchor="e", stretch=True)
    call_record_tree.column("billing_duration", width=100, minwidth=90, anchor="e", stretch=True)
    call_record_tree.column("price_per_minute", width=120, minwidth=100, anchor="e", stretch=True)
    record_scroll_y = ttk.Scrollbar(call_record_list_box, orient=tk.VERTICAL, command=call_record_tree.yview, style="App.Vertical.TScrollbar")
    call_record_tree.configure(yscrollcommand=record_scroll_y.set)
    call_record_tree.grid(row=0, column=0, sticky="nsew")
    record_scroll_y.grid(row=0, column=1, sticky="ns")
    call_record_tree.bind("<<TreeviewSelect>>", self._on_call_record_selected)

    call_record_detail_wrap = ttk.Frame(call_record_panes, style="App.TFrame")
    call_record_detail_panes = ttk.Panedwindow(call_record_detail_wrap, orient=tk.VERTICAL)
    call_record_detail_panes.pack(fill=BOTH, expand=True)
    call_record_summary_box = ttk.LabelFrame(call_record_detail_panes, text="通话总结", style="Section.TLabelframe", padding=0)
    call_record_summary_text = _new_scrolled(call_record_summary_box, state="disabled", font=conversation_font)
    call_record_summary_text.pack(fill=BOTH, expand=True)
    call_record_detail_panes.add(call_record_summary_box, weight=1)
    call_record_commitments_box = ttk.LabelFrame(call_record_detail_panes, text="客户承诺-执行事项", style="Section.TLabelframe", padding=0)
    call_record_commitments_text = _new_scrolled(call_record_commitments_box, state="disabled", font=conversation_font)
    call_record_commitments_text.pack(fill=BOTH, expand=True)
    call_record_detail_panes.add(call_record_commitments_box, weight=1)
    call_record_strategy_box = ttk.LabelFrame(call_record_detail_panes, text="下一步对话策略", style="Section.TLabelframe", padding=0)
    call_record_strategy_text = _new_scrolled(call_record_strategy_box, state="disabled", font=conversation_font)
    call_record_strategy_text.pack(fill=BOTH, expand=True)
    call_record_detail_panes.add(call_record_strategy_box, weight=1)
    call_record_panes.add(call_record_list_box, weight=2)
    call_record_panes.add(call_record_detail_wrap, weight=3)

    customer_data_tab.columnconfigure(0, weight=1)
    customer_data_tab.rowconfigure(1, weight=1)
    customer_data_toolbar = ttk.Frame(customer_data_tab, style="Toolbar.TFrame", padding=(10, 8, 10, 8))
    customer_data_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    ttk.Button(customer_data_toolbar, text="新建客户", command=self._create_new_customer_record_from_jsonl, style="Primary.TButton").pack(side=LEFT)
    customer_data_panel = ttk.Frame(customer_data_tab, style="ThinCard.TFrame", padding=0)
    customer_data_panel.grid(row=1, column=0, sticky="nsew")
    customer_data_panel.columnconfigure(0, weight=1)
    customer_data_panel.rowconfigure(0, weight=1)
    customer_data_panes = ttk.Panedwindow(customer_data_panel, orient=tk.HORIZONTAL)
    customer_data_panes.grid(row=0, column=0, sticky="nsew")
    customer_data_list_box = ttk.LabelFrame(customer_data_panes, text="客户列表", style="ThinSection.TLabelframe", padding=0)
    customer_data_list_box.columnconfigure(0, weight=1)
    customer_data_list_box.rowconfigure(0, weight=1)
    customer_data_record_tree = ttk.Treeview(
        customer_data_list_box,
        columns=("customer_name", "detail_action", "call_action"),
        show=[],
        style="ConversationCallRecord.Treeview",
    )
    customer_data_record_tree.heading("customer_name", text="客户名称")
    customer_data_record_tree.heading("detail_action", text="")
    customer_data_record_tree.heading("call_action", text="")
    customer_data_record_tree.column("customer_name", width=120, anchor="center", stretch=True)
    customer_data_record_tree.column("detail_action", width=120, anchor="center", stretch=True)
    customer_data_record_tree.column("call_action", width=120, anchor="center", stretch=True)
    customer_data_list_scroll_y = ttk.Scrollbar(customer_data_list_box, orient=tk.VERTICAL, command=customer_data_record_tree.yview, style="App.Vertical.TScrollbar")
    customer_data_record_tree.configure(yscrollcommand=customer_data_list_scroll_y.set)
    customer_data_record_tree.grid(row=0, column=0, sticky="nsew")
    customer_data_list_scroll_y.grid(row=0, column=1, sticky="ns")
    customer_data_record_tree.bind("<<TreeviewSelect>>", self._on_customer_data_record_selected)
    customer_data_record_tree.bind("<ButtonRelease-1>", self._on_customer_data_tree_click, add="+")
    customer_data_record_tree.bind("<Double-Button-1>", self._on_customer_data_tree_double_click, add="+")

    customer_data_detail_wrap = ttk.Frame(customer_data_panes, style="App.TFrame")
    customer_data_detail_wrap.columnconfigure(0, weight=1)
    customer_data_detail_wrap.rowconfigure(0, weight=1)
    customer_data_detail_vpanes = ttk.Panedwindow(customer_data_detail_wrap, orient=tk.VERTICAL)
    customer_data_detail_vpanes.grid(row=0, column=0, sticky="nsew")

    # ── 上方窗格：客户画像表格 ──────────────────────────────────────────────
    customer_data_profile_box = ttk.LabelFrame(customer_data_detail_vpanes, text="客户画像", style="ThinSection.TLabelframe", padding=0)
    customer_data_profile_wrap = ttk.Frame(customer_data_profile_box, style="Panel.TFrame")
    customer_data_profile_wrap.pack(fill=BOTH, expand=True)
    customer_data_profile_wrap.columnconfigure(0, weight=1)
    customer_data_profile_wrap.rowconfigure(0, weight=1)
    customer_data_profile_table = ttk.Treeview(
        customer_data_profile_wrap,
        columns=("field_1", "value_1", "field_2", "value_2", "field_3", "value_3"),
        show=[],
        style="ConversationProfile.Treeview",
    )
    for col in ("field_1", "value_1", "field_2", "value_2", "field_3", "value_3"):
        customer_data_profile_table.heading(col, text="")
        customer_data_profile_table.column(col, minwidth=110, anchor="w", stretch=True)
    customer_data_profile_scroll_y = ttk.Scrollbar(customer_data_profile_wrap, orient=tk.VERTICAL, command=customer_data_profile_table.yview, style="App.Vertical.TScrollbar")
    customer_data_profile_table.configure(yscrollcommand=customer_data_profile_scroll_y.set)
    customer_data_profile_table.grid(row=0, column=0, sticky="nsew")
    customer_data_profile_scroll_y.grid(row=0, column=1, sticky="ns")
    customer_data_profile_table.tag_configure("profile_even", background="#eef1f5", foreground="#0f1f35")
    customer_data_profile_table.tag_configure("profile_odd", background="#e6e9ee", foreground="#0f1f35")
    customer_data_profile_table.bind("<Configure>", lambda _event, tree=customer_data_profile_table: self._resize_profile_table_columns(tree))

    # ── 下方窗格：可滚动通话记录区 ────────────────────────────────────────
    customer_data_canvas_frame = ttk.Frame(customer_data_detail_vpanes, style="App.TFrame")
    customer_data_canvas_frame.columnconfigure(0, weight=1)
    customer_data_canvas_frame.rowconfigure(0, weight=1)
    customer_data_calls_canvas = tk.Canvas(customer_data_canvas_frame, bg="#f3f7fc", highlightthickness=0, bd=0, relief="flat")
    customer_data_detail_scroll_y = ttk.Scrollbar(customer_data_canvas_frame, orient=tk.VERTICAL, command=customer_data_calls_canvas.yview, style="App.Vertical.TScrollbar")
    customer_data_calls_canvas.configure(yscrollcommand=customer_data_detail_scroll_y.set)
    customer_data_calls_canvas.grid(row=0, column=0, sticky="nsew")
    customer_data_detail_scroll_y.grid(row=0, column=1, sticky="ns")
    customer_data_calls_container = ttk.Frame(customer_data_calls_canvas, style="Panel.TFrame")
    detail_window_id = customer_data_calls_canvas.create_window((0, 0), window=customer_data_calls_container, anchor="nw")
    customer_data_calls_container.bind("<Configure>", lambda _event: customer_data_calls_canvas.configure(scrollregion=customer_data_calls_canvas.bbox("all")))
    customer_data_calls_canvas.bind(
        "<Configure>",
        lambda event: customer_data_calls_canvas.itemconfigure(
            detail_window_id,
            width=max(1, int(getattr(event, "width", 0) or customer_data_calls_canvas.winfo_width() or 1)),
        ),
    )
    def _on_customer_data_mousewheel(event=None) -> str | None:
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
        customer_data_calls_canvas.yview_scroll(-step if delta > 0 else step, "units")
        return "break"
    customer_data_calls_canvas.bind("<MouseWheel>", _on_customer_data_mousewheel, add="+")
    customer_data_calls_canvas.bind("<Button-4>", _on_customer_data_mousewheel, add="+")
    customer_data_calls_canvas.bind("<Button-5>", _on_customer_data_mousewheel, add="+")
    customer_data_calls_container.bind("<MouseWheel>", _on_customer_data_mousewheel, add="+")
    customer_data_calls_container.bind("<Button-4>", _on_customer_data_mousewheel, add="+")
    customer_data_calls_container.bind("<Button-5>", _on_customer_data_mousewheel, add="+")
    customer_data_calls_box = ttk.Frame(customer_data_calls_container, style="Panel.TFrame", padding=0)
    customer_data_calls_box.pack(fill=BOTH, expand=True, padx=0, pady=0)
    customer_data_call_entries_wrap = ttk.Frame(customer_data_calls_box, style="Panel.TFrame")
    customer_data_call_entries_wrap.pack(fill=BOTH, expand=True)

    customer_data_detail_vpanes.add(customer_data_profile_box, weight=1)
    customer_data_detail_vpanes.add(customer_data_canvas_frame, weight=3)
    self.after_idle(lambda: self._safe_set_profile_sash(customer_data_detail_vpanes, min_top=60, min_bottom=80, force_initial=True))
    customer_data_detail_vpanes.bind(
        "<Map>",
        lambda _event: self.after_idle(
            lambda: self._safe_set_profile_sash(
                customer_data_detail_vpanes,
                min_top=60,
                min_bottom=80,
                force_initial=True,
            )
        ),
        add="+",
    )
    customer_data_detail_vpanes.bind(
        "<Configure>",
        lambda _event: self.after_idle(lambda: self._safe_set_profile_sash(customer_data_detail_vpanes, min_top=60, min_bottom=80)),
    )
    customer_data_panes.add(customer_data_list_box, weight=0)
    customer_data_panes.add(customer_data_detail_wrap, weight=1)
    _customer_data_sash_initialized = [False]

    def _set_customer_data_sash() -> None:
        if _customer_data_sash_initialized[0]:
            return
        total_w = int(customer_data_panes.winfo_width() or 0)
        if total_w <= 0:
            customer_data_panes.after(80, _set_customer_data_sash)
            return
        min_right_w = 320
        target_list_w = max(190, int(total_w * 0.19))
        target_list_w = min(target_list_w, max(220, total_w - min_right_w))
        try:
            customer_data_panes.sashpos(0, target_list_w)
        except tk.TclError:
            return
        _customer_data_sash_initialized[0] = True

    customer_data_panes.bind("<Map>", lambda _event: customer_data_panes.after_idle(_set_customer_data_sash), add="+")
    customer_data_panes.bind("<Configure>", lambda _event: customer_data_panes.after_idle(_set_customer_data_sash), add="+")

    monitor_tab.columnconfigure(0, weight=1)
    monitor_tab.rowconfigure(0, weight=1)
    monitor_shell = ttk.Frame(monitor_tab, style="Card.TFrame", padding=0)
    monitor_shell.grid(row=0, column=0, sticky="nsew")
    monitor_shell.columnconfigure(0, weight=1)
    monitor_shell.rowconfigure(2, weight=1)

    monitor_top = ttk.Frame(monitor_shell, style="Toolbar.TFrame", padding=(12, 10, 12, 10))
    monitor_top.grid(row=0, column=0, sticky="ew")
    ttk.Label(
        monitor_top,
        text="监控页仅显示当前活动对话的运行状态与事件日志。",
        background=panel_bg,
        foreground="#334155",
    ).pack(side=LEFT, fill=X, expand=True)
    ttk.Button(monitor_top, text="Export Events", command=self._export_events, style="Soft.TButton").pack(side=RIGHT)

    monitor_status = ttk.LabelFrame(monitor_shell, text="Status", style="Section.TLabelframe", padding=0)
    monitor_status.grid(row=1, column=0, sticky="ew")
    for col_idx in range(10):
        monitor_status.columnconfigure(col_idx, weight=0)
    for value_col in (1, 3, 5, 7, 9):
        monitor_status.columnconfigure(value_col, weight=1)
    ttk.Label(monitor_status, text="process:").grid(row=0, column=0, sticky="w")
    monitor_process_status_label = tk.Label(
        monitor_status,
        textvariable=self.state_var,
        font=conversation_font,
        bg=panel_bg,
        fg="#dc2626",
        anchor="w",
    )
    monitor_process_status_label.grid(row=0, column=1, sticky="w", padx=(4, 14))
    ttk.Label(monitor_status, text="session_id:").grid(row=0, column=2, sticky="w")
    ttk.Label(monitor_status, textvariable=self.session_id_var).grid(row=0, column=3, sticky="w", padx=(4, 14))
    ttk.Label(monitor_status, text="transport:").grid(row=0, column=4, sticky="w")
    ttk.Label(monitor_status, textvariable=self.transport_var).grid(row=0, column=5, sticky="w", padx=(4, 14))
    ttk.Label(monitor_status, text="channel:").grid(row=0, column=6, sticky="w")
    ttk.Label(monitor_status, textvariable=self.channel_var).grid(row=0, column=7, sticky="w", padx=(4, 14))
    ttk.Label(monitor_status, text="send:").grid(row=0, column=8, sticky="w")
    ttk.Label(monitor_status, textvariable=self.send_stat_var).grid(row=0, column=9, sticky="w")
    ttk.Label(monitor_status, text="endpoint:").grid(row=1, column=0, sticky="w", pady=(6, 0))
    ttk.Label(monitor_status, textvariable=self.endpoint_var).grid(row=1, column=1, columnspan=9, sticky="w", pady=(6, 0))

    monitor_panels = ttk.Panedwindow(monitor_shell, orient=tk.HORIZONTAL)
    monitor_panels.grid(row=2, column=0, sticky="nsew")
    monitor_main_panels = ttk.Panedwindow(monitor_panels, orient=tk.VERTICAL)
    monitor_side_panels = ttk.Panedwindow(monitor_panels, orient=tk.VERTICAL)
    # Keep ASR on the first (left) column so its width is controlled at 1/3.
    monitor_panels.add(monitor_side_panels, weight=1)
    monitor_panels.add(monitor_main_panels, weight=2)

    monitor_tts_box = ttk.LabelFrame(monitor_main_panels, text="TTS Events", style="Section.TLabelframe", padding=0)
    monitor_tts_text = _new_scrolled(monitor_tts_box, state="disabled")
    monitor_tts_text.pack(fill=BOTH, expand=True)
    monitor_tts_text.tag_configure("tts_customer", foreground="#2563eb", justify="right", spacing1=2, spacing3=2)
    monitor_tts_text.tag_configure("tts_agent", foreground="#b45309", justify="left", spacing1=2, spacing3=2)
    monitor_tts_text.tag_configure("tts_meta", foreground="#6b7280", justify="left", spacing1=2, spacing3=2)
    monitor_main_panels.add(monitor_tts_box, weight=1)

    monitor_nlp_box = ttk.LabelFrame(monitor_main_panels, text="NLP Input", style="Section.TLabelframe", padding=0)
    monitor_nlp_input_text = _new_scrolled(monitor_nlp_box, state="disabled")
    monitor_nlp_input_text.pack(fill=BOTH, expand=True)
    monitor_main_panels.add(monitor_nlp_box, weight=1)

    monitor_asr_raw_box = ttk.LabelFrame(monitor_side_panels, text="ASR原始结果", style="Section.TLabelframe", padding=0)
    monitor_asr_raw_text = _new_scrolled(monitor_asr_raw_box, state="disabled")
    monitor_asr_raw_text.tag_configure("asr_nlp", foreground="black")
    monitor_asr_raw_text.tag_configure("asr_no_nlp", foreground="red")
    monitor_asr_raw_text.pack(fill=BOTH, expand=True)
    monitor_side_panels.add(monitor_asr_raw_box, weight=1)

    monitor_latency_box = ttk.LabelFrame(monitor_side_panels, text="耗时监控", style="Section.TLabelframe", padding=0)
    monitor_latency_text = _new_scrolled(monitor_latency_box, state="disabled")
    monitor_latency_text.tag_configure("lat_header", foreground="#6b7280")
    monitor_latency_text.tag_configure("lat_label", foreground="#374151")
    monitor_latency_text.tag_configure("lat_fast", foreground="#16a34a")
    monitor_latency_text.tag_configure("lat_medium", foreground="#d97706")
    monitor_latency_text.tag_configure("lat_slow", foreground="#dc2626")
    monitor_latency_text.tag_configure("lat_total", foreground="#1d4ed8", font=("微软雅黑", 9, "bold"))
    monitor_latency_text.pack(fill=BOTH, expand=True)
    monitor_side_panels.add(monitor_latency_box, weight=1)

    _monitor_sash_initialized = [False]

    def _set_monitor_sashes() -> None:
        if _monitor_sash_initialized[0]:
            return
        width = monitor_panels.winfo_width()
        side_h = monitor_side_panels.winfo_height()
        main_h = monitor_main_panels.winfo_height()
        if (width <= 0) or (side_h <= 0) or (main_h <= 0):
            monitor_panels.after(80, _set_monitor_sashes)
            return
        min_col = 220
        target = int(width * (1.0 / 3.0))
        target = max(min_col, min(target, max(min_col, width - min_col)))
        try:
            monitor_panels.sashpos(0, target)
            monitor_side_panels.sashpos(0, max(120, side_h // 2))
            monitor_main_panels.sashpos(0, max(120, main_h // 2))
        except tk.TclError:
            return
        _monitor_sash_initialized[0] = True

    monitor_panels.bind("<Map>", lambda _event: monitor_panels.after_idle(_set_monitor_sashes))
    monitor_panels.bind("<Configure>", lambda _event: monitor_panels.after_idle(_set_monitor_sashes))

    active_conversation_page = {"name": "profile"}
    nav_button_text_map = {
        "profile": "实时对话",
        "workflow": "工作流程",
        "call_record": "通话记录",
        "customer_data": "客户资料",
        "monitor": "监控",
    }
    nav_selected_bar_color = "#1f4f8a"
    nav_unselected_bar_color = panel_bg

    def _refresh_nav_button_selected_state(selected_page: str) -> None:
        for page_name, btn in nav_button_map.items():
            is_selected = page_name == selected_page
            btn.configure(style="ConversationSidebarActive.TButton" if is_selected else "ConversationSidebar.TButton")
            strip = nav_strip_map.get(page_name)
            if isinstance(strip, tk.Frame):
                strip.configure(bg=nav_selected_bar_color if is_selected else nav_unselected_bar_color)

    def _switch_conversation_page(page: str) -> None:
        if page == "workflow":
            workflow_tab.tkraise()
            _refresh_nav_button_selected_state("workflow")
            active_conversation_page["name"] = "workflow"
            return
        if page == "call_record":
            call_record_tab.tkraise()
            _refresh_nav_button_selected_state("call_record")
            self._load_call_records_into_list()
            active_conversation_page["name"] = "call_record"
            return
        if page == "customer_data":
            customer_data_tab.tkraise()
            _refresh_nav_button_selected_state("customer_data")
            self._load_customer_data_records_into_list()
            active_conversation_page["name"] = "customer_data"
            return
        if page == "monitor":
            monitor_tab.tkraise()
            _refresh_nav_button_selected_state("monitor")
            active_conversation_page["name"] = "monitor"
            return
        customer_profile_tab.tkraise()
        _refresh_nav_button_selected_state("profile")
        active_conversation_page["name"] = "profile"

    nav_strip_map: dict[str, tk.Frame] = {}
    nav_button_map: dict[str, ttk.Button] = {}

    def _create_nav_item(row: int, page_name: str, pady: tuple[int, int] = (0, 8)) -> ttk.Button:
        item_wrap = ttk.Frame(conversation_toolbar, style="Sidebar.TFrame")
        item_wrap.grid(row=row, column=0, sticky="ew", pady=pady)
        item_wrap.columnconfigure(1, weight=1)
        strip = tk.Frame(item_wrap, width=6, bg=nav_unselected_bar_color, bd=0, highlightthickness=0)
        strip.grid(row=0, column=0, sticky="ns")
        btn = ttk.Button(
            item_wrap,
            text=nav_button_text_map.get(page_name, page_name),
            style="ConversationSidebar.TButton",
            command=lambda p=page_name: _switch_conversation_page(p),
        )
        btn.grid(row=0, column=1, sticky="ew")
        nav_strip_map[page_name] = strip
        nav_button_map[page_name] = btn
        return btn

    profile_nav_btn = _create_nav_item(2, "profile", pady=(0, 8))
    workflow_nav_btn = _create_nav_item(3, "workflow", pady=(0, 8))
    call_record_nav_btn = _create_nav_item(4, "call_record", pady=(0, 8))
    customer_data_nav_btn = _create_nav_item(5, "customer_data", pady=(0, 8))
    monitor_nav_btn = _create_nav_item(6, "monitor", pady=(0, 0))
    _switch_conversation_page("profile")

    self.profile_call_btn = profile_call_btn
    self.conversation_profile_status_var = conversation_profile_status_var
    self.conversation_profile_status_label = conversation_profile_status_label
    self.monitor_process_status_label = monitor_process_status_label
    self.dialog_profile_table = dialog_profile_table
    self.asr_text = monitor_asr_raw_text
    self.tts_text = monitor_tts_text
    self.nlp_input_text = monitor_nlp_input_text
    self.latency_text = monitor_latency_text
    self.dialog_conversation_text = dialog_conversation_text
    self.dialog_intent_text = dialog_intent_text
    self.dialog_intent_table = dialog_intent_table
    self.dialog_billing_text = dialog_billing_text
    self.dialog_billing_table = dialog_billing_table
    self.dialog_intent_queue_text = dialog_intent_queue_text
    self.dialog_strategy_text = dialog_strategy_text
    self.conversation_workflow_text = conversation_strategy_text
    self.conversation_strategy_history_text = conversation_strategy_history_text
    self.conversation_strategy_input_text = strategy_input_text
    self.conversation_system_instruction_text = conversation_system_instruction_text
    self.conversation_intent_text = conversation_intent_text
    self.conversation_customer_profile_text = conversation_customer_profile_text
    self.conversation_summary_prompt_text = conversation_summary_prompt_text
    self.conversation_strategy_prompt_text = conversation_strategy_prompt_text
    self.call_record_tree = call_record_tree
    self.call_record_summary_text = call_record_summary_text
    self.call_record_commitments_text = call_record_commitments_text
    self.call_record_strategy_text = call_record_strategy_text
    self.customer_data_record_tree = customer_data_record_tree
    self.customer_data_profile_table = customer_data_profile_table
    self.customer_data_calls_canvas = customer_data_calls_canvas
    self.customer_data_calls_container = customer_data_calls_container
    self.customer_data_call_entries_wrap = customer_data_call_entries_wrap
    self._conversation_page_switcher = _switch_conversation_page

    tab_data_dir = self._get_data_dir()
    self._load_call_records_into_list()
    self._load_customer_data_records_into_list()

    self._conversation_tab_counter += 1
    tab_id = f"conversation_{self._conversation_tab_counter}"
    return ConversationTabContext(
        tab_id=tab_id,
        title=tab_title,
        tab_frame=parent,
        conversation_command_var=self.conversation_command_var,
        conversation_server_env_var=self.conversation_server_env_var,
        conversation_profile_status_var=self.conversation_profile_status_var,
        conversation_profile_status_label=self.conversation_profile_status_label,
        call_record_selected_var=self.call_record_selected_var,
        profile_call_btn=self.profile_call_btn,
        conversation_page_switcher=self._conversation_page_switcher,
        dialog_profile_table=self.dialog_profile_table,
        monitor_asr_text=self.asr_text,
        monitor_tts_text=self.tts_text,
        monitor_nlp_input_text=self.nlp_input_text,
        monitor_latency_text=self.latency_text,
        monitor_process_status_label=self.monitor_process_status_label,
        dialog_conversation_text=self.dialog_conversation_text,
        dialog_intent_text=self.dialog_intent_text,
        dialog_intent_table=self.dialog_intent_table,
        dialog_billing_text=self.dialog_billing_text,
        dialog_billing_table=self.dialog_billing_table,
        dialog_intent_queue_text=self.dialog_intent_queue_text,
        dialog_strategy_text=self.dialog_strategy_text,
        conversation_workflow_text=self.conversation_workflow_text,
        conversation_strategy_history_text=self.conversation_strategy_history_text,
        conversation_strategy_input_text=self.conversation_strategy_input_text,
        conversation_system_instruction_text=self.conversation_system_instruction_text,
        conversation_intent_text=self.conversation_intent_text,
        conversation_customer_profile_text=self.conversation_customer_profile_text,
        conversation_summary_prompt_text=self.conversation_summary_prompt_text,
        conversation_strategy_prompt_text=self.conversation_strategy_prompt_text,
        call_record_tree=self.call_record_tree,
        call_record_summary_text=self.call_record_summary_text,
        call_record_commitments_text=self.call_record_commitments_text,
        call_record_strategy_text=self.call_record_strategy_text,
        customer_data_record_tree=self.customer_data_record_tree,
        customer_data_profile_table=self.customer_data_profile_table,
        customer_data_calls_canvas=self.customer_data_calls_canvas,
        customer_data_calls_container=self.customer_data_calls_container,
        customer_data_call_entries_wrap=self.customer_data_call_entries_wrap,
        call_record_item_by_iid=self._call_record_item_by_iid,
        customer_data_customer_by_iid=self._customer_data_customer_by_iid,
        customer_data_case_cache_by_name=self._customer_data_case_cache_by_name,
        conversation_strategy_history=self._conversation_strategy_history,
        conversation_customer_profile_history=self._conversation_customer_profile_history,
        conversation_intent_generator_history=self._conversation_intent_generator_history,
        dialog_conversation_history_by_customer=self._dialog_conversation_history_by_customer,
        dialog_conversation_active_customer_key=self._dialog_conversation_active_customer_key,
        customer_data_last_render_key=self._customer_data_last_render_key,
        data_dir=tab_data_dir,
        dialog_agent_stream_active=self._dialog_agent_stream_active,
        dialog_agent_stream_content_start=self._dialog_agent_stream_content_start,
        dialog_intent_history=list(getattr(self, "_dialog_intent_history", []) or []),
        dialog_intent_state_by_customer=dict(getattr(self, "_dialog_intent_state_by_customer", {}) or {}),
        current_session_customer_lines=list(getattr(self, "_current_session_customer_lines", []) or []),
    )
