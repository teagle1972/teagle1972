from __future__ import annotations

from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    from ..services.case_repository import (
        build_visible_customer_record_indices as repo_build_visible_customer_record_indices,
        build_visible_customer_records as repo_build_visible_customer_records,
    )
except Exception:
    from services.case_repository import (
        build_visible_customer_record_indices as repo_build_visible_customer_record_indices,
        build_visible_customer_records as repo_build_visible_customer_records,
    )


_HISTORY_TIME_STYLE_INITIALIZED = False

_PROFILE_SECTION_STOP_MARKERS = (
    "### 通话记录条目 ###",
    "### 通话记录 ###",
    "### 对话总结 ###",
    "### 客户承诺-执行事项 ###",
    "### 下一步对话策略 ###",
)


def ensure_history_time_style() -> None:
    global _HISTORY_TIME_STYLE_INITIALIZED
    if _HISTORY_TIME_STYLE_INITIALIZED:
        return
    _HISTORY_TIME_STYLE_INITIALIZED = True
    style = ttk.Style()
    style.configure(
        "HistoryTime.Treeview",
        font=("Microsoft YaHei", 11),
        rowheight=48,
        background="#f0f4f8",
        foreground="#0f1f35",
        fieldbackground="#f0f4f8",
    )
    style.map(
        "HistoryTime.Treeview",
        background=[("selected", "#2563eb")],
        foreground=[("selected", "#ffffff")],
    )


def record_has_detail_content(entry: dict[str, str]) -> bool:
    if not isinstance(entry, dict):
        return False
    for key in ("summary", "commitments", "strategy", "call_record"):
        if str(entry.get(key, "") or "").strip():
            return True
    return False


def normalize_profile_editor_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        stripped = raw_line.strip()
        if stripped in _PROFILE_SECTION_STOP_MARKERS:
            break
        lines.append(raw_line)
    normalized = "\n".join(lines).strip()
    if normalized.startswith("【客户画像】"):
        normalized = normalized[len("【客户画像】") :].lstrip()
    return normalized


def render_call_record_detail(app, record: dict[str, str], *, log_debug=None) -> None:
    customer_name = record.get("customer_name", "Unknown Customer")
    call_time = record.get("last_call_time", "-")
    call_cost = str(record.get("call_cost", "") or "").strip() or "-"
    billing_duration = str(record.get("billing_duration", "") or "").strip() or "-"
    price_per_minute = str(record.get("price_per_minute", "") or "").strip() or "-"
    if callable(log_debug):
        log_debug(
            "call-record render "
            f"record_id={str(record.get('record_id', '') or '')} "
            f"customer={customer_name} "
            f"time={call_time} "
            f"summary_len={len(str(record.get('summary', '') or ''))} "
            f"commitments_len={len(str(record.get('commitments', '') or ''))} "
            f"strategy_len={len(str(record.get('strategy', '') or ''))}",
        )
    app.call_record_selected_var.set(
        f"Selected: {customer_name} | Time: {call_time} | Cost: {call_cost} | Billing Duration: {billing_duration} | Price/Min: {price_per_minute}"
    )
    summary_widget = app.call_record_summary_text
    commitments_widget = app.call_record_commitments_text
    strategy_widget = app.call_record_strategy_text
    if isinstance(summary_widget, ScrolledText):
        app._set_text_content(summary_widget, record.get("summary", "") or "No content")
        summary_widget.configure(state="disabled")
    if isinstance(commitments_widget, ScrolledText):
        app._set_text_content(commitments_widget, record.get("commitments", "") or "No content")
        commitments_widget.configure(state="disabled")
    if isinstance(strategy_widget, ScrolledText):
        app._set_text_content(strategy_widget, record.get("strategy", "") or "No content")
        strategy_widget.configure(state="disabled")


def clear_call_record_detail(app, message: str = "请选择左侧通话记录") -> None:
    app.call_record_selected_var.set("已选记录：-")
    summary_widget = app.call_record_summary_text
    commitments_widget = app.call_record_commitments_text
    strategy_widget = app.call_record_strategy_text
    if isinstance(summary_widget, ScrolledText):
        app._set_text_content(summary_widget, message)
        summary_widget.configure(state="disabled")
    if isinstance(commitments_widget, ScrolledText):
        app._set_text_content(commitments_widget, message)
        commitments_widget.configure(state="disabled")
    if isinstance(strategy_widget, ScrolledText):
        app._set_text_content(strategy_widget, message)
        strategy_widget.configure(state="disabled")


def apply_call_record_profile_and_workflow(app, record: dict[str, str]) -> None:
    profile_text = str(record.get("customer_profile", "") or "")
    dialog_profile_tree = app.dialog_profile_table
    if isinstance(dialog_profile_tree, ttk.Treeview):
        app._fill_profile_table_from_text(dialog_profile_tree, profile_text=profile_text, auto_height=True)
    if isinstance(app.conversation_customer_profile_text, ScrolledText):
        app._set_text_content(app.conversation_customer_profile_text, profile_text)
    app._refresh_runtime_system_prompt_only()


def clear_customer_data_call_entry_views(app, message: str = "请选择左侧通话记录") -> None:
    text_widget = app.customer_data_call_entries_wrap
    if not isinstance(text_widget, tk.Text):
        return
    text_widget.configure(state="normal")
    text_widget.delete("1.0", "end")
    text_widget.insert("end", message, "section_body")
    text_widget.configure(state="disabled")


def clear_customer_data_profile_table(app, message: str = "请选择左侧通话记录") -> None:
    app._customer_data_last_render_key = ""
    tree = app.customer_data_profile_table
    if not isinstance(tree, ttk.Treeview):
        return
    app._fill_profile_table_from_text(tree, profile_text="", empty_message=message, auto_height=True)
    clear_customer_data_call_entry_views(app, message)


def render_customer_data_call_entry_views(app, records: list[dict[str, str]]) -> None:
    text_widget = app.customer_data_call_entries_wrap
    if not isinstance(text_widget, tk.Text):
        return
    if not records:
        clear_customer_data_call_entry_views(app, "当前客户暂无通话记录")
        return
    visible_records = [entry for entry in records if record_has_detail_content(entry)]
    source_records = visible_records or list(records)
    sorted_records = sorted(
        source_records,
        key=lambda item: app._parse_datetime_to_epoch(str(item.get("call_time", ""))),
        reverse=True,
    )
    palettes = [
        {"bg": "#fff7ed"},
        {"bg": "#f0fdf4"},
    ]

    text_widget.configure(state="normal")
    text_widget.delete("1.0", "end")

    for idx, entry in enumerate(sorted_records):
        call_time = str(entry.get("call_time", "") or "-")
        palette = palettes[idx % 2]
        block_tag = f"block_{idx}"
        text_widget.tag_configure(block_tag, background=palette["bg"])

        summary_content = str(entry.get("summary", "") or "").strip()
        commitments_content = str(entry.get("commitments", "") or "").strip()
        strategy_content = str(entry.get("strategy", "") or "").strip()
        call_record_content = str(entry.get("call_record", "") or "").strip()
        if not summary_content:
            summary_content = call_record_content or "暂无内容"
        if not commitments_content:
            commitments_content = "暂无内容"
        if not strategy_content:
            strategy_content = "暂无内容"

        text_widget.insert("end", f"通话记录 {idx + 1}  |  {call_time}\n", ("time_header", block_tag))
        text_widget.insert("end", "【对话总结】\n", ("section_title", block_tag))
        text_widget.insert("end", summary_content + "\n", ("section_body", block_tag))
        text_widget.insert("end", "\n【客户承诺-执行事项】\n", ("section_title", block_tag))
        text_widget.insert("end", commitments_content + "\n", ("section_body", block_tag))
        text_widget.insert("end", "\n【下一步对话策略】\n", ("section_title", block_tag))
        text_widget.insert("end", strategy_content + "\n", ("section_body", block_tag))
        text_widget.insert("end", "\n", block_tag)

    text_widget.configure(state="disabled")
    text_widget.yview_moveto(0.0)


def open_customer_data_detail_window(
    app,
    customer_name: str,
    *,
    case_data: dict[str, object] | None,
    read_case_data,
    save_case_data,
    after_save=None,
    log_debug,
) -> None:
    current_case_data = case_data if isinstance(case_data, dict) else read_case_data(customer_name)
    if not isinstance(current_case_data, dict):
        current_case_data = {}

    profile_text = normalize_profile_editor_text(str(current_case_data.get("customer_profile", "") or ""))
    source_records = list(current_case_data.get("records", []))
    case_path = str(current_case_data.get("path", "") or "").strip()
    if (not case_path) or ((not source_records) and callable(read_case_data)):
        disk_case_data = read_case_data(customer_name)
        if isinstance(disk_case_data, dict):
            current_case_data = disk_case_data
            profile_text = normalize_profile_editor_text(str(current_case_data.get("customer_profile", "") or profile_text))
            source_records = list(current_case_data.get("records", []))
            case_path = str(current_case_data.get("path", "") or case_path).strip()
    visible_source_indices = repo_build_visible_customer_record_indices(app, source_records)

    if callable(log_debug):
        log_debug(
            f"detail data customer={customer_name} records={len(source_records)} display={len(visible_source_indices)} visible={sum(1 for idx in visible_source_indices if record_has_detail_content(source_records[idx]))}"
        )

    record_items = [
        {"source_index": idx, "entry": entry}
        for idx, entry in enumerate(source_records)
        if idx in visible_source_indices
        if record_has_detail_content(entry)
    ]
    if not record_items:
        record_items = [{"source_index": idx, "entry": entry} for idx, entry in enumerate(source_records) if idx in visible_source_indices]
    record_items.sort(
        key=lambda item: app._parse_datetime_to_epoch(str(item["entry"].get("call_time", "") or "")),
        reverse=True,
    )

    ensure_history_time_style()

    win = tk.Toplevel(app)
    win.withdraw()
    win.title(f"客户明细 - {customer_name}")
    screen_w = max(1, int(app.winfo_screenwidth() or 0))
    screen_h = max(1, int(app.winfo_screenheight() or 0))
    win_w = max(980, int(screen_w * 0.82))
    win_h = max(680, int(screen_h * 0.82))
    pos_x = max(0, (screen_w - win_w) // 2)
    pos_y = max(0, (screen_h - win_h) // 2)
    win.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
    win.minsize(860, 560)
    win.configure(bg="#eaf0f7")

    root = ttk.Frame(win, style="App.TFrame", padding=10)
    root.pack(fill=tk.BOTH, expand=True)
    panes = ttk.Panedwindow(root, orient=tk.VERTICAL)
    panes.pack(fill=tk.BOTH, expand=True)

    profile_box = ttk.LabelFrame(panes, text="", style="ThinSection.TLabelframe", padding=0)
    profile_wrap = ttk.Frame(profile_box, style="Panel.TFrame", padding=(8, 8, 8, 8))
    profile_wrap.pack(fill=tk.BOTH, expand=True)
    profile_wrap.columnconfigure(0, weight=1)
    profile_wrap.rowconfigure(1, weight=1)

    profile_header = ttk.Frame(profile_wrap, style="Panel.TFrame")
    profile_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    profile_header.columnconfigure(0, weight=1)
    ttk.Label(profile_header, text="客户画像", font=("Microsoft YaHei", 12, "bold")).grid(row=0, column=0, sticky="w")

    profile_table = ttk.Treeview(
        profile_wrap,
        columns=("field_1", "value_1", "field_2", "value_2", "field_3", "value_3"),
        show="headings",
        style="ConversationProfile.Treeview",
    )
    for col in ("field_1", "value_1", "field_2", "value_2", "field_3", "value_3"):
        profile_table.heading(col, text="")
        profile_table.column(col, minwidth=80, anchor="w", stretch=True)
    profile_scroll_y = ttk.Scrollbar(
        profile_wrap,
        orient=tk.VERTICAL,
        command=profile_table.yview,
        style="App.Vertical.TScrollbar",
    )
    profile_table.configure(yscrollcommand=profile_scroll_y.set)
    profile_table.grid(row=1, column=0, sticky="nsew")
    profile_scroll_y.grid(row=1, column=1, sticky="ns")
    profile_table.tag_configure("profile_even", background="#eef1f5", foreground="#0f1f35")
    profile_table.tag_configure("profile_odd", background="#e6e9ee", foreground="#0f1f35")
    profile_state = {"text": profile_text}
    app._fill_profile_table_from_text(profile_table, profile_text=profile_state["text"], auto_height=False)
    panes.add(profile_box, weight=2)

    history_box = ttk.LabelFrame(panes, text="", style="ThinSection.TLabelframe", padding=0)
    history_container = ttk.Frame(history_box, style="Panel.TFrame", padding=(8, 8, 8, 8))
    history_container.pack(fill=tk.BOTH, expand=True)
    history_container.columnconfigure(0, weight=1)
    history_container.rowconfigure(1, weight=1)

    header_frame = ttk.Frame(history_container, style="Panel.TFrame")
    header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    header_frame.columnconfigure(0, weight=1)
    ttk.Label(header_frame, text="历史对话数据", font=("Microsoft YaHei", 12, "bold")).grid(row=0, column=0, sticky="w")

    body_wrap = ttk.Panedwindow(history_container, orient=tk.HORIZONTAL)
    body_wrap.grid(row=1, column=0, sticky="nsew")

    list_frame = ttk.Frame(body_wrap, style="Panel.TFrame")
    list_frame.columnconfigure(0, weight=1)
    list_frame.rowconfigure(0, weight=1)
    time_listbox = ttk.Treeview(list_frame, style="HistoryTime.Treeview", show="tree", selectmode="browse")
    list_scroll_y = ttk.Scrollbar(
        list_frame,
        orient=tk.VERTICAL,
        command=time_listbox.yview,
        style="App.Vertical.TScrollbar",
    )
    time_listbox.configure(yscrollcommand=list_scroll_y.set)
    time_listbox.grid(row=0, column=0, sticky="nsew")
    list_scroll_y.grid(row=0, column=1, sticky="ns")
    body_wrap.add(list_frame, weight=1)

    detail_shell = ttk.Frame(body_wrap, style="Panel.TFrame", padding=(8, 4, 4, 4))
    detail_shell.columnconfigure(0, weight=1)
    detail_shell.rowconfigure(0, weight=1)
    body_wrap.add(detail_shell, weight=2)

    combined_box = ttk.LabelFrame(detail_shell, text="历史对话编辑", style="ThinSection.TLabelframe", padding=8)
    combined_box.grid(row=0, column=0, sticky="nsew")
    combined_box.columnconfigure(0, weight=1)
    combined_box.rowconfigure(0, weight=1)

    combined_text = ScrolledText(
        combined_box,
        wrap="word",
        bg="#ffffff",
        fg="#111827",
        font=("Microsoft YaHei", 11),
        spacing1=6,
        spacing2=4,
        spacing3=6,
        relief="flat",
        highlightthickness=1,
        highlightbackground="#d7dee8",
        bd=0,
        undo=True,
    )
    combined_text.grid(row=0, column=0, sticky="nsew")

    selection_state = {"list_index": -1}
    section_titles = {
        "summary": "【对话总结】",
        "commitments": "【客户承诺-执行事项】",
        "strategy": "【下一步对话策略】",
    }

    def _build_combined_content(*, summary: str, commitments: str, strategy: str) -> str:
        return "\n\n".join(
            [
                section_titles["summary"],
                summary.strip(),
                section_titles["commitments"],
                commitments.strip(),
                section_titles["strategy"],
                strategy.strip(),
            ]
        ).strip() + "\n"

    def _set_combined_content(text: str) -> None:
        combined_text.configure(state="normal")
        combined_text.delete("1.0", "end")
        combined_text.insert("1.0", text)

    def _parse_combined_content() -> dict[str, str]:
        text = combined_text.get("1.0", "end").strip()
        result = {"summary": "", "commitments": "", "strategy": ""}
        current_key = None
        lines: dict[str, list[str]] = {"summary": [], "commitments": [], "strategy": []}
        title_to_key = {value: key for key, value in section_titles.items()}
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            maybe_key = title_to_key.get(line.strip())
            if maybe_key is not None:
                current_key = maybe_key
                continue
            if current_key is None:
                lines["summary"].append(line)
                continue
            lines[current_key].append(line)
        for key, values in lines.items():
            result[key] = "\n".join(values).strip()
        return result

    def _set_save_enabled(enabled: bool) -> None:
        save_btn.configure(state=("normal" if enabled else "disabled"))

    def _refresh_popup_focus() -> None:
        if win.winfo_exists():
            win.deiconify()
            win.lift()
            try:
                win.focus_force()
            except Exception:
                pass

    def _save_profile_text(edited_text: str) -> None:
        normalized_text = normalize_profile_editor_text(edited_text)
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        created_time = str(current_case_data.get("created_time", "") or "").strip() or now_text
        save_case_data(
            path=Path(case_path),
            customer_name=str(current_case_data.get("customer_name", "") or customer_name),
            created_time=created_time,
            updated_time=now_text,
            profile_text=normalized_text,
            records=source_records,
        )
        profile_state["text"] = normalized_text
        current_case_data["customer_profile"] = normalized_text
        current_case_data["updated_time"] = now_text
        app._fill_profile_table_from_text(profile_table, profile_text=normalized_text, auto_height=False)
        if callable(after_save):
            after_save(customer_name)
        if callable(log_debug):
            log_debug(f"profile save customer={customer_name} length={len(normalized_text)}")

    def _open_profile_editor() -> None:
        editor = tk.Toplevel(win)
        editor.title(f"编辑客户画像 - {customer_name}")
        screen_w = max(1, int(win.winfo_screenwidth() or 0))
        screen_h = max(1, int(win.winfo_screenheight() or 0))
        editor_w = max(720, int(screen_w * 0.8))
        editor_h = max(520, int(screen_h * 0.8))
        pos_x = max(0, (screen_w - editor_w) // 2)
        pos_y = max(0, (screen_h - editor_h) // 2)
        editor.geometry(f"{editor_w}x{editor_h}+{pos_x}+{pos_y}")
        editor.minsize(560, 380)
        editor.transient(win)

        editor_root = ttk.Frame(editor, style="App.TFrame", padding=10)
        editor_root.pack(fill=tk.BOTH, expand=True)
        editor_root.columnconfigure(0, weight=1)
        editor_root.rowconfigure(1, weight=1)

        ttk.Label(
            editor_root,
            text="按“字段：值”逐行编辑。新增字段就新增一行，删除字段就删除对应行。",
            foreground="#475569",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        editor_text = ScrolledText(
            editor_root,
            wrap="word",
            bg="#ffffff",
            fg="#111827",
            font=("Microsoft YaHei", 11),
            spacing1=6,
            spacing2=4,
            spacing3=6,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#d7dee8",
            bd=0,
            undo=True,
        )
        editor_text.grid(row=1, column=0, sticky="nsew")
        editor_text.insert("1.0", profile_state["text"])

        button_bar = ttk.Frame(editor_root, style="Panel.TFrame")
        button_bar.grid(row=2, column=0, sticky="e", pady=(8, 0))

        def _save_profile_editor() -> None:
            try:
                _save_profile_text(editor_text.get("1.0", "end"))
                if editor.winfo_exists():
                    editor.destroy()
                _refresh_popup_focus()
                messagebox.showinfo("保存成功", "客户画像已保存。", parent=win)
                _refresh_popup_focus()
            except Exception as exc:
                if callable(log_debug):
                    log_debug(f"profile save failed customer={customer_name} error={exc!r}")
                messagebox.showerror("保存失败", f"客户画像保存失败：{exc}", parent=editor)

        ttk.Button(button_bar, text="取消", command=editor.destroy).pack(side=tk.RIGHT)
        ttk.Button(button_bar, text="保存", command=_save_profile_editor).pack(side=tk.RIGHT, padx=(0, 8))

    profile_edit_btn = ttk.Button(profile_header, text="编辑画像", command=_open_profile_editor)
    profile_edit_btn.grid(row=0, column=1, sticky="e")

    def _show_empty_detail(message: str) -> None:
        selection_state["list_index"] = -1
        _set_combined_content(_build_combined_content(summary=message, commitments="", strategy=""))
        _set_save_enabled(False)

    def _show_record(index: int) -> None:
        if (index < 0) or (index >= len(record_items)):
            _show_empty_detail("未读取到客户历史记录。")
            return
        item = record_items[index]
        entry = item["entry"]
        selection_state["list_index"] = index
        _set_combined_content(
            _build_combined_content(
                summary=str(entry.get("summary", "") or "").strip(),
                commitments=str(entry.get("commitments", "") or "").strip(),
                strategy=str(entry.get("strategy", "") or "").strip(),
            )
        )
        _set_save_enabled(bool(case_path))

    def _save_current_record() -> None:
        current_index = int(selection_state.get("list_index", -1))
        if (current_index < 0) or (current_index >= len(record_items)):
            messagebox.showwarning("无法保存", "请先在左侧选择一条历史记录。", parent=win)
            return
        if not case_path:
            messagebox.showerror("无法保存", "未找到当前客户数据文件路径，无法持久化保存。", parent=win)
            return

        item = record_items[current_index]
        source_index = int(item["source_index"])
        if (source_index < 0) or (source_index >= len(source_records)):
            messagebox.showerror("无法保存", "当前历史记录索引无效。", parent=win)
            return

        parsed_content = _parse_combined_content()
        updated_entry = source_records[source_index]
        updated_entry["summary"] = parsed_content["summary"]
        updated_entry["commitments"] = parsed_content["commitments"]
        updated_entry["strategy"] = parsed_content["strategy"]
        item["entry"] = updated_entry

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        created_time = str(current_case_data.get("created_time", "") or "").strip() or now_text
        try:
            save_case_data(
                path=Path(case_path),
                customer_name=str(current_case_data.get("customer_name", "") or customer_name),
                created_time=created_time,
                updated_time=now_text,
                profile_text=profile_state["text"],
                records=source_records,
            )
            current_case_data["records"] = source_records
            current_case_data["updated_time"] = now_text
            if callable(after_save):
                after_save(customer_name)
            if callable(log_debug):
                log_debug(
                    f"detail save customer={customer_name} source_index={source_index} call_time={str(updated_entry.get('call_time', '') or '')}"
                )
            _refresh_popup_focus()
            messagebox.showinfo("保存成功", "历史记录已保存。", parent=win)
            _refresh_popup_focus()
        except Exception as exc:
            if callable(log_debug):
                log_debug(f"detail save failed customer={customer_name} error={exc!r}")
            messagebox.showerror("保存失败", f"历史记录保存失败：{exc}", parent=win)

    save_btn = ttk.Button(header_frame, text="保存", command=_save_current_record)
    save_btn.grid(row=0, column=1, sticky="e")

    for idx, item in enumerate(record_items):
        call_time = str(item["entry"].get("call_time", "") or "-")
        time_listbox.insert("", "end", iid=str(idx), text=f"  {call_time}")

    def _on_time_select(_event=None) -> None:
        selected = time_listbox.selection()
        if not selected:
            return
        try:
            _show_record(int(selected[0]))
        except (TypeError, ValueError):
            return

    time_listbox.bind("<<TreeviewSelect>>", _on_time_select)

    if record_items:
        time_listbox.selection_set("0")
        time_listbox.focus("0")
        _show_record(0)
    else:
        _show_empty_detail("未读取到客户详情数据，请检查客户文件解析结果。")

    panes.add(history_box, weight=3)

    def _set_detail_sashes() -> None:
        try:
            total_w = int(body_wrap.winfo_width() or 0)
            if total_w > 0:
                body_wrap.sashpos(0, int(total_w * 0.28))
        except tk.TclError:
            return

    def _set_initial_sash() -> None:
        try:
            total_h = int(panes.winfo_height() or 0)
            if total_h <= 0:
                panes.after(60, _set_initial_sash)
                return
            panes.sashpos(0, int(total_h / 3))
        except tk.TclError:
            return

    body_wrap.after_idle(_set_detail_sashes)
    body_wrap.after(120, _set_detail_sashes)
    body_wrap.bind("<Map>", lambda _event: body_wrap.after_idle(_set_detail_sashes), add="+")
    body_wrap.bind("<Configure>", lambda _event: body_wrap.after_idle(_set_detail_sashes), add="+")
    panes.after_idle(_set_initial_sash)
    panes.after(120, _set_initial_sash)
    panes.bind("<Map>", lambda _event: panes.after_idle(_set_initial_sash), add="+")
    panes.bind("<Configure>", lambda _event: panes.after_idle(_set_initial_sash), add="+")
    win.deiconify()


def open_call_record_detail_window(app, record: dict[str, str]) -> None:
    win = tk.Toplevel(app)
    win.title(f"通话详情 - {record.get('customer_name', '未知客户')}")
    win.geometry("980x700")
    win.configure(bg="#eaf0f7")

    root = ttk.Frame(win, style="App.TFrame", padding=10)
    root.pack(fill=tk.BOTH, expand=True)
    panes = ttk.Panedwindow(root, orient=tk.VERTICAL)
    panes.pack(fill=tk.BOTH, expand=True)

    summary_box = ttk.LabelFrame(panes, text="对话总结", style="Section.TLabelframe", padding=8)
    summary_text = ScrolledText(summary_box, wrap="word", bg="#ffffff", fg="#111827", spacing1=8, spacing2=4, spacing3=8, relief="flat")
    summary_text.pack(fill=tk.BOTH, expand=True)
    summary_text.insert("1.0", record.get("summary", "") or "暂无内容")
    summary_text.configure(state="disabled")
    panes.add(summary_box, weight=1)

    commitments_box = ttk.LabelFrame(panes, text="客户承诺-执行事项", style="Section.TLabelframe", padding=8)
    commitments_text = ScrolledText(commitments_box, wrap="word", bg="#ffffff", fg="#111827", spacing1=8, spacing2=4, spacing3=8, relief="flat")
    commitments_text.pack(fill=tk.BOTH, expand=True)
    commitments_text.insert("1.0", record.get("commitments", "") or "暂无内容")
    commitments_text.configure(state="disabled")
    panes.add(commitments_box, weight=1)

    strategy_box = ttk.LabelFrame(panes, text="Next Strategy", style="Section.TLabelframe", padding=8)
    strategy_text = ScrolledText(strategy_box, wrap="word", bg="#ffffff", fg="#111827", spacing1=8, spacing2=4, spacing3=8, relief="flat")
    strategy_text.pack(fill=tk.BOTH, expand=True)
    strategy_text.insert("1.0", record.get("strategy", "") or "暂无内容")
    strategy_text.configure(state="disabled")
    panes.add(strategy_box, weight=1)
