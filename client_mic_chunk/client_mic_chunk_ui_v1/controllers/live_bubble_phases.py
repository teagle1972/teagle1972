from __future__ import annotations


def prepare_live_conversation_customer_profile_response_bubble(app, source_widget) -> None:
    dialog = getattr(app, "_conversation_customer_profile_dialog", None)
    if not isinstance(dialog, dict):
        return
    if dialog.get("output") is not source_widget:
        return
    if str(dialog.get("live_response_phase", "")) == "content":
        return
    start_idx = str(dialog.get("live_response_start", "") or "")
    if not start_idx:
        dialog["live_response_phase"] = "content"
        return
    try:
        source_widget.configure(state="normal")
        source_widget.delete(start_idx, "end-1c")
    except Exception:
        return
    dialog.pop("_cp_active_left_bubble", None)
    dialog["live_response_phase"] = "content"


def append_live_conversation_customer_profile_thinking_chunk(app, source_widget, chunk: str) -> None:
    app._append_text_to_widget_with_tag(source_widget, chunk, "cs_left_bubble")


def append_live_conversation_customer_profile_content_chunk(app, source_widget, chunk: str) -> None:
    app._prepare_live_conversation_customer_profile_response_bubble(source_widget)
    app._append_text_to_widget_with_tag(source_widget, chunk, "cs_left_bubble")


def prepare_live_conversation_intent_response_bubble(app, source_widget) -> None:
    dialog = getattr(app, "_conversation_intent_dialog", None)
    if not isinstance(dialog, dict):
        return
    if dialog.get("output") is not source_widget:
        return
    if str(dialog.get("live_response_phase", "")) == "content":
        return
    start_idx = str(dialog.get("live_response_start", "") or "")
    if not start_idx:
        dialog["live_response_phase"] = "content"
        return
    try:
        source_widget.configure(state="normal")
        source_widget.delete(start_idx, "end-1c")
    except Exception:
        return
    dialog.pop("_cp_active_left_bubble", None)
    dialog["live_response_phase"] = "content"


def append_live_conversation_intent_thinking_chunk(app, source_widget, chunk: str) -> None:
    app._append_text_to_widget_with_tag(source_widget, chunk, "cs_left_bubble")


def append_live_conversation_intent_content_chunk(app, source_widget, chunk: str) -> None:
    app._prepare_live_conversation_intent_response_bubble(source_widget)
    app._append_text_to_widget_with_tag(source_widget, chunk, "cs_left_bubble")
