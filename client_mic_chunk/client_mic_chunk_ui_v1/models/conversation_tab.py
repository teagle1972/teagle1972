from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


_WORKFLOW_DOC_KEYS = (
    "system_instruction",
    "intent",
    "workflow_profile",
    "strategy",
    "strategy_input",
    "pending_items_prompt",
    "dialog_summary_prompt",
    "dialog_strategy_prompt",
)

_RUNTIME_STATE_KEYS = (
    "conversation_strategy_history",
    "conversation_customer_profile_history",
    "conversation_intent_generator_history",
    "dialog_conversation_history_by_customer",
    "dialog_conversation_active_customer_key",
    "customer_data_last_render_key",
    "dialog_agent_stream_active",
    "dialog_agent_stream_content_start",
    "dialog_intent_history",
    "dialog_intent_state_by_customer",
    "current_session_customer_lines",
)


@dataclass
class CallRecordPageState:
    items_cache: list[dict[str, str]] = field(default_factory=list)
    cache_version: int = 0
    list_dirty: bool = True
    view_loaded: bool = False
    source_signature: str = ""
    item_by_iid: dict[str, dict[str, str]] = field(default_factory=dict)
    item_by_id: dict[str, dict[str, str]] = field(default_factory=dict)
    selected_record_id: str = ""
    selected_cache_version: int = 0


def clone_call_record_page_state(state: CallRecordPageState | None) -> CallRecordPageState:
    if not isinstance(state, CallRecordPageState):
        return CallRecordPageState()
    return CallRecordPageState(
        items_cache=list(state.items_cache or []),
        cache_version=int(state.cache_version or 0),
        list_dirty=bool(state.list_dirty),
        view_loaded=bool(state.view_loaded),
        source_signature=str(state.source_signature or ""),
        item_by_iid=dict(state.item_by_iid or {}),
        item_by_id=dict(state.item_by_id or {}),
        selected_record_id=str(state.selected_record_id or ""),
        selected_cache_version=int(state.selected_cache_version or 0),
    )


@dataclass
class CustomerDataPageState:
    items_cache: list[tuple[str, str]] = field(default_factory=list)
    cache_version: int = 0
    list_dirty: bool = True
    view_loaded: bool = False
    source_signature: str = ""
    customer_by_iid: dict[str, str] = field(default_factory=dict)
    case_by_iid: dict[str, dict[str, object]] = field(default_factory=dict)
    case_cache_by_name: dict[str, dict[str, object]] = field(default_factory=dict)
    selected_customer_name: str = ""
    selected_cache_version: int = 0


def clone_customer_data_page_state(state: CustomerDataPageState | None) -> CustomerDataPageState:
    if not isinstance(state, CustomerDataPageState):
        return CustomerDataPageState()
    return CustomerDataPageState(
        items_cache=list(state.items_cache or []),
        cache_version=int(state.cache_version or 0),
        list_dirty=bool(state.list_dirty),
        view_loaded=bool(state.view_loaded),
        source_signature=str(state.source_signature or ""),
        customer_by_iid=dict(state.customer_by_iid or {}),
        case_by_iid=dict(state.case_by_iid or {}),
        case_cache_by_name=dict(state.case_cache_by_name or {}),
        selected_customer_name=str(state.selected_customer_name or ""),
        selected_cache_version=int(state.selected_cache_version or 0),
    )


@dataclass
class ConversationTabContext:
    tab_id: str
    title: str
    tab_frame: ttk.Frame
    conversation_shell: ttk.Frame | None
    conversation_command_var: tk.StringVar
    conversation_server_env_var: tk.StringVar
    conversation_profile_status_var: tk.StringVar | None
    conversation_profile_status_label: tk.Label | None
    call_record_selected_var: tk.StringVar
    profile_call_btn: ttk.Button | None
    conversation_page_switcher: Callable[[str], None] | None
    dialog_profile_table: ttk.Treeview | None
    monitor_asr_text: ScrolledText | None
    monitor_tts_text: ScrolledText | None
    monitor_nlp_input_text: ScrolledText | None
    monitor_latency_text: ScrolledText | None
    monitor_process_status_label: tk.Label | None
    dialog_conversation_text: ScrolledText | None
    dialog_intent_text: ScrolledText | None
    dialog_intent_table: ttk.Treeview | None
    dialog_billing_text: ScrolledText | None
    dialog_billing_table: ttk.Treeview | None
    dialog_intent_queue_text: ScrolledText | None
    dialog_strategy_text: ScrolledText | None
    conversation_workflow_text: ScrolledText | None
    conversation_strategy_history_text: ScrolledText | None
    conversation_strategy_input_text: tk.Text | None
    conversation_system_instruction_text: ScrolledText | None
    conversation_intent_text: ScrolledText | None
    conversation_customer_profile_text: ScrolledText | None
    conversation_pending_items_prompt_text: ScrolledText | None
    conversation_summary_prompt_text: ScrolledText | None
    conversation_strategy_prompt_text: ScrolledText | None
    call_record_tree: ttk.Treeview | None
    call_record_summary_text: tk.Text | None  # 合并视图：总结/承诺/策略 三合一
    call_record_commitments_text: ScrolledText | None  # 已废弃，保留字段兼容性（值为 None）
    call_record_strategy_text: ScrolledText | None  # 已废弃，保留字段兼容性（值为 None）
    customer_data_record_tree: ttk.Treeview | None
    customer_data_panes: ttk.Panedwindow | None
    customer_data_profile_table: ttk.Treeview | None
    customer_data_calls_canvas: tk.Canvas | None  # 已废弃，值为 None
    customer_data_calls_container: ttk.Frame | None  # 已废弃，值为 None
    customer_data_call_entries_wrap: tk.Text | None  # 单一文本区，替代原 Canvas 多 widget 方案
    customer_data_list_sash: int = -1
    call_record_state: CallRecordPageState = field(default_factory=CallRecordPageState)
    customer_data_state: CustomerDataPageState = field(default_factory=CustomerDataPageState)
    call_record_items_cache: list[dict[str, str]] = field(default_factory=list)
    call_record_cache_version: int = 0
    call_record_list_dirty: bool = True
    call_record_view_loaded: bool = False
    call_record_item_by_iid: dict[str, dict[str, str]] = field(default_factory=dict)
    call_record_item_by_id: dict[str, dict[str, str]] = field(default_factory=dict)
    customer_data_items_cache: list[tuple[str, str]] = field(default_factory=list)
    customer_data_cache_version: int = 0
    customer_data_list_dirty: bool = True
    customer_data_view_loaded: bool = False
    customer_data_customer_by_iid: dict[str, str] = field(default_factory=dict)
    customer_data_case_by_iid: dict[str, dict[str, object]] = field(default_factory=dict)
    customer_data_case_cache_by_name: dict[str, dict[str, object]] = field(default_factory=dict)
    conversation_strategy_history: list[dict[str, str]] = field(default_factory=list)
    conversation_customer_profile_history: list[dict[str, str]] = field(default_factory=list)
    conversation_intent_generator_history: list[dict[str, str]] = field(default_factory=list)
    dialog_conversation_history_by_customer: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    dialog_conversation_active_customer_key: str = ""
    customer_data_last_render_key: str = ""
    data_dir: Path | None = None
    dialog_agent_stream_active: bool = False
    dialog_agent_stream_content_start: str = ""
    dialog_intent_history: list[str] = field(default_factory=list)
    dialog_intent_state_by_customer: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    current_session_customer_lines: list[str] = field(default_factory=list)
    selected_call_record_id: str = ""
    selected_call_record_cache_version: int = 0
    selected_customer_name: str = ""
    selected_customer_cache_version: int = 0
    active_page: str = "profile"
    ui_loaded: bool = True
    workflow_doc: dict[str, str] = field(default_factory=lambda: {key: "" for key in _WORKFLOW_DOC_KEYS})
    workflow_doc_dirty: bool = False
    runtime_state: dict[str, object] = field(
        default_factory=lambda: {
            "conversation_strategy_history": [],
            "conversation_customer_profile_history": [],
            "conversation_intent_generator_history": [],
            "dialog_conversation_history_by_customer": {},
            "dialog_conversation_active_customer_key": "",
            "customer_data_last_render_key": "",
            "dialog_agent_stream_active": False,
            "dialog_agent_stream_content_start": "",
            "dialog_intent_history": [],
            "dialog_intent_state_by_customer": {},
            "current_session_customer_lines": [],
        }
    )
    ui_snapshot: dict[str, str] = field(default_factory=dict)
    ui_needs_restore: bool = False
    last_activated_seq: int = 0
