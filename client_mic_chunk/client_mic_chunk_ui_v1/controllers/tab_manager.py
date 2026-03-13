from __future__ import annotations

import ctypes
import json
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Iterator

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
    from ..services.tab_registry import (
        read_conversation_tab_registry_entries as svc_read_conversation_tab_registry_entries,
        save_conversation_tab_registry_entries as svc_save_conversation_tab_registry_entries,
    )
except Exception:
    from services.tab_registry import (
        read_conversation_tab_registry_entries as svc_read_conversation_tab_registry_entries,
        save_conversation_tab_registry_entries as svc_save_conversation_tab_registry_entries,
    )


def register_conversation_tab_context(app, context, is_template: bool = False) -> None:
    app._conversation_tabs[context.tab_id] = context
    app._conversation_tab_id_by_frame_name[str(context.tab_frame)] = context.tab_id
    if is_template:
        app._conversation_template_tab_id = context.tab_id


def _log_tab_switch_timing(app, label: str, started_at: float, *, extra: str = "") -> None:
    if not bool(getattr(app, "_debug_tab_perf_logging", False)):
        return
    widget = getattr(app, "log_text", None)
    append_line = getattr(app, "_append_line", None)
    elapsed_ms = (perf_counter() - started_at) * 1000.0
    suffix = f" {extra}" if extra else ""
    line = f"[TAB_PERF] {label} {elapsed_ms:.1f}ms{suffix}"
    if widget is not None and callable(append_line):
        try:
            append_line(widget, line)
        except Exception:
            pass


def _log_tab_context_debug(app, message: str) -> None:
    if not bool(getattr(app, "_debug_customer_data_logging", False)):
        return
    ts_text = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts_text}] [TAB_CTX] {message}"
    widget = getattr(app, "log_text", None)
    append_line = getattr(app, "_append_line", None)
    if widget is not None and callable(append_line):
        try:
            append_line(widget, line)
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


def _show_summary_pending_switch_dialog(app) -> bool:
    parent = getattr(app, "_main_notebook", None) or app
    result = {"continue": False}
    win = tk.Toplevel(parent)
    win.title("提示")
    win.transient(app)
    win.grab_set()
    win.resizable(False, False)
    win.configure(bg="#ffffff")

    frame = ttk.Frame(win, padding=(18, 16, 18, 14), style="Card.TFrame")
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(
        frame,
        text="尚未进行对话总结，继续切换可能丢失对话数据。",
        justify="left",
        wraplength=640,
    ).pack(fill=tk.X)
    btn_row = ttk.Frame(frame, style="Panel.TFrame")
    btn_row.pack(pady=(16, 0))

    def _close(allow_continue: bool) -> None:
        result["continue"] = allow_continue
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass

    ttk.Button(btn_row, text="返回", command=lambda: _close(False)).pack(side=tk.LEFT, padx=(0, 12))
    ttk.Button(btn_row, text="继续", command=lambda: _close(True), style="Primary.TButton").pack(side=tk.LEFT)
    win.protocol("WM_DELETE_WINDOW", lambda: _close(False))
    win.update_idletasks()
    try:
        win.minsize(720, 220)
        px = max(0, int((win.winfo_screenwidth() - win.winfo_width()) / 2))
        py = max(0, int((win.winfo_screenheight() - win.winfo_height()) / 2))
        win.geometry(f"720x220+{px}+{py}")
    except Exception:
        pass
    win.wait_window()
    return bool(result["continue"])


def _should_warn_summary_pending_on_tab_switch(app, selected_tab_name: str) -> bool:
    current_tab_id = str(getattr(app, "_bound_conversation_tab_id", "") or "")
    current_context = app._conversation_tabs.get(current_tab_id) if current_tab_id else None
    current_frame_name = str(getattr(current_context, "tab_frame", "") or "") if current_context is not None else ""
    if not current_tab_id or not current_frame_name or selected_tab_name == current_frame_name:
        return False
    if str(getattr(current_context, "active_page", "profile") or "profile") != "profile":
        return False
    if not bool(getattr(app, "_dialog_summary_pending_warning", False)):
        return False
    if bool(getattr(app, "_allow_next_tab_switch_without_summary", False)):
        return False
    return True


def _is_tab_switch_locked(app) -> bool:
    bridge = getattr(app, "_bridge", None)
    if bool(getattr(bridge, "running", False)):
        return True
    state_var = getattr(app, "state_var", None)
    if state_var is not None:
        try:
            return str(state_var.get() or "").strip().lower() == "running"
        except Exception:
            return False
    return False


def on_main_notebook_tab_click(app, event=None) -> str | None:
    notebook = getattr(app, "_main_notebook", None)
    if (event is None) or (not isinstance(notebook, ttk.Notebook)):
        return None
    try:
        target_tab = str(notebook.index(f"@{int(getattr(event, 'x', 0))},{int(getattr(event, 'y', 0))}"))
    except Exception:
        return None
    tabs = notebook.tabs()
    if not (0 <= int(target_tab or -1) < len(tabs)):
        return None
    selected_tab_name = str(tabs[int(target_tab)] or "")
    if not _should_warn_summary_pending_on_tab_switch(app, selected_tab_name):
        return None
    allow_switch = _show_summary_pending_switch_dialog(app)
    if not allow_switch:
        return "break"
    app._allow_next_tab_switch_without_summary = True
    return None


def _get_locked_conversation_tab_id(app) -> str:
    return str(
        getattr(app, "_runtime_conversation_tab_id", "") or getattr(app, "_active_conversation_tab_id", "") or ""
    )


def _set_text_widget_quiet(widget, text: str = "", *, disabled: bool | None = None) -> None:
    if not isinstance(widget, (tk.Text, ScrolledText)):
        return
    try:
        prev_state = str(widget.cget("state"))
    except Exception:
        prev_state = "normal"
    try:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        if text:
            widget.insert("1.0", text)
        final_state = prev_state if disabled is None else ("disabled" if disabled else "normal")
        widget.configure(state=final_state if final_state in {"normal", "disabled"} else "normal")
    except Exception:
        return


def _hibernate_inactive_tab_widgets(context) -> None:
    shell = getattr(context, "conversation_shell", None)
    if isinstance(shell, ttk.Frame):
        try:
            shell.pack_forget()
        except Exception:
            pass
    _set_text_widget_quiet(getattr(context, "conversation_strategy_history_text", None), "", disabled=True)
    _set_text_widget_quiet(getattr(context, "customer_data_call_entries_wrap", None), "", disabled=True)
    _set_text_widget_quiet(getattr(context, "call_record_summary_text", None), "", disabled=True)
    _set_text_widget_quiet(getattr(context, "dialog_intent_text", None), "", disabled=True)
    _set_text_widget_quiet(getattr(context, "dialog_conversation_text", None), "", disabled=False)


def _restore_active_tab_heavy_widgets(app, target) -> None:
    shell = getattr(target, "conversation_shell", None)
    if isinstance(shell, ttk.Frame):
        try:
            if not shell.winfo_manager():
                shell.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        except Exception:
            pass
    try:
        app._refresh_dialog_conversation_for_active_customer()
    except Exception:
        pass
    try:
        app._sync_dialog_intent_strategy_for_active_customer()
    except Exception:
        pass
    try:
        app._render_conversation_strategy_history_panel()
    except Exception:
        pass

    active_page = str(getattr(target, "active_page", "profile") or "profile")
    if active_page == "call_record":
        try:
            app._load_call_records_into_list(force_reload=False)
        except Exception:
            pass
        try:
            app._on_call_record_selected(apply_profile_and_workflow=False)
        except Exception:
            pass
    elif active_page == "customer_data":
        try:
            app._load_customer_data_records_into_list(force_reload=False)
        except Exception:
            pass
        try:
            app._customer_data_last_render_key = ""
            app._on_customer_data_record_selected()
        except Exception:
            pass

def safe_set_profile_sash(
    app,
    panes: ttk.Panedwindow,
    min_top: int = 160,
    min_bottom: int = 170,
    force_initial: bool = False,
) -> None:
    try:
        if int(panes.winfo_exists() or 0) != 1:
            return
        pane_height = panes.winfo_height()
    except tk.TclError:
        return
    if pane_height <= 0:
        return
    pane_key = str(panes)
    initialized = getattr(app, "_profile_sash_initialized", None)
    if not isinstance(initialized, set):
        initialized = set()
        setattr(app, "_profile_sash_initialized", initialized)
    should_force = force_initial or (pane_key not in initialized)
    max_top = max(min_top, pane_height - min_bottom)
    try:
        current = panes.sashpos(0)
    except tk.TclError:
        return
    if should_force or current < min_top:
        try:
            screen_h = int(ctypes.windll.user32.GetSystemMetrics(1) or 0)
        except Exception:
            screen_h = 0
        if screen_h <= 0:
            screen_h = int(app.winfo_screenheight() or 0)
        if screen_h <= 0:
            screen_h = 900
        target = max(min_top, min(int(screen_h / 4), max_top))
    else:
        target = max(min_top, min(current, max_top))
    if target == current:
        initialized.add(pane_key)
        return
    try:
        panes.sashpos(0, target)
    except tk.TclError:
        return
    initialized.add(pane_key)


def _schedule_restore_customer_data_sash(app, context) -> None:
    panes = getattr(context, "customer_data_panes", None)
    saved_sash = int(getattr(context, "customer_data_list_sash", -1) or -1)
    if not isinstance(panes, ttk.Panedwindow):
        return

    def _restore(_retries: int = 0) -> None:
        try:
            width = int(panes.winfo_width() or 0)
            if width <= 0:
                # 控件尚未可见，延迟重试；_ensure_customer_data_sash 会先设置默认值，
                # 之后本函数重试再将其修正为保存值（若有）。
                if _retries < 10:
                    panes.after(100, lambda: _restore(_retries + 1))
                return
            screen_w = panes.winfo_screenwidth()
            max_list_w = max(220, int(screen_w / 3))        # 最大 1/3 屏幕宽
            default_sash = max(120, min(int(screen_w / 6), max_list_w))  # 默认 1/6 屏幕宽
            target = default_sash if saved_sash < 0 else max(120, min(saved_sash, max_list_w))
            # 将目标值写到 widget 属性，供 _apply_customer_data_sash 在页面切换时读取。
            # 同时尝试直接写入（若控件已可见则立即生效；若隐藏则由 _apply 在 tkraise 后补写）。
            panes._sash_target = target
            panes.sashpos(0, target)
            panes._sash_restore_done = True
        except Exception:
            return

    app.after_idle(_restore)


def _capture_current_bound_context_state(app, context) -> None:
    _capture_current_workflow_doc(app, context)
    tab_id = str(getattr(context, "tab_id", "") or "")
    if tab_id:
        try:
            context.ui_snapshot = app._capture_conversation_tab_snapshot(tab_id)
        except Exception:
            pass
    current_panes = getattr(context, "customer_data_panes", None)
    if isinstance(current_panes, ttk.Panedwindow):
        try:
            current_sash = int(current_panes.sashpos(0))
            screen_w = current_panes.winfo_screenwidth()
            max_list_w = max(220, int(screen_w / 3))
            if 120 <= current_sash <= max_list_w:
                context.customer_data_list_sash = current_sash
        except Exception:
            pass
    apply_call_record_state_to_context(context, build_call_record_state_from_app(app))
    apply_customer_data_state_to_context(context, build_customer_data_state_from_app(app))
    runtime_state = _capture_runtime_state(app)
    context.runtime_state = dict(runtime_state)
    context.conversation_strategy_history = runtime_state["conversation_strategy_history"]
    context.conversation_customer_profile_history = runtime_state["conversation_customer_profile_history"]
    context.conversation_intent_generator_history = runtime_state["conversation_intent_generator_history"]
    context.dialog_conversation_history_by_customer = runtime_state["dialog_conversation_history_by_customer"]
    context.dialog_conversation_active_customer_key = runtime_state["dialog_conversation_active_customer_key"]
    context.customer_data_last_render_key = runtime_state["customer_data_last_render_key"]
    context.dialog_agent_stream_active = runtime_state["dialog_agent_stream_active"]
    context.dialog_agent_stream_content_start = runtime_state["dialog_agent_stream_content_start"]
    context.dialog_intent_history = runtime_state["dialog_intent_history"]
    context.dialog_intent_state_by_customer = runtime_state["dialog_intent_state_by_customer"]
    context.current_session_customer_lines = runtime_state["current_session_customer_lines"]


def unload_conversation_tab_ui(app, tab_id: str, *, capture_snapshot: bool = True) -> None:
    context = app._conversation_tabs.get(tab_id)
    if context is None or (not getattr(context, "ui_loaded", True)):
        return
    if capture_snapshot:
        try:
            context.ui_snapshot = app._capture_conversation_tab_snapshot(tab_id)
        except Exception:
            context.ui_snapshot = {}
    context.ui_loaded = True


def _mark_conversation_tab_recent(app, tab_id: str) -> None:
    context = app._conversation_tabs.get(tab_id)
    if context is None:
        return
    seq = int(getattr(app, "_conversation_tab_activation_seq", 0) or 0) + 1
    app._conversation_tab_activation_seq = seq
    context.last_activated_seq = seq


def _prune_loaded_conversation_tabs(app, keep_tab_id: str, *, max_loaded_tabs: int = 4) -> None:
    return


def ensure_conversation_tab_ui_loaded(app, tab_id: str):
    context = app._conversation_tabs.get(tab_id)
    if context is None or getattr(context, "ui_loaded", True):
        return context
    previous_data_override = app._tab_data_dir_override
    app._tab_data_dir_override = context.data_dir if isinstance(context.data_dir, Path) else None
    try:
        rebuilt = app._build_conversation_tab(
            parent=context.tab_frame,
            panel_bg="#f3f7fc",
            tab_title=context.title,
            command_value=context.conversation_command_var.get(),
            env_value=context.conversation_server_env_var.get(),
            tab_id_override=tab_id,
        )
    finally:
        app._tab_data_dir_override = previous_data_override

    rebuilt.data_dir = context.data_dir
    rebuilt.customer_data_list_sash = context.customer_data_list_sash
    apply_call_record_state_to_context(rebuilt, build_call_record_state_from_context(context))
    apply_customer_data_state_to_context(rebuilt, build_customer_data_state_from_context(context))
    rebuilt.runtime_state = dict(getattr(context, "runtime_state", {}) or {})
    rebuilt.conversation_strategy_history = list(getattr(context, "conversation_strategy_history", []) or [])
    rebuilt.conversation_customer_profile_history = list(getattr(context, "conversation_customer_profile_history", []) or [])
    rebuilt.conversation_intent_generator_history = list(getattr(context, "conversation_intent_generator_history", []) or [])
    rebuilt.dialog_conversation_history_by_customer = dict(getattr(context, "dialog_conversation_history_by_customer", {}) or {})
    rebuilt.dialog_conversation_active_customer_key = str(getattr(context, "dialog_conversation_active_customer_key", "") or "")
    rebuilt.customer_data_last_render_key = str(getattr(context, "customer_data_last_render_key", "") or "")
    rebuilt.dialog_agent_stream_active = bool(getattr(context, "dialog_agent_stream_active", False))
    rebuilt.dialog_agent_stream_content_start = str(getattr(context, "dialog_agent_stream_content_start", "") or "")
    rebuilt.dialog_intent_history = list(getattr(context, "dialog_intent_history", []) or [])
    rebuilt.dialog_intent_state_by_customer = dict(getattr(context, "dialog_intent_state_by_customer", {}) or {})
    rebuilt.current_session_customer_lines = list(getattr(context, "current_session_customer_lines", []) or [])
    rebuilt.workflow_doc = dict(_normalize_workflow_doc(getattr(context, "workflow_doc", {})))
    rebuilt.active_page = context.active_page
    rebuilt.ui_snapshot = dict(context.ui_snapshot)
    rebuilt.ui_loaded = True
    rebuilt.ui_needs_restore = True

    app._register_conversation_tab_context(rebuilt, is_template=(tab_id == app._conversation_template_tab_id))
    return rebuilt


def bind_conversation_tab_context(app, tab_id: str) -> bool:
    started_at = perf_counter()
    if tab_id == app._bound_conversation_tab_id:
        current = app._conversation_tabs.get(tab_id)
        if current is not None:
            current = ensure_conversation_tab_ui_loaded(app, tab_id)
            _schedule_restore_customer_data_sash(app, current)
        _log_tab_switch_timing(app, "bind.same_tab", started_at, extra=f"tab_id={tab_id}")
        return True
    target = app._conversation_tabs.get(tab_id)
    if target is None:
        _log_tab_switch_timing(app, "bind.missing_tab", started_at, extra=f"tab_id={tab_id}")
        return False
    current_id = app._bound_conversation_tab_id
    if current_id:
        current = app._conversation_tabs.get(current_id)
        if current is not None:
            _capture_current_bound_context_state(app, current)
            _hibernate_inactive_tab_widgets(current)
            current_panes = getattr(current, "customer_data_panes", None)
            if isinstance(current_panes, ttk.Panedwindow):
                try:
                    current_sash = int(current_panes.sashpos(0))
                    screen_w = current_panes.winfo_screenwidth()
                    max_list_w = max(220, int(screen_w / 3))  # 最大 1/3 屏幕宽
                    if 120 <= current_sash <= max_list_w:
                        current.customer_data_list_sash = current_sash
                except Exception:
                    pass
            apply_call_record_state_to_context(current, build_call_record_state_from_app(app))
            apply_customer_data_state_to_context(current, build_customer_data_state_from_app(app))
            current.conversation_strategy_history = app._conversation_strategy_history
            current.conversation_customer_profile_history = app._conversation_customer_profile_history
            current.conversation_intent_generator_history = app._conversation_intent_generator_history
            current.dialog_conversation_history_by_customer = app._dialog_conversation_history_by_customer
            current.dialog_conversation_active_customer_key = app._dialog_conversation_active_customer_key
            current.customer_data_last_render_key = app._customer_data_last_render_key
            current.dialog_agent_stream_active = app._dialog_agent_stream_active
            current.dialog_agent_stream_content_start = app._dialog_agent_stream_content_start
            # 使用引用赋值而非拷贝：restore 步骤已为新 Tab 创建独立副本，
            # 保存旧 Tab 状态只需记住当前对象引用即可，无需额外拷贝。
            current.dialog_intent_history = app._dialog_intent_history
            current.dialog_intent_state_by_customer = app._dialog_intent_state_by_customer
            current.current_session_customer_lines = app._current_session_customer_lines
            current_runtime_state = _capture_runtime_state(app)
            current.runtime_state = dict(current_runtime_state)
            current.conversation_strategy_history = current_runtime_state["conversation_strategy_history"]
            current.conversation_customer_profile_history = current_runtime_state["conversation_customer_profile_history"]
            current.conversation_intent_generator_history = current_runtime_state["conversation_intent_generator_history"]
            current.dialog_conversation_history_by_customer = current_runtime_state["dialog_conversation_history_by_customer"]
            current.dialog_conversation_active_customer_key = current_runtime_state["dialog_conversation_active_customer_key"]
            current.customer_data_last_render_key = current_runtime_state["customer_data_last_render_key"]
            current.dialog_agent_stream_active = current_runtime_state["dialog_agent_stream_active"]
            current.dialog_agent_stream_content_start = current_runtime_state["dialog_agent_stream_content_start"]
            current.dialog_intent_history = current_runtime_state["dialog_intent_history"]
            current.dialog_intent_state_by_customer = current_runtime_state["dialog_intent_state_by_customer"]
            current.current_session_customer_lines = current_runtime_state["current_session_customer_lines"]
            current.workflow_doc = dict(_normalize_workflow_doc(getattr(app, "_workflow_doc", {})))

    target = ensure_conversation_tab_ui_loaded(app, tab_id)
    if target is None:
        _log_tab_switch_timing(app, "bind.load_failed", started_at, extra=f"tab_id={tab_id}")
        return False

    app.conversation_command_var = target.conversation_command_var
    app.conversation_server_env_var = target.conversation_server_env_var
    app.conversation_profile_status_var = target.conversation_profile_status_var
    app.conversation_profile_status_label = target.conversation_profile_status_label
    app.call_record_selected_var = target.call_record_selected_var
    app.profile_call_btn = target.profile_call_btn
    app.dialog_profile_table = target.dialog_profile_table
    app.asr_text = target.monitor_asr_text
    app.tts_text = target.monitor_tts_text
    app.nlp_input_text = target.monitor_nlp_input_text
    app.latency_text = target.monitor_latency_text
    app.monitor_process_status_label = target.monitor_process_status_label
    app.dialog_conversation_text = target.dialog_conversation_text
    app.dialog_intent_text = target.dialog_intent_text
    app.dialog_intent_table = target.dialog_intent_table
    app.dialog_billing_text = target.dialog_billing_text
    app.dialog_billing_table = target.dialog_billing_table
    app.dialog_intent_queue_text = target.dialog_intent_queue_text
    app.dialog_strategy_text = target.dialog_strategy_text
    runtime_state = _apply_runtime_state_to_app(app, getattr(target, "runtime_state", {}))
    app._dialog_intent_history = list(runtime_state["dialog_intent_history"])
    app._dialog_intent_state_by_customer = dict(runtime_state["dialog_intent_state_by_customer"])
    app._dialog_intent_state_current_customer_key = ""
    app._current_session_customer_lines = list(runtime_state["current_session_customer_lines"])
    app.conversation_workflow_text = target.conversation_workflow_text
    app.conversation_strategy_history_text = target.conversation_strategy_history_text
    app.conversation_strategy_input_text = target.conversation_strategy_input_text
    app.conversation_system_instruction_text = target.conversation_system_instruction_text
    app.conversation_intent_text = target.conversation_intent_text
    app.conversation_customer_profile_text = target.conversation_customer_profile_text
    app.conversation_pending_items_prompt_text = target.conversation_pending_items_prompt_text
    app.conversation_summary_prompt_text = target.conversation_summary_prompt_text
    app.conversation_strategy_prompt_text = target.conversation_strategy_prompt_text
    app._workflow_doc = dict(_normalize_workflow_doc(getattr(target, "workflow_doc", {})))
    # Legacy aliases: settings-page editors were removed; bind old fields to active conversation editors.
    app.customer_profile_text = target.conversation_customer_profile_text
    app.workflow_text = target.conversation_workflow_text
    app.system_instruction_text = target.conversation_system_instruction_text
    app.call_record_tree = target.call_record_tree
    app.call_record_summary_text = target.call_record_summary_text
    app.call_record_commitments_text = target.call_record_commitments_text
    app.call_record_strategy_text = target.call_record_strategy_text
    app.customer_data_record_tree = target.customer_data_record_tree
    app.customer_data_panes = target.customer_data_panes
    app.customer_data_profile_table = target.customer_data_profile_table
    app.customer_data_calls_canvas = target.customer_data_calls_canvas
    app.customer_data_calls_container = target.customer_data_calls_container
    app.customer_data_call_entries_wrap = target.customer_data_call_entries_wrap
    app._conversation_page_switcher = target.conversation_page_switcher
    apply_call_record_state_to_app(app, build_call_record_state_from_context(target))
    apply_customer_data_state_to_app(app, build_customer_data_state_from_context(target))
    app._conversation_strategy_history = runtime_state["conversation_strategy_history"]
    app._conversation_customer_profile_history = runtime_state["conversation_customer_profile_history"]
    app._conversation_intent_generator_history = runtime_state["conversation_intent_generator_history"]
    app._dialog_conversation_history_by_customer = runtime_state["dialog_conversation_history_by_customer"]
    app._dialog_conversation_active_customer_key = runtime_state["dialog_conversation_active_customer_key"]
    app._customer_data_last_render_key = runtime_state["customer_data_last_render_key"]
    app._dialog_agent_stream_active = runtime_state["dialog_agent_stream_active"]
    app._dialog_agent_stream_content_start = runtime_state["dialog_agent_stream_content_start"]
    app._bound_conversation_tab_id = tab_id
    app._active_conversation_tab_id = tab_id
    _mark_conversation_tab_recent(app, tab_id)
    if getattr(target, "ui_needs_restore", False):
        snapshot = dict(getattr(target, "ui_snapshot", {}) or {})
        target.ui_needs_restore = False
        if snapshot:
            app._apply_conversation_tab_snapshot(tab_id, snapshot)
        else:
            _apply_workflow_doc_to_widgets(app, getattr(target, "workflow_doc", {}))
        switcher = target.conversation_page_switcher
        if callable(switcher):
            try:
                switcher(target.active_page or "profile")
            except Exception:
                switcher("profile")
        _restore_active_tab_heavy_widgets(app, target)
    else:
        _restore_active_tab_heavy_widgets(app, target)
    # 意图历史状态已在上方 lines 163-166 从 target context 恢复到 app.*，
    # 控件刷新（Treeview / Text 重绘）改为延迟一帧执行，让 Tab 的视觉切换先完成。
    # 快速连续切 Tab 时取消上一次未执行的同步，只保留最新一次。
    _pending_intent = getattr(app, "_intent_sync_after_id", None)
    app._intent_sync_after_id = None
    if _pending_intent is not None:
        try:
            app.after_cancel(_pending_intent)
        except Exception:
            pass

    def _deferred_intent_sync() -> None:
        app._intent_sync_after_id = None
        try:
            app._sync_dialog_intent_strategy_for_active_customer()
            # _sync 函数内部会替换 app._dialog_intent_history 为新 list，
            # 需要把最新引用写回当前 Tab 的 context，确保下次切走时保存的是最新数据。
            _tab = app._conversation_tabs.get(app._active_conversation_tab_id)
            if _tab is not None:
                _tab.dialog_intent_history = app._dialog_intent_history
                _tab.dialog_intent_state_by_customer = app._dialog_intent_state_by_customer
        except Exception:
            pass

    app._intent_sync_after_id = None

    # 策略历史面板渲染（可能含大量文本，耗时明显）使用 after_cancel 去重：
    # 快速连续切 Tab 时，取消上一次尚未执行的渲染，只保留最后一次。
    # 用 after(50) 而非 after_idle，确保新 Toplevel 的 Map/Paint 事件
    # 能在此回调之前被事件循环处理，避免窗口出现延迟。
    _pending = getattr(app, "_strategy_history_render_after_id", None)
    if _pending is not None:
        try:
            app.after_cancel(_pending)
        except Exception:
            pass

    def _deferred_render() -> None:
        app._strategy_history_render_after_id = None
        app._render_conversation_strategy_history_panel()

    app._strategy_history_render_after_id = None

    _schedule_restore_customer_data_sash(app, target)
    _prune_loaded_conversation_tabs(app, tab_id)

    sync_status = getattr(app, "_sync_conversation_profile_status", None)
    if callable(sync_status):
        try:
            sync_status()
        except Exception:
            pass
    active_page = str(getattr(target, "active_page", "profile") or "profile")
    data_dir_text = ""
    try:
        if isinstance(getattr(target, "data_dir", None), Path):
            data_dir_text = str(target.data_dir.resolve())
    except Exception:
        data_dir_text = str(getattr(target, "data_dir", "") or "")
    _log_tab_context_debug(
        app,
        f"bind completed visible={tab_id} bound={app._bound_conversation_tab_id} "
        f"active={app._active_conversation_tab_id} runtime={getattr(app, '_runtime_conversation_tab_id', '') or '-'} "
        f"title={getattr(target, 'title', '') or '-'} page={active_page} data_dir={data_dir_text or '-'}",
    )
    _log_tab_switch_timing(app, "bind.completed", started_at, extra=f"tab_id={tab_id} page={active_page}")
    return True


@contextmanager
def using_conversation_tab_context(app, tab_id: str) -> Iterator[None]:
    previous_id = app._bound_conversation_tab_id
    switched = False
    if tab_id and (tab_id != previous_id):
        switched = app._bind_conversation_tab_context(tab_id)
    try:
        yield
    finally:
        if switched and previous_id:
            app._bind_conversation_tab_context(previous_id)


def on_main_notebook_tab_changed(app, _event=None) -> None:
    started_at = perf_counter()
    notebook = app._main_notebook
    if not isinstance(notebook, ttk.Notebook):
        return
    if bool(getattr(app, "_tab_switch_freeze_internal", False)):
        return
    selected_tab_name = str(notebook.select() or "")
    if not selected_tab_name:
        return
    if _should_warn_summary_pending_on_tab_switch(app, selected_tab_name):
        allow_switch = _show_summary_pending_switch_dialog(app)
        if not allow_switch:
            current_tab_id = str(getattr(app, "_bound_conversation_tab_id", "") or "")
            current_context = app._conversation_tabs.get(current_tab_id) if current_tab_id else None
            try:
                app._tab_switch_freeze_internal = True
                if current_context is not None:
                    notebook.select(current_context.tab_frame)
            except Exception:
                pass
            finally:
                app._tab_switch_freeze_internal = False
            return
    tab_id = app._conversation_tab_id_by_frame_name.get(selected_tab_name)
    if not tab_id:
        return
    if _is_tab_switch_locked(app):
        locked_tab_id = _get_locked_conversation_tab_id(app)
        if locked_tab_id and (tab_id != locked_tab_id):
            locked_context = app._conversation_tabs.get(locked_tab_id)
            locked_frame = getattr(locked_context, "tab_frame", None)
            if locked_frame is not None:
                try:
                    app._tab_switch_freeze_internal = True
                    notebook.select(locked_frame)
                except Exception:
                    pass
                finally:
                    app._tab_switch_freeze_internal = False
            if not bool(getattr(app, "_tab_switch_freeze_notice_shown", False)):
                app._tab_switch_freeze_notice_shown = True
                title = str(getattr(locked_context, "title", "") or locked_tab_id)
                try:
                    messagebox.showwarning("通话进行中", f"当前正在通话，不能切换TAB页。\n\n当前通话TAB：{title}")
                except Exception:
                    pass
            _log_tab_context_debug(
                app,
                f"tab-switch blocked selected={tab_id} locked={locked_tab_id} "
                f"runtime={getattr(app, '_runtime_conversation_tab_id', '') or '-'}",
            )
            _log_tab_switch_timing(app, "notebook.blocked", started_at, extra=f"selected={tab_id} locked={locked_tab_id}")
            return
    app._bind_conversation_tab_context(tab_id)
    target = app._conversation_tabs.get(tab_id)
    active_page = str(getattr(target, "active_page", "profile") or "profile")
    data_dir_text = ""
    try:
        if target is not None and isinstance(getattr(target, "data_dir", None), Path):
            data_dir_text = str(target.data_dir.resolve())
    except Exception:
        data_dir_text = str(getattr(target, "data_dir", "") or "")
    _log_tab_context_debug(
        app,
        f"notebook changed visible={tab_id} bound={getattr(app, '_bound_conversation_tab_id', '') or '-'} "
        f"active={getattr(app, '_active_conversation_tab_id', '') or '-'} "
        f"runtime={getattr(app, '_runtime_conversation_tab_id', '') or '-'} "
        f"title={getattr(target, 'title', '') if target is not None else '-'} "
        f"page={active_page} data_dir={data_dir_text or '-'}",
    )
    _log_tab_switch_timing(app, "notebook.changed", started_at, extra=f"tab_id={tab_id} page={active_page}")
    try:
        app.after_idle(lambda _sid=started_at, _tab_id=tab_id, _page=active_page: _log_tab_switch_timing(app, "notebook.after_idle", _sid, extra=f"tab_id={_tab_id} page={_page}"))
        app.after(16, lambda _sid=started_at, _tab_id=tab_id, _page=active_page: _log_tab_switch_timing(app, "notebook.after16", _sid, extra=f"tab_id={_tab_id} page={_page}"))
        app.after(60, lambda _sid=started_at, _tab_id=tab_id, _page=active_page: _log_tab_switch_timing(app, "notebook.after60", _sid, extra=f"tab_id={_tab_id} page={_page}"))
    except Exception:
        pass


def build_unique_conversation_tab_title(app, base_title: str) -> str:
    title = (base_title or "").strip() or "对话"
    existed = {ctx.title for ctx in app._conversation_tabs.values()}
    if title not in existed:
        return title
    suffix = 2
    while True:
        candidate = f"{title}({suffix})"
        if candidate not in existed:
            return candidate
        suffix += 1


def capture_conversation_tab_snapshot(app, tab_id: str) -> dict[str, str]:
    if tab_id not in app._conversation_tabs:
        return {}
    with app._using_conversation_tab_context(tab_id):
        context = app._conversation_tabs.get(tab_id)
        workflow_doc = _capture_current_workflow_doc(app, context)
        sync_fn = getattr(app, "_sync_dialog_intent_strategy_for_active_customer", None)
        if callable(sync_fn):
            try:
                sync_fn()
            except Exception:
                pass
        profile_text = app._build_profile_text_from_dialog_profile_table()
        # Do not autosave newly-added live conversation text from the
        # "客户与坐席对话" widget. Keep the last persisted snapshot value.
        conversation_text = ""
        snapshot_path = app._get_conversation_tab_snapshot_path(tab_id)
        if isinstance(snapshot_path, Path) and snapshot_path.exists():
            try:
                raw_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                if isinstance(raw_snapshot, dict):
                    conversation_text = str(raw_snapshot.get("conversation", "") or "")
            except Exception:
                conversation_text = ""
        dialog_intent_text = app.dialog_intent_text.get("1.0", "end-1c") if isinstance(app.dialog_intent_text, ScrolledText) else ""
        system_text = workflow_doc["system_instruction"]
        intent_text = workflow_doc["intent"]
        workflow_profile_text = workflow_doc["workflow_profile"]
        strategy_text = workflow_doc["strategy"]
        strategy_input_text = workflow_doc["strategy_input"]
        strategy_history_json = json.dumps(app._conversation_strategy_history, ensure_ascii=False)
        profile_history_json = json.dumps(app._conversation_customer_profile_history, ensure_ascii=False)
        intent_history_json = json.dumps(app._conversation_intent_generator_history, ensure_ascii=False)
        dialog_intent_history_json = json.dumps(list(getattr(app, "_dialog_intent_history", []) or []), ensure_ascii=False)
        dialog_intent_state_by_customer_json = json.dumps(
            dict(getattr(app, "_dialog_intent_state_by_customer", {}) or {}),
            ensure_ascii=False,
        )
        current_session_customer_lines_json = json.dumps(
            list(getattr(app, "_current_session_customer_lines", []) or []),
            ensure_ascii=False,
        )
        summary_prompt = workflow_doc["dialog_summary_prompt"]
        pending_items_prompt = workflow_doc["pending_items_prompt"]
        strategy_prompt = workflow_doc["dialog_strategy_prompt"]
        return {
            "command": app.conversation_command_var.get(),
            "env": app.conversation_server_env_var.get(),
            "profile": profile_text,
            "conversation": conversation_text,
            "dialog_intent": dialog_intent_text,
            "system_instruction": system_text,
            "intent": intent_text,
            "workflow_profile": workflow_profile_text,
            "strategy": strategy_text,
            "strategy_input": strategy_input_text,
            "strategy_history": strategy_history_json,
            "profile_history": profile_history_json,
            "intent_history": intent_history_json,
            "dialog_intent_history": dialog_intent_history_json,
            "dialog_intent_state_by_customer": dialog_intent_state_by_customer_json,
            "current_session_customer_lines": current_session_customer_lines_json,
            "pending_items_prompt": pending_items_prompt,
            "dialog_summary_prompt": summary_prompt,
            "dialog_strategy_prompt": strategy_prompt,
        }


def apply_conversation_tab_snapshot(
    app,
    tab_id: str,
    snapshot: dict[str, str],
) -> None:
    if (not snapshot) or (tab_id not in app._conversation_tabs):
        return
    with app._using_conversation_tab_context(tab_id):
        context = app._conversation_tabs.get(tab_id)
        app.conversation_command_var.set(snapshot.get("command", app.conversation_command_var.get()))
        env_text = (snapshot.get("env", app.conversation_server_env_var.get()) or "").strip().lower()
        if env_text not in {"local", "public"}:
            env_text = "local"
        app.conversation_server_env_var.set(env_text)
        if isinstance(app.dialog_conversation_text, ScrolledText):
            app._render_dialog_conversation_history(snapshot.get("conversation", ""))
            app.dialog_conversation_text.configure(state="normal")
        if isinstance(app.dialog_intent_text, ScrolledText):
            app._set_text_content(app.dialog_intent_text, snapshot.get("dialog_intent", ""))
            app.dialog_intent_text.configure(state="disabled")
        dialog_intent_history_raw = snapshot.get("dialog_intent_history", "")
        dialog_intent_history_items: list[str] = []
        if dialog_intent_history_raw:
            try:
                parsed = json.loads(dialog_intent_history_raw)
                if isinstance(parsed, list):
                    dialog_intent_history_items = [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                dialog_intent_history_items = []
        current_session_customer_lines_raw = snapshot.get("current_session_customer_lines", "")
        current_session_customer_lines_items: list[str] = []
        if current_session_customer_lines_raw:
            try:
                parsed = json.loads(current_session_customer_lines_raw)
                if isinstance(parsed, list):
                    current_session_customer_lines_items = [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                current_session_customer_lines_items = []
        dialog_intent_state_by_customer_raw = snapshot.get("dialog_intent_state_by_customer", "")
        dialog_intent_state_by_customer: dict[str, dict[str, list[str]]] = {}
        if dialog_intent_state_by_customer_raw:
            try:
                parsed = json.loads(dialog_intent_state_by_customer_raw)
                if isinstance(parsed, dict):
                    for raw_key, raw_state in parsed.items():
                        key = str(raw_key or "").strip()
                        if (not key) or (not isinstance(raw_state, dict)):
                            continue
                        history_value = raw_state.get("history", [])
                        history = [str(item).strip() for item in history_value if str(item).strip()] if isinstance(history_value, list) else []
                        dialog_intent_state_by_customer[key] = {
                            "history": history[-200:],
                        }
            except Exception:
                dialog_intent_state_by_customer = {}
        app._dialog_intent_history = dialog_intent_history_items
        if dialog_intent_state_by_customer:
            app._dialog_intent_state_by_customer = dialog_intent_state_by_customer
        else:
            app._dialog_intent_state_by_customer = {}
            if dialog_intent_history_items:
                app._dialog_intent_state_by_customer["__default__"] = {
                    "history": list(dialog_intent_history_items[-200:]),
                }
        app._dialog_intent_state_current_customer_key = ""
        app._current_session_customer_lines = current_session_customer_lines_items
        if context is not None:
            context.dialog_intent_history = list(dialog_intent_history_items)
            context.dialog_intent_state_by_customer = dict(app._dialog_intent_state_by_customer)
            context.current_session_customer_lines = list(current_session_customer_lines_items)
        app._sync_dialog_intent_strategy_for_active_customer()
        app._refresh_dialog_intent_queue_view()
        workflow_doc = _normalize_workflow_doc(getattr(context, "workflow_doc", {}))
        for key in _WORKFLOW_DOC_KEYS:
            snapshot_value = str(snapshot.get(key, "") or "")
            if snapshot_value:
                workflow_doc[key] = snapshot_value
        if context is not None:
            context.workflow_doc = dict(workflow_doc)
            context.workflow_doc_dirty = False
        _apply_workflow_doc_to_widgets(app, workflow_doc)
        if isinstance(app.conversation_strategy_input_text, tk.Text):
            app.conversation_strategy_input_text.event_generate("<KeyRelease>")
        history_raw = snapshot.get("strategy_history", "")
        history_items: list[dict[str, str]] = []
        if history_raw:
            try:
                parsed = json.loads(history_raw)
                if isinstance(parsed, list):
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        history_items.append(
                            {
                                "instruction": str(item.get("instruction", "") or ""),
                                "response": str(item.get("response", "") or ""),
                                "created_at": str(item.get("created_at", "") or ""),
                            }
                        )
            except Exception:
                history_items = []
        app._conversation_strategy_history.clear()
        app._conversation_strategy_history.extend(history_items)
        app._render_conversation_strategy_history_panel()
        profile_history_raw = snapshot.get("profile_history", "")
        profile_history_items: list[dict[str, str]] = []
        if profile_history_raw:
            try:
                parsed = json.loads(profile_history_raw)
                if isinstance(parsed, list):
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        profile_history_items.append(
                            {
                                "instruction": str(item.get("instruction", "") or ""),
                                "response": str(item.get("response", "") or ""),
                                "created_at": str(item.get("created_at", "") or ""),
                            }
                        )
            except Exception:
                profile_history_items = []
        app._conversation_customer_profile_history.clear()
        app._conversation_customer_profile_history.extend(profile_history_items)
        intent_history_raw = snapshot.get("intent_history", "")
        intent_history_items: list[dict[str, str]] = []
        if intent_history_raw:
            try:
                parsed = json.loads(intent_history_raw)
                if isinstance(parsed, list):
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        intent_history_items.append(
                            {
                                "instruction": str(item.get("instruction", "") or ""),
                                "response": str(item.get("response", "") or ""),
                                "created_at": str(item.get("created_at", "") or ""),
                            }
                        )
            except Exception:
                intent_history_items = []
        app._conversation_intent_generator_history.clear()
        app._conversation_intent_generator_history.extend(intent_history_items)
        if context is not None:
            context.runtime_state = _capture_runtime_state(app)
        if isinstance(app.dialog_profile_table, ttk.Treeview):
            app._fill_profile_table_from_text(app.dialog_profile_table, snapshot.get("profile", ""), auto_height=True)
        app._sync_conversation_server_env_from_command(app.conversation_command_var.get().strip())


def refresh_conversation_tab_registry_view(app) -> None:
    tree = app._conversation_tab_registry_tree
    if not isinstance(tree, ttk.Treeview):
        return
    tree.delete(*tree.get_children())
    app._conversation_tab_registry_iid_to_tab_id.clear()
    items: list[tuple[str, object]] = []
    for tab_id, context in app._conversation_tabs.items():
        if tab_id == app._conversation_template_tab_id:
            continue
        items.append((tab_id, context))
    items.sort(key=lambda item: item[1].title)
    for idx, (tab_id, context) in enumerate(items):
        data_dir = context.data_dir if isinstance(context.data_dir, Path) else (app._workspace_dir / "Data")
        display_dir = str(data_dir)
        try:
            display_dir = str(data_dir.resolve().relative_to(app._workspace_dir.resolve()))
        except Exception:
            pass
        display_title = f"{context.title} *" if bool(getattr(context, "workflow_doc_dirty", False)) else context.title
        iid = f"tab_{idx}"
        tree.insert("", "end", iid=iid, values=(display_title, display_dir))
        app._conversation_tab_registry_iid_to_tab_id[iid] = tab_id


def get_conversation_tab_snapshot_path(app, tab_id: str) -> Path | None:
    context = app._conversation_tabs.get(tab_id)
    if context is None:
        return None
    data_dir = context.data_dir if isinstance(context.data_dir, Path) else (app._workspace_dir / "Data")
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    return data_dir / "_ui_tab_state.json"


def _get_conversation_tab_workflow_snapshot_path(app, tab_id: str) -> Path | None:
    context = app._conversation_tabs.get(tab_id)
    if context is None:
        return None
    data_dir = context.data_dir if isinstance(context.data_dir, Path) else (app._workspace_dir / "Data")
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    return data_dir / "_ui_tab_workflow.json"


def _get_legacy_conversation_tab_snapshot_path(app, tab_id: str) -> Path | None:
    context = app._conversation_tabs.get(tab_id)
    if context is None:
        return None
    data_dir = context.data_dir if isinstance(context.data_dir, Path) else (app._workspace_dir / "Data")
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    return data_dir / "_ui_tab_snapshot.json"



# 需要跨会话持久化的配置字段（不含运行时/会话数据）
_SNAPSHOT_PERSIST_KEYS = (
    "command",
    "env",
    "system_instruction",
    "strategy",              # conversation_workflow_text（工作流策略）
    "intent",                # conversation_intent_text（意图标签）
    "workflow_profile",      # conversation_customer_profile_text（客户个人画像）
    "pending_items_prompt",  # 待核实事项提示词模板
    "dialog_summary_prompt", # 摘要提示词模板
    "dialog_strategy_prompt",# 策略提示词模板
)

_WORKFLOW_PERSIST_KEYS = (
    "system_instruction",
    "strategy",
    "intent",
    "workflow_profile",
    "pending_items_prompt",
    "dialog_summary_prompt",
    "dialog_strategy_prompt",
)

_WORKFLOW_DOC_KEYS = (
    "system_instruction",
    "intent",
    "workflow_profile",
    "strategy",
    "strategy_input",
    "pending_items_prompt",
    "dialog_summary_prompt",
    "dialog_strategy_prompt",
)


def _normalize_workflow_doc(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {key: "" for key in _WORKFLOW_DOC_KEYS}
    return {key: str(raw.get(key, "") or "") for key in _WORKFLOW_DOC_KEYS}


def _read_workflow_doc_from_widgets(app) -> dict[str, str]:
    def _read(widget) -> str:
        try:
            return widget.get("1.0", "end-1c") if widget is not None else ""
        except Exception:
            return ""

    return {
        "system_instruction": _read(getattr(app, "conversation_system_instruction_text", None)),
        "intent": _read(getattr(app, "conversation_intent_text", None)),
        "workflow_profile": _read(getattr(app, "conversation_customer_profile_text", None)),
        "strategy": _read(getattr(app, "conversation_workflow_text", None)),
        "strategy_input": _read(getattr(app, "conversation_strategy_input_text", None)),
        "pending_items_prompt": _read(getattr(app, "conversation_pending_items_prompt_text", None)),
        "dialog_summary_prompt": _read(getattr(app, "conversation_summary_prompt_text", None)),
        "dialog_strategy_prompt": _read(getattr(app, "conversation_strategy_prompt_text", None)),
    }


def _capture_current_workflow_doc(app, context=None) -> dict[str, str]:
    workflow_doc = _normalize_workflow_doc(_read_workflow_doc_from_widgets(app))
    app._workflow_doc = dict(workflow_doc)
    if context is not None:
        context.workflow_doc = dict(workflow_doc)
    return workflow_doc


def _capture_runtime_state(app) -> dict[str, object]:
    runtime_state = {
        "conversation_strategy_history": list(getattr(app, "_conversation_strategy_history", []) or []),
        "conversation_customer_profile_history": list(getattr(app, "_conversation_customer_profile_history", []) or []),
        "conversation_intent_generator_history": list(getattr(app, "_conversation_intent_generator_history", []) or []),
        "dialog_conversation_history_by_customer": dict(getattr(app, "_dialog_conversation_history_by_customer", {}) or {}),
        "dialog_conversation_active_customer_key": str(getattr(app, "_dialog_conversation_active_customer_key", "") or ""),
        "customer_data_last_render_key": str(getattr(app, "_customer_data_last_render_key", "") or ""),
        "dialog_agent_stream_active": bool(getattr(app, "_dialog_agent_stream_active", False)),
        "dialog_agent_stream_content_start": str(getattr(app, "_dialog_agent_stream_content_start", "") or ""),
        "dialog_intent_history": list(getattr(app, "_dialog_intent_history", []) or []),
        "dialog_intent_state_by_customer": dict(getattr(app, "_dialog_intent_state_by_customer", {}) or {}),
        "current_session_customer_lines": list(getattr(app, "_current_session_customer_lines", []) or []),
    }
    return runtime_state


def _apply_runtime_state_to_app(app, runtime_state: object) -> dict[str, object]:
    source = runtime_state if isinstance(runtime_state, dict) else {}
    normalized = {
        "conversation_strategy_history": list(source.get("conversation_strategy_history", []) or []),
        "conversation_customer_profile_history": list(source.get("conversation_customer_profile_history", []) or []),
        "conversation_intent_generator_history": list(source.get("conversation_intent_generator_history", []) or []),
        "dialog_conversation_history_by_customer": dict(source.get("dialog_conversation_history_by_customer", {}) or {}),
        "dialog_conversation_active_customer_key": str(source.get("dialog_conversation_active_customer_key", "") or ""),
        "customer_data_last_render_key": str(source.get("customer_data_last_render_key", "") or ""),
        "dialog_agent_stream_active": bool(source.get("dialog_agent_stream_active", False)),
        "dialog_agent_stream_content_start": str(source.get("dialog_agent_stream_content_start", "") or ""),
        "dialog_intent_history": list(source.get("dialog_intent_history", []) or []),
        "dialog_intent_state_by_customer": dict(source.get("dialog_intent_state_by_customer", {}) or {}),
        "current_session_customer_lines": list(source.get("current_session_customer_lines", []) or []),
    }
    app._conversation_runtime_state = dict(normalized)
    app._conversation_strategy_history = normalized["conversation_strategy_history"]
    app._conversation_customer_profile_history = normalized["conversation_customer_profile_history"]
    app._conversation_intent_generator_history = normalized["conversation_intent_generator_history"]
    app._dialog_conversation_history_by_customer = normalized["dialog_conversation_history_by_customer"]
    app._dialog_conversation_active_customer_key = normalized["dialog_conversation_active_customer_key"]
    app._customer_data_last_render_key = normalized["customer_data_last_render_key"]
    app._dialog_agent_stream_active = normalized["dialog_agent_stream_active"]
    app._dialog_agent_stream_content_start = normalized["dialog_agent_stream_content_start"]
    app._dialog_intent_history = normalized["dialog_intent_history"]
    app._dialog_intent_state_by_customer = normalized["dialog_intent_state_by_customer"]
    app._current_session_customer_lines = normalized["current_session_customer_lines"]
    return normalized


def _apply_workflow_doc_to_widgets(app, workflow_doc: object) -> None:
    doc = _normalize_workflow_doc(workflow_doc)
    app._workflow_doc = dict(doc)
    if isinstance(app.conversation_system_instruction_text, ScrolledText):
        app._set_text_content(app.conversation_system_instruction_text, doc["system_instruction"])
    if isinstance(app.conversation_intent_text, ScrolledText):
        app._set_text_content(app.conversation_intent_text, doc["intent"])
    if isinstance(app.conversation_customer_profile_text, ScrolledText):
        app._set_text_content(app.conversation_customer_profile_text, doc["workflow_profile"])
    if isinstance(app.conversation_workflow_text, ScrolledText):
        app._set_text_content(app.conversation_workflow_text, doc["strategy"])
    if isinstance(app.conversation_pending_items_prompt_text, ScrolledText):
        app._set_text_content(app.conversation_pending_items_prompt_text, doc["pending_items_prompt"])
    if isinstance(app.conversation_summary_prompt_text, ScrolledText):
        app._set_text_content(app.conversation_summary_prompt_text, doc["dialog_summary_prompt"])
    if isinstance(app.conversation_strategy_prompt_text, ScrolledText):
        app._set_text_content(app.conversation_strategy_prompt_text, doc["dialog_strategy_prompt"])
    if isinstance(app.conversation_strategy_input_text, tk.Text):
        app.conversation_strategy_input_text.delete("1.0", "end")
        app.conversation_strategy_input_text.insert("1.0", doc["strategy_input"])


def _normalize_persisted_snapshot(raw: object, keys: tuple[str, ...]) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, str] = {}
    for key in keys:
        normalized[key] = str(raw.get(key, "") or "")
    return normalized


def _read_json_file_with_fallbacks(path: Path | None) -> object:
    if not (isinstance(path, Path) and path.exists()):
        return None
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return json.loads(path.read_text(encoding=encoding))
        except Exception:
            continue
    return None


def _read_persisted_conversation_tab_snapshot_bundle(app, tab_id: str) -> dict[str, str]:
    merged = {key: "" for key in _SNAPSHOT_PERSIST_KEYS}
    auto_path = get_conversation_tab_snapshot_path(app, tab_id)
    workflow_path = _get_conversation_tab_workflow_snapshot_path(app, tab_id)
    legacy_path = _get_legacy_conversation_tab_snapshot_path(app, tab_id)

    def _read(path: Path | None, keys: tuple[str, ...]) -> dict[str, str]:
        raw = _read_json_file_with_fallbacks(path)
        if raw is None:
            return {}
        return _normalize_persisted_snapshot(raw, keys)

    for source in (
        _read(legacy_path, _SNAPSHOT_PERSIST_KEYS),
        _read(auto_path, ("command", "env")),
        _read(workflow_path, _WORKFLOW_PERSIST_KEYS),
    ):
        for key, value in source.items():
            if value:
                merged[key] = value
    return merged


def save_persisted_conversation_tab_snapshots(app, persist_workflow_fields: bool = False) -> None:
    """将每个 Tab 的配置型字段写入各自的 _ui_tab_snapshot.json，供下次启动恢复。

    直接从各 Tab 的 ConversationTabContext 控件中读取内容，无需切换激活上下文，
    避免对每个 Tab 执行两次 bind_conversation_tab_context（含 Treeview/Text 刷新）
    带来的主线程阻塞。
    """

    def _read_text(widget) -> str:
        try:
            return widget.get("1.0", "end-1c") if widget is not None else ""
        except Exception:
            return ""

    def _read_var(var) -> str:
        try:
            return var.get() if var is not None else ""
        except Exception:
            return ""

    for tab_id, context in app._conversation_tabs.items():
        auto_path = app._get_conversation_tab_snapshot_path(tab_id)
        workflow_path = _get_conversation_tab_workflow_snapshot_path(app, tab_id)
        legacy_path = _get_legacy_conversation_tab_snapshot_path(app, tab_id)
        if auto_path is None:
            continue
        existing_data = _read_persisted_conversation_tab_snapshot_bundle(app, tab_id)
        snapshot_data = _normalize_persisted_snapshot(getattr(context, "ui_snapshot", {}) or {}, _SNAPSHOT_PERSIST_KEYS)
        workflow_doc = _normalize_workflow_doc(getattr(context, "workflow_doc", {}))
        ui_loaded = bool(getattr(context, "ui_loaded", True))
        if ui_loaded:
            if tab_id == getattr(app, "_bound_conversation_tab_id", ""):
                workflow_doc = _normalize_workflow_doc({**workflow_doc, **_read_workflow_doc_from_widgets(app)})
            workflow_doc = _normalize_workflow_doc(
                workflow_doc
            )
            context.workflow_doc = dict(workflow_doc)
            context.workflow_doc_dirty = False
            persist_data = {
                "command": _read_var(context.conversation_command_var),
                "env": _read_var(context.conversation_server_env_var),
                "system_instruction": workflow_doc["system_instruction"],
                "strategy": workflow_doc["strategy"],
                "intent": workflow_doc["intent"],
                "workflow_profile": workflow_doc["workflow_profile"],
                "pending_items_prompt": workflow_doc["pending_items_prompt"],
                "dialog_summary_prompt": workflow_doc["dialog_summary_prompt"],
                "dialog_strategy_prompt": workflow_doc["dialog_strategy_prompt"],
            }
        else:
            persist_data = dict(snapshot_data)
            for key in _WORKFLOW_PERSIST_KEYS:
                if workflow_doc.get(key):
                    persist_data[key] = workflow_doc[key]

        for key in _SNAPSHOT_PERSIST_KEYS:
            current_value = str(persist_data.get(key, "") or "")
            if current_value:
                continue
            snapshot_value = str(snapshot_data.get(key, "") or "")
            if snapshot_value:
                persist_data[key] = snapshot_value
                continue
            existing_value = str(existing_data.get(key, "") or "")
            if existing_value:
                persist_data[key] = existing_value
        try:
            auto_path.parent.mkdir(parents=True, exist_ok=True)
            auto_path.write_text(
                json.dumps(
                    {
                        "command": str(persist_data.get("command", "") or ""),
                        "env": str(persist_data.get("env", "") or ""),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        if persist_workflow_fields and workflow_path is not None:
            try:
                workflow_path.parent.mkdir(parents=True, exist_ok=True)
                workflow_path.write_text(
                    json.dumps(
                        {key: str(persist_data.get(key, "") or "") for key in _WORKFLOW_PERSIST_KEYS},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass
        elif workflow_path is not None and any(str(existing_data.get(key, "") or "") for key in _WORKFLOW_PERSIST_KEYS):
            try:
                workflow_path.parent.mkdir(parents=True, exist_ok=True)
                workflow_path.write_text(
                    json.dumps(
                        {key: str(existing_data.get(key, "") or "") for key in _WORKFLOW_PERSIST_KEYS},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass
        if isinstance(legacy_path, Path) and legacy_path.exists():
            try:
                legacy_path.unlink()
            except Exception:
                pass


def load_persisted_conversation_tab_snapshots(app) -> None:
    """启动时为每个已创建的 Tab 从持久化快照恢复配置型字段。"""
    for tab_id, context in app._conversation_tabs.items():
        raw = _read_persisted_conversation_tab_snapshot_bundle(app, tab_id)
        if not any(str(raw.get(key, "") or "") for key in _SNAPSHOT_PERSIST_KEYS):
            continue
        context.ui_snapshot = dict(raw)
        context.workflow_doc = _normalize_workflow_doc(raw)
        context.workflow_doc_dirty = False
        with app._using_conversation_tab_context(tab_id):
            command_val = str(raw.get("command", "") or "")
            if command_val:
                app.conversation_command_var.set(command_val)
            env_val = (str(raw.get("env", "") or "")).strip().lower()
            if env_val in {"local", "public"}:
                app.conversation_server_env_var.set(env_val)
            _apply_workflow_doc_to_widgets(app, context.workflow_doc)
            try:
                app._refresh_runtime_system_prompt_only()
            except Exception:
                pass

    template_id = str(getattr(app, "_conversation_template_tab_id", "") or "")
    if not template_id:
        return
    template_context = app._conversation_tabs.get(template_id)
    if template_context is None:
        return
    template_workflow_path = _get_conversation_tab_workflow_snapshot_path(app, template_id)
    template_workflow_doc = _normalize_workflow_doc(_read_json_file_with_fallbacks(template_workflow_path))
    if not any(str(template_workflow_doc.get(key, "") or "") for key in _WORKFLOW_PERSIST_KEYS):
        return
    template_context.workflow_doc = dict(template_workflow_doc)
    template_context.workflow_doc_dirty = False
    with app._using_conversation_tab_context(template_id):
        _apply_workflow_doc_to_widgets(app, template_context.workflow_doc)
        try:
            app._refresh_runtime_system_prompt_only()
        except Exception:
            pass


def write_conversation_tab_meta(app, data_dir: Path, title: str) -> None:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        meta_path = data_dir / "_tab_meta.json"
        meta_path.write_text(
            json.dumps({"title": str(title or "").strip() or data_dir.name}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        return


def is_template_conversation_context_bound(app) -> bool:
    return bool(app._bound_conversation_tab_id) and (app._bound_conversation_tab_id == app._conversation_template_tab_id)


def create_conversation_tab_internal(
    app,
    tab_title: str,
    source_tab_id: str = "",
    *,
    data_dir: Path | None = None,
    copy_source_data: bool = True,
    select_new_tab: bool = True,
    persist: bool = True,
    reset_workflow_fields: bool = True,
) -> str | None:
    notebook = app._main_notebook
    if not isinstance(notebook, ttk.Notebook):
        return None
    normalized_title = app._build_unique_conversation_tab_title(tab_title)
    source_id = source_tab_id or app._conversation_template_tab_id or app._active_conversation_tab_id
    snapshot = app._capture_conversation_tab_snapshot(source_id)
    # 新 Tab 的工作流程页面全部从空白开始，不从模版继承任何数据。
    for _key in (
        "system_instruction", "workflow_profile", "strategy", "strategy_input",
        "intent", "dialog_intent", "conversation",
        "strategy_history", "profile_history", "intent_history",
        "dialog_intent_history", "dialog_intent_state_by_customer",
        "current_session_customer_lines",
        "pending_items_prompt",
        "dialog_summary_prompt", "dialog_strategy_prompt",
    ):
        snapshot[_key] = ""
    source_context = app._conversation_tabs.get(source_id)
    source_data_dir = (
        source_context.data_dir
        if source_context and isinstance(source_context.data_dir, Path)
        else (app._workspace_dir / "Data")
    )
    target_data_dir = data_dir if isinstance(data_dir, Path) else app._build_new_tab_data_dir(normalized_title)
    if not reset_workflow_fields:
        restored_snapshot: dict[str, str] = {}
        temp_context = type("_TempContext", (), {"data_dir": target_data_dir})()
        temp_tabs = getattr(app, "_conversation_tabs", {})
        existing_temp = temp_tabs.get("__restore__")
        temp_tabs["__restore__"] = temp_context
        try:
            restored_snapshot = _read_persisted_conversation_tab_snapshot_bundle(app, "__restore__")
        finally:
            if existing_temp is None:
                temp_tabs.pop("__restore__", None)
            else:
                temp_tabs["__restore__"] = existing_temp
        snapshot = restored_snapshot or app._capture_conversation_tab_snapshot(source_id)
    if copy_source_data:
        app._copy_tab_case_files(source_data_dir, target_data_dir)
    else:
        target_data_dir.mkdir(parents=True, exist_ok=True)

    previous_bound_id = app._bound_conversation_tab_id
    previous_data_override = app._tab_data_dir_override
    app._bound_conversation_tab_id = ""
    app._tab_data_dir_override = target_data_dir

    frame = ttk.Frame(notebook, style="App.TFrame")
    notebook.add(frame, text=normalized_title)
    try:
        context = app._build_conversation_tab(
            parent=frame,
            panel_bg="#f3f7fc",
            tab_title=normalized_title,
            command_value=snapshot.get("command", app.conversation_command_var.get()),
            env_value=snapshot.get("env", app.conversation_server_env_var.get()),
        )
    except Exception:
        notebook.forget(frame)
        raise
    finally:
        app._tab_data_dir_override = previous_data_override

    app._register_conversation_tab_context(context, is_template=False)
    context.data_dir = target_data_dir
    app._write_conversation_tab_meta(target_data_dir, normalized_title)
    if previous_bound_id and (previous_bound_id in app._conversation_tabs):
        app._bind_conversation_tab_context(previous_bound_id)
    app._apply_conversation_tab_snapshot(context.tab_id, snapshot)
    context.workflow_doc = _normalize_workflow_doc(snapshot)
    context.workflow_doc_dirty = False
    context.runtime_state = _capture_runtime_state(app)
    if select_new_tab:
        notebook.select(frame)
        app._bind_conversation_tab_context(context.tab_id)
    else:
        context.ui_snapshot = dict(snapshot)
        _hibernate_inactive_tab_widgets(context)
    if persist:
        app._refresh_conversation_tab_registry_view()
        app._save_persisted_conversation_tabs()
    return context.tab_id


def create_conversation_tab_from_settings(app) -> None:
    def _reset_new_tab_defaults(tab_id: str) -> None:
        if tab_id not in app._conversation_tabs:
            return
        with app._using_conversation_tab_context(tab_id):
            # 新 Tab 工作流程页面全部清空，不继承模版数据。
            if isinstance(app.conversation_customer_profile_text, ScrolledText):
                app._set_text_content(app.conversation_customer_profile_text, "")
            if isinstance(app.conversation_system_instruction_text, ScrolledText):
                app._set_text_content(app.conversation_system_instruction_text, "")
            if isinstance(app.conversation_intent_text, ScrolledText):
                app._set_text_content(app.conversation_intent_text, "")
            if isinstance(app.conversation_workflow_text, ScrolledText):
                app._set_text_content(app.conversation_workflow_text, "")
            if isinstance(app.conversation_pending_items_prompt_text, ScrolledText):
                app._set_text_content(app.conversation_pending_items_prompt_text, "")
            if isinstance(app.conversation_strategy_input_text, tk.Text):
                app.conversation_strategy_input_text.delete("1.0", "end")
            current_context = app._conversation_tabs.get(tab_id)
            if current_context is not None:
                current_context.workflow_doc = _normalize_workflow_doc({})
                current_context.workflow_doc_dirty = False
                current_context.runtime_state = dict(getattr(app, "_conversation_runtime_state", {}) or {})
                app._workflow_doc = dict(current_context.workflow_doc)
            if isinstance(app.dialog_conversation_text, ScrolledText):
                app._set_text_content(app.dialog_conversation_text, "")
            if isinstance(app.dialog_intent_text, ScrolledText):
                app._set_text_content(app.dialog_intent_text, "")
                app.dialog_intent_text.configure(state="disabled")
            if isinstance(app.dialog_profile_table, ttk.Treeview):
                app._fill_profile_table_from_text(app.dialog_profile_table, "", auto_height=True)

            app._conversation_strategy_history.clear()
            app._conversation_customer_profile_history.clear()
            app._conversation_intent_generator_history.clear()
            app._dialog_conversation_history_by_customer.clear()
            app._dialog_conversation_active_customer_key = ""
            app._dialog_intent_history = []
            app._dialog_intent_state_by_customer = {}
            app._dialog_intent_state_current_customer_key = ""
            app._current_session_customer_lines = []
            app._conversation_runtime_state = _capture_runtime_state(app)
            app._refresh_dialog_intent_queue_view()
            app._render_conversation_strategy_history_panel()

            apply_call_record_state_to_app(app, make_empty_call_record_state())
            current_context = app._conversation_tabs.get(tab_id)
            if current_context is not None:
                apply_call_record_state_to_context(current_context, make_empty_call_record_state())
            apply_customer_data_state_to_app(app, make_empty_customer_data_state())
            if current_context is not None:
                apply_customer_data_state_to_context(current_context, make_empty_customer_data_state())
            app._customer_data_last_render_key = ""
            if isinstance(app.call_record_tree, ttk.Treeview):
                app.call_record_tree.delete(*app.call_record_tree.get_children())
            if isinstance(app.customer_data_record_tree, ttk.Treeview):
                app.customer_data_record_tree.delete(*app.customer_data_record_tree.get_children())
            app._clear_call_record_detail("Data 目录下暂无通话记录")
            app._clear_customer_data_profile_table("Data 目录下暂无通话记录")

    raw_title = (app.create_conversation_tab_name_var.get() or "").strip()
    if not raw_title:
        messagebox.showwarning("Name required", "Please enter a tab name.")
        return
    try:
        new_tab_id = app._create_conversation_tab_internal(
            tab_title=raw_title,
            source_tab_id=app._conversation_template_tab_id or app._active_conversation_tab_id,
            copy_source_data=False,
            select_new_tab=True,
            persist=True,
        )
        if new_tab_id:
            _reset_new_tab_defaults(new_tab_id)
            app._save_persisted_conversation_tab_snapshots()
    except Exception as exc:
        messagebox.showerror("Create failed", f"Failed to create tab: {exc}")
        return
    app.create_conversation_tab_name_var.set("")


def delete_selected_conversation_tab_from_settings(app) -> None:
    tree = app._conversation_tab_registry_tree
    if not isinstance(tree, ttk.Treeview):
        return
    selected = tree.selection()
    if not selected:
        messagebox.showwarning("No tab selected", "Please select a tab in the list first.")
        return
    iid = selected[0]
    tab_id = app._conversation_tab_registry_iid_to_tab_id.get(iid, "")
    if not tab_id:
        messagebox.showwarning("Invalid selection", "Selected tab is invalid. Refresh and retry.")
        return
    app._delete_conversation_tab(tab_id)


def delete_conversation_tab(app, tab_id: str) -> None:
    if not tab_id:
        return
    if tab_id == app._conversation_template_tab_id:
        messagebox.showwarning("Cannot delete", "Template tab cannot be deleted.")
        return
    context = app._conversation_tabs.get(tab_id)
    if context is None:
        app._refresh_conversation_tab_registry_view()
        app._save_persisted_conversation_tabs()
        return
    if app._bridge.running and (app._runtime_conversation_tab_id == tab_id):
        messagebox.showwarning("Tab running", "This tab is in an active call. Stop it before deleting.")
        return
    notebook = app._main_notebook
    if isinstance(notebook, ttk.Notebook):
        try:
            notebook.forget(context.tab_frame)
        except Exception:
            pass
    app._conversation_tabs.pop(tab_id, None)
    app._conversation_tab_id_by_frame_name.pop(str(context.tab_frame), None)

    if app._bound_conversation_tab_id == tab_id:
        app._bound_conversation_tab_id = ""
    if app._active_conversation_tab_id == tab_id:
        app._active_conversation_tab_id = ""
    if app._runtime_conversation_tab_id == tab_id:
        app._runtime_conversation_tab_id = ""

    if isinstance(context.data_dir, Path):
        tabs_root = (app._workspace_dir / "Data" / "_tabs").resolve()
        try:
            resolved = context.data_dir.resolve()
            resolved.relative_to(tabs_root)
            if resolved.exists():
                shutil.rmtree(resolved, ignore_errors=True)
        except Exception:
            pass

    template_id = app._conversation_template_tab_id
    if template_id:
        app._bind_conversation_tab_context(template_id)

    app._refresh_conversation_tab_registry_view()
    app._save_persisted_conversation_tabs()


def save_persisted_conversation_tabs(app) -> None:
    if app._suspend_tab_registry_save:
        return
    entries: list[dict[str, str]] = []
    for tab_id, context in app._conversation_tabs.items():
        if tab_id == app._conversation_template_tab_id:
            continue
        data_dir = context.data_dir if isinstance(context.data_dir, Path) else app._workspace_dir / "Data"
        data_dir_text = str(data_dir)
        try:
            data_dir_text = str(data_dir.resolve().relative_to(app._workspace_dir.resolve()))
        except Exception:
            pass
        entries.append({"title": context.title, "data_dir": data_dir_text})
    path = app._get_conversation_tab_registry_path()
    svc_save_conversation_tab_registry_entries(path, entries)


def read_conversation_tab_registry_entries(app, path: Path) -> list[dict[str, str]]:
    return svc_read_conversation_tab_registry_entries(path)


def load_persisted_conversation_tabs(app) -> None:
    path = app._get_conversation_tab_registry_path()
    raw_items: list[dict[str, str]] = []
    if path.exists():
        raw_items = app._read_conversation_tab_registry_entries(path)
    if not raw_items:
        bak_path = path.with_suffix(path.suffix + ".bak")
        if bak_path.exists():
            raw_items = app._read_conversation_tab_registry_entries(bak_path)

    tabs_root = path.parent
    known_data_dirs: set[str] = set()
    normalized_items: list[dict[str, str]] = []
    for item in raw_items:
        title = str(item.get("title", "") or "").strip()
        if not title:
            continue
        data_dir_text = str(item.get("data_dir", "") or "").strip()
        data_dir = Path(data_dir_text) if data_dir_text else app._build_new_tab_data_dir(title)
        if not data_dir.is_absolute():
            data_dir = app._workspace_dir / data_dir
        try:
            normalized_data_dir = str(data_dir.resolve())
        except Exception:
            normalized_data_dir = str(data_dir)
        if normalized_data_dir in known_data_dirs:
            continue
        known_data_dirs.add(normalized_data_dir)
        normalized_items.append({"title": title, "data_dir": str(data_dir)})

    if tabs_root.exists():
        for child in sorted(tabs_root.iterdir(), key=lambda p: p.name):
            if not child.is_dir():
                continue
            meta_path = child / "_tab_meta.json"
            auto_snapshot_path = child / "_ui_tab_state.json"
            workflow_snapshot_path = child / "_ui_tab_workflow.json"
            legacy_snapshot_path = child / "_ui_tab_snapshot.json"
            if (not meta_path.exists()) and (not auto_snapshot_path.exists()) and (not workflow_snapshot_path.exists()) and (not legacy_snapshot_path.exists()):
                continue
            recovered_title = child.name
            if meta_path.exists():
                try:
                    meta_raw = json.loads(meta_path.read_text(encoding="utf-8"))
                    if isinstance(meta_raw, dict):
                        recovered_title = str(meta_raw.get("title", "") or "").strip() or recovered_title
                except Exception:
                    recovered_title = child.name
            try:
                normalized_child = str(child.resolve())
            except Exception:
                normalized_child = str(child)
            if normalized_child in known_data_dirs:
                continue
            known_data_dirs.add(normalized_child)
            normalized_items.append({"title": recovered_title, "data_dir": str(child)})

    if not normalized_items:
        return

    app._suspend_tab_registry_save = True
    try:
        for item in normalized_items:
            title = str(item.get("title", "") or "").strip()
            data_dir_text = str(item.get("data_dir", "") or "").strip()
            data_dir = Path(data_dir_text) if data_dir_text else app._build_new_tab_data_dir(title)
            if not data_dir.is_absolute():
                data_dir = app._workspace_dir / data_dir
            try:
                app._create_conversation_tab_internal(
                    tab_title=title,
                    source_tab_id=app._conversation_template_tab_id,
                    data_dir=data_dir,
                    copy_source_data=False,
                    select_new_tab=False,
                    persist=False,
                    reset_workflow_fields=False,
                )
            except Exception:
                continue
    finally:
        app._suspend_tab_registry_save = False
    app._refresh_conversation_tab_registry_view()
    app._save_persisted_conversation_tabs()
