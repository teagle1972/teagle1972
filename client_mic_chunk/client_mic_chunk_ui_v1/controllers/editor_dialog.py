from __future__ import annotations

import queue
import threading
from datetime import datetime

import tkinter as tk
from tkinter import BOTH, LEFT, X, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
try:
    from .ui_widgets import TtlScrolledText
except Exception:
    from ui_widgets import TtlScrolledText

try:
    from ..backend import ClientProcessBridge, UiEvent  # type: ignore[attr-defined]
except Exception:
    from backend import ClientProcessBridge, UiEvent


def open_settings_editor_dialog(
    app,
    kind: str,
    kind_label: str,
    source_widget: ScrolledText,
) -> None:
    for existing in list(app._editor_dialogs):
        app._close_settings_editor_dialog(existing)
    if app._settings_asr_bridge.running:
        app._stop_settings_asr()
        app.asr_enabled_var.set(False)
        app.asr_toggle_text_var.set("Enable ASR")

    win = tk.Toplevel(app)
    win.title(f"{kind_label} - Edit")
    win.geometry("980x680")
    win.configure(bg="#f3f6fb")

    root = ttk.Frame(win, style="App.TFrame", padding=10)
    root.pack(fill=BOTH, expand=True)

    top = ttk.Frame(root, style="Panel.TFrame", padding=(10, 10, 10, 10))
    top.pack(fill=X)
    submit_var = tk.StringVar(value="Submit")
    dialog: dict[str, object] = {}

    ttk.Button(
        top,
        textvariable=submit_var,
        command=lambda: app._submit_editor_dialog(dialog),
        style="Primary.TButton",
    ).pack(side=LEFT)
    ttk.Button(top, text="Close", command=lambda: app._close_settings_editor_dialog(dialog), style="Soft.TButton").pack(
        side=LEFT, padx=(8, 0)
    )

    panes = ttk.Panedwindow(root, orient=tk.VERTICAL)
    panes.pack(fill=BOTH, expand=True, pady=(8, 0))

    instruction_box = ttk.LabelFrame(
        panes,
        text="Input (can include ASR recognized text)",
        style="Section.TLabelframe",
        padding=8,
    )
    instruction_editor = TtlScrolledText(
        instruction_box,
        wrap="word",
        bg="#ffffff",
        fg="#111827",
        insertbackground="#111827",
        relief="flat",
        highlightthickness=1,
        highlightbackground="#d7dee8",
    )
    instruction_editor.pack(fill=BOTH, expand=True)
    instruction_editor.tag_configure("asr_partial", foreground="#9ca3af")
    instruction_editor.insert("1.0", source_widget.get("1.0", "end-1c"))
    panes.add(instruction_box, weight=2)

    output_box = ttk.LabelFrame(panes, text="Model output", style="Section.TLabelframe", padding=8)
    output_editor = TtlScrolledText(
        output_box,
        wrap="word",
        state="disabled",
        bg="#ffffff",
        fg="#111827",
        insertbackground="#111827",
        relief="flat",
        highlightthickness=1,
        highlightbackground="#d7dee8",
    )
    output_editor.pack(fill=BOTH, expand=True)
    panes.add(output_box, weight=1)

    event_q: queue.Queue[UiEvent] = queue.Queue()
    bridge = ClientProcessBridge(on_event=event_q.put)
    dialog.update(
        {
            "kind": kind,
            "kind_label": kind_label,
            "window": win,
            "instruction_editor": instruction_editor,
            "output_editor": output_editor,
            "source": source_widget,
            "queue": event_q,
            "bridge": bridge,
            "submit_var": submit_var,
            "asr_stream_active": False,
            "asr_stream_phase": "",
            "asr_stream_line_start": "",
            "asr_stream_content_start": "",
        }
    )
    app._editor_dialogs.append(dialog)

    cmd_var = getattr(app, "settings_asr_command_var", None)
    if cmd_var is not None:
        try:
            latest_command = str(cmd_var.get() or "").strip()
        except Exception:
            latest_command = ""
        if latest_command:
            app._settings_asr_command = latest_command
    command = app._ensure_unbuffered_python_command(app._settings_asr_command)
    command = app._ensure_mic_capture_command(command)
    strict_ok, strict_message = app._check_strict_webrtc_readiness(command)
    if not strict_ok:
        app._append_line(
            app.log_text,
            (
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"[STRICT_WEBRTC] preflight_failed scope=editor:{kind_label} "
                f"reason={app._sanitize_inline_text(strict_message)}"
            ),
        )
        win.protocol("WM_DELETE_WINDOW", lambda: app._close_settings_editor_dialog(dialog))
        app._poll_editor_dialog_events(dialog)
        return
    app._append_line(
        app.log_text,
        (
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"[ASR_EDITOR:{kind_label}] start requested command={command}"
        ),
    )
    try:
        bridge.start(command=command, cwd=str(app._workspace_dir))
    except Exception as exc:
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [ASR_EDITOR:{kind_label}] start failed: {exc}",
        )

    win.protocol("WM_DELETE_WINDOW", lambda: app._close_settings_editor_dialog(dialog))
    app._poll_editor_dialog_events(dialog)


def close_settings_editor_dialog(app, dialog: dict[str, object], destroy_window: bool = True) -> None:
    bridge = dialog.get("bridge")
    if isinstance(bridge, ClientProcessBridge):
        try:
            bridge.stop()
        except Exception:
            pass

    win = dialog.get("window")
    if destroy_window and isinstance(win, tk.Toplevel):
        try:
            if win.winfo_exists():
                win.destroy()
        except Exception:
            pass

    if dialog in app._editor_dialogs:
        app._editor_dialogs.remove(dialog)


def poll_editor_dialog_events(app, dialog: dict[str, object]) -> None:
    win = dialog.get("window")
    if not isinstance(win, tk.Toplevel):
        return
    try:
        if not win.winfo_exists():
            app._close_settings_editor_dialog(dialog, destroy_window=False)
            return
    except Exception:
        app._close_settings_editor_dialog(dialog, destroy_window=False)
        return

    q = dialog.get("queue")
    editor = dialog.get("instruction_editor")
    kind_label = str(dialog.get("kind_label", "settings"))
    if isinstance(q, queue.Queue):
        while True:
            try:
                event = q.get_nowait()
            except queue.Empty:
                break
            ts_text = event.ts.strftime("%H:%M:%S")
            if event.kind == "log":
                app._append_line(app.log_text, f"[{ts_text}] [ASR_EDITOR:{kind_label}] {event.raw}")
                continue
            if event.kind in {"asr_partial", "asr_commit"} and isinstance(editor, ScrolledText):
                text = app._sanitize_inline_text(str(event.payload.get("text", "")))
                command = str(event.payload.get("command", "")).strip()
                if text and command:
                    text = f"{text} (command={command})"
                stream_active = bool(dialog.get("asr_stream_active", False))
                stream_phase = str(dialog.get("asr_stream_phase", "") or "")
                stream_line_start = str(dialog.get("asr_stream_line_start", "") or "")
                stream_start = str(dialog.get("asr_stream_content_start", "") or "")

                if event.kind == "asr_partial":
                    if not text:
                        continue
                    if stream_active and stream_phase == "commit":
                        editor.insert("end", "\n")
                        stream_active = False
                        stream_phase = ""
                        stream_line_start = ""
                        stream_start = ""
                        dialog["asr_stream_active"] = False
                        dialog["asr_stream_phase"] = ""
                        dialog["asr_stream_line_start"] = ""
                        dialog["asr_stream_content_start"] = ""
                    if not stream_active:
                        if editor.get("1.0", "end-1c").strip():
                            editor.insert("end", "\n")
                        stream_line_start = editor.index("end-1c")
                        editor.insert("end", app._get_asr_prefix("partial", ts_text))
                        stream_start = editor.index("end-1c")
                        dialog["asr_stream_line_start"] = stream_line_start
                        dialog["asr_stream_content_start"] = stream_start
                        dialog["asr_stream_active"] = True
                        dialog["asr_stream_phase"] = "partial"
                    else:
                        dialog["asr_stream_phase"] = "partial"
                    end_index = editor.index("end-1c")
                    editor.delete(stream_start, end_index)
                    editor.insert("end", text)
                    editor.tag_add("asr_partial", stream_line_start, editor.index("end-1c"))
                    editor.see("end")
                    continue

                if stream_active:
                    if not stream_line_start:
                        stream_line_start = f"{stream_start} linestart"
                    if text:
                        end_index = editor.index("end-1c")
                        editor.delete(stream_line_start, end_index)
                        editor.insert(
                            stream_line_start,
                            f"{app._get_asr_prefix('commit', ts_text)}{text}",
                        )
                    dialog["asr_stream_phase"] = "commit"
                    editor.tag_remove("asr_partial", stream_line_start, editor.index("end-1c"))
                    editor.see("end")
                elif text:
                    prefix = "\n" if editor.get("1.0", "end-1c").strip() else ""
                    editor.insert("end", prefix + f"{app._get_asr_prefix('commit', ts_text)}{text}")
                    stream_line_start = editor.index("end-1c linestart")
                    dialog["asr_stream_active"] = True
                    dialog["asr_stream_phase"] = "commit"
                    dialog["asr_stream_line_start"] = stream_line_start
                    dialog["asr_stream_content_start"] = editor.index("end-1c")
                    editor.see("end")
                continue
            if event.kind in {"process_stopped", "process_exit"}:
                if bool(dialog.get("asr_stream_active", False)) and isinstance(editor, ScrolledText):
                    editor.insert("end", "\n")
                    dialog["asr_stream_active"] = False
                    dialog["asr_stream_phase"] = ""
                    dialog["asr_stream_line_start"] = ""
                    dialog["asr_stream_content_start"] = ""
                code = event.payload.get("return_code")
                app._append_line(
                    app.log_text,
                    f"[{ts_text}] [ASR_EDITOR:{kind_label}] process exit: return_code={code}",
                )

    win.after(80, lambda: app._poll_editor_dialog_events(dialog))


def build_dialog_llm_prompt(kind: str, instruction_text: str) -> str:
    instruction = (instruction_text or "").strip()
    if kind == "customer_profile":
        return "\n\n".join(
            [
                "You are an assistant that drafts customer profiles.",
                "Task: build a complete customer profile from user input.",
                "Output rules:",
                "1. First line must be [Customer Profile].",
                "2. Then one field per line: field_name: value.",
                "3. Prefer concrete, usable mock data when possible.",
                "User input:",
                instruction,
            ]
        )
    if kind == "workflow":
        return "\n\n".join(
            [
                "You are an assistant that drafts phone call workflows.",
                "Task: generate a workflow from user input.",
                "Output rules:",
                "1. Return actionable workflow steps only.",
                "2. Keep wording concise and operational.",
                "3. Do not include explanations outside the final workflow.",
                "User input:",
                instruction,
            ]
        )
    return instruction


def submit_editor_dialog(app, dialog: dict[str, object]) -> None:
    if app._llm_submit_running:
        messagebox.showinfo("Submitting", "LLM request is running.")
        return

    editor = dialog.get("instruction_editor")
    if not isinstance(editor, ScrolledText):
        return
    prompt = (editor.get("1.0", "end-1c") or "").strip()
    if not prompt:
        kind_label = str(dialog.get("kind_label", "Content"))
        messagebox.showwarning("Empty content", f"{kind_label} cannot be empty.")
        return

    submit_var = dialog.get("submit_var")
    if isinstance(submit_var, tk.StringVar):
        submit_var.set("Submitting...")

    app._llm_submit_running = True
    output_editor = dialog.get("output_editor")
    if isinstance(output_editor, ScrolledText):
        app._set_text_content(output_editor, "[LLM thinking...]\n")

    kind = str(dialog.get("kind", "workflow"))
    kind_label = str(dialog.get("kind_label", "Content"))
    llm_prompt = app._build_dialog_llm_prompt(kind, prompt)
    app._log_llm_prompts(kind_label, llm_prompt)
    app._append_llm_prompt_block_to_system_instruction(
        begin_tag=f"[LLM_DIALOG_PROMPT_BEGIN][{kind_label}]",
        end_tag=f"[LLM_DIALOG_PROMPT_END][{kind_label}]",
        llm_prompt=llm_prompt,
    )
    app._set_llm_generation_frozen(True)

    threading.Thread(
        target=app._submit_editor_dialog_worker,
        args=(dialog, llm_prompt),
        daemon=True,
    ).start()


def submit_editor_dialog_worker(app, dialog: dict[str, object], llm_prompt: str) -> None:
    result_text = ""
    thinking_text = ""
    error_text = ""
    try:
        result_text, thinking_text = app._call_direct_llm_for_system_instruction(
            llm_prompt,
            on_thinking_chunk=lambda chunk: app.after(0, app._append_dialog_output_chunk, dialog, chunk),
        )
    except Exception as exc:
        error_text = str(exc)

    app.after(
        0,
        lambda: app._on_editor_dialog_submit_done(dialog, result_text, thinking_text, error_text),
    )


def on_editor_dialog_submit_done(
    app,
    dialog: dict[str, object],
    result_text: str,
    thinking_text: str,
    error_text: str,
) -> None:
    app._llm_submit_running = False
    submit_var = dialog.get("submit_var")
    if isinstance(submit_var, tk.StringVar):
        submit_var.set("Submit")

    if error_text:
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] submit failed: {error_text}",
        )
        app._append_dialog_output_chunk(dialog, f"\n[ERROR] {error_text}\n")
        app._set_llm_generation_frozen(False)
        messagebox.showerror("Submit failed", error_text)
        return

    summary = app._sanitize_inline_text(result_text) or "(empty reply)"
    kind = str(dialog.get("kind", ""))
    source_widget = dialog.get("source")
    if kind == "customer_profile":
        target_widget = source_widget if isinstance(source_widget, ScrolledText) else app.customer_profile_text
    elif kind == "workflow":
        target_widget = source_widget if isinstance(source_widget, ScrolledText) else app.workflow_text
    else:
        target_widget = source_widget
    if isinstance(target_widget, ScrolledText):
        app._set_text_content(target_widget, result_text or "")

    app._append_line(
        app.log_text,
        (
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] submit success: {summary} "
            f"| thinking_chars={len(thinking_text or '')}"
        ),
    )
    app._close_settings_editor_dialog(dialog)
    app._set_llm_generation_frozen(False)
