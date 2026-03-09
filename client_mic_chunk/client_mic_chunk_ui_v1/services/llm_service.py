from __future__ import annotations

import json
import os
from typing import Callable

import requests


ChunkCallback = Callable[[str], None] | None


def extract_llm_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str) and item:
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            for key in ("text", "content", "reasoning_content", "summary"):
                v = item.get(key)
                if isinstance(v, str) and v:
                    parts.append(v)
        return "".join(parts)
    if isinstance(value, dict):
        for key in ("text", "content", "reasoning_content", "summary"):
            v = value.get(key)
            if isinstance(v, str) and v:
                return v
        for v in value.values():
            txt = extract_llm_text(v)
            if txt:
                return txt
    return ""


def call_ark_chat_completion(
    llm_prompt: str,
    on_thinking_chunk: ChunkCallback = None,
    on_content_chunk: ChunkCallback = None,
) -> tuple[str, str]:
    api_key = os.getenv("ARK_API_KEY") or "5b2dde3a-28c8-4e69-a447-ea1bc4cca1f1"
    model_id = os.getenv("ARK_MODEL_ID") or "doubao-seed-1-8-251228"
    base_url = (os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
    if not api_key:
        raise RuntimeError("ARK_API_KEY is empty")

    payload = {
        "model": model_id,
        "messages": [{"role": "system", "content": llm_prompt}],
        "stream": True,
        "thinking": {"type": "enabled"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Accept-Charset": "utf-8",
    }

    content_parts: list[str] = []
    thinking_parts: list[str] = []
    url = f"{base_url}/chat/completions"
    with requests.post(url, headers=headers, json=payload, timeout=120, stream=True) as response:
        if response.status_code != 200:
            body = (response.text or "").strip()
            if len(body) > 400:
                body = body[:400] + "..."
            raise RuntimeError(f"HTTP {response.status_code}: {body}")
        response.encoding = "utf-8"
        for raw in response.iter_lines(decode_unicode=False):
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw).strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if not data_str or data_str == "[DONE]":
                continue
            try:
                chunk = json.loads(data_str)
            except Exception:
                continue

            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0] or {}
            delta = choice.get("delta") or {}

            delta_content = extract_llm_text(delta.get("content")) or extract_llm_text(delta.get("text"))
            if delta_content:
                content_parts.append(delta_content)
                if on_content_chunk is not None:
                    try:
                        on_content_chunk(delta_content)
                    except Exception:
                        pass

            delta_thinking = (
                extract_llm_text(delta.get("reasoning_content"))
                or extract_llm_text(delta.get("reasoning"))
                or extract_llm_text(delta.get("thinking"))
            )
            if delta_thinking:
                thinking_parts.append(delta_thinking)
                if on_thinking_chunk is not None:
                    try:
                        on_thinking_chunk(delta_thinking)
                    except Exception:
                        pass

            msg = choice.get("message") or {}
            msg_content = extract_llm_text(msg.get("content"))
            msg_thinking = extract_llm_text(msg.get("reasoning_content")) or extract_llm_text(msg.get("reasoning"))
            if msg_content and not content_parts:
                content_parts.append(msg_content)
                if on_content_chunk is not None:
                    try:
                        on_content_chunk(msg_content)
                    except Exception:
                        pass
            if msg_thinking and not thinking_parts:
                thinking_parts.append(msg_thinking)
                if on_thinking_chunk is not None:
                    try:
                        on_thinking_chunk(msg_thinking)
                    except Exception:
                        pass

    return "".join(content_parts).strip(), "".join(thinking_parts).strip()


def call_deepseek_chat_completion(
    llm_prompt: str,
    on_thinking_chunk: ChunkCallback = None,
    on_content_chunk: ChunkCallback = None,
) -> tuple[str, str]:
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("ARK_API_KEY") or "sk-5cd4a5e62d2a452d9360964caf56a29e"
    model_id = os.getenv("DEEPSEEK_MODEL_ID") or "deepseek-reasoner"
    base_url = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is empty")

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "你是超级业务专家。"},
            {"role": "user", "content": llm_prompt},
        ],
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Accept-Charset": "utf-8",
    }

    content_parts: list[str] = []
    thinking_parts: list[str] = []
    url = f"{base_url}/chat/completions"
    with requests.post(url, headers=headers, json=payload, timeout=180, stream=True) as response:
        if response.status_code != 200:
            body = (response.text or "").strip()
            if len(body) > 400:
                body = body[:400] + "..."
            raise RuntimeError(f"HTTP {response.status_code}: {body}")
        response.encoding = "utf-8"
        for raw in response.iter_lines(decode_unicode=False):
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw).strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if (not data_str) or (data_str == "[DONE]"):
                continue
            try:
                chunk = json.loads(data_str)
            except Exception:
                continue

            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0] or {}
            delta = choice.get("delta") or {}

            delta_content = extract_llm_text(delta.get("content")) or extract_llm_text(delta.get("text"))
            if delta_content:
                content_parts.append(delta_content)
                if on_content_chunk is not None:
                    try:
                        on_content_chunk(delta_content)
                    except Exception:
                        pass

            delta_thinking = (
                extract_llm_text(delta.get("reasoning_content"))
                or extract_llm_text(delta.get("reasoning"))
                or extract_llm_text(delta.get("thinking"))
            )
            if delta_thinking:
                thinking_parts.append(delta_thinking)
                if on_thinking_chunk is not None:
                    try:
                        on_thinking_chunk(delta_thinking)
                    except Exception:
                        pass

            msg = choice.get("message") or {}
            msg_content = extract_llm_text(msg.get("content"))
            msg_thinking = extract_llm_text(msg.get("reasoning_content")) or extract_llm_text(msg.get("reasoning"))
            if msg_content and (not content_parts):
                content_parts.append(msg_content)
                if on_content_chunk is not None:
                    try:
                        on_content_chunk(msg_content)
                    except Exception:
                        pass
            if msg_thinking and (not thinking_parts):
                thinking_parts.append(msg_thinking)
                if on_thinking_chunk is not None:
                    try:
                        on_thinking_chunk(msg_thinking)
                    except Exception:
                        pass

    return "".join(content_parts).strip(), "".join(thinking_parts).strip()


def call_deepseek_chat_fast(
    llm_prompt: str,
    system_prompt: str = "你是超级业务专家。请严格按照要求输出JSON格式结果。",
    on_content_chunk: ChunkCallback = None,
) -> str:
    """使用 deepseek-chat 非思考模型进行快速推断，直接返回内容文本。"""
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("ARK_API_KEY") or "sk-5cd4a5e62d2a452d9360964caf56a29e"
    model_id = os.getenv("DEEPSEEK_CHAT_MODEL_ID") or "deepseek-chat"
    base_url = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is empty")

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": llm_prompt},
        ],
        "stream": True,
        "max_tokens": 512,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Accept-Charset": "utf-8",
    }

    content_parts: list[str] = []
    url = f"{base_url}/chat/completions"
    with requests.post(url, headers=headers, json=payload, timeout=30, stream=True) as response:
        if response.status_code != 200:
            body = (response.text or "").strip()
            if len(body) > 400:
                body = body[:400] + "..."
            raise RuntimeError(f"HTTP {response.status_code}: {body}")
        response.encoding = "utf-8"
        for raw in response.iter_lines(decode_unicode=False):
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw).strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if (not data_str) or (data_str == "[DONE]"):
                continue
            try:
                chunk = json.loads(data_str)
            except Exception:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0] or {}
            delta = choice.get("delta") or {}
            delta_content = extract_llm_text(delta.get("content")) or extract_llm_text(delta.get("text"))
            if delta_content:
                content_parts.append(delta_content)
                if on_content_chunk is not None:
                    try:
                        on_content_chunk(delta_content)
                    except Exception:
                        pass
            msg = choice.get("message") or {}
            msg_content = extract_llm_text(msg.get("content"))
            if msg_content and not content_parts:
                content_parts.append(msg_content)
                if on_content_chunk is not None:
                    try:
                        on_content_chunk(msg_content)
                    except Exception:
                        pass

    return "".join(content_parts).strip()


def call_ark_chat_fast(
    llm_prompt: str,
    system_prompt: str = "你是超级业务专家。请严格按照要求输出JSON格式结果。",
    on_content_chunk: ChunkCallback = None,
) -> str:
    """使用 doubao-seed-1-6-flash 非思考模型进行快速推断，直接返回内容文本。"""
    api_key = os.getenv("ARK_API_KEY") or "5b2dde3a-28c8-4e69-a447-ea1bc4cca1f1"
    model_id = (
        os.getenv("INTENT_MODEL_ID")
        or os.getenv("ARK_MODEL_ID")
        or os.getenv("ARK_FLASH_MODEL_ID")
        or "doubao-seed-1-8-251228"
    )
    base_url = (os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
    max_tokens_env = int(os.getenv("ARK_MAX_TOKENS", "256"))

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": llm_prompt},
        ],
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    if max_tokens_env > 0:
        payload["max_tokens"] = max(96, min(max_tokens_env, 256))
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Charset": "utf-8",
    }

    url = f"{base_url}/chat/completions"
    with requests.post(url, headers=headers, json=payload, timeout=30) as response:
        if response.status_code != 200:
            body = (response.text or "").strip()
            if len(body) > 400:
                body = body[:400] + "..."
            raise RuntimeError(f"HTTP {response.status_code}: {body}")
        try:
            data = response.json()
        except Exception:
            data = {}
        choices = data.get("choices") if isinstance(data, dict) else []
        message_obj = (choices[0] or {}).get("message") if isinstance(choices, list) and choices else {}
        content = extract_llm_text((message_obj or {}).get("content")).strip()
        if content and on_content_chunk is not None:
            try:
                on_content_chunk(content)
            except Exception:
                pass
        return content
