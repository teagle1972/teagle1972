from __future__ import annotations


def _normalize_key(app, value: str) -> str:
    key = app._sanitize_inline_text(str(value or ""))
    return key or "__default__"


def _ensure_store(app) -> dict[str, dict[str, list[str]]]:
    store = getattr(app, "_dialog_intent_state_by_customer", None)
    if not isinstance(store, dict):
        store = {}
        app._dialog_intent_state_by_customer = store
    return store


def _active_key(app) -> str:
    return _normalize_key(app, str(getattr(app, "_dialog_conversation_active_customer_key", "") or ""))


def refresh_intent_queue_view(app) -> None:
    widget = getattr(app, "dialog_intent_text", None)
    if widget is None:
        return
    history: list[str] = list(getattr(app, "_dialog_intent_history", []) or [])
    try:
        prev_state = str(widget.cget("state"))
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        if history:
            for idx, item in enumerate(history, start=1):
                text = str(item or "").strip()
                if text:
                    widget.insert("end", f"{idx}. {text}\n")
        else:
            widget.insert("end", "暂无客户意图\n")
        widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "disabled")
        widget.see("1.0")
    except Exception:
        return


def sync_intent_strategy_for_active_customer(app) -> None:
    store = _ensure_store(app)
    raw_previous_key = str(getattr(app, "_dialog_intent_state_current_customer_key", "") or "").strip()
    if raw_previous_key:
        previous_key = _normalize_key(app, raw_previous_key)
        store[previous_key] = {
            "history": list(getattr(app, "_dialog_intent_history", []) or [])[-200:],
        }

    key = _active_key(app)
    state = store.get(key, {})
    history = state.get("history", []) if isinstance(state, dict) else []
    app._dialog_intent_history = [str(item).strip() for item in history if str(item).strip()][-200:]
    app._dialog_intent_state_current_customer_key = key
    refresh_intent_queue_view(app)


