from __future__ import annotations

from tkinter import ttk


def _set_conversation_tab_dirty_visual(app, context) -> None:
    notebook = getattr(app, "_main_notebook", None)
    if not isinstance(notebook, ttk.Notebook) or context is None:
        refresh_registry = getattr(app, "_refresh_conversation_tab_registry_view", None)
        if callable(refresh_registry):
            try:
                refresh_registry()
            except Exception:
                pass
        return
    title = str(getattr(context, "title", "") or "")
    dirty = bool(getattr(context, "workflow_doc_dirty", False))
    try:
        notebook.tab(context.tab_frame, text=f"{title} *" if dirty else title)
    except Exception:
        pass
    refresh_registry = getattr(app, "_refresh_conversation_tab_registry_view", None)
    if callable(refresh_registry):
        try:
            refresh_registry()
        except Exception:
            pass


def _set_workflow_doc_dirty(app, dirty: bool) -> None:
    tab_id = str(getattr(app, "_active_conversation_tab_id", "") or "")
    tabs = getattr(app, "_conversation_tabs", {})
    if (not tab_id) or (not isinstance(tabs, dict)):
        return
    context = tabs.get(tab_id)
    if context is None:
        return
    context.workflow_doc_dirty = bool(dirty)
    _set_conversation_tab_dirty_visual(app, context)


def _sync_workflow_doc_from_widgets(app, *, mark_dirty: bool) -> None:
    workflow_doc = getattr(app, "_workflow_doc", None)
    if not isinstance(workflow_doc, dict):
        workflow_doc = {}
        app._workflow_doc = workflow_doc

    def _read(widget) -> str:
        try:
            return widget.get("1.0", "end-1c") if widget is not None else ""
        except Exception:
            return ""

    workflow_doc["system_instruction"] = _read(getattr(app, "conversation_system_instruction_text", None))
    workflow_doc["intent"] = _read(getattr(app, "conversation_intent_text", None))
    workflow_doc["workflow_profile"] = _read(getattr(app, "conversation_customer_profile_text", None))
    workflow_doc["strategy"] = _read(getattr(app, "conversation_workflow_text", None))
    workflow_doc["strategy_input"] = _read(getattr(app, "conversation_strategy_input_text", None))
    workflow_doc["pending_items_prompt"] = _read(getattr(app, "conversation_pending_items_prompt_text", None))
    workflow_doc["dialog_summary_prompt"] = _read(getattr(app, "conversation_summary_prompt_text", None))
    workflow_doc["dialog_strategy_prompt"] = _read(getattr(app, "conversation_strategy_prompt_text", None))

    tab_id = str(getattr(app, "_active_conversation_tab_id", "") or "")
    tabs = getattr(app, "_conversation_tabs", {})
    if tab_id and isinstance(tabs, dict):
        context = tabs.get(tab_id)
        if context is not None:
            context.workflow_doc = dict(workflow_doc)
            if mark_dirty:
                context.workflow_doc_dirty = True
                _set_conversation_tab_dirty_visual(app, context)


def refresh_system_instruction(app) -> None:
    _sync_workflow_doc_from_widgets(app, mark_dirty=False)
    app._runtime_system_prompt = app._build_runtime_system_prompt()


def refresh_runtime_system_prompt_only(app) -> None:
    _sync_workflow_doc_from_widgets(app, mark_dirty=False)
    app._runtime_system_prompt = app._build_runtime_system_prompt()


def on_conversation_workflow_text_edited(app, _event=None) -> None:
    _sync_workflow_doc_from_widgets(app, mark_dirty=True)
    app.after_idle(app._refresh_runtime_system_prompt_only)
