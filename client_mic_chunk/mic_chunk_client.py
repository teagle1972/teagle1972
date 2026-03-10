import argparse
import gzip
import importlib
import json
import math
import os
import queue
import re
import struct
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pyaudio
import requests

# Allow vendored dependencies (e.g., websocket-client) when global site-packages are not writable.
_VENDOR_DIR = Path(__file__).resolve().parent / ".vendor"
if _VENDOR_DIR.exists():
    sys.path.insert(0, str(_VENDOR_DIR))

try:
    import websocket
    from websocket import WebSocketConnectionClosedException, WebSocketTimeoutException
except Exception:
    websocket = None
    WebSocketConnectionClosedException = Exception
    WebSocketTimeoutException = TimeoutError


class _WebRtcApmAdapter:
    def __init__(
        self,
        *,
        processor: Any,
        backend: str,
        sample_rate: int,
        channels: int,
        frame_ms: int = 10,
    ) -> None:
        self.processor = processor
        self.backend = backend
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.frame_ms = int(frame_ms)
        self.frame_bytes = int(self.sample_rate * self.frame_ms / 1000) * 2 * self.channels
        if self.frame_bytes <= 0:
            raise ValueError("invalid webrtc frame size")
        self._lock = threading.Lock()
        self._capture_buffer = bytearray()
        self._reverse_buffer = bytearray()
        self._configure_formats()

    def _configure_formats(self) -> None:
        stream_fn = getattr(self.processor, "set_stream_format", None)
        if callable(stream_fn):
            variants = [
                {
                    "input_sample_rate": self.sample_rate,
                    "input_channels": self.channels,
                    "output_sample_rate": self.sample_rate,
                    "output_channels": self.channels,
                },
                {"sample_rate": self.sample_rate, "channels": self.channels},
            ]
            configured = False
            for kwargs in variants:
                try:
                    stream_fn(**kwargs)
                    configured = True
                    break
                except Exception:
                    continue
            if not configured:
                arg_variants = [
                    (self.sample_rate, self.channels, self.sample_rate, self.channels),
                    (self.sample_rate, self.channels),
                ]
                for values in arg_variants:
                    try:
                        stream_fn(*values)
                        break
                    except Exception:
                        continue

        reverse_fn = getattr(self.processor, "set_reverse_stream_format", None)
        if callable(reverse_fn):
            configured = False
            variants = [
                {"sample_rate": self.sample_rate, "channels": self.channels},
            ]
            for kwargs in variants:
                try:
                    reverse_fn(**kwargs)
                    configured = True
                    break
                except Exception:
                    continue
            if not configured:
                try:
                    reverse_fn(self.sample_rate, self.channels)
                except Exception:
                    pass

    def _coerce_pcm(self, value: Any, fallback: bytes) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, bytearray):
            return bytes(value)
        if isinstance(value, memoryview):
            return value.tobytes()
        return fallback

    def _set_stream_delay_ms(self, delay_ms: int) -> None:
        delay_fn = getattr(self.processor, "set_stream_delay", None)
        if callable(delay_fn):
            try:
                delay_fn(int(delay_ms))
                return
            except Exception:
                pass
        delay_fn = getattr(self.processor, "set_stream_delay_ms", None)
        if callable(delay_fn):
            try:
                delay_fn(int(delay_ms))
            except Exception:
                pass

    def feed_reverse(self, pcm: bytes) -> None:
        if not pcm:
            return
        reverse_fn = getattr(self.processor, "process_reverse_stream", None)
        if not callable(reverse_fn):
            reverse_fn = getattr(self.processor, "analyze_reverse_stream", None)
        if not callable(reverse_fn):
            return
        self._reverse_buffer.extend(pcm)
        while len(self._reverse_buffer) >= self.frame_bytes:
            frame = bytes(self._reverse_buffer[: self.frame_bytes])
            del self._reverse_buffer[: self.frame_bytes]
            with self._lock:
                reverse_fn(frame)

    def process_capture(self, pcm: bytes, *, delay_ms: int = 0) -> bytes:
        if not pcm:
            return pcm
        process_fn = getattr(self.processor, "process_stream", None)
        if not callable(process_fn):
            return pcm

        self._capture_buffer.extend(pcm)
        out = bytearray()
        while len(self._capture_buffer) >= self.frame_bytes:
            frame = bytes(self._capture_buffer[: self.frame_bytes])
            del self._capture_buffer[: self.frame_bytes]
            with self._lock:
                self._set_stream_delay_ms(delay_ms)
                processed = process_fn(frame)
            out.extend(self._coerce_pcm(processed, frame))

        if self._capture_buffer:
            # Keep stream moving even if chunk size is not exactly aligned to frame size.
            out.extend(bytes(self._capture_buffer))
            self._capture_buffer.clear()
        return bytes(out)


class MicChunkClient:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.session_id = args.session_id or f"mic_{uuid.uuid4().hex[:12]}"
        self.frames_per_chunk = int(args.sample_rate * args.chunk_ms / 1000)
        self.bytes_per_sample = 2  # 16-bit PCM, aligned with test/micDemo.py
        self.channels = 1
        if self.frames_per_chunk <= 0:
            raise ValueError("frames_per_chunk must be > 0")
        self.chunk_bytes = self.frames_per_chunk * self.bytes_per_sample * self.channels
        self.packets_per_second = 1000.0 / float(args.chunk_ms)

        self.stop_event = threading.Event()
        self.audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=args.queue_size)
        self.chunk_index = 0
        self.max_chunks = args.max_chunks

        self._pa: pyaudio.PyAudio | None = None
        self._input_stream = None
        self._output_stream = None
        self._capture_thread: threading.Thread | None = None
        self._sender_thread: threading.Thread | None = None
        self._receiver_thread: threading.Thread | None = None
        self._receiver_control_thread: threading.Thread | None = None
        self._receiver_media_thread: threading.Thread | None = None
        self._ws = None
        self._ws_control = None
        self._ws_media = None
        self._ws_send_lock = threading.Lock()
        self._ws_control_send_lock = threading.Lock()
        self._ws_media_send_lock = threading.Lock()
        self._ws_media_reconnect_deadline = 0.0
        self._ws_audio_frame_count = 0
        self._ws_audio_total_bytes = 0
        self._play_frames_written = 0
        self._play_first_frame_at = 0.0
        self._drop_audio_until_tts_end = False
        self._tts_active = False
        self._tts_started_at = 0.0
        self._tts_last_segment_at = 0.0
        self._tts_interrupted_recent = False
        self._tts_latency_emitted = False
        # Reference-based echo suppression state (far-end TTS render -> near-end mic capture).
        self._aec_warned_rate_mismatch = False
        self._aec_resample_src_total = 0
        self._aec_resample_dst_total = 0
        self._aec_resample_prev_sample: int | None = None
        self._aec_engine = str(getattr(self.args, "aec_engine", "webrtc") or "webrtc").strip().lower()
        self._aec_effective_engine = "webrtc"
        self._aec_webrtc_backend = ""
        self._aec_webrtc_adapter: _WebRtcApmAdapter | None = None
        self._aec_webrtc_error = ""
        self._aec_webrtc_warn_deadline = 0.0
        self._aec_ref_lock = threading.Lock()
        self._aec_ref_ring = bytearray()
        self._aec_ref_delay_bytes = self._ms_to_pcm16_bytes(self.args.aec_ref_delay_ms)
        self._aec_dynamic_delay_bytes = self._aec_ref_delay_bytes
        self._aec_search_span_bytes = self._ms_to_pcm16_bytes(self.args.aec_search_span_ms)
        self._aec_search_step_bytes = max(2, self._ms_to_pcm16_bytes(self.args.aec_search_step_ms))
        self._aec_auto_delay_counter = 0
        self._aec_delay_log_deadline = 0.0
        self._aec_gate_log_deadline = 0.0
        self._aec_tts_gate_log_deadline = 0.0
        self._aec_warmup_log_deadline = 0.0
        self._aec_tts_stale_log_deadline = 0.0
        self._aec_half_duplex_log_deadline = 0.0
        self._aec_barge_in_hits = 0
        self._aec_ref_history_bytes = self._ms_to_pcm16_bytes(self.args.aec_ref_buffer_ms)
        self._aec_ref_capacity_bytes = max(
            self.chunk_bytes * 4,
            self._aec_ref_history_bytes + self._aec_ref_delay_bytes + self.chunk_bytes * 2,
        )
        self._aec_output_latency_ms = 0
        self._aec_last_ref_feed_at = 0.0
        self._asr_wait_since = 0.0
        self._asr_first_commit_seen = False
        self._asr_wait_warned = False
        self._asr_seq = 1
        self._last_audio_sent_at: float = 0.0  # 鏈€杩戜竴娆″彂閫侀煶棰?chunk 鐨勬椂鍒伙紝鐢ㄤ簬璁＄畻涓婁紶+鍚庡彴鑰楁椂
        self._queue_drop_oldest = 0
        self._queue_drop_newest = 0
        self._queue_drop_log_deadline = 0.0
        self._terminate_cause_lock = threading.Lock()
        self._pending_terminate_cause: dict[str, object] | None = None
        self._whoami_probed = False

        self._runtime_customer_profile = (os.getenv("CUSTOMER_PROFILE") or "").strip()
        self._runtime_workflow_text = (os.getenv("WORKFLOW_TEXT") or "").strip()
        self._runtime_workflow_json = self._extract_workflow_json(os.getenv("WORKFLOW_JSON") or "")
        self._runtime_system_instruction_text = (os.getenv("SYSTEM_INSTRUCTION_TEXT") or "").strip()
        self._runtime_intent_labels = self._extract_intent_labels(os.getenv("INTENT_LABELS") or "")
        self._runtime_intent_fallback_label = (os.getenv("INTENT_FALLBACK_LABEL") or "").strip()
        self._runtime_prompt_pushed = False
        self._start_dialog_sent = False

        self._save_dir: Path | None = Path(args.save_dir) if args.save_dir else None
        if self._save_dir is not None:
            self._save_dir.mkdir(parents=True, exist_ok=True)

    @property
    def endpoint(self) -> str:
        return self.args.base_url.rstrip("/") + "/api/v3/audio/chunks"

    def _build_ws_endpoint(self, path: str) -> str:
        base = self.args.base_url.rstrip("/")
        if base.startswith("http://"):
            ws_base = "ws://" + base[len("http://") :]
        elif base.startswith("https://"):
            ws_base = "wss://" + base[len("https://") :]
        elif base.startswith(("ws://", "wss://")):
            ws_base = base
        else:
            ws_base = "ws://" + base
        endpoint_path = path if path.startswith("/") else f"/{path}"
        query = urlencode({"session_id": self.session_id, "format": self.args.audio_format})
        return f"{ws_base}{endpoint_path}?{query}"

    @property
    def ws_endpoint(self) -> str:
        return self._build_ws_endpoint(self.args.ws_path)

    @property
    def ws_control_endpoint(self) -> str:
        return self._build_ws_endpoint(self.args.ws_control_path)

    @property
    def ws_media_endpoint(self) -> str:
        return self._build_ws_endpoint(self.args.ws_media_path)

    @property
    def asr_ws_endpoint(self) -> str:
        return str(self.args.asr_ws_url).strip()

    def _probe_server_whoami(self) -> None:
        if self._whoami_probed:
            return
        self._whoami_probed = True
        url = self.args.base_url.rstrip("/") + "/debug/whoami"
        try:
            resp = requests.get(url, timeout=2.0)
            body_text = (resp.text or "").strip()
            payload: dict[str, Any]
            try:
                parsed = resp.json()
                payload = parsed if isinstance(parsed, dict) else {"body": parsed}
            except Exception:
                payload = {"body": body_text[:500]}
            payload["status_code"] = resp.status_code
            print("[server/whoami] " + json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            print(f"[server/whoami] failed url={url} err={exc}")

    @staticmethod
    def _gzip_compress(data: bytes) -> bytes:
        return gzip.compress(data)

    @staticmethod
    def _gzip_decompress(data: bytes) -> bytes:
        return gzip.decompress(data)

    def _new_asr_auth_headers(self) -> list[str]:
        return [
            "X-Api-Resource-Id: volc.bigasr.sauc.duration",
            f"X-Api-Request-Id: {uuid.uuid4()}",
            f"X-Api-Access-Key: {self.args.asr_access_key}",
            f"X-Api-App-Key: {self.args.asr_app_key}",
        ]

    def _build_asr_full_request(self, seq: int) -> bytes:
        header = bytearray()
        header.append((0b0001 << 4) | 1)
        header.append((0b0001 << 4) | 0b0001)
        header.append((0b0001 << 4) | 0b0001)
        header.extend(bytes([0x00]))

        payload = {
            "user": {"uid": self.session_id},
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": self.args.sample_rate,
                "bits": 16,
                "channel": 1,
                "language": self.args.asr_language,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "enable_lid": False,
                "show_utterances": True,
                "enable_nonstream": False,
                "result_type": "single",
                "end_window_size": self.args.asr_end_window_size,
                "force_to_speech_time": self.args.asr_force_to_speech_time,
            },
        }
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        compressed = self._gzip_compress(payload_bytes)

        req = bytearray()
        req.extend(bytes(header))
        req.extend(struct.pack(">i", seq))
        req.extend(struct.pack(">I", len(compressed)))
        req.extend(compressed)
        return bytes(req)

    def _build_asr_audio_request(self, seq: int, segment: bytes, is_last: bool = False) -> bytes:
        header = bytearray()
        header.append((0b0001 << 4) | 1)
        header.append((0b0010 << 4) | (0b0011 if is_last else 0b0001))
        header.append((0b0001 << 4) | 0b0001)
        header.extend(bytes([0x00]))

        actual_seq = -seq if is_last else seq
        compressed_segment = self._gzip_compress(segment)

        req = bytearray()
        req.extend(bytes(header))
        req.extend(struct.pack(">i", actual_seq))
        req.extend(struct.pack(">I", len(compressed_segment)))
        req.extend(compressed_segment)
        return bytes(req)

    def _parse_asr_response(self, msg: bytes) -> dict[str, Any]:
        header_size = msg[0] & 0x0F
        message_type = msg[1] >> 4
        flags = msg[1] & 0x0F
        serialization = msg[2] >> 4
        compression = msg[2] & 0x0F
        payload = msg[header_size * 4 :]

        is_last = bool(flags & 0x02)
        code = 0
        seq = 0
        event = 0

        if flags & 0x01:
            seq = struct.unpack(">i", payload[:4])[0]
            payload = payload[4:]
        if flags & 0x04:
            event = struct.unpack(">i", payload[:4])[0]
            payload = payload[4:]

        if message_type == 0b1001:
            payload = payload[4:]
        elif message_type == 0b1111:
            code = struct.unpack(">i", payload[:4])[0]
            payload = payload[8:]

        payload_msg: Any = None
        if payload:
            if compression == 0b0001:
                payload = self._gzip_decompress(payload)
            if serialization == 0b0001:
                payload_msg = json.loads(payload.decode("utf-8"))

        return {"code": code, "seq": seq, "event": event, "is_last": is_last, "payload_msg": payload_msg}

    @staticmethod
    def _extract_asr_text(payload_msg: Any) -> str:
        if payload_msg is None:
            return ""

        obj = payload_msg
        if isinstance(obj, dict) and isinstance(obj.get("result"), dict):
            obj = obj["result"]

        if isinstance(obj, dict) and isinstance(obj.get("utterances"), list):
            texts = []
            for u in obj["utterances"]:
                if not isinstance(u, dict):
                    continue
                t = u.get("text") or u.get("sentence")
                if isinstance(t, str) and t.strip():
                    texts.append(t.strip())
            if texts:
                return " ".join(texts)

        if isinstance(obj, dict):
            for k in ("text", "transcript", "sentence"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()

        if isinstance(payload_msg, dict):
            for k in ("text", "transcript", "sentence"):
                v = payload_msg.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()

        if isinstance(payload_msg, str):
            return payload_msg.strip()
        return ""

    @staticmethod
    def _extract_intent_labels(raw_text: str) -> list[str]:
        labels: list[str] = []
        seen: set[str] = set()
        marker_prefixes = (
            "intents:",
            "model:",
            "customer:",
            "assistant:",
        )
        for raw_line in (raw_text or "").splitlines():
            line = str(raw_line or "").replace("\r", "").strip()
            if not line:
                continue
            line = re.sub(r"^[\-\*\u2022]\s*", "", line)
            line = re.sub(r"^\d+\s*[\.)]\s*", "", line)
            line = line.rstrip(",;").strip()
            if not line:
                continue
            lower_line = line.lower()
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
        return labels

    @staticmethod
    def _extract_workflow_json(raw_text: str) -> dict[str, Any] | None:
        current = (raw_text or "").strip()
        if not current:
            return None
        try:
            payload = json.loads(current)
        except Exception as exc:
            print(f"[prompt] ignore invalid WORKFLOW_JSON: {exc}")
            return None
        if not isinstance(payload, dict):
            print("[prompt] ignore invalid WORKFLOW_JSON: root must be JSON object")
            return None
        return payload

    @staticmethod
    def _workflow_graph_stats(workflow_obj: dict[str, Any] | None) -> tuple[int, int]:
        if not isinstance(workflow_obj, dict):
            return 0, 0
        nodes = workflow_obj.get("nodes")
        edges = workflow_obj.get("edges")
        return (
            len(nodes) if isinstance(nodes, list) else 0,
            len(edges) if isinstance(edges, list) else 0,
        )

    def _build_prompt_context_payload(self) -> dict[str, Any]:
        prompt_context: dict[str, Any] = {}
        system_instruction = str(self._runtime_system_instruction_text or "").strip()
        customer_profile = str(self._runtime_customer_profile or "").strip()
        workflow_text = str(self._runtime_workflow_text or "").strip()
        if system_instruction:
            prompt_context["system_instruction"] = system_instruction
        if customer_profile:
            prompt_context["customer_profile"] = customer_profile
        if self._runtime_workflow_json:
            prompt_context["workflow_json"] = self._runtime_workflow_json
        elif workflow_text:
            prompt_context["workflow_text"] = workflow_text
        return prompt_context

    def _build_webrtc_processor_instance(self, processor_cls: Any) -> Any:
        ctor_variants = [
            {
                "enable_aec": True,
                "enable_ns": bool(self.args.aec_webrtc_ns),
                "enable_agc": bool(self.args.aec_webrtc_agc),
            },
            {},
        ]
        last_error = ""
        for kwargs in ctor_variants:
            try:
                return processor_cls(**kwargs)
            except Exception as exc:
                last_error = str(exc)
        try:
            return processor_cls()
        except Exception as exc:
            if not last_error:
                last_error = str(exc)
            raise RuntimeError(last_error or str(exc)) from exc

    def _configure_webrtc_processor(self, processor: Any) -> None:
        aec_type_fn = getattr(processor, "set_aec_type", None)
        if callable(aec_type_fn):
            try:
                aec_type_fn(int(self.args.aec_webrtc_aec_type))
            except Exception:
                pass
        onoff_methods = [
            ("set_aec_enabled", True),
            ("set_ns_enabled", bool(self.args.aec_webrtc_ns)),
            ("set_agc_enabled", bool(self.args.aec_webrtc_agc)),
        ]
        for name, value in onoff_methods:
            fn = getattr(processor, name, None)
            if callable(fn):
                try:
                    fn(value)
                except Exception:
                    pass

    def _create_webrtc_adapter(self) -> _WebRtcApmAdapter | None:
        load_errors: list[str] = []
        candidates = [
            ("aec_audio_processing", "AudioProcessor"),
            ("webrtc_apm", "AudioProcessor"),
            ("webrtc_audio_processing", "AudioProcessingModule"),
        ]
        for module_name, class_name in candidates:
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                load_errors.append(f"{module_name}: {exc}")
                continue
            processor_cls = getattr(module, class_name, None)
            if processor_cls is None:
                load_errors.append(f"{module_name}: missing {class_name}")
                continue
            try:
                processor = self._build_webrtc_processor_instance(processor_cls)
                self._configure_webrtc_processor(processor)
                adapter = _WebRtcApmAdapter(
                    processor=processor,
                    backend=f"{module_name}.{class_name}",
                    sample_rate=self.args.sample_rate,
                    channels=self.channels,
                )
                return adapter
            except Exception as exc:
                load_errors.append(f"{module_name}: {exc}")
                continue
        self._aec_webrtc_error = "; ".join(load_errors)
        return None

    def _init_aec_engine(self) -> None:
        self._aec_effective_engine = "webrtc"
        self._aec_webrtc_backend = ""
        self._aec_webrtc_adapter = None
        self._aec_webrtc_error = ""
        engine = self._aec_engine
        if engine != "webrtc":
            raise RuntimeError(f"unsupported aec engine: {engine}; only webrtc is supported")
        if not self.args.aec_enabled:
            self._aec_effective_engine = "disabled"
            return

        adapter = self._create_webrtc_adapter()
        if adapter is None:
            message = self._aec_webrtc_error or "no usable python WebRTC APM backend found"
            raise RuntimeError(f"webrtc aec required but unavailable: {message}")
        self._aec_webrtc_adapter = adapter
        self._aec_webrtc_backend = adapter.backend
        self._aec_effective_engine = "webrtc"

    def _ms_to_pcm16_bytes(self, duration_ms: int) -> int:
        frames = int(self.args.sample_rate * max(0, int(duration_ms)) / 1000)
        return frames * self.bytes_per_sample * self.channels

    def _resample_playback_for_aec(self, audio: bytes) -> bytes:
        if not audio:
            return b""
        if self.args.playback_sample_rate == self.args.sample_rate:
            return audio
        src_rate = int(self.args.playback_sample_rate)
        dst_rate = int(self.args.sample_rate)
        if src_rate <= 0 or dst_rate <= 0:
            return b""
        sample_count = len(audio) // 2
        if sample_count <= 0:
            return b""
        src_samples: list[int] = []
        for i in range(sample_count):
            off = i * 2
            src_samples.append(int.from_bytes(audio[off : off + 2], byteorder="little", signed=True))
        if not src_samples:
            return b""
        src_start = self._aec_resample_src_total
        src_end = src_start + len(src_samples)
        dst_end = int((src_end * dst_rate) // src_rate)
        emit_count = dst_end - self._aec_resample_dst_total
        if emit_count <= 0:
            self._aec_resample_src_total = src_end
            self._aec_resample_prev_sample = src_samples[-1]
            return b""

        out = bytearray(emit_count * 2)
        for i in range(emit_count):
            dst_idx = self._aec_resample_dst_total + i
            src_pos = (float(dst_idx) * float(src_rate)) / float(dst_rate)
            local_pos = src_pos - float(src_start)
            base = int(local_pos)
            frac = local_pos - float(base)
            if base < 0:
                s0 = self._aec_resample_prev_sample if self._aec_resample_prev_sample is not None else src_samples[0]
                s1 = src_samples[0]
            elif base >= (len(src_samples) - 1):
                s0 = src_samples[-1]
                s1 = src_samples[-1]
            else:
                s0 = src_samples[base]
                s1 = src_samples[base + 1]
            sample = int((1.0 - frac) * float(s0) + frac * float(s1))
            if sample > 32767:
                sample = 32767
            elif sample < -32768:
                sample = -32768
            off = i * 2
            out[off : off + 2] = int(sample).to_bytes(2, byteorder="little", signed=True)

        self._aec_resample_src_total = src_end
        self._aec_resample_dst_total += emit_count
        self._aec_resample_prev_sample = src_samples[-1]
        try:
            return bytes(out)
        except Exception as exc:
            if not self._aec_warned_rate_mismatch:
                print(f"[aec] failed to resample playback reference: {exc}")
                self._aec_warned_rate_mismatch = True
            return b""

    def _append_playback_reference(self, audio: bytes) -> None:
        if (not self.args.aec_enabled) or (not audio):
            return
        reference = self._resample_playback_for_aec(audio)
        if not reference:
            return
        if self._aec_effective_engine == "webrtc" and self._aec_webrtc_adapter is not None:
            try:
                self._aec_webrtc_adapter.feed_reverse(reference)
            except Exception as exc:
                now = time.monotonic()
                if now >= self._aec_webrtc_warn_deadline:
                    self._aec_webrtc_warn_deadline = now + 2.0
                    print(f"[aec] webrtc_reverse_stream_failed: {exc}")
        self._aec_last_ref_feed_at = time.monotonic()
        with self._aec_ref_lock:
            self._aec_ref_ring.extend(reference)
            overflow = len(self._aec_ref_ring) - self._aec_ref_capacity_bytes
            if overflow > 0:
                del self._aec_ref_ring[:overflow]

    def _refresh_aec_output_latency(self) -> None:
        if (not self.args.aec_enabled) or (not self.args.aec_use_output_latency):
            return
        if self._output_stream is None:
            return
        old_ref_delay_bytes = self._aec_ref_delay_bytes
        old_dynamic_delay_bytes = self._aec_dynamic_delay_bytes
        try:
            raw_latency = float(self._output_stream.get_output_latency() or 0.0)
        except Exception:
            raw_latency = 0.0
        output_latency_ms = max(0, int(round(raw_latency * 1000.0)))
        base_delay_ms = max(0, int(self.args.aec_ref_delay_ms))
        total_delay_ms = base_delay_ms + output_latency_ms
        self._aec_ref_delay_bytes = self._ms_to_pcm16_bytes(total_delay_ms)
        if self.args.aec_auto_delay and old_dynamic_delay_bytes > 0:
            delay_delta = self._aec_ref_delay_bytes - old_ref_delay_bytes
            self._aec_dynamic_delay_bytes = max(0, old_dynamic_delay_bytes + delay_delta)
        else:
            self._aec_dynamic_delay_bytes = self._aec_ref_delay_bytes
        min_capacity = self._aec_ref_history_bytes + self._aec_ref_delay_bytes + (self.chunk_bytes * 2)
        if min_capacity > self._aec_ref_capacity_bytes:
            self._aec_ref_capacity_bytes = min_capacity
        self._aec_output_latency_ms = output_latency_ms
        print(
            "[aec] output_latency_adjust "
            f"base_delay_ms={base_delay_ms} "
            f"output_latency_ms={output_latency_ms} "
            f"effective_delay_ms={total_delay_ms} "
            f"dynamic_delay_ms={self._bytes_to_ms(self._aec_dynamic_delay_bytes)}"
        )

    def _extract_reference_for_delay(self, chunk_size: int, delay_bytes: int) -> bytes:
        if chunk_size <= 0:
            return b""
        delay = max(0, int(delay_bytes))
        with self._aec_ref_lock:
            ring_size = len(self._aec_ref_ring)
            if ring_size <= 0:
                return b"\x00" * chunk_size
            end = ring_size - delay
            if end <= 0:
                return b"\x00" * chunk_size
            start = end - chunk_size
            prefix_zeros = 0
            if start < 0:
                prefix_zeros = -start
                start = 0
            clipped = bytes(self._aec_ref_ring[start:end])
        if prefix_zeros > 0:
            clipped = (b"\x00" * prefix_zeros) + clipped
        if len(clipped) < chunk_size:
            clipped = (b"\x00" * (chunk_size - len(clipped))) + clipped
        elif len(clipped) > chunk_size:
            clipped = clipped[-chunk_size:]
        return clipped

    def _pcm16_similarity(self, lhs: bytes, rhs: bytes) -> float:
        sample_count = min(len(lhs), len(rhs)) // 2
        if sample_count <= 0:
            return 0.0
        dot = 0.0
        lhs_energy = 0.0
        rhs_energy = 0.0
        for i in range(sample_count):
            off = i * 2
            l = int.from_bytes(lhs[off : off + 2], byteorder="little", signed=True)
            r = int.from_bytes(rhs[off : off + 2], byteorder="little", signed=True)
            dot += float(l * r)
            lhs_energy += float(l * l)
            rhs_energy += float(r * r)
        denom = math.sqrt(max(1.0, lhs_energy * rhs_energy))
        score = abs(dot) / denom
        if score > 1.0:
            score = 1.0
        return score

    def _bytes_to_ms(self, pcm_bytes: int) -> int:
        sample_width = self.bytes_per_sample * self.channels
        if sample_width <= 0 or self.args.sample_rate <= 0:
            return 0
        frames = float(max(0, int(pcm_bytes))) / float(sample_width)
        return int((frames * 1000.0) / float(self.args.sample_rate))

    def _get_reference_for_mic_chunk(self, mic_data: bytes) -> bytes:
        chunk_size = len(mic_data)
        if (not self.args.aec_enabled) or chunk_size <= 0:
            return b""
        if self._aec_last_ref_feed_at <= 0:
            return b"\x00" * chunk_size
        hold_ms = max(0, int(self.args.aec_ref_hold_ms))
        elapsed_ms = (time.monotonic() - self._aec_last_ref_feed_at) * 1000.0
        if elapsed_ms > float(hold_ms):
            return b"\x00" * chunk_size

        center_delay = max(0, int(self._aec_dynamic_delay_bytes or self._aec_ref_delay_bytes))
        if not self.args.aec_auto_delay:
            return self._extract_reference_for_delay(chunk_size, center_delay)

        center_ref = self._extract_reference_for_delay(chunk_size, center_delay)
        if self._pcm16_rms(center_ref) < self.args.aec_ref_min_rms:
            return center_ref
        interval_chunks = max(1, int(self.args.aec_auto_delay_interval_chunks))
        self._aec_auto_delay_counter += 1
        if (self._aec_auto_delay_counter % interval_chunks) != 0:
            return center_ref

        span = max(0, int(self._aec_search_span_bytes))
        step = max(2, int(self._aec_search_step_bytes))
        best_delay = center_delay
        best_ref = center_ref
        best_score = self._pcm16_similarity(mic_data, center_ref)
        if span > 0:
            start = max(0, center_delay - span)
            end = center_delay + span
            delay = start
            while delay <= end:
                ref = self._extract_reference_for_delay(chunk_size, delay)
                score = self._pcm16_similarity(mic_data, ref)
                if score > best_score:
                    best_delay = delay
                    best_ref = ref
                    best_score = score
                delay += step
        best_ref_rms = self._pcm16_rms(best_ref)
        if best_score >= self.args.aec_auto_delay_min_score and best_ref_rms >= self.args.aec_ref_min_rms:
            smoothed_delay = int((0.80 * float(center_delay)) + (0.20 * float(best_delay)))
            self._aec_dynamic_delay_bytes = max(0, smoothed_delay)

            now = time.monotonic()
            if abs(best_delay - center_delay) >= step and now >= self._aec_delay_log_deadline:
                self._aec_delay_log_deadline = now + 2.5
                print(
                    "[aec] auto_delay "
                    f"best_ms={self._bytes_to_ms(best_delay)} "
                    f"current_ms={self._bytes_to_ms(self._aec_dynamic_delay_bytes)} "
                    f"score={best_score:.3f}"
                )
            return best_ref
        return center_ref

    def _should_mute_for_tts_warmup(self, mic_data: bytes | None = None) -> bool:
        if (not self.args.aec_enabled) or (not self._tts_active):
            return False
        warmup_ms = max(0, int(self.args.aec_tts_warmup_mute_ms))
        ref_wait_mute_ms = max(warmup_ms, int(self.args.aec_tts_ref_wait_mute_ms))
        if ref_wait_mute_ms <= 0 or self._tts_started_at <= 0:
            return False
        elapsed_ms = (time.monotonic() - self._tts_started_at) * 1000.0
        no_ref_after_start = self._aec_last_ref_feed_at <= self._tts_started_at
        # Policy: no reference means no echo evidence; allow upstream ASR.
        if no_ref_after_start:
            return False
        if elapsed_ms > float(warmup_ms):
            return False
        if self.args.aec_preserve_barge_in and mic_data:
            mic_rms = self._pcm16_rms(mic_data)
            if mic_rms >= int(self.args.aec_barge_in_warmup_rms):
                return False
        now = time.monotonic()
        if now >= self._aec_warmup_log_deadline:
            self._aec_warmup_log_deadline = now + 2.0
            print(
                "[aec] tts_warmup_mute "
                f"elapsed_ms={int(elapsed_ms)} "
                f"warmup_ms={warmup_ms} "
                f"ref_wait_mute_ms={ref_wait_mute_ms} "
                f"no_ref_after_start={no_ref_after_start} "
                f"has_segment={(self._tts_last_segment_at > self._tts_started_at)}"
            )
        return True

    def _maybe_clear_stale_tts_state(self) -> None:
        if not self._tts_active:
            return
        stale_ms = max(0, int(self.args.aec_tts_stale_ms))
        if stale_ms <= 0:
            return
        now = time.monotonic()
        started_elapsed_ms = (now - self._tts_started_at) * 1000.0 if self._tts_started_at > 0 else 0.0
        last_ref_elapsed_ms = (now - self._aec_last_ref_feed_at) * 1000.0 if self._aec_last_ref_feed_at > 0 else 0.0
        ref_after_start = (self._aec_last_ref_feed_at > 0) and (
            (self._tts_started_at <= 0) or (self._aec_last_ref_feed_at > self._tts_started_at)
        )
        no_ref_after_start = not ref_after_start
        should_clear = False
        no_ref_stale_ms = max(stale_ms, int(self.args.aec_tts_ref_wait_mute_ms) + 400)
        if no_ref_after_start:
            segment_elapsed_ms = (now - self._tts_last_segment_at) * 1000.0 if self._tts_last_segment_at > 0 else 0.0
            segment_recent = (
                self._tts_last_segment_at > self._tts_started_at and segment_elapsed_ms <= 1200.0
            )
            if (not segment_recent) and started_elapsed_ms >= float(no_ref_stale_ms):
                should_clear = True
        elif ref_after_start and last_ref_elapsed_ms >= float(stale_ms):
            should_clear = True
        if not should_clear:
            return
        self._tts_active = False
        self._tts_started_at = 0.0
        self._aec_barge_in_hits = 0
        if now >= self._aec_tts_stale_log_deadline:
            self._aec_tts_stale_log_deadline = now + 2.0
            print(
                "[aec] clear_stale_tts_state "
                f"stale_ms={stale_ms} "
                f"no_ref_stale_ms={no_ref_stale_ms} "
                f"since_tts_start_ms={int(started_elapsed_ms)} "
                f"since_ref_ms={int(last_ref_elapsed_ms)} "
                f"ref_after_start={ref_after_start}"
            )

    def _is_tts_barge_in(self, mic_data: bytes, ref_data: bytes) -> bool:
        mic_rms = self._pcm16_rms(mic_data)
        if mic_rms < int(self.args.aec_tts_barge_in_rms):
            return False
        ref_rms = self._pcm16_rms(ref_data)
        if ref_rms > 0 and mic_rms < int(float(ref_rms) * self.args.aec_tts_barge_in_ratio):
            return False
        if ref_rms >= self.args.aec_ref_min_rms:
            similarity = self._pcm16_similarity(mic_data, ref_data)
            if similarity > self.args.aec_tts_barge_in_sim_max:
                return False
        return True

    def _process_with_webrtc_apm(self, mic_data: bytes) -> bytes:
        if (not mic_data) or self._aec_webrtc_adapter is None:
            return mic_data
        delay_ms = self._bytes_to_ms(self._aec_dynamic_delay_bytes)
        try:
            return self._aec_webrtc_adapter.process_capture(mic_data, delay_ms=delay_ms)
        except Exception as exc:
            now = time.monotonic()
            if now >= self._aec_webrtc_warn_deadline:
                self._aec_webrtc_warn_deadline = now + 2.0
                print(f"[aec] webrtc_process_failed: {exc}")
            return mic_data

    def _apply_echo_post_filters(self, raw_mic_data: bytes, ref_data: bytes, cleaned: bytes) -> bytes:
        if (not raw_mic_data) or (not ref_data) or (not cleaned):
            return cleaned
        before = self._pcm16_similarity(raw_mic_data, ref_data)
        after = self._pcm16_similarity(cleaned, ref_data)
        mic_rms = self._pcm16_rms(raw_mic_data)
        cleaned_rms = self._pcm16_rms(cleaned)
        ref_rms = self._pcm16_rms(ref_data)
        near_end_active = mic_rms >= int(float(ref_rms) * self.args.aec_near_end_protect_ratio)
        preserve_barge = self.args.aec_preserve_barge_in and self._tts_active
        if self.args.aec_echo_gate:
            if self._tts_active and (not near_end_active):
                tts_gate_hit = (
                    before >= self.args.aec_tts_echo_gate_sim_threshold
                    and after >= self.args.aec_tts_echo_gate_clean_sim_threshold
                    and cleaned_rms <= int(float(ref_rms) * self.args.aec_tts_echo_gate_rms_ratio)
                )
                if tts_gate_hit:
                    barge_candidate = self._is_tts_barge_in(raw_mic_data, ref_data)
                    if (not preserve_barge) or (not barge_candidate):
                        now = time.monotonic()
                        if now >= self._aec_tts_gate_log_deadline:
                            self._aec_tts_gate_log_deadline = now + 2.0
                            print(
                                "[aec] tts_echo_gate "
                                f"sim_before={before:.3f} "
                                f"sim_after={after:.3f} "
                                f"mic_rms={mic_rms} "
                                f"clean_rms={cleaned_rms} "
                                f"ref_rms={ref_rms} "
                                f"preserve_barge={preserve_barge} "
                                f"barge_candidate={barge_candidate}"
                            )
                        return b"\x00" * len(cleaned)
            if (not self._tts_active) and (not near_end_active) and (
                before >= self.args.aec_echo_gate_sim_threshold
                and after >= self.args.aec_echo_gate_clean_sim_threshold
                and cleaned_rms <= int(float(ref_rms) * self.args.aec_echo_gate_rms_ratio)
            ):
                now = time.monotonic()
                if now >= self._aec_gate_log_deadline:
                    self._aec_gate_log_deadline = now + 2.0
                    print(
                        "[aec] echo_gate "
                        f"sim_before={before:.3f} "
                        f"sim_after={after:.3f} "
                        f"mic_rms={mic_rms} "
                        f"clean_rms={cleaned_rms} "
                        f"ref_rms={ref_rms}"
                    )
                return b"\x00" * len(cleaned)
        if self.args.aec_residual_suppress:
            if (
                before >= self.args.aec_residual_sim_threshold
                and after >= self.args.aec_residual_sim_threshold
                and mic_rms <= int(float(ref_rms) * 1.35)
            ):
                cleaned = self._apply_pcm_gain(cleaned, self.args.aec_residual_attenuation)
        return cleaned

    def start(self) -> None:
        need_pa = (not self.args.local) or self.args.playback
        if need_pa:
            self._pa = pyaudio.PyAudio()

        if not self.args.local:
            assert self._pa is not None
            self._print_input_device_info(self.args.input_device_index)
            open_kwargs = dict(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.args.sample_rate,
                input=True,
                frames_per_buffer=self.frames_per_chunk,
            )
            # Align with micDemo: use PortAudio default input unless user explicitly sets index.
            if self.args.input_device_index is not None:
                open_kwargs["input_device_index"] = self.args.input_device_index
            print(
                "[mic/monitor] opening input stream "
                f"sample_rate={self.args.sample_rate} chunk_ms={self.args.chunk_ms} "
                f"frames_per_chunk={self.frames_per_chunk}"
            )
            try:
                self._input_stream = self._pa.open(**open_kwargs)
            except Exception as exc:
                print(
                    "[mic/error] failed to open input stream "
                    f"sample_rate={self.args.sample_rate} frames_per_chunk={self.frames_per_chunk} "
                    f"input_device_index={self.args.input_device_index}: {exc}"
                )
                raise
            print(
                "[mic/monitor] opened input stream "
                f"sample_rate={self.args.sample_rate} chunk_ms={self.args.chunk_ms} "
                f"frames_per_chunk={self.frames_per_chunk}"
            )
        if self.args.playback:
            assert self._pa is not None
            self._print_output_device_info(self.args.output_device_index)
            self._open_output_stream()
            self._refresh_aec_output_latency()
        if self.args.aec_enabled:
            self._init_aec_engine()
            print(
                "[aec] enabled "
                f"engine={self._aec_engine} "
                f"effective_engine={self._aec_effective_engine} "
                f"webrtc_backend={self._aec_webrtc_backend or '-'} "
                f"webrtc_post_filter={self.args.aec_webrtc_post_filter} "
                f"ref_delay_ms={self.args.aec_ref_delay_ms} "
                f"ref_buffer_ms={self.args.aec_ref_buffer_ms} "
                f"ref_hold_ms={self.args.aec_ref_hold_ms} "
                f"auto_delay={self.args.aec_auto_delay} "
                f"auto_delay_min_score={self.args.aec_auto_delay_min_score} "
                f"search_span_ms={self.args.aec_search_span_ms} "
                f"search_step_ms={self.args.aec_search_step_ms} "
                f"auto_delay_interval_chunks={self.args.aec_auto_delay_interval_chunks} "
                f"echo_gate={self.args.aec_echo_gate} "
                f"tts_warmup_mute_ms={self.args.aec_tts_warmup_mute_ms} "
                f"tts_ref_wait_mute_ms={self.args.aec_tts_ref_wait_mute_ms} "
                f"tts_stale_ms={self.args.aec_tts_stale_ms} "
                f"preserve_barge_in={self.args.aec_preserve_barge_in} "
                f"barge_in_warmup_rms={self.args.aec_barge_in_warmup_rms} "
                f"tts_gate_sim={self.args.aec_tts_echo_gate_sim_threshold} "
                f"tts_gate_clean_sim={self.args.aec_tts_echo_gate_clean_sim_threshold} "
                f"tts_gate_rms_ratio={self.args.aec_tts_echo_gate_rms_ratio} "
                f"tts_half_duplex={self.args.aec_tts_half_duplex} "
                f"tts_barge_in_rms={self.args.aec_tts_barge_in_rms} "
                f"tts_barge_in_ratio={self.args.aec_tts_barge_in_ratio} "
                f"tts_barge_in_sim_max={self.args.aec_tts_barge_in_sim_max} "
                f"tts_barge_in_chunks={self.args.aec_tts_barge_in_chunks} "
                f"tts_barge_in_interrupt={self.args.aec_tts_barge_in_interrupt} "
                f"near_end_protect_ratio={self.args.aec_near_end_protect_ratio} "
                f"use_output_latency={self.args.aec_use_output_latency} "
                f"output_latency_ms={self._aec_output_latency_ms} "
                f"sample_rate={self.args.sample_rate} "
                f"playback_sample_rate={self.args.playback_sample_rate}"
            )
            if self.args.chunk_ms > 40:
                print(
                    "[aec] warning: chunk_ms is large; "
                    "consider 10-20ms for better echo cancellation responsiveness."
                )
        if self.args.transport == "ws":
            self._probe_server_whoami()
            self._connect_websocket()
            if self.args.ws_split_channels:
                self._receiver_control_thread = threading.Thread(
                    target=self._ws_receive_control_loop, daemon=True
                )
                self._receiver_media_thread = threading.Thread(
                    target=self._ws_receive_media_loop, daemon=True
                )
                self._receiver_control_thread.start()
                self._receiver_media_thread.start()
            else:
                self._receiver_thread = threading.Thread(target=self._ws_receive_loop, daemon=True)
                self._receiver_thread.start()
        elif self.args.transport == "asrws":
            self._connect_asr_websocket()
            self._receiver_thread = threading.Thread(target=self._asr_receive_loop, daemon=True)
            self._receiver_thread.start()

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self._capture_thread.start()
        self._sender_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.args.transport == "ws":
            self._send_dialog_control_event("end_dialog", "缁撴潫瀵硅瘽")
            if self.args.ws_split_channels:
                if self._ws_control is not None:
                    try:
                        with self._ws_control_send_lock:
                            self._ws_control.send(json.dumps({"event": "stop"}))
                    except Exception:
                        pass
                if self._ws_media is not None:
                    try:
                        self._ws_media.close()
                    except Exception:
                        pass
                if self._ws_control is not None:
                    try:
                        self._ws_control.close()
                    except Exception:
                        pass
            elif self._ws is not None:
                try:
                    with self._ws_send_lock:
                        self._ws.send(json.dumps({"event": "stop"}))
                except Exception:
                    pass
                try:
                    self._ws.close()
                except Exception:
                    pass
        elif self.args.transport == "asrws":
            if self._ws is not None:
                try:
                    with self._ws_send_lock:
                        self._ws.send_binary(self._build_asr_audio_request(self._asr_seq, b"", is_last=True))
                except Exception:
                    pass
                try:
                    self._ws.close()
                except Exception:
                    pass
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2)
        if self._sender_thread is not None:
            self._sender_thread.join(timeout=5)
        if self._receiver_thread is not None:
            self._receiver_thread.join(timeout=2)
        if self._receiver_control_thread is not None:
            self._receiver_control_thread.join(timeout=2)
        if self._receiver_media_thread is not None:
            self._receiver_media_thread.join(timeout=2)

        if self._input_stream is not None:
            self._input_stream.stop_stream()
            self._input_stream.close()
        if self._output_stream is not None:
            self._wait_playback_drain()
            self._output_stream.stop_stream()
            self._output_stream.close()
        if self._pa is not None:
            self._pa.terminate()

    def _open_output_stream(self) -> None:
        if not self.args.playback:
            return
        if self._pa is None:
            return
        output_kwargs = dict(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.args.playback_sample_rate,
            output=True,
            frames_per_buffer=1024,
        )
        if self.args.output_device_index is not None:
            output_kwargs["output_device_index"] = self.args.output_device_index
        self._output_stream = self._pa.open(**output_kwargs)
        self._output_stream.start_stream()

    def _interrupt_playback(self) -> None:
        # Clear already buffered audio so user barge-in can be heard immediately.
        self._play_frames_written = 0
        self._play_first_frame_at = 0.0
        if self._output_stream is None:
            return
        try:
            self._output_stream.stop_stream()
        except Exception:
            pass
        try:
            self._output_stream.close()
        except Exception:
            pass
        self._output_stream = None
        try:
            self._open_output_stream()
            self._refresh_aec_output_latency()
        except Exception as exc:
            print(f"[ws/tts] reopen playback stream failed after interrupt: {exc}")

    def _enqueue_audio(self, data: bytes) -> None:
        if not data:
            return
        try:
            self.audio_queue.put_nowait(data)
        except queue.Full:
            dropped_oldest = False
            try:
                _ = self.audio_queue.get_nowait()
                dropped_oldest = True
                self._queue_drop_oldest += 1
            except queue.Empty:
                pass
            try:
                self.audio_queue.put_nowait(data)
            except queue.Full:
                self._queue_drop_newest += 1
            now = time.monotonic()
            if now >= self._queue_drop_log_deadline:
                self._queue_drop_log_deadline = now + 2.0
                print(
                    "[send/queue] drop "
                    f"dropped_oldest={self._queue_drop_oldest} "
                    f"dropped_newest={self._queue_drop_newest} "
                    f"queue_size={self.audio_queue.qsize()} "
                    f"maxsize={self.audio_queue.maxsize} "
                    f"replaced={dropped_oldest}"
                )

    def _normalize_chunk_bytes(self, data: bytes) -> bytes:
        if len(data) == self.chunk_bytes:
            return data
        if len(data) > self.chunk_bytes:
            return data[: self.chunk_bytes]
        return data + (b"\x00" * (self.chunk_bytes - len(data)))

    def _apply_pcm_gain(self, data: bytes, gain: float) -> bytes:
        if gain == 1.0 or self.bytes_per_sample != 2:
            return data
        out = bytearray(len(data))
        sample_count = len(data) // 2
        for i in range(sample_count):
            off = i * 2
            sample = int.from_bytes(data[off : off + 2], byteorder="little", signed=True)
            scaled = int(sample * gain)
            if scaled > 32767:
                scaled = 32767
            elif scaled < -32768:
                scaled = -32768
            out[off : off + 2] = int(scaled).to_bytes(2, byteorder="little", signed=True)
        return bytes(out)

    def _apply_mic_gain(self, data: bytes) -> bytes:
        return self._apply_pcm_gain(data, self.args.mic_gain)

    def _pcm16_rms(self, data: bytes) -> int:
        if not data or self.bytes_per_sample != 2:
            return 0
        sample_count = len(data) // 2
        if sample_count == 0:
            return 0
        total = 0
        for i in range(sample_count):
            off = i * 2
            sample = int.from_bytes(data[off : off + 2], byteorder="little", signed=True)
            total += sample * sample
        return int(math.sqrt(total / sample_count))

    def _print_input_device_info(self, input_device_index: int | None) -> None:
        assert self._pa is not None
        if input_device_index is None:
            try:
                info = self._pa.get_default_input_device_info()
                idx = int(info.get("index", -1))
                name = info.get("name", "unknown")
                max_channels = int(info.get("maxInputChannels", 0))
                default_rate = int(float(info.get("defaultSampleRate", 0)))
                print(
                    f"[mic] using default input device: index={idx}, "
                    f"name={name}, max_input_channels={max_channels}, default_rate={default_rate}"
                )
            except Exception:
                print("[mic] no explicit input device; PortAudio default input will be used")
            return
        try:
            info = self._pa.get_device_info_by_index(input_device_index)
            name = info.get("name", "unknown")
            max_channels = int(info.get("maxInputChannels", 0))
            default_rate = int(float(info.get("defaultSampleRate", 0)))
            print(
                f"[mic] input_device_index={input_device_index}, "
                f"name={name}, max_input_channels={max_channels}, default_rate={default_rate}"
            )
        except Exception as exc:
            print(f"[mic] failed to query input device {input_device_index}: {exc}")

    def _print_output_device_info(self, output_device_index: int | None) -> None:
        assert self._pa is not None
        if output_device_index is None:
            try:
                info = self._pa.get_default_output_device_info()
                idx = int(info.get("index", -1))
                name = info.get("name", "unknown")
                max_channels = int(info.get("maxOutputChannels", 0))
                default_rate = int(float(info.get("defaultSampleRate", 0)))
                print(
                    f"[spk] using default output device: index={idx}, "
                    f"name={name}, max_output_channels={max_channels}, default_rate={default_rate}"
                )
            except Exception:
                print("[spk] no explicit output device; PortAudio default output will be used")
            return
        try:
            info = self._pa.get_device_info_by_index(output_device_index)
            name = info.get("name", "unknown")
            max_channels = int(info.get("maxOutputChannels", 0))
            default_rate = int(float(info.get("defaultSampleRate", 0)))
            print(
                f"[spk] output_device_index={output_device_index}, "
                f"name={name}, max_output_channels={max_channels}, default_rate={default_rate}"
            )
        except Exception as exc:
            print(f"[spk] failed to query output device {output_device_index}: {exc}")

    def _capture_local_loop(self) -> None:
        pcm_path = Path("output.pcm")
        if not pcm_path.exists():
            print(f"[capture] local mode enabled but file not found: {pcm_path.resolve()}")
            self.stop_event.set()
            return
        print(f"[mic/monitor] local mode active source_file={pcm_path.resolve()}")

        sleep_s = self.args.chunk_ms / 1000.0
        while not self.stop_event.is_set():
            with pcm_path.open("rb") as f:
                while not self.stop_event.is_set():
                    data = f.read(self.chunk_bytes)
                    if not data:
                        break
                    data = self._normalize_chunk_bytes(data)
                    self._enqueue_audio(data)
                    time.sleep(sleep_s)

    def _capture_loop(self) -> None:
        if self.args.local:
            self._capture_local_loop()
            return

        assert self._input_stream is not None
        captured_chunks = 0
        while not self.stop_event.is_set():
            self._maybe_clear_stale_tts_state()
            try:
                # Align with micDemo: positional False == exception_on_overflow=False.
                data = self._input_stream.read(self.frames_per_chunk, False)
            except Exception as exc:
                print(f"[capture] read failed: {exc}")
                continue

            # Keep an opt-in gain knob for debugging; default remains pass-through.
            if self.args.mic_gain != 1.0:
                data = self._apply_mic_gain(data)

            if self.args.aec_enabled:
                if self._should_mute_for_tts_warmup(data):
                    self._aec_barge_in_hits = 0
                    data = b"\x00" * len(data)
                else:
                    ref = self._get_reference_for_mic_chunk(data)
                    if self.args.aec_tts_half_duplex and self._tts_active:
                        if self._is_tts_barge_in(data, ref):
                            self._aec_barge_in_hits += 1
                            if self._aec_barge_in_hits < int(self.args.aec_tts_barge_in_chunks):
                                now = time.monotonic()
                                if now >= self._aec_half_duplex_log_deadline:
                                    self._aec_half_duplex_log_deadline = now + 2.0
                                    print(
                                        "[aec] tts_half_duplex_hold "
                                        f"barge_in_hits={self._aec_barge_in_hits} "
                                        f"need_hits={int(self.args.aec_tts_barge_in_chunks)}"
                                    )
                                data = b"\x00" * len(data)
                            else:
                                now = time.monotonic()
                                if now >= self._aec_half_duplex_log_deadline:
                                    self._aec_half_duplex_log_deadline = now + 2.0
                                    print(
                                        "[aec] tts_barge_in_release "
                                        f"hits={self._aec_barge_in_hits}"
                                    )
                                if self.args.aec_tts_barge_in_interrupt:
                                    self._drop_audio_until_tts_end = True
                                    self._interrupt_playback()
                                self._tts_active = False
                                self._tts_started_at = 0.0
                                self._aec_barge_in_hits = 0
                        else:
                            self._aec_barge_in_hits = 0
                            now = time.monotonic()
                            if now >= self._aec_half_duplex_log_deadline:
                                self._aec_half_duplex_log_deadline = now + 2.0
                                print("[aec] tts_half_duplex_mute")
                            data = b"\x00" * len(data)
                    if any(data):
                        raw_mic_data = data
                        data = self._process_with_webrtc_apm(data)
                        if self.args.aec_webrtc_post_filter:
                            data = self._apply_echo_post_filters(
                                raw_mic_data=raw_mic_data,
                                ref_data=ref,
                                cleaned=data,
                            )

            # Compute RMS once if needed for debug.
            need_rms = self.args.mic_debug_every > 0
            rms = self._pcm16_rms(data) if need_rms else 0

            captured_chunks += 1
            if captured_chunks == 1:
                print(f"[mic/monitor] first_chunk chunk_bytes={len(data)} rms={rms}")
            elif captured_chunks % 100 == 0:
                print(f"[mic/monitor] captured_chunks={captured_chunks} last_chunk_bytes={len(data)} rms={rms}")

            self._enqueue_audio(data)

    def _sender_loop(self) -> None:
        while not self.stop_event.is_set():
            if (
                self._asr_wait_since > 0
                and (not self._asr_first_commit_seen)
                and (not self._asr_wait_warned)
                and (time.monotonic() - self._asr_wait_since >= 8.0)
            ):
                self._asr_wait_warned = True
                wait_ms = int((time.monotonic() - self._asr_wait_since) * 1000)
                print(f"[asr/monitor] waiting_first_commit elapsed_ms={wait_ms}")

            if self.max_chunks is not None and self.chunk_index >= self.max_chunks:
                self.stop_event.set()
                break

            try:
                chunk = self.audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            idx = self.chunk_index
            self.chunk_index += 1

            t0 = time.time()
            try:
                self._send_one_chunk(chunk_index=idx, audio_bytes=chunk)
            except Exception as exc:
                print(f"[send] chunk={idx} failed: {exc}")
            finally:
                dt = (time.time() - t0) * 1000
                should_log_send = dt >= float(self.args.send_slow_ms)
                if (not should_log_send) and self.args.send_debug_every > 0:
                    should_log_send = (idx % int(self.args.send_debug_every)) == 0
                if should_log_send:
                    print(f"[send] chunk={idx} done in {dt:.0f}ms")

    def _send_one_chunk(self, chunk_index: int, audio_bytes: bytes) -> None:
        if self.args.transport == "ws":
            self._send_one_chunk_ws(chunk_index=chunk_index, audio_bytes=audio_bytes)
            return
        if self.args.transport == "asrws":
            self._send_one_chunk_asrws(chunk_index=chunk_index, audio_bytes=audio_bytes)
            return
        self._send_one_chunk_http(chunk_index=chunk_index, audio_bytes=audio_bytes)

    def _send_one_chunk_ws(self, chunk_index: int, audio_bytes: bytes) -> None:
        if self.args.ws_split_channels:
            if self._ws_media is None:
                self._reconnect_ws_media(reason="send")
            ws_media = self._ws_media
            if ws_media is None:
                raise RuntimeError("media websocket is not connected")
            try:
                with self._ws_media_send_lock:
                    current_ws = self._ws_media
                    if current_ws is None:
                        raise RuntimeError("media websocket is not connected")
                    current_ws.send_binary(audio_bytes)
            except WebSocketConnectionClosedException:
                self._drop_ws_media_socket()
                raise RuntimeError("media websocket closed while sending")
        else:
            if self._ws is None:
                raise RuntimeError("websocket is not connected")
            with self._ws_send_lock:
                self._ws.send_binary(audio_bytes)
        self._last_audio_sent_at = time.monotonic()
        if chunk_index % 20 == 0:
            print(f"[ws/send] chunk={chunk_index} bytes={len(audio_bytes)}")

    def _send_one_chunk_asrws(self, chunk_index: int, audio_bytes: bytes) -> None:
        if self._ws is None:
            raise RuntimeError("asr websocket is not connected")
        req = self._build_asr_audio_request(self._asr_seq, audio_bytes, is_last=False)
        with self._ws_send_lock:
            self._ws.send_binary(req)
        self._asr_seq += 1
        if chunk_index % 20 == 0:
            print(f"[asrws/send] chunk={chunk_index} bytes={len(audio_bytes)}")

    def _send_one_chunk_http(self, chunk_index: int, audio_bytes: bytes) -> None:
        params = {
            "session_id": self.session_id,
            "chunk_index": chunk_index,
            "format": self.args.audio_format,
        }
        if self.args.response_mode:
            params["response_mode"] = self.args.response_mode

        with requests.post(
            self.endpoint,
            params=params,
            data=audio_bytes,
            headers={"Content-Type": "application/octet-stream"},
            stream=True,
            timeout=(self.args.connect_timeout, self.args.read_timeout),
        ) as resp:
            if resp.status_code != 200:
                body = resp.text[:500]
                raise RuntimeError(f"status={resp.status_code}, body={body}")

            content_type = (resp.headers.get("content-type") or "").lower()
            if "application/json" in content_type:
                payload = resp.json()
                print(f"[asr] {payload.get('asr_text', '')}")
                return

            audio_total = 0
            audio_buffer = bytearray()
            for part in resp.iter_content(chunk_size=4096):
                if not part:
                    continue
                audio_total += len(part)
                if self._output_stream is not None:
                    self._output_stream.write(part)
                    self._append_playback_reference(part)
                if self._save_dir is not None:
                    audio_buffer.extend(part)

            if self._save_dir is not None and audio_total > 0:
                out_path = self._save_dir / f"{chunk_index:06d}.pcm"
                out_path.write_bytes(audio_buffer)
            print(f"[tts] chunk={chunk_index} audio_bytes={audio_total}")

    def _build_runtime_prompt_payload(self) -> dict[str, Any] | None:
        payload: dict[str, Any] = {"event": "set_system_prompt"}
        prompt_context = self._build_prompt_context_payload()
        if prompt_context:
            payload["prompt_context"] = prompt_context
        if self._runtime_intent_labels:
            payload["intent_labels"] = list(self._runtime_intent_labels)
        if self._runtime_intent_fallback_label:
            payload["fallback_label"] = self._runtime_intent_fallback_label
        if len(payload) <= 1:
            return None
        return payload

    def _push_runtime_prompt_if_needed(self, trigger: str) -> None:
        if self.args.transport != "ws":
            return
        if self._runtime_prompt_pushed:
            return
        payload = self._build_runtime_prompt_payload()
        if payload is None:
            return
        wire = json.dumps(payload, ensure_ascii=False)
        try:
            if self.args.ws_split_channels:
                if self._ws_control is None:
                    return
                with self._ws_control_send_lock:
                    self._ws_control.send(wire)
            else:
                if self._ws is None:
                    return
                with self._ws_send_lock:
                    self._ws.send(wire)
            self._runtime_prompt_pushed = True
            workflow_nodes, workflow_edges = self._workflow_graph_stats(self._runtime_workflow_json)
            prompt_context = payload.get("prompt_context")
            if isinstance(prompt_context, dict):
                prompt_context_keys = ",".join(sorted(prompt_context.keys()))
            else:
                prompt_context_keys = ""
            print(
                f"[ws/control] set_system_prompt sent trigger={trigger} "
                f"chars={len(str(payload.get('system_prompt', '')))} "
                f"prompt_context={'on' if isinstance(prompt_context, dict) else 'off'} "
                f"prompt_context_keys={prompt_context_keys} "
                f"workflow_json={'on' if isinstance(prompt_context, dict) and ('workflow_json' in prompt_context) else 'off'} "
                f"nodes={workflow_nodes} edges={workflow_edges}"
            )
        except Exception as exc:
            print(f"[ws/control] set_system_prompt send failed trigger={trigger}: {exc}")

    def _send_dialog_control_event(self, event_name: str, trigger_text: str) -> None:
        if self.args.transport != "ws":
            return
        payload = {
            "event": str(event_name or "").strip(),
            "text": str(trigger_text or "").strip(),
            "trigger_text": str(trigger_text or "").strip(),
        }
        wire = json.dumps(payload, ensure_ascii=False)
        try:
            if self.args.ws_split_channels:
                if self._ws_control is None:
                    return
                with self._ws_control_send_lock:
                    self._ws_control.send(wire)
            else:
                if self._ws is None:
                    return
                with self._ws_send_lock:
                    self._ws.send(wire)
            print(f"[ws/control] {event_name} sent text={trigger_text}")
        except Exception as exc:
            print(f"[ws/control] {event_name} send failed: {exc}")

    def _connect_websocket(self) -> None:
        if websocket is None:
            raise RuntimeError("websocket-client is required for --transport ws")
        if self.args.ws_split_channels:
            try:
                self._ws_control = websocket.create_connection(
                    self.ws_control_endpoint,
                    timeout=self.args.connect_timeout,
                    enable_multithread=True,
                )
                self._ws_control.settimeout(1.0)
                self._ws_media = websocket.create_connection(
                    self.ws_media_endpoint,
                    timeout=self.args.connect_timeout,
                    enable_multithread=True,
                )
                self._ws_media.settimeout(1.0)
            except Exception:
                if self._ws_control is not None:
                    try:
                        self._ws_control.close()
                    except Exception:
                        pass
                    self._ws_control = None
                if self._ws_media is not None:
                    try:
                        self._ws_media.close()
                    except Exception:
                        pass
                    self._ws_media = None
                raise
            print(f"[ws] connected(control): {self.ws_control_endpoint}")
            print(f"[ws] connected(media):   {self.ws_media_endpoint}")
            return
        self._ws = websocket.create_connection(
            self.ws_endpoint,
            timeout=self.args.connect_timeout,
            enable_multithread=True,
        )
        self._ws.settimeout(1.0)
        print(f"[ws] connected: {self.ws_endpoint}")

    def _drop_ws_media_socket(self) -> None:
        ws_media = None
        with self._ws_media_send_lock:
            if self._ws_media is not None:
                ws_media = self._ws_media
                self._ws_media = None
        if ws_media is not None:
            try:
                ws_media.close()
            except Exception:
                pass

    def _reconnect_ws_media(self, reason: str = "") -> bool:
        if (not self.args.ws_split_channels) or websocket is None:
            return False
        now = time.monotonic()
        if now < self._ws_media_reconnect_deadline:
            return False
        retry_sec = max(0.2, float(self.args.ws_media_reconnect_interval_sec))
        self._ws_media_reconnect_deadline = now + retry_sec
        try:
            new_ws = websocket.create_connection(
                self.ws_media_endpoint,
                timeout=self.args.connect_timeout,
                enable_multithread=True,
            )
            new_ws.settimeout(1.0)
        except Exception as exc:
            print(f"[ws/media] reconnect failed reason={reason or '-'}: {exc}")
            return False

        old_ws = None
        with self._ws_media_send_lock:
            old_ws = self._ws_media
            self._ws_media = new_ws
        if old_ws is not None:
            try:
                old_ws.close()
            except Exception:
                pass
        self._ws_media_reconnect_deadline = 0.0
        print(f"[ws/media] reconnected reason={reason or '-'}")
        return True

    def _connect_asr_websocket(self) -> None:
        if websocket is None:
            raise RuntimeError("websocket-client is required for --transport asrws")
        headers = self._new_asr_auth_headers()
        print(f"[asrws] connecting: {self.asr_ws_endpoint}")
        self._ws = websocket.create_connection(
            self.asr_ws_endpoint,
            timeout=self.args.connect_timeout,
            header=headers,
            enable_multithread=True,
        )
        self._ws.settimeout(1.0)
        print(f"[ws] connected: {self.asr_ws_endpoint}")

        self._asr_seq = 1
        full_req = self._build_asr_full_request(self._asr_seq)
        with self._ws_send_lock:
            self._ws.send_binary(full_req)
        self._asr_seq += 1

        print("[asrws] waiting ack")
        try:
            ack = self._ws.recv()
        except Exception as exc:
            raise RuntimeError(f"failed to receive asr ack: {exc}") from exc
        if not isinstance(ack, bytes):
            raise RuntimeError("invalid asr ack: non-binary response")
        parsed = self._parse_asr_response(ack)
        if int(parsed.get("code", 0)) != 0:
            raise RuntimeError(f"asr ack error code={parsed.get('code')} event={parsed.get('event')}")
        print("[asrws] ack ok")

        print(f"[ws/ready] session_id={self.session_id}")
        self._asr_wait_since = time.monotonic()
        self._asr_first_commit_seen = False
        self._asr_wait_warned = False
        print(
            f"[asr/monitor] ready session_id={self.session_id} "
            f"sample_rate={self.args.sample_rate}"
        )

    def _asr_receive_loop(self) -> None:
        if self._ws is None:
            return
        while not self.stop_event.is_set():
            try:
                message = self._ws.recv()
            except WebSocketTimeoutException:
                continue
            except WebSocketConnectionClosedException:
                break
            except Exception as exc:
                if not self.stop_event.is_set():
                    print(f"[asrws/recv] failed: {exc}")
                break

            if not isinstance(message, bytes):
                text = str(message).strip()
                if text:
                    print(f"[asrws/event] {text}")
                continue

            try:
                parsed = self._parse_asr_response(message)
            except Exception as exc:
                print(f"[asrws/recv] parse failed: {exc}")
                continue

            code = int(parsed.get("code", 0))
            if code != 0:
                print(f"[asr/error] code={code} event={parsed.get('event')}")
                continue

            text_value = self._extract_asr_text(parsed.get("payload_msg"))
            if not text_value:
                continue
            if (not self._asr_first_commit_seen) and self._asr_wait_since > 0:
                self._asr_first_commit_seen = True
                elapsed_ms = int((time.monotonic() - self._asr_wait_since) * 1000)
                print(f"[asr/monitor] first_commit elapsed_ms={elapsed_ms}")
            print(f"[asr] {text_value}")

        if not self.stop_event.is_set():
            print("[asrws] server disconnected")
            self.stop_event.set()

    def _ws_receive_loop(self) -> None:
        if self._ws is None:
            return
        while not self.stop_event.is_set():
            try:
                message = self._ws.recv()
            except WebSocketTimeoutException:
                continue
            except WebSocketConnectionClosedException:
                break
            except Exception as exc:
                if not self.stop_event.is_set():
                    print(f"[ws/recv] failed: {exc}")
                break

            if isinstance(message, bytes):
                self._handle_ws_audio(message)
                continue
            self._handle_ws_text(str(message))

        if not self.stop_event.is_set():
            self._log_ws_disconnect(channel="single", reason="server_disconnected")
            self.stop_event.set()

    def _ws_receive_control_loop(self) -> None:
        if self._ws_control is None:
            return
        while not self.stop_event.is_set():
            try:
                message = self._ws_control.recv()
            except WebSocketTimeoutException:
                continue
            except WebSocketConnectionClosedException:
                break
            except Exception as exc:
                if not self.stop_event.is_set():
                    print(f"[ws/control] recv failed: {exc}")
                break

            if isinstance(message, bytes):
                try:
                    self._handle_ws_text(message.decode("utf-8", errors="ignore"))
                except Exception:
                    pass
                continue
            self._handle_ws_text(str(message))

        if not self.stop_event.is_set():
            self._log_ws_disconnect(channel="control", reason="server_disconnected")
            self.stop_event.set()

    def _log_ws_disconnect(self, *, channel: str, reason: str) -> None:
        cause: dict[str, object] | None = None
        with self._terminate_cause_lock:
            if self._pending_terminate_cause is not None:
                cause = dict(self._pending_terminate_cause)
                self._pending_terminate_cause = None
        if cause is None:
            print(f"[ws/{channel}] server disconnected")
            print(
                "[ws/disconnect] "
                + json.dumps(
                    {
                        "channel": channel,
                        "reason": reason,
                        "cause": "unknown",
                    },
                    ensure_ascii=False,
                )
            )
            return
        print(
            "[ws/disconnect] "
            + json.dumps(
                {
                    "channel": channel,
                    "reason": reason,
                    "cause": "terminate_session",
                    **cause,
                },
                ensure_ascii=False,
            )
        )

    def _ws_receive_media_loop(self) -> None:
        while not self.stop_event.is_set():
            if self._ws_media is None:
                if not self._reconnect_ws_media(reason="recv"):
                    time.sleep(max(0.05, float(self.args.ws_media_reconnect_interval_sec)))
                    continue
            try:
                ws_media = self._ws_media
                if ws_media is None:
                    continue
                message = ws_media.recv()
            except WebSocketTimeoutException:
                continue
            except WebSocketConnectionClosedException:
                self._drop_ws_media_socket()
                if not self.stop_event.is_set():
                    print("[ws/media] disconnected, trying reconnect")
                continue
            except Exception as exc:
                self._drop_ws_media_socket()
                if not self.stop_event.is_set():
                    print(f"[ws/media] recv failed: {exc}; trying reconnect")
                continue

            if isinstance(message, bytes):
                self._handle_ws_audio(message)
                continue
            self._handle_ws_text(str(message))

    def _handle_ws_audio(self, audio: bytes) -> None:
        if not audio:
            return
        if self._drop_audio_until_tts_end:
            return
        if not self._tts_active:
            self._tts_active = True
            if self._tts_started_at <= 0:
                self._tts_started_at = time.monotonic()
            self._aec_barge_in_hits = 0
        self._ws_audio_frame_count += 1
        self._ws_audio_total_bytes += len(audio)
        if self._ws_audio_frame_count == 1:
            print(f"[ws/tts] first_frame_bytes={len(audio)}")
            # End-to-end latency: last audio frame sent -> first TTS frame received.
            if self._last_audio_sent_at > 0:
                e2e_ms = int((time.monotonic() - self._last_audio_sent_at) * 1000)
                print(f"[latency] e2e_ms={e2e_ms}  (upload+backend+download)")
        if self._output_stream is not None:
            if self._play_first_frame_at <= 0:
                self._play_first_frame_at = time.monotonic()
            self._output_stream.write(audio)
            self._play_frames_written += len(audio) // 2  # PCM16 mono
            self._append_playback_reference(audio)
        elif self._ws_audio_frame_count == 1:
            print("[ws/tts] playback is disabled; start with --playback to hear audio")
        if self._save_dir is not None:
            out_path = self._save_dir / f"ws_{self._ws_audio_frame_count:06d}.pcm"
            out_path.write_bytes(audio)
        if self._ws_audio_frame_count % 50 == 0:
            print(
                f"[ws/tts] frames={self._ws_audio_frame_count}, "
                f"total_audio_bytes={self._ws_audio_total_bytes}"
            )

    def _wait_playback_drain(self, extra_pad_sec: float = 0.02) -> None:
        if self._output_stream is None:
            return
        if self._play_frames_written <= 0 or self._play_first_frame_at <= 0:
            return
        total = self._play_frames_written / float(self.args.playback_sample_rate)
        elapsed = max(0.0, time.monotonic() - self._play_first_frame_at)
        try:
            out_lat = float(self._output_stream.get_output_latency() or 0.0)
        except Exception:
            out_lat = 0.0
        remain = max(0.0, total - elapsed)
        wait_more = remain + max(0.0, out_lat) + max(0.0, extra_pad_sec)
        if wait_more > 0:
            time.sleep(wait_more)
        self._play_frames_written = 0
        self._play_first_frame_at = 0.0

    def _handle_ws_text(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        try:
            payload = json.loads(text)
        except Exception:
            print(f"[ws/event] {text}")
            return
        event = str(payload.get("event", "")).strip().lower()
        if event == "ready":
            session_id = payload.get("session_id")
            print(f"[ws/ready] session_id={session_id}")
            self._asr_wait_since = time.monotonic()
            self._asr_first_commit_seen = False
            self._asr_wait_warned = False
            self._push_runtime_prompt_if_needed(trigger="ready")
            if (not self.args.skip_auto_start_dialog) and (not self._start_dialog_sent):
                self._send_dialog_control_event("start_dialog", "开始对话")
                self._start_dialog_sent = True
            print(
                f"[asr/monitor] ready session_id={session_id} "
                f"sample_rate={payload.get('asr_sample_rate', '-')}"
            )
            return
        if event in {"asr_commit", "asr", "asr_result", "asr_final", "asr_text", "asr_partial"}:
            text_value = payload.get("text", "")
            if not text_value:
                text_value = payload.get("asr_text", "")
            if not text_value and isinstance(payload.get("result"), dict):
                text_value = payload["result"].get("text", "")
            cmd = payload.get("command")
            if (not self._asr_first_commit_seen) and self._asr_wait_since > 0:
                self._asr_first_commit_seen = True
                elapsed_ms = int((time.monotonic() - self._asr_wait_since) * 1000)
                print(f"[asr/monitor] first_commit elapsed_ms={elapsed_ms}")
            is_commit = event in {"asr_commit", "asr_final"}
            asr_prefix = "[asr]" if is_commit else "[asr/partial]"
            if cmd:
                print(f"{asr_prefix} {text_value} (command={cmd})")
            else:
                print(f"{asr_prefix} {text_value}")
            if is_commit:
                if text_value:
                    print(f"[latency/asr] | {text_value}")
            return
        if event == "command":
            command = str(payload.get("command", "") or "")
            action = str(payload.get("action", "") or "")
            terminate_source = str(payload.get("terminate_source", "") or "")
            terminate_reason = str(payload.get("terminate_reason", "") or "")
            terminate_trace_id = str(payload.get("terminate_trace_id", "") or "")
            terminate_by = str(payload.get("terminate_by", "") or "")
            trigger_text = str(payload.get("trigger_text", "") or "")
            if action == "terminate_session":
                with self._terminate_cause_lock:
                    self._pending_terminate_cause = {
                        "command": command,
                        "action": action,
                        "terminate_source": terminate_source,
                        "terminate_reason": terminate_reason,
                        "terminate_trace_id": terminate_trace_id,
                        "terminate_by": terminate_by,
                        "trigger_text": trigger_text,
                    }
                print(
                    "[ws/terminate] "
                    + json.dumps(
                        {
                            "command": command,
                            "action": action,
                            "terminate_source": terminate_source,
                            "terminate_reason": terminate_reason,
                            "terminate_trace_id": terminate_trace_id,
                            "terminate_by": terminate_by,
                            "trigger_text": trigger_text,
                            "server_ts": payload.get("server_ts"),
                        },
                        ensure_ascii=False,
                    )
                )
                # Server explicitly asked to terminate this dialog session:
                # stop capture/upload loops immediately instead of waiting for manual stop.
                if not self.stop_event.is_set():
                    self.stop_event.set()
                    if self.args.transport == "ws":
                        if self.args.ws_split_channels:
                            if self._ws_media is not None:
                                try:
                                    self._ws_media.close()
                                except Exception:
                                    pass
                            if self._ws_control is not None:
                                try:
                                    self._ws_control.close()
                                except Exception:
                                    pass
                        elif self._ws is not None:
                            try:
                                self._ws.close()
                            except Exception:
                                pass
                    print("[ws/terminate] stop_event set by server terminate_session")
            print(
                f"[ws/command] command={command} "
                f"action={action} "
                f"terminate_source={terminate_source} "
                f"terminate_reason={terminate_reason} "
                f"terminate_trace_id={terminate_trace_id} "
                f"workflow_applied={payload.get('workflow_applied')} "
                f"workflow_nodes={payload.get('workflow_nodes')} "
                f"workflow_edges={payload.get('workflow_edges')}"
            )
            return
        if event == "billing_started":
            print(
                "[billing/start] "
                + json.dumps(
                    {
                        "session_id": str(payload.get("session_id", "") or ""),
                        "source": str(payload.get("source", "") or ""),
                        "trigger_text": str(payload.get("trigger_text", "") or ""),
                        "started_at": payload.get("started_at"),
                    },
                    ensure_ascii=False,
                )
            )
            return
        if event == "billing_result":
            print(
                "[billing/result] "
                + json.dumps(payload, ensure_ascii=False)
            )
            return
        if event == "tts_start":
            self._drop_audio_until_tts_end = False
            self._tts_active = True
            self._tts_started_at = time.monotonic()
            self._tts_last_segment_at = self._tts_started_at
            self._tts_interrupted_recent = False
            self._tts_latency_emitted = False
            self._aec_barge_in_hits = 0
            print(f"[tts] start text={payload.get('text', '')}")
            return
        if event == "nlp_prompt":
            print(
                f"[nlp/prompt] mode={payload.get('mode', '')} "
                f"text={payload.get('text', '')}"
            )
            return
        if event == "intent_result":
            text_value = str(payload.get("text", "") or "")
            intents_value = payload.get("intents", [])
            intents: list[str] = []
            if isinstance(intents_value, list):
                intents = [str(item).strip() for item in intents_value if str(item).strip()]
            elif intents_value is not None:
                item = str(intents_value).strip()
                if item:
                    intents = [item]
            print(
                "[intent] "
                + json.dumps(
                    {
                        "text": text_value,
                        "intents": intents,
                        "model": str(payload.get("model", "") or ""),
                    },
                    ensure_ascii=False,
                )
            )
            return
        if event == "intent_prompt":
            print(
                "[intent/prompt] "
                + json.dumps(
                    {
                        "text": str(payload.get("text", "") or ""),
                        "prompt": str(payload.get("prompt", "") or ""),
                        "model": str(payload.get("model", "") or ""),
                    },
                    ensure_ascii=False,
                )
            )
            return
        if event == "workflow_progress":
            advanced_value = payload.get("advanced", False)
            if isinstance(advanced_value, str):
                advanced_flag = advanced_value.strip().lower() in {"1", "true", "yes", "y"}
            else:
                advanced_flag = bool(advanced_value)
            try:
                workflow_nodes = int(payload.get("workflow_nodes", 0) or 0)
            except Exception:
                workflow_nodes = 0
            try:
                workflow_edges = int(payload.get("workflow_edges", 0) or 0)
            except Exception:
                workflow_edges = 0
            print(
                "[workflow] "
                + json.dumps(
                    {
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
                        "advanced": advanced_flag,
                        "intents": payload.get("intents", []),
                        "intent_labels": payload.get("intent_labels", []),
                        "workflow_nodes": workflow_nodes,
                        "workflow_edges": workflow_edges,
                    },
                    ensure_ascii=False,
                )
            )
            return
        if event == "tts_segment":
            self._tts_last_segment_at = time.monotonic()
            print(
                f"[tts/segment] seq={payload.get('seq', 0)} "
                f"text={payload.get('text', '')}"
            )
            return
        if event == "assistant_text":
            print(f"[assistant] {payload.get('text', '')}")
            return
        if event == "tts_interrupted":
            self._drop_audio_until_tts_end = True
            self._tts_active = False
            self._tts_started_at = 0.0
            self._tts_last_segment_at = 0.0
            self._aec_barge_in_hits = 0
            if not self._tts_interrupted_recent:
                self._interrupt_playback()
            self._tts_interrupted_recent = True
            print(
                f"[tts] interrupted trigger={payload.get('trigger', '')} "
                f"text={payload.get('text', '')}"
            )
            return
        if event == "tts_latency":
            latency = payload.get("latency")
            if isinstance(latency, dict):
                print(
                    f"[latency/backend] "
                    f"queue_wait_ms={latency.get('queue_wait_ms')} "
                    f"nlp_first_token_ms={latency.get('nlp_first_token_ms')} "
                    f"tts_first_audio_ms={latency.get('tts_first_audio_ms')}",
                    flush=True,
                )
                self._tts_latency_emitted = True
            else:
                print(f"[latency/backend] raw payload={payload!r}", flush=True)
            return
        if event == "tts_end":
            interrupted = payload.get("interrupted", False)
            if isinstance(interrupted, str):
                interrupted = interrupted.strip().lower() in ("1", "true", "yes", "y")
            else:
                interrupted = bool(interrupted)
            self._drop_audio_until_tts_end = False
            self._tts_active = False
            self._tts_started_at = 0.0
            self._tts_last_segment_at = 0.0
            self._aec_barge_in_hits = 0
            if interrupted and (not self._tts_interrupted_recent):
                self._interrupt_playback()
            self._tts_interrupted_recent = False
            print(
                f"[tts] end audio_bytes={payload.get('audio_bytes', 0)} "
                f"interrupted={interrupted}"
            )
            return
        if event == "error":
            print(f"[ws/error] {payload.get('message', '')}")
            return
        print(f"[ws/event] {payload}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mic chunk client for realtime ASR/TTS")
    parser.add_argument(
        "--server-env",  
        default="local",#local|public
        choices=["local", "public"],
        help="Server environment preset: local (127.0.0.1) or public (閸忣剛缍夌純鎴濆彠)",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Override server base URL directly; if empty, use --server-env preset URL",
    )
    parser.add_argument(
        "--local-base-url",
        default="http://127.0.0.1:8080",
        help="Local preset base URL",
    )
    parser.add_argument(
        "--public-base-url",
        default="https://sd66afouoqou1cki04eng.apigateway-cn-beijing.volceapi.com/",
        help="Public preset base URL",
    )
    parser.add_argument(
        "--transport",
        default="ws",
        choices=["ws", "http", "asrws"],
        help="Transport protocol: ws/http for gateway mode, asrws for direct ASR websocket mode",
    )
    parser.add_argument(
        "--ws-split-channels",
        dest="ws_split_channels",
        action="store_true",
        default=True,
        help="Use dual websocket channels: control(text) + media(binary).",
    )
    parser.add_argument(
        "--ws-single-channel",
        dest="ws_split_channels",
        action="store_false",
        help="Use single websocket channel (/ws/realtime/audio).",
    )
    parser.add_argument(
        "--ws-control-path",
        default="/ws/realtime/control",
        help="Control websocket endpoint path (text events/commands).",
    )
    parser.add_argument(
        "--ws-media-path",
        default="/ws/realtime/media",
        help="Media websocket endpoint path (binary audio).",
    )
    parser.add_argument(
        "--ws-path",
        default="/ws/realtime/audio",
        help="Single websocket endpoint path (used with --ws-single-channel).",
    )
    parser.add_argument(
        "--ws-media-reconnect-interval-sec",
        type=float,
        default=1.0,
        help="Retry interval for media websocket reconnect in split-channel mode",
    )
    parser.add_argument(
        "--skip-auto-start-dialog",
        action="store_true",
        help="Do not auto-send start_dialog on ready event",
    )
    parser.add_argument(
        "--asr-ws-url",
        default=os.getenv("ASR_WS_URL", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"),
        help="Direct ASR websocket url (used with --transport asrws).",
    )
    parser.add_argument(
        "--asr-app-key",
        default=os.getenv("ASR_APP_KEY", "3339811743"),
        help="Direct ASR app key (used with --transport asrws).",
    )
    parser.add_argument(
        "--asr-access-key",
        default=os.getenv("ASR_ACCESS_KEY", "blE2xMz0L7odR1jXt-AOiFx98tUwhs4G"),
        help="Direct ASR access key (used with --transport asrws).",
    )
    parser.add_argument(
        "--asr-language",
        default=os.getenv("ASR_LANGUAGE", "zh-CN"),
        help="Direct ASR language (used with --transport asrws).",
    )
    parser.add_argument(
        "--asr-end-window-size",
        type=int,
        default=int(os.getenv("ASR_END_WINDOW_SIZE", "200")),
        help="Direct ASR end window size.",
    )
    parser.add_argument(
        "--asr-force-to-speech-time",
        type=int,
        default=int(os.getenv("ASR_FORCE_TO_SPEECH_TIME", "100")),
        help="Direct ASR force_to_speech_time.",
    )
    parser.add_argument("--session-id", default="", help="Custom session id")
    parser.add_argument("--audio-format", default="pcm", help="Audio format query parameter")
    parser.add_argument(
        "--response-mode",
        default="stream_audio",
        choices=["stream_audio", "json"],
        help="Response mode for server endpoint",
    )

    parser.add_argument("--sample-rate", type=int, default=16000, help="Mic sample rate")
    parser.add_argument(
        "--chunk-ms",
        type=int,
        default=20,
        help="Chunk duration in milliseconds; 10-20ms is recommended for AEC responsiveness",
    )
    parser.add_argument(
        "--queue-size",
        type=int,
        default=128,
        help="Capture queue size in chunks (20ms per chunk, default keeps ~2.56s of audio)",
    )
    parser.add_argument("--max-chunks", type=int, default=None, help="Stop automatically after N chunks")
    parser.add_argument(
        "--local",
        action="store_true",
        default=False,
        help="Read local ./output.pcm in a loop and send chunks instead of recording from mic",
    )
    parser.add_argument("--input-device-index", type=int, default=None, help="Optional input device index")
    parser.add_argument("--output-device-index", type=int, default=None, help="Optional output device index")
    parser.add_argument(
        "--list-input-devices",
        action="store_true",
        default=False,
        help="List available input devices and exit",
    )
    parser.add_argument(
        "--list-output-devices",
        action="store_true",
        default=False,
        help="List available output devices and exit",
    )
    parser.add_argument(
        "--mic-gain",
        type=float,
        default=1.0,
        help="Linear gain multiplier for mic PCM before sending (1.0 means unchanged)",
    )
    parser.add_argument(
        "--mic-debug-every",
        type=int,
        default=0,
        help="Print mic RMS every N captured chunks (0 disables)",
    )
    parser.add_argument(
        "--send-debug-every",
        type=int,
        default=20,
        help="Print per-chunk send latency every N chunks (0 disables periodic send logs)",
    )
    parser.add_argument(
        "--send-slow-ms",
        type=float,
        default=25.0,
        help="Always print per-chunk send latency when it exceeds this threshold (milliseconds)",
    )
    parser.add_argument(
        "--aec",
        dest="aec_enabled",
        action="store_true",
        default=True,
        help="Enable reference-based acoustic echo cancellation (default on)",
    )
    parser.add_argument(
        "--no-aec",
        dest="aec_enabled",
        action="store_false",
        help="Disable reference-based acoustic echo cancellation",
    )
    parser.add_argument(
        "--aec-engine",
        choices=["webrtc"],
        default="webrtc",
        help="AEC engine: webrtc (APM/AEC3-style)",
    )
    parser.add_argument(
        "--aec-webrtc-required",
        dest="aec_webrtc_required",
        action="store_true",
        default=True,
        help="Fail startup if WebRTC APM backend is unavailable",
    )
    parser.add_argument(
        "--aec-webrtc-ns",
        dest="aec_webrtc_ns",
        action="store_true",
        default=True,
        help="Enable NS in WebRTC APM backend when supported",
    )
    parser.add_argument(
        "--no-aec-webrtc-ns",
        dest="aec_webrtc_ns",
        action="store_false",
        help="Disable NS in WebRTC APM backend",
    )
    parser.add_argument(
        "--aec-webrtc-agc",
        dest="aec_webrtc_agc",
        action="store_true",
        default=False,
        help="Enable AGC in WebRTC APM backend when supported",
    )
    parser.add_argument(
        "--no-aec-webrtc-agc",
        dest="aec_webrtc_agc",
        action="store_false",
        help="Disable AGC in WebRTC APM backend",
    )
    parser.add_argument(
        "--aec-webrtc-aec-type",
        type=int,
        default=1,
        help="AEC mode hint passed to WebRTC backend when supported (backend-specific meaning)",
    )
    parser.add_argument(
        "--aec-webrtc-post-filter",
        dest="aec_webrtc_post_filter",
        action="store_true",
        default=False,
        help="Apply post echo-gate filters after WebRTC APM capture processing",
    )
    parser.add_argument(
        "--no-aec-webrtc-post-filter",
        dest="aec_webrtc_post_filter",
        action="store_false",
        help="Do not apply post-filters on WebRTC APM output",
    )
    parser.add_argument(
        "--aec-ref-delay-ms",
        type=int,
        default=120,
        help="Reference delay relative to mic capture, in milliseconds",
    )
    parser.add_argument(
        "--aec-ref-buffer-ms",
        type=int,
        default=500,
        help="Reference history ring buffer size, in milliseconds",
    )
    parser.add_argument(
        "--aec-ref-hold-ms",
        type=int,
        default=250,
        help="How long reference remains valid after playback stops, in milliseconds",
    )
    parser.add_argument(
        "--aec-ref-min-rms",
        type=float,
        default=400.0,
        help="Minimum reference RMS required before cancellation is applied",
    )
    parser.add_argument(
        "--aec-max-suppress-gain",
        type=float,
        default=2.4,
        help="Upper bound for adaptive echo suppression gain",
    )
    parser.add_argument(
        "--aec-adapt-alpha",
        type=float,
        default=0.35,
        help="Smoothing factor for adaptive suppression gain in [0,1]",
    )
    parser.add_argument(
        "--aec-auto-delay",
        dest="aec_auto_delay",
        action="store_true",
        default=True,
        help="Enable dynamic search around configured delay to track echo path drift",
    )
    parser.add_argument(
        "--no-aec-auto-delay",
        dest="aec_auto_delay",
        action="store_false",
        help="Disable dynamic AEC delay search",
    )
    parser.add_argument(
        "--aec-search-span-ms",
        type=int,
        default=260,
        help="Delay search range on each side of current AEC delay (milliseconds)",
    )
    parser.add_argument(
        "--aec-search-step-ms",
        type=int,
        default=5,
        help="Delay search step size (milliseconds)",
    )
    parser.add_argument(
        "--aec-auto-delay-min-score",
        type=float,
        default=0.22,
        help="Minimum correlation score required before auto-delay is allowed to update",
    )
    parser.add_argument(
        "--aec-auto-delay-interval-chunks",
        type=int,
        default=4,
        help="Run auto-delay search once every N chunks to reduce CPU cost",
    )
    parser.add_argument(
        "--aec-use-output-latency",
        dest="aec_use_output_latency",
        action="store_true",
        default=True,
        help="Include output device latency into effective AEC reference delay",
    )
    parser.add_argument(
        "--no-aec-use-output-latency",
        dest="aec_use_output_latency",
        action="store_false",
        help="Do not include output device latency into AEC reference delay",
    )
    parser.add_argument(
        "--aec-echo-gate",
        dest="aec_echo_gate",
        action="store_true",
        default=True,
        help="Enable hard gate: replace echo-dominant chunks with silence before upload",
    )
    parser.add_argument(
        "--no-aec-echo-gate",
        dest="aec_echo_gate",
        action="store_false",
        help="Disable hard echo gate",
    )
    parser.add_argument(
        "--aec-echo-gate-sim-threshold",
        type=float,
        default=0.78,
        help="Raw mic/reference similarity threshold for hard echo gate",
    )
    parser.add_argument(
        "--aec-echo-gate-clean-sim-threshold",
        type=float,
        default=0.62,
        help="Post-AEC similarity threshold for hard echo gate",
    )
    parser.add_argument(
        "--aec-echo-gate-rms-ratio",
        type=float,
        default=0.90,
        help="Hard gate trigger ratio: cleaned_rms <= ref_rms * ratio",
    )
    parser.add_argument(
        "--aec-tts-warmup-mute-ms",
        type=int,
        default=120,
        help="Mute mic for a short warmup window after tts_start before reference ring is ready",
    )
    parser.add_argument(
        "--aec-tts-ref-wait-mute-ms",
        type=int,
        default=2200,
        help="When no playback reference frame has arrived yet, keep mic muted up to this duration",
    )
    parser.add_argument(
        "--aec-tts-stale-ms",
        type=int,
        default=900,
        help="Auto-clear TTS-active state if no new playback reference arrives for this long",
    )
    parser.add_argument(
        "--aec-preserve-barge-in",
        dest="aec_preserve_barge_in",
        action="store_true",
        default=True,
        help="Prioritize user barge-in during TTS by avoiding hard AEC mute gates",
    )
    parser.add_argument(
        "--no-aec-preserve-barge-in",
        dest="aec_preserve_barge_in",
        action="store_false",
        help="Disable barge-in priority and allow hard AEC mute gates during TTS",
    )
    parser.add_argument(
        "--aec-barge-in-warmup-rms",
        type=float,
        default=900.0,
        help="When preserve-barge-in is on, do not warmup-mute mic if RMS reaches this threshold",
    )
    parser.add_argument(
        "--aec-tts-echo-gate-sim-threshold",
        type=float,
        default=0.66,
        help="TTS-active hard gate raw similarity threshold (more aggressive than generic gate)",
    )
    parser.add_argument(
        "--aec-tts-echo-gate-clean-sim-threshold",
        type=float,
        default=0.50,
        help="TTS-active hard gate post-AEC similarity threshold",
    )
    parser.add_argument(
        "--aec-tts-echo-gate-rms-ratio",
        type=float,
        default=1.25,
        help="TTS-active hard gate trigger ratio: cleaned_rms <= ref_rms * ratio",
    )
    parser.add_argument(
        "--aec-tts-half-duplex",
        dest="aec_tts_half_duplex",
        action="store_true",
        default=False,
        help="Mute upstream mic during TTS unless barge-in is detected",
    )
    parser.add_argument(
        "--no-aec-tts-half-duplex",
        dest="aec_tts_half_duplex",
        action="store_false",
        help="Disable half-duplex mute during TTS",
    )
    parser.add_argument(
        "--aec-tts-barge-in-rms",
        type=float,
        default=1200.0,
        help="Minimum mic RMS to treat input as potential user barge-in during TTS",
    )
    parser.add_argument(
        "--aec-tts-barge-in-ratio",
        type=float,
        default=1.65,
        help="Require mic_rms >= ref_rms * ratio for barge-in during TTS",
    )
    parser.add_argument(
        "--aec-tts-barge-in-sim-max",
        type=float,
        default=0.55,
        help="Maximum mic/reference similarity allowed for barge-in during TTS",
    )
    parser.add_argument(
        "--aec-tts-barge-in-chunks",
        type=int,
        default=2,
        help="Consecutive barge-in chunks required to release TTS half-duplex mute",
    )
    parser.add_argument(
        "--aec-tts-barge-in-interrupt",
        dest="aec_tts_barge_in_interrupt",
        action="store_true",
        default=False,
        help="Interrupt local playback when barge-in release is triggered",
    )
    parser.add_argument(
        "--no-aec-tts-barge-in-interrupt",
        dest="aec_tts_barge_in_interrupt",
        action="store_false",
        help="Do not interrupt local playback on barge-in release",
    )
    parser.add_argument(
        "--aec-near-end-protect-ratio",
        type=float,
        default=1.18,
        help="If mic_rms >= ref_rms * ratio, treat as near-end speech and bypass hard echo gates",
    )
    parser.add_argument(
        "--aec-residual-suppress",
        dest="aec_residual_suppress",
        action="store_true",
        default=True,
        help="Apply a second attenuation pass when chunk still strongly matches playback reference",
    )
    parser.add_argument(
        "--no-aec-residual-suppress",
        dest="aec_residual_suppress",
        action="store_false",
        help="Disable residual echo attenuation pass",
    )
    parser.add_argument(
        "--aec-residual-sim-threshold",
        type=float,
        default=0.80,
        help="Cosine similarity threshold used by residual suppression logic",
    )
    parser.add_argument(
        "--aec-residual-attenuation",
        type=float,
        default=0.25,
        help="Residual echo attenuation gain in (0,1]; lower means stronger suppression",
    )

    parser.add_argument(
        "--playback",
        dest="playback",
        action="store_true",
        default=True,
        help="Play streamed TTS audio (default on)",
    )
    parser.add_argument(
        "--no-playback",
        dest="playback",
        action="store_false",
        help="Disable local speaker playback",
    )
    parser.add_argument("--playback-sample-rate", type=int, default=24000, help="Playback sample rate")
    parser.add_argument("--save-dir", default="", help="Optional folder to save returned pcm chunks")

    parser.add_argument("--connect-timeout", type=float, default=5.0, help="HTTP connect timeout")
    parser.add_argument("--read-timeout", type=float, default=120.0, help="HTTP read timeout")

    args = parser.parse_args()
    if args.aec_engine != "webrtc":
        raise ValueError("--aec-engine must be webrtc")
    if args.aec_webrtc_aec_type < 0:
        raise ValueError("--aec-webrtc-aec-type must be >= 0")
    if args.aec_ref_delay_ms < 0:
        raise ValueError("--aec-ref-delay-ms must be >= 0")
    if args.aec_ref_buffer_ms <= 0:
        raise ValueError("--aec-ref-buffer-ms must be > 0")
    if args.aec_ref_hold_ms < 0:
        raise ValueError("--aec-ref-hold-ms must be >= 0")
    if args.aec_ref_min_rms < 0:
        raise ValueError("--aec-ref-min-rms must be >= 0")
    if args.aec_max_suppress_gain < 0:
        raise ValueError("--aec-max-suppress-gain must be >= 0")
    if not (0.0 <= args.aec_adapt_alpha <= 1.0):
        raise ValueError("--aec-adapt-alpha must be in [0, 1]")
    if args.aec_search_span_ms < 0:
        raise ValueError("--aec-search-span-ms must be >= 0")
    if args.aec_search_step_ms <= 0:
        raise ValueError("--aec-search-step-ms must be > 0")
    if not (0.0 <= args.aec_auto_delay_min_score <= 1.0):
        raise ValueError("--aec-auto-delay-min-score must be in [0, 1]")
    if args.aec_auto_delay_interval_chunks <= 0:
        raise ValueError("--aec-auto-delay-interval-chunks must be > 0")
    if not (0.0 <= args.aec_echo_gate_sim_threshold <= 1.0):
        raise ValueError("--aec-echo-gate-sim-threshold must be in [0, 1]")
    if not (0.0 <= args.aec_echo_gate_clean_sim_threshold <= 1.0):
        raise ValueError("--aec-echo-gate-clean-sim-threshold must be in [0, 1]")
    if args.aec_echo_gate_rms_ratio <= 0:
        raise ValueError("--aec-echo-gate-rms-ratio must be > 0")
    if args.aec_tts_warmup_mute_ms < 0:
        raise ValueError("--aec-tts-warmup-mute-ms must be >= 0")
    if args.aec_tts_ref_wait_mute_ms < 0:
        raise ValueError("--aec-tts-ref-wait-mute-ms must be >= 0")
    if args.aec_tts_stale_ms < 0:
        raise ValueError("--aec-tts-stale-ms must be >= 0")
    if args.aec_barge_in_warmup_rms < 0:
        raise ValueError("--aec-barge-in-warmup-rms must be >= 0")
    if not (0.0 <= args.aec_tts_echo_gate_sim_threshold <= 1.0):
        raise ValueError("--aec-tts-echo-gate-sim-threshold must be in [0, 1]")
    if not (0.0 <= args.aec_tts_echo_gate_clean_sim_threshold <= 1.0):
        raise ValueError("--aec-tts-echo-gate-clean-sim-threshold must be in [0, 1]")
    if args.aec_tts_echo_gate_rms_ratio <= 0:
        raise ValueError("--aec-tts-echo-gate-rms-ratio must be > 0")
    if args.aec_tts_barge_in_rms < 0:
        raise ValueError("--aec-tts-barge-in-rms must be >= 0")
    if args.aec_tts_barge_in_ratio <= 0:
        raise ValueError("--aec-tts-barge-in-ratio must be > 0")
    if not (0.0 <= args.aec_tts_barge_in_sim_max <= 1.0):
        raise ValueError("--aec-tts-barge-in-sim-max must be in [0, 1]")
    if args.aec_tts_barge_in_chunks <= 0:
        raise ValueError("--aec-tts-barge-in-chunks must be > 0")
    if args.aec_near_end_protect_ratio <= 0:
        raise ValueError("--aec-near-end-protect-ratio must be > 0")
    if args.ws_media_reconnect_interval_sec <= 0:
        raise ValueError("--ws-media-reconnect-interval-sec must be > 0")
    if not (0.0 <= args.aec_residual_sim_threshold <= 1.0):
        raise ValueError("--aec-residual-sim-threshold must be in [0, 1]")
    if not (0.0 < args.aec_residual_attenuation <= 1.0):
        raise ValueError("--aec-residual-attenuation must be in (0, 1]")
    if args.transport != "asrws" and (not args.base_url):
        args.base_url = args.public_base_url if args.server_env == "public" else args.local_base_url
    return args


def main() -> None:
    args = parse_args()
    if args.list_input_devices or args.list_output_devices:
        pa = pyaudio.PyAudio()
        try:
            if args.list_input_devices:
                default_input_index = None
                try:
                    default_input_index = int(pa.get_default_input_device_info()["index"])
                except Exception:
                    pass
                for i in range(pa.get_device_count()):
                    info = pa.get_device_info_by_index(i)
                    max_input_channels = int(info.get("maxInputChannels", 0))
                    if max_input_channels <= 0:
                        continue
                    marker = " (default)" if default_input_index is not None and i == default_input_index else ""
                    name = info.get("name", "unknown")
                    default_rate = int(float(info.get("defaultSampleRate", 0)))
                    print(
                        f"[mic] index={i}, channels={max_input_channels}, "
                        f"default_rate={default_rate}, name={name}{marker}"
                    )
            if args.list_output_devices:
                default_output_index = None
                try:
                    default_output_index = int(pa.get_default_output_device_info()["index"])
                except Exception:
                    pass
                for i in range(pa.get_device_count()):
                    info = pa.get_device_info_by_index(i)
                    max_output_channels = int(info.get("maxOutputChannels", 0))
                    if max_output_channels <= 0:
                        continue
                    marker = " (default)" if default_output_index is not None and i == default_output_index else ""
                    name = info.get("name", "unknown")
                    default_rate = int(float(info.get("defaultSampleRate", 0)))
                    print(
                        f"[spk] index={i}, channels={max_output_channels}, "
                        f"default_rate={default_rate}, name={name}{marker}"
                    )
        finally:
            pa.terminate()
        return

    client = MicChunkClient(args)
    if args.transport == "ws":
        endpoint: Any
        if args.ws_split_channels:
            endpoint = {
                "control": client.ws_control_endpoint,
                "media": client.ws_media_endpoint,
            }
        else:
            endpoint = client.ws_endpoint
    elif args.transport == "asrws":
        endpoint = client.asr_ws_endpoint
    else:
        endpoint = client.endpoint
    print(
        json.dumps(
            {
                "endpoint": endpoint,
                "server_env": args.server_env,
                "base_url": args.base_url,
                "transport": args.transport,
                "session_id": client.session_id,
                "chunk_ms": args.chunk_ms,
                "sample_rate": args.sample_rate,
                "packets_per_second": round(client.packets_per_second, 3),
                "chunk_bytes": client.chunk_bytes,
                "ws_split_channels": bool(args.ws_split_channels),
                "response_mode": args.response_mode,
                "playback": args.playback,
                "local": args.local,
                "aec_enabled": bool(args.aec_enabled),
                "aec_engine": args.aec_engine,
                "aec_webrtc_required": bool(args.aec_webrtc_required),
                "aec_webrtc_post_filter": bool(args.aec_webrtc_post_filter),
                "aec_ref_delay_ms": args.aec_ref_delay_ms,
                "aec_ref_buffer_ms": args.aec_ref_buffer_ms,
                "asrws": args.transport == "asrws",
                "asr_language": args.asr_language,
            },
            ensure_ascii=False,
        )
    )
    print("Press Ctrl+C to stop.")

    try:
        client.start()
        while not client.stop_event.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
        print("Stopped.")


if __name__ == "__main__":
    main()
