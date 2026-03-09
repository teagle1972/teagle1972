from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable


def safe_split_command(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=False)
    except Exception:
        return command.split()


def safe_join_tokens(tokens: list[str]) -> str:
    if not tokens:
        return ""
    try:
        return subprocess.list2cmdline(tokens)
    except Exception:
        return " ".join(tokens)


def _remove_option(tokens: list[str], flag: str) -> bool:
    changed = False
    i = 0
    while i < len(tokens):
        if tokens[i] != flag:
            i += 1
            continue
        del tokens[i]
        changed = True
        if i < len(tokens):
            nxt = tokens[i]
            if nxt and (not nxt.startswith("--")):
                del tokens[i]
        continue
    return changed


def _upsert_option(tokens: list[str], flag: str, value: str, *, force: bool = False) -> bool:
    changed = False
    idx = -1
    try:
        idx = tokens.index(flag)
    except ValueError:
        idx = -1
    if idx < 0:
        tokens.extend([flag, value])
        return True
    if idx + 1 >= len(tokens):
        tokens.append(value)
        return True
    current = str(tokens[idx + 1]).strip()
    if current.startswith("--"):
        tokens.insert(idx + 1, value)
        return True
    if force or (not current):
        if current != value:
            tokens[idx + 1] = value
            return True
    return changed


def _get_option_value(tokens: list[str], flag: str) -> str:
    try:
        idx = tokens.index(flag)
    except ValueError:
        return ""
    if idx + 1 >= len(tokens):
        return ""
    value = str(tokens[idx + 1]).strip()
    if value.startswith("--"):
        return ""
    return value


def ensure_mic_capture_command(command: str, log_monitor: Callable[[str], None] | None = None) -> str:
    tokens = safe_split_command(command)
    if not tokens:
        return command
    original = list(tokens)
    tokens = [token for token in tokens if token != "--local"]
    if (tokens != original) and callable(log_monitor):
        log_monitor("removed --local to enable microphone capture")

    # Profiles:
    # - asr_first (default): keep only core AEC settings to protect ASR accuracy.
    # - aggressive: keep legacy stronger suppression behavior.
    profile = str(os.getenv("MIC_CHUNK_AEC_PROFILE", "asr_first") or "asr_first").strip().lower()
    if profile not in {"asr_first", "aggressive"}:
        profile = "asr_first"

    removed_no_aec = _remove_option(tokens, "--no-aec")
    if removed_no_aec and callable(log_monitor):
        log_monitor("removed conflicting --no-aec")
    if "--aec" not in tokens:
        tokens.append("--aec")
        if callable(log_monitor):
            log_monitor("added --aec")
    engine_value = _get_option_value(tokens, "--aec-engine")
    if engine_value and engine_value.lower() != "webrtc" and callable(log_monitor):
        log_monitor(f"removed conflicting --aec-engine {engine_value}")
    if _upsert_option(tokens, "--aec-engine", "webrtc", force=True) and callable(log_monitor):
        log_monitor("set --aec-engine webrtc")
    if "--aec-webrtc-required" not in tokens:
        tokens.append("--aec-webrtc-required")
        if callable(log_monitor):
            log_monitor("added --aec-webrtc-required")

    # Core recommendation: keep dynamic delay tracking for robust AEC.
    if "--no-aec-auto-delay" in tokens:
        _remove_option(tokens, "--no-aec-auto-delay")
        if callable(log_monitor):
            log_monitor("removed --no-aec-auto-delay")
    if "--aec-auto-delay" not in tokens:
        tokens.append("--aec-auto-delay")
        if callable(log_monitor):
            log_monitor("added --aec-auto-delay")

    # Preserve user-configured chunk size. Only clamp invalid value.
    chunk_value = _get_option_value(tokens, "--chunk-ms")
    if chunk_value:
        try:
            if int(chunk_value) <= 0:
                if _upsert_option(tokens, "--chunk-ms", "20", force=True) and callable(log_monitor):
                    log_monitor("fixed invalid --chunk-ms to 20")
        except ValueError:
            if _upsert_option(tokens, "--chunk-ms", "20", force=True) and callable(log_monitor):
                log_monitor("fixed invalid --chunk-ms to 20")

    # Keep queue safety floor only.
    queue_size_value = _get_option_value(tokens, "--queue-size")
    try:
        queue_size_num = int(queue_size_value)
    except Exception:
        queue_size_num = 0
    if queue_size_num < 64:
        if _upsert_option(tokens, "--queue-size", "128", force=True) and callable(log_monitor):
            log_monitor("set --queue-size 128 to reduce mic chunk drops")

    # In ASR-first mode, remove aggressive gates/NS/post-filters unless user explicitly opts aggressive.
    if profile == "asr_first":
        aggressive_flags = (
            "--aec-echo-gate",
            "--aec-webrtc-ns",
            "--aec-webrtc-post-filter",
            "--aec-use-output-latency",
            "--aec-tts-half-duplex",
            "--aec-tts-barge-in-interrupt",
        )
        for flag in aggressive_flags:
            if flag in tokens:
                _remove_option(tokens, flag)
                if callable(log_monitor):
                    log_monitor(f"removed {flag} for ASR-first profile")

        # Explicitly keep these disabled to avoid accidental re-enable from inherited command templates.
        keep_disabled_flags = (
            "--no-aec-echo-gate",
            "--no-aec-webrtc-ns",
            "--no-aec-webrtc-post-filter",
            "--no-aec-tts-half-duplex",
        )
        for flag in keep_disabled_flags:
            if flag not in tokens:
                tokens.append(flag)
                if callable(log_monitor):
                    log_monitor(f"added {flag}")

        # ASR-friendly defaults only when user did not set them.
        asr_first_defaults = (
            ("--queue-size", "128"),
            ("--aec-ref-delay-ms", "160"),
            ("--aec-max-suppress-gain", "1.6"),
            ("--aec-near-end-protect-ratio", "1.16"),
            ("--aec-tts-warmup-mute-ms", "20"),
            ("--aec-tts-ref-wait-mute-ms", "600"),
        )
        for flag, value in asr_first_defaults:
            if _upsert_option(tokens, flag, value, force=False) and callable(log_monitor):
                log_monitor(f"added {flag} {value}")
    else:
        # Legacy aggressive defaults.
        if "--no-aec-webrtc-ns" in tokens:
            _remove_option(tokens, "--no-aec-webrtc-ns")
        if "--aec-webrtc-ns" not in tokens:
            tokens.append("--aec-webrtc-ns")
        if "--aec-webrtc-post-filter" in tokens:
            _remove_option(tokens, "--aec-webrtc-post-filter")
        if "--no-aec-webrtc-post-filter" not in tokens:
            tokens.append("--no-aec-webrtc-post-filter")
        if "--aec-echo-gate" not in tokens:
            tokens.append("--aec-echo-gate")
        aggressive_defaults = (
            ("--aec-ref-delay-ms", "120"),
            ("--aec-max-suppress-gain", "2.4"),
            ("--aec-near-end-protect-ratio", "1.18"),
            ("--aec-tts-warmup-mute-ms", "120"),
            ("--aec-tts-ref-wait-mute-ms", "2200"),
        )
        for flag, value in aggressive_defaults:
            _upsert_option(tokens, flag, value, force=False)

    return safe_join_tokens(tokens)


def ensure_unbuffered_python_command(command: str, log_monitor: Callable[[str], None] | None = None) -> str:
    tokens = safe_split_command(command)
    if not tokens:
        return command
    exe = Path(tokens[0]).name.lower()
    is_python = exe.startswith("python") or exe == "py"
    if (not is_python) or ("-u" in tokens[1:]):
        return command
    rebuilt = [tokens[0], "-u", *tokens[1:]]
    if callable(log_monitor):
        log_monitor("enabled python -u for realtime log output")
    return safe_join_tokens(rebuilt)


def _resolve_python_executable(tokens: list[str]) -> str:
    if not tokens:
        return ""
    first = str(tokens[0] or "").strip()
    if not first:
        return ""
    first_name = Path(first.strip('"')).name.lower()
    if first_name.startswith("python") or first_name == "py":
        current = str(sys.executable or "").strip()
        return current or first
    if first_name in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        for token in tokens[1:]:
            candidate = str(token or "").strip()
            if not candidate:
                continue
            name = Path(candidate.strip('"')).name.lower()
            if name.startswith("python") or name == "py":
                current = str(sys.executable or "").strip()
                return current or candidate
    return ""


def check_strict_webrtc_readiness(command: str, cwd: Path) -> tuple[bool, str]:
    tokens = safe_split_command(command)
    python_exe = _resolve_python_executable(tokens)
    if not python_exe:
        return False, "Unable to resolve Python interpreter from command; please launch via python/py directly."

    probe_script = (
        "import importlib, json, sys\n"
        "mods=['aec_audio_processing','webrtc_apm','webrtc_audio_processing']\n"
        "usable=[]\n"
        "errors={}\n"
        "for m in mods:\n"
        "    try:\n"
        "        importlib.import_module(m)\n"
        "        usable.append(m)\n"
        "    except Exception as e:\n"
        "        errors[m]=f'{type(e).__name__}: {e}'\n"
        "print(json.dumps({'python': sys.version.split()[0], 'version_ok': tuple(sys.version_info[:2]) >= (3, 11), 'usable': usable, 'errors': errors}, ensure_ascii=False))\n"
    )
    try:
        proc = subprocess.run(
            [python_exe, "-c", probe_script],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
    except FileNotFoundError:
        return False, f"Python interpreter not found: {python_exe}"
    except subprocess.TimeoutExpired:
        return False, "Strict WebRTC preflight timed out (5s); please check Python environment health."
    except Exception as exc:
        return False, f"Strict WebRTC preflight execution failed: {exc}"

    output = (proc.stdout or "").strip()
    if proc.returncode != 0:
        err = (proc.stderr or "").strip() or output or "<empty>"
        return False, f"Preflight subprocess failed (exit={proc.returncode}): {err}"
    if not output:
        return False, "Preflight returned no output; please verify Python runtime state."

    try:
        payload = json.loads(output)
    except Exception:
        return False, f"Preflight output is not valid JSON: {output}"

    python_version = str(payload.get("python", "") or "")
    version_ok = bool(payload.get("version_ok", False))
    usable = payload.get("usable", [])
    errors = payload.get("errors", {})
    if not isinstance(usable, list):
        usable = []
    if not isinstance(errors, dict):
        errors = {}

    if (not version_ok) or (not usable):
        missing = [name for name in ("aec_audio_processing", "webrtc_apm", "webrtc_audio_processing") if name not in usable]
        err_parts: list[str] = []
        for name in missing:
            detail = str(errors.get(name, "") or "").strip()
            if detail:
                err_parts.append(f"{name}: {detail}")
            else:
                err_parts.append(f"{name}: not found")
        reason = "; ".join(err_parts) if err_parts else "No usable WebRTC APM backend found."
        return (
            False,
            "Strict WebRTC preflight failed. "
            f"Python={python_version or '<unknown>'}, version_ok={version_ok}, "
            f"backend_errors={reason}. "
            "Please use Python 3.11+ and install webrtc-apm or aec-audio-processing.",
        )

    backend = str(usable[0])
    return True, f"Strict WebRTC preflight passed. Python={python_version}, backend={backend}"

