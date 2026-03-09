from __future__ import annotations

def refresh_system_instruction(app) -> None:
    app._runtime_system_prompt = app._build_runtime_system_prompt()


def refresh_runtime_system_prompt_only(app) -> None:
    app._runtime_system_prompt = app._build_runtime_system_prompt()


def on_conversation_workflow_text_edited(app, _event=None) -> None:
    app.after_idle(app._refresh_runtime_system_prompt_only)
