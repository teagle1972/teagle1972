from __future__ import annotations

import shutil
import threading
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import BOTH, LEFT, X, messagebox, ttk
from tkinter.scrolledtext import ScrolledText


def _build_llm_customer_profile_prompt(reference_profile: str) -> str:
    return "\n\n".join(
        [
            "你是一个用于外呼场景的客户资料生成助手。",
            "请参考给定的客户资料，生成一份可直接用于外呼的新客户资料。",
            "输出要求：",
            "1. 只输出客户资料正文，不要解释说明，不要使用 Markdown。",
            "2. 每行一个字段，格式：字段名: 值。",
            "3. 必须包含客户姓名字段，且姓名要和参考客户资料中的名字有巨大反差，不能相似",
            "4. 字段内容完整、具体、有实际意义。",
            "【参考客户资料】",
            reference_profile.strip(),
        ]
    )


def _open_customer_generation_dialog(app) -> dict[str, object]:
    win = tk.Toplevel(app)
    win.title("新建客户")
    win.configure(bg="#f3f7fc")
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    w = sw // 2
    h = sh // 2
    x = (sw - w) // 2
    y = (sh - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")

    root = ttk.Frame(win, style="App.TFrame", padding=10)
    root.pack(fill=BOTH, expand=True)
    body = ttk.LabelFrame(root, text="输出", style="Section.TLabelframe", padding=8)
    body.pack(fill=BOTH, expand=True)
    output = ScrolledText(
        body,
        wrap="word",
        state="disabled",
        font=("微软雅黑", 11),
        spacing1=8,
        spacing2=4,
        spacing3=8,
        bg="#ffffff",
        fg="#6b7280",
        insertbackground="#111827",
        relief="flat",
        highlightthickness=1,
        highlightbackground="#d7dee8",
    )
    output.tag_configure("thinking", foreground="#9ca3af")
    output.tag_configure("result", foreground="#111827")
    output.pack(fill=BOTH, expand=True)

    dialog: dict[str, object] = {"window": win, "output": output, "result_started": False}
    return dialog


def _append_customer_generation_dialog_text(dialog: dict[str, object], text: str, *, target: str = "thinking") -> None:
    if not text:
        return
    win = dialog.get("window")
    if isinstance(win, tk.Toplevel):
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
    output = dialog.get("output")
    if not isinstance(output, ScrolledText):
        return
    # 第一次写入正式结果时：清空窗口，切换为黑色文字
    if target == "result" and not dialog.get("result_started"):
        dialog["result_started"] = True
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.configure(state="disabled")
    output.configure(state="normal")
    output.insert("end", text, target)
    output.configure(state="disabled")
    output.see("end")


def _close_customer_generation_dialog(dialog: dict[str, object]) -> None:
    win = dialog.get("window")
    if not isinstance(win, tk.Toplevel):
        return
    try:
        if win.winfo_exists():
            win.destroy()
    except Exception:
        return


def save_new_customer_record(app, profile_text: str, strategy_text: str) -> Path:
    now = datetime.now()
    now_text = now.strftime("%Y-%m-%d %H:%M:%S")
    customer_name = app._extract_customer_name_from_profile_text(profile_text)
    existing_path = app._find_customer_case_file(customer_name)
    if existing_path is None:
        filename = f"{app._sanitize_filename_component(customer_name)}_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        path = app._get_data_dir() / filename
        created_time = now_text
        records = [
            {
                "call_time": now_text,
                "call_cost": "",
                "call_record": "",
                "summary": "",
                "commitments": "",
                "strategy": (strategy_text or "").strip(),
            }
        ]
    else:
        path = existing_path
        case_data = app._read_customer_case_file(path)
        created_time = str(case_data.get("created_time", "")).strip() or now_text
        records = list(case_data.get("records", []))
        if not records:
            records.append(
                {
                    "call_time": now_text,
                    "call_cost": "",
                    "call_record": "",
                    "summary": "",
                    "commitments": "",
                    "strategy": (strategy_text or "").strip(),
                }
            )
    app._save_customer_case_file(
        path=path,
        customer_name=customer_name,
        created_time=created_time,
        updated_time=now_text,
        profile_text=profile_text,
        records=records,
    )
    return path


def create_new_customer_record_from_jsonl(app, default_workflow: str) -> None:
    if app._llm_submit_running:
        messagebox.showinfo("正在提交", "LLM 请求正在运行中。")
        return

    profile_source_widget = app.conversation_customer_profile_text
    strategy_source_widget = app.conversation_workflow_text
    reference_profile = (
        profile_source_widget.get("1.0", "end-1c") if isinstance(profile_source_widget, ScrolledText) else ""
    )
    reference_profile = str(reference_profile or "").strip()
    if not reference_profile:
        messagebox.showwarning("客户资料不能为空", "请先填写客户资料后再生成。")
        return

    strategy_text = (
        strategy_source_widget.get("1.0", "end-1c") if isinstance(strategy_source_widget, ScrolledText) else ""
    )
    strategy_text = str(strategy_text or "").strip()
    if not strategy_text:
        messagebox.showwarning("策略模板不能为空", "请先填写初始策略模板后再生成。")
        return

    llm_prompt = _build_llm_customer_profile_prompt(reference_profile)
    dialog = _open_customer_generation_dialog(app)
    app._log_llm_prompts("新建客户(客户资料页)", llm_prompt)

    app._llm_submit_running = True
    app._set_llm_generation_frozen(True)

    thinking_seen = {"value": False}
    content_seen = {"value": False}
    result_store = {"value": ""}
    thinking_store = {"value": ""}
    error_store = {"value": ""}

    def _on_thinking_chunk(chunk: str) -> None:
        if not chunk:
            return
        thinking_seen["value"] = True
        app.after(0, lambda c=chunk: _append_customer_generation_dialog_text(dialog, c, target="thinking"))

    def _on_content_chunk(chunk: str) -> None:
        if not chunk:
            return
        content_seen["value"] = True
        app.after(0, lambda c=chunk: _append_customer_generation_dialog_text(dialog, c, target="result"))

    def _worker() -> None:
        try:
            result_text, thinking_text = app._call_direct_llm_for_system_instruction(
                llm_prompt,
                on_thinking_chunk=_on_thinking_chunk,
                on_content_chunk=_on_content_chunk,
            )
            result_store["value"] = result_text
            thinking_store["value"] = thinking_text
        except Exception as exc:
            error_store["value"] = str(exc)
        app.after(0, _on_done)

    def _on_done() -> None:
        app._llm_submit_running = False
        app._set_llm_generation_frozen(False)

        thinking_text = str(thinking_store.get("value", "") or "")
        if (not thinking_seen["value"]) and thinking_text:
            _append_customer_generation_dialog_text(dialog, thinking_text, target="thinking")

        error_text = str(error_store.get("value", "") or "")
        if error_text:
            _append_customer_generation_dialog_text(dialog, f"[错误] {error_text}\n", target="result")
            app._append_line(
                app.log_text,
                f"[{datetime.now().strftime('%H:%M:%S')}] [CUSTOMER_DATA] 新建客户失败: {error_text}",
            )
            messagebox.showerror("新建客户失败", error_text)
            return

        profile_text = str(result_store.get("value", "") or "").strip()
        if not profile_text:
            _append_customer_generation_dialog_text(dialog, "[结果为空，请重试]\n", target="result")
            messagebox.showwarning("新建客户失败", "LLM 返回内容为空，请重试。")
            return

        # 若流式内容未触发（非流式模式），将完整结果一次性填入结果区
        if not content_seen["value"]:
            _append_customer_generation_dialog_text(dialog, profile_text, target="result")

        dialog_profile_tree = app.dialog_profile_table
        if isinstance(dialog_profile_tree, ttk.Treeview):
            app._fill_profile_table_from_text(dialog_profile_tree, profile_text=profile_text, auto_height=True)
        app._refresh_runtime_system_prompt_only()
        path = app._save_new_customer_record(profile_text=profile_text, strategy_text=strategy_text)
        app._load_call_records_into_list()
        app._load_customer_data_records_into_list()
        app._append_line(
            app.log_text,
            f"[{datetime.now().strftime('%H:%M:%S')}] [CUSTOMER_DATA] 新建客户成功 file={path.name}",
        )
        app.after(500, lambda: _close_customer_generation_dialog(dialog))

    threading.Thread(target=_worker, daemon=True).start()


def get_data_dir(app) -> Path:
    override = app._tab_data_dir_override
    if isinstance(override, Path):
        data_dir = override
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    bound_id = app._bound_conversation_tab_id
    if bound_id:
        context = app._conversation_tabs.get(bound_id)
        if context and isinstance(context.data_dir, Path):
            data_dir = context.data_dir
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir
    data_dir = app._workspace_dir / "Data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def build_new_tab_data_dir(app, tab_title: str) -> Path:
    root = app._workspace_dir / "Data" / "_tabs"
    root.mkdir(parents=True, exist_ok=True)
    base_name = app._sanitize_filename_component(tab_title) or "tab"
    candidate = root / base_name
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        nxt = root / f"{base_name}_{suffix}"
        if not nxt.exists():
            return nxt
        suffix += 1


def copy_tab_case_files(app, source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    if not source_dir.exists():
        return
    for source_file in source_dir.glob("*.txt"):
        if not source_file.is_file():
            continue
        shutil.copy2(source_file, target_dir / source_file.name)


def save_dialog_summary_record(
    app,
    summary_content: str,
    strategy_content: str,
    commitments_content: str = "",
) -> Path:
    now = datetime.now()
    now_text = now.strftime("%Y-%m-%d %H:%M:%S")
    profile_text = app._build_profile_text_from_dialog_profile_table().strip()
    if (not profile_text) and isinstance(app.conversation_customer_profile_text, ScrolledText):
        profile_text = (app.conversation_customer_profile_text.get("1.0", "end-1c") or "").strip()
    # Extract only the current session's dialogue (from last orange separator onwards)
    conversation_text = app._extract_dialog_current_session_text()
    customer_name = app._extract_customer_name_from_profile_text(profile_text)
    existing_path = app._find_customer_case_file(customer_name)
    if existing_path is None:
        filename = f"{app._sanitize_filename_component(customer_name)}_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        path = app._get_data_dir() / filename
        created_time = now_text
        records: list[dict[str, str]] = []
    else:
        path = existing_path
        case_data = app._read_customer_case_file(path)
        created_time = str(case_data.get("created_time", "")).strip() or now_text
        records = list(case_data.get("records", []))

    total_cost = 0.0
    try:
        total_cost = float(getattr(app, "_last_billing_total_cost", 0.0) or 0.0)
    except Exception:
        total_cost = 0.0
    call_cost_text = f"¥{total_cost:.5f}"

    duration_seconds = 0.0
    try:
        duration_seconds = float(getattr(app, "_last_billing_duration_seconds", 0.0) or 0.0)
    except Exception:
        duration_seconds = 0.0
    price_per_minute = 0.0
    if duration_seconds > 0:
        price_per_minute = (total_cost * 60.0) / duration_seconds
    duration_text = f"{duration_seconds:.1f}s" if duration_seconds > 0 else ""
    price_per_minute_text = f"{price_per_minute:.5f}" if duration_seconds > 0 else ""
    records.append(
        {
            "call_time": now_text,
            "call_cost": call_cost_text,
            "billing_duration": duration_text,
            "billing_duration_seconds": round(duration_seconds, 3) if duration_seconds > 0 else "",
            "price_per_minute": price_per_minute_text,
            "call_record": conversation_text,
            "summary": (summary_content or "").strip(),
            "commitments": (commitments_content or "").strip(),
            "strategy": (strategy_content or "").strip(),
        }
    )
    app._save_customer_case_file(
        path=path,
        customer_name=customer_name,
        created_time=created_time,
        updated_time=now_text,
        profile_text=profile_text,
        records=records,
    )
    return path


