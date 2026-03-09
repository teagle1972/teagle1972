from __future__ import annotations

import ctypes
import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

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


def safe_set_profile_sash(
    app,
    panes: ttk.Panedwindow,
    min_top: int = 160,
    min_bottom: int = 170,
    force_initial: bool = False,
) -> None:
    pane_height = panes.winfo_height()
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


def bind_conversation_tab_context(app, tab_id: str) -> bool:
    if tab_id == app._bound_conversation_tab_id:
        return True
    target = app._conversation_tabs.get(tab_id)
    if target is None:
        return False
    current_id = app._bound_conversation_tab_id
    if current_id:
        current = app._conversation_tabs.get(current_id)
        if current is not None:
            current.call_record_item_by_iid = app._call_record_item_by_iid
            current.customer_data_customer_by_iid = app._customer_data_customer_by_iid
            current.customer_data_case_cache_by_name = app._customer_data_case_cache_by_name
            current.conversation_strategy_history = app._conversation_strategy_history
            current.conversation_customer_profile_history = app._conversation_customer_profile_history
            current.conversation_intent_generator_history = app._conversation_intent_generator_history
            current.dialog_conversation_history_by_customer = app._dialog_conversation_history_by_customer
            current.dialog_conversation_active_customer_key = app._dialog_conversation_active_customer_key
            current.customer_data_last_render_key = app._customer_data_last_render_key
            current.dialog_agent_stream_active = app._dialog_agent_stream_active
            current.dialog_agent_stream_content_start = app._dialog_agent_stream_content_start
            current.dialog_intent_history = list(getattr(app, "_dialog_intent_history", []) or [])
            current.dialog_intent_state_by_customer = dict(getattr(app, "_dialog_intent_state_by_customer", {}) or {})
            current.current_session_customer_lines = list(getattr(app, "_current_session_customer_lines", []) or [])

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
    app.dialog_intent_queue_text = target.dialog_intent_queue_text
    app.dialog_strategy_text = target.dialog_strategy_text
    app._dialog_intent_history = list(getattr(target, "dialog_intent_history", []) or [])
    app._dialog_intent_state_by_customer = dict(getattr(target, "dialog_intent_state_by_customer", {}) or {})
    app._dialog_intent_state_current_customer_key = ""
    app._current_session_customer_lines = list(getattr(target, "current_session_customer_lines", []) or [])
    app.conversation_workflow_text = target.conversation_workflow_text
    app.conversation_strategy_history_text = target.conversation_strategy_history_text
    app.conversation_strategy_input_text = target.conversation_strategy_input_text
    app.conversation_system_instruction_text = target.conversation_system_instruction_text
    app.conversation_intent_text = target.conversation_intent_text
    app.conversation_customer_profile_text = target.conversation_customer_profile_text
    app.conversation_summary_prompt_text = target.conversation_summary_prompt_text
    app.conversation_strategy_prompt_text = target.conversation_strategy_prompt_text
    # Legacy aliases: settings-page editors were removed; bind old fields to active conversation editors.
    app.customer_profile_text = target.conversation_customer_profile_text
    app.workflow_text = target.conversation_workflow_text
    app.system_instruction_text = target.conversation_system_instruction_text
    app.call_record_tree = target.call_record_tree
    app.call_record_summary_text = target.call_record_summary_text
    app.call_record_commitments_text = target.call_record_commitments_text
    app.call_record_strategy_text = target.call_record_strategy_text
    app.customer_data_record_tree = target.customer_data_record_tree
    app.customer_data_profile_table = target.customer_data_profile_table
    app.customer_data_calls_canvas = target.customer_data_calls_canvas
    app.customer_data_calls_container = target.customer_data_calls_container
    app.customer_data_call_entries_wrap = target.customer_data_call_entries_wrap
    app._conversation_page_switcher = target.conversation_page_switcher
    app._call_record_item_by_iid = target.call_record_item_by_iid
    app._customer_data_customer_by_iid = target.customer_data_customer_by_iid
    app._customer_data_case_cache_by_name = target.customer_data_case_cache_by_name
    app._conversation_strategy_history = target.conversation_strategy_history
    app._conversation_customer_profile_history = target.conversation_customer_profile_history
    app._conversation_intent_generator_history = target.conversation_intent_generator_history
    app._dialog_conversation_history_by_customer = target.dialog_conversation_history_by_customer
    app._dialog_conversation_active_customer_key = target.dialog_conversation_active_customer_key
    app._customer_data_last_render_key = target.customer_data_last_render_key
    app._dialog_agent_stream_active = target.dialog_agent_stream_active
    app._dialog_agent_stream_content_start = target.dialog_agent_stream_content_start
    app._bound_conversation_tab_id = tab_id
    app._active_conversation_tab_id = tab_id
    # 提示词模板控件在每个 Tab 创建时已初始化，切换 Tab 时不重置内容，
    # 保持与系统指令控件相同的行为（避免光标被移位）。
    app._render_conversation_strategy_history_panel()
    app._sync_dialog_intent_strategy_for_active_customer()
    app._refresh_dialog_intent_queue_view()
    sync_status = getattr(app, "_sync_conversation_profile_status", None)
    if callable(sync_status):
        try:
            sync_status()
        except Exception:
            pass
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
    notebook = app._main_notebook
    if not isinstance(notebook, ttk.Notebook):
        return
    selected_tab_name = str(notebook.select() or "")
    if not selected_tab_name:
        return
    tab_id = app._conversation_tab_id_by_frame_name.get(selected_tab_name)
    if not tab_id:
        return
    app._bind_conversation_tab_context(tab_id)


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
        sync_fn = getattr(app, "_sync_dialog_intent_strategy_for_active_customer", None)
        if callable(sync_fn):
            try:
                sync_fn()
            except Exception:
                pass
        profile_text = app._build_profile_text_from_dialog_profile_table()
        conversation_text = (
            app.dialog_conversation_text.get("1.0", "end-1c")
            if isinstance(app.dialog_conversation_text, ScrolledText)
            else ""
        )
        dialog_intent_text = app.dialog_intent_text.get("1.0", "end-1c") if isinstance(app.dialog_intent_text, ScrolledText) else ""
        system_text = (
            app.conversation_system_instruction_text.get("1.0", "end-1c")
            if isinstance(app.conversation_system_instruction_text, ScrolledText)
            else ""
        )
        intent_text = (
            app.conversation_intent_text.get("1.0", "end-1c")
            if isinstance(app.conversation_intent_text, ScrolledText)
            else ""
        )
        workflow_profile_text = (
            app.conversation_customer_profile_text.get("1.0", "end-1c")
            if isinstance(app.conversation_customer_profile_text, ScrolledText)
            else ""
        )
        strategy_text = (
            app.conversation_workflow_text.get("1.0", "end-1c")
            if isinstance(app.conversation_workflow_text, ScrolledText)
            else ""
        )
        strategy_input_text = (
            app.conversation_strategy_input_text.get("1.0", "end-1c")
            if isinstance(app.conversation_strategy_input_text, tk.Text)
            else ""
        )
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
        }


def apply_conversation_tab_snapshot(
    app,
    tab_id: str,
    snapshot: dict[str, str],
) -> None:
    if (not snapshot) or (tab_id not in app._conversation_tabs):
        return
    with app._using_conversation_tab_context(tab_id):
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
        context = app._conversation_tabs.get(tab_id)
        if context is not None:
            context.dialog_intent_history = list(dialog_intent_history_items)
            context.dialog_intent_state_by_customer = dict(app._dialog_intent_state_by_customer)
            context.current_session_customer_lines = list(current_session_customer_lines_items)
        app._sync_dialog_intent_strategy_for_active_customer()
        app._refresh_dialog_intent_queue_view()
        if isinstance(app.conversation_system_instruction_text, ScrolledText):
            app._set_text_content(app.conversation_system_instruction_text, snapshot.get("system_instruction", ""))
        if isinstance(app.conversation_intent_text, ScrolledText):
            app._set_text_content(app.conversation_intent_text, snapshot.get("intent", ""))
        if isinstance(app.conversation_customer_profile_text, ScrolledText):
            app._set_text_content(app.conversation_customer_profile_text, snapshot.get("workflow_profile", ""))
        if isinstance(app.conversation_workflow_text, ScrolledText):
            app._set_text_content(app.conversation_workflow_text, snapshot.get("strategy", ""))
        if isinstance(app.conversation_strategy_input_text, tk.Text):
            app.conversation_strategy_input_text.delete("1.0", "end")
            app.conversation_strategy_input_text.insert("1.0", snapshot.get("strategy_input", ""))
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
        iid = f"tab_{idx}"
        tree.insert("", "end", iid=iid, values=(context.title, display_dir))
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
    return data_dir / "_ui_tab_snapshot.json"


def save_persisted_conversation_tab_snapshots(app) -> None:
    for tab_id in list(app._conversation_tabs.keys()):
        snapshot_path = app._get_conversation_tab_snapshot_path(tab_id)
        if not isinstance(snapshot_path, Path):
            continue
        snapshot = app._capture_conversation_tab_snapshot(tab_id)
        try:
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            continue


def load_persisted_conversation_tab_snapshots(app) -> None:
    for tab_id in list(app._conversation_tabs.keys()):
        snapshot_path = app._get_conversation_tab_snapshot_path(tab_id)
        if (not isinstance(snapshot_path, Path)) or (not snapshot_path.exists()):
            continue
        try:
            raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        normalized: dict[str, str] = {}
        for key, value in raw.items():
            k = str(key)
            if isinstance(value, str):
                normalized[k] = value
            else:
                try:
                    normalized[k] = json.dumps(value, ensure_ascii=False)
                except Exception:
                    normalized[k] = str(value)
        try:
            app._apply_conversation_tab_snapshot(tab_id, normalized)
        except Exception:
            continue


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
) -> str | None:
    notebook = app._main_notebook
    if not isinstance(notebook, ttk.Notebook):
        return None
    normalized_title = app._build_unique_conversation_tab_title(tab_title)
    source_id = source_tab_id or app._conversation_template_tab_id or app._active_conversation_tab_id
    snapshot = app._capture_conversation_tab_snapshot(source_id)
    source_context = app._conversation_tabs.get(source_id)
    source_data_dir = (
        source_context.data_dir
        if source_context and isinstance(source_context.data_dir, Path)
        else (app._workspace_dir / "Data")
    )
    target_data_dir = data_dir if isinstance(data_dir, Path) else app._build_new_tab_data_dir(normalized_title)
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
    if select_new_tab:
        notebook.select(frame)
        app._bind_conversation_tab_context(context.tab_id)
    if persist:
        app._refresh_conversation_tab_registry_view()
        app._save_persisted_conversation_tabs()
    return context.tab_id


def create_conversation_tab_from_settings(app) -> None:
    def _reset_new_tab_defaults(tab_id: str) -> None:
        if tab_id not in app._conversation_tabs:
            return
        with app._using_conversation_tab_context(tab_id):
            if isinstance(app.conversation_customer_profile_text, ScrolledText):
                app._set_text_content(app.conversation_customer_profile_text, "")
            if isinstance(app.conversation_system_instruction_text, ScrolledText):
                app._set_text_content(app.conversation_system_instruction_text, "")
            if isinstance(app.conversation_intent_text, ScrolledText):
                app._set_text_content(app.conversation_intent_text, "")
            if isinstance(app.conversation_workflow_text, ScrolledText):
                app._set_text_content(app.conversation_workflow_text, "")
            if isinstance(app.conversation_strategy_input_text, tk.Text):
                app.conversation_strategy_input_text.delete("1.0", "end")
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
            app._refresh_dialog_intent_queue_view()
            app._render_conversation_strategy_history_panel()

            app._call_record_item_by_iid.clear()
            app._customer_data_customer_by_iid.clear()
            app._customer_data_case_cache_by_name.clear()
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
            snapshot_path = child / "_ui_tab_snapshot.json"
            if (not meta_path.exists()) and (not snapshot_path.exists()):
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
                )
            except Exception:
                continue
    finally:
        app._suspend_tab_registry_save = False
    app._refresh_conversation_tab_registry_view()
    app._save_persisted_conversation_tabs()
