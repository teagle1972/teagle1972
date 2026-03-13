from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import messagebox

try:
    from .audio_helpers import (
        format_numeric_for_option as ctrl_format_numeric_for_option,
        get_profile_tuning_defaults as ctrl_get_profile_tuning_defaults,
        normalize_aec_profile as ctrl_normalize_aec_profile,
        read_command_option as ctrl_read_command_option,
        remove_command_option as ctrl_remove_command_option,
    )
except Exception:
    from audio_helpers import (
        format_numeric_for_option as ctrl_format_numeric_for_option,
        get_profile_tuning_defaults as ctrl_get_profile_tuning_defaults,
        normalize_aec_profile as ctrl_normalize_aec_profile,
        read_command_option as ctrl_read_command_option,
        remove_command_option as ctrl_remove_command_option,
    )


def set_audio_config_status(app, text: str) -> None:
    if isinstance(getattr(app, "audio_config_status_var", None), tk.StringVar):
        app.audio_config_status_var.set(str(text or "").strip() or "-")


def load_audio_config_from_command_text(app, command_text: str, update_status: bool = True) -> None:
    tokens = app._safe_split(command_text)
    if not tokens:
        return
    for spec in app._audio_tuning_specs:
        key = str(spec["key"])
        flag = str(spec["flag"])
        current = ctrl_read_command_option(tokens, flag)
        if not current:
            continue
        var = getattr(app, f"audio_{key}_var", None)
        if isinstance(var, tk.StringVar):
            var.set(current)
    if update_status:
        set_audio_config_status(app, "已从当前启动命令回填参数")


def load_audio_config_from_current_command(app, update_status: bool = True) -> None:
    command_text = (app.command_var.get() or "").strip()
    if not command_text:
        command_text = (app.conversation_command_var.get() or "").strip()
    load_audio_config_from_command_text(app, command_text, update_status=update_status)


def reset_audio_config_defaults_for_profile(
    app,
    apply_profile_overrides: bool = True,
    update_status: bool = True,
) -> None:
    profile = ctrl_normalize_aec_profile(app.aec_profile_var.get())
    app.aec_profile_var.set(profile)
    defaults = ctrl_get_profile_tuning_defaults(
        profile if apply_profile_overrides else "asr_first",
        specs=app._audio_tuning_specs,
        asr_first_overrides=app._asr_first_profile_overrides,
        aggressive_overrides=app._aggressive_profile_overrides,
    )
    for key, value in defaults.items():
        var = getattr(app, f"audio_{key}_var", None)
        if isinstance(var, tk.StringVar):
            var.set(str(value))
    if update_status:
        profile_label = "ASR优先" if profile == "asr_first" else "增强抑制"
        set_audio_config_status(app, f"已恢复默认值（{profile_label}）")


def reset_audio_config_defaults(app) -> None:
    reset_audio_config_defaults_for_profile(app, apply_profile_overrides=True, update_status=True)


def collect_validated_audio_tuning_values(app, *, show_error: bool) -> dict[str, str] | None:
    values: dict[str, str] = {}
    for spec in app._audio_tuning_specs:
        key = str(spec["key"])
        label = str(spec["label"])
        value_type = str(spec["type"])
        min_value = float(spec["min"])
        max_value = float(spec["max"])
        unit = str(spec["unit"])
        var = getattr(app, f"audio_{key}_var", None)
        raw = str(var.get() if isinstance(var, tk.StringVar) else "").strip()
        if not raw:
            raw = str(spec["default"])
        try:
            if value_type == "int":
                parsed = float(int(raw))
            else:
                parsed = float(raw)
        except Exception:
            if show_error:
                messagebox.showerror(
                    "参数格式错误",
                    f"{label} 必须是数字，单位 {unit}，范围 {ctrl_format_numeric_for_option(min_value, value_type)} ~ {ctrl_format_numeric_for_option(max_value, value_type)}。",
                )
            return None
        if (parsed < min_value) or (parsed > max_value):
            if show_error:
                messagebox.showerror(
                    "参数超出范围",
                    f"{label} 超出范围，单位 {unit}，允许 {ctrl_format_numeric_for_option(min_value, value_type)} ~ {ctrl_format_numeric_for_option(max_value, value_type)}。",
                )
            return None
        normalized = ctrl_format_numeric_for_option(parsed, value_type)
        if isinstance(var, tk.StringVar):
            var.set(normalized)
        values[key] = normalized
    return values


def apply_audio_tuning_values_to_command(app, command_text: str, values: dict[str, str]) -> str:
    command = str(command_text or "").strip()
    if not command:
        return command
    tokens = app._safe_split(command)
    if not tokens:
        return command
    for spec in app._audio_tuning_specs:
        key = str(spec["key"])
        flag = str(spec["flag"])
        value = values.get(key, "")
        if not value:
            continue
        ctrl_remove_command_option(tokens, flag)
        tokens.extend([flag, value])
    return app._safe_join(tokens)


def build_runtime_audio_config_payload(app, values: dict[str, str]) -> dict[str, object]:
    return {
        "strict_webrtc_required": bool(app.strict_webrtc_required_var.get()),
        "aec_profile": ctrl_normalize_aec_profile(app.aec_profile_var.get()),
        "audio_tuning": values,
    }


def save_runtime_audio_config(app, values: dict[str, str] | None = None, *, silent: bool = False) -> bool:
    payload_values = (
        values if isinstance(values, dict) else collect_validated_audio_tuning_values(app, show_error=not silent)
    )
    if not isinstance(payload_values, dict):
        return False
    payload = build_runtime_audio_config_payload(app, payload_values)
    try:
        app._runtime_audio_config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        if not silent:
            messagebox.showerror("保存失败", f"参数配置保存失败：{exc}")
        return False
    return True


def load_runtime_audio_config(app) -> bool:
    path = app._runtime_audio_config_path
    if not path.exists():
        set_audio_config_status(app, "未发现已保存配置，已加载默认值")
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        set_audio_config_status(app, f"配置文件读取失败，已使用默认值: {exc}")
        return False
    if not isinstance(raw, dict):
        set_audio_config_status(app, "配置文件格式异常，已使用默认值")
        return False
    app.strict_webrtc_required_var.set(bool(raw.get("strict_webrtc_required", True)))
    profile = ctrl_normalize_aec_profile(str(raw.get("aec_profile", app.aec_profile_var.get()) or "asr_first"))
    app.aec_profile_var.set(profile)
    tuning_raw = raw.get("audio_tuning", {})
    defaults = ctrl_get_profile_tuning_defaults(
        profile,
        specs=app._audio_tuning_specs,
        asr_first_overrides=app._asr_first_profile_overrides,
        aggressive_overrides=app._aggressive_profile_overrides,
    )
    if isinstance(tuning_raw, dict):
        for key, value in tuning_raw.items():
            key_text = str(key)
            if key_text in defaults:
                defaults[key_text] = str(value)
    for key, value in defaults.items():
        var = getattr(app, f"audio_{key}_var", None)
        if isinstance(var, tk.StringVar):
            var.set(str(value))
    os.environ["MIC_CHUNK_AEC_PROFILE"] = profile
    set_audio_config_status(app, f"已加载参数配置: {path.name}")
    return True


def apply_audio_config_to_commands(
    app,
    *,
    save_config: bool = True,
    update_status: bool = True,
    show_error: bool = True,
) -> bool:
    values = collect_validated_audio_tuning_values(app, show_error=show_error)
    if values is None:
        return False
    profile = ctrl_normalize_aec_profile(app.aec_profile_var.get())
    app.aec_profile_var.set(profile)
    os.environ["MIC_CHUNK_AEC_PROFILE"] = profile
    startup_command = str(app._default_command or app._fixed_startup_command).strip() or app._fixed_startup_command
    startup_command = apply_audio_tuning_values_to_command(app, startup_command, values)
    app.command_var.set(startup_command)
    app.conversation_command_var.set(startup_command)
    app._apply_server_env_to_command()
    app._apply_server_env_to_conversation_command()
    settings_asr_command = str(app.command_var.get() or startup_command).strip()
    app.settings_asr_command_var.set(settings_asr_command)
    app._settings_asr_command = settings_asr_command
    if save_config:
        if not save_runtime_audio_config(app, values, silent=False):
            return False
    if update_status:
        set_audio_config_status(app, "参数已应用并保存")
    return True


def save_audio_config_from_ui(app) -> None:
    values = collect_validated_audio_tuning_values(app, show_error=True)
    if values is None:
        return
    profile = ctrl_normalize_aec_profile(app.aec_profile_var.get())
    app.aec_profile_var.set(profile)
    os.environ["MIC_CHUNK_AEC_PROFILE"] = profile
    app._settings_asr_command = str(app.settings_asr_command_var.get() or app._settings_asr_command or "").strip()
    ok = save_runtime_audio_config(app, values, silent=False)
    if ok:
        set_audio_config_status(app, "参数配置已保存")
