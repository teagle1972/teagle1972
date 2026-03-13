from __future__ import annotations

from tkinter.scrolledtext import ScrolledText


def render_conversation_intent_dialog_history(app, dialog: dict[str, object]) -> None:
    history_widget = dialog.get("history_text")
    if not isinstance(history_widget, ScrolledText):
        return
    tab_id = str(dialog.get("tab_id", "") or "")
    history = app._get_conversation_intent_generator_history_for_tab(tab_id)
    try:
        history_widget.configure(state="normal")
        history_widget.delete("1.0", "end")
    except Exception:
        return
    dialog["_cp_bubble_refs"] = []
    dialog.pop("_cp_active_left_bubble", None)
    if not history:
        try:
            history_widget.insert("end", "暂无历史记录\n", ("cs_hint",))
        except Exception:
            return
        history_widget.see("end")
        return
    for item in history:
        instruction = str(item.get("instruction", "") or "-")
        response = str(item.get("response", "") or "-")
        app._insert_customer_profile_bubble_row(
            history_widget,
            header="",
            body=instruction,
            is_right=True,
            keep_active=False,
        )
        app._insert_customer_profile_bubble_row(
            history_widget,
            header="",
            body=response,
            is_right=False,
            keep_active=False,
        )
