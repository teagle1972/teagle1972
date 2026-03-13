from __future__ import annotations


def toggle_asr(app) -> None:
    enabled = not bool(app.asr_enabled_var.get())
    app.asr_enabled_var.set(enabled)
    app.asr_toggle_text_var.set("关闭ASR识别" if enabled else "开启ASR识别")
    if enabled:
        app._log_asr_monitor("switch_on")
        app._start_settings_asr()
    else:
        app._log_asr_monitor("switch_off")
        app._reset_asr_wait()
        app._stop_settings_asr()
        app._set_microphone_open("settings", False, reason="asr_switch_off")
        if app._bridge.running and app._main_mic_open:
            app._log_asr_monitor("switch_off stopping main process to close microphone")
            app._stop()
    app._refresh_system_instruction()
