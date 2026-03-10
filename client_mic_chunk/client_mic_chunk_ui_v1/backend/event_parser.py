from __future__ import annotations

import ast
import json
import re
from typing import Optional

from .models import UiEvent


RE_WS_READY = re.compile(r"^\[ws/ready\]\s+session_id=(?P<session_id>.+)$")
RE_WS_CONNECTED_SPLIT = re.compile(r"^\[ws\]\s+connected\((?P<channel>control|media)\):\s*(?P<endpoint>.+)$")
RE_WS_CONNECTED_SINGLE = re.compile(r"^\[ws\]\s+connected:\s*(?P<endpoint>.+)$")
RE_WS_TERMINATE = re.compile(r"^\[ws/terminate\]\s+(?P<body>\{.*\})$")
RE_WS_DISCONNECT = re.compile(r"^\[ws/disconnect\]\s+(?P<body>\{.*\})$")
RE_BILLING_START = re.compile(r"^\[billing/start\]\s+(?P<body>\{.*\})$")
RE_BILLING_RESULT = re.compile(r"^\[billing/result\]\s+(?P<body>\{.*\})$")
RE_SEND_DONE = re.compile(r"^\[send\]\s+chunk=(?P<chunk>\d+)\s+done\s+in\s+(?P<ms>\d+)ms$")
RE_SEND_FAILED = re.compile(r"^\[send\]\s+chunk=(?P<chunk>\d+)\s+failed:\s+(?P<reason>.+)$")
RE_ASR_PARTIAL = re.compile(r"^\[asr/partial\]\s+(?P<text>.+)$")
RE_ASR = re.compile(r"^\[asr\]\s+(?P<text>.+)$")
RE_TTS_START = re.compile(r"^\[tts\]\s+start\s+text=(?P<text>.*)$")
RE_NLP_PROMPT = re.compile(r"^\[nlp/prompt\]\s+mode=(?P<mode>.*?)\s+text=(?P<text>.*)$")
RE_TTS_SEGMENT = re.compile(r"^\[tts/segment\]\s+seq=(?P<seq>\d+)\s+text=(?P<text>.*)$")
RE_TTS_INTERRUPTED = re.compile(r"^\[tts\]\s+interrupted\s+trigger=(?P<trigger>.*?)\s+text=(?P<text>.*)$")
RE_TTS_END = re.compile(r"^\[tts\]\s+end\s+audio_bytes=(?P<audio_bytes>\d+)\s+interrupted=(?P<interrupted>.+)$")
RE_WS_TTS_FIRST_FRAME = re.compile(r"^\[ws/tts\]\s+first_frame_bytes=(?P<bytes>\d+)$")
RE_ASSISTANT_TEXT = re.compile(r"^\[assistant\]\s+(?P<text>.*)$")
RE_INTENT_RESULT = re.compile(r"^\[intent\]\s+(?P<body>\{.*\})$")
RE_INTENT_PROMPT = re.compile(r"^\[intent/prompt\]\s+(?P<body>\{.*\})$")
RE_WORKFLOW_PROGRESS = re.compile(r"^\[workflow\]\s+(?P<body>\{.*\})$")
RE_LATENCY_E2E = re.compile(r"^\[latency\]\s+e2e_ms=(?P<ms>\d+)")
RE_LATENCY_ASR = re.compile(r"^\[latency/asr\](?:\s+(?P<params>[^|]*))?\|\s*(?P<text>.*)$")
RE_LATENCY_BACKEND = re.compile(r"^\[latency/backend\]\s+(?P<params>.+)$")
RE_LOG_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}\s+[0-9:,\.\-]+\s+-\s+[A-Z]+\s+-\s+")
RE_TS_BRACKET_PREFIX = re.compile(r"^\[[0-9:\-\/\s\.,]{6,}\]\s+")
RE_LOG_LATENCY_TURN = re.compile(r"^ws turn latency .*?(?P<body>\{.*\})\s*$")
RE_LOG_LATENCY_ASR = re.compile(
    r"^asr_commit latency .*?\basr_recognition_ms=(?P<asr_recognition_ms>[-+]?\d+(?:\.\d+)?)\s+"
    r"asr_silence_wait_ms=(?P<asr_silence_wait_ms>[-+]?\d+(?:\.\d+)?)\s+text=(?P<text>.*)$"
)
RE_INLINE_SEND_NOISE = re.compile(r"\[send\]\s+chunk=\d+\s+done\s+in\s+\d+ms")


def _clean_inline_noise(text: str) -> str:
    cleaned = RE_INLINE_SEND_NOISE.sub("", text or "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _strip_common_prefixes(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    prev = None
    while cleaned and cleaned != prev:
        prev = cleaned
        cleaned = RE_LOG_PREFIX.sub("", cleaned, count=1)
        cleaned = RE_TS_BRACKET_PREFIX.sub("", cleaned, count=1)
    return cleaned.strip()


def _focus_known_event_segment(text: str) -> str:
    lowered = (text or "").lower()
    anchors = [
        "[latency/asr]",
        "[latency/backend]",
        "[latency]",
        "ws turn latency",
        "asr_commit latency",
    ]
    for anchor in anchors:
        idx = lowered.find(anchor)
        if idx >= 0:
            return text[idx:].strip()
    return text.strip()


def parse_line(line: str) -> Optional[UiEvent]:
    text = _focus_known_event_segment(_strip_common_prefixes((line or "").strip()))
    if not text:
        return None

    m = RE_WS_READY.match(text)
    if m:
        return UiEvent(kind="session_ready", payload={"session_id": m.group("session_id")}, raw=text)

    m = RE_WS_CONNECTED_SPLIT.match(text)
    if m:
        return UiEvent(
            kind="ws_connected_split",
            payload={"channel": m.group("channel"), "endpoint": m.group("endpoint")},
            raw=text,
        )

    m = RE_WS_CONNECTED_SINGLE.match(text)
    if m:
        return UiEvent(kind="ws_connected_single", payload={"endpoint": m.group("endpoint")}, raw=text)

    m = RE_WS_TERMINATE.match(text)
    if m:
        try:
            payload = json.loads(m.group("body"))
        except Exception:
            payload = {}
        return UiEvent(
            kind="ws_command",
            payload={
                "command": str(payload.get("command", "") or ""),
                "action": str(payload.get("action", "") or ""),
                "terminate_source": str(payload.get("terminate_source", "") or ""),
                "terminate_reason": str(payload.get("terminate_reason", "") or ""),
                "terminate_trace_id": str(payload.get("terminate_trace_id", "") or ""),
                "terminate_by": str(payload.get("terminate_by", "") or ""),
                "trigger_text": str(payload.get("trigger_text", "") or ""),
                "server_ts": payload.get("server_ts"),
            },
            raw=text,
        )

    m = RE_WS_DISCONNECT.match(text)
    if m:
        try:
            payload = json.loads(m.group("body"))
        except Exception:
            payload = {}
        return UiEvent(
            kind="ws_disconnect",
            payload={
                "channel": str(payload.get("channel", "") or ""),
                "reason": str(payload.get("reason", "") or ""),
                "cause": str(payload.get("cause", "") or ""),
                "command": str(payload.get("command", "") or ""),
                "action": str(payload.get("action", "") or ""),
                "terminate_source": str(payload.get("terminate_source", "") or ""),
                "terminate_reason": str(payload.get("terminate_reason", "") or ""),
                "terminate_trace_id": str(payload.get("terminate_trace_id", "") or ""),
                "terminate_by": str(payload.get("terminate_by", "") or ""),
                "trigger_text": str(payload.get("trigger_text", "") or ""),
            },
            raw=text,
        )

    m = RE_BILLING_START.match(text)
    if m:
        try:
            payload = json.loads(m.group("body"))
        except Exception:
            payload = {}
        return UiEvent(
            kind="billing_started",
            payload={
                "session_id": str(payload.get("session_id", "") or ""),
                "source": str(payload.get("source", "") or ""),
                "trigger_text": str(payload.get("trigger_text", "") or ""),
                "started_at": payload.get("started_at"),
            },
            raw=text,
        )

    m = RE_BILLING_RESULT.match(text)
    if m:
        try:
            payload = json.loads(m.group("body"))
        except Exception:
            payload = {}
        return UiEvent(kind="billing_result", payload=payload if isinstance(payload, dict) else {}, raw=text)

    m = RE_SEND_DONE.match(text)
    if m:
        return UiEvent(
            kind="audio_sent",
            payload={"chunk_index": int(m.group("chunk")), "cost_ms": int(m.group("ms"))},
            raw=text,
        )

    m = RE_SEND_FAILED.match(text)
    if m:
        return UiEvent(
            kind="audio_send_failed",
            payload={"chunk_index": int(m.group("chunk")), "reason": m.group("reason")},
            raw=text,
        )

    m = RE_ASR_PARTIAL.match(text)
    if m:
        asr_text = m.group("text")
        command = ""
        if asr_text.endswith(")") and " (command=" in asr_text:
            head, _, tail = asr_text.rpartition(" (command=")
            asr_text = head
            command = tail[:-1]
        return UiEvent(kind="asr_partial", payload={"text": asr_text, "command": command}, raw=text)

    m = RE_ASR.match(text)
    if m:
        asr_text = m.group("text")
        command = ""
        if asr_text.endswith(")") and " (command=" in asr_text:
            head, _, tail = asr_text.rpartition(" (command=")
            asr_text = head
            command = tail[:-1]
        return UiEvent(kind="asr_commit", payload={"text": asr_text, "command": command}, raw=text)

    m = RE_TTS_START.match(text)
    if m:
        return UiEvent(kind="tts_start", payload={"text": _clean_inline_noise(m.group("text"))}, raw=text)

    m = RE_NLP_PROMPT.match(text)
    if m:
        return UiEvent(
            kind="nlp_prompt",
            payload={"mode": m.group("mode"), "text": m.group("text")},
            raw=text,
        )

    m = RE_TTS_SEGMENT.match(text)
    if m:
        return UiEvent(
            kind="tts_segment",
            payload={"seq": int(m.group("seq")), "text": _clean_inline_noise(m.group("text"))},
            raw=text,
        )

    m = RE_TTS_INTERRUPTED.match(text)
    if m:
        return UiEvent(
            kind="tts_interrupted",
            payload={"trigger": m.group("trigger"), "text": m.group("text")},
            raw=text,
        )

    m = RE_TTS_END.match(text)
    if m:
        interrupted = m.group("interrupted").strip().lower() in {"1", "true", "yes", "y"}
        return UiEvent(
            kind="tts_end",
            payload={"audio_bytes": int(m.group("audio_bytes")), "interrupted": interrupted},
            raw=text,
        )

    m = RE_WS_TTS_FIRST_FRAME.match(text)
    if m:
        return UiEvent(
            kind="tts_first_frame",
            payload={"audio_bytes": int(m.group("bytes"))},
            raw=text,
        )

    m = RE_ASSISTANT_TEXT.match(text)
    if m:
        return UiEvent(kind="assistant_text", payload={"text": _clean_inline_noise(m.group("text"))}, raw=text)

    m = RE_INTENT_RESULT.match(text)
    if m:
        payload_text = m.group("body")
        try:
            payload = json.loads(payload_text)
        except Exception:
            payload = {}
        strategies = payload.get("strategies", payload.get("conversation_strategies", payload.get("next_strategies", [])))
        intents = payload.get("intents", [])
        if isinstance(intents, list):
            normalized_intents = [str(item).strip() for item in intents if str(item).strip()]
        elif intents is None:
            normalized_intents = []
        else:
            item = str(intents).strip()
            normalized_intents = [item] if item else []
        if isinstance(strategies, list):
            normalized_strategies = [str(item).strip() for item in strategies if str(item).strip()]
        elif strategies is None:
            normalized_strategies = []
        else:
            item = str(strategies).strip()
            normalized_strategies = [item] if item else []
        return UiEvent(
            kind="intent_result",
            payload={
                "text": str(payload.get("text", "") or ""),
                "intents": normalized_intents,
                "strategies": normalized_strategies,
                "model": str(payload.get("model", "") or ""),
            },
            raw=text,
        )

    m = RE_INTENT_PROMPT.match(text)
    if m:
        payload_text = m.group("body")
        try:
            payload = json.loads(payload_text)
        except Exception:
            payload = {}
        return UiEvent(
            kind="intent_prompt",
            payload={
                "text": str(payload.get("text", "") or ""),
                "prompt": str(payload.get("prompt", "") or ""),
                "model": str(payload.get("model", "") or ""),
            },
            raw=text,
        )

    m = RE_WORKFLOW_PROGRESS.match(text)
    if m:
        payload_text = m.group("body")
        try:
            payload = json.loads(payload_text)
        except Exception:
            payload = {}
        intents_value = payload.get("intents", [])
        intent_labels_value = payload.get("intent_labels", [])
        intents = intents_value if isinstance(intents_value, list) else []
        intent_labels = intent_labels_value if isinstance(intent_labels_value, list) else []
        advanced_value = payload.get("advanced", False)
        if isinstance(advanced_value, str):
            advanced = advanced_value.strip().lower() in {"1", "true", "yes", "y"}
        else:
            advanced = bool(advanced_value)
        try:
            workflow_nodes = int(payload.get("workflow_nodes", 0) or 0)
        except Exception:
            workflow_nodes = 0
        try:
            workflow_edges = int(payload.get("workflow_edges", 0) or 0)
        except Exception:
            workflow_edges = 0
        return UiEvent(
            kind="workflow_progress",
            payload={
                "trigger": str(payload.get("trigger", "") or ""),
                "session_id": str(payload.get("session_id", "") or ""),
                "from_node_id": str(payload.get("from_node_id", "") or ""),
                "jump_node_id": str(payload.get("jump_node_id", "") or ""),
                "cursor_node_id": str(payload.get("cursor_node_id", "") or ""),
                "route_node_id": str(payload.get("route_node_id", "") or ""),
                "content_node_id": str(payload.get("content_node_id", "") or ""),
                "intent_source_node_id": str(payload.get("intent_source_node_id", "") or ""),
                "matched_label": str(payload.get("matched_label", "") or ""),
                "reason": str(payload.get("reason", "") or ""),
                "advanced": advanced,
                "intents": [str(item).strip() for item in intents if str(item).strip()],
                "intent_labels": [str(item).strip() for item in intent_labels if str(item).strip()],
                "workflow_nodes": workflow_nodes,
                "workflow_edges": workflow_edges,
            },
            raw=text,
        )

    m = RE_LATENCY_ASR.match(text)
    if m:
        params: dict = {}
        params_raw = (m.group("params") or "").strip()
        if params_raw:
            for kv in params_raw.split():
                if "=" in kv:
                    k, _, v = kv.partition("=")
                    try:
                        params[k] = float(v) if v not in ("None", "null", "-") else None
                    except ValueError:
                        params[k] = None
        asr_text = m.group("text").strip()
        if asr_text:
            params["asr_text"] = asr_text
        return UiEvent(kind="latency_asr", payload=params, raw=text)

    m = RE_LATENCY_E2E.match(text)
    if m:
        return UiEvent(kind="latency_e2e", payload={"ms": int(m.group("ms"))}, raw=text)

    m = RE_LATENCY_BACKEND.match(text)
    if m:
        params: dict[str, Optional[float]] = {}
        for kv in m.group("params").split():
            if "=" in kv:
                k, _, v = kv.partition("=")
                try:
                    params[k] = float(v)
                except ValueError:
                    params[k] = None
        return UiEvent(kind="latency_backend", payload=params, raw=text)

    m = RE_LOG_LATENCY_TURN.match(text)
    if m:
        payload_text = m.group("body")
        try:
            payload = ast.literal_eval(payload_text)
        except Exception:
            payload = {}
        params: dict[str, Optional[float]] = {}
        for key in ("queue_wait_ms", "nlp_first_token_ms", "tts_first_audio_ms", "backend_total_ms", "first_send_ms"):
            value = payload.get(key) if isinstance(payload, dict) else None
            try:
                params[key] = float(value) if value is not None else None
            except (TypeError, ValueError):
                params[key] = None
        return UiEvent(kind="latency_backend", payload=params, raw=text)

    m = RE_LOG_LATENCY_ASR.match(text)
    if m:
        params: dict[str, Optional[float] | str] = {}
        try:
            params["asr_recognition_ms"] = float(m.group("asr_recognition_ms"))
        except (TypeError, ValueError):
            params["asr_recognition_ms"] = None
        try:
            params["asr_silence_wait_ms"] = float(m.group("asr_silence_wait_ms"))
        except (TypeError, ValueError):
            params["asr_silence_wait_ms"] = None
        asr_text = (m.group("text") or "").strip()
        if asr_text:
            params["asr_text"] = asr_text
        return UiEvent(kind="latency_asr", payload=params, raw=text)

    return None
