from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from collections import deque


def _cleanup_old_logs(log_dir: Path, max_age_seconds: float = 7200.0) -> None:
    """删除 log_dir 中修改时间早于 max_age_seconds 的 .log 文件。"""
    try:
        if not log_dir.exists():
            return
        cutoff = time.time() - max_age_seconds
        for f in log_dir.iterdir():
            if f.suffix != ".log":
                continue
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass

try:
    from ..models.conversation_tab import CallRecordPageState
except Exception:
    from models.conversation_tab import CallRecordPageState

try:
    from ..models.conversation_tab import CustomerDataPageState
except Exception:
    from models.conversation_tab import CustomerDataPageState


def init_runtime_fields(
    app,
    *,
    runtime_audio_config_filename: str,
    fixed_startup_command: str,
) -> None:
    is_frozen = bool(getattr(sys, "frozen", False))
    startup_command = fixed_startup_command
    if is_frozen:
        workspace_dir = Path(sys.executable).resolve().parent
        meipass_dir = Path(getattr(sys, "_MEIPASS", workspace_dir))
        resource_root = meipass_dir
        backend_exe = workspace_dir / "backend_runtime" / "mic_chunk_client_backend.exe"
        if not backend_exe.exists():
            backend_exe = workspace_dir / "mic_chunk_client_backend.exe"
        if backend_exe.exists():
            startup_command = str(backend_exe)
    else:
        resource_root = Path(__file__).resolve().parent.parent.parent
        workspace_dir = resource_root

    ui_resource_dir = resource_root / "client_mic_chunk_ui_v1"
    if not ui_resource_dir.exists():
        ui_resource_dir = resource_root

    bundled_data_dir = resource_root / "Data"
    workspace_data_dir = workspace_dir / "Data"
    if bundled_data_dir.exists():
        workspace_data_dir.mkdir(parents=True, exist_ok=True)
        for child in bundled_data_dir.iterdir():
            target = workspace_data_dir / child.name
            if target.exists():
                continue
            try:
                if child.is_dir():
                    shutil.copytree(child, target)
                else:
                    shutil.copy2(child, target)
            except Exception:
                pass

    app._workspace_dir = workspace_dir
    app._resource_dir = resource_root
    app._ui_resource_dir = ui_resource_dir
    app._runtime_log_dir = app._workspace_dir / "logs"
    _cleanup_old_logs(app._runtime_log_dir)
    app._runtime_log_file_path = None
    app._runtime_log_file = None
    app._default_command = startup_command
    app._settings_asr_command = startup_command
    app._runtime_audio_config_path = app._workspace_dir / runtime_audio_config_filename
    app.flow_editor_panel = None
    app.flow_monitor_canvas = None
    app.flow_panes = None
    app.flow_json_box = None
    app._audio_config_loaded = False
    app.customer_profile_text = None
    app.workflow_text = None
    app.system_instruction_text = None
    app.ai_analysis_text = None
    app.call_record_tree = None
    app.customer_data_record_tree = None
    app.call_record_summary_text = None
    app.call_record_commitments_text = None
    app.call_record_strategy_text = None
    app.customer_data_panes = None
    app.customer_data_profile_table = None
    app.customer_data_calls_canvas = None
    app.customer_data_calls_container = None
    app.customer_data_call_entries_wrap = None
    app.asr_text = None
    app.asr_commit_text = None
    app.tts_text = None
    app.nlp_input_text = None
    app.dialog_intent_text = None
    app.dialog_intent_table = None
    app.dialog_intent_queue_text = None
    app.dialog_strategy_text = None
    app._dialog_intent_history = []
    app._dialog_intent_state_by_customer = {}
    app._dialog_intent_state_current_customer_key = ""
    app._current_session_customer_lines = []
    app._current_session_dialog_lines = []
    app.intent_text = None
    app.intent_system_text = None
    app.intent_prompt_text = None
    app.dialog_billing_text = None
    app.dialog_billing_table = None
    app.profile_call_btn = None
    app.conversation_profile_status_var = None
    app.conversation_profile_status_label = None
    app.monitor_process_status_label = None
    app.conversation_workflow_text = None
    app.conversation_strategy_history_text = None
    app.conversation_strategy_input_text = None
    app.conversation_system_instruction_text = None
    app.conversation_intent_text = None
    app.conversation_customer_profile_text = None
    app.conversation_pending_items_prompt_text = None
    app.conversation_summary_prompt_text = None
    app.conversation_strategy_prompt_text = None
    app._workflow_doc = {
        "system_instruction": "",
        "intent": "",
        "workflow_profile": "",
        "strategy": "",
        "strategy_input": "",
        "pending_items_prompt": "",
        "dialog_summary_prompt": "",
        "dialog_strategy_prompt": "",
    }
    app._conversation_workflow_syncing = False
    app._conversation_strategy_history = []
    app._conversation_customer_profile_history = []
    app._conversation_intent_generator_history = []
    app._dialog_conversation_history_by_customer = {}
    app._dialog_conversation_active_customer_key = ""
    app._conversation_runtime_state = {
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
    app._last_billing_total_cost = 0.0
    app._last_billing_duration_seconds = 0.0
    app._last_billing_price_per_minute = 0.0
    app._call_record_page_state = CallRecordPageState()
    app._customer_data_page_state = CustomerDataPageState()
    app._call_record_item_by_iid = {}
    app._call_record_item_by_id = {}
    app._call_record_cache_version = 0
    app._selected_call_record_id = ""
    app._selected_call_record_cache_version = 0
    app._customer_data_customer_by_iid = {}
    app._customer_data_case_by_iid = {}
    app._customer_data_case_cache_by_name = {}
    app._customer_data_cache_version = 0
    app._customer_data_last_render_key = ""
    app._selected_customer_name = ""
    app._selected_customer_cache_version = 0
    app._conversation_page_switcher = None
    app._main_notebook = None
    app._conversation_tabs = {}
    app._conversation_tab_id_by_frame_name = {}
    app._conversation_template_tab_id = ""
    app._active_conversation_tab_id = ""
    app._bound_conversation_tab_id = ""
    app._runtime_conversation_tab_id = ""
    app._conversation_tab_counter = 0
    app._tab_data_dir_override = None
    app._conversation_tab_registry_tree = None
    app._conversation_tab_registry_iid_to_tab_id = {}
    app._suspend_tab_registry_save = False
    app._snapshot_autosave_after_id = None
    app._snapshot_autosave_interval_ms = 3000
    app._debug_tab_perf_logging = False
    app._debug_ui_block_logging = False
    app._debug_customer_data_logging = True
    app._tab_switch_freeze_internal = False
    app._tab_switch_freeze_notice_shown = False
    app._intent_sync_after_id = None
    app._conversation_strategy_dialog = None
    app._conversation_customer_profile_dialog = None
    app._conversation_intent_dialog = None


def init_session_state_fields(app) -> None:
    app._event_history = []
    app._send_count = 0
    app._send_total_ms = 0
    app._control_endpoint = ""
    app._media_endpoint = ""
    app._single_endpoint = ""
    app._tts_stream_content_start = ""
    app._tts_stream_active = False
    app._asr_stream_content_start = ""
    app._asr_stream_active = False
    app._asr_history_lines = []
    app._asr_wait_since = 0.0
    app._asr_first_commit_seen = False
    app._asr_wait_warned = False
    app._main_mic_open = False
    app._settings_mic_open = False
    app._dialog_agent_stream_active = False
    app._dialog_agent_stream_content_start = ""
    app._settings_asr_stream_active = False
    app._settings_asr_stream_phase = ""
    app._settings_asr_stream_line_start = ""
    app._settings_asr_stream_content_start = ""
    app._settings_asr_stream_widget = None
    app._asr_submit_thinking_seen = False
    app._llm_submit_running = False
    app._llm_freeze_depth = 0
    app._llm_freeze_widget_style = {}
    app._runtime_system_prompt = ""
    app._loaded_workflow_json_text = ""
    app._loaded_workflow_json_path = ""
    app._loaded_workflow_json_nodes = 0
    app._loaded_workflow_json_edges = 0
    app._loaded_workflow_payload = None
    app._flow_active_node_id = ""
    app._flow_hover_node_id = ""
    app._flow_tooltip_window = None
    app._flow_tooltip_label = None
    app._editor_dialogs = []
    app._event_backlog_high = deque()
    app._event_backlog_normal = deque()
    app._settings_event_backlog = deque()
    app._pending_log_lines = []
    app._next_log_flush_at = 0.0
    app._send_done_summary_second = ""
    app._send_done_summary_count = 0
    app._send_done_summary_first_chunk = 0
    app._send_done_summary_last_chunk = 0
    app._send_done_summary_total_ms = 0
    app._send_done_summary_max_ms = 0
    app._send_done_summary_deadline = 0.0
    app._send_fail_summary_second = ""
    app._send_fail_summary_reason = ""
    app._send_fail_summary_count = 0
    app._send_fail_summary_first_chunk = 0
    app._send_fail_summary_last_chunk = 0
    app._session_trace_start_source = ""
    app._session_trace_start_trigger = ""
    app._session_trace_last_command = ""
    app._session_trace_last_action = ""
    app._session_trace_first_tts_frame_seen = False
    app._session_trace_tts_started = False
    app._session_trace_tts_empty = False
    app._session_trace_disconnect_channels = []
    app._session_trace_summary_emitted = False
    app._dialog_summary_pending_warning = False
    app._allow_next_tab_switch_without_summary = False
    app._skip_auto_start_dialog_once = False
    app._call_overlay_window = None
    app._call_overlay_canvas = None
    app._call_overlay_canvas_bg_item = None
    app._call_overlay_canvas_calling_item = None
    app._call_overlay_canvas_status_item = None
    app._call_overlay_accept_button = None
    app._call_overlay_hangup_button = None
    app._call_overlay_accept_button_place = None
    app._call_overlay_hangup_button_place = None
    app._call_overlay_drag_offset = None
    app._call_overlay_calling_anim_id = None
    app._call_overlay_calling_step = 0
    app._call_overlay_status_poll_after_id = None
    app._call_overlay_bg_image = None
    app._call_overlay_audio_started = False
    app._call_overlay_audio_click_ready = False
    app._call_overlay_phase = "connecting"
    app._call_overlay_reconnect_pending = False
    app._call_overlay_restart_in_progress = False
    app._call_overlay_restart_scheduled = False
