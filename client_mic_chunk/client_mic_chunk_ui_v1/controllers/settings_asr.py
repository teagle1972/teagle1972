from __future__ import annotations

import time
from datetime import datetime

from tkinter.scrolledtext import ScrolledText


def start_settings_asr(app) -> None:
    if app._settings_asr_bridge.running:
        app._log_asr_monitor("settings ASR already running")
        return
    cmd_var = getattr(app, "settings_asr_command_var", None)
    if cmd_var is not None:
        try:
            latest_command = str(cmd_var.get() or "").strip()
        except Exception:
            latest_command = ""
        if latest_command:
            app._settings_asr_command = latest_command
    command = app._ensure_unbuffered_python_command(app._settings_asr_command)
    command = app._ensure_mic_capture_command(command)
    strict_ok, strict_message = app._check_strict_webrtc_readiness(command)
    if not strict_ok:
        ts_text = datetime.now().strftime("%H:%M:%S")
        app._append_line(
            app.log_text,
            (
                f"[{ts_text}] [STRICT_WEBRTC] preflight_failed scope=settings_asr "
                f"reason={app._sanitize_inline_text(strict_message)}"
            ),
        )
        app._log_asr_monitor(f"strict_webrtc_preflight_failed scope=settings_asr reason={strict_message}")
        app.asr_enabled_var.set(False)
        app.asr_toggle_text_var.set("寮€鍚疉SR璇嗗埆")
        return
    app._append_line(
        app.log_text,
        f"[{datetime.now().strftime('%H:%M:%S')}] [ASR_DIRECT] start requested command={command}",
    )
    try:
        app._settings_asr_bridge.start(command=command, cwd=str(app._workspace_dir))
    except Exception as exc:
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [ASR_DIRECT] start failed: {exc}",
        )
        app._log_asr_monitor(f"settings ASR start failed: {exc}")
        app.asr_enabled_var.set(False)
        app.asr_toggle_text_var.set("开启ASR识别")


def begin_asr_wait(app) -> None:
    app._asr_wait_since = time.monotonic()
    app._asr_first_commit_seen = False
    app._asr_wait_warned = False
    app._log_asr_monitor("start_waiting_first_commit")


def mark_asr_commit_seen(app) -> None:
    if app._asr_first_commit_seen:
        return
    app._asr_first_commit_seen = True
    elapsed_ms = 0
    if app._asr_wait_since > 0:
        elapsed_ms = int((time.monotonic() - app._asr_wait_since) * 1000)
    app._log_asr_monitor(f"first_commit_received elapsed_ms={elapsed_ms}")


def check_asr_wait_timeout(app) -> None:
    if not app.asr_enabled_var.get():
        return
    if not app._settings_asr_bridge.running:
        return
    if app._asr_wait_since <= 0 or app._asr_first_commit_seen or app._asr_wait_warned:
        return
    elapsed = time.monotonic() - app._asr_wait_since
    if elapsed >= 8.0:
        app._asr_wait_warned = True
        app._log_asr_monitor(f"waiting_first_commit_timeout elapsed_ms={int(elapsed * 1000)}")


def reset_asr_wait(app) -> None:
    app._asr_wait_since = 0.0
    app._asr_first_commit_seen = False
    app._asr_wait_warned = False


def log_asr_monitor(app, message: str) -> None:
    line = f"[ASR_MONITOR] {message}"
    print(line, flush=True)
    if hasattr(app, "log_text"):
        app._append_line(app.log_text, f"[{datetime.now().strftime('%H:%M:%S')}] {line}")


def is_microphone_open(app) -> bool:
    return (
        app._main_mic_open
        or app._settings_mic_open
        or app._bridge.running
        or app._settings_asr_bridge.running
    )


def set_microphone_open(app, source: str, opened: bool, reason: str = "") -> None:
    if source == "main":
        current = app._main_mic_open
        if current == opened:
            return
        app._main_mic_open = opened
    else:
        current = app._settings_mic_open
        if current == opened:
            return
        app._settings_mic_open = opened
    state = "open" if opened else "closed"
    extra = f" reason={reason}" if reason else ""
    app._log_asr_monitor(f"mic_state source={source} state={state}{extra}")


def update_microphone_state_from_log(app, source: str, raw_line: str) -> None:
    line = (raw_line or "").lower()
    if (
        "[mic/monitor] opened input stream" in line
        or "[mic/monitor] first_chunk" in line
        or "[mic/monitor] captured_chunks=" in line
    ):
        app._set_microphone_open(source, True, reason="log_detected")


def get_asr_prefix(app, phase: str, ts_text: str) -> str:
    if app.asr_prefix_enabled_var.get():
        return f"[{phase} {ts_text}] "
    return f"[ASR {ts_text}] "


def start_settings_asr_stream_line(
    app,
    prefix: str,
    phase: str = "partial",
    widget: ScrolledText | None = None,
) -> None:
    widget = widget or app.system_instruction_text
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    existing_text = widget.get("1.0", "end-1c")
    if existing_text and not existing_text.endswith("\n"):
        widget.insert("end", "\n")
    app._settings_asr_stream_line_start = widget.index("end-1c")
    widget.insert("end", prefix)
    app._settings_asr_stream_content_start = widget.index("end-1c")
    app._settings_asr_stream_active = True
    app._settings_asr_stream_phase = phase
    app._settings_asr_stream_widget = widget
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")


def replace_settings_asr_stream_text(app, text: str) -> None:
    if not app._settings_asr_stream_active:
        return
    widget = app._settings_asr_stream_widget or app.system_instruction_text
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    end_index = widget.index("end-1c")
    widget.delete(app._settings_asr_stream_content_start, end_index)
    widget.insert("end", text)
    widget.tag_remove("asr_partial", app._settings_asr_stream_line_start, widget.index("end-1c"))
    if app._settings_asr_stream_phase == "partial":
        widget.tag_add("asr_partial", app._settings_asr_stream_line_start, widget.index("end-1c"))
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")


def replace_settings_asr_stream_with_commit(app, ts_text: str, text: str) -> None:
    if not app._settings_asr_stream_active:
        return
    widget = app._settings_asr_stream_widget or app.system_instruction_text
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    end_index = widget.index("end-1c")
    line_start = app._settings_asr_stream_line_start or f"{app._settings_asr_stream_content_start} linestart"
    widget.delete(line_start, end_index)
    widget.insert(line_start, f"{app._get_asr_prefix('commit', ts_text)}{text}")
    widget.tag_remove("asr_partial", line_start, widget.index("end-1c"))
    app._settings_asr_stream_phase = "commit"
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")


def close_settings_asr_stream_line(app) -> None:
    if not app._settings_asr_stream_active:
        return
    widget = app._settings_asr_stream_widget or app.system_instruction_text
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    widget.insert("end", "\n")
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")
    app._settings_asr_stream_active = False
    app._settings_asr_stream_phase = ""
    app._settings_asr_stream_line_start = ""
    app._settings_asr_stream_content_start = ""
    app._settings_asr_stream_widget = None
