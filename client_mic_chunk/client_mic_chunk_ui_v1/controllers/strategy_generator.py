from __future__ import annotations

import threading
from datetime import datetime

import tkinter as tk
import tkinter.font as tkfont
from tkinter import BOTH, LEFT, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
try:
    from .ui_widgets import TtlScrolledText
except Exception:
    from ui_widgets import TtlScrolledText


def render_conversation_strategy_history_panel(app) -> None:
    widget = app.conversation_strategy_history_text
    if not isinstance(widget, ScrolledText):
        return
    history_items = app._conversation_strategy_history
    if not history_items:
        text = "暂无历史提交"
    else:
        lines: list[str] = []
        for idx, item in enumerate(history_items, start=1):
            created_at = str(item.get("created_at", "") or "").strip()
            label = f"[{idx}] {created_at}" if created_at else f"[{idx}]"
            instruction = str(item.get("instruction", "") or "").strip() or "-"
            response = str(item.get("response", "") or "").strip() or "-"
            lines.append(f"{label} 指令")
            lines.append(instruction)
            lines.append(f"{label} 返回")
            lines.append(response)
            if idx < len(history_items):
                lines.append("")
        text = "\n".join(lines)

    prev_state = str(widget.cget("state"))
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", text)
    widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "disabled")
    widget.see("end")


def get_conversation_strategy_history_for_tab(app, tab_id: str) -> list[dict[str, str]]:
    if tab_id and (tab_id in app._conversation_tabs):
        context = app._conversation_tabs.get(tab_id)
        if context is not None:
            return context.conversation_strategy_history
    return app._conversation_strategy_history


def render_conversation_strategy_dialog_history(app, dialog: dict[str, object]) -> None:
    history_widget = dialog.get("history_text")
    if not isinstance(history_widget, ScrolledText):
        return
    tab_id = str(dialog.get("tab_id", "") or "")
    history = app._get_conversation_strategy_history_for_tab(tab_id)
    history_widget.configure(state="normal")
    history_widget.delete("1.0", "end")
    app._update_conversation_strategy_dialog_history_tags(history_widget)
    history_widget.tag_configure(
        "cs_hint",
        justify="center",
        foreground="#6b7280",
        spacing1=10,
        spacing3=10,
    )
    if not history:
        history_widget.insert("end", "暂无历史记录\n", ("cs_hint",))
    else:
        width = int(history_widget.winfo_width() or history_widget.winfo_reqwidth() or 900)
        max_bubble_width = max(240, int(width * (2.0 / 3.0)) - 28)
        for item in history:
            instruction = str(item.get("instruction", "") or "-")
            response = str(item.get("response", "") or "-")
            wrapped_instruction = app._wrap_text_for_strategy_history_bubble(
                text=instruction,
                history_widget=history_widget,
                max_width_px=max_bubble_width,
            )
            wrapped_response = app._wrap_text_for_strategy_history_bubble(
                text=response,
                history_widget=history_widget,
                max_width_px=max_bubble_width,
            )
            history_widget.insert("end", f"{wrapped_instruction}\n\n", ("cs_right_bubble",))
            history_widget.insert("end", f"{wrapped_response}\n\n", ("cs_left_bubble",))
    history_widget.configure(state="normal")
    history_widget.see("end")


def prepare_live_conversation_strategy_response_bubble(app, source_widget: ScrolledText) -> None:
    dialog = getattr(app, "_conversation_strategy_dialog", None)
    if not isinstance(dialog, dict):
        return
    if dialog.get("output") is not source_widget:
        return
    if str(dialog.get("live_response_phase", "")) == "content":
        return
    start_idx = str(dialog.get("live_response_start", "") or "")
    if not start_idx:
        dialog["live_response_phase"] = "content"
        return
    try:
        source_widget.configure(state="normal")
        source_widget.delete(start_idx, "end-1c")
    except Exception:
        return
    dialog["live_response_phase"] = "content"


def append_live_conversation_strategy_thinking_chunk(app, source_widget: ScrolledText, chunk: str) -> None:
    app._append_text_to_widget_with_tag(source_widget, chunk, "cs_left_bubble")


def append_live_conversation_strategy_content_chunk(app, source_widget: ScrolledText, chunk: str) -> None:
    app._prepare_live_conversation_strategy_response_bubble(source_widget)
    app._append_text_to_widget_with_tag(source_widget, chunk, "cs_left_bubble")


def append_conversation_strategy_history(
    app,
    instruction_text: str,
    response_text: str,
) -> None:
    app._conversation_strategy_history.append(
        {
            "instruction": str(instruction_text or ""),
            "response": str(response_text or ""),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    if len(app._conversation_strategy_history) > 50:
        del app._conversation_strategy_history[:-50]


def build_conversation_strategy_prompt_with_history(app, instruction_text: str, tab_id: str = "") -> str:
    history_items = app._get_conversation_strategy_history_for_tab(tab_id)
    history_lines: list[str] = [
        "请根据历史记录和当前新指令，生成更新后的完整对话策略。",
        "输出要求：只输出最终策略正文，不要解释。",
    ]
    if history_items:
        history_lines.append("以下是历史提交：")
        for idx, item in enumerate(history_items, start=1):
            history_lines.append(f"[历史指令{idx}]")
            history_lines.append(str(item.get("instruction", "") or ""))
            history_lines.append(f"[历史返回{idx}]")
            history_lines.append(str(item.get("response", "") or ""))
    history_lines.append("[当前新指令]")
    history_lines.append(str(instruction_text or "").strip())
    merged_instruction = "\n".join(history_lines)
    return app._build_dialog_llm_prompt(kind="workflow", instruction_text=merged_instruction)


def submit_conversation_strategy_from_panel(app) -> None:
    app._open_conversation_strategy_generator_dialog()


def open_conversation_strategy_generator_dialog(
    app,
    *,
    ui_font_family: str,
    ui_font_size: int,
) -> None:
    existing = getattr(app, "_conversation_strategy_dialog", None)
    if isinstance(existing, dict):
        win = existing.get("win")
        if isinstance(win, tk.Toplevel) and win.winfo_exists():
            win.deiconify()
            win.lift()
            win.focus_force()
            try:
                win.grab_set()
            except Exception:
                pass
            return

    win = tk.Toplevel(app)
    win.title("对话策略生成")
    screen_w = int(app.winfo_screenwidth() or 1600)
    screen_h = int(app.winfo_screenheight() or 900)
    width = int(screen_w * 2 / 3)
    height = int(screen_h * 2 / 3)
    x = int((screen_w - width) / 2)
    y = int((screen_h - height) / 2)
    win.geometry(f"{width}x{height}+{x}+{y}")
    win.minsize(600, 400)
    win.configure(bg="#f3f4f6")
    try:
        win.transient(app)
    except Exception:
        pass
    try:
        win.grab_set()
    except Exception:
        pass

    root = ttk.Frame(win, style="App.TFrame", padding=(14, 12, 14, 12))
    root.pack(fill=BOTH, expand=True)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    top_bar = ttk.Frame(root, style="Panel.TFrame", padding=(4, 2, 4, 6))
    top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    top_bar.columnconfigure(0, weight=1)
    ttk.Label(top_bar, text="对话策略生成", background="#f3f4f6", foreground="#111827").grid(row=0, column=0, sticky="w")
    save_btn = ttk.Button(
        top_bar,
        text="保存",
        command=lambda: app._save_conversation_strategy_dialog(),
        style="Primary.TButton",
    )
    save_btn.grid(row=0, column=1, sticky="e")

    llm_history_box = tk.Frame(
        root,
        bg="#f8fafc",
        highlightthickness=1,
        highlightbackground="#dde3ea",
        highlightcolor="#dde3ea",
        bd=0,
    )
    llm_history_box.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
    llm_history_box.grid_columnconfigure(0, weight=1)
    llm_history_box.grid_rowconfigure(0, weight=1)
    llm_history_text = TtlScrolledText(
        llm_history_box,
        wrap="word",
        state="normal",
        bg="#f8fafc",
        fg="#111827",
        insertbackground="#111827",
        insertwidth=0,
        relief="flat",
        highlightthickness=0,
        takefocus=0,
        borderwidth=0,
        padx=10,
        pady=10,
        font=(ui_font_family, ui_font_size),
    )
    llm_history_text.grid(row=0, column=0, sticky="nsew")
    llm_history_text.bind("<KeyPress>", lambda _event: "break", add="+")
    llm_history_text.bind("<<Paste>>", lambda _event: "break", add="+")
    llm_history_text.bind("<<Cut>>", lambda _event: "break", add="+")
    llm_history_text.bind(
        "<Configure>",
        lambda _event, widget=llm_history_text: app._update_conversation_strategy_dialog_history_tags(widget),
        add="+",
    )

    bottom = ttk.Frame(root, style="Panel.TFrame")
    bottom.grid(row=2, column=0, sticky="ew")
    bottom.columnconfigure(0, weight=1)
    bottom.rowconfigure(0, weight=1)
    input_box = tk.Frame(
        bottom,
        bg="#ffffff",
        highlightthickness=1,
        highlightbackground="#d6dce5",
        highlightcolor="#d6dce5",
        bd=0,
    )
    input_box.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    input_box.grid_columnconfigure(0, weight=1)
    input_box.grid_rowconfigure(0, weight=1)
    input_text = TtlScrolledText(
        input_box,
        wrap="word",
        state="normal",
        bg="#ffffff",
        fg="#111827",
        insertbackground="#111827",
        relief="flat",
        highlightthickness=0,
        borderwidth=0,
        height=6,
        padx=10,
        pady=10,
        font=(ui_font_family, ui_font_size),
    )
    input_text.grid(row=0, column=0, sticky="nsew")

    def _on_strategy_input_return(event: object) -> str:
        if getattr(event, "state", 0) & 0x1:
            return ""
        app._generate_conversation_strategy_in_dialog()
        return "break"

    input_text.bind("<Return>", _on_strategy_input_return)

    submit_wrap = ttk.Frame(bottom, style="Panel.TFrame")
    submit_wrap.grid(row=0, column=1, sticky="se")
    submit_btn = ttk.Button(
        submit_wrap,
        text="提交",
        command=lambda: app._generate_conversation_strategy_in_dialog(),
        style="Primary.TButton",
    )
    submit_btn.pack(anchor="se")

    dialog_tab_id = app._bound_conversation_tab_id or app._active_conversation_tab_id
    history_items = app._get_conversation_strategy_history_for_tab(dialog_tab_id)
    latest_result = ""
    if history_items:
        latest_result = str(history_items[-1].get("response", "") or "").strip()
    app._conversation_strategy_dialog = {
        "win": win,
        "history_text": llm_history_text,
        "output": llm_history_text,
        "input": input_text,
        "submit_btn": submit_btn,
        "save_btn": save_btn,
        "tab_id": dialog_tab_id,
        "last_result": latest_result,
        "last_instruction": "",
    }
    def _on_strategy_win_map(event: object = None) -> None:
        win.unbind("<Map>")
        try:
            win.update_idletasks()
        except Exception:
            pass
        d = getattr(app, "_conversation_strategy_dialog", None)
        if isinstance(d, dict):
            app._render_conversation_strategy_dialog_history(d)

    win.bind("<Map>", _on_strategy_win_map)

    def _close_dialog() -> None:
        current = getattr(app, "_conversation_strategy_dialog", None)
        if isinstance(current, dict) and (current.get("win") is win):
            app._conversation_strategy_dialog = None
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass

    win.protocol("WM_DELETE_WINDOW", _close_dialog)


def generate_conversation_strategy_in_dialog(app) -> None:
    if app._llm_submit_running:
        messagebox.showinfo("Submitting", "LLM request is running.")
        return
    dialog = getattr(app, "_conversation_strategy_dialog", None)
    if not isinstance(dialog, dict):
        return
    win = dialog.get("win")
    if not isinstance(win, tk.Toplevel) or (not win.winfo_exists()):
        app._conversation_strategy_dialog = None
        return
    output_widget = dialog.get("output")
    input_widget = dialog.get("input")
    if not isinstance(output_widget, ScrolledText):
        return
    if not isinstance(input_widget, ScrolledText):
        return
    instruction_text = (input_widget.get("1.0", "end-1c") or "").strip()
    if not instruction_text:
        messagebox.showwarning("Empty content", "请输入指令后再提交。")
        return
    input_widget.delete("1.0", "end")
    submit_tab_id = str(dialog.get("tab_id", "") or (app._bound_conversation_tab_id or app._active_conversation_tab_id))
    llm_prompt = app._build_conversation_strategy_prompt_with_history(instruction_text, tab_id=submit_tab_id)
    kind_label = "对话策略"
    app._log_llm_prompts(f"{kind_label}(对话页提交)", llm_prompt)
    app._append_llm_prompt_block_to_system_instruction(
        begin_tag=f"[LLM_PANEL_PROMPT_BEGIN][{kind_label}]",
        end_tag=f"[LLM_PANEL_PROMPT_END][{kind_label}]",
        llm_prompt=llm_prompt,
    )
    dialog["last_instruction"] = instruction_text
    app._render_conversation_strategy_dialog_history(dialog)
    app._update_conversation_strategy_dialog_history_tags(output_widget)
    app._append_text_to_widget_with_tag(
        output_widget,
        f"{instruction_text}\n\n",
        "cs_right_bubble",
    )
    dialog["live_response_start"] = output_widget.index("end-1c")
    dialog["live_response_phase"] = "thinking"
    app._append_text_to_widget_with_tag(output_widget, "思考中...\n", "cs_left_bubble")
    app._llm_submit_running = True
    threading.Thread(
        target=app._submit_conversation_strategy_llm_worker,
        args=(submit_tab_id, output_widget, instruction_text, llm_prompt),
        daemon=True,
    ).start()


def submit_conversation_strategy_llm_worker(
    app,
    submit_tab_id: str,
    source_widget: ScrolledText,
    instruction_text: str,
    llm_prompt: str,
) -> None:
    result_text = ""
    thinking_text = ""
    error_text = ""
    thinking_seen = {"value": False}
    content_seen = {"value": False}

    def on_thinking_chunk(chunk: str) -> None:
        if not chunk:
            return
        thinking_seen["value"] = True
        app.after(0, app._append_live_conversation_strategy_thinking_chunk, source_widget, chunk)

    def on_content_chunk(chunk: str) -> None:
        if not chunk:
            return
        content_seen["value"] = True
        app.after(0, app._append_live_conversation_strategy_content_chunk, source_widget, chunk)

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
        lambda: app._on_submit_conversation_strategy_llm_done(
            submit_tab_id=submit_tab_id,
            source_widget=source_widget,
            instruction_text=instruction_text,
            result_text=result_text,
            thinking_text=thinking_text,
            error_text=error_text,
            thinking_seen=bool(thinking_seen["value"]),
            content_seen=bool(content_seen["value"]),
        ),
    )


def on_submit_conversation_strategy_llm_done(
    app,
    submit_tab_id: str,
    source_widget: ScrolledText,
    instruction_text: str,
    result_text: str,
    thinking_text: str,
    error_text: str,
    thinking_seen: bool,
    content_seen: bool,
) -> None:
    app._llm_submit_running = False
    kind_label = "对话策略"
    if (not thinking_seen) and thinking_text:
        app._append_live_conversation_strategy_thinking_chunk(source_widget, thinking_text)

    if error_text:
        messagebox.showerror("LLM请求失败", error_text)
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] {kind_label} submit failed: {error_text}",
        )
        return

    if not content_seen:
        app._prepare_live_conversation_strategy_response_bubble(source_widget)
        if result_text:
            app._append_text_to_widget_with_tag(source_widget, str(result_text), "cs_left_bubble")
    if submit_tab_id and (submit_tab_id in app._conversation_tabs):
        with app._using_conversation_tab_context(submit_tab_id):
            app._append_conversation_strategy_history(instruction_text=instruction_text, response_text=result_text or "")
            app._render_conversation_strategy_history_panel()
    else:
        app._append_conversation_strategy_history(instruction_text=instruction_text, response_text=result_text or "")
        app._render_conversation_strategy_history_panel()
    dialog = getattr(app, "_conversation_strategy_dialog", None)
    if isinstance(dialog, dict):
        dialog["last_result"] = str(result_text or "")
        dialog_tab_id = str(dialog.get("tab_id", "") or "")
        if (not dialog_tab_id) or (dialog_tab_id == submit_tab_id):
            app._render_conversation_strategy_dialog_history(dialog)
    app._append_line(
        app.log_text,
        (
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] {kind_label} submit success: "
            f"{app._sanitize_inline_text(result_text) or '(empty reply)'}"
        ),
    )


def save_conversation_strategy_dialog(app) -> None:
    dialog = getattr(app, "_conversation_strategy_dialog", None)
    if not isinstance(dialog, dict):
        return
    win = dialog.get("win")
    if not isinstance(win, tk.Toplevel) or (not win.winfo_exists()):
        app._conversation_strategy_dialog = None
        return
    final_text = str(dialog.get("last_result", "") or "").strip()
    if not final_text:
        messagebox.showwarning("未生成结果", "请先点击“提交”并等待返回结果。")
        return
    tab_id = str(dialog.get("tab_id", "") or (app._bound_conversation_tab_id or app._active_conversation_tab_id))
    if tab_id and (tab_id in app._conversation_tabs):
        with app._using_conversation_tab_context(tab_id):
            if isinstance(app.conversation_workflow_text, ScrolledText):
                app._set_text_content(app.conversation_workflow_text, final_text)
    else:
        if isinstance(app.conversation_workflow_text, ScrolledText):
            app._set_text_content(app.conversation_workflow_text, final_text)
    app._conversation_strategy_dialog = None
    try:
        win.grab_release()
    except Exception:
        pass
    try:
        win.destroy()
    except Exception:
        pass
