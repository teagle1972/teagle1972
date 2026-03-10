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
            call_cost_text = str(entry.get("call_cost", "") or "").strip()
            billing_duration_text = str(entry.get("billing_duration", "") or "").strip() or "-"
            price_per_minute_text = str(entry.get("price_per_minute", "") or "").strip() or "-"
            items.append(
                {
                    "customer_name": customer_name,
                    "last_call_time": call_time or "-",
                    "call_cost": call_cost_text,
                    "billing_duration": billing_duration_text,
                    "price_per_minute": price_per_minute_text,
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
    customer_name = record.get("customer_name", "Unknown Customer")
    call_time = record.get("last_call_time", "-")
    call_cost = str(record.get("call_cost", "") or "").strip() or "-"
    billing_duration = str(record.get("billing_duration", "") or "").strip() or "-"
    price_per_minute = str(record.get("price_per_minute", "") or "").strip() or "-"
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
    app._refresh_runtime_system_prompt_only()


def load_call_records_into_list(app) -> None:
    tree = app.call_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    tree.delete(*tree.get_children())
    app._call_record_item_by_iid.clear()
    items = app._build_call_record_items()
    if not items:
        app._clear_call_record_detail("Data 目录下暂时无通话记录")
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
                    item.get("billing_duration", "") or "-",
                    item.get("price_per_minute", "") or "-",
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


def clear_customer_data_profile_table(app, message: str = "请选择左侧通话记录") -> None:
    app._customer_data_last_render_key = ""
    tree = app.customer_data_profile_table
    if not isinstance(tree, ttk.Treeview):
        return
    app._fill_profile_table_from_text(tree, profile_text="", empty_message=message, auto_height=True)
    app._clear_customer_data_call_entry_views(message)


def clear_customer_data_call_entry_views(app, message: str = "请选择左侧通话记录") -> None:
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
            fg="#000000",
            font=("Microsoft YaHei", 11),
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
            fg="#000000",
            font=("Microsoft YaHei", 11),
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
            text="展开",
            cursor="hand2",
            bg=text_bg,
            fg="#000000",
            font=("Microsoft YaHei", 11),
        )
        marker.pack(side=tk.TOP, pady=(2, 0))

        expanded = {"value": False}

        def _toggle(_event=None) -> str:
            expanded["value"] = not bool(expanded["value"])
            target_height = expanded_height if expanded["value"] else collapsed_height
            text_widget.configure(height=target_height)
            marker.configure(text="收起" if expanded["value"] else "展开")
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
            fg="#000000",
            font=("Microsoft YaHei", 11, "bold"),
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
            title="下一步对话策略",
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
                        "billing_duration": str(entry.get("billing_duration", "") or ""),
                        "billing_duration_seconds": str(entry.get("billing_duration_seconds", "") or ""),
                        "price_per_minute": str(entry.get("price_per_minute", "") or ""),
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
        messagebox.showwarning("No customer data", "Please create or select a customer first.")
        return False

    profile_text = str(case_data.get("customer_profile", "") or "").strip()
    if not profile_text:
        messagebox.showwarning("Customer profile required", "Current customer profile is empty, cannot start a call.")
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
        app._clear_customer_data_profile_table("Data 目录下暂时无通话记录")
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
                values=(customer_name, "\u2139", "\u260E"),
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
        app._clear_customer_data_profile_table("记录失效，请刷新")
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
    if col_id not in {"#2", "#3"}:
        return
    current_selected = tree.selection()
    is_selected = bool(current_selected and (current_selected[0] == row_id))
    if not is_selected:
        tree.selection_set(row_id)
    tree.focus(row_id)
    app._on_customer_data_record_selected()
    customer_name = app._customer_data_customer_by_iid.get(row_id)
    if not customer_name:
        return

    if col_id == "#2":
        open_customer_data_detail_window(app, customer_name)
        return

    # 鐢佃瘽鍥炬爣鐐瑰嚮锛氬姞杞芥埛鐨勮瘽鏁版崍瀹炴椂璇濋〉?
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
        start_from_call_icon = getattr(app, "_start_from_customer_data_call_icon", None)
        if callable(start_from_call_icon):
            try:
                start_from_call_icon()
                app._append_line(app.log_text, f"[{ts_text}] [CUSTOMER_DATA] start_from_customer_data_call_icon() dispatched")
                return
            except Exception:
                pass
        app._append_line(app.log_text, f"[{ts_text}] [CUSTOMER_DATA] call-icon handler missing -> fallback start")
        app._start_from_conversation_profile()

    # Run after page switch is fully reflected to avoid click-event timing issues.
    app.after_idle(lambda: app.after(120, _trigger_call_after_switch))


def on_customer_data_tree_double_click(app, event=None) -> None:
    pass


def open_customer_data_detail_window(app, customer_name: str) -> None:
    case_data = app._customer_data_case_cache_by_name.get(customer_name)
    profile_text = ""
    records: list[dict[str, str]] = []
    if isinstance(case_data, dict):
        profile_text = str(case_data.get("customer_profile", "") or "")
        records = list(case_data.get("records", []))

    records.sort(
        key=lambda item: app._parse_datetime_to_epoch(str(item.get("call_time", "") or "")),
        reverse=True,
    )
    history_lines: list[str] = []
    for idx, entry in enumerate(records, start=1):
        call_time = str(entry.get("call_time", "") or "").strip() or "-"
        call_record = str(entry.get("call_record", "") or "").strip()
        summary = str(entry.get("summary", "") or "").strip()
        commitments = str(entry.get("commitments", "") or "").strip()
        strategy = str(entry.get("strategy", "") or "").strip()
        parts: list[str] = []
        if call_record:
            parts.append(call_record)
        if summary:
            parts.append(f"【总结】{summary}")
        if commitments:
            parts.append(f"【承诺】{commitments}")
        if strategy:
            parts.append(f"【策略】{strategy}")
        content = "\n".join(parts).strip() or "暂无内容"
        history_lines.append(f"[{idx}] {call_time}\n{content}")
    history_text = "\n\n".join(history_lines).strip() or "暂无历史对话信息"

    win = tk.Toplevel(app)
    win.title(f"客户明细 - {customer_name}")
    screen_w = max(1, int(app.winfo_screenwidth() or 0))
    screen_h = max(1, int(app.winfo_screenheight() or 0))
    win_w = max(900, int(screen_w * 0.8))
    win_h = max(600, int(screen_h * 0.8))
    pos_x = max(0, (screen_w - win_w) // 2)
    pos_y = max(0, (screen_h - win_h) // 2)
    win.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
    win.minsize(800, 520)
    win.configure(bg="#eaf0f7")

    root = ttk.Frame(win, style="App.TFrame", padding=10)
    root.pack(fill=tk.BOTH, expand=True)
    panes = ttk.Panedwindow(root, orient=tk.VERTICAL)
    panes.pack(fill=tk.BOTH, expand=True)

    profile_box = ttk.LabelFrame(panes, text="客户画像", style="ThinSection.TLabelframe", padding=0)
    profile_wrap = ttk.Frame(profile_box, style="Panel.TFrame")
    profile_wrap.pack(fill=tk.BOTH, expand=True)
    profile_wrap.columnconfigure(0, weight=1)
    profile_wrap.rowconfigure(0, weight=1)
    profile_table = ttk.Treeview(
        profile_wrap,
        columns=("field_1", "value_1", "field_2", "value_2", "field_3", "value_3"),
        show=[],
        style="ConversationProfile.Treeview",
    )
    for col in ("field_1", "value_1", "field_2", "value_2", "field_3", "value_3"):
        profile_table.heading(col, text="")
        profile_table.column(col, minwidth=110, anchor="w", stretch=True)
    profile_scroll_y = ttk.Scrollbar(
        profile_wrap,
        orient=tk.VERTICAL,
        command=profile_table.yview,
        style="App.Vertical.TScrollbar",
    )
    profile_table.configure(yscrollcommand=profile_scroll_y.set)
    profile_table.grid(row=0, column=0, sticky="nsew")
    profile_scroll_y.grid(row=0, column=1, sticky="ns")
    profile_table.tag_configure("profile_even", background="#eef1f5", foreground="#0f1f35")
    profile_table.tag_configure("profile_odd", background="#e6e9ee", foreground="#0f1f35")
    # Keep a fixed table viewport; avoid content-driven height expansion
    # that can squeeze the history pane.
    app._fill_profile_table_from_text(profile_table, profile_text=profile_text, auto_height=False)
    profile_table.bind(
        "<Configure>",
        lambda _event, tree=profile_table: app._resize_profile_table_columns(tree),
        add="+",
    )
    panes.add(profile_box, weight=2)

    history_box = ttk.LabelFrame(panes, text="历史对话数据", style="ThinSection.TLabelframe", padding=0)
    history_wrap = ttk.Frame(history_box, style="Panel.TFrame")
    history_wrap.pack(fill=tk.BOTH, expand=True)
    history_wrap.columnconfigure(0, weight=1)
    history_wrap.rowconfigure(0, weight=1)
    history_widget = tk.Text(
        history_wrap,
        wrap="word",
        bg="#ffffff",
        fg="#111827",
        relief="flat",
        highlightthickness=0,
    )
    history_scroll_y = ttk.Scrollbar(
        history_wrap,
        orient=tk.VERTICAL,
        command=history_widget.yview,
        style="App.Vertical.TScrollbar",
    )
    history_widget.configure(yscrollcommand=history_scroll_y.set)
    history_widget.grid(row=0, column=0, sticky="nsew")
    history_scroll_y.grid(row=0, column=1, sticky="ns")
    history_widget.insert("1.0", history_text)
    history_widget.configure(state="disabled")
    panes.add(history_box, weight=3)

    def _set_initial_sash() -> None:
        try:
            total_h = int(panes.winfo_height() or 0)
            if total_h <= 0:
                panes.after(60, _set_initial_sash)
                return
            panes.sashpos(0, int(total_h / 3))
        except tk.TclError:
            return

    panes.after_idle(_set_initial_sash)
    # Re-apply ratio after layout settles and when window size changes.
    panes.after(120, _set_initial_sash)
    panes.bind("<Map>", lambda _event: panes.after_idle(_set_initial_sash), add="+")
    panes.bind("<Configure>", lambda _event: panes.after_idle(_set_initial_sash), add="+")


def open_call_record_detail_window(app, record: dict[str, str]) -> None:
    win = tk.Toplevel(app)
    win.title(f"閫氳瘽璇︽儏 - {record.get('customer_name', '未知客户')}")
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

    strategy_box = ttk.LabelFrame(panes, text="Next Strategy", style="Section.TLabelframe", padding=8)
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
        messagebox.showwarning("No record selected", "Please select a call record first.")
        return
    iid = selected[0]
    record = app._call_record_item_by_iid.get(iid)
    if not record:
        messagebox.showwarning("Invalid record", "The selected record is unavailable.")
        return

    customer_name = str(record.get("customer_name", "") or "")
    app._set_dialog_conversation_active_customer(customer_name)
    app._apply_call_record_profile_and_workflow(record)
    app._render_dialog_conversation_history(record.get("call_record", ""), customer_name=customer_name)
    app._append_dialog_session_separator()
    switcher = app._conversation_page_switcher
    if callable(switcher):
        switcher("profile")


