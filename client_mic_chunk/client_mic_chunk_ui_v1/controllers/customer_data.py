from __future__ import annotations

from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    from .call_record_state import (
        apply_call_record_state_to_app,
        apply_call_record_state_to_context,
        build_call_record_state_from_app,
        build_call_record_state_from_context,
        make_empty_call_record_state,
    )
except Exception:
    from call_record_state import (
        apply_call_record_state_to_app,
        apply_call_record_state_to_context,
        build_call_record_state_from_app,
        build_call_record_state_from_context,
        make_empty_call_record_state,
    )

try:
    from .customer_data_events import (
        on_call_record_call as event_on_call_record_call,
        on_call_record_selected as event_on_call_record_selected,
        on_call_record_tree_click as event_on_call_record_tree_click,
        on_customer_data_record_selected as event_on_customer_data_record_selected,
        on_customer_data_tree_click as event_on_customer_data_tree_click,
    )
except Exception:
    from customer_data_events import (
        on_call_record_call as event_on_call_record_call,
        on_call_record_selected as event_on_call_record_selected,
        on_call_record_tree_click as event_on_call_record_tree_click,
        on_customer_data_record_selected as event_on_customer_data_record_selected,
        on_customer_data_tree_click as event_on_customer_data_tree_click,
    )

try:
    from .customer_data_render import (
        apply_call_record_profile_and_workflow as render_apply_call_record_profile_and_workflow,
        clear_call_record_detail as render_clear_call_record_detail,
        clear_customer_data_call_entry_views as render_clear_customer_data_call_entry_views,
        clear_customer_data_profile_table as render_clear_customer_data_profile_table,
        ensure_history_time_style as render_ensure_history_time_style,
        open_call_record_detail_window as render_open_call_record_detail_window,
        open_customer_data_detail_window as render_open_customer_data_detail_window,
        record_has_detail_content as render_record_has_detail_content,
        render_call_record_detail as render_render_call_record_detail,
        render_customer_data_call_entry_views as render_render_customer_data_call_entry_views,
    )
except Exception:
    from customer_data_render import (
        apply_call_record_profile_and_workflow as render_apply_call_record_profile_and_workflow,
        clear_call_record_detail as render_clear_call_record_detail,
        clear_customer_data_call_entry_views as render_clear_customer_data_call_entry_views,
        clear_customer_data_profile_table as render_clear_customer_data_profile_table,
        ensure_history_time_style as render_ensure_history_time_style,
        open_call_record_detail_window as render_open_call_record_detail_window,
        open_customer_data_detail_window as render_open_customer_data_detail_window,
        record_has_detail_content as render_record_has_detail_content,
        render_call_record_detail as render_render_call_record_detail,
        render_customer_data_call_entry_views as render_render_customer_data_call_entry_views,
    )

try:
    from .customer_data_state import (
        apply_customer_data_state_to_app,
        apply_customer_data_state_to_context,
        build_customer_data_state_from_app,
        build_customer_data_state_from_context,
        make_empty_customer_data_state,
    )
except Exception:
    from customer_data_state import (
        apply_customer_data_state_to_app,
        apply_customer_data_state_to_context,
        build_customer_data_state_from_app,
        build_customer_data_state_from_context,
        make_empty_customer_data_state,
    )

try:
    from ..services.case_repository import (
        build_call_record_items as repo_build_call_record_items,
        build_customer_case_cache_by_name as repo_build_customer_case_cache_by_name,
        build_customer_case_cache_by_name_from_dir as _build_customer_case_cache_by_name_from_dir,
        build_visible_customer_records as repo_build_visible_customer_records,
        get_case_source_dirs as _get_case_source_dirs,
        iter_case_files as _iter_case_files,
        lookup_case_payload_by_name as _lookup_case_payload_by_name,
        normalize_customer_lookup_key as _normalize_customer_lookup_key,
        read_customer_case_data_from_files as _read_customer_case_data_from_files,
    )
except Exception:
    from services.case_repository import (
        build_call_record_items as repo_build_call_record_items,
        build_customer_case_cache_by_name as repo_build_customer_case_cache_by_name,
        build_customer_case_cache_by_name_from_dir as _build_customer_case_cache_by_name_from_dir,
        build_visible_customer_records as repo_build_visible_customer_records,
        get_case_source_dirs as _get_case_source_dirs,
        iter_case_files as _iter_case_files,
        lookup_case_payload_by_name as _lookup_case_payload_by_name,
        normalize_customer_lookup_key as _normalize_customer_lookup_key,
        read_customer_case_data_from_files as _read_customer_case_data_from_files,
    )

# 模块级标志：只初始化一次自定义 Treeview 样式，避免每次打开窗口重复配置
_HISTORY_TIME_STYLE_INITIALIZED = False


def _ensure_history_time_style() -> None:
    global _HISTORY_TIME_STYLE_INITIALIZED
    if _HISTORY_TIME_STYLE_INITIALIZED:
        return
    render_ensure_history_time_style()
    _HISTORY_TIME_STYLE_INITIALIZED = True


def _record_has_detail_content(entry: dict[str, str]) -> bool:
    return render_record_has_detail_content(entry)


def _get_active_conversation_context(app):
    tab_id = str(getattr(app, "_active_conversation_tab_id", "") or "")
    if not tab_id:
        return None
    tabs = getattr(app, "_conversation_tabs", {})
    if not isinstance(tabs, dict):
        return None
    return tabs.get(tab_id)


def _bump_call_record_cache_version(app, context=None) -> int:
    state = build_call_record_state_from_app(app)
    current = int(state.cache_version or 0)
    next_version = current + 1
    state.cache_version = next_version
    apply_call_record_state_to_app(app, state)
    if context is not None:
        context_state = build_call_record_state_from_context(context)
        context_state.cache_version = next_version
        apply_call_record_state_to_context(context, context_state)
    return next_version


def _bump_customer_data_cache_version(app, context=None) -> int:
    state = build_customer_data_state_from_app(app)
    current = int(state.cache_version or 0)
    next_version = current + 1
    state.cache_version = next_version
    apply_customer_data_state_to_app(app, state)
    if context is not None:
        context_state = build_customer_data_state_from_context(context)
        context_state.cache_version = next_version
        apply_customer_data_state_to_context(context, context_state)
    return next_version


def _resolve_call_record_from_selection(app, tree: ttk.Treeview | None = None) -> dict[str, str] | None:
    active_tree = tree if isinstance(tree, ttk.Treeview) else app.call_record_tree
    if not isinstance(active_tree, ttk.Treeview):
        return None
    selected = active_tree.selection()
    iid = str(selected[0] if selected else (active_tree.focus() or "") or "")
    if iid:
        record = (getattr(app, "_call_record_item_by_iid", {}) or {}).get(iid)
        if isinstance(record, dict):
            record_id = str(record.get("record_id", "") or "")
            if record_id:
                app._selected_call_record_id = record_id
                app._selected_call_record_cache_version = int(getattr(app, "_call_record_cache_version", 0) or 0)
            return record
    selected_record_id = str(getattr(app, "_selected_call_record_id", "") or "")
    if selected_record_id:
        record = (getattr(app, "_call_record_item_by_id", {}) or {}).get(selected_record_id)
        if isinstance(record, dict):
            return record
    return None


def _get_current_data_dir_signature(app) -> str:
    try:
        data_dir = app._get_data_dir()
    except Exception:
        data_dir = None
    if isinstance(data_dir, Path):
        try:
            return str(data_dir.resolve())
        except Exception:
            return str(data_dir)
    return ""


def _log_customer_data_debug(app, message: str) -> None:
    if not bool(getattr(app, "_debug_customer_data_logging", False)):
        return
    line = f"[{datetime.now().strftime('%H:%M:%S')}] [CUSTOMER_DATA] {message}"
    append_line = getattr(app, "_append_line", None)
    log_widget = getattr(app, "log_text", None)
    if (log_widget is not None) and callable(append_line):
        try:
            append_line(log_widget, line)
        except Exception:
            pass
    workspace_dir = getattr(app, "_workspace_dir", None)
    if workspace_dir is None:
        return
    try:
        log_dir = workspace_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        queue_async_log_write = getattr(app, "_queue_async_log_write", None)
        if callable(queue_async_log_write):
            queue_async_log_write(log_dir / "customer_data_debug.log", line)
    except Exception:
        return


def build_call_record_items(app) -> list[dict[str, str]]:
    return repo_build_call_record_items(app, log_debug=lambda message: _log_customer_data_debug(app, message))


def build_visible_customer_records(app, records: list[dict[str, str]]) -> list[dict[str, str]]:
    return repo_build_visible_customer_records(app, records)


def _resolve_customer_name_from_row(app, tree: ttk.Treeview, row_id: str) -> str:
    app_state = build_customer_data_state_from_app(app)
    payload_by_iid = app_state.case_by_iid or {}
    payload = payload_by_iid.get(row_id)
    if isinstance(payload, dict):
        payload_name = str(payload.get("customer_name", "") or "").strip()
        if payload_name:
            return payload_name
    customer_name = str((app_state.customer_by_iid or {}).get(row_id, "") or "").strip()
    if customer_name:
        return customer_name
    try:
        values = tree.item(row_id, "values")
    except Exception:
        values = ()
    if values:
        customer_name = str(values[0] or "").strip()
    if not customer_name:
        return ""
    cache_by_name = getattr(app, "_customer_data_case_cache_by_name", {}) or {}
    if _lookup_case_payload_by_name(cache_by_name, customer_name) is None:
        try:
            cache_by_name = app._build_customer_case_cache_by_name()
            app_state.case_cache_by_name = dict(cache_by_name)
            apply_customer_data_state_to_app(app, app_state)
            context = _get_active_conversation_context(app)
            if context is not None:
                context_state = build_customer_data_state_from_context(context)
                context_state.case_cache_by_name = dict(cache_by_name)
                apply_customer_data_state_to_context(context, context_state)
        except Exception:
            cache_by_name = getattr(app, "_customer_data_case_cache_by_name", {}) or {}
    if _lookup_case_payload_by_name(cache_by_name, customer_name) is None:
        return ""
    try:
        app_state.customer_by_iid[row_id] = customer_name
        apply_customer_data_state_to_app(app, app_state)
        context = _get_active_conversation_context(app)
        if context is not None:
            context_state = build_customer_data_state_from_context(context)
            context_state.customer_by_iid = dict(app_state.customer_by_iid)
            apply_customer_data_state_to_context(context, context_state)
    except Exception:
        pass
    return customer_name


def _load_customer_case_data_from_disk(app, customer_name: str, *, context=None) -> dict[str, object] | None:
    target_name = str(customer_name or "").strip()
    if not target_name:
        return None
    try:
        data_dir = getattr(context, "data_dir", None) if context is not None else None
        if isinstance(data_dir, Path):
            cache_by_name = _build_customer_case_cache_by_name_from_dir(app, data_dir)
        else:
            cache_by_name = app._build_customer_case_cache_by_name()
    except Exception:
        cache_by_name = {}
    if not isinstance(cache_by_name, dict):
        return None
    if cache_by_name:
        app_state = build_customer_data_state_from_app(app)
        app_state.case_cache_by_name = dict(cache_by_name)
        apply_customer_data_state_to_app(app, app_state)
        target_context = context if context is not None else _get_active_conversation_context(app)
        if target_context is not None:
            context_state = build_customer_data_state_from_context(target_context)
            context_state.case_cache_by_name = dict(cache_by_name)
            apply_customer_data_state_to_context(target_context, context_state)
        _bump_customer_data_cache_version(app, target_context)
        if target_name and target_name == str(getattr(app, "_selected_customer_name", "") or "").strip():
            app_state = build_customer_data_state_from_app(app)
            app_state.selected_cache_version = int(getattr(app, "_customer_data_cache_version", 0) or 0)
            apply_customer_data_state_to_app(app, app_state)
            if target_context is not None:
                context_state = build_customer_data_state_from_context(target_context)
                context_state.selected_cache_version = int(getattr(app, "_selected_customer_cache_version", 0) or 0)
                apply_customer_data_state_to_context(target_context, context_state)
    payload = _lookup_case_payload_by_name(cache_by_name, target_name)
    if isinstance(payload, dict):
        return payload
    return None


def _get_customer_case_data_for_context(
    app,
    customer_name: str,
    *,
    context=None,
    prefer_fresh: bool = False,
) -> dict[str, object] | None:
    target_name = str(customer_name or "").strip()
    if not target_name:
        return None

    if context is not None and (not prefer_fresh):
        context_cache = getattr(context, "customer_data_case_cache_by_name", {}) or {}
        payload = _lookup_case_payload_by_name(context_cache, target_name)
        if isinstance(payload, dict):
            return payload

    if not prefer_fresh:
        app_cache = getattr(app, "_customer_data_case_cache_by_name", {}) or {}
        payload = _lookup_case_payload_by_name(app_cache, target_name)
        if isinstance(payload, dict):
            return payload

    return _load_customer_case_data_from_disk(app, target_name, context=context)


def mark_conversation_tab_data_dirty(
    app,
    *,
    tab_id: str = "",
    call_records: bool = True,
    customer_data: bool = True,
) -> None:
    target_id = str(tab_id or getattr(app, "_active_conversation_tab_id", "") or "")
    if not target_id:
        return
    tabs = getattr(app, "_conversation_tabs", {})
    if not isinstance(tabs, dict):
        return
    context = tabs.get(target_id)
    if context is None:
        return
    if call_records:
        call_record_state = build_call_record_state_from_context(context)
        call_record_state.list_dirty = True
        call_record_state.view_loaded = False
        call_record_state.selected_record_id = ""
        call_record_state.selected_cache_version = 0
        apply_call_record_state_to_context(context, call_record_state)
    if customer_data:
        customer_state = build_customer_data_state_from_context(context)
        customer_state.list_dirty = True
        customer_state.view_loaded = False
        customer_state.selected_customer_name = ""
        customer_state.selected_cache_version = 0
        apply_customer_data_state_to_context(context, customer_state)
        context.customer_data_last_render_key = ""


def render_call_record_detail(app, record: dict[str, str]) -> None:
    render_render_call_record_detail(app, record, log_debug=lambda message: _log_customer_data_debug(app, message))

def clear_call_record_detail(app, message: str = "请选择左侧通话记录") -> None:
    render_clear_call_record_detail(app, message)

def apply_call_record_profile_and_workflow(app, record: dict[str, str]) -> None:
    render_apply_call_record_profile_and_workflow(app, record)


def load_call_records_into_list(app, force_reload: bool = False) -> None:
    tree = app.call_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    context = _get_active_conversation_context(app)
    data_dir_text = ""
    try:
        data_dir = app._get_data_dir()
        data_dir_text = str(data_dir.resolve()) if isinstance(data_dir, Path) else str(data_dir or "")
    except Exception:
        data_dir_text = "-"
    _log_customer_data_debug(
        app,
        f"call-record load-start visible={getattr(app, '_active_conversation_tab_id', '') or '-'} "
        f"bound={getattr(app, '_bound_conversation_tab_id', '') or '-'} "
        f"runtime={getattr(app, '_runtime_conversation_tab_id', '') or '-'} "
        f"context={getattr(context, 'tab_id', '') if context is not None else '-'} "
        f"title={getattr(context, 'title', '') if context is not None else '-'} "
        f"force_reload={int(bool(force_reload))} data_dir={data_dir_text}",
    )
    context_state = build_call_record_state_from_context(context) if context is not None else make_empty_call_record_state()
    source_signature = _get_current_data_dir_signature(app)
    if str(context_state.source_signature or "") != source_signature:
        if context is not None:
            _log_customer_data_debug(
                app,
                f"call-record source-changed invalidate "
                f"old={context_state.source_signature or '-'} new={source_signature or '-'} "
                f"context={getattr(context, 'tab_id', '') or '-'} title={getattr(context, 'title', '') or '-'}",
            )
        context_state = make_empty_call_record_state()
        context_state.list_dirty = True
        if context is not None:
            apply_call_record_state_to_context(context, context_state)
    tree_children = list(tree.get_children())
    context_item_by_iid = dict(context_state.item_by_iid or {})
    cached_view_consistent = True
    if context is not None:
        cached_view_consistent = (
            len(tree_children) == len(context_item_by_iid)
            and (set(tree_children) == set(context_item_by_iid.keys()))
        )
    if (
        (not force_reload)
        and (context is not None)
        and (not bool(context_state.list_dirty))
        and bool(context_state.view_loaded)
        and cached_view_consistent
    ):
        apply_call_record_state_to_app(app, context_state)
        if int(context_state.selected_cache_version or 0) == int(getattr(app, "_call_record_cache_version", 0) or 0):
            context_state.selected_cache_version = int(getattr(app, "_call_record_cache_version", 0) or 0)
            apply_call_record_state_to_app(app, context_state)
        else:
            context_state.selected_record_id = ""
            context_state.selected_cache_version = 0
            apply_call_record_state_to_app(app, context_state)
        if tree.get_children():
            target_iid = ""
            selected_record_id = str(getattr(app, "_selected_call_record_id", "") or "")
            if selected_record_id:
                for iid, item in (getattr(app, "_call_record_item_by_iid", {}) or {}).items():
                    if str(item.get("record_id", "") or "") == selected_record_id:
                        target_iid = iid
                        break
            if (not target_iid) and tree.selection():
                target_iid = str(tree.selection()[0] or "")
            if (not target_iid) and tree.focus():
                target_iid = str(tree.focus() or "")
            if (not target_iid):
                children = tree.get_children()
                target_iid = str(children[0] or "") if children else ""
            if target_iid:
                try:
                    tree.selection_set(target_iid)
                    tree.focus(target_iid)
                except Exception:
                    pass
                _log_customer_data_debug(
                    app,
                    f"call-record cached-view restore target_iid={target_iid} "
                    f"selected_record_id={selected_record_id} "
                    f"children={len(tree.get_children())}",
                )
                app._on_call_record_selected(apply_profile_and_workflow=False)
        return
    if (
        (not force_reload)
        and (context is not None)
        and (not bool(context_state.list_dirty))
        and bool(context_state.view_loaded)
        and (not cached_view_consistent)
    ):
        _log_customer_data_debug(
            app,
            f"call-record cached-view mismatch force-reload "
            f"tree_children={len(tree_children)} "
            f"context_items={len(context_item_by_iid)}",
        )
    tree.delete(*tree.get_children())
    app._call_record_item_by_iid.clear()
    app._call_record_item_by_id.clear()
    previous_selected_record_id = str(getattr(app, "_selected_call_record_id", "") or "")
    items: list[dict[str, str]] = []
    use_cached_items = (not force_reload) and (context is not None) and (not bool(context_state.list_dirty))
    if use_cached_items:
        items = list(context_state.items_cache or [])
    if not use_cached_items:
        items = app._build_call_record_items()
        if context is not None:
            context_state.items_cache = list(items)
            context_state.list_dirty = False
            context_state.source_signature = source_signature
            apply_call_record_state_to_context(context, context_state)
        _bump_call_record_cache_version(app, context)
    if not items:
        if context is not None:
            context_state = build_call_record_state_from_context(context)
            context_state.items_cache = []
            context_state.list_dirty = False
            context_state.view_loaded = True
            context_state.cache_version = int(getattr(app, "_call_record_cache_version", 0) or 0)
            context_state.source_signature = source_signature
            context_state.item_by_iid = {}
            context_state.item_by_id = {}
            context_state.selected_record_id = ""
            context_state.selected_cache_version = 0
            apply_call_record_state_to_context(context, context_state)
        empty_state = build_call_record_state_from_app(app)
        empty_state.items_cache = []
        empty_state.list_dirty = False
        empty_state.view_loaded = True
        empty_state.cache_version = int(getattr(app, "_call_record_cache_version", 0) or 0)
        empty_state.source_signature = source_signature
        empty_state.item_by_iid = {}
        empty_state.item_by_id = {}
        empty_state.selected_record_id = ""
        empty_state.selected_cache_version = 0
        apply_call_record_state_to_app(app, empty_state)
        app._clear_call_record_detail("Data 目录下暂时无通话记录")
        return
    first_iid = ""
    preferred_iid = ""
    for idx, item in enumerate(items):
        try:
            iid = f"rec_{idx}"
            row_tag = "record_even" if idx % 2 == 0 else "record_odd"
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
                tags=(row_tag,),
            )
            app._call_record_item_by_iid[iid] = item
            record_id = str(item.get("record_id", "") or "")
            if record_id:
                app._call_record_item_by_id[record_id] = item
            if not first_iid:
                first_iid = iid
            if previous_selected_record_id and (record_id == previous_selected_record_id):
                preferred_iid = iid
        except Exception as exc:
            app._append_line(
                app.log_text,
                f"[{datetime.now().strftime('%H:%M:%S')}] [CALL_RECORD] read failed: {exc}",
            )
    target_iid = preferred_iid or first_iid
    if target_iid:
        _log_customer_data_debug(
            app,
            f"call-record load target_iid={target_iid} "
            f"items={len(items)} "
            f"cache_version={int(getattr(app, '_call_record_cache_version', 0) or 0)} "
            f"previous_selected_record_id={previous_selected_record_id}",
        )
        tree.selection_set(target_iid)
        tree.focus(target_iid)
        selected_item = app._call_record_item_by_iid.get(target_iid, {})
        app_state = build_call_record_state_from_app(app)
        app_state.items_cache = list(items)
        app_state.list_dirty = False
        app_state.view_loaded = True
        app_state.cache_version = int(getattr(app, "_call_record_cache_version", 0) or 0)
        app_state.source_signature = source_signature
        app_state.item_by_iid = dict(getattr(app, "_call_record_item_by_iid", {}) or {})
        app_state.item_by_id = dict(getattr(app, "_call_record_item_by_id", {}) or {})
        app_state.selected_record_id = str(selected_item.get("record_id", "") or "")
        app_state.selected_cache_version = int(getattr(app, "_call_record_cache_version", 0) or 0)
        apply_call_record_state_to_app(app, app_state)
        app._on_call_record_selected(apply_profile_and_workflow=False)
        if context is not None:
            context_state = build_call_record_state_from_app(app)
            context_state.items_cache = list(items)
            context_state.list_dirty = False
            context_state.view_loaded = True
            context_state.source_signature = source_signature
            apply_call_record_state_to_context(context, context_state)
    else:
        if context is not None:
            context_state = build_call_record_state_from_context(context)
            context_state.items_cache = list(items)
            context_state.list_dirty = False
            context_state.view_loaded = True
            context_state.cache_version = int(getattr(app, "_call_record_cache_version", 0) or 0)
            context_state.source_signature = source_signature
            context_state.item_by_iid = dict(getattr(app, "_call_record_item_by_iid", {}) or {})
            context_state.item_by_id = dict(getattr(app, "_call_record_item_by_id", {}) or {})
            context_state.selected_record_id = ""
            context_state.selected_cache_version = 0
            apply_call_record_state_to_context(context, context_state)
        app_state = build_call_record_state_from_app(app)
        app_state.items_cache = list(items)
        app_state.list_dirty = False
        app_state.view_loaded = True
        app_state.cache_version = int(getattr(app, "_call_record_cache_version", 0) or 0)
        app_state.source_signature = source_signature
        app_state.selected_record_id = ""
        app_state.selected_cache_version = 0
        apply_call_record_state_to_app(app, app_state)
        app._clear_call_record_detail("记录读取失败")


def clear_customer_data_profile_table(app, message: str = "请选择左侧通话记录") -> None:
    render_clear_customer_data_profile_table(app, message)


def clear_customer_data_call_entry_views(app, message: str = "请选择左侧通话记录") -> None:
    render_clear_customer_data_call_entry_views(app, message)


def render_customer_data_call_entry_views(app, records: list[dict[str, str]]) -> None:
    render_render_customer_data_call_entry_views(app, records)


def build_customer_case_cache_by_name(app) -> dict[str, dict[str, object]]:
    return repo_build_customer_case_cache_by_name(app)


def get_selected_customer_case_data(app, ensure_default_selection: bool = True) -> dict[str, object] | None:
    cache = app._customer_data_case_cache_by_name
    if not cache:
        cache = app._build_customer_case_cache_by_name()
        app._customer_data_case_cache_by_name = cache
    if not cache:
        return None

    selected_name = str(getattr(app, "_selected_customer_name", "") or "").strip()
    payload = _lookup_case_payload_by_name(cache, selected_name)
    if isinstance(payload, dict):
        return payload

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

    payload = _lookup_case_payload_by_name(cache, selected_name)
    if isinstance(payload, dict):
        return payload

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
    if isinstance(app.conversation_customer_profile_text, ScrolledText):
        app._set_text_content(app.conversation_customer_profile_text, profile_text)
    app._refresh_runtime_system_prompt_only()
    return True

def load_customer_data_records_into_list(app, force_reload: bool = False) -> None:
    tree = app.customer_data_record_tree
    if not isinstance(tree, ttk.Treeview):
        return
    context = _get_active_conversation_context(app)
    data_dir_text = ""
    try:
        data_dir = app._get_data_dir()
        data_dir_text = str(data_dir.resolve()) if isinstance(data_dir, Path) else str(data_dir or "")
    except Exception:
        data_dir_text = "-"
    _log_customer_data_debug(
        app,
        f"customer-data load-start visible={getattr(app, '_active_conversation_tab_id', '') or '-'} "
        f"bound={getattr(app, '_bound_conversation_tab_id', '') or '-'} "
        f"runtime={getattr(app, '_runtime_conversation_tab_id', '') or '-'} "
        f"context={getattr(context, 'tab_id', '') if context is not None else '-'} "
        f"title={getattr(context, 'title', '') if context is not None else '-'} "
        f"force_reload={int(bool(force_reload))} data_dir={data_dir_text}",
    )
    context_state = build_customer_data_state_from_context(context) if context is not None else make_empty_customer_data_state()
    source_signature = _get_current_data_dir_signature(app)
    if str(context_state.source_signature or "") != source_signature:
        if context is not None:
            _log_customer_data_debug(
                app,
                f"customer-data source-changed invalidate "
                f"old={context_state.source_signature or '-'} new={source_signature or '-'} "
                f"context={getattr(context, 'tab_id', '') or '-'} title={getattr(context, 'title', '') or '-'}",
            )
        context_state = make_empty_customer_data_state()
        context_state.list_dirty = True
        if context is not None:
            apply_customer_data_state_to_context(context, context_state)
    if (
        (not force_reload)
        and (context is not None)
        and (not bool(context_state.list_dirty))
        and bool(context_state.view_loaded)
    ):
        apply_customer_data_state_to_app(app, context_state)
        if int(context_state.selected_cache_version or 0) == int(getattr(app, "_customer_data_cache_version", 0) or 0):
            context_state.selected_cache_version = int(getattr(app, "_customer_data_cache_version", 0) or 0)
            apply_customer_data_state_to_app(app, context_state)
        else:
            context_state.selected_customer_name = ""
            context_state.selected_cache_version = 0
            apply_customer_data_state_to_app(app, context_state)
        if not tree.get_children():
            for idx, (customer_name, _latest_time) in enumerate(list(context_state.items_cache or [])):
                iid = f"customer_data_{idx}"
                row_tag = "record_even" if idx % 2 == 0 else "record_odd"
                try:
                    tree.insert(
                        "",
                        "end",
                        iid=iid,
                        values=(customer_name, "\u2139", "\u260E", "\u2715"),
                        tags=(row_tag,),
                    )
                except Exception:
                    continue
            selected_name = str(getattr(app, "_selected_customer_name", "") or "")
            target_iid = ""
            for iid, customer_name in (getattr(app, "_customer_data_customer_by_iid", {}) or {}).items():
                if str(customer_name or "") == selected_name:
                    target_iid = iid
                    break
            if (not target_iid) and tree.get_children():
                target_iid = str(tree.get_children()[0] or "")
            if target_iid:
                try:
                    tree.selection_set(target_iid)
                    tree.focus(target_iid)
                except Exception:
                    pass
        return
    previous_selected_name = ""
    selected = tree.selection()
    if selected:
        previous_selected_name = str(app._customer_data_customer_by_iid.get(selected[0], "")).strip()
    if not previous_selected_name:
        previous_selected_name = str(getattr(app, "_selected_customer_name", "") or "").strip()
    tree.delete(*tree.get_children())
    app._customer_data_customer_by_iid.clear()
    app._customer_data_case_by_iid.clear()
    cache_by_name: dict[str, dict[str, object]] = {}
    customer_items: list[tuple[str, str]] = []
    use_cached_items = (not force_reload) and (context is not None) and (not bool(context_state.list_dirty))
    if use_cached_items:
        cache_by_name = dict(context_state.case_cache_by_name or {})
        customer_items = list(context_state.items_cache or [])
    if not use_cached_items:
        cache_by_name = app._build_customer_case_cache_by_name()
        customer_items = []
        for customer_name, payload in cache_by_name.items():
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
        if context is not None:
            context_state.case_cache_by_name = dict(cache_by_name)
            context_state.items_cache = list(customer_items)
            context_state.list_dirty = False
            context_state.source_signature = source_signature
            apply_customer_data_state_to_context(context, context_state)
        _bump_customer_data_cache_version(app, context)
    app_state = build_customer_data_state_from_app(app)
    app_state.case_cache_by_name = dict(cache_by_name)
    app_state.source_signature = source_signature
    apply_customer_data_state_to_app(app, app_state)
    if not app._customer_data_case_cache_by_name:
        if context is not None:
            context_state = build_customer_data_state_from_context(context)
            context_state.case_cache_by_name = {}
            context_state.items_cache = []
            context_state.list_dirty = False
            context_state.view_loaded = True
            context_state.cache_version = int(getattr(app, "_customer_data_cache_version", 0) or 0)
            context_state.source_signature = source_signature
            context_state.selected_customer_name = ""
            context_state.selected_cache_version = 0
            context_state.customer_by_iid = {}
            context_state.case_by_iid = {}
            apply_customer_data_state_to_context(context, context_state)
        app_state = build_customer_data_state_from_app(app)
        app_state.items_cache = []
        app_state.list_dirty = False
        app_state.view_loaded = True
        app_state.cache_version = int(getattr(app, "_customer_data_cache_version", 0) or 0)
        app_state.source_signature = source_signature
        app_state.customer_by_iid = {}
        app_state.case_by_iid = {}
        app_state.case_cache_by_name = {}
        app_state.selected_customer_name = ""
        app_state.selected_cache_version = 0
        apply_customer_data_state_to_app(app, app_state)
        app._clear_customer_data_profile_table("Data 目录下暂时无通话记录")
        return
    first_iid = ""
    preferred_iid = ""
    for idx, (customer_name, _latest_time) in enumerate(customer_items):
        try:
            iid = f"customer_data_{idx}"
            row_tag = "record_even" if idx % 2 == 0 else "record_odd"
            tree.insert(
                "",
                "end",
                iid=iid,
                values=(customer_name, "\u2139", "\u260E", "\u2715"),
                tags=(row_tag,),
            )
            app_state = build_customer_data_state_from_app(app)
            app_state.customer_by_iid[iid] = customer_name
            payload = _lookup_case_payload_by_name(cache_by_name, customer_name)
            if isinstance(payload, dict):
                app_state.case_by_iid[iid] = payload
            apply_customer_data_state_to_app(app, app_state)
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
        app_state = build_customer_data_state_from_app(app)
        app_state.items_cache = list(customer_items)
        app_state.list_dirty = False
        app_state.view_loaded = True
        app_state.cache_version = int(getattr(app, "_customer_data_cache_version", 0) or 0)
        app_state.source_signature = source_signature
        app_state.selected_customer_name = str(app_state.customer_by_iid.get(target_iid, "")).strip()
        app_state.selected_cache_version = int(getattr(app, "_customer_data_cache_version", 0) or 0)
        apply_customer_data_state_to_app(app, app_state)
        app._on_customer_data_record_selected()
        if context is not None:
            apply_customer_data_state_to_context(context, build_customer_data_state_from_app(app))
    else:
        if context is not None:
            context_state = build_customer_data_state_from_context(context)
            context_state.items_cache = list(customer_items)
            context_state.list_dirty = False
            context_state.view_loaded = True
            context_state.cache_version = int(getattr(app, "_customer_data_cache_version", 0) or 0)
            context_state.source_signature = source_signature
            context_state.selected_customer_name = ""
            context_state.selected_cache_version = 0
            context_state.customer_by_iid = dict(getattr(app, "_customer_data_customer_by_iid", {}) or {})
            context_state.case_by_iid = dict(getattr(app, "_customer_data_case_by_iid", {}) or {})
            context_state.case_cache_by_name = dict(getattr(app, "_customer_data_case_cache_by_name", {}) or {})
            apply_customer_data_state_to_context(context, context_state)
        app_state = build_customer_data_state_from_app(app)
        app_state.items_cache = list(customer_items)
        app_state.list_dirty = False
        app_state.view_loaded = True
        app_state.cache_version = int(getattr(app, "_customer_data_cache_version", 0) or 0)
        app_state.source_signature = source_signature
        app_state.selected_customer_name = ""
        app_state.selected_cache_version = 0
        apply_customer_data_state_to_app(app, app_state)
        app._clear_customer_data_profile_table("记录读取失败")


def on_customer_data_record_selected(app, _event=None) -> None:
    event_on_customer_data_record_selected(
        app,
        _event=_event,
        resolve_customer_name_from_row=_resolve_customer_name_from_row,
        get_active_conversation_context=_get_active_conversation_context,
        get_customer_case_data_for_context=_get_customer_case_data_for_context,
        log_debug=_log_customer_data_debug,
    )


def on_customer_data_tree_click(app, event=None) -> str | None:
    return event_on_customer_data_tree_click(
        app,
        event=event,
        resolve_customer_name_from_row=_resolve_customer_name_from_row,
        get_active_conversation_context=_get_active_conversation_context,
        read_customer_case_data_from_files=_read_customer_case_data_from_files,
        get_customer_case_data_for_context=_get_customer_case_data_for_context,
        lookup_case_payload_by_name=_lookup_case_payload_by_name,
        delete_customer_by_name=delete_customer_by_name,
        log_debug=_log_customer_data_debug,
    )


def on_customer_data_tree_double_click(app, event=None) -> None:
    pass


def open_customer_data_detail_window(
    app,
    customer_name: str,
    *,
    context=None,
    data_dir: Path | None = None,
    case_data: dict[str, object] | None = None,
) -> None:
    render_open_customer_data_detail_window(
        app,
        customer_name,
        case_data=case_data,
        read_case_data=lambda name: _read_customer_case_data_from_files(app, name, data_dir=data_dir),
        save_case_data=lambda *, path, customer_name, created_time, updated_time, profile_text, records: app._save_customer_case_file(
            path=path,
            customer_name=customer_name,
            created_time=created_time,
            updated_time=updated_time,
            profile_text=profile_text,
            records=records,
        ),
        after_save=lambda name: _after_customer_detail_saved(app, name),
        log_debug=lambda message: _log_customer_data_debug(app, message),
    )


def open_call_record_detail_window(app, record: dict[str, str]) -> None:
    render_open_call_record_detail_window(app, record)


def _after_customer_detail_saved(app, customer_name: str) -> None:
    target_name = str(customer_name or "").strip()
    app._mark_conversation_tab_data_dirty(call_records=True, customer_data=True)
    app._customer_data_last_render_key = ""
    try:
        app._load_customer_data_records_into_list(force_reload=True)
    except Exception:
        pass
    try:
        tree = getattr(app, "customer_data_record_tree", None)
        if isinstance(tree, ttk.Treeview):
            target_iid = ""
            customer_by_iid = getattr(app, "_customer_data_customer_by_iid", {}) or {}
            for iid, name in customer_by_iid.items():
                if str(name or "").strip() == target_name:
                    target_iid = str(iid or "")
                    break
            if target_iid:
                tree.selection_set(target_iid)
                tree.focus(target_iid)
                tree.see(target_iid)
        app._selected_customer_name = target_name
        app._on_customer_data_record_selected()
    except Exception:
        pass

def on_call_record_selected(app, _event=None, apply_profile_and_workflow: bool = False) -> None:
    event_on_call_record_selected(
        app,
        _event=_event,
        get_active_conversation_context=_get_active_conversation_context,
        log_debug=_log_customer_data_debug,
    )


def on_call_record_tree_click(app, event=None) -> str | None:
    return event_on_call_record_tree_click(app, event=event, log_debug=_log_customer_data_debug)


def on_call_record_call(app) -> None:
    event_on_call_record_call(app, resolve_call_record_from_selection=_resolve_call_record_from_selection)


def delete_customer_by_name(app, customer_name: str) -> None:
    confirmed = messagebox.askyesno(
        "确认删除",
        f"确定要删除客户「{customer_name}」的所有数据吗？\n此操作不可恢复。",
    )
    if not confirmed:
        return
    data_dir = app._get_data_dir()
    deleted_count = 0
    for path in list(data_dir.glob("*.txt")):
        try:
            case_data = app._read_customer_case_file(path)
            if str(case_data.get("customer_name", "") or "") == customer_name:
                path.unlink()
                deleted_count += 1
        except Exception:
            pass
    if deleted_count == 0:
        messagebox.showinfo("提示", f"未找到客户「{customer_name}」的数据文件。")
        return
    app._mark_conversation_tab_data_dirty(call_records=True, customer_data=True)
    app._load_customer_data_records_into_list(force_reload=True)
    app._clear_customer_data_profile_table("请选择左侧通话记录")
