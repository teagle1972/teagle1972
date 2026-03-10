from __future__ import annotations

import threading
from datetime import datetime

import tkinter as tk
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText


def build_intent_generation_prompt(customer_profile_text: str, workflow_text: str, count: int) -> str:
    return "\n\n".join(
        [
            "你是电话业务场景的意图标签生成助手。",
            f"任务：根据客户画像与工作流程，生成 {count} 个客户意图标签。",
            "输出要求：",
            "1. 仅输出标签列表，每行一个标签，不要解释，不要 Markdown。",
            "2. 标签要短、清晰、可执行，尽量覆盖沟通中的关键分支。",
            f"3. 标签数量必须严格等于 {count} 个。",
            "4. 标签命名建议使用“Cxx_标签名”格式。",
            "【客户画像】",
            customer_profile_text.strip(),
            "【工作流程】",
            workflow_text.strip(),
        ]
    )


def append_intent_system_text(app, text: str) -> None:
    if not text:
        return
    widget = app.intent_system_text
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    widget.insert("end", text)
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")


def generate_intents_from_settings(app) -> None:
    if app._llm_submit_running:
        messagebox.showinfo("Submitting", "LLM request is running.")
        return

    count_text = (app.intent_generate_count_var.get() or "").strip()
    try:
        count = int(count_text)
    except Exception:
        messagebox.showwarning("Invalid count", "数量必须是整数。")
        return
    if count <= 0:
        messagebox.showwarning("Invalid count", "数量必须大于 0。")
        return

    customer_profile_text = app._strip_panel_llm_debug_blocks(app.customer_profile_text.get("1.0", "end-1c") or "").strip()
    workflow_text = app._strip_panel_llm_debug_blocks(app.workflow_text.get("1.0", "end-1c") or "").strip()
    if (not customer_profile_text) or (not workflow_text):
        messagebox.showwarning("Empty content", "请先在当前对话页准备客户画像和工作流程内容。")
        return
    llm_prompt = app._build_intent_generation_prompt(customer_profile_text, workflow_text, count)
    app._log_llm_prompts("意图生成", llm_prompt)
    app.intent_generate_text_var.set("生成中...")
    app._set_text_content(app.intent_system_text, "[LLM_INTENT_THINKING_BEGIN]\n")
    app._llm_submit_running = True
    app._set_llm_generation_frozen(True)

    threading.Thread(
        target=app._generate_intents_from_settings_worker,
        args=(llm_prompt,),
        daemon=True,
    ).start()


def generate_intents_from_settings_worker(app, llm_prompt: str) -> None:
    result_text = ""
    thinking_text = ""
    error_text = ""
    thinking_seen = {"value": False}

    def on_thinking_chunk(chunk: str) -> None:
        if not chunk:
            return
        thinking_seen["value"] = True
        app.after(0, app._append_intent_system_text, chunk)

    try:
        result_text, thinking_text = app._call_direct_llm_for_system_instruction(
            llm_prompt,
            on_thinking_chunk=on_thinking_chunk,
        )
    except Exception as exc:
        error_text = str(exc)

    app.after(
        0,
        lambda: app._on_generate_intents_from_settings_done(
            result_text=result_text,
            thinking_text=thinking_text,
            error_text=error_text,
            thinking_seen=bool(thinking_seen["value"]),
        ),
    )


def on_generate_intents_from_settings_done(
    app,
    result_text: str,
    thinking_text: str,
    error_text: str,
    thinking_seen: bool,
) -> None:
    app._llm_submit_running = False
    app.intent_generate_text_var.set("鐢熸垚鎰忓浘")

    if (not thinking_seen) and thinking_text:
        app._append_intent_system_text(thinking_text)
    app._append_intent_system_text("\n[LLM_INTENT_THINKING_END]\n")

    if error_text:
        app._append_intent_system_text(f"[LLM_INTENT_ERROR] {error_text}\n")
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] 鎰忓浘鐢熸垚澶辫触: {error_text}",
        )
        app._set_llm_generation_frozen(False)
        return

    app._set_text_content(app.intent_text, result_text or "")
    summary = app._sanitize_inline_text(result_text) or "(empty reply)"
    app._append_line(
        app.log_text,
        (
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] 鎰忓浘鐢熸垚鎴愬姛: {summary} "
            f"| thinking_chars={len(thinking_text or '')}"
        ),
    )
    app._set_llm_generation_frozen(False)


def submit_settings_panel_llm(
    app,
    kind: str,
    kind_label: str,
    source_widget: ScrolledText,
) -> None:
    if app._llm_submit_running:
        messagebox.showinfo("Submitting", "LLM request is running.")
        return
    raw_prompt = source_widget.get("1.0", "end-1c") or ""
    if not raw_prompt.strip():
        messagebox.showwarning("Empty content", f"{kind_label}涓嶈兘涓虹┖")
        return

    llm_prompt = app._build_dialog_llm_prompt(kind, raw_prompt)
    app._log_llm_prompts(f"{kind_label}(璁剧疆椤垫彁浜?", llm_prompt)
    app._append_llm_prompt_block_to_system_instruction(
        begin_tag=f"[LLM_PANEL_PROMPT_BEGIN][{kind_label}]",
        end_tag=f"[LLM_PANEL_PROMPT_END][{kind_label}]",
        llm_prompt=llm_prompt,
    )
    app._set_text_content(source_widget, "")
    app._append_ai_analysis_text(f"[LLM_PANEL_THINKING_BEGIN][{kind_label}]\n")
    app._llm_submit_running = True
    app._set_llm_generation_frozen(True)

    threading.Thread(
        target=app._submit_settings_panel_llm_worker,
        args=(kind, kind_label, source_widget, llm_prompt),
        daemon=True,
    ).start()


def submit_settings_panel_llm_worker(
    app,
    kind: str,
    kind_label: str,
    source_widget: ScrolledText,
    llm_prompt: str,
) -> None:
    result_text = ""
    thinking_text = ""
    error_text = ""
    thinking_seen = {"value": False}

    def on_thinking_chunk(chunk: str) -> None:
        if not chunk:
            return
        thinking_seen["value"] = True
        app.after(0, app._append_ai_analysis_text, chunk)

    def on_content_chunk(chunk: str) -> None:
        if not chunk:
            return
        app.after(0, app._append_text_to_widget, source_widget, chunk)

    try:
        result_text, thinking_text = app._call_direct_llm_for_system_instruction(
            llm_prompt,
            on_thinking_chunk=on_thinking_chunk,
            on_content_chunk=on_content_chunk,
        )
    except Exception as exc:
        error_text = str(exc)

    app.after(
        0,
        lambda: app._on_submit_settings_panel_llm_done(
            kind=kind,
            kind_label=kind_label,
            source_widget=source_widget,
            result_text=result_text,
            thinking_text=thinking_text,
            error_text=error_text,
            thinking_seen=bool(thinking_seen["value"]),
        ),
    )


def on_submit_settings_panel_llm_done(
    app,
    kind: str,
    kind_label: str,
    source_widget: ScrolledText,
    result_text: str,
    thinking_text: str,
    error_text: str,
    thinking_seen: bool,
) -> None:
    app._llm_submit_running = False
    if (not thinking_seen) and thinking_text:
        app._append_ai_analysis_text(thinking_text)
    app._append_ai_analysis_text(f"\n[LLM_PANEL_THINKING_END][{kind_label}]\n")

    if error_text:
        app._append_ai_analysis_text(f"[LLM_PANEL_ERROR][{kind_label}] {error_text}\n")
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] {kind_label} submit failed: {error_text}",
        )
        app._set_llm_generation_frozen(False)
        return

    app._set_text_content(source_widget, result_text or "")
    app._append_line(
        app.log_text,
        (
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] {kind_label} submit success: "
            f"{app._sanitize_inline_text(result_text) or '(empty reply)'}"
        ),
    )
    app._refresh_system_instruction()
    app._set_llm_generation_frozen(False)


def strip_panel_llm_debug_blocks(raw_text: str) -> str:
    lines: list[str] = []
    skip_block = False
    for line in (raw_text or "").splitlines():
        marker = line.strip()
        if marker == "[LLM_THINKING_BEGIN]" or marker == "[LLM_RESULT_BEGIN]":
            skip_block = True
            continue
        if marker == "[LLM_THINKING_END]" or marker == "[LLM_RESULT_END]":
            skip_block = False
            continue
        if marker.startswith("[LLM_ERROR]"):
            continue
        if skip_block:
            continue
        lines.append(line)
    return "\n".join(lines)


def build_system_instruction_prompt_for_submit(app) -> str:
    raw_text = app.system_instruction_text.get("1.0", "end-1c") or ""
    return app._strip_llm_asr_debug_blocks(raw_text).strip()


def append_system_instruction_text(app, text: str) -> None:
    if not text:
        return
    widget = app.system_instruction_text
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    widget.insert("end", text)
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")


def append_ai_analysis_text(app, text: str) -> None:
    if not text:
        return
    widget = app.ai_analysis_text
    if not isinstance(widget, ScrolledText):
        return
    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    widget.insert("end", text)
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
    widget.see("end")


def append_text_to_widget(widget: ScrolledText, text: str) -> None:
    if (not text) or (not isinstance(widget, ScrolledText)):
        return
    try:
        prev_state = str(widget.cget("state"))
        widget.configure(state="normal")
        widget.insert("end", text)
        widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
        widget.see("end")
    except Exception:
        return


def set_llm_generation_frozen(app, frozen: bool) -> None:
    if frozen:
        app._llm_freeze_depth += 1
        if app._llm_freeze_depth > 1:
            return
        try:
            app.configure(cursor="watch")
        except Exception:
            pass
        for widget in (
            app.customer_profile_text,
            app.workflow_text,
            app.system_instruction_text,
            app.ai_analysis_text,
            app.intent_system_text,
            app.intent_prompt_text,
            app.intent_text,
            app.dialog_conversation_text,
            app.dialog_intent_text,
        ):
            if not isinstance(widget, (ScrolledText, tk.Text)):
                continue
            try:
                prev_state = str(widget.cget("state"))
                prev_bg = str(widget.cget("bg"))
                prev_fg = str(widget.cget("fg"))
                prev_insert = str(widget.cget("insertbackground"))
                app._llm_freeze_widget_style[widget] = (prev_state, prev_bg, prev_fg, prev_insert)
                widget.configure(
                    state="disabled",
                    bg="#eef2f7",
                    fg="#6b7280",
                    insertbackground="#6b7280",
                )
            except Exception:
                pass
        return

    if app._llm_freeze_depth <= 0:
        return
    app._llm_freeze_depth -= 1
    if app._llm_freeze_depth > 0:
        return
    try:
        app.configure(cursor="")
    except Exception:
        pass
    for widget, style in list(app._llm_freeze_widget_style.items()):
        prev_state, prev_bg, prev_fg, prev_insert = style
        try:
            widget.configure(bg=prev_bg, fg=prev_fg, insertbackground=prev_insert)
            widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
        except Exception:
            pass
    app._llm_freeze_widget_style.clear()


def append_llm_prompt_block_to_system_instruction(
    app,
    begin_tag: str,
    end_tag: str,
    llm_prompt: str,
) -> None:
    prompt_text = llm_prompt if llm_prompt is not None else ""
    app._append_ai_analysis_text(f"\n{begin_tag}\n{prompt_text}\n{end_tag}\n")


def append_asr_submit_thinking_chunk(app, chunk: str) -> None:
    if not chunk:
        return
    app._asr_submit_thinking_seen = True
    app._append_ai_analysis_text(chunk)


def trigger_customer_profile_submit_from_asr(app) -> None:
    if app._llm_submit_running:
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] ASR submit ignored: request already running",
        )
        return
    prompt = app._build_system_instruction_prompt_for_submit()
    if not prompt:
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] ASR submit ignored: empty system instruction",
        )
        return
    llm_prompt = app._build_dialog_llm_prompt(kind="customer_profile", instruction_text=prompt)
    app._log_llm_prompts("绯荤粺鎸囦护(ASR鎻愪氦)", llm_prompt)
    app._append_llm_prompt_block_to_system_instruction(
        begin_tag="[LLM_ASR_PROMPT_BEGIN]",
        end_tag="[LLM_ASR_PROMPT_END]",
        llm_prompt=llm_prompt,
    )
    app._set_text_content(app.customer_profile_text, "")
    app._append_ai_analysis_text("[LLM_ASR_THINKING_BEGIN]\n")
    app._asr_submit_thinking_seen = False
    app._llm_submit_running = True
    app._set_llm_generation_frozen(True)
    app._append_line(
        app.log_text,
        f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] ASR submit started",
    )
    threading.Thread(
        target=app._trigger_customer_profile_submit_from_asr_worker,
        args=(llm_prompt,),
        daemon=True,
    ).start()


def trigger_customer_profile_submit_from_asr_worker(app, llm_prompt: str) -> None:
    result_text = ""
    thinking_text = ""
    error_text = ""
    try:
        result_text, thinking_text = app._call_direct_llm_for_system_instruction(
            llm_prompt,
            on_thinking_chunk=lambda chunk: app.after(0, app._append_asr_submit_thinking_chunk, chunk),
            on_content_chunk=lambda chunk: app.after(0, app._append_text_to_widget, app.customer_profile_text, chunk),
        )
    except Exception as exc:
        error_text = str(exc)
    app.after(
        0,
        lambda: app._on_customer_profile_submit_from_asr_done(result_text, thinking_text, error_text),
    )


def on_customer_profile_submit_from_asr_done(
    app,
    result_text: str,
    thinking_text: str,
    error_text: str,
) -> None:
    app._llm_submit_running = False
    if (not app._asr_submit_thinking_seen) and thinking_text:
        app._append_ai_analysis_text(thinking_text)
    app._append_ai_analysis_text("\n[LLM_ASR_THINKING_END]\n")
    if error_text:
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] ASR submit failed: {error_text}",
        )
        app._append_ai_analysis_text(f"[LLM_ASR_ERROR] {error_text}\n")
        app._set_llm_generation_frozen(False)
        return
    app._set_text_content(app.customer_profile_text, result_text or "")
    app._refresh_system_instruction()
    summary = app._sanitize_inline_text(result_text) or "(empty reply)"
    app._append_line(
        app.log_text,
        (
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] ASR submit success: {summary} "
            f"| thinking_chars={len(thinking_text or '')}"
        ),
    )
    app._set_llm_generation_frozen(False)


def append_dialog_output_chunk(app, dialog: dict[str, object], text: str) -> None:
    if not text:
        return
    win = dialog.get("window")
    if isinstance(win, tk.Toplevel):
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
    output_editor = dialog.get("output_editor")
    if not isinstance(output_editor, ScrolledText):
        return
    try:
        prev_state = str(output_editor.cget("state"))
        output_editor.configure(state="normal")
        output_editor.insert("end", text)
        output_editor.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
        output_editor.see("end")
    except Exception:
        pass


def log_llm_prompts(app, kind_label: str, llm_prompt: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    app._append_line(app.log_text, f"[{ts}] [LLM_PROMPT][{kind_label}] PROMPT_BEGIN")
    for line in (llm_prompt or "").splitlines():
        app._append_line(app.log_text, f"[{ts}] [LLM_PROMPT][{kind_label}] {line}")
    app._append_line(app.log_text, f"[{ts}] [LLM_PROMPT][{kind_label}] PROMPT_END")

