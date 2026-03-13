from __future__ import annotations

import tkinter as tk


def apply_server_env_to_command(app) -> None:
    apply_server_env_to_command_vars(app, app.command_var, app.server_env_var)


def apply_server_env_to_conversation_command(app) -> None:
    apply_server_env_to_command_vars(app, app.conversation_command_var, app.conversation_server_env_var)


def apply_server_env_to_command_vars(app, command_var: tk.StringVar, env_var: tk.StringVar) -> None:
    env = (env_var.get() or "local").strip().lower()
    if env not in {"local", "public"}:
        env = "local"
        env_var.set(env)

    command = (command_var.get() or "").strip()
    tokens = app._safe_split(command)
    if not tokens:
        return

    rebuilt: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in {"--server-env", "--base-url"}:
            i += 2 if i + 1 < len(tokens) else 1
            continue
        rebuilt.append(token)
        i += 1

    rebuilt.extend(["--server-env", env])
    new_command = app._safe_join(rebuilt)
    if new_command != command:
        command_var.set(new_command)


def sync_server_env_from_command(app, command: str) -> None:
    sync_server_env_from_command_to_var(app, command, app.server_env_var)


def sync_conversation_server_env_from_command(app, command: str) -> None:
    sync_server_env_from_command_to_var(app, command, app.conversation_server_env_var)


def sync_server_env_from_command_to_var(app, command: str, env_var: tk.StringVar) -> None:
    tokens = app._safe_split(command)
    if not tokens:
        return
    env = ""
    if "--server-env" in tokens:
        idx = tokens.index("--server-env")
        if idx + 1 < len(tokens):
            env = str(tokens[idx + 1]).strip().lower()
    if (not env) and ("--base-url" in tokens):
        idx = tokens.index("--base-url")
        if idx + 1 < len(tokens):
            base_url = str(tokens[idx + 1]).strip().lower()
            if base_url and ("127.0.0.1" not in base_url) and ("localhost" not in base_url):
                env = "public"
            elif base_url:
                env = "local"
    if env in {"local", "public"} and env != env_var.get():
        env_var.set(env)

