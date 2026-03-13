from __future__ import annotations

import os
import shlex
import subprocess
import threading
from typing import Callable, Mapping, Optional

from .event_parser import parse_line
from .models import UiEvent


EventCallback = Callable[[UiEvent], None]


class ClientProcessBridge:
    def __init__(self, on_event: EventCallback) -> None:
        self._on_event = on_event
        self._proc: Optional[subprocess.Popen[str]] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self, command: str, cwd: str, env_overrides: Optional[Mapping[str, str]] = None) -> None:
        if not command.strip():
            raise ValueError("command cannot be empty")
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                raise RuntimeError("process is already running")

            env = None
            if env_overrides:
                env = os.environ.copy()
                for key, value in env_overrides.items():
                    env[str(key)] = str(value)

            argv = self._split_command(command)
            creationflags = self._win_creationflags()
            self._proc = subprocess.Popen(
                argv,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                bufsize=0,
                shell=False,
                env=env,
                creationflags=creationflags,
            )

            self._reader_thread = threading.Thread(target=self._read_stdout_loop, daemon=True)
            self._reader_thread.start()

        self._on_event(UiEvent(kind="process_started", payload={"command": command, "cwd": cwd}))

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return

        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=self._win_creationflags(),
            )
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        else:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        self._on_event(UiEvent(kind="process_stopped", payload={"return_code": proc.returncode}))

    def _read_stdout_loop(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is None or proc.stdout is None:
            return

        try:
            for line in iter(proc.stdout.readline, b""):
                raw = self._decode_output_line(line).rstrip("\r\n")
                if not raw:
                    continue
                self._on_event(UiEvent(kind="log", raw=raw))
                parsed = parse_line(raw)
                if parsed is not None:
                    self._on_event(parsed)
        finally:
            return_code = proc.poll()
            self._on_event(UiEvent(kind="process_exit", payload={"return_code": return_code}))

    @staticmethod
    def _split_command(command: str) -> list[str]:
        if os.name == "nt":
            return shlex.split(command, posix=False)
        return shlex.split(command, posix=True)

    @staticmethod
    def _win_creationflags() -> int:
        if os.name != "nt":
            return 0
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @staticmethod
    def _decode_output_line(line: bytes) -> str:
        if isinstance(line, str):
            return line
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "cp936"):
            try:
                return line.decode(encoding)
            except UnicodeDecodeError:
                continue
        return line.decode("utf-8", errors="replace")

