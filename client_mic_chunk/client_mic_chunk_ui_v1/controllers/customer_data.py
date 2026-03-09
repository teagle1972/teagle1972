from __future__ import annotations

from datetime import datetime

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText


def build_call_record_items(app) -> list[dict[str, str]]:
    data_dir = app._get_data_dir()
    items: list[dict[str, str]] = []
    files = sorted(data_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        try:
            case_data = app._read_customer_case_file(path)
        except Exception as exc:
            app._append_line(
                app.log_text,
                f"[{datetime.now().strftime('%H:%M:%S')}] [CALL_RECORD] read failed: {path.name} {exc}",
            )
            continue
        customer_name = str(case_data.get("customer_name", "未知客户"))
        profile_text = str(case_data.get("customer_profile", "") or "")
        records = list(case_data.get("records", []))
        for idx, entry in enumerate(records):
            call_time = str(entry.get("call_time", "") or "").strip() or str(case_data.get("updated_time", "") or "")
            items.append(
                {
                    "customer_name": customer_name,
                    "last_call_time": call_time or "-",
                    "call_cost": str(entry.get("call_cost", "") or "").strip(),
                    "customer_profile": profile_text,
                    "call_record": str(entry.get("call_record", "") or ""),
                    "summary": str(entry.get("summary", "") or ""),
                    "commitments": str(entry.get("commitments", "") or ""),
                    "strategy": str(entry.get("strategy", "") or ""),
                    "path": str(path),
                    "entry_index": str(idx),
                }
            )
    items.sort(key=lambda item: app._parse_datetime_to_epoch(item.get("last_call_time", "")), reverse=True)
    return items


def render_call_record_detail(app, record: dict[str, str]) -> None:
    customer_name = record.get("customer_name", "未知客户")
    call_time = record.get("last_call_time", "-")
    call_cost = str(record.get("call_cost", "") or "").strip() or "-"
    app.call_record_selected_var.set(
        f"已选记录：{customer_name}  |  通话时间：{call_time}  |  通话费用：{call_cost}"
    )
    summary_widget = app.call_record_summary_text
    commitments_widget = app.call_record_commitments_text
    strategy_widget = app.call_record_strategy_text
    if isinstance(summary_widget, ScrolledText):
        app._set_text_content(summary_widget, record.get("summary", "") or "暂无内容")
        summary_widget.configure(state="disabled")
    if isinstance(commitments_widget, ScrolledText):
        app._set_text_content(commitments_widget, record.get("commitments", "") or "暂无内容")
        commitments_widget.configure(state="disabled")
    if isinstance(strategy_widget, ScrolledText):
        app._set_text_content(strategy_widget, record.get("strategy", "") or "暂无内容")
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
    app._refresh_runtime_system_prompt_only()


def load_call_records_into_list(app) -> None:
    tree = app.call_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    tree.delete(*tree.get_children())
    app._call_record_item_by_iid.clear()
    items = app._build_call_record_items()
    if not items:
        app._clear_call_record_detail("Data 目录下暂无通话记录")
        return
    first_iid = ""
    for idx, item in enumerate(items):
        try:
            iid = f"rec_{idx}"
            tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    item.get("customer_name", "未知客户"),
                    item.get("last_call_time", "-"),
                    item.get("call_cost", "") or "-",
                ),
            )
            app._call_record_item_by_iid[iid] = item
            if not first_iid:
                first_iid = iid
        except Exception as exc:
            app._append_line(
                app.log_text,
                f"[{datetime.now().strftime('%H:%M:%S')}] [CALL_RECORD] read failed: {exc}",
            )
    if first_iid:
        tree.selection_set(first_iid)
        tree.focus(first_iid)
        app._on_call_record_selected(apply_profile_and_workflow=False)
    else:
        app._clear_call_record_detail("记录读取失败")


def clear_customer_data_profile_table(app, message: str = "请择左侧通话记录") -> None:
    app._customer_data_last_render_key = ""
    tree = app.customer_data_profile_table
    if not isinstance(tree, ttk.Treeview):
        return
    app._fill_profile_table_from_text(tree, profile_text="", empty_message=message, auto_height=True)
    app._clear_customer_data_call_entry_views(message)


def clear_customer_data_call_entry_views(app, message: str = "请择左侧通话记录") -> None:
    container = app.customer_data_call_entries_wrap
    canvas = app.customer_data_calls_canvas
    if not isinstance(container, ttk.Frame):
        return
    for child in list(container.winfo_children()):
        child.destroy()
    ttk.Label(container, text=message, style="Muted.TLabel").pack(anchor="w", padx=8, pady=8)
    if isinstance(canvas, tk.Canvas):
        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))


def render_customer_data_call_entry_views(app, records: list[dict[str, str]]) -> None:
    container = app.customer_data_call_entries_wrap
    canvas = app.customer_data_calls_canvas
    if not isinstance(container, ttk.Frame):
        return
    for child in list(container.winfo_children()):
        child.destroy()
    if not records:
        app._clear_customer_data_call_entry_views("当前客户暂无通话记录")
        return
    sorted_records = sorted(
        records,
        key=lambda item: app._parse_datetime_to_epoch(str(item.get("call_time", ""))),
        reverse=True,
    )
    palettes = [
        {"bg": "#fff7ed", "border": "#fdba74"},
        {"bg": "#f0fdf4", "border": "#86efac"},
    ]

    def _estimate_height(content: str) -> int:
        lines = (content or "").splitlines() or [""]
        estimated = 0
        for raw_line in lines:
            # Prefer extra room to avoid inner scrolling in read-only detail blocks.
            estimated += max(1, (len(raw_line) // 24) + 1)
        return max(2, estimated + 1)

    def _build_collapsible_text_panel(
        parent,
        title: str,
        content: str,
        text_bg: str,
        border_color: str,
        pady: tuple[int, int],
    ) -> None:
        collapsed_height = 5
        expanded_height = max(collapsed_height, _estimate_height(content))
        panel = tk.LabelFrame(
            parent,
            text=title,
            bg=text_bg,
            fg="#334155",
            font=("微软雅黑", 9),
            bd=1,
            relief="flat",
            padx=8,
            pady=6,
        )
        panel.pack(fill=tk.X, expand=False, pady=pady)

        text_widget = tk.Text(
            panel,
            wrap="word",
            state="normal",
            bg=text_bg,
            fg="#111827",
            relief="flat",
            highlightthickness=1,
            highlightbackground=border_color,
            height=collapsed_height,
            bd=0,
        )
        text_widget.pack(fill=tk.X, expand=False)
        text_widget.insert("1.0", content)
        text_widget.configure(state="disabled")

        toggle_wrap = tk.Frame(panel, bg=text_bg)
        toggle_wrap.pack(fill=tk.X, expand=False, pady=(4, 0))
        divider = tk.Frame(toggle_wrap, height=1, bg=border_color)
        divider.pack(fill=tk.X, side=tk.TOP)
        marker = tk.Label(
            toggle_wrap,
            text="▼展",
            cursor="hand2",
            bg=text_bg,
            fg="#475569",
            font=("微软雅黑", 9),
        )
        marker.pack(side=tk.TOP, pady=(2, 0))

        expanded = {"value": False}

        def _toggle(_event=None) -> str:
            expanded["value"] = not bool(expanded["value"])
            target_height = expanded_height if expanded["value"] else collapsed_height
            text_widget.configure(height=target_height)
            marker.configure(text="" if expanded["value"] else "չ")
            if isinstance(canvas, tk.Canvas):
                canvas.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
            return "break"

        marker.bind("<Button-1>", _toggle)

    for idx, entry in enumerate(sorted_records):
        call_time = str(entry.get("call_time", "") or "-")
        palette = palettes[idx % 2]
        text_bg = palette["bg"]
        border_color = palette["border"]
        summary_content = str(entry.get("summary", "") or "暂无内容")
        commitments_content = str(entry.get("commitments", "") or "暂无内容")
        strategy_content = str(entry.get("strategy", "") or "暂无内容")
        card = tk.LabelFrame(
            container,
            text=f"通话记录 {idx + 1}  |  {call_time}",
            bg=text_bg,
            fg="#1e3a5f",
            font=("微软雅黑", 9, "bold"),
            bd=1,
            relief="flat",
            padx=8,
            pady=8,
        )
        card.pack(fill=tk.X, expand=False, padx=4, pady=(0, 8))

        _build_collapsible_text_panel(
            parent=card,
            title="对话总结",
            content=summary_content,
            text_bg=text_bg,
            border_color=border_color,
            pady=(0, 6),
        )
        _build_collapsible_text_panel(
            parent=card,
            title="客户承诺-执行事项",
            content=commitments_content,
            text_bg=text_bg,
            border_color=border_color,
            pady=(0, 6),
        )
        _build_collapsible_text_panel(
            parent=card,
            title="һԻ",
            content=strategy_content,
            text_bg=text_bg,
            border_color=border_color,
            pady=(0, 0),
        )
    if isinstance(canvas, tk.Canvas):
        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))


def build_customer_case_cache_by_name(app) -> dict[str, dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    data_dir = app._get_data_dir()
    files = sorted(data_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        try:
            case_data = app._read_customer_case_file(path)
        except Exception as exc:
            app._append_line(
                app.log_text,
                f"[{datetime.now().strftime('%H:%M:%S')}] [CUSTOMER_DATA] read failed: {path.name} {exc}",
            )
            continue
        customer_name = str(case_data.get("customer_name", "未知客户") or "未知客户")
        profile_text = str(case_data.get("customer_profile", "") or "")
        created_time = str(case_data.get("created_time", "") or "")
        updated_time = str(case_data.get("updated_time", "") or "")
        records = list(case_data.get("records", []))

        payload = grouped.get(customer_name)
        if payload is None:
            payload = {
                "customer_name": customer_name,
                "customer_profile": profile_text,
                "created_time": created_time,
                "updated_time": updated_time,
                "records": [],
            }
            grouped[customer_name] = payload
        else:
            if (not str(payload.get("customer_profile", "")).strip()) and profile_text.strip():
                payload["customer_profile"] = profile_text
            existing_created = str(payload.get("created_time", "") or "")
            if (not existing_created) or (
                created_time and app._parse_datetime_to_epoch(created_time) < app._parse_datetime_to_epoch(existing_created)
            ):
                payload["created_time"] = created_time
            existing_updated = str(payload.get("updated_time", "") or "")
            if app._parse_datetime_to_epoch(updated_time) > app._parse_datetime_to_epoch(existing_updated):
                payload["updated_time"] = updated_time

        merged_records = payload.get("records", [])
        if isinstance(merged_records, list):
            for entry in records:
                merged_records.append(
                    {
                        "call_time": str(entry.get("call_time", "") or ""),
                        "call_cost": str(entry.get("call_cost", "") or ""),
                        "call_record": str(entry.get("call_record", "") or ""),
                        "summary": str(entry.get("summary", "") or ""),
                        "commitments": str(entry.get("commitments", "") or ""),
                        "strategy": str(entry.get("strategy", "") or ""),
                    }
                )

    return grouped


def get_selected_customer_case_data(app, ensure_default_selection: bool = True) -> dict[str, object] | None:
    cache = app._customer_data_case_cache_by_name
    if not cache:
        cache = app._build_customer_case_cache_by_name()
        app._customer_data_case_cache_by_name = cache
    if not cache:
        return None

    selected_name = ""
    tree = app.customer_data_record_tree
    if isinstance(tree, ttk.Treeview):
        selected = tree.selection()
        if selected:
            selected_name = str(app._customer_data_customer_by_iid.get(selected[0], "")).strip()
        if (not selected_name) and ensure_default_selection:
            children = list(tree.get_children())
            if children:
                first_iid = children[0]
                tree.selection_set(first_iid)
                tree.focus(first_iid)
                selected_name = str(app._customer_data_customer_by_iid.get(first_iid, "")).strip()

    if selected_name and isinstance(cache.get(selected_name), dict):
        return cache[selected_name]

    latest_name = max(
        cache.keys(),
        key=lambda name: app._parse_datetime_to_epoch(str(cache[name].get("updated_time", "") or "")),
    )
    return cache.get(latest_name)


def extract_latest_strategy_from_case_data(
    app,
    case_data: dict[str, object],
    *,
    default_workflow: str,
) -> str:
    records = list(case_data.get("records", []))
    if not records:
        return default_workflow
    sorted_records = sorted(
        records,
        key=lambda item: app._parse_datetime_to_epoch(str(item.get("call_time", "") or "")),
        reverse=True,
    )
    for entry in sorted_records:
        strategy = str(entry.get("strategy", "") or "").strip()
        if strategy:
            return strategy
    return default_workflow


def prepare_call_context_from_customer_data_and_workflow_page(
    app,
    *,
    default_workflow: str,
) -> bool:
    case_data = app._get_selected_customer_case_data(ensure_default_selection=True)
    if not isinstance(case_data, dict):
        messagebox.showwarning("无客户数据", "请先创建或选择一个客户。")
        return False

    profile_text = str(case_data.get("customer_profile", "") or "").strip()
    if not profile_text:
        messagebox.showwarning("客户画像为空", "当前客户资料缺少客户画像，无法发起呼叫。")
        return False

    dialog_profile_tree = app.dialog_profile_table
    if isinstance(dialog_profile_tree, ttk.Treeview):
        app._fill_profile_table_from_text(dialog_profile_tree, profile_text=profile_text, auto_height=True)
    app._refresh_runtime_system_prompt_only()
    return True

def load_customer_data_records_into_list(app) -> None:
    tree = app.customer_data_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    previous_selected_name = ""
    selected = tree.selection()
    if selected:
        previous_selected_name = str(app._customer_data_customer_by_iid.get(selected[0], "")).strip()
    tree.delete(*tree.get_children())
    app._customer_data_customer_by_iid.clear()
    app._customer_data_case_cache_by_name = app._build_customer_case_cache_by_name()
    if not app._customer_data_case_cache_by_name:
        app._clear_customer_data_profile_table("Data 目录下暂无通话记录")
        return
    customer_items: list[tuple[str, str]] = []
    for customer_name, payload in app._customer_data_case_cache_by_name.items():
        latest_time = str(payload.get("updated_time", "") or "")
        records = list(payload.get("records", []))
        if records:
            latest_time = max(
                (str(item.get("call_time", "") or "") for item in records),
                key=lambda text: app._parse_datetime_to_epoch(text),
                default=latest_time,
            )
        customer_items.append((customer_name, latest_time))
    customer_items.sort(key=lambda item: app._parse_datetime_to_epoch(item[1]), reverse=True)
    first_iid = ""
    preferred_iid = ""
    for idx, (customer_name, _latest_time) in enumerate(customer_items):
        try:
            iid = f"customer_data_{idx}"
            tree.insert(
                "",
                "end",
                iid=iid,
                values=(customer_name, "📞"),
            )
            app._customer_data_customer_by_iid[iid] = customer_name
            if not first_iid:
                first_iid = iid
            if previous_selected_name and (customer_name == previous_selected_name):
                preferred_iid = iid
        except Exception as exc:
            app._append_line(
                app.log_text,
                f"[{datetime.now().strftime('%H:%M:%S')}] [CUSTOMER_DATA] read failed: {exc}",
            )
    target_iid = preferred_iid or first_iid
    if target_iid:
        tree.selection_set(target_iid)
        tree.focus(target_iid)
        app._on_customer_data_record_selected()
    else:
        app._clear_customer_data_profile_table("记录读取失败")


def on_customer_data_record_selected(app, _event=None) -> None:
    tree = app.customer_data_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    selected = tree.selection()
    if not selected:
        focus_iid = str(tree.focus() or "")
        if focus_iid and (focus_iid in app._customer_data_customer_by_iid):
            selected = (focus_iid,)
        else:
            return
    iid = selected[0]
    customer_name = app._customer_data_customer_by_iid.get(iid)
    if not customer_name:
        app._clear_customer_data_profile_table()
        return
    case_data = app._customer_data_case_cache_by_name.get(customer_name)
    if not isinstance(case_data, dict):
        app._clear_customer_data_profile_table("ͻϻʧЧ½ͻлҳˢ¡")
        return
    profile_text = str(case_data.get("customer_profile", "") or "")
    records = list(case_data.get("records", []))
    render_key_parts: list[str] = [customer_name, str(case_data.get("updated_time", "") or ""), profile_text]
    for entry in records:
        render_key_parts.append(str(entry.get("call_time", "") or ""))
        render_key_parts.append(str(entry.get("summary", "") or ""))
        render_key_parts.append(str(entry.get("commitments", "") or ""))
        render_key_parts.append(str(entry.get("strategy", "") or ""))
    render_key = "\x1f".join(render_key_parts)
    if render_key == app._customer_data_last_render_key:
        return
    profile_tree = app.customer_data_profile_table
    if isinstance(profile_tree, ttk.Treeview):
        app._fill_profile_table_from_text(profile_tree, profile_text=profile_text, auto_height=True)
    app._render_customer_data_call_entry_views(records)
    app._customer_data_last_render_key = render_key


def on_customer_data_tree_click(app, event=None) -> None:
    tree = app.customer_data_record_tree
    if (event is None) or (not isinstance(tree, ttk.Treeview)):
        return
    x = int(getattr(event, "x", 0))
    y = int(getattr(event, "y", 0))
    row_id = tree.identify_row(y)
    col_id = tree.identify_column(x)
    region = str(tree.identify("region", x, y) or "")
    if not row_id:
        return
    if row_id not in app._customer_data_customer_by_iid:
        return
    if region != "cell":
        return
    if col_id == "#1":
        return
    if col_id != "#2":
        return
    current_selected = tree.selection()
    is_selected = bool(current_selected and (current_selected[0] == row_id))
    if not is_selected:
        tree.selection_set(row_id)
    tree.focus(row_id)
    app._on_customer_data_record_selected()

    # 电话图标点击：加载户的话数捈实时话页?
    customer_name = app._customer_data_customer_by_iid.get(row_id)
    if customer_name:
        app._set_dialog_conversation_active_customer(str(customer_name))
        case_data = app._customer_data_case_cache_by_name.get(customer_name)
        if isinstance(case_data, dict):
            profile_text = str(case_data.get("customer_profile", "") or "")
            dialog_profile_tree = app.dialog_profile_table
            if isinstance(dialog_profile_tree, ttk.Treeview):
                app._fill_profile_table_from_text(dialog_profile_tree, profile_text=profile_text, auto_height=True)
            records = list(case_data.get("records", []))
            sorted_records = sorted(
                records,
                key=lambda item: app._parse_datetime_to_epoch(str(item.get("call_time", "") or "")),
                reverse=True,
            )
            most_recent_call_record = ""
            for entry in sorted_records:
                call_record_text = str(entry.get("call_record", "") or "").strip()
                if call_record_text:
                    most_recent_call_record = call_record_text
                    break
            app._render_dialog_conversation_history(most_recent_call_record, customer_name=str(customer_name))

    switcher = app._conversation_page_switcher
    if callable(switcher):
        switcher("profile")

    def _trigger_call_after_switch() -> None:
        ts_text = datetime.now().strftime("%H:%M:%S")
        app._append_line(app.log_text, f"[{ts_text}] [CUSTOMER_DATA] call-icon clicked -> invoke profile call")
        btn = app.profile_call_btn
        if isinstance(btn, ttk.Button):
            try:
                btn.invoke()
                app._append_line(app.log_text, f"[{ts_text}] [CUSTOMER_DATA] profile_call_btn.invoke() dispatched")
                return
            except Exception:
                pass
        app._append_line(app.log_text, f"[{ts_text}] [CUSTOMER_DATA] profile_call_btn missing -> fallback start")
        app._start_from_conversation_profile()

    # Run after page switch is fully reflected to avoid click-event timing issues.
    app.after_idle(lambda: app.after(120, _trigger_call_after_switch))


def on_customer_data_tree_double_click(app, event=None) -> None:
    pass


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
    summary_text = ScrolledText(summary_box, wrap="word", bg="#ffffff", fg="#111827", relief="flat")
    summary_text.pack(fill=tk.BOTH, expand=True)
    summary_text.insert("1.0", record.get("summary", "") or "暂无内容")
    summary_text.configure(state="disabled")
    panes.add(summary_box, weight=1)

    commitments_box = ttk.LabelFrame(panes, text="客户承诺-执行事项", style="Section.TLabelframe", padding=8)
    commitments_text = ScrolledText(commitments_box, wrap="word", bg="#ffffff", fg="#111827", relief="flat")
    commitments_text.pack(fill=tk.BOTH, expand=True)
    commitments_text.insert("1.0", record.get("commitments", "") or "暂无内容")
    commitments_text.configure(state="disabled")
    panes.add(commitments_box, weight=1)

    strategy_box = ttk.LabelFrame(panes, text="下一步对话策略", style="Section.TLabelframe", padding=8)
    strategy_text = ScrolledText(strategy_box, wrap="word", bg="#ffffff", fg="#111827", relief="flat")
    strategy_text.pack(fill=tk.BOTH, expand=True)
    strategy_text.insert("1.0", record.get("strategy", "") or "暂无内容")
    strategy_text.configure(state="disabled")
    panes.add(strategy_box, weight=1)

def on_call_record_selected(app, _event=None, apply_profile_and_workflow: bool = False) -> None:
    tree = app.call_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    selected = tree.selection()
    if not selected:
        app._clear_call_record_detail()
        return
    iid = selected[0]
    record = app._call_record_item_by_iid.get(iid)
    if not record:
        app._clear_call_record_detail()
        return
    app._render_call_record_detail(record)


def on_call_record_call(app) -> None:
    tree = app.call_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    selected = tree.selection()
    if not selected:
        messagebox.showwarning("未选择记录", "请先选择一条通话记录。")
        return
    iid = selected[0]
    record = app._call_record_item_by_iid.get(iid)
    if not record:
        messagebox.showwarning("无效记录", "当前记录不可用。")
        return

    customer_name = str(record.get("customer_name", "") or "")
    app._set_dialog_conversation_active_customer(customer_name)
    app._apply_call_record_profile_and_workflow(record)
    app._render_dialog_conversation_history(record.get("call_record", ""), customer_name=customer_name)
    app._append_dialog_session_separator()
    switcher = app._conversation_page_switcher
    if callable(switcher):
        switcher("profile")

