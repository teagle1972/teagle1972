from __future__ import annotations

import re
from datetime import datetime

from tkinter.scrolledtext import ScrolledText

_DIALOG_DEFAULT_CUSTOMER_KEY = "__default__"

# Session separator — marks the boundary between conversation sessions on disk and in widget
_SESS_SEP_RE = re.compile(r"^-{10,}")
_SESS_SEP_DASHES = "-" * 41


def _is_session_separator(line: str) -> bool:
    return bool(_SESS_SEP_RE.match(line.strip()))


def _build_session_separator(dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now()
    date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    return f"{_SESS_SEP_DASHES}   {date_str}   {_SESS_SEP_DASHES}"


def _filter_entries_to_last_session(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return entries from the last session separator line onwards (inclusive).
    If no separator exists, return all entries."""
    last_sep = -1
    for i, entry in enumerate(entries):
        if _is_session_separator(entry.get("text", "")):
            last_sep = i
    if last_sep >= 0:
        return entries[last_sep:]
    return entries


def _normalize_customer_key(name: str) -> str:
    normalized = sanitize_inline_text(str(name or ""))
    return normalized or _DIALOG_DEFAULT_CUSTOMER_KEY


def _ensure_dialog_history_store(app) -> dict[str, list[dict[str, str]]]:
    store = getattr(app, "_dialog_conversation_history_by_customer", None)
    if not isinstance(store, dict):
        store = {}
        app._dialog_conversation_history_by_customer = store
    active_key = getattr(app, "_dialog_conversation_active_customer_key", "")
    if not isinstance(active_key, str):
        app._dialog_conversation_active_customer_key = _DIALOG_DEFAULT_CUSTOMER_KEY
    return store


def _resolve_selected_customer_from_tree(tree, mapping: dict[str, str]) -> str:
    if tree is None:
        return ""
    try:
        selected = tree.selection()
    except Exception:
        return ""
    if not selected:
        return ""
    iid = str(selected[0] or "")
    if not iid:
        return ""
    return sanitize_inline_text(str(mapping.get(iid, "")))


def _resolve_active_customer_key(app) -> str:
    _ensure_dialog_history_store(app)
    pinned = _normalize_customer_key(getattr(app, "_dialog_conversation_active_customer_key", ""))
    if pinned != _DIALOG_DEFAULT_CUSTOMER_KEY:
        app._dialog_conversation_active_customer_key = pinned
        return pinned

    selected_customer = _resolve_selected_customer_from_tree(
        getattr(app, "customer_data_record_tree", None),
        getattr(app, "_customer_data_customer_by_iid", {}) or {},
    )
    if selected_customer:
        key = _normalize_customer_key(selected_customer)
        app._dialog_conversation_active_customer_key = key
        return key

    selected_record_iid = ""
    call_record_tree = getattr(app, "call_record_tree", None)
    if call_record_tree is not None:
        try:
            selected = call_record_tree.selection()
            if selected:
                selected_record_iid = str(selected[0] or "")
        except Exception:
            selected_record_iid = ""
    if selected_record_iid:
        item = (getattr(app, "_call_record_item_by_iid", {}) or {}).get(selected_record_iid, {})
        if isinstance(item, dict):
            customer_name = sanitize_inline_text(str(item.get("customer_name", "")))
            if customer_name:
                key = _normalize_customer_key(customer_name)
                app._dialog_conversation_active_customer_key = key
                return key

    profile_text = ""
    profile_widget = getattr(app, "conversation_customer_profile_text", None)
    if isinstance(profile_widget, ScrolledText):
        try:
            profile_text = profile_widget.get("1.0", "end-1c")
        except Exception:
            profile_text = ""
    if (not profile_text) and callable(getattr(app, "_build_profile_text_from_dialog_profile_table", None)):
        try:
            profile_text = app._build_profile_text_from_dialog_profile_table()
        except Exception:
            profile_text = ""
    if profile_text and callable(getattr(app, "_extract_customer_name_from_profile_text", None)):
        try:
            name = sanitize_inline_text(app._extract_customer_name_from_profile_text(profile_text))
        except Exception:
            name = ""
        if name:
            key = _normalize_customer_key(name)
            app._dialog_conversation_active_customer_key = key
            return key

    app._dialog_conversation_active_customer_key = _DIALOG_DEFAULT_CUSTOMER_KEY
    return _DIALOG_DEFAULT_CUSTOMER_KEY


def _append_dialog_line_to_widget(app, role: str, text: str) -> None:
    tag = "dialog_meta"
    if role == "customer":
        tag = "dialog_customer"
    elif role == "agent":
        tag = "dialog_agent"
    prev_state = str(app.dialog_conversation_text.cget("state"))
    app.dialog_conversation_text.configure(state="normal")
    start = app.dialog_conversation_text.index("end-1c")
    app.dialog_conversation_text.insert("end", text + "\n")
    app.dialog_conversation_text.tag_add(tag, start, app.dialog_conversation_text.index("end-1c"))
    app._trim_scrolled_text(app.dialog_conversation_text, max_lines=800)
    app.dialog_conversation_text.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    app.dialog_conversation_text.see("end")


def _lines_to_entries(content: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    normalized = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    for raw_line in normalized.split("\n"):
        line = str(raw_line)
        if not line:
            continue
        role = "meta"
        tag = _resolve_dialog_history_tag(line)
        if tag in {"dialog_customer", "dialog_customer_history"}:
            role = "customer"
        elif tag in {"dialog_agent", "dialog_agent_history"}:
            role = "agent"
        entries.append({"role": role, "text": line})
    return entries


def _render_dialog_entries(app, entries: list[dict[str, str]], *, see: str = "1.0") -> None:
    widget = app.dialog_conversation_text
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    first_start_seen = False
    for item in entries:
        line = str(item.get("text", ""))
        if not line:
            continue
        tag = _resolve_dialog_history_tag(line)
        # Add 5 blank lines before every "对话开始" marker except the very first one;
        # "对话结束" markers do not get extra blank lines.
        if "对话开始" in line:
            if first_start_seen:
                widget.insert("end", "\n" * 5)
            first_start_seen = True
        start = widget.index("end-1c")
        widget.insert("end", line + "\n")
        widget.tag_add(tag, start, widget.index("end-1c"))
    if entries:
        # Visual separator between historical and new conversation
        widget.insert("end", "\n\n\n\n\n")
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see(see)


def _sync_active_dialog_history_from_widget(app) -> None:
    if not isinstance(getattr(app, "dialog_conversation_text", None), ScrolledText):
        return
    store = _ensure_dialog_history_store(app)
    key = _resolve_active_customer_key(app)
    content = app.dialog_conversation_text.get("1.0", "end-1c")
    entries = _lines_to_entries(content)
    if len(entries) > 800:
        entries = entries[-800:]
    store[key] = entries


def set_dialog_conversation_active_customer(app, customer_name: str) -> None:
    _ensure_dialog_history_store(app)
    app._dialog_conversation_active_customer_key = _normalize_customer_key(customer_name)
    sync_fn = getattr(app, "_sync_dialog_intent_strategy_for_active_customer", None)
    if callable(sync_fn):
        try:
            sync_fn()
        except Exception:
            pass


def refresh_dialog_conversation_for_active_customer(app) -> None:
    store = _ensure_dialog_history_store(app)
    key = _resolve_active_customer_key(app)
    entries = list(store.get(key, []))
    _render_dialog_entries(app, entries, see="1.0")
    sync_fn = getattr(app, "_sync_dialog_intent_strategy_for_active_customer", None)
    if callable(sync_fn):
        try:
            sync_fn()
        except Exception:
            pass


def sync_conversation_profile_status(app) -> None:
    var = getattr(app, "conversation_profile_status_var", None)
    label = getattr(app, "conversation_profile_status_label", None)
    if var is None:
        return
    state_text = str(app.state_var.get() if hasattr(app, "state_var") else "stopped").strip().lower() or "stopped"
    endpoint_text = str(app.endpoint_var.get() if hasattr(app, "endpoint_var") else "-").strip() or "-"
    # Keep header compact so it does not squeeze right-side controls (local/public).
    endpoint_max = 80
    if len(endpoint_text) > endpoint_max:
        endpoint_text = endpoint_text[: endpoint_max - 3] + "..."
    var.set(f"{state_text} | endpoint={endpoint_text}")
    if label is None:
        pass
    else:
        try:
            if label.winfo_exists():
                label.configure(fg="#16a34a" if state_text == "running" else "#dc2626")
        except Exception:
            pass
    monitor_label = getattr(app, "monitor_process_status_label", None)
    if monitor_label is None:
        return
    try:
        if not monitor_label.winfo_exists():
            return
    except Exception:
        return
    monitor_label.configure(fg="#16a34a" if state_text == "running" else "#dc2626")


def reset_runtime_status(app) -> None:
    app.state_var.set("stopped")
    app.session_id_var.set("-")
    app.send_stat_var.set("0 chunks / avg 0ms")
    app.endpoint_var.set("-")
    app._send_count = 0
    app._send_total_ms = 0
    app._control_endpoint = ""
    app._media_endpoint = ""
    app._single_endpoint = ""
    app._tts_stream_active = False
    app._tts_stream_content_start = ""
    app._dialog_agent_stream_active = False
    app._dialog_agent_stream_content_start = ""
    app._asr_stream_active = False
    app._asr_stream_content_start = ""
    sync_conversation_profile_status(app)


def clear_text(widget: ScrolledText) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.configure(state="disabled")


def append_line(widget: ScrolledText, line: str, max_lines: int = 800) -> None:
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    widget.insert("end", line + "\n")
    line_count = int(widget.index("end-1c").split(".")[0])
    if line_count > max_lines:
        drop_to = line_count - max_lines
        widget.delete("1.0", f"{drop_to}.0")
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")


def append_line_with_tag(widget: ScrolledText, line: str, tag: str, max_lines: int = 800) -> None:
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    line_start = widget.index("end")
    widget.insert("end", line + "\n")
    if tag:
        widget.tag_add(tag, f"{line_start} linestart", f"{line_start} lineend")
    line_count = int(widget.index("end-1c").split(".")[0])
    if line_count > max_lines:
        drop_to = line_count - max_lines
        widget.delete("1.0", f"{drop_to}.0")
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")


def set_text_content(widget: ScrolledText, text: str) -> None:
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", text)
    widget.mark_set("insert", "1.0")
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("1.0")


def sanitize_inline_text(text: str) -> str:
    return " ".join((text or "").replace("\r", " ").replace("\n", " ").split())


def parse_intent_window(text: str) -> tuple[list[str], str]:
    labels: list[str] = []
    seen: set[str] = set()
    fallback_label = ""
    marker_prefixes = (
        "intents:",
        "model:",
        "customer:",
        "assistant:",
    )
    for raw_line in (text or "").splitlines():
        line = str(raw_line or "").replace("\r", "").strip()
        if not line:
            continue
        line = re.sub(r"^[\-\*\u2022]\s*", "", line)
        line = re.sub(r"^\d+\s*[\.)]\s*", "", line)
        line = line.rstrip(",;").strip()
        if not line:
            continue
        lower_line = line.lower()
        if lower_line.startswith(("fallback_label:", "fallback:")):
            fallback_label = line.split(":", 1)[1].strip() if ":" in line else ""
            fallback_label = fallback_label.rstrip(",;").strip()
            continue
        if lower_line.startswith(marker_prefixes):
            continue
        if line.startswith("[") and ("]" in line):
            continue
        if re.fullmatch(r"[-_=]{3,}", line):
            continue
        label = line
        if (not label) or (label in seen):
            continue
        labels.append(label)
        seen.add(label)
    return labels, fallback_label


def append_tts_line(app, role: str, text: str) -> None:
    tag = "tts_meta"
    if role == "customer":
        tag = "tts_customer"
    elif role == "agent":
        tag = "tts_agent"
    app.tts_text.configure(state="normal")
    start = app.tts_text.index("end-1c")
    app.tts_text.insert("end", text + "\n")
    app.tts_text.tag_add(tag, start, app.tts_text.index("end-1c"))
    app._trim_scrolled_text(app.tts_text, max_lines=800)
    app.tts_text.configure(state="disabled")
    app.tts_text.see("end")


def start_tts_stream_line(app, prefix: str) -> None:
    app.tts_text.configure(state="normal")
    line_start = app.tts_text.index("end-1c")
    app.tts_text.insert("end", prefix)
    app._tts_stream_content_start = app.tts_text.index("end-1c")
    app.tts_text.tag_add("tts_agent", line_start, app.tts_text.index("end-1c"))
    app._tts_stream_active = True
    app.tts_text.configure(state="disabled")
    app.tts_text.see("end")


def append_tts_stream_text(app, text: str) -> None:
    if not app._tts_stream_active:
        return
    app.tts_text.configure(state="normal")
    app.tts_text.insert("end", text)
    line_start = f"{app._tts_stream_content_start} linestart"
    app.tts_text.tag_add("tts_agent", line_start, app.tts_text.index("end-1c"))
    app.tts_text.configure(state="disabled")
    app.tts_text.see("end")


def replace_tts_stream_text(app, text: str) -> None:
    if not app._tts_stream_active:
        return
    app.tts_text.configure(state="normal")
    end_index = app.tts_text.index("end-1c")
    app.tts_text.delete(app._tts_stream_content_start, end_index)
    app.tts_text.insert("end", text)
    line_start = f"{app._tts_stream_content_start} linestart"
    app.tts_text.tag_add("tts_agent", line_start, app.tts_text.index("end-1c"))
    app.tts_text.configure(state="disabled")
    app.tts_text.see("end")


def close_tts_stream_line(app) -> None:
    if not app._tts_stream_active:
        return
    app.tts_text.configure(state="normal")
    app.tts_text.insert("end", "\n")
    app._trim_scrolled_text(app.tts_text, max_lines=800)
    app.tts_text.configure(state="disabled")
    app.tts_text.see("end")
    app._tts_stream_active = False
    app._tts_stream_content_start = ""


def append_dialog_conversation_line(app, role: str, text: str) -> None:
    store = _ensure_dialog_history_store(app)
    key = _resolve_active_customer_key(app)
    lines = list(store.get(key, []))
    lines.append({"role": str(role or "meta"), "text": str(text or "")})
    if len(lines) > 800:
        lines = lines[-800:]
    store[key] = lines
    if _normalize_customer_key(getattr(app, "_dialog_conversation_active_customer_key", "")) == key:
        _append_dialog_line_to_widget(app, role=str(role or "meta"), text=str(text or ""))


def _resolve_dialog_history_tag(line: str) -> str:
    text = str(line or "")
    if _is_session_separator(text):
        return "dialog_session_sep"
    if ("客户:" in text) or ("瀹㈡埛:" in text):
        return "dialog_customer_history"
    if ("坐席:" in text) or ("鍧愬腑:" in text):
        return "dialog_agent_history"
    return "dialog_meta_history"


def render_dialog_conversation_history(app, text: str, customer_name: str = "") -> None:
    store = _ensure_dialog_history_store(app)
    key = _normalize_customer_key(customer_name) if customer_name else _resolve_active_customer_key(app)
    app._dialog_conversation_active_customer_key = key
    entries = _lines_to_entries(text)
    if len(entries) > 800:
        entries = entries[-800:]
    store[key] = entries
    # Only display the most recent session (from last separator onwards) in the widget
    display_entries = _filter_entries_to_last_session(entries)
    _render_dialog_entries(app, display_entries, see="1.0")
    sync_fn = getattr(app, "_sync_dialog_intent_strategy_for_active_customer", None)
    if callable(sync_fn):
        try:
            sync_fn()
        except Exception:
            pass


def append_dialog_session_separator(app) -> None:
    """Insert an orange session-separator line into the conversation widget and in-memory store.
    Call this when starting a new conversation session after loading history."""
    sep_line = _build_session_separator()
    store = _ensure_dialog_history_store(app)
    key = _resolve_active_customer_key(app)
    lines = list(store.get(key, []))
    lines.append({"role": "session_sep", "text": sep_line})
    if len(lines) > 800:
        lines = lines[-800:]
    store[key] = lines
    widget = app.dialog_conversation_text
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    start = widget.index("end-1c")
    widget.insert("end", sep_line + "\n")
    widget.tag_add("dialog_session_sep", start, widget.index("end-1c"))
    app._trim_scrolled_text(widget, max_lines=800)
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")


def append_dialog_session_marker(app, marker_text: str, *, blank_lines_before: int = 5) -> None:
    """Insert a black marker line for session start/end and sync in-memory history."""
    widget = app.dialog_conversation_text
    marker = sanitize_inline_text(str(marker_text or ""))
    if not marker:
        return
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    for _ in range(max(0, int(blank_lines_before))):
        widget.insert("end", "\n")
    start = widget.index("end-1c")
    widget.insert("end", marker + "\n")
    widget.tag_add("dialog_session_marker", start, widget.index("end-1c"))
    app._trim_scrolled_text(widget, max_lines=800)
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")
    _sync_active_dialog_history_from_widget(app)


def extract_dialog_current_session_text(app) -> str:
    """Return the widget's conversation text trimmed to the last session separator.
    Used when saving so that each call record stores only its own session's dialogue."""
    content = (app.dialog_conversation_text.get("1.0", "end-1c") or "").strip()
    lines = content.splitlines()
    last_sep_idx = -1
    for i, line in enumerate(lines):
        if _is_session_separator(line):
            last_sep_idx = i
    if last_sep_idx >= 0:
        return "\n".join(lines[last_sep_idx:]).strip()
    return content


def append_dialog_customer_intent(app, customer_text: str, intent_summary: str) -> None:
    widget = app.dialog_conversation_text
    safe_intent = app._sanitize_inline_text(intent_summary)
    if not safe_intent:
        return
    safe_customer_text = app._sanitize_inline_text(customer_text)
    content = widget.get("1.0", "end-1c")
    lines = content.splitlines()
    if not lines:
        return
    target_line = 0
    for idx in range(len(lines), 0, -1):
        line_text = lines[idx - 1]
        if "客户:" not in line_text:
            continue
        if safe_customer_text and safe_customer_text not in line_text:
            continue
        target_line = idx
        break
    if target_line <= 0:
        for idx in range(len(lines), 0, -1):
            if "客户:" in lines[idx - 1]:
                target_line = idx
                break
    if target_line <= 0:
        return
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    line_start = f"{target_line}.0"
    line_end = widget.index(f"{target_line}.0 lineend")
    current_line = widget.get(line_start, line_end)
    old_marker = "  [意图:"
    old_pos = current_line.find(old_marker)
    if old_pos >= 0:
        remove_start = f"{target_line}.0+{old_pos}c"
        widget.delete(remove_start, line_end)
        line_end = widget.index(f"{target_line}.0 lineend")
    intent_text = f"  [意图: {safe_intent}]"
    widget.insert(line_end, intent_text)
    intent_start = line_end
    intent_end = widget.index(f"{intent_start}+{len(intent_text)}c")
    widget.tag_add("dialog_customer", intent_start, intent_end)
    widget.tag_add("dialog_intent_inline", intent_start, intent_end)
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")
    _sync_active_dialog_history_from_widget(app)


def start_dialog_agent_stream_line(app, prefix: str) -> None:
    prev_state = str(app.dialog_conversation_text.cget("state"))
    app.dialog_conversation_text.configure(state="normal")
    line_start = app.dialog_conversation_text.index("end-1c")
    app.dialog_conversation_text.insert("end", prefix)
    app._dialog_agent_stream_content_start = app.dialog_conversation_text.index("end-1c")
    app.dialog_conversation_text.tag_add("dialog_agent", line_start, app.dialog_conversation_text.index("end-1c"))
    app._dialog_agent_stream_active = True
    app.dialog_conversation_text.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    app.dialog_conversation_text.see("end")


def append_dialog_agent_stream_text(app, text: str) -> None:
    if not app._dialog_agent_stream_active:
        return
    prev_state = str(app.dialog_conversation_text.cget("state"))
    app.dialog_conversation_text.configure(state="normal")
    app.dialog_conversation_text.insert("end", text)
    line_start = f"{app._dialog_agent_stream_content_start} linestart"
    app.dialog_conversation_text.tag_add("dialog_agent", line_start, app.dialog_conversation_text.index("end-1c"))
    app.dialog_conversation_text.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    app.dialog_conversation_text.see("end")


def replace_dialog_agent_stream_text(app, text: str) -> None:
    if not app._dialog_agent_stream_active:
        return
    prev_state = str(app.dialog_conversation_text.cget("state"))
    app.dialog_conversation_text.configure(state="normal")
    end_index = app.dialog_conversation_text.index("end-1c")
    app.dialog_conversation_text.delete(app._dialog_agent_stream_content_start, end_index)
    app.dialog_conversation_text.insert("end", text)
    line_start = f"{app._dialog_agent_stream_content_start} linestart"
    app.dialog_conversation_text.tag_add("dialog_agent", line_start, app.dialog_conversation_text.index("end-1c"))
    app.dialog_conversation_text.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    app.dialog_conversation_text.see("end")


def close_dialog_agent_stream_line(app) -> None:
    if not app._dialog_agent_stream_active:
        return
    prev_state = str(app.dialog_conversation_text.cget("state"))
    app.dialog_conversation_text.configure(state="normal")
    app.dialog_conversation_text.insert("end", "\n")
    app._trim_scrolled_text(app.dialog_conversation_text, max_lines=800)
    app.dialog_conversation_text.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    app.dialog_conversation_text.see("end")
    app._dialog_agent_stream_active = False
    app._dialog_agent_stream_content_start = ""
    _sync_active_dialog_history_from_widget(app)


def start_asr_stream_line(app, prefix: str) -> None:
    app.asr_text.configure(state="normal")
    app.asr_text.insert("end", prefix)
    app._asr_stream_content_start = app.asr_text.index("end-1c")
    app._asr_stream_active = True
    app.asr_text.configure(state="disabled")
    app.asr_text.see("end")


def replace_asr_stream_text(app, text: str) -> None:
    if not app._asr_stream_active:
        return
    app.asr_text.configure(state="normal")
    end_index = app.asr_text.index("end-1c")
    app.asr_text.delete(app._asr_stream_content_start, end_index)
    app.asr_text.insert("end", text)
    app.asr_text.configure(state="disabled")
    app.asr_text.see("end")


def close_asr_stream_line(app, tag: str = "") -> None:
    if not app._asr_stream_active:
        return
    app.asr_text.configure(state="normal")
    if tag:
        line_start = f"{app._asr_stream_content_start} linestart"
        app.asr_text.tag_add(tag, line_start, "end-1c")
    app.asr_text.insert("end", "\n")
    app._trim_scrolled_text(app.asr_text, max_lines=800)
    app.asr_text.configure(state="disabled")
    app.asr_text.see("end")
    app._asr_stream_active = False
    app._asr_stream_content_start = ""


def trim_scrolled_text(widget: ScrolledText, max_lines: int = 800) -> None:
    line_count = int(widget.index("end-1c").split(".")[0])
    if line_count > max_lines:
        drop_to = line_count - max_lines
        widget.delete("1.0", f"{drop_to}.0")
