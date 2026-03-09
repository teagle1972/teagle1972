from __future__ import annotations

from tkinter.scrolledtext import ScrolledText


def _read_scrolled(widget) -> str:
    if isinstance(widget, ScrolledText):
        return widget.get("1.0", "end-1c") or ""
    return ""


def build_runtime_system_prompt(app) -> str:
    conversation_system = getattr(app, "conversation_system_instruction_text", None)
    conversation_profile = getattr(app, "conversation_customer_profile_text", None)
    conversation_workflow = getattr(app, "conversation_workflow_text", None)

    system_raw = _read_scrolled(conversation_system)
    if not system_raw:
        system_raw = _read_scrolled(getattr(app, "system_instruction_text", None))

    profile_raw = app._build_profile_text_from_dialog_profile_table()
    if not profile_raw:
        profile_raw = _read_scrolled(conversation_profile)
    if not profile_raw:
        profile_raw = _read_scrolled(getattr(app, "customer_profile_text", None))

    workflow_raw = _read_scrolled(conversation_workflow)
    if not workflow_raw:
        workflow_raw = _read_scrolled(getattr(app, "workflow_text", None))

    system_text = app._strip_llm_asr_debug_blocks(system_raw).strip()
    profile_text = app._strip_panel_llm_debug_blocks(profile_raw).strip()
    workflow_text = app._strip_panel_llm_debug_blocks(workflow_raw).strip()
    parts = [part for part in (system_text, profile_text, workflow_text) if part]
    return "\n\n".join(parts)
