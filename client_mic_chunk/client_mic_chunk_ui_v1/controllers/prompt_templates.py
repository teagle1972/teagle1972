from __future__ import annotations

from tkinter.scrolledtext import ScrolledText


def get_template_from_widget(widget) -> str:
    if isinstance(widget, ScrolledText):
        try:
            return widget.get("1.0", "end-1c").strip()
        except Exception:
            pass
    return ""


def get_dialog_summary_prompt_template(app) -> str:
    return get_template_from_widget(app.conversation_summary_prompt_text)


def get_pending_items_prompt_template(app) -> str:
    return get_template_from_widget(app.conversation_pending_items_prompt_text)


def get_dialog_strategy_prompt_template(app) -> str:
    return get_template_from_widget(app.conversation_strategy_prompt_text)
