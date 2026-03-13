from __future__ import annotations

import re
import threading
from datetime import datetime

import tkinter as tk
from tkinter import BOTH, LEFT, RIGHT, X, Y, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
try:
    from .ui_widgets import TtlScrolledText
except Exception:
    from ui_widgets import TtlScrolledText


def build_dialog_summary_text(app, focus_hint: str = "") -> str:
    raw_conversation = app.dialog_conversation_text.get("1.0", "end-1c") or ""
    raw_intent = app.dialog_intent_text.get("1.0", "end-1c") or ""
    lines = [line.strip() for line in raw_conversation.splitlines() if line.strip()]
    customer_last = ""
    agent_last = ""
    for line in lines:
        lower = line.lower()
        if lower.startswith(("客户", "customer", "c:")):
            customer_last = line
        elif lower.startswith(("坐席", "agent", "a:")):
            agent_last = line

    intent_lines = [line.strip() for line in raw_intent.splitlines() if line.strip()]
    top_intent = intent_lines[-1] if intent_lines else "暂无"

    if not lines:
        return "\n".join(
            [
                "【对话总结】",
                "当前没有可总结的对话内容。",
                "",
                "提示：先进行对话，再点击\"对话总结\"。",
            ]
        )

    summary_lines = [
        "【对话总结】",
        f"对话行数：{len(lines)}",
        f"最新客户意图：{top_intent}",
        "",
        "【最近客户发言】",
        customer_last or "暂无",
        "",
        "【最近坐席发言】",
        agent_last or "暂无",
        "",
        "【关注点】",
        focus_hint or "无",
        "",
        "【最近对话片段】",
    ]
    tail_lines = lines[-8:] if len(lines) > 8 else lines
    summary_lines.extend(tail_lines)
    return "\n".join(summary_lines)


def build_next_dialog_strategy_text(app, focus_hint: str = "") -> str:
    raw_conversation = app.dialog_conversation_text.get("1.0", "end-1c") or ""
    raw_intent = app.dialog_intent_text.get("1.0", "end-1c") or ""
    lines = [line.strip() for line in raw_conversation.splitlines() if line.strip()]
    intent_lines = [line.strip() for line in raw_intent.splitlines() if line.strip()]
    top_intent = intent_lines[-1] if intent_lines else "暂无"

    if not lines:
        return "\n".join(
            [
                "【下一步对话策略】",
                "当前没有对话内容，建议先完成首轮沟通。",
                "1. 明确核身字段，确认是否本人接听。",
                "2. 说明来电目的，进入还款安排确认。",
            ]
        )

    strategy_lines = [
        "【下一步对话策略】",
        f"当前识别意图：{top_intent}",
        f"重点关注：{focus_hint or '确认还款时间与金额'}",
        "",
        "1. 先复述客户最新表态，确认理解一致。",
        "2. 提单点问题：仅问一个明确时间点或金额。",
        "3. 若客户模糊回应，要求给出具体日期和操作渠道。",
        "4. 若客户拒绝，切换为风险提示并约定下一次联系时间。",
    ]
    return "\n".join(strategy_lines)


DEFAULT_DIALOG_SUMMARY_PROMPT_TEMPLATE = "\n".join(
    [
        "你是一名专业的对话总结助手，请根据以下对话内容生成一份简洁的总结报告。",
        "输出要求：不要使用Markdown格式，不要使用**加粗**、#标题、---分隔线等特殊标记。",
        "请按照以下要点进行整理：",
        "1. 本次对话的主要内容",
        "2. 客户的核心诉求与意图，以及当前的处理进度或结果",
        "3. 客户的承诺",
        "如需列举多条，请使用\"1. ...\"的格式",
        "换行时请使用\"关键词：\n内容\"的格式",
    ]
)

DEFAULT_NEXT_DIALOG_STRATEGY_PROMPT_TEMPLATE = "\n".join(
    [
        "你是一名专业的对话策略顾问，请根据以下对话内容和待确认事项，生成下一步的对话策略建议。",
        "策略要求：",
        "1. 要逐一和客户确认【待确认事项】的执行情况，问清原因",
        "2. 针对【待确认事项】中的具体答复设计下一步对话策略",
        "3. 策略应具体可操作，避免泛泛而谈",
        "4. 每条策略建议精简至1-2句话",
        "5. 策略按优先级排序，最重要的放在最前面",
    ]
)


class _SafePromptDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_prompt_template(template_text: str, **values: str) -> str:
    template = str(template_text or "")
    safe_values = _SafePromptDict({k: str(v or "") for k, v in values.items()})
    try:
        return template.format_map(safe_values)
    except Exception:
        return template


def build_dialog_summary_llm_prompt(
    conversation_text: str,
    extra_hint: str = "",
    template_text: str = "",
) -> str:
    hint = str(extra_hint or "").strip()
    hint_block = f"\n\n重点关注：{hint}" if hint else ""
    template = str(template_text or "").strip()
    rendered = _render_prompt_template(template, extra_hint=hint, extra_hint_block=hint_block)
    conv = (conversation_text or "").strip()
    return rendered.rstrip() + f"\n\n对话内容如下：\n{conv}{hint_block}"


def build_pending_items_llm_prompt(conversation_text: str, template_text: str = "") -> str:
    conv = (conversation_text or "").strip()
    template = str(template_text or "").strip()
    if not template:
        return ""
    rendered = _render_prompt_template(template, conversation_text=conv)
    if "{conversation_text}" in template:
        return rendered.strip()
    return rendered.rstrip() + f"\n\n对话内容如下：\n{conv}"


def _extract_last_n_rounds_text(conversation_text: str, n: int = 3) -> str:
    """Extract the last n customer-agent exchange rounds from conversation text."""
    lines = [line for line in (conversation_text or "").splitlines() if line.strip()]
    rounds: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        is_customer = ("客户:" in line or "客户：" in line)
        if is_customer:
            if current:
                rounds.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        rounds.append(current)
    tail = rounds[-n:] if len(rounds) > n else rounds
    return "\n".join(line for r in tail for line in r)


def build_next_dialog_strategy_llm_prompt(
    conversation_text: str,
    commitment_confirmation_text: str = "",
    extra_hint: str = "",
    template_text: str = "",
) -> str:
    hint = str(extra_hint or "").strip()
    hint_block = f"\n\n重点关注：{hint}" if hint else ""
    template = str(template_text or "").strip()
    rendered = _render_prompt_template(template, extra_hint=hint, extra_hint_block=hint_block)
    conv = (conversation_text or "").strip()
    commitment = (commitment_confirmation_text or "").strip() or "暂无"
    return rendered.rstrip() + f"\n\n对话内容：\n{conv}\n\n待确认承诺事项：\n{commitment}{hint_block}"


def extract_pending_commitment_items(summary_text: str) -> list[str]:
    lines = (summary_text or "").splitlines()
    pending_items: list[str] = []
    in_pending_block = False

    def _normalize_item(raw_line: str) -> str:
        text = (raw_line or "").strip()
        if not text:
            return ""
        text = re.sub(r"^\s*[-*•]+\s*", "", text)
        text = re.sub(r"^\s*\d+\s*[\.、\-]\s*", "", text)
        text = re.sub(r"^\s*[（(]\d+[）)]\s*", "", text)
        return text.strip()

    def _push_item(raw_line: str) -> None:
        item = _normalize_item(raw_line)
        if not item:
            return
        if item in {"无", "暂无", "无待确认事项", "无待确认", "-", "无。"}:
            return
        if item not in pending_items:
            pending_items.append(item)

    for raw_line in lines:
        line = (raw_line or "").strip()
        if not line:
            continue
        # 只要行内含【待确认事项】即命中，兼容 **【...】** 等各种 LLM 格式
        if "【待确认事项】" in line:
            in_pending_block = True
            tail = line.split("【待确认事项】", 1)[1].strip()
            tail = tail.lstrip("*").lstrip("：").strip()
            if tail:
                _push_item(tail)
            continue
        if "待确认事项" in line and not in_pending_block:
            in_pending_block = True
            for sep in ("：", ":"):
                if sep in line:
                    _push_item(line.split(sep, 1)[1])
                    break
            continue
        if in_pending_block:
            # 遇到下一个【...】段落标题则终止
            if re.search(r"【[^】]+】", line) and re.match(r"^\**【", line):
                break
            _push_item(line)

    return pending_items


def format_commitment_confirmation_text(confirmed_rows: list[dict[str, str]]) -> str:
    rows = confirmed_rows or []
    if not rows:
        return "【客户承诺-执行事项】\n无待确认事项"
    lines: list[str] = ["【客户承诺-执行事项】"]
    for idx, row in enumerate(rows, start=1):
        item = str(row.get("item", "") or "").strip() or "（未提供事项）"
        status = str(row.get("status", "") or "").strip() or "待确认"
        answer = str(row.get("answer", "") or "").strip() or "-"
        lines.append(f"{idx}. 待确认事项：{item}")
        lines.append(f"   坐席确认结果：{status}")
        lines.append(f"   坐席答复：{answer}")
    return "\n".join(lines)


def open_commitment_confirmation_dialog(
    app,
    parent: tk.Toplevel,
    pending_items: list[str],
) -> list[dict[str, str]] | None:
    if not pending_items:
        return []
    dialog = tk.Toplevel(parent)
    dialog.title("待确认事项确认")
    screen_w = app.winfo_screenwidth()
    screen_h = app.winfo_screenheight()
    dlg_w = screen_w // 2
    dlg_h = screen_h // 2
    dlg_x = (screen_w - dlg_w) // 2
    dlg_y = (screen_h - dlg_h) // 2
    dialog.geometry(f"{dlg_w}x{dlg_h}+{dlg_x}+{dlg_y}")
    dialog.minsize(600, 400)
    dialog.configure(bg="#eaf0f7")
    dialog.transient(parent)
    dialog.grab_set()

    root = ttk.Frame(dialog, style="App.TFrame", padding=10)
    root.pack(fill=BOTH, expand=True)

    ttk.Label(
        root,
        text="请逐条确认客户承诺事项，并填写坐席确认答复。",
        style="Muted.TLabel",
    ).pack(anchor="w", pady=(0, 8))

    canvas = tk.Canvas(root, bg="#f3f7fc", highlightthickness=0, bd=0)
    canvas.pack(side=LEFT, fill=BOTH, expand=True)
    scrollbar = ttk.Scrollbar(root, orient=tk.VERTICAL, command=canvas.yview, style="App.Vertical.TScrollbar")
    scrollbar.pack(side=RIGHT, fill=Y)
    canvas.configure(yscrollcommand=scrollbar.set)

    container = ttk.Frame(canvas, style="App.TFrame")
    window_id = canvas.create_window((0, 0), window=container, anchor="nw")

    def _sync_canvas_width(event=None) -> None:
        width = max(canvas.winfo_width(), 200)
        try:
            canvas.itemconfigure(window_id, width=width)
        except tk.TclError:
            return

    def _sync_scroll_region(event=None) -> None:
        bbox = canvas.bbox("all")
        if bbox:
            canvas.configure(scrollregion=bbox)

    container.bind("<Configure>", _sync_scroll_region)
    canvas.bind("<Configure>", _sync_canvas_width)

    row_defs: list[tuple[str, tk.StringVar, tk.StringVar]] = []
    for idx, item in enumerate(pending_items, start=1):
        box = ttk.LabelFrame(container, text=f"事项 {idx}", style="Section.TLabelframe", padding=8)
        box.pack(fill=X, expand=False, pady=(0, 8))
        label = tk.Label(
            box,
            text=item,
            bg="#f8fafc",
            fg="#0f172a",
            anchor="w",
            justify="left",
            wraplength=1,
            padx=8,
            pady=6,
        )
        label.pack(fill=X, expand=False, pady=(0, 8))
        label.bind(
            "<Configure>",
            lambda e, lbl=label: lbl.configure(wraplength=max(e.width - 16, 1)),
        )
        editor = ttk.Frame(box, style="Panel.TFrame")
        editor.pack(fill=X, expand=False)
        ttk.Label(editor, text="确认结果:", background="#f8fafc", foreground="#334155").pack(side=LEFT)
        status_var = tk.StringVar(value="已确认")
        status_combo = ttk.Combobox(
            editor,
            textvariable=status_var,
            values=("已确认", "未确认", "待跟进"),
            state="readonly",
            width=10,
        )
        status_combo.pack(side=LEFT, padx=(6, 10))
        ttk.Label(editor, text="坐席答复:", background="#f8fafc", foreground="#334155").pack(side=LEFT)
        answer_var = tk.StringVar(value="")
        ttk.Entry(editor, textvariable=answer_var).pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        row_defs.append((item, status_var, answer_var))

    action_bar = ttk.Frame(container, style="Toolbar.TFrame", padding=(0, 4, 0, 0))
    action_bar.pack(fill=X, expand=False, pady=(4, 2))
    result_holder: dict[str, list[dict[str, str]] | None] = {"rows": None}

    def _on_confirm() -> None:
        rows: list[dict[str, str]] = []
        for item, status_var, answer_var in row_defs:
            status = (status_var.get() or "").strip() or "待确认"
            answer = (answer_var.get() or "").strip()
            rows.append({"item": item, "status": status, "answer": answer})
        result_holder["rows"] = rows
        dialog.destroy()

    def _on_cancel() -> None:
        result_holder["rows"] = None
        dialog.destroy()

    ttk.Button(action_bar, text="确认并继续", command=_on_confirm, style="Primary.TButton").pack(side=RIGHT)
    ttk.Button(action_bar, text="取消", command=_on_cancel, style="Soft.TButton").pack(side=RIGHT, padx=(0, 8))

    dialog.protocol("WM_DELETE_WINDOW", _on_cancel)
    dialog.bind("<Escape>", lambda _event: _on_cancel())
    app.after_idle(_sync_scroll_region)
    app.after_idle(_sync_canvas_width)
    dialog.wait_window()
    return result_holder.get("rows")


def _extract_last_session_text(full_text: str) -> str:
    """Extract text from the last ===对话开始=== marker to the end."""
    lines = full_text.splitlines()
    last_start_idx = -1
    for i, line in enumerate(lines):
        if "对话开始" in line:
            last_start_idx = i
    if last_start_idx == -1:
        return full_text
    return "\n".join(lines[last_start_idx:])


def open_dialog_summary_modal(app, *, ui_font_family: str) -> None:
    win = tk.Toplevel(app)
    win.title("对话总结")
    screen_w = app.winfo_screenwidth()
    screen_h = app.winfo_screenheight()
    win_w = int(screen_w * 0.8)
    win_h = int(screen_h * 0.8)
    pos_x = max((screen_w - win_w) // 2, 0)
    pos_y = max((screen_h - win_h) // 2, 0)
    win.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
    win.minsize(880, 620)
    win.configure(bg="#eaf0f7")
    win.transient(app)
    win.grab_set()

    root = ttk.Frame(win, style="App.TFrame", padding=12)
    root.pack(fill=BOTH, expand=True)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    top = ttk.Frame(root, style="Toolbar.TFrame", padding=(12, 10, 12, 10))
    top.pack(fill=X, pady=(0, 10))

    panes = ttk.Panedwindow(root, orient=tk.VERTICAL)
    panes.pack(fill=BOTH, expand=True)

    def _make_scrolled(parent: tk.Widget) -> TtlScrolledText:
        return TtlScrolledText(
            parent,
            wrap="word",
            state="normal",
            bg="#ffffff",
            fg="#0f1f35",
            insertbackground="#0f1f35",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#d7dee8",
            font=(ui_font_family, 9),
        )

    def _make_panel(title: str) -> tuple:
        box = ttk.LabelFrame(panes, text=title, style="Section.TLabelframe", padding=8)
        header = ttk.Frame(box, style="Toolbar.TFrame")
        header.pack(fill=X, pady=(0, 2))
        # Scope radio buttons on the left
        scope_var = tk.StringVar(value="全部")
        scope_frame = ttk.Frame(header, style="Toolbar.TFrame")
        scope_frame.pack(side=LEFT)
        ttk.Radiobutton(scope_frame, text="当前", variable=scope_var, value="当前").pack(side=LEFT)
        ttk.Radiobutton(scope_frame, text="全部", variable=scope_var, value="全部").pack(side=LEFT, padx=(6, 0))
        # Action buttons on the right
        clear_btn = ttk.Button(header, text="清除", style="Soft.TButton", width=5)
        clear_btn.pack(side=RIGHT, padx=(4, 0))
        gen_btn = ttk.Button(header, text="生成", style="Soft.TButton", width=5)
        gen_btn.pack(side=RIGHT)
        text_widget = _make_scrolled(box)
        # LLM 思考过程用灰色，正式内容用黑色
        text_widget.tag_configure("thinking", foreground="#9ca3af")
        text_widget.tag_configure("result", foreground="#111827")
        text_widget.pack(fill=BOTH, expand=True)
        panes.add(box, weight=1)
        return text_widget, gen_btn, clear_btn, scope_var

    def _get_conversation_text(scope: str) -> str:
        """Get conversation text based on scope: '当前' returns last session only, '全部' returns all."""
        full_text = ""
        try:
            full_text = (app.dialog_history_text.get("1.0", "end") or "").strip()
        except Exception:
            full_text = (app._extract_dialog_current_session_text() or "").strip()
        if not full_text:
            return ""
        if scope == "当前":
            return _extract_last_session_text(full_text)
        return full_text

    # Panel order: 1-客户承诺-执行事项, 2-对话总结, 3-下一步对话策略
    commitments_text, gen_commitments_btn, clear_commitments_btn, commitments_scope_var = _make_panel("客户承诺-执行事项")
    summary_text, gen_summary_btn, clear_summary_btn, summary_scope_var = _make_panel("对话总结")
    strategy_text, gen_strategy_btn, clear_strategy_btn, strategy_scope_var = _make_panel("下一步对话策略")

    modal_state: dict[str, object] = {
        "generation": 0,
        "phase_pending_items": "idle",
        "phase_summary": "idle",
        "phase_strategy": "idle",
        "conversation_text": "",
        "commitments_conversation_text": "",
        "summary_conversation_text": "",
        "strategy_conversation_text": "",
        "recent_rounds_text": "",
        "commitments_content": "",
        "extra_hint": "",
        "auto_chain": False,
    }

    def _set_modal_text(widget: ScrolledText, text: str, clear: bool = False, tag: str = "") -> None:
        if (not win.winfo_exists()) or (not widget.winfo_exists()):
            return
        prev_state = str(widget.cget("state"))
        widget.configure(state="normal")
        if clear:
            widget.delete("1.0", "end")
        if text:
            widget.insert("end", text, tag) if tag else widget.insert("end", text)
        widget.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
        widget.see("end")

    def _stream_final_text(
        target_widget: ScrolledText,
        phase_key: str,
        generation: int,
        final_text: str,
        pos: int = 0,
        chunk_size: int = 28,
    ) -> None:
        if (not win.winfo_exists()) or (generation != int(modal_state.get("generation", 0))):
            return
        if pos == 0:
            modal_state[phase_key] = "result"
            _set_modal_text(target_widget, "", clear=True)
        piece = final_text[pos : pos + chunk_size]
        if piece:
            _set_modal_text(target_widget, piece, clear=False, tag="result")
        next_pos = pos + chunk_size
        if next_pos < len(final_text):
            win.after(
                20,
                lambda: _stream_final_text(
                    target_widget=target_widget,
                    phase_key=phase_key,
                    generation=generation,
                    final_text=final_text,
                    pos=next_pos,
                    chunk_size=chunk_size,
                ),
            )

    def _show_done_toast() -> None:
        if not win.winfo_exists():
            return
        toast = tk.Toplevel(win)
        toast.title("")
        toast.resizable(False, False)
        toast.attributes("-topmost", True)
        toast.overrideredirect(True)
        lbl = tk.Label(
            toast,
            text="任务完成",
            font=("微软雅黑", 16, "bold"),
            bg="#1a7f3c",
            fg="#ffffff",
            padx=32,
            pady=18,
        )
        lbl.pack()
        toast.update_idletasks()
        tw, th = toast.winfo_width(), toast.winfo_height()
        wx = win.winfo_rootx() + (win.winfo_width() - tw) // 2
        wy = win.winfo_rooty() + (win.winfo_height() - th) // 2
        toast.geometry(f"+{wx}+{wy}")
        win.after(2000, lambda: toast.destroy() if toast.winfo_exists() else None)

    def _set_gen_buttons_state(state: str) -> None:
        if not win.winfo_exists():
            return
        for _btn in (generate_all_btn, gen_commitments_btn, gen_summary_btn, gen_strategy_btn):
            try:
                _btn.configure(state=state)
            except Exception:
                pass
        try:
            save_btn.configure(state="disabled" if state == "disabled" else save_btn.cget("state"))
        except Exception:
            pass

    def _on_task_done(task_key: str, generation: int, result_text: str, error_text: str) -> None:
        if (not win.winfo_exists()) or (generation != int(modal_state.get("generation", 0))):
            return

        if task_key == "pending_items":
            if error_text:
                modal_state["phase_pending_items"] = "result"
                _set_modal_text(commitments_text, f"[ERROR] {error_text}", clear=True, tag="result")
                _set_gen_buttons_state("normal")
                return
            pending_items = extract_pending_commitment_items(result_text or "")
            if pending_items:
                confirmed_rows = open_commitment_confirmation_dialog(app, win, pending_items)
                if confirmed_rows is None:
                    _set_modal_text(commitments_text, "已取消待确认事项确认。", clear=True, tag="result")
                    _set_gen_buttons_state("normal")
                    return
                commitments_content = format_commitment_confirmation_text(confirmed_rows)
            else:
                commitments_content = "【客户承诺-执行事项】\n无待确认事项"
            modal_state["phase_pending_items"] = "result"
            modal_state["commitments_content"] = commitments_content
            _set_modal_text(commitments_text, commitments_content, clear=True, tag="result")
            if not modal_state.get("auto_chain"):
                _set_gen_buttons_state("normal")
                _show_done_toast()
                return
            conversation_text = str(modal_state.get("summary_conversation_text", "") or modal_state.get("conversation_text", "") or "")
            extra_hint = str(modal_state.get("extra_hint", "") or "")
            summary_prompt = app._build_dialog_summary_llm_prompt(
                conversation_text=conversation_text,
                extra_hint=extra_hint,
            )
            _ts = datetime.now().strftime("%H:%M:%S")
            app._append_line(app.log_text, f"[{_ts}] [LLM_DIRECT] 对话总结任务启动")
            app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== 对话总结 提示词 =====")
            for _ln in summary_prompt.splitlines():
                app._append_line(app.log_text, f"[{_ts}]   {_ln}")
            app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== END =====")
            modal_state["phase_summary"] = "thinking"
            _set_modal_text(summary_text, "", clear=True)
            threading.Thread(
                target=_run_llm_task_worker,
                args=("summary", summary_prompt, generation),
                daemon=True,
            ).start()
            return

        if task_key == "summary":
            if error_text:
                modal_state["phase_summary"] = "result"
                _set_modal_text(summary_text, f"[ERROR] {error_text}", clear=True, tag="result")
                _set_gen_buttons_state("normal")
                return
            if str(modal_state.get("phase_summary", "thinking")) != "result":
                _stream_final_text(summary_text, "phase_summary", generation, result_text or "(empty)")
            if not modal_state.get("auto_chain"):
                _set_gen_buttons_state("normal")
                _show_done_toast()
                return
            extra_hint = str(modal_state.get("extra_hint", "") or "")
            commitments_content = str(modal_state.get("commitments_content", "") or "")
            strategy_prompt = app._build_next_dialog_strategy_llm_prompt(
                conversation_text=str(modal_state.get("strategy_conversation_text", "") or modal_state.get("conversation_text", "") or ""),
                commitment_confirmation_text=commitments_content,
                extra_hint=extra_hint,
            )
            _ts = datetime.now().strftime("%H:%M:%S")
            app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== 对话策略 提示词 =====")
            for _ln in strategy_prompt.splitlines():
                app._append_line(app.log_text, f"[{_ts}]   {_ln}")
            app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== END =====")
            modal_state["phase_strategy"] = "thinking"
            _set_modal_text(strategy_text, "", clear=True)
            threading.Thread(
                target=_run_llm_task_worker,
                args=("strategy", strategy_prompt, generation),
                daemon=True,
            ).start()
            return

        # task_key == "strategy"
        if error_text:
            modal_state["phase_strategy"] = "result"
            _set_modal_text(strategy_text, f"[ERROR] {error_text}", clear=True, tag="result")
            _set_gen_buttons_state("normal")
            return
        if str(modal_state.get("phase_strategy", "thinking")) != "result":
            _stream_final_text(strategy_text, "phase_strategy", generation, result_text or "(empty)")
        _set_gen_buttons_state("normal")
        if win.winfo_exists():
            save_btn.configure(state="normal")
        _show_done_toast()

    def _run_llm_task_worker(task_key: str, llm_prompt: str, generation: int) -> None:
        result_text = ""
        error_text = ""
        content_started = {"value": False}

        def _resolve_phase_and_widget() -> tuple[str, object]:
            if task_key == "pending_items":
                return "phase_pending_items", commitments_text
            if task_key == "summary":
                return "phase_summary", summary_text
            return "phase_strategy", strategy_text

        def on_thinking_chunk(chunk: str) -> None:
            if not chunk:
                return

            def _append_thinking() -> None:
                if (not win.winfo_exists()) or (generation != int(modal_state.get("generation", 0))):
                    return
                phase_key, target_widget = _resolve_phase_and_widget()
                if str(modal_state.get(phase_key, "thinking")) != "thinking":
                    return
                _set_modal_text(target_widget, chunk, clear=False, tag="thinking")

            app.after(0, _append_thinking)

        def on_content_chunk(chunk: str) -> None:
            if not chunk:
                return
            first_chunk = not content_started["value"]
            content_started["value"] = True

            def _append_content() -> None:
                if (not win.winfo_exists()) or (generation != int(modal_state.get("generation", 0))):
                    return
                phase_key, target_widget = _resolve_phase_and_widget()
                if first_chunk:
                    modal_state[phase_key] = "result"
                    _set_modal_text(target_widget, "", clear=True)
                _set_modal_text(target_widget, chunk, clear=False, tag="result")

            app.after(0, _append_content)

        try:
            result_text, _thinking_text = app._call_deepseek_for_dialog_tasks(
                llm_prompt,
                on_thinking_chunk=on_thinking_chunk,
                on_content_chunk=on_content_chunk,
            )
        except Exception as exc:
            error_text = str(exc)

        app.after(0, lambda: _on_task_done(task_key, generation, result_text, error_text))

    def _prep_generation(auto_chain: bool, scope: str = "全部") -> tuple[str, int] | tuple[None, None]:
        conversation_text = _get_conversation_text(scope)
        if not conversation_text:
            messagebox.showwarning("无对话内容", "当前无可用对话内容。")
            return None, None
        generation = int(modal_state.get("generation", 0)) + 1
        modal_state["generation"] = generation
        modal_state["conversation_text"] = conversation_text
        modal_state["extra_hint"] = ""
        modal_state["auto_chain"] = auto_chain
        _set_gen_buttons_state("disabled")
        return conversation_text, generation

    def _run_generate_all() -> None:
        # Capture per-panel conversation texts based on each panel's scope
        commitments_conv = _get_conversation_text(commitments_scope_var.get())
        summary_conv = _get_conversation_text(summary_scope_var.get())
        strategy_conv = _get_conversation_text(strategy_scope_var.get())
        if not commitments_conv:
            messagebox.showwarning("无对话内容", "当前无可用对话内容。")
            return
        generation = int(modal_state.get("generation", 0)) + 1
        modal_state["generation"] = generation
        modal_state["commitments_conversation_text"] = commitments_conv
        modal_state["summary_conversation_text"] = summary_conv or commitments_conv
        modal_state["strategy_conversation_text"] = strategy_conv or commitments_conv
        modal_state["conversation_text"] = commitments_conv
        modal_state["extra_hint"] = ""
        modal_state["auto_chain"] = True
        modal_state["commitments_content"] = ""
        modal_state["phase_pending_items"] = "thinking"
        modal_state["phase_summary"] = "idle"
        modal_state["phase_strategy"] = "idle"
        _set_gen_buttons_state("disabled")
        _set_modal_text(commitments_text, "", clear=True)
        _set_modal_text(summary_text, "", clear=True)
        _set_modal_text(strategy_text, "", clear=True)
        pending_template = app._get_pending_items_prompt_template()
        if not pending_template:
            messagebox.showwarning("提示词为空", "请先在工作流程页填写“待核实事项提示词”。")
            _set_gen_buttons_state("normal")
            return
        pending_prompt = build_pending_items_llm_prompt(commitments_conv, template_text=pending_template)
        _ts = datetime.now().strftime("%H:%M:%S")
        app._append_line(app.log_text, f"[{_ts}] [LLM_DIRECT] 一键生成启动")
        app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== 待核实事项 提示词 =====")
        for _ln in pending_prompt.splitlines():
            app._append_line(app.log_text, f"[{_ts}]   {_ln}")
        app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== END =====")
        threading.Thread(
            target=_run_llm_task_worker,
            args=("pending_items", pending_prompt, generation),
            daemon=True,
        ).start()

    def _run_generate_commitments() -> None:
        conversation_text, generation = _prep_generation(auto_chain=False, scope=commitments_scope_var.get())
        if conversation_text is None:
            return
        modal_state["commitments_content"] = ""
        modal_state["phase_pending_items"] = "thinking"
        _set_modal_text(commitments_text, "", clear=True)
        pending_template = app._get_pending_items_prompt_template()
        if not pending_template:
            messagebox.showwarning("提示词为空", "请先在工作流程页填写“待核实事项提示词”。")
            _set_gen_buttons_state("normal")
            return
        pending_prompt = build_pending_items_llm_prompt(conversation_text, template_text=pending_template)
        _ts = datetime.now().strftime("%H:%M:%S")
        app._append_line(app.log_text, f"[{_ts}] [LLM_DIRECT] 待核实事项提取启动")
        app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== 客户承诺-执行事项 提示词 =====")
        for _ln in pending_prompt.splitlines():
            app._append_line(app.log_text, f"[{_ts}]   {_ln}")
        app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== END =====")
        threading.Thread(
            target=_run_llm_task_worker,
            args=("pending_items", pending_prompt, generation),
            daemon=True,
        ).start()

    def _run_generate_summary() -> None:
        conversation_text, generation = _prep_generation(auto_chain=False, scope=summary_scope_var.get())
        if conversation_text is None:
            return
        modal_state["phase_summary"] = "thinking"
        _set_modal_text(summary_text, "", clear=True)
        summary_prompt = app._build_dialog_summary_llm_prompt(
            conversation_text=conversation_text, extra_hint=""
        )
        _ts = datetime.now().strftime("%H:%M:%S")
        app._append_line(app.log_text, f"[{_ts}] [LLM_DIRECT] 对话总结生成启动")
        app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== 对话总结 提示词 =====")
        for _ln in summary_prompt.splitlines():
            app._append_line(app.log_text, f"[{_ts}]   {_ln}")
        app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== END =====")
        threading.Thread(
            target=_run_llm_task_worker,
            args=("summary", summary_prompt, generation),
            daemon=True,
        ).start()

    def _run_generate_strategy() -> None:
        conversation_text, generation = _prep_generation(auto_chain=False, scope=strategy_scope_var.get())
        if conversation_text is None:
            return
        modal_state["phase_strategy"] = "thinking"
        _set_modal_text(strategy_text, "", clear=True)
        commitments_content = (
            commitments_text.get("1.0", "end-1c").strip()
            or str(modal_state.get("commitments_content", "") or "")
        )
        strategy_prompt = app._build_next_dialog_strategy_llm_prompt(
            conversation_text=conversation_text,
            commitment_confirmation_text=commitments_content,
            extra_hint="",
        )
        _ts = datetime.now().strftime("%H:%M:%S")
        app._append_line(app.log_text, f"[{_ts}] [LLM_DIRECT] 对话策略生成启动")
        app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== 下一步对话策略 提示词 =====")
        for _ln in strategy_prompt.splitlines():
            app._append_line(app.log_text, f"[{_ts}]   {_ln}")
        app._append_line(app.log_text, f"[{_ts}] [LLM_PROMPT] ===== END =====")
        threading.Thread(
            target=_run_llm_task_worker,
            args=("strategy", strategy_prompt, generation),
            daemon=True,
        ).start()

    # Wire up individual panel "生成" buttons
    gen_commitments_btn.configure(command=_run_generate_commitments)
    gen_summary_btn.configure(command=_run_generate_summary)
    gen_strategy_btn.configure(command=_run_generate_strategy)

    # Wire up "清除" buttons
    clear_commitments_btn.configure(command=lambda: _set_modal_text(commitments_text, "", clear=True))
    clear_summary_btn.configure(command=lambda: _set_modal_text(summary_text, "", clear=True))
    clear_strategy_btn.configure(command=lambda: _set_modal_text(strategy_text, "", clear=True))

    def _save_summary_and_close() -> None:
        summary_content = summary_text.get("1.0", "end-1c").strip()
        commitments_content = commitments_text.get("1.0", "end-1c").strip()
        strategy_content = strategy_text.get("1.0", "end-1c").strip()
        if not strategy_content:
            messagebox.showwarning("策略为空", "请先生成下一步对话策略。")
            return
        try:
            path = app._save_dialog_summary_record(
                summary_content=summary_content,
                strategy_content=strategy_content,
                commitments_content=commitments_content,
            )
            app._append_line(
                app.log_text,
                f"[{datetime.now().strftime('%H:%M:%S')}] [CALL_RECORD] saved {path.name}",
            )
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        app._mark_conversation_tab_data_dirty()
        app._dialog_summary_pending_warning = False
        app._allow_next_tab_switch_without_summary = False
        app._load_call_records_into_list(force_reload=True)
        app._load_customer_data_records_into_list(force_reload=True)
        win.destroy()
        switcher = app._conversation_page_switcher
        if callable(switcher):
            switcher("call_record")

    # Top bar: "一键生成" on left side of right cluster, "保存" rightmost
    save_btn = ttk.Button(top, text="保存", command=_save_summary_and_close, style="Primary.TButton")
    save_btn.pack(side=RIGHT)
    generate_all_btn = ttk.Button(top, text="一键生成", command=_run_generate_all, style="Soft.TButton")
    generate_all_btn.pack(side=RIGHT, padx=(0, 8))

    def _set_equal_split() -> None:
        pane_height = panes.winfo_height()
        if pane_height <= 0:
            return
        try:
            third = pane_height // 3
            if abs(panes.sashpos(0) - third) > 2:
                panes.sashpos(0, third)
            if abs(panes.sashpos(1) - third * 2) > 2:
                panes.sashpos(1, third * 2)
        except tk.TclError:
            return

    app.after_idle(_set_equal_split)
    panes.bind("<Configure>", lambda _event: app.after_idle(_set_equal_split))

    win.bind("<Escape>", lambda _event: win.destroy())
