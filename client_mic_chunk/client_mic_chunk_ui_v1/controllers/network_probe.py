from __future__ import annotations

import json
import os
from datetime import datetime

import requests
from tkinter import messagebox


def resolve_whoami_base_url(app) -> str:
    command = (
        app.conversation_command_var.get().strip()
        or app.command_var.get().strip()
        or app._fixed_startup_command
    )
    tokens = app._safe_split(command)
    env = (app.conversation_server_env_var.get() or app.server_env_var.get() or "local").strip().lower()
    if env not in {"local", "public"}:
        env = "local"
    base_url = ""
    local_base_url = app._whoami_local_base_url
    public_base_url = app._whoami_public_base_url
    i = 0
    while i < len(tokens):
        token = str(tokens[i]).strip()
        if token == "--server-env" and (i + 1) < len(tokens):
            value = str(tokens[i + 1]).strip().lower()
            if value in {"local", "public"}:
                env = value
            i += 2
            continue
        if token == "--base-url" and (i + 1) < len(tokens):
            base_url = str(tokens[i + 1]).strip()
            i += 2
            continue
        if token == "--local-base-url" and (i + 1) < len(tokens):
            local_base_url = str(tokens[i + 1]).strip() or local_base_url
            i += 2
            continue
        if token == "--public-base-url" and (i + 1) < len(tokens):
            public_base_url = str(tokens[i + 1]).strip() or public_base_url
            i += 2
            continue
        i += 1
    resolved = base_url or (public_base_url if env == "public" else local_base_url)
    resolved = resolved.strip()
    if resolved.startswith("ws://"):
        resolved = "http://" + resolved[len("ws://") :]
    elif resolved.startswith("wss://"):
        resolved = "https://" + resolved[len("wss://") :]
    return resolved.rstrip("/")


def request_whoami_from_settings(app) -> None:
    base_url = resolve_whoami_base_url(app)
    if not base_url:
        messagebox.showerror("Whoami失败", "无法解析服务端地址。")
        return
    url = f"{base_url}/debug/whoami"
    ts_text = datetime.now().strftime("%H:%M:%S")
    app._append_line(app.log_text, f"[{ts_text}] [WHOAMI] request {url}")
    try:
        resp = requests.get(url, timeout=5.0)
        body_text = (resp.text or "").strip()
        payload: dict[str, object]
        try:
            parsed = resp.json()
            payload = parsed if isinstance(parsed, dict) else {"body": parsed}
        except Exception:
            payload = {"body": body_text[:800]}
        payload["status_code"] = resp.status_code
        app._append_line(
            app.log_text,
            f"[{ts_text}] [WHOAMI] response {json.dumps(payload, ensure_ascii=False)}",
        )
        host = str(payload.get("host", "") or "")
        pid = str(payload.get("pid", "") or "")
        revision = str(payload.get("revision", "") or "")
        log_dir = str(payload.get("log_dir", "") or "")
        log_file = str(payload.get("log_file", "") or "")
        messagebox.showinfo(
            "Whoami",
            (
                f"host: {host}\n"
                f"pid: {pid}\n"
                f"revision: {revision}\n"
                f"log_dir: {log_dir}\n"
                f"log_file: {log_file}"
            ),
        )
    except Exception as exc:
        app._append_line(app.log_text, f"[{ts_text}] [WHOAMI] failed: {exc}")
        messagebox.showerror("Whoami失败", str(exc))


def probe_public_ip(*, use_env_proxy: bool) -> tuple[str, str]:
    urls = [
        "https://api.ipify.org?format=json",
        "https://httpbin.org/ip",
        "https://ifconfig.me/ip",
    ]
    session = requests.Session()
    session.trust_env = bool(use_env_proxy)
    proxies = None if use_env_proxy else {"http": None, "https": None}
    last_error = ""
    try:
        for url in urls:
            try:
                resp = session.get(url, timeout=3.5, proxies=proxies)
                text = (resp.text or "").strip()
                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code} @ {url}"
                    continue
                ip_value = ""
                try:
                    payload = resp.json()
                    if isinstance(payload, dict):
                        if isinstance(payload.get("ip"), str):
                            ip_value = payload.get("ip", "").strip()
                        elif isinstance(payload.get("origin"), str):
                            ip_value = payload.get("origin", "").strip()
                except Exception:
                    pass
                if (not ip_value) and text:
                    ip_value = " ".join(text.split())
                if ip_value:
                    return ip_value, url
                last_error = f"empty body @ {url}"
            except Exception as exc:
                last_error = f"{url}: {exc}"
                continue
    finally:
        try:
            session.close()
        except Exception:
            pass
    return "", last_error or "probe failed"


def request_network_probe_from_settings(app) -> None:
    ts_text = datetime.now().strftime("%H:%M:%S")
    base_url = resolve_whoami_base_url(app) or "https://example.com"
    proxy_keys = (
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    )
    env_proxy = {k: str(os.environ.get(k, "") or "").strip() for k in proxy_keys}
    env_proxy = {k: v for k, v in env_proxy.items() if v}
    request_proxy = requests.utils.get_environ_proxies(base_url) or {}
    app._append_line(app.log_text, f"[{ts_text}] [NET] probe start base={base_url}")
    try:
        ip_with_proxy, src_with = probe_public_ip(use_env_proxy=True)
        ip_direct, src_direct = probe_public_ip(use_env_proxy=False)
        proxy_env_on = bool(env_proxy)
        request_proxy_on = bool(request_proxy)
        same_ip = bool(ip_with_proxy and ip_direct and ip_with_proxy == ip_direct)
        different_ip = bool(ip_with_proxy and ip_direct and ip_with_proxy != ip_direct)
        likely_proxy = False
        status_text = "未知"
        if different_ip and request_proxy_on:
            likely_proxy = True
            status_text = "是（代理出口与直连出口不同）"
        elif same_ip and request_proxy_on:
            status_text = "可能未生效（已配置代理但出口IP一致）"
        elif request_proxy_on and (ip_with_proxy and (not ip_direct)):
            likely_proxy = True
            status_text = "是（代理可达，直连探测失败）"
        elif request_proxy_on:
            status_text = "可能是（检测信息不足）"
        else:
            status_text = "否（未检测到代理配置）"

        payload = {
            "proxy_env_on": proxy_env_on,
            "request_proxy_on": request_proxy_on,
            "likely_proxy_in_use": likely_proxy,
            "ip_via_env_proxy": ip_with_proxy,
            "ip_via_direct": ip_direct,
            "probe_src_via_proxy": src_with,
            "probe_src_via_direct": src_direct,
            "request_proxy": request_proxy,
            "env_proxy": env_proxy,
        }
        app._append_line(app.log_text, f"[{ts_text}] [NET] result {json.dumps(payload, ensure_ascii=False)}")
        messagebox.showinfo(
            "网络检测",
            (
                f"是否走代理: {status_text}\n\n"
                f"代理出口IP: {ip_with_proxy or '-'}\n"
                f"直连出口IP: {ip_direct or '-'}\n"
                f"代理探测: {src_with or '-'}\n"
                f"直连探测: {src_direct or '-'}\n"
                f"requests代理配置: {'有' if request_proxy_on else '无'}\n"
                f"环境变量代理: {'有' if proxy_env_on else '无'}"
            ),
        )
    except Exception as exc:
        app._append_line(app.log_text, f"[{ts_text}] [NET] failed: {exc}")
        messagebox.showerror("网络检测失败", str(exc))

