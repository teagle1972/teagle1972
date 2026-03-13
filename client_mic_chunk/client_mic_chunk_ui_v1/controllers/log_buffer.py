from __future__ import annotations

import time
from pathlib import Path


def _log_ui_blocking(app, label: str, started_at: float, *, threshold_ms: float = 100.0, extra: str = "") -> None:
    if not bool(getattr(app, "_debug_ui_block_logging", False)):
        return
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if elapsed_ms < threshold_ms:
        return
    suffix = f" {extra}" if extra else ""
    line = f"[UI_BLOCK] {label} {elapsed_ms:.1f}ms{suffix}"
    try:
        app.log_text.configure(state="normal")
        app.log_text.insert("end", line + "\n")
        app.log_text.configure(state="disabled")
        app.log_text.see("end")
    except Exception:
        pass
    workspace_dir = getattr(app, "_workspace_dir", None)
    if isinstance(workspace_dir, Path):
        try:
            log_dir = workspace_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            queue_async_log_write = getattr(app, "_queue_async_log_write", None)
            if callable(queue_async_log_write):
                queue_async_log_write(log_dir / "ui_blocking.log", line)
        except Exception:
            pass


def reset_send_done_summary(app) -> None:
    app._send_done_summary_second = ""
    app._send_done_summary_count = 0
    app._send_done_summary_first_chunk = 0
    app._send_done_summary_last_chunk = 0
    app._send_done_summary_total_ms = 0
    app._send_done_summary_max_ms = 0
    app._send_done_summary_deadline = 0.0


def flush_send_done_summary(app, *, force: bool = False) -> None:
    if app._send_done_summary_count <= 0:
        return
    if (not force) and time.monotonic() < app._send_done_summary_deadline:
        return

    avg_ms = app._send_done_summary_total_ms / max(app._send_done_summary_count, 1)
    if app._send_done_summary_count == 1:
        line = (
            f"[{app._send_done_summary_second}] "
            f"[send] chunk={app._send_done_summary_last_chunk} done in {int(avg_ms)}ms"
        )
    else:
        line = (
            f"[{app._send_done_summary_second}] [send] "
            f"chunks={app._send_done_summary_first_chunk}-{app._send_done_summary_last_chunk} "
            f"count={app._send_done_summary_count} avg={avg_ms:.1f}ms max={app._send_done_summary_max_ms}ms"
        )
    app._pending_log_lines.append(line)
    reset_send_done_summary(app)


def consume_send_done_log(
    app,
    *,
    ts_text: str,
    raw_line: str,
    send_done_log_re,
    send_done_summary_interval_seconds: float,
) -> bool:
    m = send_done_log_re.match((raw_line or "").strip())
    if m is None:
        flush_send_done_summary(app, force=True)
        return False

    chunk = int(m.group("chunk"))
    cost_ms = int(m.group("ms"))
    if app._send_done_summary_count > 0 and ts_text != app._send_done_summary_second:
        flush_send_done_summary(app, force=True)

    if app._send_done_summary_count <= 0:
        app._send_done_summary_second = ts_text
        app._send_done_summary_first_chunk = chunk
        app._send_done_summary_last_chunk = chunk
        app._send_done_summary_total_ms = cost_ms
        app._send_done_summary_max_ms = cost_ms
        app._send_done_summary_count = 1
        app._send_done_summary_deadline = time.monotonic() + send_done_summary_interval_seconds
        return True

    app._send_done_summary_last_chunk = chunk
    app._send_done_summary_total_ms += cost_ms
    if cost_ms > app._send_done_summary_max_ms:
        app._send_done_summary_max_ms = cost_ms
    app._send_done_summary_count += 1
    return True


def buffer_log_line(app, *, line: str, log_flush_interval_seconds: float) -> None:
    if not line:
        return
    app._pending_log_lines.append(line)
    if len(app._pending_log_lines) >= 120:
        flush_log_buffer(app, force=True, log_flush_interval_seconds=log_flush_interval_seconds)


def flush_log_buffer(app, *, force: bool = False, log_flush_interval_seconds: float) -> None:
    started_at = time.perf_counter()
    if not app._pending_log_lines:
        return
    now = time.monotonic()
    if (not force) and (now < app._next_log_flush_at):
        return

    lines = app._pending_log_lines
    app._pending_log_lines = []
    write_time_log_lines = getattr(app, "_write_time_log_lines", None)
    if callable(write_time_log_lines):
        try:
            write_time_log_lines(lines)
        except Exception:
            pass
    app._write_runtime_log_lines(lines)
    app._next_log_flush_at = now + log_flush_interval_seconds
    _log_ui_blocking(app, "flush_log_buffer", started_at, extra=f"lines={len(lines)}")
