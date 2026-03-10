from __future__ import annotations

import json
import queue
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from tkinter import filedialog, messagebox


def _normalize_command_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace(" ", "").replace("\t", "")
    while text and text[-1] in "。．.!！?？,，;；:：":
        text = text[:-1]
    return text


def _is_system_dialog_command_text(text: str, command: str = "") -> bool:
    cmd = str(command or "").strip().lower()
    if cmd in {"start_dialog", "end_dialog"}:
        return True
    normalized = _normalize_command_text(text)
    return normalized in {"开始对话", "结束对话"}


def _append_session_dialog_line(app, role: str, text: str) -> None:
    role_name = "客户" if role == "customer" else ("坐席" if role == "agent" else "系统")
    safe_text = app._sanitize_inline_text(str(text or ""))
    if not safe_text:
        return
    if not isinstance(getattr(app, "_current_session_dialog_lines", None), list):
        app._current_session_dialog_lines = []
    line = f"{role_name}: {safe_text}"
    if (not app._current_session_dialog_lines) or app._current_session_dialog_lines[-1] != line:
        app._current_session_dialog_lines.append(line)
    if len(app._current_session_dialog_lines) > 200:
        app._current_session_dialog_lines = app._current_session_dialog_lines[-200:]


def _append_dialog_turn(app, role: str, ts_text: str, text: str) -> str:
    safe_text = app._sanitize_inline_text(str(text or ""))
    if not safe_text:
        return ""
    prefix = "客户" if role == "customer" else ("坐席" if role == "agent" else "系统")
    app._append_dialog_conversation_line(role=role, text=f"[{ts_text}] {prefix}: {safe_text}")
    _append_session_dialog_line(app, role=role, text=safe_text)
    return safe_text


def _remember_latency_text(app, key: str, text: str) -> None:
    if not isinstance(getattr(app, "_pending_latency", None), dict):
        app._pending_latency = {}
    cleaned = app._sanitize_inline_text(str(text or ""))
    if cleaned:
        app._pending_latency[key] = cleaned


def _append_dialog_session_marker(app, phase: str, event_ts) -> None:
    marker_phase = "开始" if phase == "start" else "结束"
    dt_text = event_ts.strftime("%Y-%m-%d %H:%M:%S")
    marker = f"=========================== 对话{marker_phase}：{dt_text} ==========================="
    append_marker = getattr(app, "_append_dialog_session_marker", None)
    if callable(append_marker):
        try:
            append_marker(marker, blank_lines_before=5)
        except Exception:
            pass
    save_snapshot = getattr(app, "_save_persisted_conversation_tab_snapshots", None)
    if callable(save_snapshot):
        try:
            save_snapshot()
        except Exception:
            pass


def _to_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return 0


def _to_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return 0.0


def clear_views(app) -> None:
    sync_intent_state = getattr(app, "_sync_dialog_intent_strategy_for_active_customer", None)
    if callable(sync_intent_state):
        try:
            sync_intent_state()
        except Exception:
            pass
    active_key = app._sanitize_inline_text(str(getattr(app, "_dialog_conversation_active_customer_key", "") or "")) or "__default__"
    intent_store = getattr(app, "_dialog_intent_state_by_customer", None)
    if not isinstance(intent_store, dict):
        intent_store = {}
        app._dialog_intent_state_by_customer = intent_store
    intent_store[active_key] = {"intents": [], "history": [], "strategies": []}

    app._pending_latency = None
    latency_widget = getattr(app, "latency_text", None)
    if latency_widget is not None:
        try:
            app._clear_text(latency_widget)
        except Exception:
            pass
    app._clear_text(app.asr_text)
    commit_widget = getattr(app, "asr_commit_text", None)
    if commit_widget is not None:
        try:
            app._clear_text(commit_widget)
        except Exception:
            pass
    app._clear_text(app.tts_text)
    app._clear_text(app.nlp_input_text)
    app._clear_text(app.intent_text)
    app._clear_text(app.intent_system_text)
    app._clear_text(app.intent_prompt_text)
    billing_widget = getattr(app, "dialog_billing_text", None)
    if billing_widget is not None:
        try:
            app._clear_text(billing_widget)
        except Exception:
            pass
    billing_table = getattr(app, "dialog_billing_table", None)
    if billing_table is not None:
        try:
            for iid in billing_table.get_children():
                billing_table.delete(iid)
        except Exception:
            pass
    intent_table = getattr(app, "dialog_intent_table", None)
    if intent_table is not None:
        try:
            for iid in intent_table.get_children():
                intent_table.delete(iid)
        except Exception:
            pass
    app._set_text_content(app.dialog_conversation_text, "")
    app.dialog_conversation_text.configure(state="normal")
    app._clear_text(app.dialog_intent_text)
    if getattr(app, "dialog_strategy_text", None) is not None:
        app._clear_text(app.dialog_strategy_text)
    app._clear_text(app.log_text)
    app._event_history.clear()
    app._event_backlog_high.clear()
    app._event_backlog_normal.clear()
    app._settings_event_backlog.clear()
    app._pending_log_lines.clear()
    app._next_log_flush_at = 0.0
    app._reset_send_done_summary()
    app._tts_stream_active = False
    app._tts_stream_content_start = ""
    app._dialog_agent_stream_active = False
    app._dialog_agent_stream_content_start = ""
    app._asr_stream_active = False
    app._asr_stream_content_start = ""
    app._dialog_intent_history = []
    app._dialog_intent_state_current_customer_key = active_key
    app._current_session_customer_lines = []
    app._current_session_dialog_lines = []
    app._current_agent_stream_text = ""
    app._flow_active_node_id = ""
    app._asr_history_lines.clear()
    app._refresh_system_instruction()
    app._reset_runtime_status()
    app._refresh_dialog_intent_queue_view()


def export_events(app) -> None:
    if not app._event_history:
        messagebox.showinfo("No data", "No events to export.")
        return
    default_name = f"session_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path = filedialog.asksaveasfilename(
        title="Export events",
        defaultextension=".json",
        initialfile=default_name,
        filetypes=[("JSON", "*.json"), ("All files", "*.*")],
    )
    if not out_path:
        return
    Path(out_path).write_text(json.dumps(app._event_history, ensure_ascii=False, indent=2), encoding="utf-8")
    messagebox.showinfo("Exported", f"Saved: {out_path}")


def is_high_priority_event(kind: str, high_priority_event_kinds: set[str] | frozenset[str]) -> bool:
    return kind in high_priority_event_kinds


def drain_event_queues(
    app,
    *,
    is_high_priority: Callable[[str], bool],
    limit: int,
) -> None:
    if limit <= 0:
        return
    main_quota = max(1, int(limit * 0.75))
    settings_quota = max(1, limit - main_quota)
    drained = 0

    for _ in range(main_quota):
        try:
            event = app._event_queue.get_nowait()
        except queue.Empty:
            break
        if is_high_priority(event.kind):
            app._event_backlog_high.append(event)
        else:
            app._event_backlog_normal.append(event)
        drained += 1

    for _ in range(settings_quota):
        try:
            event = app._settings_asr_queue.get_nowait()
        except queue.Empty:
            break
        app._settings_event_backlog.append(event)
        drained += 1

    remaining = limit - drained
    while remaining > 0:
        pulled = False
        try:
            event = app._event_queue.get_nowait()
            if is_high_priority(event.kind):
                app._event_backlog_high.append(event)
            else:
                app._event_backlog_normal.append(event)
            remaining -= 1
            pulled = True
        except queue.Empty:
            pass
        if remaining <= 0:
            break
        try:
            event = app._settings_asr_queue.get_nowait()
            app._settings_event_backlog.append(event)
            remaining -= 1
            pulled = True
        except queue.Empty:
            pass
        if not pulled:
            break


def pop_next_buffered_event(app):
    if app._event_backlog_high:
        return "main", app._event_backlog_high.popleft()
    if app._settings_event_backlog:
        return "settings", app._settings_event_backlog.popleft()
    if app._event_backlog_normal:
        return "main", app._event_backlog_normal.popleft()
    return None


def poll_events(
    app,
    *,
    drain_limit: int,
    max_events_per_tick: int,
    max_ms_per_tick: float,
    busy_interval_ms: int,
    idle_interval_ms: int,
) -> None:
    app._drain_event_queues(limit=drain_limit)
    tick_start = time.perf_counter()
    processed = 0

    while processed < max_events_per_tick:
        elapsed_ms = (time.perf_counter() - tick_start) * 1000.0
        if elapsed_ms >= max_ms_per_tick:
            break
        next_item = app._pop_next_buffered_event()
        if next_item is None:
            break
        source, event = next_item
        if source == "main":
            target_tab_id = app._runtime_conversation_tab_id or app._active_conversation_tab_id
            if target_tab_id:
                with app._using_conversation_tab_context(target_tab_id):
                    app._handle_event(event)
            else:
                app._handle_event(event)
        else:
            app._handle_settings_asr_event(event)
        processed += 1

    app._flush_send_done_summary(force=False)
    app._flush_log_buffer(force=False)
    app._check_asr_wait_timeout()
    has_pending = (
        bool(app._event_backlog_high)
        or bool(app._event_backlog_normal)
        or bool(app._settings_event_backlog)
        or (not app._event_queue.empty())
        or (not app._settings_asr_queue.empty())
    )
    next_interval = busy_interval_ms if has_pending else idle_interval_ms
    app.after(next_interval, app._poll_events)


def handle_event(
    app,
    event,
    *,
    event_history_max: int,
    event_history_trim_batch: int,
) -> None:
    ts_text = event.ts.strftime("%H:%M:%S")
    app._event_history.append(
        {
            "ts": event.ts.isoformat(timespec="milliseconds"),
            "kind": event.kind,
            "payload": event.payload,
            "raw": event.raw,
        }
    )
    if len(app._event_history) > event_history_max:
        overflow = len(app._event_history) - event_history_max
        trim_count = max(overflow, event_history_trim_batch)
        del app._event_history[:trim_count]

    if event.kind == "process_started":
        prev_state = str(app.state_var.get() if hasattr(app, "state_var") else "").strip().lower()
        if prev_state != "running":
            _append_dialog_session_marker(app, "start", event.ts)
        # Start each conversation with a clean monitor panel (4 sub-windows only).
        for widget_name in ("asr_text", "tts_text", "nlp_input_text", "latency_text"):
            widget = getattr(app, widget_name, None)
            if widget is None:
                continue
            try:
                app._clear_text(widget)
            except Exception:
                pass
        app._pending_latency = None
        app._asr_stream_active = False
        app._asr_stream_content_start = ""
        app._tts_stream_active = False
        app._tts_stream_content_start = ""
        sync_intent_state = getattr(app, "_sync_dialog_intent_strategy_for_active_customer", None)
        if callable(sync_intent_state):
            try:
                sync_intent_state()
            except Exception:
                pass
        active_key = app._sanitize_inline_text(str(getattr(app, "_dialog_conversation_active_customer_key", "") or "")) or "__default__"
        intent_store = getattr(app, "_dialog_intent_state_by_customer", None)
        if not isinstance(intent_store, dict):
            intent_store = {}
            app._dialog_intent_state_by_customer = intent_store
        intent_store[active_key] = {"history": []}
        app.state_var.set("running")
        app._sync_conversation_profile_status()
        app._dialog_intent_history = []
        app._dialog_intent_state_current_customer_key = active_key
        app._current_session_customer_lines = []
        app._current_session_dialog_lines = []
        app._current_agent_stream_text = ""
        app._refresh_dialog_intent_queue_view()
        app._append_line(app.log_text, f"[{ts_text}] process started: {event.payload.get('command', '')}")
        return

    if event.kind in {"process_stopped", "process_exit"}:
        prev_state = str(app.state_var.get() if hasattr(app, "state_var") else "").strip().lower()
        if prev_state != "stopped":
            _append_dialog_session_marker(app, "end", event.ts)
        app.state_var.set("stopped")
        close_call_overlay = getattr(app, "_close_customer_call_overlay", None)
        if callable(close_call_overlay):
            try:
                close_call_overlay()
            except Exception:
                pass
        app._sync_conversation_profile_status()
        code = event.payload.get("return_code")
        app._set_microphone_open("main", False, reason=event.kind)
        app._close_asr_stream_line()
        app._close_dialog_agent_stream_line()
        app._runtime_conversation_tab_id = ""
        app._flush_send_done_summary(force=True)
        app._flush_log_buffer(force=True)
        app._append_line(app.log_text, f"[{ts_text}] process exit: return_code={code}")
        app._close_runtime_log_file()
        return

    if event.kind == "log":
        if app._consume_send_done_log(ts_text=ts_text, raw_line=event.raw):
            return
        app._buffer_log_line(f"[{ts_text}] {event.raw}")
        app._update_microphone_state_from_log("main", event.raw)
        return

    if event.kind == "session_ready":
        app.session_id_var.set(str(event.payload.get("session_id", "-")))
        app._sync_conversation_profile_status()
        return

    if event.kind == "ws_connected_split":
        channel = str(event.payload.get("channel", ""))
        endpoint = str(event.payload.get("endpoint", ""))
        app.transport_var.set("ws")
        app.channel_var.set("split")
        if channel == "control":
            app._control_endpoint = endpoint
        elif channel == "media":
            app._media_endpoint = endpoint
        app.endpoint_var.set(f"control={app._control_endpoint or '-'} | media={app._media_endpoint or '-'}")
        app._sync_conversation_profile_status()
        on_overlay_ws_connected = getattr(app, "_on_customer_call_overlay_ws_connected", None)
        if callable(on_overlay_ws_connected):
            try:
                on_overlay_ws_connected()
            except Exception:
                pass
        return

    if event.kind == "ws_connected_single":
        app.transport_var.set("ws")
        app.channel_var.set("single")
        app._single_endpoint = str(event.payload.get("endpoint", ""))
        app.endpoint_var.set(app._single_endpoint or "-")
        app._sync_conversation_profile_status()
        on_overlay_ws_connected = getattr(app, "_on_customer_call_overlay_ws_connected", None)
        if callable(on_overlay_ws_connected):
            try:
                on_overlay_ws_connected()
            except Exception:
                pass
        return

    if event.kind == "tts_first_frame":
        on_overlay_tts_first_frame = getattr(app, "_on_customer_call_overlay_tts_first_frame", None)
        if callable(on_overlay_tts_first_frame):
            try:
                on_overlay_tts_first_frame()
            except Exception:
                pass
        return

    if event.kind == "audio_sent":
        app._send_count += 1
        app._send_total_ms += int(event.payload.get("cost_ms", 0))
        avg_ms = app._send_total_ms / max(app._send_count, 1)
        app.send_stat_var.set(f"{app._send_count} chunks / avg {avg_ms:.1f}ms")
        return

    if event.kind == "audio_send_failed":
        reason = str(event.payload.get("reason", ""))
        chunk = event.payload.get("chunk_index")
        app._append_line(app.log_text, f"[{ts_text}] [send] chunk={chunk} failed: {reason}")
        return

    if event.kind == "ws_command":
        command = app._sanitize_inline_text(str(event.payload.get("command", "")))
        action = app._sanitize_inline_text(str(event.payload.get("action", "")))
        terminate_source = app._sanitize_inline_text(str(event.payload.get("terminate_source", "")))
        terminate_reason = app._sanitize_inline_text(str(event.payload.get("terminate_reason", "")))
        terminate_trace_id = app._sanitize_inline_text(str(event.payload.get("terminate_trace_id", "")))
        terminate_by = app._sanitize_inline_text(str(event.payload.get("terminate_by", "")))
        trigger_text = app._sanitize_inline_text(str(event.payload.get("trigger_text", "")))
        app._append_line(
            app.log_text,
            (
                f"[{ts_text}] [ws/terminate] command={command} action={action} "
                f"source={terminate_source} by={terminate_by} reason={terminate_reason} "
                f"trace_id={terminate_trace_id} trigger_text={trigger_text}"
            ),
        )
        return

    if event.kind == "billing_started":
        source = app._sanitize_inline_text(str(event.payload.get("source", "") or ""))
        trigger_text = app._sanitize_inline_text(str(event.payload.get("trigger_text", "") or ""))
        started_at = event.payload.get("started_at")
        app._append_line(
            app.log_text,
            f"[{ts_text}] [billing] started source={source or '-'} trigger={trigger_text or '-'} started_at={started_at}",
        )
        return

    if event.kind == "billing_result":
        usage = event.payload.get("usage", {}) if isinstance(event.payload, dict) else {}
        cost = event.payload.get("cost", {}) if isinstance(event.payload, dict) else {}
        tts = event.payload.get("tts", {}) if isinstance(event.payload, dict) else {}
        asr = event.payload.get("asr", {}) if isinstance(event.payload, dict) else {}
        model_costs = event.payload.get("model_costs", {}) if isinstance(event.payload, dict) else {}
        models = event.payload.get("models", []) if isinstance(event.payload, dict) else []
        total_cost = _to_float(cost.get("total") if isinstance(cost, dict) else 0.0)
        llm_cost = _to_float(cost.get("llm_total") if isinstance(cost, dict) else 0.0)
        tts_cost = _to_float(cost.get("tts_total") if isinstance(cost, dict) else 0.0)
        asr_cost = _to_float(cost.get("asr_total") if isinstance(cost, dict) else 0.0)
        prompt_tokens = _to_int(usage.get("prompt_tokens") if isinstance(usage, dict) else 0)
        completion_tokens = _to_int(usage.get("completion_tokens") if isinstance(usage, dict) else 0)
        total_tokens = _to_int(usage.get("total_tokens") if isinstance(usage, dict) else 0)
        cached_tokens = _to_int(usage.get("cached_tokens") if isinstance(usage, dict) else 0)
        reasoning_tokens = _to_int(usage.get("reasoning_tokens") if isinstance(usage, dict) else 0)
        tts_usage = tts.get("usage", {}) if isinstance(tts, dict) else {}
        asr_usage = asr.get("usage", {}) if isinstance(asr, dict) else {}
        tts_characters = _to_int(tts_usage.get("characters") if isinstance(tts_usage, dict) else 0)
        asr_audio_seconds = _to_float(asr_usage.get("audio_seconds") if isinstance(asr_usage, dict) else 0.0)
        duration_seconds = _to_float(event.payload.get("duration_seconds") if isinstance(event.payload, dict) else 0.0)
        cost_16 = model_costs.get("doubao-seed-1.6-flash", {}) if isinstance(model_costs, dict) else {}
        cost_18 = model_costs.get("doubao-seed-1.8", {}) if isinstance(model_costs, dict) else {}
        summary = (
            f"本次通话费用：¥{total_cost:.5f}，"
            f"分项(LLM=¥{llm_cost:.5f}，TTS=¥{tts_cost:.5f}，ASR=¥{asr_cost:.5f})，"
            f"token 总计={total_tokens}（输入={prompt_tokens}，输出={completion_tokens}，缓存输入={cached_tokens}，思维={reasoning_tokens}），"
            f"计费时长={duration_seconds:.1f}s"
        )
        per_model_summary = (
            f"模型费用：1.6-flash=¥{_to_float(cost_16.get('cost_total')):.5f}"
            f"(token={_to_int(cost_16.get('total_tokens'))})，"
            f"1.8=¥{_to_float(cost_18.get('cost_total')):.5f}"
            f"(token={_to_int(cost_18.get('total_tokens'))})，"
            f"TTS=¥{tts_cost:.5f}(chars={tts_characters})，"
            f"ASR=¥{asr_cost:.5f}(audio_s={asr_audio_seconds:.3f})"
        )
        price_per_minute = 0.0
        if duration_seconds > 0:
            price_per_minute = (total_cost * 60.0) / duration_seconds
        app._last_billing_total_cost = round(total_cost, 5)
        app._last_billing_duration_seconds = round(duration_seconds, 3)
        app._last_billing_price_per_minute = round(price_per_minute, 5)
        billing_rows = [
            ("本次通话费用", f"¥{total_cost:.5f}"),
            ("价格/分钟", f"¥{price_per_minute:.5f}" if duration_seconds > 0 else "-"),
            ("计费时长", f"{duration_seconds:.1f}s"),
            ("TTS", f"¥{tts_cost:.5f} (chars={tts_characters})"),
            ("ASR", f"¥{asr_cost:.5f} (audio_s={asr_audio_seconds:.3f})"),
            ("LLM", f"¥{llm_cost:.5f}"),
            ("token 总计", str(total_tokens)),
            ("1.6-flash", f"¥{_to_float(cost_16.get('cost_total')):.5f} (token={_to_int(cost_16.get('total_tokens'))})"),
            ("1.8", f"¥{_to_float(cost_18.get('cost_total')):.5f} (token={_to_int(cost_18.get('total_tokens'))})"),
            ("输入", str(prompt_tokens)),
            ("输出", str(completion_tokens)),
            ("缓存输入", str(cached_tokens)),
            ("思维", str(reasoning_tokens)),
        ]
        billing_widget = getattr(app, "dialog_billing_text", None)
        if billing_widget is not None:
            try:
                app._set_text_content(
                    billing_widget,
                    "\n".join([f"{k}: {v}" for k, v in billing_rows]),
                )
            except Exception:
                pass
        billing_table = getattr(app, "dialog_billing_table", None)
        if billing_table is not None:
            try:
                for iid in billing_table.get_children():
                    billing_table.delete(iid)
                for idx, (item_name, value_text) in enumerate(billing_rows, start=1):
                    tag = "billing_even" if (idx % 2 == 0) else "billing_odd"
                    billing_table.insert("", "end", values=(item_name, value_text), tags=(tag,))
            except Exception:
                pass
        app._append_tts_line(role="meta", text=f"[{ts_text}] {summary}")
        app._append_tts_line(role="meta", text=f"[{ts_text}] {per_model_summary}")
        app._append_line(app.log_text, f"[{ts_text}] [billing] {summary}")
        app._append_line(app.log_text, f"[{ts_text}] [billing] {per_model_summary}")
        if isinstance(models, list):
            for item in models:
                if not isinstance(item, dict):
                    continue
                model_name = app._sanitize_inline_text(str(item.get("model", "") or ""))
                model_key = app._sanitize_inline_text(str(item.get("model_key", "") or ""))
                calls = _to_int(item.get("calls"))
                item_usage = item.get("usage", {}) if isinstance(item.get("usage"), dict) else {}
                item_cost = item.get("cost", {}) if isinstance(item.get("cost"), dict) else {}
                app._append_line(
                    app.log_text,
                    (
                        f"[{ts_text}] [billing/model] model={model_name or model_key or '-'} calls={calls} "
                        f"total_tokens={_to_int(item_usage.get('total_tokens'))} "
                        f"prompt={_to_int(item_usage.get('prompt_tokens'))} "
                        f"completion={_to_int(item_usage.get('completion_tokens'))} "
                        f"cached={_to_int(item_usage.get('cached_tokens'))} "
                        f"cost=¥{_to_float(item_cost.get('total')):.5f}"
                    ),
                )
        return

    if event.kind == "ws_disconnect":
        channel = app._sanitize_inline_text(str(event.payload.get("channel", "")))
        reason = app._sanitize_inline_text(str(event.payload.get("reason", "")))
        cause = app._sanitize_inline_text(str(event.payload.get("cause", "")))
        terminate_source = app._sanitize_inline_text(str(event.payload.get("terminate_source", "")))
        terminate_reason = app._sanitize_inline_text(str(event.payload.get("terminate_reason", "")))
        terminate_trace_id = app._sanitize_inline_text(str(event.payload.get("terminate_trace_id", "")))
        app._append_line(
            app.log_text,
            (
                f"[{ts_text}] [ws/disconnect] channel={channel} reason={reason} cause={cause} "
                f"source={terminate_source} terminate_reason={terminate_reason} trace_id={terminate_trace_id}"
            ),
        )
        return

    if event.kind == "asr_partial":
        text = app._sanitize_inline_text(str(event.payload.get("text", "")))
        command = str(event.payload.get("command", "")).strip()
        if not text:
            return
        if command:
            text = f"{text} | command={command}"
        if not app._asr_stream_active:
            app._start_asr_stream_line(prefix=f"[{ts_text}] ")
        app._replace_asr_stream_text(text)
        return

    if event.kind == "asr_commit":
        text = app._sanitize_inline_text(str(event.payload.get("text", "")))
        command = str(event.payload.get("command", "")).strip()
        nlp_submitted = bool(event.payload.get("nlp_submitted", True))
        asr_color_tag = "asr_nlp" if nlp_submitted else "asr_no_nlp"
        command_suffix = f" | command={command}" if command else ""
        is_system_command = _is_system_dialog_command_text(text=text, command=command)
        if text and (not is_system_command):
            # If agent stream line is still open, close it first so customer text
            # starts on a new line instead of being appended to the same row.
            if getattr(app, "_dialog_agent_stream_active", False):
                app._close_dialog_agent_stream_line()
            if getattr(app, "_tts_stream_active", False):
                app._close_tts_stream_line()
            clean_text = _append_dialog_turn(app, role="customer", ts_text=ts_text, text=text)
            if clean_text:
                app._append_tts_line(role="customer", text=f"[{ts_text}] 客户: {clean_text}")
        if text:
            if not isinstance(getattr(app, "_current_session_customer_lines", None), list):
                app._current_session_customer_lines = []
            if (not is_system_command) and ((not app._current_session_customer_lines) or app._current_session_customer_lines[-1] != text):
                app._current_session_customer_lines.append(text)
                _append_session_dialog_line(app, role="customer", text=text)
        if app._asr_stream_active:
            if text:
                app._replace_asr_stream_text(f"{text}{command_suffix}")
            app._close_asr_stream_line(tag=asr_color_tag)
        else:
            if not text:
                return
            app._append_line_with_tag(app.asr_text, f"[{ts_text}] {text}{command_suffix}", tag=asr_color_tag)
        return

    if event.kind == "tts_start":
        app._close_tts_stream_line()
        return

    if event.kind == "nlp_prompt":
        mode = app._sanitize_inline_text(str(event.payload.get("mode", ""))) or "-"
        prompt_text = app._sanitize_inline_text(str(event.payload.get("text", "")))
        if not prompt_text:
            return
        _remember_latency_text(app, "nlp_text", prompt_text.replace(" || ", " | "))
        targets = []
        if app.nlp_input_text is not None:
            targets.append(app.nlp_input_text)
        for widget in targets:
            app._append_line(widget, f"[{ts_text}] mode={mode}")
            for part in prompt_text.split(" || "):
                line = app._sanitize_inline_text(part)
                if line:
                    app._append_line(widget, f"  {line}")
            app._append_line(widget, "-" * 40)
        return

    if event.kind == "workflow_progress":
        app._handle_workflow_progress_event(event.payload, ts_text)
        return

    if event.kind == "intent_result":
        customer_text = app._sanitize_inline_text(str(event.payload.get("text", "")))
        intents_value = event.payload.get("intents", [])
        intents: list[str] = []
        if isinstance(intents_value, list):
            intents = [app._sanitize_inline_text(str(item)) for item in intents_value if str(item).strip()]
        elif intents_value is not None:
            item = app._sanitize_inline_text(str(intents_value))
            if item:
                intents = [item]
        model = app._sanitize_inline_text(str(event.payload.get("model", "")))
        app._append_line(app.intent_system_text, f"[{ts_text}] 客户: {customer_text or '-'}")
        app._append_line(
            app.intent_system_text,
            f"  intents: {', '.join(intents) if intents else '-'}",
        )
        if model:
            app._append_line(app.intent_system_text, f"  model: {model}")
        app._append_line(app.intent_system_text, "-" * 40)
        existing_history = list(getattr(app, "_dialog_intent_history", []) or [])
        for intent in intents:
            if intent and (intent not in existing_history):
                existing_history.append(intent)
        app._dialog_intent_history = existing_history[-200:]
        active_key = app._sanitize_inline_text(str(getattr(app, "_dialog_conversation_active_customer_key", "") or "")) or "__default__"
        store = getattr(app, "_dialog_intent_state_by_customer", None)
        if not isinstance(store, dict):
            store = {}
            app._dialog_intent_state_by_customer = store
        store[active_key] = {
            "history": list(app._dialog_intent_history),
        }
        app._dialog_intent_state_current_customer_key = active_key
        if callable(getattr(app, "_sync_dialog_intent_strategy_for_active_customer", None)):
            app._sync_dialog_intent_strategy_for_active_customer()
        app._refresh_dialog_intent_queue_view()
        intent_summary = ", ".join(intents) if intents else "-"
        if intent_summary and intent_summary != "-":
            app._append_dialog_customer_intent(customer_text=customer_text, intent_summary=intent_summary)
        return

    if event.kind == "intent_prompt":
        customer_text = app._sanitize_inline_text(str(event.payload.get("text", "")))
        prompt_text = app._sanitize_inline_text(str(event.payload.get("prompt", "")))
        model = app._sanitize_inline_text(str(event.payload.get("model", "")))
        app._append_line(app.intent_prompt_text, f"[{ts_text}] 客户: {customer_text or '-'}")
        if model:
            app._append_line(app.intent_prompt_text, f"  model: {model}")
        if prompt_text:
            app._append_line(app.intent_prompt_text, "  prompt:")
            for part in prompt_text.split(" || "):
                line = app._sanitize_inline_text(part)
                if line:
                    app._append_line(app.intent_prompt_text, f"    {line}")
        app._append_line(app.intent_prompt_text, "-" * 40)
        return

    if event.kind == "tts_segment":
        text = app._sanitize_inline_text(str(event.payload.get("text", "")))
        if not text:
            return
        if not app._tts_stream_active:
            app._start_tts_stream_line(prefix=f"[{ts_text}] 坐席: ")
        if not app._dialog_agent_stream_active:
            app._start_dialog_agent_stream_line(prefix=f"[{ts_text}] \u5750\u5e2d: ")
        app._append_tts_stream_text(text)
        app._append_dialog_agent_stream_text(text)
        if not isinstance(getattr(app, "_current_agent_stream_text", None), str):
            app._current_agent_stream_text = ""
        app._current_agent_stream_text += text
        return

    if event.kind == "assistant_text":
        text = str(event.payload.get("text", ""))
        normalized = app._sanitize_inline_text(text)
        if app._tts_stream_active and normalized:
            pending_stream_text = app._sanitize_inline_text(str(getattr(app, "_current_agent_stream_text", "") or ""))
            # Keep streamed TTS as source of truth. Do not overwrite live text with
            # parsed "[assistant]" logs, which may be incomplete or out-of-order.
            if (not pending_stream_text) and normalized:
                app._append_tts_stream_text(normalized)
                app._append_dialog_agent_stream_text(normalized)
                pending_stream_text = normalized
            app._close_tts_stream_line()
            app._close_dialog_agent_stream_line()
            final_agent_text = pending_stream_text or normalized
            _append_session_dialog_line(app, role="agent", text=final_agent_text)
            app._current_agent_stream_text = ""
        elif normalized:
            _append_dialog_turn(app, role="agent", ts_text=ts_text, text=normalized)
            app._append_tts_line(role="agent", text=f"[{ts_text}] 坐席: {normalized}")
            app._current_agent_stream_text = ""
        return

    if event.kind == "tts_interrupted":
        trigger = str(event.payload.get("trigger", ""))
        text = str(event.payload.get("text", ""))
        app._close_tts_stream_line()
        app._close_dialog_agent_stream_line()
        pending_agent_text = app._sanitize_inline_text(str(getattr(app, "_current_agent_stream_text", "") or ""))
        if pending_agent_text:
            _append_session_dialog_line(app, role="agent", text=pending_agent_text)
        app._current_agent_stream_text = ""
        app._append_tts_line(
            role="meta",
            text=(
                f"[{ts_text}] interrupted | trigger={app._sanitize_inline_text(trigger)} "
                f"| asr_text={app._sanitize_inline_text(text)}"
            ),
        )
        return

    if event.kind == "tts_end":
        audio_bytes = int(event.payload.get("audio_bytes", 0))
        interrupted = bool(event.payload.get("interrupted", False))
        app._close_tts_stream_line()
        app._close_dialog_agent_stream_line()
        pending_agent_text = app._sanitize_inline_text(str(getattr(app, "_current_agent_stream_text", "") or ""))
        if pending_agent_text:
            _append_session_dialog_line(app, role="agent", text=pending_agent_text)
        app._current_agent_stream_text = ""
        app._append_tts_line(
            role="meta",
            text=f"[{ts_text}] end | audio_bytes={audio_bytes} | interrupted={interrupted}",
        )

    if event.kind == "latency_asr":
        if not isinstance(getattr(app, "_pending_latency", None), dict):
            app._pending_latency = {}
        app._pending_latency.update(event.payload)

    if event.kind == "latency_e2e":
        if not isinstance(getattr(app, "_pending_latency", None), dict):
            app._pending_latency = {}
        app._pending_latency["e2e_ms"] = event.payload.get("ms")

    if event.kind == "latency_backend":
        if not isinstance(getattr(app, "_pending_latency", None), dict):
            app._pending_latency = {}
        app._pending_latency.update(event.payload)
        try:
            _render_latency_block(app, ts_text, app._pending_latency)
        except Exception as _exc:
            try:
                app._append_line(app.log_text, f"[{ts_text}] [latency] render error: {_exc}")
            except Exception:
                pass
        app._pending_latency = None


def handle_settings_asr_event(app, event) -> None:
    ts_text = event.ts.strftime("%H:%M:%S")
    if event.kind == "process_started":
        app._append_line(app.log_text, f"[{ts_text}] [ASR_DIRECT] process started")
        app._begin_asr_wait()
        return

    if event.kind in {"process_stopped", "process_exit"}:
        code = event.payload.get("return_code")
        app._set_microphone_open("settings", False, reason=event.kind)
        app.asr_enabled_var.set(False)
        app.asr_toggle_text_var.set("开启ASR识别")
        app._close_settings_asr_stream_line()
        app._append_line(app.log_text, f"[{ts_text}] [ASR_DIRECT] process exit: return_code={code}")
        if app.asr_enabled_var.get() and (code not in (0, None)) and (not app._asr_first_commit_seen):
            app._log_asr_monitor("settings ASR exited before first commit")
        app._reset_asr_wait()
        return

    if event.kind == "log":
        app._buffer_log_line(f"[{ts_text}] [ASR_DIRECT] {event.raw}")
        app._update_microphone_state_from_log("settings", event.raw)
        lowered = (event.raw or "").lower()
        if "modulenotfounderror" in lowered and "pyaudio" in lowered:
            app._log_asr_monitor("missing dependency: pyaudio; install with pip install PyAudio")
        return

    if event.kind == "asr_partial":
        if not app.asr_enabled_var.get():
            return
        text = str(event.payload.get("text", ""))
        command = str(event.payload.get("command", ""))
        clean_text = app._sanitize_inline_text(text)
        if not clean_text:
            return
        target_widget = app.system_instruction_text
        if target_widget is None:
            return
        if command:
            clean_text = f"{clean_text} (command={command})"
        if app._settings_asr_stream_active and app._settings_asr_stream_widget is not target_widget:
            app._close_settings_asr_stream_line()
        if app._settings_asr_stream_active and app._settings_asr_stream_phase == "commit":
            app._close_settings_asr_stream_line()
        if not app._settings_asr_stream_active:
            app._start_settings_asr_stream_line(
                prefix=app._get_asr_prefix("partial", ts_text),
                phase="partial",
                widget=target_widget,
            )
        else:
            app._settings_asr_stream_phase = "partial"
        app._replace_settings_asr_stream_text(clean_text)
        return

    if event.kind == "asr_commit":
        if not app.asr_enabled_var.get():
            return
        text = str(event.payload.get("text", ""))
        command = str(event.payload.get("command", ""))
        if app._settings_asr_should_submit_customer_profile(text=text, command=command):
            app._mark_asr_commit_seen()
            submit_text = "系统指令---提交"
            target_widget = app.system_instruction_text
            if target_widget is None:
                return
            if app._settings_asr_stream_active and app._settings_asr_stream_widget is not target_widget:
                app._close_settings_asr_stream_line()
            if app._settings_asr_stream_active:
                app._replace_settings_asr_stream_with_commit(ts_text=ts_text, text=submit_text)
            else:
                app._start_settings_asr_stream_line(
                    prefix=app._get_asr_prefix("commit", ts_text),
                    phase="commit",
                    widget=target_widget,
                )
                app._replace_settings_asr_stream_with_commit(ts_text=ts_text, text=submit_text)
            app._close_settings_asr_stream_line()
            app._asr_history_lines.append(f"[{ts_text}] {submit_text}")
            app._asr_history_lines = app._asr_history_lines[-12:]
            app._trigger_customer_profile_submit_from_asr()
            app._refresh_system_instruction()
            return
        clean_text = app._sanitize_inline_text(text)
        if clean_text and command:
            clean_text = f"{clean_text} (command={command})"
        if (not clean_text) and (not app._settings_asr_stream_active):
            return
        app._mark_asr_commit_seen()
        target_widget = app.system_instruction_text
        if target_widget is None:
            return
        if clean_text:
            app._asr_history_lines.append(f"[{ts_text}] {clean_text}")
            app._asr_history_lines = app._asr_history_lines[-12:]
        if app._settings_asr_stream_active and app._settings_asr_stream_widget is not target_widget:
            app._close_settings_asr_stream_line()
        if app._settings_asr_stream_active:
            if clean_text:
                app._replace_settings_asr_stream_with_commit(ts_text=ts_text, text=clean_text)
        elif clean_text:
            app._start_settings_asr_stream_line(
                prefix=app._get_asr_prefix("commit", ts_text),
                phase="commit",
                widget=target_widget,
            )
            app._replace_settings_asr_stream_with_commit(ts_text=ts_text, text=clean_text)
        app._refresh_system_instruction()


def _render_latency_block(app, ts_text: str, data: dict) -> None:
    """将本轮所有耗时指标写入耗时监控面板。"""
    widget = getattr(app, "latency_text", None)
    if widget is None:
        return

    def _fmt(v) -> str:
        if v is None:
            return "  --"
        return f"{int(round(float(v))):>4,} ms"

    def _tag(v, fast: float, slow: float) -> str:
        if v is None:
            return "lat_label"
        f = float(v)
        if f < fast:
            return "lat_fast"
        if f < slow:
            return "lat_medium"
        return "lat_slow"

    rows = [
        ("队列等待NLP", "queue_wait_ms",          20,   100),
        ("NLP首包",     "nlp_first_token_ms",    400,   700),
        ("TTS首包",     "tts_first_audio_ms",    500,   800),
    ]

    try:
        widget.configure(state="normal")
        widget.insert("end", f"[{ts_text}] ─── 本轮耗时 ──────────────────\n", "lat_header")
        asr_val = app._sanitize_inline_text(str(data.get("asr_text") or ""))
        widget.insert("end", f"  {'ASR识别':<12}", "lat_label")
        if asr_val:
            widget.insert("end", f"[{asr_val}]", "lat_label")
        else:
            widget.insert("end", "--", "lat_label")
        widget.insert("end", "\n")
        for label, key, fast, slow in rows:
            v = data.get(key)
            widget.insert("end", f"  {label:<12}", "lat_label")
            widget.insert("end", f"{_fmt(v)}", _tag(v, fast, slow))
            widget.insert("end", "\n")
        widget.insert("end", "\n")
        widget.see("end")
    finally:
        widget.configure(state="disabled")
