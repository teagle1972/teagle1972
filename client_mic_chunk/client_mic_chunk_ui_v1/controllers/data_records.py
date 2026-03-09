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
            "你是电话业务场景的客户资料生成助手。",
            "请参考给定客户画像，生成一个可直接用于外呼的新客户资料。",
            "输出要求：",
            "1. 仅输出客户资料正文，不要解释，不要 Markdown。",
            "2. 每行一个字段，格式为“字段名: 字段值”。",
            "3. 必须包含“客户姓名”字段。",
            "4. 字段尽量完整且可执行，保持真实、具体。",
            "【参考客户画像】",
            reference_profile.strip(),
        ]
    )


def _open_customer_generation_dialog(app) -> dict[str, object]:
    win = tk.Toplevel(app)
    win.title("新建客户生成中")
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
    header = ttk.Frame(root, style="Toolbar.TFrame", padding=(8, 8, 8, 8))
    header.pack(fill=X, pady=(0, 8))
    ttk.Label(header, text="LLM 思考过程", background="#f3f7fc", foreground="#111827").pack(side=LEFT)
    body = ttk.LabelFrame(root, text="过程输出", style="Section.TLabelframe", padding=8)
    body.pack(fill=BOTH, expand=True)
    output = ScrolledText(
        body,
        wrap="word",
        state="disabled",
        bg="#ffffff",
        fg="#111827",
        insertbackground="#111827",
        relief="flat",
        highlightthickness=1,
        highlightbackground="#d7dee8",
    )
    output.pack(fill=BOTH, expand=True)

    dialog: dict[str, object] = {"window": win, "output": output}
    return dialog


def _append_customer_generation_dialog_text(dialog: dict[str, object], text: str) -> None:
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
    prev_state = str(output.cget("state"))
    output.configure(state="normal")
    output.insert("end", text)
    output.configure(state=prev_state if prev_state in {"normal", "disabled"} else "normal")
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
        messagebox.showinfo("Submitting", "LLM request is running.")
        return

    profile_source_widget = app.conversation_customer_profile_text
    strategy_source_widget = app.conversation_workflow_text
    reference_profile = (
        profile_source_widget.get("1.0", "end-1c") if isinstance(profile_source_widget, ScrolledText) else ""
    )
    reference_profile = str(reference_profile or "").strip()
    if not reference_profile:
        messagebox.showwarning("客户画像为空", "请先在“对话-工作流程-客户画像”填写内容。")
        return

    strategy_text = (
        strategy_source_widget.get("1.0", "end-1c") if isinstance(strategy_source_widget, ScrolledText) else ""
    )
    strategy_text = str(strategy_text or "").strip()
    if not strategy_text:
        messagebox.showwarning("初始策略模板为空", "请先在【对话-工作流程-初始策略模板】填写内容，再新建客户。")
        return

    llm_prompt = _build_llm_customer_profile_prompt(reference_profile)
    dialog = _open_customer_generation_dialog(app)
    _append_customer_generation_dialog_text(dialog, "[LLM_THINKING_BEGIN]\n")
    app._log_llm_prompts("新建客户(客户资料页)", llm_prompt)

    app._llm_submit_running = True
    app._set_llm_generation_frozen(True)

    thinking_seen = {"value": False}
    result_box = {"value": ""}
    thinking_box = {"value": ""}
    error_box = {"value": ""}

    def _on_thinking_chunk(chunk: str) -> None:
        if not chunk:
            return
        thinking_seen["value"] = True
        app.after(0, _append_customer_generation_dialog_text, dialog, chunk)

    def _worker() -> None:
        try:
            result_text, thinking_text = app._call_direct_llm_for_system_instruction(
                llm_prompt,
                on_thinking_chunk=_on_thinking_chunk,
            )
            result_box["value"] = result_text
            thinking_box["value"] = thinking_text
        except Exception as exc:
            error_box["value"] = str(exc)
        app.after(0, _on_done)

    def _on_done() -> None:
        app._llm_submit_running = False
        app._set_llm_generation_frozen(False)

        thinking_text = str(thinking_box.get("value", "") or "")
        if (not thinking_seen["value"]) and thinking_text:
            _append_customer_generation_dialog_text(dialog, thinking_text)
        _append_customer_generation_dialog_text(dialog, "\n[LLM_THINKING_END]\n")

        error_text = str(error_box.get("value", "") or "")
        if error_text:
            _append_customer_generation_dialog_text(dialog, f"[LLM_ERROR] {error_text}\n")
            app._append_line(
                app.log_text,
                f"[{datetime.now().strftime('%H:%M:%S')}] [CUSTOMER_DATA] 新建客户失败: {error_text}",
            )
            messagebox.showerror("新建客户失败", error_text)
            return

        profile_text = str(result_box.get("value", "") or "").strip()
        if not profile_text:
            _append_customer_generation_dialog_text(dialog, "[LLM_ERROR] 结果为空\n")
            messagebox.showwarning("新建客户失败", "LLM 返回为空，请重试。")
            return

        _append_customer_generation_dialog_text(
            dialog,
            f"\n[LLM_RESULT_BEGIN]\n{profile_text}\n[LLM_RESULT_END]\n",
        )

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

    records.append(
        {
            "call_time": now_text,
            "call_cost": call_cost_text,
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
