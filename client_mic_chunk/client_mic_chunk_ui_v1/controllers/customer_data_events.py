from __future__ import annotations

from datetime import datetime

from tkinter import messagebox, ttk

try:
    from .call_record_state import (
        apply_call_record_state_to_app,
        apply_call_record_state_to_context,
        build_call_record_state_from_app,
    )
    from .customer_data_state import (
        apply_customer_data_state_to_app,
        apply_customer_data_state_to_context,
        build_customer_data_state_from_app,
    )
except Exception:
    from call_record_state import (
        apply_call_record_state_to_app,
        apply_call_record_state_to_context,
        build_call_record_state_from_app,
    )
    from customer_data_state import (
        apply_customer_data_state_to_app,
        apply_customer_data_state_to_context,
        build_customer_data_state_from_app,
    )


def on_customer_data_record_selected(
    app,
    _event=None,
    *,
    resolve_customer_name_from_row,
    get_active_conversation_context,
    get_customer_case_data_for_context,
    log_debug,
) -> None:
    tree = app.customer_data_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    selected = tree.selection()
    if not selected:
        focus_iid = str(tree.focus() or "")
        if focus_iid and resolve_customer_name_from_row(app, tree, focus_iid):
            selected = (focus_iid,)
        else:
            log_debug(app, "select skipped: no selection/focus")
            return
    iid = selected[0]
    customer_name = resolve_customer_name_from_row(app, tree, iid)
    if not customer_name:
        log_debug(app, f"select missing customer iid={iid}")
        app._clear_customer_data_profile_table()
        return
    app_state = build_customer_data_state_from_app(app)
    app_state.selected_customer_name = customer_name
    app_state.selected_cache_version = int(getattr(app, "_customer_data_cache_version", 0) or 0)
    apply_customer_data_state_to_app(app, app_state)
    context = get_active_conversation_context(app)
    if context is not None:
        apply_customer_data_state_to_context(context, app_state)
    case_data = get_customer_case_data_for_context(app, customer_name, context=context, prefer_fresh=False)
    row_payload = (getattr(app, "_customer_data_case_by_iid", {}) or {}).get(iid)
    if isinstance(row_payload, dict):
        case_data = row_payload
    if not isinstance(case_data, dict):
        log_debug(app, f"select stale customer={customer_name}")
        app._clear_customer_data_profile_table("记录失效，请刷新")
        return
    profile_text = str(case_data.get("customer_profile", "") or "")
    records = list(case_data.get("records", []))
    records = app.build_visible_customer_records(records) if callable(getattr(app, "build_visible_customer_records", None)) else records
    render_key_parts: list[str] = [customer_name, str(case_data.get("updated_time", "") or ""), profile_text]
    for entry in records:
        render_key_parts.append(str(entry.get("call_time", "") or ""))
        render_key_parts.append(str(entry.get("summary", "") or ""))
        render_key_parts.append(str(entry.get("commitments", "") or ""))
        render_key_parts.append(str(entry.get("strategy", "") or ""))
    render_key = "\x1f".join(render_key_parts)
    if render_key == app._customer_data_last_render_key:
        log_debug(app, f"select no-op customer={customer_name} render_key=unchanged")
        return
    log_debug(app, f"select render customer={customer_name} records={len(records)}")
    app._customer_data_last_render_key = render_key
    profile_tree = app.customer_data_profile_table
    if isinstance(profile_tree, ttk.Treeview):
        app._fill_profile_table_from_text(profile_tree, profile_text=profile_text, auto_height=True)

    def _deferred_render() -> None:
        if app._customer_data_last_render_key != render_key:
            return
        app._render_customer_data_call_entry_views(records)

    app.after_idle(_deferred_render)


def on_customer_data_tree_click(
    app,
    event=None,
    *,
    resolve_customer_name_from_row,
    get_active_conversation_context,
    read_customer_case_data_from_files,
    get_customer_case_data_for_context,
    lookup_case_payload_by_name,
    delete_customer_by_name,
    log_debug,
) -> str | None:
    tree = app.customer_data_record_tree
    if (event is None) or (not isinstance(tree, ttk.Treeview)):
        log_debug(app, "click ignored: invalid event/tree")
        return None
    x = int(getattr(event, "x", 0))
    y = int(getattr(event, "y", 0))
    row_id = tree.identify_row(y)
    raw_col_id = str(tree.identify_column(x) or "")
    raw_region = str(tree.identify("region", x, y) or "")
    log_debug(app, f"click raw x={x} y={y} row={row_id or '-'} col={raw_col_id or '-'} region={raw_region or '-'}")
    if not row_id:
        log_debug(app, "click ignored: no row hit")
        return None

    def _hit_column(target_col: str) -> bool:
        try:
            bbox = tree.bbox(row_id, target_col)
        except Exception:
            return False
        if not bbox:
            return False
        cell_x, cell_y, cell_w, cell_h = bbox
        return (cell_x <= x < (cell_x + cell_w)) and (cell_y <= y < (cell_y + cell_h))

    col_id = ""
    for candidate in ("#2", "#3", "#4", "#1"):
        if _hit_column(candidate):
            col_id = candidate
            break
    if not col_id:
        col_id = raw_col_id
    if col_id not in {"#1", "#2", "#3", "#4"}:
        log_debug(app, f"click ignored: unsupported col={col_id or '-'} row={row_id}")
        return None

    current_selected = tree.selection()
    is_selected = bool(current_selected and (current_selected[0] == row_id))
    customer_name = resolve_customer_name_from_row(app, tree, row_id)
    if not customer_name:
        log_debug(app, f"click ignored: unresolved row={row_id}")
        return None
    log_debug(app, f"click hit row={row_id} col={col_id} customer={customer_name or ''} selected={is_selected}")
    if col_id == "#1":
        if not is_selected:
            tree.selection_set(row_id)
        tree.focus(row_id)
        app_state = build_customer_data_state_from_app(app)
        app_state.selected_customer_name = customer_name
        apply_customer_data_state_to_app(app, app_state)
        app._on_customer_data_record_selected()
        return "break"
    if col_id == "#4":
        if not is_selected:
            tree.selection_set(row_id)
        tree.focus(row_id)
        app_state = build_customer_data_state_from_app(app)
        app_state.selected_customer_name = customer_name
        apply_customer_data_state_to_app(app, app_state)
        delete_customer_by_name(app, customer_name)
        return "break"
    if col_id == "#2":
        tree.focus(row_id)
        log_debug(app, f"detail click customer={customer_name}")
        current_context = get_active_conversation_context(app)
        current_data_dir = getattr(current_context, "data_dir", None) if current_context is not None else None
        current_case_data = (getattr(app, "_customer_data_case_by_iid", {}) or {}).get(row_id)
        if not isinstance(current_case_data, dict):
            current_case_data = read_customer_case_data_from_files(app, customer_name, data_dir=current_data_dir)
        if not isinstance(current_case_data, dict):
            current_case_data = get_customer_case_data_for_context(
                app,
                customer_name,
                context=current_context,
                prefer_fresh=True,
            )

        def _open_detail_window(
            _name=str(customer_name),
            _context=current_context,
            _data_dir=current_data_dir,
            _case_data=current_case_data,
        ) -> None:
            try:
                app._open_customer_data_detail_window(
                    _name,
                    context=_context,
                    data_dir=_data_dir,
                    case_data=_case_data,
                )
                log_debug(app, f"detail opened customer={_name}")
            except Exception as exc:
                log_debug(app, f"detail failed customer={_name} error={exc}")

        app.after_idle(_open_detail_window)
        if not is_selected:
            app.after_idle(lambda _iid=row_id: tree.selection_set(_iid))
        app_state = build_customer_data_state_from_app(app)
        app_state.selected_customer_name = customer_name
        apply_customer_data_state_to_app(app, app_state)
        return "break"

    if col_id == "#3":
        is_running = bool(getattr(app._bridge, "running", False)) or (
            str(app.state_var.get() if hasattr(app, "state_var") else "").strip().lower() == "running"
        )
        if is_running:
            log_debug(app, "call-icon blocked immediately: running -> no page switch, no data mutation")
            messagebox.showwarning("当前通话未结束", "当前通话未结束，请挂断后再拨。")
            return "break"

    if not is_selected:
        tree.selection_set(row_id)
    tree.focus(row_id)
    app_state = build_customer_data_state_from_app(app)
    app_state.selected_customer_name = customer_name
    apply_customer_data_state_to_app(app, app_state)
    app._on_customer_data_record_selected()

    app._set_dialog_conversation_active_customer(str(customer_name))
    case_data = lookup_case_payload_by_name(app._customer_data_case_cache_by_name, customer_name)
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

    def _trigger_call_after_switch() -> None:
        log_debug(app, "call-icon clicked -> invoke profile call")
        start_from_call_icon = getattr(app, "_start_from_customer_data_call_icon", None)
        if callable(start_from_call_icon):
            try:
                start_from_call_icon()
                log_debug(app, "start_from_customer_data_call_icon() dispatched")
                return
            except Exception:
                pass
        log_debug(app, "call-icon handler missing -> fallback start")
        app._start_from_conversation_profile()

    switcher = app._conversation_page_switcher
    if callable(switcher):
        switcher("profile")

    app.after_idle(lambda: app.after(120, _trigger_call_after_switch))
    return "break"


def on_call_record_selected(
    app,
    _event=None,
    *,
    get_active_conversation_context,
    log_debug,
) -> None:
    tree = app.call_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    selected = tree.selection()
    if not selected:
        log_debug(app, f"call-record select skipped no-selection focus={str(tree.focus() or '')}")
        app._clear_call_record_detail()
        return
    iid = selected[0]
    record = (getattr(app, "_call_record_item_by_iid", {}) or {}).get(iid)
    if not isinstance(record, dict):
        log_debug(
            app,
            f"call-record select missing-record iid={iid} "
            f"focus={str(tree.focus() or '')} "
            f"selected={list(selected)} "
            f"map_size={len((getattr(app, '_call_record_item_by_iid', {}) or {}))}",
        )
        app._clear_call_record_detail()
        return
    log_debug(
        app,
        "call-record select "
        f"iid={iid} "
        f"focus={str(tree.focus() or '')} "
        f"record_id={str(record.get('record_id', '') or '')} "
        f"time={str(record.get('last_call_time', '') or '')} "
        f"summary_prefix={str(record.get('summary', '') or '')[:60].replace(chr(10), ' ')}",
    )
    app_state = build_call_record_state_from_app(app)
    app_state.selected_record_id = str(record.get("record_id", "") or "")
    app_state.selected_cache_version = int(getattr(app, "_call_record_cache_version", 0) or 0)
    apply_call_record_state_to_app(app, app_state)
    context = get_active_conversation_context(app)
    if context is not None:
        apply_call_record_state_to_context(context, app_state)
    app._render_call_record_detail(record)


def on_call_record_tree_click(app, event=None, *, log_debug) -> str | None:
    tree = app.call_record_tree
    if (event is None) or (not isinstance(tree, ttk.Treeview)):
        return None
    try:
        row_id = str(tree.identify_row(int(getattr(event, "y", 0))) or "")
    except Exception:
        row_id = ""
    log_debug(
        app,
        f"call-record click y={int(getattr(event, 'y', 0) or 0)} "
        f"row_id={row_id or '-'} "
        f"before_selected={list(tree.selection())} "
        f"before_focus={str(tree.focus() or '')}",
    )
    if not row_id:
        return None
    try:
        tree.selection_set(row_id)
        tree.focus(row_id)
    except Exception:
        return None
    record = (getattr(app, "_call_record_item_by_iid", {}) or {}).get(row_id)
    log_debug(
        app,
        "call-record click applied "
        f"row_id={row_id} "
        f"after_selected={list(tree.selection())} "
        f"after_focus={str(tree.focus() or '')} "
        f"record_id={str((record or {}).get('record_id', '') or '')} "
        f"time={str((record or {}).get('last_call_time', '') or '')}",
    )
    app.after_idle(lambda: app._on_call_record_selected(apply_profile_and_workflow=False))
    return None


def on_call_record_call(app, *, resolve_call_record_from_selection) -> None:
    tree = app.call_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    record = resolve_call_record_from_selection(app, tree)
    if not isinstance(record, dict):
        from tkinter import messagebox

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
