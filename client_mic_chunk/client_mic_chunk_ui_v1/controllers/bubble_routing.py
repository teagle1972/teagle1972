from __future__ import annotations


def is_instruction_header_line(text: str) -> bool:
    t = str(text or "").strip()
    return t.startswith("指令 ") or t.lower().startswith("instruction ")


def is_llm_header_line(text: str) -> bool:
    t = str(text or "").strip()
    return t.startswith("LLM返回 ") or t.lower().startswith("llm return ")


def try_append_customer_profile_bubble(app, widget, text: str, tag: str) -> bool:
    dialog = None
    for _attr in ("_conversation_customer_profile_dialog", "_conversation_intent_dialog", "_conversation_strategy_dialog"):
        _d = getattr(app, _attr, None)
        if isinstance(_d, dict) and _d.get("output") is widget:
            dialog = _d
            break
    if not isinstance(dialog, dict):
        return False
    if tag not in {"cs_right_bubble", "cs_left_bubble"}:
        return False
    clean_text = str(text or "").replace("\r", "")
    if not clean_text:
        return True

    # When history is re-rendered via delete("1.0", "end"), reset bubble refs.
    try:
        is_empty = str(widget.index("end-1c")) == "1.0"
    except Exception:
        is_empty = False
    if is_empty:
        dialog["_cp_bubble_refs"] = []
        dialog.pop("_cp_active_left_bubble", None)

    lines = clean_text.split("\n")
    header = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip("\n")
    is_right = tag == "cs_right_bubble"

    # New LLM bubble header line: start a live/empty bubble.
    if (not is_right) and app._is_llm_header_line(header) and (not body.strip()):
        app._insert_customer_profile_bubble_row(widget, header=header, body="", is_right=False, keep_active=True)
        return True

    # Stream chunks or thinking text: append to the current active left bubble.
    if not is_right:
        active = dialog.get("_cp_active_left_bubble")
        if isinstance(active, dict) and (not app._is_instruction_header_line(header)) and (not app._is_llm_header_line(header)):
            app._append_customer_profile_bubble_text(widget, active, clean_text)
            return True

    # Full block render (history or immediate instruction/response).
    if app._is_instruction_header_line(header) or app._is_llm_header_line(header):
        app._insert_customer_profile_bubble_row(
            widget,
            header=header,
            body=body,
            is_right=is_right,
            keep_active=(not is_right),
        )
        return True

    # Fallback: still render as a bubble, preserving alignment.
    app._insert_customer_profile_bubble_row(
        widget,
        header="",
        body=clean_text.strip("\n"),
        is_right=is_right,
        keep_active=(not is_right),
    )
    return True
