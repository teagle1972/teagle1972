from __future__ import annotations

from datetime import datetime
import threading

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
try:
    from .ui_widgets import TtlScrolledText
except Exception:
    from ui_widgets import TtlScrolledText


def _wrap_bubble_text_by_px(widget: ScrolledText, text: str, max_width_px: int) -> str:
    raw_text = str(text or "").replace("\r", "")
    max_px = max(140, int(max_width_px or 0))
    try:
        font = tkfont.nametofont(str(widget.cget("font")))
    except Exception:
        return raw_text
    wrapped_lines: list[str] = []
    for paragraph in raw_text.split("\n"):
        if not paragraph:
            wrapped_lines.append("")
            continue
        current = ""
        for ch in paragraph:
            candidate = current + ch
            if (not current) or (font.measure(candidate) <= max_px):
                current = candidate
                continue
            wrapped_lines.append(current)
            current = ch
        if current:
            wrapped_lines.append(current)
    return "\n".join(wrapped_lines)


def _draw_rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> int:
    r = max(4, int(radius))
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return int(canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs))


def _render_customer_profile_bubble(
    history_widget: ScrolledText,
    canvas: tk.Canvas,
    header: str,
    body_text: str,
    is_right: bool,
) -> int:
    widget_width = int(history_widget.winfo_width() or history_widget.winfo_reqwidth() or 900)
    host_width = max(320, widget_width - 20)
    max_bubble_width = max(240, int(host_width * 0.68))
    text_limit = max(180, max_bubble_width - 28)
    body = _wrap_bubble_text_by_px(history_widget, body_text, text_limit).strip("\n")
    content = "\n".join(x for x in [header, body] if x) if (header or body) else ""
    try:
        font = tkfont.nametofont(str(history_widget.cget("font")))
    except Exception:
        font = tkfont.nametofont("TkDefaultFont")
    line_h = int(font.metrics("linespace") or 18)
    widest = 0
    for line in content.split("\n"):
        widest = max(widest, int(font.measure(line)))
    bubble_w = min(max_bubble_width, max(190, widest + 26))
    bubble_h = max(40, int(len(content.split("\n")) * line_h + 24))
    fill = "#e9eef3" if is_right else str(history_widget.cget("bg"))
    edge = "#c7d0db" if is_right else ""
    canvas.configure(
        width=bubble_w + 2,
        height=bubble_h + 2,
        bg=str(history_widget.cget("bg")),
        bd=0,
        highlightthickness=0,
    )
    canvas.delete("all")
    _draw_rounded_rect(canvas, 1, 1, bubble_w, bubble_h, 12, fill=fill, outline=edge, width=1)
    canvas.create_text(14, 12, anchor="nw", text=content, fill="#1f2937", font=font)
    return bubble_h + 6


def _insert_customer_profile_bubble(
    app,
    history_widget: ScrolledText,
    *,
    header: str,
    body_text: str,
    is_right: bool,
    keep_key: str | None = None,
) -> None:
    bg = str(history_widget.cget("bg"))
    widget_width = int(history_widget.winfo_width() or history_widget.winfo_reqwidth() or 900)
    host_width = max(320, widget_width - 20)
    row = tk.Frame(history_widget, bg=bg, width=host_width, height=1, bd=0, highlightthickness=0)
    row.pack_propagate(False)
    canvas = tk.Canvas(row, bd=0, highlightthickness=0, bg=bg)
    canvas.pack(anchor=("e" if is_right else "w"), padx=((0, 8) if is_right else (8, 0)), pady=(2, 2))
    row.configure(height=_render_customer_profile_bubble(history_widget, canvas, header, body_text, is_right))
    history_widget.window_create("end", window=row)
    history_widget.insert("end", "\n")
    dialog = getattr(app, "_conversation_customer_profile_dialog", None)
    if isinstance(dialog, dict):
        refs = dialog.setdefault("_bubble_refs", [])
        if isinstance(refs, list):
            refs.append((row, canvas))
        if keep_key:
            dialog[keep_key] = {
                "row": row,
                "canvas": canvas,
                "header": header,
                "text": str(body_text or ""),
                "is_right": bool(is_right),
            }


def _update_live_customer_profile_bubble(
    app,
    history_widget: ScrolledText,
    *,
    replace: bool,
    chunk: str,
    switch_to_content: bool,
) -> None:
    dialog = getattr(app, "_conversation_customer_profile_dialog", None)
    if not isinstance(dialog, dict):
        return
    if dialog.get("output") is not history_widget:
        return
    bubble = dialog.get("live_response_bubble")
    if not isinstance(bubble, dict):
        return
    row = bubble.get("row")
    canvas = bubble.get("canvas")
    if (not isinstance(row, tk.Frame)) or (not isinstance(canvas, tk.Canvas)):
        return
    current = str(bubble.get("text", "") or "")
    if replace:
        current = str(chunk or "")
    else:
        if switch_to_content and str(dialog.get("live_response_phase", "")) != "content":
            current = ""
            dialog["live_response_phase"] = "content"
        current += str(chunk or "")
    bubble["text"] = current
    row.configure(
        height=_render_customer_profile_bubble(
            history_widget,
            canvas,
            str(bubble.get("header", "")),
            current,
            bool(bubble.get("is_right", False)),
        )
    )
    history_widget.see("end")


def get_conversation_customer_profile_history_for_tab(app, tab_id: str) -> list[dict[str, str]]:
    if tab_id and (tab_id in app._conversation_tabs):
        context = app._conversation_tabs.get(tab_id)
        if context is not None:
            return context.conversation_customer_profile_history
    return app._conversation_customer_profile_history


def render_conversation_customer_profile_dialog_history(app, dialog: dict[str, object]) -> None:
    history_widget = dialog.get("history_text")
    if not isinstance(history_widget, ScrolledText):
        return
    tab_id = str(dialog.get("tab_id", "") or "")
    history = app._get_conversation_customer_profile_history_for_tab(tab_id)
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
        max_bubble_width = max(width // 2, int(width * (2.0 / 3.0)) - 28)
        for idx, item in enumerate(history, start=1):
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
            history_widget.insert("end", "\n")
            history_widget.insert("end", f"{wrapped_response}\n\n", ("cs_left_bubble",))
    history_widget.configure(state="normal")
    history_widget.see("end")


def append_conversation_customer_profile_history(
    app,
    instruction_text: str,
    response_text: str,
) -> None:
    app._conversation_customer_profile_history.append(
        {
            "instruction": str(instruction_text or ""),
            "response": str(response_text or ""),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    if len(app._conversation_customer_profile_history) > 50:
        del app._conversation_customer_profile_history[:-50]


def build_conversation_customer_profile_prompt_with_history(app, instruction_text: str, tab_id: str = "") -> str:
    history_items = app._get_conversation_customer_profile_history_for_tab(tab_id)
    history_lines: list[str] = [
        "请根据历史记录和当前新指令，生成更新后的完整客户画像。",
        "输出要求：只输出最终客户画像正文，首行必须是“客户画像”。",
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
    return app._build_dialog_llm_prompt(kind="customer_profile", instruction_text=merged_instruction)


def get_conversation_intent_generator_history_for_tab(app, tab_id: str) -> list[dict[str, str]]:
    if tab_id and (tab_id in app._conversation_tabs):
        context = app._conversation_tabs.get(tab_id)
        if context is not None:
            return context.conversation_intent_generator_history
    return app._conversation_intent_generator_history


def render_conversation_intent_dialog_history(app, dialog: dict[str, object]) -> None:
    history_widget = dialog.get("history_text")
    if not isinstance(history_widget, ScrolledText):
        return
    tab_id = str(dialog.get("tab_id", "") or "")
    history = app._get_conversation_intent_generator_history_for_tab(tab_id)
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
        max_bubble_width = max(width // 2, int(width * (2.0 / 3.0)) - 28)
        for idx, item in enumerate(history, start=1):
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
            history_widget.insert("end", "\n")
            history_widget.insert("end", f"{wrapped_response}\n\n", ("cs_left_bubble",))
    history_widget.configure(state="normal")
    history_widget.see("end")


def append_conversation_intent_generator_history(
    app,
    instruction_text: str,
    response_text: str,
) -> None:
    app._conversation_intent_generator_history.append(
        {
            "instruction": str(instruction_text or ""),
            "response": str(response_text or ""),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    if len(app._conversation_intent_generator_history) > 50:
        del app._conversation_intent_generator_history[:-50]


def build_conversation_intent_prompt_with_history(app, instruction_text: str, tab_id: str = "") -> str:
    history_items = app._get_conversation_intent_generator_history_for_tab(tab_id)
    profile_text = (
        app.conversation_customer_profile_text.get("1.0", "end-1c")
        if isinstance(app.conversation_customer_profile_text, ScrolledText)
        else ""
    )
    workflow_text = (
        app.conversation_workflow_text.get("1.0", "end-1c")
        if isinstance(app.conversation_workflow_text, ScrolledText)
        else ""
    )
    context_profile = app._strip_panel_llm_debug_blocks(profile_text or "").strip()
    context_workflow = app._strip_panel_llm_debug_blocks(workflow_text or "").strip()
    history_lines: list[str] = [
        "请根据历史记录和当前新指令，生成更新后的客户意图标签列表。",
        "输出要求：仅输出最终意图标签列表，每行一个，不要解释，不要 Markdown。",
    ]
    if context_profile:
        history_lines.extend(["【客户画像】", context_profile])
    if context_workflow:
        history_lines.extend(["【对话策略】", context_workflow])
    if history_items:
        history_lines.append("以下是历史提交：")
        for idx, item in enumerate(history_items, start=1):
            history_lines.append(f"[历史指令{idx}]")
            history_lines.append(str(item.get("instruction", "") or ""))
            history_lines.append(f"[历史返回{idx}]")
            history_lines.append(str(item.get("response", "") or ""))
    history_lines.append("[当前新指令]")
    history_lines.append(str(instruction_text or "").strip())
    return "\n".join(history_lines)


def open_conversation_customer_profile_generator_dialog(
    app,
    *,
    ui_font_family: str,
    ui_font_size: int,
) -> None:
    existing = getattr(app, "_conversation_customer_profile_dialog", None)
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
    win.title("客户画像生成")
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
    root.pack(fill=tk.BOTH, expand=True)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    top_bar = ttk.Frame(root, style="Panel.TFrame", padding=(4, 2, 4, 6))
    top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    top_bar.columnconfigure(0, weight=1)
    ttk.Label(top_bar, text="客户画像生成", background="#f3f4f6", foreground="#111827").grid(row=0, column=0, sticky="w")
    save_btn = ttk.Button(
        top_bar,
        text="保存",
        command=lambda: app._save_conversation_customer_profile_dialog(),
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
        wrap="char",
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

    def _on_input_return(event: object) -> str:
        if getattr(event, "state", 0) & 0x1:
            return ""
        app._generate_conversation_customer_profile_in_dialog()
        return "break"

    input_text.bind("<Return>", _on_input_return)

    submit_wrap = ttk.Frame(bottom, style="Panel.TFrame")
    submit_wrap.grid(row=0, column=1, sticky="se")
    submit_btn = ttk.Button(
        submit_wrap,
        text="提交",
        command=lambda: app._generate_conversation_customer_profile_in_dialog(),
        style="Primary.TButton",
    )
    submit_btn.pack(anchor="se")

    dialog_tab_id = app._bound_conversation_tab_id or app._active_conversation_tab_id
    history_items = app._get_conversation_customer_profile_history_for_tab(dialog_tab_id)
    latest_result = ""
    if history_items:
        latest_result = str(history_items[-1].get("response", "") or "").strip()
    app._conversation_customer_profile_dialog = {
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
    def _on_win_map(event: object = None) -> None:
        win.unbind("<Map>")
        try:
            win.update_idletasks()
        except Exception:
            pass
        d = getattr(app, "_conversation_customer_profile_dialog", None)
        if isinstance(d, dict):
            app._render_conversation_customer_profile_dialog_history(d)

    win.bind("<Map>", _on_win_map)

    def _close_dialog() -> None:
        current = getattr(app, "_conversation_customer_profile_dialog", None)
        if isinstance(current, dict) and (current.get("win") is win):
            app._conversation_customer_profile_dialog = None
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass

    win.protocol("WM_DELETE_WINDOW", _close_dialog)


def generate_conversation_customer_profile_in_dialog(app) -> None:
    if app._llm_submit_running:
        messagebox.showinfo("Submitting", "LLM request is running.")
        return
    dialog = getattr(app, "_conversation_customer_profile_dialog", None)
    if not isinstance(dialog, dict):
        return
    win = dialog.get("win")
    if not isinstance(win, tk.Toplevel) or (not win.winfo_exists()):
        app._conversation_customer_profile_dialog = None
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
    llm_prompt = app._build_conversation_customer_profile_prompt_with_history(instruction_text, tab_id=submit_tab_id)
    kind_label = "客户画像"
    app._log_llm_prompts(f"{kind_label}(对话页提交)", llm_prompt)
    app._append_llm_prompt_block_to_system_instruction(
        begin_tag=f"[LLM_PANEL_PROMPT_BEGIN][{kind_label}]",
        end_tag=f"[LLM_PANEL_PROMPT_END][{kind_label}]",
        llm_prompt=llm_prompt,
    )
    dialog["last_instruction"] = instruction_text
    app._render_conversation_customer_profile_dialog_history(dialog)
    app._update_conversation_strategy_dialog_history_tags(output_widget)
    app._append_text_to_widget_with_tag(
        output_widget,
        f"{instruction_text}\n\n",
        "cs_right_bubble",
    )
    output_widget.insert("end", "\n")
    dialog["live_response_start"] = output_widget.index("end-1c")
    dialog["live_response_phase"] = "thinking"
    app._append_text_to_widget_with_tag(output_widget, "思考中...\n", "cs_left_bubble")
    app._llm_submit_running = True
    threading.Thread(
        target=app._submit_conversation_customer_profile_llm_worker,
        args=(submit_tab_id, output_widget, instruction_text, llm_prompt),
        daemon=True,
    ).start()


def submit_conversation_customer_profile_llm_worker(
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
        app.after(0, app._append_live_conversation_customer_profile_thinking_chunk, source_widget, chunk)

    def on_content_chunk(chunk: str) -> None:
        if not chunk:
            return
        content_seen["value"] = True
        app.after(0, app._append_live_conversation_customer_profile_content_chunk, source_widget, chunk)

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
        lambda: app._on_submit_conversation_customer_profile_llm_done(
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


def on_submit_conversation_customer_profile_llm_done(
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
    kind_label = "客户画像"
    if (not thinking_seen) and thinking_text:
        app._append_live_conversation_customer_profile_thinking_chunk(source_widget, thinking_text)

    if error_text:
        messagebox.showerror("LLM请求失败", error_text)
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] {kind_label} submit failed: {error_text}",
        )
        return

    if not content_seen:
        app._prepare_live_conversation_customer_profile_response_bubble(source_widget)
        if result_text:
            app._append_text_to_widget_with_tag(source_widget, str(result_text), "cs_left_bubble")
    if submit_tab_id and (submit_tab_id in app._conversation_tabs):
        with app._using_conversation_tab_context(submit_tab_id):
            app._append_conversation_customer_profile_history(
                instruction_text=instruction_text,
                response_text=result_text or "",
            )
    else:
        app._append_conversation_customer_profile_history(
            instruction_text=instruction_text,
            response_text=result_text or "",
        )
    dialog = getattr(app, "_conversation_customer_profile_dialog", None)
    if isinstance(dialog, dict):
        dialog["last_result"] = str(result_text or "")
        dialog_tab_id = str(dialog.get("tab_id", "") or "")
        if (not dialog_tab_id) or (dialog_tab_id == submit_tab_id):
            app._render_conversation_customer_profile_dialog_history(dialog)
    app._append_line(
        app.log_text,
        (
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] {kind_label} submit success: "
            f"{app._sanitize_inline_text(result_text) or '(empty reply)'}"
        ),
    )


def save_conversation_customer_profile_dialog(app) -> None:
    dialog = getattr(app, "_conversation_customer_profile_dialog", None)
    if not isinstance(dialog, dict):
        return
    win = dialog.get("win")
    if not isinstance(win, tk.Toplevel) or (not win.winfo_exists()):
        app._conversation_customer_profile_dialog = None
        return
    final_text = str(dialog.get("last_result", "") or "").strip()
    if not final_text:
        messagebox.showwarning("未生成结果", "请先点击“提交”并等待返回结果。")
        return
    tab_id = str(dialog.get("tab_id", "") or (app._bound_conversation_tab_id or app._active_conversation_tab_id))
    if tab_id and (tab_id in app._conversation_tabs):
        with app._using_conversation_tab_context(tab_id):
            if isinstance(app.conversation_customer_profile_text, ScrolledText):
                app._set_text_content(app.conversation_customer_profile_text, final_text)
    else:
        if isinstance(app.conversation_customer_profile_text, ScrolledText):
            app._set_text_content(app.conversation_customer_profile_text, final_text)
    app._conversation_customer_profile_dialog = None
    try:
        win.grab_release()
    except Exception:
        pass
    try:
        win.destroy()
    except Exception:
        pass


def open_conversation_intent_generator_dialog(
    app,
    *,
    ui_font_family: str,
    ui_font_size: int,
) -> None:
    existing = getattr(app, "_conversation_intent_dialog", None)
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
    win.title("Intent生成")
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
    root.pack(fill=tk.BOTH, expand=True)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    top_bar = ttk.Frame(root, style="Panel.TFrame", padding=(4, 2, 4, 6))
    top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    top_bar.columnconfigure(0, weight=1)
    ttk.Label(top_bar, text="Intent生成", background="#f3f4f6", foreground="#111827").grid(row=0, column=0, sticky="w")
    save_btn = ttk.Button(
        top_bar,
        text="保存",
        command=lambda: app._save_conversation_intent_dialog(),
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

    def _on_intent_input_return(event: object) -> str:
        if getattr(event, "state", 0) & 0x1:
            return ""
        app._generate_conversation_intent_in_dialog()
        return "break"

    input_text.bind("<Return>", _on_intent_input_return)

    submit_wrap = ttk.Frame(bottom, style="Panel.TFrame")
    submit_wrap.grid(row=0, column=1, sticky="se")
    submit_btn = ttk.Button(
        submit_wrap,
        text="提交",
        command=lambda: app._generate_conversation_intent_in_dialog(),
        style="Primary.TButton",
    )
    submit_btn.pack(anchor="se")

    dialog_tab_id = app._bound_conversation_tab_id or app._active_conversation_tab_id
    history_items = app._get_conversation_intent_generator_history_for_tab(dialog_tab_id)
    latest_result = ""
    if history_items:
        latest_result = str(history_items[-1].get("response", "") or "").strip()
    app._conversation_intent_dialog = {
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
    def _on_intent_win_map(event: object = None) -> None:
        win.unbind("<Map>")
        try:
            win.update_idletasks()
        except Exception:
            pass
        d = getattr(app, "_conversation_intent_dialog", None)
        if isinstance(d, dict):
            app._render_conversation_intent_dialog_history(d)

    win.bind("<Map>", _on_intent_win_map)

    def _close_dialog() -> None:
        current = getattr(app, "_conversation_intent_dialog", None)
        if isinstance(current, dict) and (current.get("win") is win):
            app._conversation_intent_dialog = None
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass

    win.protocol("WM_DELETE_WINDOW", _close_dialog)


def generate_conversation_intent_in_dialog(app) -> None:
    if app._llm_submit_running:
        messagebox.showinfo("Submitting", "LLM request is running.")
        return
    dialog = getattr(app, "_conversation_intent_dialog", None)
    if not isinstance(dialog, dict):
        return
    win = dialog.get("win")
    if not isinstance(win, tk.Toplevel) or (not win.winfo_exists()):
        app._conversation_intent_dialog = None
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
    llm_prompt = app._build_conversation_intent_prompt_with_history(instruction_text, tab_id=submit_tab_id)
    kind_label = "Intent生成"
    app._log_llm_prompts(f"{kind_label}(对话页提交)", llm_prompt)
    app._append_llm_prompt_block_to_system_instruction(
        begin_tag=f"[LLM_PANEL_PROMPT_BEGIN][{kind_label}]",
        end_tag=f"[LLM_PANEL_PROMPT_END][{kind_label}]",
        llm_prompt=llm_prompt,
    )
    dialog["last_instruction"] = instruction_text
    app._render_conversation_intent_dialog_history(dialog)
    app._update_conversation_strategy_dialog_history_tags(output_widget)
    app._append_text_to_widget_with_tag(
        output_widget,
        f"{instruction_text}\n\n",
        "cs_right_bubble",
    )
    output_widget.insert("end", "\n")
    dialog["live_response_start"] = output_widget.index("end-1c")
    dialog["live_response_phase"] = "thinking"
    app._append_text_to_widget_with_tag(output_widget, "思考中...\n", "cs_left_bubble")
    app._llm_submit_running = True
    threading.Thread(
        target=app._submit_conversation_intent_llm_worker,
        args=(submit_tab_id, output_widget, instruction_text, llm_prompt),
        daemon=True,
    ).start()


def submit_conversation_intent_llm_worker(
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
        app.after(0, app._append_live_conversation_intent_thinking_chunk, source_widget, chunk)

    def on_content_chunk(chunk: str) -> None:
        if not chunk:
            return
        content_seen["value"] = True
        app.after(0, app._append_live_conversation_intent_content_chunk, source_widget, chunk)

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
        lambda: app._on_submit_conversation_intent_llm_done(
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


def on_submit_conversation_intent_llm_done(
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
    kind_label = "Intent生成"
    if (not thinking_seen) and thinking_text:
        app._append_live_conversation_intent_thinking_chunk(source_widget, thinking_text)

    if error_text:
        messagebox.showerror("LLM请求失败", error_text)
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] {kind_label} submit failed: {error_text}",
        )
        return

    if not content_seen:
        app._prepare_live_conversation_intent_response_bubble(source_widget)
        if result_text:
            app._append_text_to_widget_with_tag(source_widget, str(result_text), "cs_left_bubble")
    if submit_tab_id and (submit_tab_id in app._conversation_tabs):
        with app._using_conversation_tab_context(submit_tab_id):
            app._append_conversation_intent_generator_history(
                instruction_text=instruction_text,
                response_text=result_text or "",
            )
    else:
        app._append_conversation_intent_generator_history(
            instruction_text=instruction_text,
            response_text=result_text or "",
        )
    dialog = getattr(app, "_conversation_intent_dialog", None)
    if isinstance(dialog, dict):
        dialog["last_result"] = str(result_text or "")
        dialog_tab_id = str(dialog.get("tab_id", "") or "")
        if (not dialog_tab_id) or (dialog_tab_id == submit_tab_id):
            app._render_conversation_intent_dialog_history(dialog)
    app._append_line(
        app.log_text,
        (
            f"[{datetime.now().strftime('%H:%M:%S')}] [LLM_DIRECT] {kind_label} submit success: "
            f"{app._sanitize_inline_text(result_text) or '(empty reply)'}"
        ),
    )


def save_conversation_intent_dialog(app) -> None:
    dialog = getattr(app, "_conversation_intent_dialog", None)
    if not isinstance(dialog, dict):
        return
    win = dialog.get("win")
    if not isinstance(win, tk.Toplevel) or (not win.winfo_exists()):
        app._conversation_intent_dialog = None
        return
    final_text = str(dialog.get("last_result", "") or "").strip()
    if not final_text:
        messagebox.showwarning("未生成结果", "请先点击“提交”并等待返回结果。")
        return
    tab_id = str(dialog.get("tab_id", "") or (app._bound_conversation_tab_id or app._active_conversation_tab_id))
    if tab_id and (tab_id in app._conversation_tabs):
        with app._using_conversation_tab_context(tab_id):
            if isinstance(app.conversation_intent_text, ScrolledText):
                app._set_text_content(app.conversation_intent_text, final_text)
    else:
        if isinstance(app.conversation_intent_text, ScrolledText):
            app._set_text_content(app.conversation_intent_text, final_text)
    app._conversation_intent_dialog = None
    try:
        win.grab_release()
    except Exception:
        pass
    try:
        win.destroy()
    except Exception:
        pass
