from __future__ import annotations

import json
import os
import queue
import re
import sys
import ctypes
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, LEFT, RIGHT, X, Y, messagebox
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable, Iterator

import requests
try:
    import winsound
except Exception:
    winsound = None

try:
    from .backend import ClientProcessBridge, UiEvent  # type: ignore[attr-defined]
except Exception:
    from backend import ClientProcessBridge, UiEvent

try:
    from .flow_editor.panel import FlowEditorPanel  # type: ignore[attr-defined]
except Exception:
    from flow_editor.panel import FlowEditorPanel

try:
    from .flow_editor.canvas_view import FlowCanvas  # type: ignore[attr-defined]
    from .flow_editor.models import Edge as FlowEdge, Node as FlowNode, NodeType  # type: ignore[attr-defined]
except Exception:
    from flow_editor.canvas_view import FlowCanvas
    from flow_editor.models import Edge as FlowEdge, Node as FlowNode, NodeType

try:
    from .config.audio_runtime import (
        AGGRESSIVE_PROFILE_OVERRIDES,
        ASR_FIRST_PROFILE_OVERRIDES,
        AUDIO_TUNING_SPECS,
        RUNTIME_AUDIO_CONFIG_FILENAME,
    )
    from .models.conversation_tab import ConversationTabContext
except Exception:
    from config.audio_runtime import (
        AGGRESSIVE_PROFILE_OVERRIDES,
        ASR_FIRST_PROFILE_OVERRIDES,
        AUDIO_TUNING_SPECS,
        RUNTIME_AUDIO_CONFIG_FILENAME,
    )
    from models.conversation_tab import ConversationTabContext

try:
    from .controllers.editor_dialog import (
        build_dialog_llm_prompt as ctrl_build_dialog_llm_prompt,
        close_settings_editor_dialog as ctrl_close_settings_editor_dialog,
        on_editor_dialog_submit_done as ctrl_on_editor_dialog_submit_done,
        open_settings_editor_dialog as ctrl_open_settings_editor_dialog,
        poll_editor_dialog_events as ctrl_poll_editor_dialog_events,
        submit_editor_dialog as ctrl_submit_editor_dialog,
        submit_editor_dialog_worker as ctrl_submit_editor_dialog_worker,
    )
    from .controllers.app_bootstrap import (
        init_runtime_fields as ctrl_init_runtime_fields,
        init_session_state_fields as ctrl_init_session_state_fields,
    )
    from .controllers.audio_helpers import normalize_aec_profile as ctrl_normalize_aec_profile
    from .controllers.audio_config import (
        apply_audio_config_to_commands as ctrl_apply_audio_config_to_commands,
        apply_audio_tuning_values_to_command as ctrl_apply_audio_tuning_values_to_command,
        build_runtime_audio_config_payload as ctrl_build_runtime_audio_config_payload,
        collect_validated_audio_tuning_values as ctrl_collect_validated_audio_tuning_values,
        load_audio_config_from_command_text as ctrl_load_audio_config_from_command_text,
        load_audio_config_from_current_command as ctrl_load_audio_config_from_current_command,
        load_runtime_audio_config as ctrl_load_runtime_audio_config,
        reset_audio_config_defaults as ctrl_reset_audio_config_defaults,
        reset_audio_config_defaults_for_profile as ctrl_reset_audio_config_defaults_for_profile,
        save_audio_config_from_ui as ctrl_save_audio_config_from_ui,
        save_runtime_audio_config as ctrl_save_runtime_audio_config,
        set_audio_config_status as ctrl_set_audio_config_status,
    )
    from .controllers.server_env import (
        apply_server_env_to_command as ctrl_apply_server_env_to_command,
        apply_server_env_to_command_vars as ctrl_apply_server_env_to_command_vars,
        apply_server_env_to_conversation_command as ctrl_apply_server_env_to_conversation_command,
        sync_conversation_server_env_from_command as ctrl_sync_conversation_server_env_from_command,
        sync_server_env_from_command as ctrl_sync_server_env_from_command,
        sync_server_env_from_command_to_var as ctrl_sync_server_env_from_command_to_var,
    )
    from .controllers.network_probe import (
        probe_public_ip as ctrl_probe_public_ip,
        request_network_probe_from_settings as ctrl_request_network_probe_from_settings,
        request_whoami_from_settings as ctrl_request_whoami_from_settings,
        resolve_whoami_base_url as ctrl_resolve_whoami_base_url,
    )
    from .controllers.log_buffer import (
        buffer_log_line as ctrl_buffer_log_line,
        consume_send_done_log as ctrl_consume_send_done_log,
        flush_log_buffer as ctrl_flush_log_buffer,
        flush_send_done_summary as ctrl_flush_send_done_summary,
        reset_send_done_summary as ctrl_reset_send_done_summary,
    )
    from .controllers.asr_switch import toggle_asr as ctrl_toggle_asr
    from .controllers.flow_monitor_ui import (
        apply_flow_monitor_active_node_style as ctrl_apply_flow_monitor_active_node_style,
        bind_flow_monitor_hover_events as ctrl_bind_flow_monitor_hover_events,
        center_flow_monitor_node as ctrl_center_flow_monitor_node,
        flow_monitor_node_id_at as ctrl_flow_monitor_node_id_at,
        flow_monitor_zoom_in as ctrl_flow_monitor_zoom_in,
        flow_monitor_zoom_out as ctrl_flow_monitor_zoom_out,
        flow_monitor_zoom_reset as ctrl_flow_monitor_zoom_reset,
        highlight_flow_monitor_node as ctrl_highlight_flow_monitor_node,
        hide_flow_tooltip as ctrl_hide_flow_tooltip,
        lock_flow_monitor_interactions as ctrl_lock_flow_monitor_interactions,
        on_flow_monitor_leave as ctrl_on_flow_monitor_leave,
        on_flow_monitor_motion as ctrl_on_flow_monitor_motion,
        restore_flow_monitor_highlight as ctrl_restore_flow_monitor_highlight,
        show_flow_tooltip as ctrl_show_flow_tooltip,
        toggle_flow_script_panel as ctrl_toggle_flow_script_panel,
    )
    from .controllers.flow_graph_models import (
        build_flow_graph_models as ctrl_build_flow_graph_models,
        coerce_node_type as ctrl_coerce_node_type,
        to_float as ctrl_to_float,
    )
    from .controllers.workflow_loader import (
        clear_loaded_workflow_json as ctrl_clear_loaded_workflow_json,
        load_workflow_json_file as ctrl_load_workflow_json_file,
        render_flow_monitor_graph as ctrl_render_flow_monitor_graph,
    )
    from .controllers.workflow_events import handle_workflow_progress_event as ctrl_handle_workflow_progress_event
    from .controllers.removed_features import (
        generate_intents_from_settings as ctrl_generate_intents_from_settings_removed,
        open_customer_profile_dialog as ctrl_open_customer_profile_dialog_removed,
        open_workflow_dialog as ctrl_open_workflow_dialog_removed,
        submit_customer_profile_from_panel as ctrl_submit_customer_profile_from_panel_removed,
        submit_settings_panel_llm as ctrl_submit_settings_panel_llm_removed,
        submit_workflow_from_panel as ctrl_submit_workflow_from_panel_removed,
    )
    from .controllers.prompt_templates import (
        get_dialog_strategy_prompt_template as ctrl_get_dialog_strategy_prompt_template,
        get_dialog_summary_prompt_template as ctrl_get_dialog_summary_prompt_template,
        get_pending_items_prompt_template as ctrl_get_pending_items_prompt_template,
    )
    from .controllers.strategy_dialog_history import (
        render_conversation_strategy_dialog_history as ctrl_render_conversation_strategy_dialog_history,
    )
    from .controllers.widget_appenders import append_text_to_widget_with_tag as ctrl_append_text_to_widget_with_tag
    from .controllers.bubble_routing import (
        is_instruction_header_line as ctrl_is_instruction_header_line,
        is_llm_header_line as ctrl_is_llm_header_line,
        try_append_customer_profile_bubble as ctrl_try_append_customer_profile_bubble,
    )
    from .controllers.bubble_canvas import draw_rounded_rect as ctrl_draw_rounded_rect
    from .controllers.bubble_updates import append_customer_profile_bubble_text as ctrl_append_customer_profile_bubble_text
    from .controllers.bubble_renderer import render_customer_profile_bubble_canvas as ctrl_render_customer_profile_bubble_canvas
    from .controllers.bubble_rows import insert_customer_profile_bubble_row as ctrl_insert_customer_profile_bubble_row
    from .controllers.bubble_text_wrap import wrap_text_for_strategy_history_bubble as ctrl_wrap_text_for_strategy_history_bubble
    from .controllers.history_tags import (
        update_customer_profile_dialog_history_tags as ctrl_update_customer_profile_dialog_history_tags,
        update_conversation_strategy_dialog_history_tags as ctrl_update_conversation_strategy_dialog_history_tags,
    )
    from .controllers.profile_dialog_history import (
        render_conversation_customer_profile_dialog_history as ctrl_render_conversation_customer_profile_dialog_history,
    )
    from .controllers.intent_dialog_history import (
        render_conversation_intent_dialog_history as ctrl_render_conversation_intent_dialog_history,
    )
    from .controllers.live_bubble_phases import (
        append_live_conversation_customer_profile_content_chunk as ctrl_append_live_conversation_customer_profile_content_chunk_phase,
        append_live_conversation_customer_profile_thinking_chunk as ctrl_append_live_conversation_customer_profile_thinking_chunk_phase,
        append_live_conversation_intent_content_chunk as ctrl_append_live_conversation_intent_content_chunk_phase,
        append_live_conversation_intent_thinking_chunk as ctrl_append_live_conversation_intent_thinking_chunk_phase,
        prepare_live_conversation_intent_response_bubble as ctrl_prepare_live_conversation_intent_response_bubble_phase,
        prepare_live_conversation_customer_profile_response_bubble as ctrl_prepare_live_conversation_customer_profile_response_bubble_phase,
    )
    from .controllers.strategy_generator import (
        append_conversation_strategy_history as ctrl_append_conversation_strategy_history,
        append_live_conversation_strategy_content_chunk as ctrl_append_live_conversation_strategy_content_chunk,
        append_live_conversation_strategy_thinking_chunk as ctrl_append_live_conversation_strategy_thinking_chunk,
        build_conversation_strategy_prompt_with_history as ctrl_build_conversation_strategy_prompt_with_history,
        generate_conversation_strategy_in_dialog as ctrl_generate_conversation_strategy_in_dialog,
        get_conversation_strategy_history_for_tab as ctrl_get_conversation_strategy_history_for_tab,
        on_submit_conversation_strategy_llm_done as ctrl_on_submit_conversation_strategy_llm_done,
        open_conversation_strategy_generator_dialog as ctrl_open_conversation_strategy_generator_dialog,
        prepare_live_conversation_strategy_response_bubble as ctrl_prepare_live_conversation_strategy_response_bubble,
        render_conversation_strategy_history_panel as ctrl_render_conversation_strategy_history_panel,
        save_conversation_strategy_dialog as ctrl_save_conversation_strategy_dialog,
        submit_conversation_strategy_from_panel as ctrl_submit_conversation_strategy_from_panel,
        submit_conversation_strategy_llm_worker as ctrl_submit_conversation_strategy_llm_worker,
    )
    from .controllers.runtime_events import (
        clear_views as ctrl_clear_views,
        drain_event_queues as ctrl_drain_event_queues,
        export_events as ctrl_export_events,
        handle_event as ctrl_handle_event,
        handle_settings_asr_event as ctrl_handle_settings_asr_event,
        is_high_priority_event as ctrl_is_high_priority_event,
        poll_events as ctrl_poll_events,
        pop_next_buffered_event as ctrl_pop_next_buffered_event,
    )
    from .controllers.dialog_summary import (
        build_dialog_summary_llm_prompt as ctrl_build_dialog_summary_llm_prompt,
        build_dialog_summary_text as ctrl_build_dialog_summary_text,
        build_next_dialog_strategy_llm_prompt as ctrl_build_next_dialog_strategy_llm_prompt,
        build_next_dialog_strategy_text as ctrl_build_next_dialog_strategy_text,
        extract_pending_commitment_items as ctrl_extract_pending_commitment_items,
        format_commitment_confirmation_text as ctrl_format_commitment_confirmation_text,
        open_commitment_confirmation_dialog as ctrl_open_commitment_confirmation_dialog,
        open_dialog_summary_modal as ctrl_open_dialog_summary_modal,
    )
    from .controllers.tab_manager import (
        apply_conversation_tab_snapshot as ctrl_apply_conversation_tab_snapshot,
        bind_conversation_tab_context as ctrl_bind_conversation_tab_context,
        build_unique_conversation_tab_title as ctrl_build_unique_conversation_tab_title,
        capture_conversation_tab_snapshot as ctrl_capture_conversation_tab_snapshot,
        create_conversation_tab_from_settings as ctrl_create_conversation_tab_from_settings,
        create_conversation_tab_internal as ctrl_create_conversation_tab_internal,
        delete_conversation_tab as ctrl_delete_conversation_tab,
        delete_selected_conversation_tab_from_settings as ctrl_delete_selected_conversation_tab_from_settings,
        get_conversation_tab_snapshot_path as ctrl_get_conversation_tab_snapshot_path,
        is_template_conversation_context_bound as ctrl_is_template_conversation_context_bound,
        load_persisted_conversation_tab_snapshots as ctrl_load_persisted_conversation_tab_snapshots,
        load_persisted_conversation_tabs as ctrl_load_persisted_conversation_tabs,
        on_main_notebook_tab_click as ctrl_on_main_notebook_tab_click,
        on_main_notebook_tab_changed as ctrl_on_main_notebook_tab_changed,
        read_conversation_tab_registry_entries as ctrl_read_conversation_tab_registry_entries,
        refresh_conversation_tab_registry_view as ctrl_refresh_conversation_tab_registry_view,
        register_conversation_tab_context as ctrl_register_conversation_tab_context,
        safe_set_profile_sash as ctrl_safe_set_profile_sash,
        save_persisted_conversation_tab_snapshots as ctrl_save_persisted_conversation_tab_snapshots,
        save_persisted_conversation_tabs as ctrl_save_persisted_conversation_tabs,
        using_conversation_tab_context as ctrl_using_conversation_tab_context,
        write_conversation_tab_meta as ctrl_write_conversation_tab_meta,
    )
    from .controllers.customer_data import (
        apply_call_record_profile_and_workflow as ctrl_apply_call_record_profile_and_workflow,
        build_call_record_items as ctrl_build_call_record_items,
        build_customer_case_cache_by_name as ctrl_build_customer_case_cache_by_name,
        build_visible_customer_records as ctrl_build_visible_customer_records,
        clear_call_record_detail as ctrl_clear_call_record_detail,
        clear_customer_data_call_entry_views as ctrl_clear_customer_data_call_entry_views,
        clear_customer_data_profile_table as ctrl_clear_customer_data_profile_table,
        extract_latest_strategy_from_case_data as ctrl_extract_latest_strategy_from_case_data,
        get_selected_customer_case_data as ctrl_get_selected_customer_case_data,
        load_call_records_into_list as ctrl_load_call_records_into_list,
        load_customer_data_records_into_list as ctrl_load_customer_data_records_into_list,
        mark_conversation_tab_data_dirty as ctrl_mark_conversation_tab_data_dirty,
        on_call_record_call as ctrl_on_call_record_call,
        on_call_record_selected as ctrl_on_call_record_selected,
        on_call_record_tree_click as ctrl_on_call_record_tree_click,
        on_customer_data_record_selected as ctrl_on_customer_data_record_selected,
        on_customer_data_tree_click as ctrl_on_customer_data_tree_click,
        on_customer_data_tree_double_click as ctrl_on_customer_data_tree_double_click,
        open_call_record_detail_window as ctrl_open_call_record_detail_window,
        open_customer_data_detail_window as ctrl_open_customer_data_detail_window,
        prepare_call_context_from_customer_data_and_workflow_page as ctrl_prepare_call_context_from_customer_data_and_workflow_page,
        render_call_record_detail as ctrl_render_call_record_detail,
        render_customer_data_call_entry_views as ctrl_render_customer_data_call_entry_views,
        delete_customer_by_name as ctrl_delete_customer_by_name,
    )
    from .controllers.profile_intent_dialog import (
        append_conversation_customer_profile_history as ctrl_append_conversation_customer_profile_history,
        append_conversation_intent_generator_history as ctrl_append_conversation_intent_generator_history,
        build_conversation_customer_profile_prompt_with_history as ctrl_build_conversation_customer_profile_prompt_with_history,
        build_conversation_intent_prompt_with_history as ctrl_build_conversation_intent_prompt_with_history,
        generate_conversation_customer_profile_in_dialog as ctrl_generate_conversation_customer_profile_in_dialog,
        generate_conversation_intent_in_dialog as ctrl_generate_conversation_intent_in_dialog,
        get_conversation_customer_profile_history_for_tab as ctrl_get_conversation_customer_profile_history_for_tab,
        get_conversation_intent_generator_history_for_tab as ctrl_get_conversation_intent_generator_history_for_tab,
        on_submit_conversation_customer_profile_llm_done as ctrl_on_submit_conversation_customer_profile_llm_done,
        on_submit_conversation_intent_llm_done as ctrl_on_submit_conversation_intent_llm_done,
        open_conversation_customer_profile_generator_dialog as ctrl_open_conversation_customer_profile_generator_dialog,
        open_conversation_intent_generator_dialog as ctrl_open_conversation_intent_generator_dialog,
        render_conversation_customer_profile_dialog_history as ctrl_render_conversation_customer_profile_dialog_history,
        save_conversation_customer_profile_dialog as ctrl_save_conversation_customer_profile_dialog,
        save_conversation_intent_dialog as ctrl_save_conversation_intent_dialog,
        submit_conversation_customer_profile_llm_worker as ctrl_submit_conversation_customer_profile_llm_worker,
        submit_conversation_intent_llm_worker as ctrl_submit_conversation_intent_llm_worker,
    )
    from .controllers.panel_llm import (
        append_ai_analysis_text as ctrl_append_ai_analysis_text,
        append_asr_submit_thinking_chunk as ctrl_append_asr_submit_thinking_chunk,
        append_dialog_output_chunk as ctrl_append_dialog_output_chunk,
        append_intent_system_text as ctrl_append_intent_system_text,
        append_llm_prompt_block_to_system_instruction as ctrl_append_llm_prompt_block_to_system_instruction,
        append_system_instruction_text as ctrl_append_system_instruction_text,
        append_text_to_widget as ctrl_append_text_to_widget,
        build_intent_generation_prompt as ctrl_build_intent_generation_prompt,
        build_system_instruction_prompt_for_submit as ctrl_build_system_instruction_prompt_for_submit,
        generate_intents_from_settings as ctrl_generate_intents_from_settings,
        generate_intents_from_settings_worker as ctrl_generate_intents_from_settings_worker,
        log_llm_prompts as ctrl_log_llm_prompts,
        on_customer_profile_submit_from_asr_done as ctrl_on_customer_profile_submit_from_asr_done,
        on_generate_intents_from_settings_done as ctrl_on_generate_intents_from_settings_done,
        on_submit_settings_panel_llm_done as ctrl_on_submit_settings_panel_llm_done,
        set_llm_generation_frozen as ctrl_set_llm_generation_frozen,
        strip_panel_llm_debug_blocks as ctrl_strip_panel_llm_debug_blocks,
        submit_settings_panel_llm as ctrl_submit_settings_panel_llm,
        submit_settings_panel_llm_worker as ctrl_submit_settings_panel_llm_worker,
        trigger_customer_profile_submit_from_asr as ctrl_trigger_customer_profile_submit_from_asr,
        trigger_customer_profile_submit_from_asr_worker as ctrl_trigger_customer_profile_submit_from_asr_worker,
    )
    from .controllers.settings_asr import (
        begin_asr_wait as ctrl_begin_asr_wait,
        check_asr_wait_timeout as ctrl_check_asr_wait_timeout,
        close_settings_asr_stream_line as ctrl_close_settings_asr_stream_line,
        get_asr_prefix as ctrl_get_asr_prefix,
        is_microphone_open as ctrl_is_microphone_open,
        log_asr_monitor as ctrl_log_asr_monitor,
        mark_asr_commit_seen as ctrl_mark_asr_commit_seen,
        replace_settings_asr_stream_text as ctrl_replace_settings_asr_stream_text,
        replace_settings_asr_stream_with_commit as ctrl_replace_settings_asr_stream_with_commit,
        reset_asr_wait as ctrl_reset_asr_wait,
        set_microphone_open as ctrl_set_microphone_open,
        start_settings_asr as ctrl_start_settings_asr,
        start_settings_asr_stream_line as ctrl_start_settings_asr_stream_line,
        update_microphone_state_from_log as ctrl_update_microphone_state_from_log,
    )
    from .controllers.profile_table import (
        fill_profile_table_from_text as ctrl_fill_profile_table_from_text,
        refresh_dialog_profile_table as ctrl_refresh_dialog_profile_table,
        resize_customer_data_profile_columns as ctrl_resize_customer_data_profile_columns,
        resize_dialog_profile_columns as ctrl_resize_dialog_profile_columns,
        resize_profile_table_columns as ctrl_resize_profile_table_columns,
    )
    from .controllers.system_prompt import (
        build_runtime_system_prompt as ctrl_build_runtime_system_prompt,
    )
    from .controllers.data_records import (
        build_new_tab_data_dir as ctrl_build_new_tab_data_dir,
        copy_tab_case_files as ctrl_copy_tab_case_files,
        create_new_customer_record_from_jsonl as ctrl_create_new_customer_record_from_jsonl,
        get_data_dir as ctrl_get_data_dir,
        save_dialog_summary_record as ctrl_save_dialog_summary_record,
        save_new_customer_record as ctrl_save_new_customer_record,
    )
    from .controllers.workflow_sync import (
        on_conversation_workflow_text_edited as ctrl_on_conversation_workflow_text_edited,
        refresh_runtime_system_prompt_only as ctrl_refresh_runtime_system_prompt_only,
        refresh_system_instruction as ctrl_refresh_system_instruction,
        _set_workflow_doc_dirty as ctrl_set_workflow_doc_dirty,
    )
    from .controllers.stream_runtime import (
        append_dialog_agent_stream_text as ctrl_append_dialog_agent_stream_text,
        append_dialog_conversation_line as ctrl_append_dialog_conversation_line,
        append_dialog_customer_intent as ctrl_append_dialog_customer_intent,
        append_dialog_session_marker as ctrl_append_dialog_session_marker,
        append_dialog_session_separator as ctrl_append_dialog_session_separator,
        append_line as ctrl_append_line,
        append_line_with_tag as ctrl_append_line_with_tag,
        append_tts_line as ctrl_append_tts_line,
        append_tts_stream_text as ctrl_append_tts_stream_text,
        clear_text as ctrl_clear_text,
        close_asr_stream_line as ctrl_close_asr_stream_line,
        close_dialog_agent_stream_line as ctrl_close_dialog_agent_stream_line,
        close_tts_stream_line as ctrl_close_tts_stream_line,
        extract_dialog_current_session_text as ctrl_extract_dialog_current_session_text,
        parse_intent_window as ctrl_parse_intent_window,
        replace_asr_stream_text as ctrl_replace_asr_stream_text,
        replace_dialog_agent_stream_text as ctrl_replace_dialog_agent_stream_text,
        refresh_dialog_conversation_for_active_customer as ctrl_refresh_dialog_conversation_for_active_customer,
        render_dialog_conversation_history as ctrl_render_dialog_conversation_history,
        replace_tts_stream_text as ctrl_replace_tts_stream_text,
        reset_runtime_status as ctrl_reset_runtime_status,
        sanitize_inline_text as ctrl_sanitize_inline_text,
        set_dialog_conversation_active_customer as ctrl_set_dialog_conversation_active_customer,
        set_text_content as ctrl_set_text_content,
        sync_conversation_profile_status as ctrl_sync_conversation_profile_status,
        start_asr_stream_line as ctrl_start_asr_stream_line,
        start_dialog_agent_stream_line as ctrl_start_dialog_agent_stream_line,
        start_tts_stream_line as ctrl_start_tts_stream_line,
        trim_scrolled_text as ctrl_trim_scrolled_text,
    )
    from .controllers.layout_builder import build_layout as ctrl_build_layout
    from .controllers.conversation_tab_builder import build_conversation_tab as ctrl_build_conversation_tab
    from .controllers.call_timer_overlay import CallTimerOverlay as ctrl_CallTimerOverlay
except Exception:
    from controllers.app_bootstrap import (
        init_runtime_fields as ctrl_init_runtime_fields,
        init_session_state_fields as ctrl_init_session_state_fields,
    )
    from controllers.audio_helpers import normalize_aec_profile as ctrl_normalize_aec_profile
    from controllers.audio_config import (
        apply_audio_config_to_commands as ctrl_apply_audio_config_to_commands,
        apply_audio_tuning_values_to_command as ctrl_apply_audio_tuning_values_to_command,
        build_runtime_audio_config_payload as ctrl_build_runtime_audio_config_payload,
        collect_validated_audio_tuning_values as ctrl_collect_validated_audio_tuning_values,
        load_audio_config_from_command_text as ctrl_load_audio_config_from_command_text,
        load_audio_config_from_current_command as ctrl_load_audio_config_from_current_command,
        load_runtime_audio_config as ctrl_load_runtime_audio_config,
        reset_audio_config_defaults as ctrl_reset_audio_config_defaults,
        reset_audio_config_defaults_for_profile as ctrl_reset_audio_config_defaults_for_profile,
        save_audio_config_from_ui as ctrl_save_audio_config_from_ui,
        save_runtime_audio_config as ctrl_save_runtime_audio_config,
        set_audio_config_status as ctrl_set_audio_config_status,
    )
    from controllers.server_env import (
        apply_server_env_to_command as ctrl_apply_server_env_to_command,
        apply_server_env_to_command_vars as ctrl_apply_server_env_to_command_vars,
        apply_server_env_to_conversation_command as ctrl_apply_server_env_to_conversation_command,
        sync_conversation_server_env_from_command as ctrl_sync_conversation_server_env_from_command,
        sync_server_env_from_command as ctrl_sync_server_env_from_command,
        sync_server_env_from_command_to_var as ctrl_sync_server_env_from_command_to_var,
    )
    from controllers.network_probe import (
        probe_public_ip as ctrl_probe_public_ip,
        request_network_probe_from_settings as ctrl_request_network_probe_from_settings,
        request_whoami_from_settings as ctrl_request_whoami_from_settings,
        resolve_whoami_base_url as ctrl_resolve_whoami_base_url,
    )
    from controllers.log_buffer import (
        buffer_log_line as ctrl_buffer_log_line,
        consume_send_done_log as ctrl_consume_send_done_log,
        flush_log_buffer as ctrl_flush_log_buffer,
        flush_send_done_summary as ctrl_flush_send_done_summary,
        reset_send_done_summary as ctrl_reset_send_done_summary,
    )
    from controllers.asr_switch import toggle_asr as ctrl_toggle_asr
    from controllers.flow_monitor_ui import (
        apply_flow_monitor_active_node_style as ctrl_apply_flow_monitor_active_node_style,
        bind_flow_monitor_hover_events as ctrl_bind_flow_monitor_hover_events,
        center_flow_monitor_node as ctrl_center_flow_monitor_node,
        flow_monitor_node_id_at as ctrl_flow_monitor_node_id_at,
        flow_monitor_zoom_in as ctrl_flow_monitor_zoom_in,
        flow_monitor_zoom_out as ctrl_flow_monitor_zoom_out,
        flow_monitor_zoom_reset as ctrl_flow_monitor_zoom_reset,
        highlight_flow_monitor_node as ctrl_highlight_flow_monitor_node,
        hide_flow_tooltip as ctrl_hide_flow_tooltip,
        lock_flow_monitor_interactions as ctrl_lock_flow_monitor_interactions,
        on_flow_monitor_leave as ctrl_on_flow_monitor_leave,
        on_flow_monitor_motion as ctrl_on_flow_monitor_motion,
        restore_flow_monitor_highlight as ctrl_restore_flow_monitor_highlight,
        show_flow_tooltip as ctrl_show_flow_tooltip,
        toggle_flow_script_panel as ctrl_toggle_flow_script_panel,
    )
    from controllers.flow_graph_models import (
        build_flow_graph_models as ctrl_build_flow_graph_models,
        coerce_node_type as ctrl_coerce_node_type,
        to_float as ctrl_to_float,
    )
    from controllers.workflow_loader import (
        clear_loaded_workflow_json as ctrl_clear_loaded_workflow_json,
        load_workflow_json_file as ctrl_load_workflow_json_file,
        render_flow_monitor_graph as ctrl_render_flow_monitor_graph,
    )
    from controllers.workflow_events import handle_workflow_progress_event as ctrl_handle_workflow_progress_event
    from controllers.removed_features import (
        generate_intents_from_settings as ctrl_generate_intents_from_settings_removed,
        open_customer_profile_dialog as ctrl_open_customer_profile_dialog_removed,
        open_workflow_dialog as ctrl_open_workflow_dialog_removed,
        submit_customer_profile_from_panel as ctrl_submit_customer_profile_from_panel_removed,
        submit_settings_panel_llm as ctrl_submit_settings_panel_llm_removed,
        submit_workflow_from_panel as ctrl_submit_workflow_from_panel_removed,
    )
    from controllers.prompt_templates import (
        get_dialog_strategy_prompt_template as ctrl_get_dialog_strategy_prompt_template,
        get_dialog_summary_prompt_template as ctrl_get_dialog_summary_prompt_template,
        get_pending_items_prompt_template as ctrl_get_pending_items_prompt_template,
    )
    from controllers.strategy_dialog_history import (
        render_conversation_strategy_dialog_history as ctrl_render_conversation_strategy_dialog_history,
    )
    from controllers.widget_appenders import append_text_to_widget_with_tag as ctrl_append_text_to_widget_with_tag
    from controllers.bubble_routing import (
        is_instruction_header_line as ctrl_is_instruction_header_line,
        is_llm_header_line as ctrl_is_llm_header_line,
        try_append_customer_profile_bubble as ctrl_try_append_customer_profile_bubble,
    )
    from controllers.bubble_canvas import draw_rounded_rect as ctrl_draw_rounded_rect
    from controllers.bubble_updates import append_customer_profile_bubble_text as ctrl_append_customer_profile_bubble_text
    from controllers.bubble_renderer import render_customer_profile_bubble_canvas as ctrl_render_customer_profile_bubble_canvas
    from controllers.bubble_rows import insert_customer_profile_bubble_row as ctrl_insert_customer_profile_bubble_row
    from controllers.bubble_text_wrap import wrap_text_for_strategy_history_bubble as ctrl_wrap_text_for_strategy_history_bubble
    from controllers.history_tags import (
        update_customer_profile_dialog_history_tags as ctrl_update_customer_profile_dialog_history_tags,
        update_conversation_strategy_dialog_history_tags as ctrl_update_conversation_strategy_dialog_history_tags,
    )
    from controllers.profile_dialog_history import (
        render_conversation_customer_profile_dialog_history as ctrl_render_conversation_customer_profile_dialog_history,
    )
    from controllers.intent_dialog_history import (
        render_conversation_intent_dialog_history as ctrl_render_conversation_intent_dialog_history,
    )
    from controllers.live_bubble_phases import (
        append_live_conversation_customer_profile_content_chunk as ctrl_append_live_conversation_customer_profile_content_chunk_phase,
        append_live_conversation_customer_profile_thinking_chunk as ctrl_append_live_conversation_customer_profile_thinking_chunk_phase,
        append_live_conversation_intent_content_chunk as ctrl_append_live_conversation_intent_content_chunk_phase,
        append_live_conversation_intent_thinking_chunk as ctrl_append_live_conversation_intent_thinking_chunk_phase,
        prepare_live_conversation_intent_response_bubble as ctrl_prepare_live_conversation_intent_response_bubble_phase,
        prepare_live_conversation_customer_profile_response_bubble as ctrl_prepare_live_conversation_customer_profile_response_bubble_phase,
    )
    from controllers.editor_dialog import (
        build_dialog_llm_prompt as ctrl_build_dialog_llm_prompt,
        close_settings_editor_dialog as ctrl_close_settings_editor_dialog,
        on_editor_dialog_submit_done as ctrl_on_editor_dialog_submit_done,
        open_settings_editor_dialog as ctrl_open_settings_editor_dialog,
        poll_editor_dialog_events as ctrl_poll_editor_dialog_events,
        submit_editor_dialog as ctrl_submit_editor_dialog,
        submit_editor_dialog_worker as ctrl_submit_editor_dialog_worker,
    )
    from controllers.strategy_generator import (
        append_conversation_strategy_history as ctrl_append_conversation_strategy_history,
        append_live_conversation_strategy_content_chunk as ctrl_append_live_conversation_strategy_content_chunk,
        append_live_conversation_strategy_thinking_chunk as ctrl_append_live_conversation_strategy_thinking_chunk,
        build_conversation_strategy_prompt_with_history as ctrl_build_conversation_strategy_prompt_with_history,
        generate_conversation_strategy_in_dialog as ctrl_generate_conversation_strategy_in_dialog,
        get_conversation_strategy_history_for_tab as ctrl_get_conversation_strategy_history_for_tab,
        on_submit_conversation_strategy_llm_done as ctrl_on_submit_conversation_strategy_llm_done,
        open_conversation_strategy_generator_dialog as ctrl_open_conversation_strategy_generator_dialog,
        prepare_live_conversation_strategy_response_bubble as ctrl_prepare_live_conversation_strategy_response_bubble,
        render_conversation_strategy_history_panel as ctrl_render_conversation_strategy_history_panel,
        save_conversation_strategy_dialog as ctrl_save_conversation_strategy_dialog,
        submit_conversation_strategy_from_panel as ctrl_submit_conversation_strategy_from_panel,
        submit_conversation_strategy_llm_worker as ctrl_submit_conversation_strategy_llm_worker,
    )
    from controllers.runtime_events import (
        clear_views as ctrl_clear_views,
        drain_event_queues as ctrl_drain_event_queues,
        export_events as ctrl_export_events,
        handle_event as ctrl_handle_event,
        handle_settings_asr_event as ctrl_handle_settings_asr_event,
        is_high_priority_event as ctrl_is_high_priority_event,
        poll_events as ctrl_poll_events,
        pop_next_buffered_event as ctrl_pop_next_buffered_event,
    )
    from controllers.dialog_summary import (
        build_dialog_summary_llm_prompt as ctrl_build_dialog_summary_llm_prompt,
        build_dialog_summary_text as ctrl_build_dialog_summary_text,
        build_next_dialog_strategy_llm_prompt as ctrl_build_next_dialog_strategy_llm_prompt,
        build_next_dialog_strategy_text as ctrl_build_next_dialog_strategy_text,
        extract_pending_commitment_items as ctrl_extract_pending_commitment_items,
        format_commitment_confirmation_text as ctrl_format_commitment_confirmation_text,
        open_commitment_confirmation_dialog as ctrl_open_commitment_confirmation_dialog,
        open_dialog_summary_modal as ctrl_open_dialog_summary_modal,
    )
    from controllers.tab_manager import (
        apply_conversation_tab_snapshot as ctrl_apply_conversation_tab_snapshot,
        bind_conversation_tab_context as ctrl_bind_conversation_tab_context,
        build_unique_conversation_tab_title as ctrl_build_unique_conversation_tab_title,
        capture_conversation_tab_snapshot as ctrl_capture_conversation_tab_snapshot,
        create_conversation_tab_from_settings as ctrl_create_conversation_tab_from_settings,
        create_conversation_tab_internal as ctrl_create_conversation_tab_internal,
        delete_conversation_tab as ctrl_delete_conversation_tab,
        delete_selected_conversation_tab_from_settings as ctrl_delete_selected_conversation_tab_from_settings,
        get_conversation_tab_snapshot_path as ctrl_get_conversation_tab_snapshot_path,
        is_template_conversation_context_bound as ctrl_is_template_conversation_context_bound,
        load_persisted_conversation_tab_snapshots as ctrl_load_persisted_conversation_tab_snapshots,
        load_persisted_conversation_tabs as ctrl_load_persisted_conversation_tabs,
        on_main_notebook_tab_click as ctrl_on_main_notebook_tab_click,
        on_main_notebook_tab_changed as ctrl_on_main_notebook_tab_changed,
        read_conversation_tab_registry_entries as ctrl_read_conversation_tab_registry_entries,
        refresh_conversation_tab_registry_view as ctrl_refresh_conversation_tab_registry_view,
        register_conversation_tab_context as ctrl_register_conversation_tab_context,
        safe_set_profile_sash as ctrl_safe_set_profile_sash,
        save_persisted_conversation_tab_snapshots as ctrl_save_persisted_conversation_tab_snapshots,
        save_persisted_conversation_tabs as ctrl_save_persisted_conversation_tabs,
        using_conversation_tab_context as ctrl_using_conversation_tab_context,
        write_conversation_tab_meta as ctrl_write_conversation_tab_meta,
    )
    from controllers.customer_data import (
        apply_call_record_profile_and_workflow as ctrl_apply_call_record_profile_and_workflow,
        build_call_record_items as ctrl_build_call_record_items,
        build_customer_case_cache_by_name as ctrl_build_customer_case_cache_by_name,
        build_visible_customer_records as ctrl_build_visible_customer_records,
        clear_call_record_detail as ctrl_clear_call_record_detail,
        clear_customer_data_call_entry_views as ctrl_clear_customer_data_call_entry_views,
        clear_customer_data_profile_table as ctrl_clear_customer_data_profile_table,
        extract_latest_strategy_from_case_data as ctrl_extract_latest_strategy_from_case_data,
        get_selected_customer_case_data as ctrl_get_selected_customer_case_data,
        load_call_records_into_list as ctrl_load_call_records_into_list,
        load_customer_data_records_into_list as ctrl_load_customer_data_records_into_list,
        mark_conversation_tab_data_dirty as ctrl_mark_conversation_tab_data_dirty,
        on_call_record_call as ctrl_on_call_record_call,
        on_call_record_selected as ctrl_on_call_record_selected,
        on_call_record_tree_click as ctrl_on_call_record_tree_click,
        on_customer_data_record_selected as ctrl_on_customer_data_record_selected,
        on_customer_data_tree_click as ctrl_on_customer_data_tree_click,
        on_customer_data_tree_double_click as ctrl_on_customer_data_tree_double_click,
        open_call_record_detail_window as ctrl_open_call_record_detail_window,
        open_customer_data_detail_window as ctrl_open_customer_data_detail_window,
        prepare_call_context_from_customer_data_and_workflow_page as ctrl_prepare_call_context_from_customer_data_and_workflow_page,
        render_call_record_detail as ctrl_render_call_record_detail,
        render_customer_data_call_entry_views as ctrl_render_customer_data_call_entry_views,
        delete_customer_by_name as ctrl_delete_customer_by_name,
    )
    from controllers.profile_intent_dialog import (
        append_conversation_customer_profile_history as ctrl_append_conversation_customer_profile_history,
        append_conversation_intent_generator_history as ctrl_append_conversation_intent_generator_history,
        build_conversation_customer_profile_prompt_with_history as ctrl_build_conversation_customer_profile_prompt_with_history,
        build_conversation_intent_prompt_with_history as ctrl_build_conversation_intent_prompt_with_history,
        generate_conversation_customer_profile_in_dialog as ctrl_generate_conversation_customer_profile_in_dialog,
        generate_conversation_intent_in_dialog as ctrl_generate_conversation_intent_in_dialog,
        get_conversation_customer_profile_history_for_tab as ctrl_get_conversation_customer_profile_history_for_tab,
        get_conversation_intent_generator_history_for_tab as ctrl_get_conversation_intent_generator_history_for_tab,
        on_submit_conversation_customer_profile_llm_done as ctrl_on_submit_conversation_customer_profile_llm_done,
        on_submit_conversation_intent_llm_done as ctrl_on_submit_conversation_intent_llm_done,
        open_conversation_customer_profile_generator_dialog as ctrl_open_conversation_customer_profile_generator_dialog,
        open_conversation_intent_generator_dialog as ctrl_open_conversation_intent_generator_dialog,
        render_conversation_customer_profile_dialog_history as ctrl_render_conversation_customer_profile_dialog_history,
        save_conversation_customer_profile_dialog as ctrl_save_conversation_customer_profile_dialog,
        save_conversation_intent_dialog as ctrl_save_conversation_intent_dialog,
        submit_conversation_customer_profile_llm_worker as ctrl_submit_conversation_customer_profile_llm_worker,
        submit_conversation_intent_llm_worker as ctrl_submit_conversation_intent_llm_worker,
    )
    from controllers.panel_llm import (
        append_ai_analysis_text as ctrl_append_ai_analysis_text,
        append_asr_submit_thinking_chunk as ctrl_append_asr_submit_thinking_chunk,
        append_dialog_output_chunk as ctrl_append_dialog_output_chunk,
        append_intent_system_text as ctrl_append_intent_system_text,
        append_llm_prompt_block_to_system_instruction as ctrl_append_llm_prompt_block_to_system_instruction,
        append_system_instruction_text as ctrl_append_system_instruction_text,
        append_text_to_widget as ctrl_append_text_to_widget,
        build_intent_generation_prompt as ctrl_build_intent_generation_prompt,
        build_system_instruction_prompt_for_submit as ctrl_build_system_instruction_prompt_for_submit,
        generate_intents_from_settings as ctrl_generate_intents_from_settings,
        generate_intents_from_settings_worker as ctrl_generate_intents_from_settings_worker,
        log_llm_prompts as ctrl_log_llm_prompts,
        on_customer_profile_submit_from_asr_done as ctrl_on_customer_profile_submit_from_asr_done,
        on_generate_intents_from_settings_done as ctrl_on_generate_intents_from_settings_done,
        on_submit_settings_panel_llm_done as ctrl_on_submit_settings_panel_llm_done,
        set_llm_generation_frozen as ctrl_set_llm_generation_frozen,
        strip_panel_llm_debug_blocks as ctrl_strip_panel_llm_debug_blocks,
        submit_settings_panel_llm as ctrl_submit_settings_panel_llm,
        submit_settings_panel_llm_worker as ctrl_submit_settings_panel_llm_worker,
        trigger_customer_profile_submit_from_asr as ctrl_trigger_customer_profile_submit_from_asr,
        trigger_customer_profile_submit_from_asr_worker as ctrl_trigger_customer_profile_submit_from_asr_worker,
    )
    from controllers.settings_asr import (
        begin_asr_wait as ctrl_begin_asr_wait,
        check_asr_wait_timeout as ctrl_check_asr_wait_timeout,
        close_settings_asr_stream_line as ctrl_close_settings_asr_stream_line,
        get_asr_prefix as ctrl_get_asr_prefix,
        is_microphone_open as ctrl_is_microphone_open,
        log_asr_monitor as ctrl_log_asr_monitor,
        mark_asr_commit_seen as ctrl_mark_asr_commit_seen,
        replace_settings_asr_stream_text as ctrl_replace_settings_asr_stream_text,
        replace_settings_asr_stream_with_commit as ctrl_replace_settings_asr_stream_with_commit,
        reset_asr_wait as ctrl_reset_asr_wait,
        set_microphone_open as ctrl_set_microphone_open,
        start_settings_asr as ctrl_start_settings_asr,
        start_settings_asr_stream_line as ctrl_start_settings_asr_stream_line,
        update_microphone_state_from_log as ctrl_update_microphone_state_from_log,
    )
    from controllers.profile_table import (
        fill_profile_table_from_text as ctrl_fill_profile_table_from_text,
        refresh_dialog_profile_table as ctrl_refresh_dialog_profile_table,
        resize_customer_data_profile_columns as ctrl_resize_customer_data_profile_columns,
        resize_dialog_profile_columns as ctrl_resize_dialog_profile_columns,
        resize_profile_table_columns as ctrl_resize_profile_table_columns,
    )
    from controllers.system_prompt import (
        build_runtime_system_prompt as ctrl_build_runtime_system_prompt,
    )
    from controllers.data_records import (
        build_new_tab_data_dir as ctrl_build_new_tab_data_dir,
        copy_tab_case_files as ctrl_copy_tab_case_files,
        create_new_customer_record_from_jsonl as ctrl_create_new_customer_record_from_jsonl,
        get_data_dir as ctrl_get_data_dir,
        save_dialog_summary_record as ctrl_save_dialog_summary_record,
        save_new_customer_record as ctrl_save_new_customer_record,
    )
    from controllers.workflow_sync import (
        on_conversation_workflow_text_edited as ctrl_on_conversation_workflow_text_edited,
        refresh_runtime_system_prompt_only as ctrl_refresh_runtime_system_prompt_only,
        refresh_system_instruction as ctrl_refresh_system_instruction,
        _set_workflow_doc_dirty as ctrl_set_workflow_doc_dirty,
    )
    from controllers.stream_runtime import (
        append_dialog_agent_stream_text as ctrl_append_dialog_agent_stream_text,
        append_dialog_conversation_line as ctrl_append_dialog_conversation_line,
        append_dialog_customer_intent as ctrl_append_dialog_customer_intent,
        append_dialog_session_marker as ctrl_append_dialog_session_marker,
        append_dialog_session_separator as ctrl_append_dialog_session_separator,
        append_line as ctrl_append_line,
        append_line_with_tag as ctrl_append_line_with_tag,
        append_tts_line as ctrl_append_tts_line,
        append_tts_stream_text as ctrl_append_tts_stream_text,
        clear_text as ctrl_clear_text,
        close_asr_stream_line as ctrl_close_asr_stream_line,
        close_dialog_agent_stream_line as ctrl_close_dialog_agent_stream_line,
        close_tts_stream_line as ctrl_close_tts_stream_line,
        extract_dialog_current_session_text as ctrl_extract_dialog_current_session_text,
        parse_intent_window as ctrl_parse_intent_window,
        replace_asr_stream_text as ctrl_replace_asr_stream_text,
        replace_dialog_agent_stream_text as ctrl_replace_dialog_agent_stream_text,
        refresh_dialog_conversation_for_active_customer as ctrl_refresh_dialog_conversation_for_active_customer,
        render_dialog_conversation_history as ctrl_render_dialog_conversation_history,
        replace_tts_stream_text as ctrl_replace_tts_stream_text,
        reset_runtime_status as ctrl_reset_runtime_status,
        sanitize_inline_text as ctrl_sanitize_inline_text,
        set_dialog_conversation_active_customer as ctrl_set_dialog_conversation_active_customer,
        set_text_content as ctrl_set_text_content,
        sync_conversation_profile_status as ctrl_sync_conversation_profile_status,
        start_asr_stream_line as ctrl_start_asr_stream_line,
        start_dialog_agent_stream_line as ctrl_start_dialog_agent_stream_line,
        start_tts_stream_line as ctrl_start_tts_stream_line,
        trim_scrolled_text as ctrl_trim_scrolled_text,
    )
    from controllers.layout_builder import build_layout as ctrl_build_layout
    from controllers.conversation_tab_builder import build_conversation_tab as ctrl_build_conversation_tab
    from controllers.call_timer_overlay import CallTimerOverlay as ctrl_CallTimerOverlay

try:
    from .services.case_store import (
        build_profile_text_from_slot_items as svc_build_profile_text_from_slot_items,
        extract_customer_name_from_profile_text as svc_extract_customer_name_from_profile_text,
        parse_datetime_to_epoch as svc_parse_datetime_to_epoch,
        parse_profile_kv_rows as svc_parse_profile_kv_rows,
        pick_random_customer_profile_from_jsonl_path as svc_pick_random_customer_profile_from_jsonl_path,
        read_customer_case_file as svc_read_customer_case_file,
        resolve_customer_jsonl_path as svc_resolve_customer_jsonl_path,
        sanitize_filename_component as svc_sanitize_filename_component,
        save_customer_case_file as svc_save_customer_case_file,
    )
    from .services.llm_service import (
        call_ark_chat_completion as svc_call_ark_chat_completion,
        call_deepseek_chat_completion as svc_call_deepseek_chat_completion,
        call_deepseek_chat_fast as svc_call_deepseek_chat_fast,
        extract_llm_text as svc_extract_llm_text,
    )
    from .controllers.intent_hexagon import (
        refresh_intent_queue_view as ctrl_refresh_intent_queue_view,
        sync_intent_strategy_for_active_customer as ctrl_sync_intent_strategy_for_active_customer,
    )
    from .services.tab_registry import (
        get_conversation_tab_registry_path as svc_get_conversation_tab_registry_path,
    )
    from .services.command_utils import (
        check_strict_webrtc_readiness as svc_check_strict_webrtc_readiness,
        ensure_mic_capture_command as svc_ensure_mic_capture_command,
        ensure_unbuffered_python_command as svc_ensure_unbuffered_python_command,
        safe_join_tokens as svc_safe_join_tokens,
        safe_split_command as svc_safe_split_command,
    )
except Exception:
    from services.case_store import (
        build_profile_text_from_slot_items as svc_build_profile_text_from_slot_items,
        extract_customer_name_from_profile_text as svc_extract_customer_name_from_profile_text,
        parse_datetime_to_epoch as svc_parse_datetime_to_epoch,
        parse_profile_kv_rows as svc_parse_profile_kv_rows,
        pick_random_customer_profile_from_jsonl_path as svc_pick_random_customer_profile_from_jsonl_path,
        read_customer_case_file as svc_read_customer_case_file,
        resolve_customer_jsonl_path as svc_resolve_customer_jsonl_path,
        sanitize_filename_component as svc_sanitize_filename_component,
        save_customer_case_file as svc_save_customer_case_file,
    )
    from services.llm_service import (
        call_ark_chat_completion as svc_call_ark_chat_completion,
        call_deepseek_chat_completion as svc_call_deepseek_chat_completion,
        call_deepseek_chat_fast as svc_call_deepseek_chat_fast,
        extract_llm_text as svc_extract_llm_text,
    )
    from controllers.intent_hexagon import (
        refresh_intent_queue_view as ctrl_refresh_intent_queue_view,
        sync_intent_strategy_for_active_customer as ctrl_sync_intent_strategy_for_active_customer,
    )
    from services.tab_registry import (
        get_conversation_tab_registry_path as svc_get_conversation_tab_registry_path,
    )
    from services.command_utils import (
        check_strict_webrtc_readiness as svc_check_strict_webrtc_readiness,
        ensure_mic_capture_command as svc_ensure_mic_capture_command,
        ensure_unbuffered_python_command as svc_ensure_unbuffered_python_command,
        safe_join_tokens as svc_safe_join_tokens,
        safe_split_command as svc_safe_split_command,
    )

UI_POLL_MAX_EVENTS_PER_TICK = 180
UI_POLL_MAX_MS_PER_TICK = 10.0
UI_POLL_DRAIN_LIMIT_PER_TICK = 720
UI_POLL_BUSY_INTERVAL_MS = 1
UI_POLL_IDLE_INTERVAL_MS = 80
UI_LOG_FLUSH_INTERVAL_SECONDS = 0.10
UI_EVENT_HISTORY_MAX = 5000
UI_EVENT_HISTORY_TRIM_BATCH = 500
UI_SEND_DONE_SUMMARY_INTERVAL_SECONDS = 1.0
TIME_LOG_MAX_LINES = 2000
UI_HIGH_PRIORITY_EVENT_KINDS = frozenset(
    {
        "tts_start",
        "tts_segment",
        "assistant_text",
        "tts_interrupted",
        "tts_end",
        "billing_result",
        "asr_commit",
        "latency_asr",
        "latency_e2e",
        "latency_backend",
        "session_ready",
        "process_stopped",
        "process_exit",
    }
)
RE_SEND_DONE_LOG = re.compile(r"^\[send\]\s+chunk=(?P<chunk>\d+)\s+done\s+in\s+(?P<ms>\d+)ms$")
UI_FONT_FAMILY = "微软雅黑"
UI_FONT_SIZE = 9
FIXED_STARTUP_COMMAND = "python mic_chunk_client.py"
WHOAMI_LOCAL_BASE_URL = "http://127.0.0.1:8080"
WHOAMI_PUBLIC_BASE_URL = "https://sd66afouoqou1cki04eng.apigateway-cn-beijing.volceapi.com/"

def _enable_windows_dpi_awareness() -> None:
    # Prevent blurry bitmap scaling on high-DPI displays.
    if not hasattr(ctypes, "windll"):
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class MicChunkUiApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Mic Chunk Client UI v1")
        self.geometry("1280x820")
        self.minsize(1080, 700)
        self._apply_global_font()
        self.after_idle(self._maximize_window_on_start)

        self._event_queue: queue.Queue[UiEvent] = queue.Queue()
        self._bridge = ClientProcessBridge(on_event=self._event_queue.put)
        self._settings_asr_queue: queue.Queue[UiEvent] = queue.Queue()
        self._settings_asr_bridge = ClientProcessBridge(on_event=self._settings_asr_queue.put)
        ctrl_init_session_state_fields(self)

        ctrl_init_runtime_fields(
            self,
            runtime_audio_config_filename=RUNTIME_AUDIO_CONFIG_FILENAME,
            fixed_startup_command=FIXED_STARTUP_COMMAND,
        )
        self._audio_tuning_specs = AUDIO_TUNING_SPECS
        self._asr_first_profile_overrides = ASR_FIRST_PROFILE_OVERRIDES
        self._aggressive_profile_overrides = AGGRESSIVE_PROFILE_OVERRIDES
        self._fixed_startup_command = self._default_command
        self._whoami_local_base_url = WHOAMI_LOCAL_BASE_URL
        self._whoami_public_base_url = WHOAMI_PUBLIC_BASE_URL
        self._async_log_queue: queue.Queue[tuple[Path, str] | None] = queue.Queue()
        self._async_log_writer_stop = threading.Event()
        self._async_log_writer_thread = threading.Thread(
            target=self._async_log_writer_loop,
            name="ui-log-writer",
            daemon=True,
        )
        self._runtime_log_file_path: Path | None = None
        self._time_log_file_path = self._runtime_log_dir / f"time_log_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log"
        self._time_log_read_offset = 0
        self._async_log_writer_thread.start()
        self._write_time_log_line(f"# time_log_started_at={datetime.now().isoformat(timespec='seconds')}")

        self._call_timer_overlay = ctrl_CallTimerOverlay(self)

        self._build_variables()
        self._build_layout()
        self._refresh_system_instruction()
        self._schedule_snapshot_autosave()
        self._poll_events()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _maximize_window_on_start(self) -> None:
        try:
            self.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            self.wm_state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            self.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass
        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        self.geometry(f"{width}x{height}+0+0")

    def _apply_global_font(self) -> None:
        family = UI_FONT_FAMILY
        size = UI_FONT_SIZE
        for font_name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
            "TkIconFont",
            "TkTooltipFont",
            "TkFixedFont",
        ):
            try:
                tkfont.nametofont(font_name).configure(family=family, size=size)
            except tk.TclError:
                pass
        self.option_add("*Font", (family, size))
        ttk.Style(self).configure(".", font=(family, size))

    @property
    def active_tab(self) -> "ConversationTabContext | None":
        """返回当前激活 Tab 的 ConversationTabContext，供业务逻辑直接访问控件，
        无需通过 app.dialog_conversation_text 等共享别名。"""
        return self._conversation_tabs.get(self._active_conversation_tab_id)

    def _build_variables(self) -> None:
        initial_env = str(os.getenv("MIC_CHUNK_SERVER_ENV", "local") or "").strip().lower()
        if initial_env not in {"local", "public"}:
            initial_env = "local"
        profile = ctrl_normalize_aec_profile(os.getenv("MIC_CHUNK_AEC_PROFILE", "asr_first"))
        self.command_var = tk.StringVar(value=self._default_command)
        self.server_env_var = tk.StringVar(value=initial_env)
        self.conversation_command_var = tk.StringVar(value=self._default_command)
        self.conversation_server_env_var = tk.StringVar(value=initial_env)
        self.settings_asr_command_var = tk.StringVar(value=self._settings_asr_command or self._default_command)
        self.strict_webrtc_required_var = tk.BooleanVar(value=True)
        self.aec_profile_var = tk.StringVar(value=profile)
        self.audio_config_status_var = tk.StringVar(value="未加载参数配置")
        self.state_var = tk.StringVar(value="stopped")
        self.session_id_var = tk.StringVar(value="-")
        self.transport_var = tk.StringVar(value="-")
        self.channel_var = tk.StringVar(value="-")
        self.send_stat_var = tk.StringVar(value="0 chunks / avg 0ms")
        self.endpoint_var = tk.StringVar(value="-")
        self.asr_enabled_var = tk.BooleanVar(value=False)
        self.asr_toggle_text_var = tk.StringVar(value="开启ASR识别")
        self.asr_prefix_enabled_var = tk.BooleanVar(value=True)
        self.intent_generate_count_var = tk.StringVar(value="10")
        self.intent_generate_text_var = tk.StringVar(value="生成意图")
        self.flow_path_var = tk.StringVar(value="未加载")
        self.flow_summary_var = tk.StringVar(value="未加载流程文件")
        self.flow_show_script_var = tk.BooleanVar(value=False)
        self.call_record_selected_var = tk.StringVar(value="已选记录：-")
        self.create_conversation_tab_name_var = tk.StringVar(value="")
        for spec in AUDIO_TUNING_SPECS:
            key = str(spec["key"])
            default_text = str(spec["default"])
            setattr(self, f"audio_{key}_var", tk.StringVar(value=default_text))
        self._audio_config_loaded = self._load_runtime_audio_config()
        if not self._audio_config_loaded:
            self._reset_audio_config_defaults_for_profile(apply_profile_overrides=True, update_status=False)
            self._load_audio_config_from_current_command(update_status=False)
        if not self._apply_audio_config_to_commands(save_config=False, update_status=False, show_error=False):
            self._reset_audio_config_defaults_for_profile(apply_profile_overrides=True, update_status=False)
            self._apply_audio_config_to_commands(save_config=False, update_status=False, show_error=False)

    def _build_layout(self) -> None:
        ctrl_build_layout(
            self,
            FlowCanvas=FlowCanvas,
            FlowEditorPanel=FlowEditorPanel,
            UI_FONT_FAMILY=UI_FONT_FAMILY,
            UI_FONT_SIZE=UI_FONT_SIZE,
        )

    def _set_audio_config_status(self, text: str) -> None:
        ctrl_set_audio_config_status(self, text)

    def _load_audio_config_from_command_text(self, command_text: str, update_status: bool = True) -> None:
        ctrl_load_audio_config_from_command_text(self, command_text, update_status=update_status)

    def _load_audio_config_from_current_command(self, update_status: bool = True) -> None:
        ctrl_load_audio_config_from_current_command(self, update_status=update_status)

    def _reset_audio_config_defaults_for_profile(self, apply_profile_overrides: bool = True, update_status: bool = True) -> None:
        ctrl_reset_audio_config_defaults_for_profile(
            self,
            apply_profile_overrides=apply_profile_overrides,
            update_status=update_status,
        )

    def _reset_audio_config_defaults(self) -> None:
        ctrl_reset_audio_config_defaults(self)

    def _collect_validated_audio_tuning_values(self, *, show_error: bool) -> dict[str, str] | None:
        return ctrl_collect_validated_audio_tuning_values(self, show_error=show_error)

    def _apply_audio_tuning_values_to_command(self, command_text: str, values: dict[str, str]) -> str:
        return ctrl_apply_audio_tuning_values_to_command(self, command_text, values)

    def _build_runtime_audio_config_payload(self, values: dict[str, str]) -> dict[str, object]:
        return ctrl_build_runtime_audio_config_payload(self, values)

    def _save_runtime_audio_config(self, values: dict[str, str] | None = None, *, silent: bool = False) -> bool:
        return ctrl_save_runtime_audio_config(self, values, silent=silent)

    def _load_runtime_audio_config(self) -> bool:
        return ctrl_load_runtime_audio_config(self)

    def _apply_audio_config_to_commands(
        self,
        *,
        save_config: bool = True,
        update_status: bool = True,
        show_error: bool = True,
    ) -> bool:
        return ctrl_apply_audio_config_to_commands(
            self,
            save_config=save_config,
            update_status=update_status,
            show_error=show_error,
        )

    def _save_audio_config_from_ui(self) -> None:
        ctrl_save_audio_config_from_ui(self)

    def _build_conversation_tab(
        self,
        parent: ttk.Frame,
        panel_bg: str,
        tab_title: str,
        command_value: str,
        env_value: str,
        *,
        tab_id_override: str = "",
    ) -> ConversationTabContext:
        return ctrl_build_conversation_tab(
            self,
            parent,
            panel_bg,
            tab_title,
            command_value,
            env_value,
            tab_id_override=tab_id_override,
            UI_FONT_FAMILY=UI_FONT_FAMILY,
            UI_FONT_SIZE=UI_FONT_SIZE,
            conversation_tab_context_cls=ConversationTabContext,
        )

    def _register_conversation_tab_context(self, context: ConversationTabContext, is_template: bool = False) -> None:
        ctrl_register_conversation_tab_context(self, context, is_template=is_template)

    def _safe_set_profile_sash(self, panes: ttk.Panedwindow, min_top: int = 160, min_bottom: int = 170, force_initial: bool = False) -> None:
        ctrl_safe_set_profile_sash(self, panes, min_top=min_top, min_bottom=min_bottom, force_initial=force_initial)

    def _bind_conversation_tab_context(self, tab_id: str) -> bool:
        return ctrl_bind_conversation_tab_context(self, tab_id)

    @contextmanager
    def _using_conversation_tab_context(self, tab_id: str) -> Iterator[None]:
        with ctrl_using_conversation_tab_context(self, tab_id):
            yield

    def _on_main_notebook_tab_changed(self, _event=None) -> None:
        ctrl_on_main_notebook_tab_changed(self, _event=_event)

    def _on_main_notebook_tab_click(self, event=None) -> str | None:
        return ctrl_on_main_notebook_tab_click(self, event=event)

    def _build_unique_conversation_tab_title(self, base_title: str) -> str:
        return ctrl_build_unique_conversation_tab_title(self, base_title)

    def _capture_conversation_tab_snapshot(self, tab_id: str) -> dict[str, str]:
        return ctrl_capture_conversation_tab_snapshot(self, tab_id)

    def _apply_conversation_tab_snapshot(self, tab_id: str, snapshot: dict[str, str]) -> None:
        ctrl_apply_conversation_tab_snapshot(self, tab_id, snapshot)

    def _create_conversation_tab_internal(
        self,
        tab_title: str,
        source_tab_id: str = "",
        *,
        data_dir: Path | None = None,
        copy_source_data: bool = True,
        select_new_tab: bool = True,
        persist: bool = True,
        reset_workflow_fields: bool = True,
    ) -> str | None:
        return ctrl_create_conversation_tab_internal(
            self,
            tab_title,
            source_tab_id,
            data_dir=data_dir,
            copy_source_data=copy_source_data,
            select_new_tab=select_new_tab,
            persist=persist,
            reset_workflow_fields=reset_workflow_fields,
        )

    def _create_conversation_tab_from_settings(self) -> None:
        ctrl_create_conversation_tab_from_settings(self)

    def _resolve_whoami_base_url(self) -> str:
        return ctrl_resolve_whoami_base_url(self)

    def _request_whoami_from_settings(self) -> None:
        ctrl_request_whoami_from_settings(self)

    @staticmethod
    def _probe_public_ip(*, use_env_proxy: bool) -> tuple[str, str]:
        return ctrl_probe_public_ip(use_env_proxy=use_env_proxy)

    def _request_network_probe_from_settings(self) -> None:
        ctrl_request_network_probe_from_settings(self)

    def _delete_selected_conversation_tab_from_settings(self) -> None:
        ctrl_delete_selected_conversation_tab_from_settings(self)

    def _delete_conversation_tab(self, tab_id: str) -> None:
        ctrl_delete_conversation_tab(self, tab_id)

    def _refresh_conversation_tab_registry_view(self) -> None:
        ctrl_refresh_conversation_tab_registry_view(self)

    def _get_conversation_tab_registry_path(self) -> Path:
        return svc_get_conversation_tab_registry_path(self._workspace_dir)

    def _save_persisted_conversation_tabs(self) -> None:
        ctrl_save_persisted_conversation_tabs(self)

    def _read_conversation_tab_registry_entries(self, path: Path) -> list[dict[str, str]]:
        return ctrl_read_conversation_tab_registry_entries(self, path)

    def _load_persisted_conversation_tabs(self) -> None:
        ctrl_load_persisted_conversation_tabs(self)

    def _get_conversation_tab_snapshot_path(self, tab_id: str) -> Path | None:
        return ctrl_get_conversation_tab_snapshot_path(self, tab_id)

    def _save_persisted_conversation_tab_snapshots(self, persist_workflow_fields: bool = False) -> None:
        ctrl_save_persisted_conversation_tab_snapshots(self, persist_workflow_fields=persist_workflow_fields)

    def _load_persisted_conversation_tab_snapshots(self) -> None:
        ctrl_load_persisted_conversation_tab_snapshots(self)

    def _write_conversation_tab_meta(self, data_dir: Path, title: str) -> None:
        ctrl_write_conversation_tab_meta(self, data_dir, title)

    def _is_template_conversation_context_bound(self) -> bool:
        return ctrl_is_template_conversation_context_bound(self)

    def _start(
        self,
        *,
        command_override: str | None = None,
        profile_text: str | None = None,
        workflow_text: str | None = None,
        system_text: str | None = None,
        intent_text: str | None = None,
    ) -> None:
        if command_override is None:
            self._apply_server_env_to_command()
        if not self._runtime_conversation_tab_id:
            self._runtime_conversation_tab_id = self._active_conversation_tab_id or self._conversation_template_tab_id
        command = (command_override if command_override is not None else self.command_var.get()).strip()
        if not command:
            messagebox.showwarning("Invalid command", "Command cannot be empty.")
            return
        skip_auto_start_dialog = bool(self._skip_auto_start_dialog_once)
        self._skip_auto_start_dialog_once = False
        if skip_auto_start_dialog:
            tokens = self._safe_split(command)
            if "--skip-auto-start-dialog" not in tokens:
                tokens.append("--skip-auto-start-dialog")
                command = self._safe_join(tokens)
        command = self._ensure_unbuffered_python_command(command)
        command = self._ensure_mic_capture_command(command)
        self.command_var.set(command)
        if command_override is not None:
            self.conversation_command_var.set(command)
        strict_ok, strict_message = self._check_strict_webrtc_readiness(command)
        if not strict_ok:
            ts_text = datetime.now().strftime("%H:%M:%S")
            self._append_line(
                self.log_text,
                f"[{ts_text}] [STRICT_WEBRTC] preflight_failed {self._sanitize_inline_text(strict_message)}",
            )
            messagebox.showerror("Strict WebRTC check failed", strict_message)
            return

        if self._is_microphone_open():
            self._log_asr_monitor("start_check mic=open -> close_then_reopen")
            if self._settings_asr_bridge.running:
                self._stop_settings_asr()
                if self.asr_enabled_var.get():
                    self.asr_enabled_var.set(False)
                    self.asr_toggle_text_var.set("开启ASR识别")
                    self._log_asr_monitor("start_check forced settings ASR switch_off")
                    self._reset_asr_wait()
                    self._refresh_system_instruction()
            if self._bridge.running:
                self._stop()
        elif self._bridge.running:
            # Process is running but mic state is not detected as open; restart to keep behavior deterministic.
            self._log_asr_monitor("start_check process_running -> restart")
            self._stop()

        self._open_runtime_log_file()
        self._reset_runtime_status()
        self._set_cmd_derived_status(command)
        if profile_text is None:
            profile_text = self._build_profile_text_from_dialog_profile_table()
        if workflow_text is None:
            workflow_text = (
                self.conversation_workflow_text.get("1.0", "end-1c")
                if isinstance(self.conversation_workflow_text, ScrolledText)
                else (self.workflow_text.get("1.0", "end-1c") if isinstance(self.workflow_text, ScrolledText) else "")
            )
        if system_text is None:
            system_text = (
                self.conversation_system_instruction_text.get("1.0", "end-1c")
                if isinstance(self.conversation_system_instruction_text, ScrolledText)
                else (
                    self.system_instruction_text.get("1.0", "end-1c")
                    if isinstance(self.system_instruction_text, ScrolledText)
                    else ""
                )
            )
        if intent_text is None:
            intent_text = (
                self.conversation_intent_text.get("1.0", "end-1c")
                if isinstance(self.conversation_intent_text, ScrolledText)
                else (self.intent_text.get("1.0", "end-1c") if isinstance(self.intent_text, ScrolledText) else "")
            )
        profile_text = str(profile_text or "").strip()
        workflow_text = str(workflow_text or "").strip()
        system_text = str(system_text or "").strip()
        intent_raw_text = str(intent_text or "").strip()
        self._runtime_system_prompt = self._build_runtime_system_prompt_from_values(
            system_text=system_text,
            profile_text=profile_text,
            workflow_text=workflow_text,
        )
        intent_labels, intent_fallback_label = self._parse_intent_window(intent_raw_text)
        intent_label_text = "\n".join(intent_labels)
        workflow_json_text = (self._loaded_workflow_json_text or "").strip()
        env_overrides = {
            "CUSTOMER_PROFILE": profile_text,
            "WORKFLOW_TEXT": workflow_text,
            "WORKFLOW_JSON": workflow_json_text,
            "SYSTEM_INSTRUCTION_TEXT": system_text,
            "INTENT_LABELS": intent_label_text,
            "INTENT_FALLBACK_LABEL": intent_fallback_label,
        }
        ts_text = datetime.now().strftime("%H:%M:%S")
        self._append_line(
            self.log_text,
            (
                f"[{ts_text}] [PROMPT_SYNC] system_chars={len(self._runtime_system_prompt)} "
                f"profile_chars={len(profile_text)} workflow_chars={len(workflow_text)} "
                f"workflow_json={'on' if workflow_json_text else 'off'} "
                f"intent_labels={len(intent_labels)} fallback_label={intent_fallback_label or '-'}"
            ),
        )
        if workflow_json_text:
            self._append_line(
                self.log_text,
                (
                    f"[{ts_text}] [FLOW_UPLOAD] enabled path={self._loaded_workflow_json_path or '-'} "
                    f"nodes={self._loaded_workflow_json_nodes} edges={self._loaded_workflow_json_edges}"
                ),
            )
        else:
            self._append_line(self.log_text, f"[{ts_text}] [FLOW_UPLOAD] disabled")
        if intent_raw_text and (not intent_labels) and (not intent_fallback_label):
            self._append_line(
                self.log_text,
                f"[{ts_text}] [PROMPT_SYNC] intent_labels=0 (Intent窗口未解析到有效标签)",
            )
        payload_json = json.dumps(env_overrides, ensure_ascii=False, indent=2)
        print(
            "[START_ENV_OVERRIDES_BEGIN]\n"
            f"{payload_json}\n"
            "[START_ENV_OVERRIDES_END]",
            flush=True,
        )
        self._append_line(self.log_text, f"[{ts_text}] [START_ENV_OVERRIDES] BEGIN")
        for raw_line in payload_json.splitlines():
            self._append_line(self.log_text, f"[{ts_text}] [START_ENV_OVERRIDES] {raw_line}")
        self._append_line(self.log_text, f"[{ts_text}] [START_ENV_OVERRIDES] END")
        try:
            self._bridge.start(command=command, cwd=str(self._workspace_dir), env_overrides=env_overrides)
        except Exception as exc:
            messagebox.showerror("Start failed", str(exc))

    def _start_from_conversation_profile(self, prefer_customer_data_context: bool = False) -> None:
        self._runtime_conversation_tab_id = self._active_conversation_tab_id or self._conversation_template_tab_id
        if not self._apply_audio_config_to_commands(save_config=False, update_status=False, show_error=True):
            return

        prepared = False
        if prefer_customer_data_context:
            prepared = self._prepare_call_context_from_customer_data_and_workflow_page()
        if prefer_customer_data_context and (not prepared):
            return

        self._apply_server_env_to_conversation_command()
        command = (self.conversation_command_var.get() or "").strip()
        if not command:
            command = (self._default_command or "").strip()
            if command:
                self.conversation_command_var.set(command)
                self._apply_server_env_to_conversation_command()
                command = (self.conversation_command_var.get() or "").strip()
        if not command:
            messagebox.showwarning("Invalid command", "Command cannot be empty.")
            return

        conversation_env = (self.conversation_server_env_var.get() or "local").strip().lower()
        if conversation_env not in {"local", "public"}:
            conversation_env = "local"
            self.conversation_server_env_var.set(conversation_env)
        self.server_env_var.set(conversation_env)
        self.command_var.set(command)
        self._apply_server_env_to_command()
        self.conversation_command_var.set(self.command_var.get())
        self._sync_conversation_server_env_from_command(self.conversation_command_var.get().strip())
        # profile_text：仅从实时对话画像表格提取，不再 fallback 到工作流程页
        profile_text = self._build_profile_text_from_dialog_profile_table()

        # workflow_text：从客户资料页当前选中客户的最新通话记录中提取对话策略
        case_data = self._get_selected_customer_case_data(ensure_default_selection=True)
        if not isinstance(case_data, dict):
            messagebox.showwarning("无客户数据", "请先在客户资料页选择一个客户。")
            return
        workflow_text = self._extract_latest_strategy_from_case_data(case_data)
        if not workflow_text:
            messagebox.showwarning("对话策略为空", "当前客户没有可用的对话策略，请先完成一次对话总结或在新建客户时填写初始策略模板。")
            return

        system_text = (
            self.conversation_system_instruction_text.get("1.0", "end-1c")
            if isinstance(self.conversation_system_instruction_text, ScrolledText)
            else ""
        )
        intent_text = (
            self.conversation_intent_text.get("1.0", "end-1c")
            if isinstance(self.conversation_intent_text, ScrolledText)
            else ""
        )
        self._start(
            command_override=command,
            profile_text=profile_text,
            workflow_text=workflow_text,
            system_text=system_text,
            intent_text=intent_text,
        )

    def _start_from_customer_data_call_icon(self) -> None:
        is_running = bool(self._bridge.running) or (
            str(self.state_var.get() if hasattr(self, "state_var") else "").strip().lower() == "running"
        )
        if is_running:
            messagebox.showwarning("当前通话未结束", "当前通话未结束，请挂断后再拨。")
            return
        self._skip_auto_start_dialog_once = True
        self._open_customer_call_overlay()
        self._call_overlay_reconnect_pending = False
        self._call_overlay_restart_in_progress = False
        self._call_overlay_restart_scheduled = False
        self._start_from_conversation_profile(prefer_customer_data_context=True)
        if self._skip_auto_start_dialog_once and (not self._bridge.running):
            self._skip_auto_start_dialog_once = False
        if not self._bridge.running:
            self._close_customer_call_overlay()

    def _resume_customer_data_call_icon_after_stop(self) -> None:
        self._call_overlay_reconnect_pending = False
        self._call_overlay_restart_scheduled = False
        self._skip_auto_start_dialog_once = True
        self._open_customer_call_overlay()
        self._start_from_conversation_profile(prefer_customer_data_context=True)
        if self._skip_auto_start_dialog_once and (not self._bridge.running):
            self._skip_auto_start_dialog_once = False
        if not self._bridge.running:
            self._call_overlay_restart_in_progress = False
            self._close_customer_call_overlay()

    def _build_profile_text_from_dialog_profile_table(self) -> str:
        tree = self.dialog_profile_table
        if not isinstance(tree, ttk.Treeview):
            return ""
        lines = ["【客户画像】"]
        has_rows = False
        for iid in tree.get_children():
            values = list(tree.item(iid, "values") or [])
            if len(values) < 6:
                values.extend([""] * (6 - len(values)))
            for key_idx, value_idx in ((0, 1), (2, 3), (4, 5)):
                key = str(values[key_idx] or "").strip()
                value = str(values[value_idx] or "").strip()
                if (not key) or (key == "暂无客户画像数据"):
                    continue
                has_rows = True
                if value and (not value.endswith((",", ":", "：", "，"))):
                    value = f"{value},"
                lines.append(f"{key}: {value}" if value else f"{key}:")
        return "\n".join(lines) if has_rows else ""

    def _build_runtime_system_prompt_from_values(
        self,
        *,
        system_text: str,
        profile_text: str,
        workflow_text: str,
    ) -> str:
        clean_system = self._strip_llm_asr_debug_blocks(system_text or "").strip()
        clean_profile = self._strip_panel_llm_debug_blocks(profile_text or "").strip()
        clean_workflow = self._strip_panel_llm_debug_blocks(workflow_text or "").strip()
        parts = [part for part in (clean_system, clean_profile, clean_workflow) if part]
        return "\n\n".join(parts)

    def _stop(self) -> None:
        self._bridge.stop()
        self._set_microphone_open("main", False, reason="stop_clicked")
        try:
            self._call_timer_overlay.freeze()
        except Exception:
            pass
        if not bool(getattr(self, "_call_overlay_reconnect_pending", False)):
            self._close_customer_call_overlay()

    def _stop_settings_asr(self) -> None:
        self._settings_asr_bridge.stop()
        self._set_microphone_open("settings", False, reason="settings_asr_stopped")
        self._close_settings_asr_stream_line()
        self._refresh_system_instruction()

    def _stop_all_connections(self) -> None:
        self._stop()
        self._stop_settings_asr()
        if self.asr_enabled_var.get():
            self.asr_enabled_var.set(False)
            self.asr_toggle_text_var.set("开启ASR识别")
        self._reset_asr_wait()
        self._close_customer_call_overlay()

    def _open_customer_call_overlay(self) -> None:
        self._close_customer_call_overlay()

        # 同步加载背景图片，确保窗口直接以正确尺寸打开
        resource_dir = getattr(self, "_ui_resource_dir", Path(__file__).resolve().parent)
        bg_path = Path(resource_dir) / "1.png"
        bg_image: tk.PhotoImage | None = None
        try:
            bg_image = tk.PhotoImage(file=str(bg_path))
        except Exception:
            bg_image = None
        self._call_overlay_bg_image = bg_image

        if bg_image is not None:
            _default_w = bg_image.width()
            _default_h = bg_image.height()
        else:
            _default_w, _default_h = 520, 300

        screen_w = int(self.winfo_screenwidth() or 1600)
        screen_h = int(self.winfo_screenheight() or 900)
        min_w = min(screen_w - 80, 520)
        min_h = min(screen_h - 120, 300)
        _default_w = max(min_w, _default_w)
        _default_h = max(min_h, _default_h)

        win = tk.Toplevel(self)
        win.title("Call Overlay")
        win.attributes("-topmost", True)
        win.overrideredirect(True)
        win.resizable(False, False)
        win.configure(bg="#000000")
        win.protocol("WM_DELETE_WINDOW", self._hangup_customer_call_overlay)

        pos_x = max(0, int((screen_w - _default_w) / 2))
        pos_y = max(0, int((screen_h - _default_h) / 2))
        win.geometry(f"{_default_w}x{_default_h}+{pos_x}+{pos_y}")
        win.lift()
        win.update_idletasks()

        # Canvas covers entire window; text items have no background → transparent
        canvas = tk.Canvas(win, bg="#000000", highlightthickness=0, bd=0,
                           width=_default_w, height=_default_h)
        canvas.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)

        cx, cy = _default_w // 2, int(_default_h * 0.40)
        sx, sy = _default_w // 2, int(_default_h * 0.92)

        bg_item = canvas.create_image(0, 0, anchor="nw")
        if bg_image is not None:
            canvas.itemconfig(bg_item, image=bg_image)
        calling_item = canvas.create_text(
            cx, cy,
            text="连接中...",
            fill="#00ff00",
            font=(UI_FONT_FAMILY, 24, "bold"),
            anchor="center",
        )
        status_var = self.conversation_profile_status_var
        status_text = str(status_var.get() if isinstance(status_var, tk.StringVar) else "stopped | endpoint=-")
        status_item = canvas.create_text(
            sx, sy,
            text=f"状态: {status_text}",
            fill="#ffffff",
            font=(UI_FONT_FAMILY, 10, "bold"),
            anchor="center",
        )
        btn_font_size = 14
        btn_w = max(110, int(_default_w * 0.18))
        btn_h = max(46, int(_default_h * 0.14))
        btn_y = int(_default_h * 0.72)
        accept_button = tk.Button(
            win,
            text="接听",
            font=(UI_FONT_FAMILY, btn_font_size, "bold"),
            fg="#ffffff",
            bg="#169c46",
            disabledforeground="#f2f2f2",
            activeforeground="#ffffff",
            activebackground="#1bb14f",
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self._accept_customer_call_overlay,
        )
        accept_btn_x = max(24, int(_default_w * 0.20))
        accept_button.place(x=accept_btn_x, y=btn_y, width=btn_w, height=btn_h)
        accept_button.place_forget()
        hangup_button = tk.Button(
            win,
            text="挂断",
            font=(UI_FONT_FAMILY, btn_font_size, "bold"),
            fg="#ffffff",
            bg="#c9362b",
            activeforeground="#ffffff",
            activebackground="#de4034",
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self._hangup_customer_call_overlay,
        )
        hangup_btn_x = _default_w - btn_w - max(24, int(_default_w * 0.20))
        hangup_button.place(x=hangup_btn_x, y=btn_y, width=btn_w, height=btn_h)
        hangup_button.place_forget()

        self._call_overlay_window = win
        self._call_overlay_canvas = canvas
        self._call_overlay_canvas_bg_item = bg_item
        self._call_overlay_canvas_calling_item = calling_item
        self._call_overlay_canvas_status_item = status_item
        self._call_overlay_accept_button = accept_button
        self._call_overlay_hangup_button = hangup_button
        self._call_overlay_accept_button_place = {
            "x": accept_btn_x,
            "y": btn_y,
            "width": btn_w,
            "height": btn_h,
        }
        self._call_overlay_hangup_button_place = {
            "x": hangup_btn_x,
            "y": btn_y,
            "width": btn_w,
            "height": btn_h,
        }
        self._call_overlay_calling_anim_id = None
        self._call_overlay_calling_step = 0
        self._call_overlay_audio_started = False
        self._call_overlay_audio_click_ready = False
        self._call_overlay_phase = "connecting"
        self._call_overlay_drag_offset = None

        def _start_overlay_drag(event) -> None:
            try:
                self._call_overlay_drag_offset = (
                    int(getattr(event, "x_root", 0)) - int(win.winfo_x()),
                    int(getattr(event, "y_root", 0)) - int(win.winfo_y()),
                )
            except Exception:
                self._call_overlay_drag_offset = None

        def _drag_overlay(event) -> None:
            offset = getattr(self, "_call_overlay_drag_offset", None)
            if not isinstance(offset, tuple) or len(offset) != 2:
                return
            try:
                next_x = int(getattr(event, "x_root", 0)) - int(offset[0])
                next_y = int(getattr(event, "y_root", 0)) - int(offset[1])
                win.geometry(f"+{max(0, next_x)}+{max(0, next_y)}")
            except Exception:
                return

        def _end_overlay_drag(_event=None) -> None:
            self._call_overlay_drag_offset = None

        canvas.bind("<ButtonPress-1>", _start_overlay_drag, add="+")
        canvas.bind("<B1-Motion>", _drag_overlay, add="+")
        canvas.bind("<ButtonRelease-1>", _end_overlay_drag, add="+")
        canvas.tag_bind(calling_item, "<ButtonPress-1>", _start_overlay_drag, add="+")
        canvas.tag_bind(calling_item, "<B1-Motion>", _drag_overlay, add="+")
        canvas.tag_bind(calling_item, "<ButtonRelease-1>", _end_overlay_drag, add="+")
        canvas.tag_bind(status_item, "<ButtonPress-1>", _start_overlay_drag, add="+")
        canvas.tag_bind(status_item, "<B1-Motion>", _drag_overlay, add="+")
        canvas.tag_bind(status_item, "<ButtonRelease-1>", _end_overlay_drag, add="+")

        # Bounce animation: 8-frame vertical sine approximation at 120 ms/frame
        _BOUNCE_Y = [0, -5, -9, -12, -13, -12, -9, -5]
        _DOTS = ["", ".", "..", "..."]

        def _animate_calling():
            if self._call_overlay_calling_anim_id is None:
                return
            try:
                if not canvas.winfo_exists():
                    return
            except Exception:
                return
            step = self._call_overlay_calling_step
            # Recompute base y from current canvas size
            try:
                h = canvas.winfo_height() or _default_h
            except Exception:
                h = _default_h
            w = canvas.winfo_width() or _default_w
            base_cx = w // 2
            base_cy = int(h * 0.40)
            dy = _BOUNCE_Y[step % len(_BOUNCE_Y)]
            canvas.coords(calling_item, base_cx, base_cy + dy)
            phase = str(getattr(self, "_call_overlay_phase", "connecting") or "connecting")
            dot_text = _DOTS[(step // len(_BOUNCE_Y)) % len(_DOTS)]
            if phase == "connected":
                phase_text = "通话中..."
            elif phase == "calling":
                phase_text = f"呼叫中{dot_text}"
            else:
                phase_text = f"连接中{dot_text}"
            canvas.itemconfig(calling_item, text=phase_text)
            self._call_overlay_calling_step += 1
            self._call_overlay_calling_anim_id = win.after(120, _animate_calling)

        self._call_overlay_calling_anim_id = win.after(0, _animate_calling)
        self._schedule_customer_call_overlay_status_poll()

    def _set_customer_call_overlay_buttons_visible(self, visible: bool) -> None:
        accept_button = getattr(self, "_call_overlay_accept_button", None)
        hangup_button = getattr(self, "_call_overlay_hangup_button", None)
        if accept_button is not None:
            try:
                if visible and isinstance(getattr(self, "_call_overlay_accept_button_place", None), dict):
                    accept_button.place(**self._call_overlay_accept_button_place)
                else:
                    accept_button.place_forget()
            except Exception:
                pass
        if hangup_button is not None:
            try:
                if visible and isinstance(getattr(self, "_call_overlay_hangup_button_place", None), dict):
                    hangup_button.place(**self._call_overlay_hangup_button_place)
                else:
                    hangup_button.place_forget()
            except Exception:
                pass

    def _accept_customer_call_overlay(self) -> None:
        if str(getattr(self, "_call_overlay_phase", "") or "") != "calling":
            return
        if not bool(getattr(self, "_call_overlay_audio_started", False)):
            return
        if not bool(getattr(self, "_call_overlay_audio_click_ready", False)):
            return
        status_var = self.conversation_profile_status_var
        status_text = str(status_var.get() if isinstance(status_var, tk.StringVar) else "stopped | endpoint=-")
        state_prefix = status_text.strip().lower().split("|", 1)[0].strip()
        if state_prefix != "running":
            return
        self._stop_customer_call_overlay_audio_loop()
        self._call_overlay_phase = "connected"
        # 停止跳动动画，避免继续覆盖接通状态文案
        anim_id = self._call_overlay_calling_anim_id
        if anim_id is not None:
            try:
                self.after_cancel(anim_id)
            except Exception:
                pass
            self._call_overlay_calling_anim_id = None
        canvas = self._call_overlay_canvas
        calling_item = self._call_overlay_canvas_calling_item
        if canvas is None or calling_item is None:
            return
        try:
            if not canvas.winfo_exists():
                return
        except Exception:
            return
        canvas.itemconfig(calling_item, text="通话中...", fill="#ffff00")
        accept_button = self._call_overlay_accept_button
        if accept_button is not None:
            try:
                accept_button.configure(
                    state="disabled",
                    cursor="arrow",
                    bg="#7a7a7a",
                    activebackground="#7a7a7a",
                    disabledforeground="#f2f2f2",
                )
            except Exception:
                pass

    def _hangup_customer_call_overlay(self) -> None:
        self._close_customer_call_overlay(disconnect=True)

    def _schedule_customer_call_overlay_status_poll(self) -> None:
        if self._call_overlay_status_poll_after_id:
            try:
                self.after_cancel(self._call_overlay_status_poll_after_id)
            except Exception:
                pass
        self._call_overlay_status_poll_after_id = self.after(250, self._poll_customer_call_overlay_status)

    def _poll_customer_call_overlay_status(self) -> None:
        self._call_overlay_status_poll_after_id = None
        canvas = self._call_overlay_canvas
        item_id = self._call_overlay_canvas_status_item
        win = self._call_overlay_window
        if canvas is None or item_id is None or win is None:
            return
        try:
            if not win.winfo_exists() or not canvas.winfo_exists():
                return
        except Exception:
            return
        status_var = self.conversation_profile_status_var
        status_text = str(status_var.get() if isinstance(status_var, tk.StringVar) else "stopped | endpoint=-")
        try:
            canvas.itemconfig(item_id, text=f"状态: {status_text}")
        except Exception:
            return
        state_prefix = status_text.strip().lower().split("|", 1)[0].strip()
        if state_prefix != "running":
            # 进程已退出 → 重置为连接中
            self._call_overlay_phase = "connecting"
            self._call_overlay_ws_connected = False
            calling_item = self._call_overlay_canvas_calling_item
            if calling_item is not None:
                try:
                    canvas.itemconfig(calling_item, text="连接中...", fill="#00ff00")
                except Exception:
                    pass
            if bool(getattr(self, "_call_overlay_audio_started", False)):
                self._stop_customer_call_overlay_audio_loop()
            self._set_customer_call_overlay_buttons_visible(False)
        self._schedule_customer_call_overlay_status_poll()

    def _start_customer_call_overlay_audio_loop(self) -> None:
        resource_dir = getattr(self, "_ui_resource_dir", Path(__file__).resolve().parent)
        audio_path = Path(resource_dir) / "1.wav"
        self._call_overlay_audio_started = False
        self._call_overlay_audio_click_ready = False
        if not audio_path.exists():
            return
        if winsound is None:
            return
        self._stop_customer_call_overlay_audio_loop()
        try:
            winsound.PlaySound(
                str(audio_path),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP,
            )
            self._call_overlay_audio_started = True
            self._set_customer_call_overlay_buttons_visible(True)
            try:
                self.after(350, self._mark_customer_call_overlay_audio_click_ready)
            except Exception:
                self._call_overlay_audio_click_ready = True
        except Exception:
            self._call_overlay_audio_started = False
            self._call_overlay_audio_click_ready = False

    def _stop_customer_call_overlay_audio_loop(self) -> None:
        self._call_overlay_audio_started = False
        self._call_overlay_audio_click_ready = False
        if winsound is None:
            return
        try:
            winsound.PlaySound(None, 0)
        except Exception:
            pass

    def _mark_customer_call_overlay_audio_click_ready(self) -> None:
        if not bool(getattr(self, "_call_overlay_audio_started", False)):
            self._call_overlay_audio_click_ready = False
            return
        if self._call_overlay_window is None:
            self._call_overlay_audio_click_ready = False
            return
        self._call_overlay_audio_click_ready = True

    def _on_customer_call_overlay_ws_connected(self) -> None:
        self._call_overlay_ws_connected = True
        # WS 建连成功 → 切换到"呼叫中"阶段并开始放铃声
        self._call_overlay_phase = "calling"
        canvas = self._call_overlay_canvas
        calling_item = self._call_overlay_canvas_calling_item
        if canvas is not None and calling_item is not None:
            try:
                canvas.itemconfig(calling_item, text="呼叫中...", fill="#00ff00")
            except Exception:
                pass
        if not bool(getattr(self, "_call_overlay_audio_started", False)):
            self._start_customer_call_overlay_audio_loop()

    def _on_customer_call_overlay_tts_first_frame(self) -> None:
        # TTS 首包 → 先显示"通话中..."，再关闭呼叫浮窗、启动计时
        canvas = self._call_overlay_canvas
        calling_item = self._call_overlay_canvas_calling_item
        if canvas is not None and calling_item is not None:
            try:
                canvas.itemconfig(calling_item, text="通话中...", fill="#00ff00")
            except Exception:
                pass
        self._close_customer_call_overlay()
        try:
            self._call_timer_overlay.start()
        except Exception:
            pass

    def _close_customer_call_overlay(self, disconnect: bool = False) -> None:
        if self._call_overlay_status_poll_after_id:
            try:
                self.after_cancel(self._call_overlay_status_poll_after_id)
            except Exception:
                pass
            self._call_overlay_status_poll_after_id = None
        # Cancel calling animation
        anim_id = getattr(self, "_call_overlay_calling_anim_id", None)
        if anim_id is not None:
            try:
                self.after_cancel(anim_id)
            except Exception:
                pass
        self._call_overlay_calling_anim_id = None
        self._stop_customer_call_overlay_audio_loop()
        if disconnect:
            try:
                self._call_timer_overlay.freeze()
            except Exception:
                pass
        if disconnect and bool(getattr(self._bridge, "running", False)):
            try:
                self._bridge.stop()
            except Exception:
                pass
            try:
                self._set_microphone_open("main", False, reason="call_overlay_closed")
            except Exception:
                pass
        win = self._call_overlay_window
        if win is not None:
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass
        # winsound loop stop is best-effort; issue one more stop after window teardown.
        self._stop_customer_call_overlay_audio_loop()
        self._call_overlay_window = None
        self._call_overlay_canvas = None
        self._call_overlay_canvas_bg_item = None
        self._call_overlay_canvas_calling_item = None
        self._call_overlay_canvas_status_item = None
        self._call_overlay_accept_button = None
        self._call_overlay_hangup_button = None
        self._call_overlay_accept_button_place = None
        self._call_overlay_hangup_button_place = None
        self._call_overlay_bg_image = None
        self._call_overlay_audio_started = False
        self._call_overlay_audio_click_ready = False
        self._call_overlay_phase = "connecting"
        self._call_overlay_drag_offset = None
        self._call_overlay_ws_connected = False

    def _schedule_snapshot_autosave(self) -> None:
        if self._snapshot_autosave_after_id:
            try:
                self.after_cancel(self._snapshot_autosave_after_id)
            except Exception:
                pass
        self._snapshot_autosave_after_id = self.after(self._snapshot_autosave_interval_ms, self._run_snapshot_autosave)

    def _run_snapshot_autosave(self) -> None:
        self._snapshot_autosave_after_id = None
        try:
            self._save_persisted_conversation_tab_snapshots()
        except Exception:
            pass
        if self.winfo_exists():
            self._schedule_snapshot_autosave()

    def _on_close(self) -> None:
        if self.flow_editor_panel and (not self.flow_editor_panel.confirm_close()):
            return
        try:
            self._hide_flow_tooltip()
            if self._snapshot_autosave_after_id:
                try:
                    self.after_cancel(self._snapshot_autosave_after_id)
                except Exception:
                    pass
                self._snapshot_autosave_after_id = None
            self._save_persisted_conversation_tabs()
            self._save_persisted_conversation_tab_snapshots()
            self._save_runtime_audio_config(silent=True)
            for dialog in list(self._editor_dialogs):
                self._close_settings_editor_dialog(dialog, destroy_window=False)
            self._stop()
            self._stop_settings_asr()
            self._flush_send_done_summary(force=True)
            self._flush_log_buffer(force=True)
            self._close_runtime_log_file()
            self._close_async_log_writer()
        finally:
            if self._flow_tooltip_window:
                try:
                    self._flow_tooltip_window.destroy()
                except Exception:
                    pass
                self._flow_tooltip_window = None
                self._flow_tooltip_label = None
            self.destroy()

    def _clear_views(self) -> None:
        ctrl_clear_views(self)

    def _export_events(self) -> None:
        ctrl_export_events(self)

    @staticmethod
    def _is_high_priority_event(kind: str) -> bool:
        return ctrl_is_high_priority_event(kind, UI_HIGH_PRIORITY_EVENT_KINDS)

    def _drain_event_queues(self, limit: int = UI_POLL_DRAIN_LIMIT_PER_TICK) -> None:
        ctrl_drain_event_queues(self, is_high_priority=self._is_high_priority_event, limit=limit)

    def _pop_next_buffered_event(self) -> tuple[str, UiEvent] | None:
        return ctrl_pop_next_buffered_event(self)

    def _reset_send_done_summary(self) -> None:
        ctrl_reset_send_done_summary(self)

    def _flush_send_done_summary(self, force: bool = False) -> None:
        ctrl_flush_send_done_summary(self, force=force)

    def _consume_send_done_log(self, ts_text: str, raw_line: str) -> bool:
        return ctrl_consume_send_done_log(
            self,
            ts_text=ts_text,
            raw_line=raw_line,
            send_done_log_re=RE_SEND_DONE_LOG,
            send_done_summary_interval_seconds=UI_SEND_DONE_SUMMARY_INTERVAL_SECONDS,
        )

    def _buffer_log_line(self, line: str) -> None:
        ctrl_buffer_log_line(
            self,
            line=line,
            log_flush_interval_seconds=UI_LOG_FLUSH_INTERVAL_SECONDS,
        )

    def _flush_log_buffer(self, force: bool = False) -> None:
        ctrl_flush_log_buffer(
            self,
            force=force,
            log_flush_interval_seconds=UI_LOG_FLUSH_INTERVAL_SECONDS,
        )

    def _poll_events(self) -> None:
        ctrl_poll_events(
            self,
            drain_limit=UI_POLL_DRAIN_LIMIT_PER_TICK,
            max_events_per_tick=UI_POLL_MAX_EVENTS_PER_TICK,
            max_ms_per_tick=UI_POLL_MAX_MS_PER_TICK,
            busy_interval_ms=UI_POLL_BUSY_INTERVAL_MS,
            idle_interval_ms=UI_POLL_IDLE_INTERVAL_MS,
        )

    def _handle_event(self, event: UiEvent) -> None:
        ctrl_handle_event(
            self,
            event,
            event_history_max=UI_EVENT_HISTORY_MAX,
            event_history_trim_batch=UI_EVENT_HISTORY_TRIM_BATCH,
        )

    def _handle_settings_asr_event(self, event: UiEvent) -> None:
        ctrl_handle_settings_asr_event(self, event)

    def _set_cmd_derived_status(self, command: str) -> None:
        tokens = self._safe_split(command)
        transport = "ws"
        channel = "split"

        if "--transport" in tokens:
            idx = tokens.index("--transport")
            if idx + 1 < len(tokens):
                transport = tokens[idx + 1].strip()
        if "--ws-single-channel" in tokens:
            channel = "single"
        if "--ws-split-channels" in tokens:
            channel = "split"
        if transport == "http":
            channel = "-"

        self.transport_var.set(transport)
        self.channel_var.set(channel)
        self._sync_server_env_from_command(command)

    def _on_server_env_changed(self) -> None:
        self._apply_server_env_to_command()

    def _on_conversation_server_env_changed(self) -> None:
        self._apply_server_env_to_conversation_command()

    def _on_conversation_command_changed(self, _event=None) -> None:
        self.after_idle(lambda: self._sync_conversation_server_env_from_command(self.conversation_command_var.get().strip()))

    def _apply_server_env_to_command(self) -> None:
        ctrl_apply_server_env_to_command(self)

    def _apply_server_env_to_conversation_command(self) -> None:
        ctrl_apply_server_env_to_conversation_command(self)

    def _apply_server_env_to_command_vars(self, command_var: tk.StringVar, env_var: tk.StringVar) -> None:
        ctrl_apply_server_env_to_command_vars(self, command_var, env_var)

    def _sync_server_env_from_command(self, command: str) -> None:
        ctrl_sync_server_env_from_command(self, command)

    def _sync_conversation_server_env_from_command(self, command: str) -> None:
        ctrl_sync_conversation_server_env_from_command(self, command)

    def _sync_server_env_from_command_to_var(self, command: str, env_var: tk.StringVar) -> None:
        ctrl_sync_server_env_from_command_to_var(self, command, env_var)

    def _toggle_asr(self) -> None:
        ctrl_toggle_asr(self)

    def _clear_customer_profile_text(self) -> None:
        return

    def _clear_workflow_text(self) -> None:
        return

    def _clear_conversation_strategy_text(self) -> None:
        widget = self.conversation_workflow_text
        if isinstance(widget, ScrolledText):
            self._set_text_content(widget, "")
        input_widget = self.conversation_strategy_input_text
        if isinstance(input_widget, tk.Text):
            input_widget.delete("1.0", "end")
            input_widget.event_generate("<KeyRelease>")
        self._conversation_strategy_history.clear()
        self._render_conversation_strategy_history_panel()

    def _clear_system_instruction_text(self) -> None:
        return

    def _clear_ai_analysis_text(self) -> None:
        return

    def _toggle_flow_script_panel(self) -> None:
        ctrl_toggle_flow_script_panel(self)

    def _flow_monitor_zoom_in(self) -> None:
        ctrl_flow_monitor_zoom_in(self)

    def _flow_monitor_zoom_out(self) -> None:
        ctrl_flow_monitor_zoom_out(self)

    def _flow_monitor_zoom_reset(self) -> None:
        ctrl_flow_monitor_zoom_reset(self)

    def _apply_flow_monitor_active_node_style(self) -> None:
        ctrl_apply_flow_monitor_active_node_style(self)

    def _lock_flow_monitor_interactions(self) -> None:
        ctrl_lock_flow_monitor_interactions(self)

    def _bind_flow_monitor_hover_events(self) -> None:
        ctrl_bind_flow_monitor_hover_events(self)

    def _restore_flow_monitor_highlight(self) -> None:
        ctrl_restore_flow_monitor_highlight(self)

    def _flow_monitor_node_id_at(self, canvas_x: float, canvas_y: float) -> str:
        return ctrl_flow_monitor_node_id_at(self, canvas_x, canvas_y)

    def _show_flow_tooltip(self, text: str, screen_x: int, screen_y: int) -> None:
        ctrl_show_flow_tooltip(self, text, screen_x, screen_y)

    def _hide_flow_tooltip(self) -> None:
        ctrl_hide_flow_tooltip(self)

    def _on_flow_monitor_leave(self, _event: tk.Event) -> None:
        ctrl_on_flow_monitor_leave(self, _event)

    def _on_flow_monitor_motion(self, event: tk.Event) -> None:
        ctrl_on_flow_monitor_motion(self, event)

    @staticmethod
    def _to_float(value: object, fallback: float) -> float:
        return ctrl_to_float(value, fallback)

    @staticmethod
    def _coerce_node_type(value: object) -> str:
        return ctrl_coerce_node_type(value)

    def _build_flow_graph_models(
        self,
        payload: dict[str, object],
    ) -> tuple[list[FlowNode], list[FlowEdge], dict[str, object], dict[str, object]]:
        return ctrl_build_flow_graph_models(payload)

    def _render_flow_monitor_graph(self, payload: dict[str, object]) -> None:
        ctrl_render_flow_monitor_graph(self, payload)

    def _center_flow_monitor_node(self, node_id: str) -> None:
        ctrl_center_flow_monitor_node(self, node_id)

    def _highlight_flow_monitor_node(self, node_id: str, *, center: bool = True) -> bool:
        return ctrl_highlight_flow_monitor_node(self, node_id, center=center)

    def _handle_workflow_progress_event(self, payload: dict[str, object], ts_text: str) -> None:
        ctrl_handle_workflow_progress_event(self, payload, ts_text)

    def _load_workflow_json_file(self) -> None:
        ctrl_load_workflow_json_file(self)

    def _clear_loaded_workflow_json(self) -> None:
        ctrl_clear_loaded_workflow_json(self)

    def _clear_intent_page_views(self) -> None:
        return

    def _submit_customer_profile_from_panel(self) -> None:
        ctrl_submit_customer_profile_from_panel_removed(self)

    def _submit_workflow_from_panel(self) -> None:
        ctrl_submit_workflow_from_panel_removed(self)

    def _open_conversation_customer_profile_dialog(self) -> None:
        self._open_conversation_customer_profile_generator_dialog()

    def _render_conversation_strategy_history_panel(self) -> None:
        ctrl_render_conversation_strategy_history_panel(self)

    def _get_conversation_strategy_history_for_tab(self, tab_id: str) -> list[dict[str, str]]:
        return ctrl_get_conversation_strategy_history_for_tab(self, tab_id)

    def _render_conversation_strategy_dialog_history(self, dialog: dict[str, object]) -> None:
        ctrl_render_conversation_strategy_dialog_history(self, dialog)

    def _append_text_to_widget_with_tag(self, widget: ScrolledText, text: str, tag: str) -> None:
        ctrl_append_text_to_widget_with_tag(self, widget, text, tag)

    def _try_append_customer_profile_bubble(self, widget: ScrolledText, text: str, tag: str) -> bool:
        return ctrl_try_append_customer_profile_bubble(self, widget, text, tag)

    @staticmethod
    def _is_instruction_header_line(text: str) -> bool:
        return ctrl_is_instruction_header_line(text)

    @staticmethod
    def _is_llm_header_line(text: str) -> bool:
        return ctrl_is_llm_header_line(text)

    @staticmethod
    def _draw_rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> int:
        return ctrl_draw_rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs)

    def _render_customer_profile_bubble_canvas(
        self,
        widget: ScrolledText,
        canvas: tk.Canvas,
        header: str,
        body: str,
        is_right: bool,
    ) -> int:
        return ctrl_render_customer_profile_bubble_canvas(self, widget, canvas, header, body, is_right)

    def _insert_customer_profile_bubble_row(
        self,
        widget: ScrolledText,
        *,
        header: str,
        body: str,
        is_right: bool,
        keep_active: bool,
    ) -> None:
        ctrl_insert_customer_profile_bubble_row(
            self,
            widget,
            header=header,
            body=body,
            is_right=is_right,
            keep_active=keep_active,
        )

    def _append_customer_profile_bubble_text(self, widget: ScrolledText, active: dict[str, object], chunk: str) -> None:
        ctrl_append_customer_profile_bubble_text(self, widget, active, chunk)

    def _prepare_live_conversation_strategy_response_bubble(self, source_widget: ScrolledText) -> None:
        ctrl_prepare_live_conversation_strategy_response_bubble(self, source_widget)

    def _append_live_conversation_strategy_thinking_chunk(self, source_widget: ScrolledText, chunk: str) -> None:
        ctrl_append_live_conversation_strategy_thinking_chunk(self, source_widget, chunk)

    def _append_live_conversation_strategy_content_chunk(self, source_widget: ScrolledText, chunk: str) -> None:
        ctrl_append_live_conversation_strategy_content_chunk(self, source_widget, chunk)

    def _wrap_text_for_strategy_history_bubble(
        self,
        text: str,
        history_widget: ScrolledText,
        max_width_px: int,
    ) -> str:
        return ctrl_wrap_text_for_strategy_history_bubble(text, history_widget, max_width_px)

    def _update_conversation_strategy_dialog_history_tags(self, history_widget: ScrolledText) -> None:
        ctrl_update_conversation_strategy_dialog_history_tags(history_widget)

    def _update_customer_profile_dialog_history_tags(self, history_widget: ScrolledText) -> None:
        ctrl_update_customer_profile_dialog_history_tags(history_widget)

    def _append_conversation_strategy_history(
        self,
        instruction_text: str,
        response_text: str,
    ) -> None:
        ctrl_append_conversation_strategy_history(self, instruction_text, response_text)

    def _build_conversation_strategy_prompt_with_history(self, instruction_text: str, tab_id: str = "") -> str:
        return ctrl_build_conversation_strategy_prompt_with_history(self, instruction_text, tab_id)

    def _submit_conversation_strategy_from_panel(self) -> None:
        ctrl_submit_conversation_strategy_from_panel(self)

    def _open_conversation_strategy_generator_dialog(self) -> None:
        ctrl_open_conversation_strategy_generator_dialog(
            self,
            ui_font_family=UI_FONT_FAMILY,
            ui_font_size=UI_FONT_SIZE,
        )

    def _generate_conversation_strategy_in_dialog(self) -> None:
        ctrl_generate_conversation_strategy_in_dialog(self)

    def _submit_conversation_strategy_llm_worker(
        self,
        submit_tab_id: str,
        source_widget: ScrolledText,
        instruction_text: str,
        llm_prompt: str,
    ) -> None:
        ctrl_submit_conversation_strategy_llm_worker(
            self,
            submit_tab_id,
            source_widget,
            instruction_text,
            llm_prompt,
        )

    def _on_submit_conversation_strategy_llm_done(
        self,
        submit_tab_id: str,
        source_widget: ScrolledText,
        instruction_text: str,
        result_text: str,
        thinking_text: str,
        error_text: str,
        thinking_seen: bool,
        content_seen: bool,
    ) -> None:
        ctrl_on_submit_conversation_strategy_llm_done(
            self,
            submit_tab_id,
            source_widget,
            instruction_text,
            result_text,
            thinking_text,
            error_text,
            thinking_seen,
            content_seen,
        )

    def _save_conversation_strategy_dialog(self) -> None:
        ctrl_save_conversation_strategy_dialog(self)

    def _get_conversation_customer_profile_history_for_tab(self, tab_id: str) -> list[dict[str, str]]:
        return ctrl_get_conversation_customer_profile_history_for_tab(self, tab_id)

    def _render_conversation_customer_profile_dialog_history(self, dialog: dict[str, object]) -> None:
        ctrl_render_conversation_customer_profile_dialog_history(self, dialog)

    def _prepare_live_conversation_customer_profile_response_bubble(self, source_widget: ScrolledText) -> None:
        ctrl_prepare_live_conversation_customer_profile_response_bubble_phase(self, source_widget)

    def _append_live_conversation_customer_profile_thinking_chunk(self, source_widget: ScrolledText, chunk: str) -> None:
        ctrl_append_live_conversation_customer_profile_thinking_chunk_phase(self, source_widget, chunk)

    def _append_live_conversation_customer_profile_content_chunk(self, source_widget: ScrolledText, chunk: str) -> None:
        ctrl_append_live_conversation_customer_profile_content_chunk_phase(self, source_widget, chunk)

    def _append_conversation_customer_profile_history(
        self,
        instruction_text: str,
        response_text: str,
    ) -> None:
        ctrl_append_conversation_customer_profile_history(self, instruction_text, response_text)

    def _build_conversation_customer_profile_prompt_with_history(self, instruction_text: str, tab_id: str = "") -> str:
        return ctrl_build_conversation_customer_profile_prompt_with_history(self, instruction_text, tab_id=tab_id)

    def _save_conversation_system_instruction_from_panel(self) -> None:
        """保存系统指令的内容，使其立即生效"""
        self._refresh_runtime_system_prompt_only()
        self._save_persisted_conversation_tab_snapshots(persist_workflow_fields=True)
        ctrl_set_workflow_doc_dirty(self, False)
        from tkinter import messagebox
        messagebox.showinfo("保存成功", "系统指令已保存并生效")

    def _save_conversation_customer_profile_from_panel(self) -> None:
        """保存客户画像内容到快照"""
        try:
            self._save_persisted_conversation_tab_snapshots(persist_workflow_fields=True)
            ctrl_set_workflow_doc_dirty(self, False)
            from tkinter import messagebox
            messagebox.showinfo("保存成功", "客户画像已保存")
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc))

    def _save_conversation_intent_from_panel(self) -> None:
        """保存客户意图内容到快照"""
        try:
            self._save_persisted_conversation_tab_snapshots(persist_workflow_fields=True)
            ctrl_set_workflow_doc_dirty(self, False)
            from tkinter import messagebox
            messagebox.showinfo("保存成功", "客户意图已保存")
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc))

    def _save_conversation_strategy_from_panel(self) -> None:
        """保存对话策略内容到快照"""
        try:
            self._save_persisted_conversation_tab_snapshots(persist_workflow_fields=True)
            ctrl_set_workflow_doc_dirty(self, False)
            from tkinter import messagebox
            messagebox.showinfo("保存成功", "对话策略已保存")
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc))

    def _save_dialog_summary_prompt_from_panel(self) -> None:
        """保存对话总结提示词模板"""
        try:
            self._save_persisted_conversation_tab_snapshots(persist_workflow_fields=True)
            ctrl_set_workflow_doc_dirty(self, False)
            from tkinter import messagebox
            messagebox.showinfo("保存成功", "对话总结提示词已保存")
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc))

    def _save_pending_items_prompt_from_panel(self) -> None:
        """保存待核实事项提示词模板"""
        try:
            self._save_persisted_conversation_tab_snapshots(persist_workflow_fields=True)
            ctrl_set_workflow_doc_dirty(self, False)
            from tkinter import messagebox
            messagebox.showinfo("保存成功", "待核实事项提示词已保存")
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc))

    def _save_dialog_strategy_prompt_from_panel(self) -> None:
        """保存对话策略提示词模板"""
        try:
            self._save_persisted_conversation_tab_snapshots(persist_workflow_fields=True)
            ctrl_set_workflow_doc_dirty(self, False)
            from tkinter import messagebox
            messagebox.showinfo("保存成功", "对话策略提示词已保存")
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc))

    def _submit_conversation_customer_profile_from_panel(self) -> None:
        self._open_conversation_customer_profile_generator_dialog()

    def _open_conversation_customer_profile_generator_dialog(self) -> None:
        ctrl_open_conversation_customer_profile_generator_dialog(
            self,
            ui_font_family=UI_FONT_FAMILY,
            ui_font_size=UI_FONT_SIZE,
        )

    def _generate_conversation_customer_profile_in_dialog(self) -> None:
        ctrl_generate_conversation_customer_profile_in_dialog(self)

    def _submit_conversation_customer_profile_llm_worker(
        self,
        submit_tab_id: str,
        source_widget: ScrolledText,
        instruction_text: str,
        llm_prompt: str,
    ) -> None:
        ctrl_submit_conversation_customer_profile_llm_worker(
            self,
            submit_tab_id,
            source_widget,
            instruction_text,
            llm_prompt,
        )

    def _on_submit_conversation_customer_profile_llm_done(
        self,
        submit_tab_id: str,
        source_widget: ScrolledText,
        instruction_text: str,
        result_text: str,
        thinking_text: str,
        error_text: str,
        thinking_seen: bool,
        content_seen: bool,
    ) -> None:
        ctrl_on_submit_conversation_customer_profile_llm_done(
            self,
            submit_tab_id,
            source_widget,
            instruction_text,
            result_text,
            thinking_text,
            error_text,
            thinking_seen,
            content_seen,
        )

    def _save_conversation_customer_profile_dialog(self) -> None:
        ctrl_save_conversation_customer_profile_dialog(self)

    def _get_conversation_intent_generator_history_for_tab(self, tab_id: str) -> list[dict[str, str]]:
        return ctrl_get_conversation_intent_generator_history_for_tab(self, tab_id)

    def _render_conversation_intent_dialog_history(self, dialog: dict[str, object]) -> None:
        ctrl_render_conversation_intent_dialog_history(self, dialog)

    def _prepare_live_conversation_intent_response_bubble(self, source_widget: ScrolledText) -> None:
        ctrl_prepare_live_conversation_intent_response_bubble_phase(self, source_widget)

    def _append_live_conversation_intent_thinking_chunk(self, source_widget: ScrolledText, chunk: str) -> None:
        ctrl_append_live_conversation_intent_thinking_chunk_phase(self, source_widget, chunk)

    def _append_live_conversation_intent_content_chunk(self, source_widget: ScrolledText, chunk: str) -> None:
        ctrl_append_live_conversation_intent_content_chunk_phase(self, source_widget, chunk)

    def _append_conversation_intent_generator_history(
        self,
        instruction_text: str,
        response_text: str,
    ) -> None:
        ctrl_append_conversation_intent_generator_history(self, instruction_text, response_text)

    def _build_conversation_intent_prompt_with_history(self, instruction_text: str, tab_id: str = "") -> str:
        return ctrl_build_conversation_intent_prompt_with_history(self, instruction_text, tab_id=tab_id)

    def _submit_conversation_intent_from_panel(self) -> None:
        self._open_conversation_intent_generator_dialog()

    def _open_conversation_intent_generator_dialog(self) -> None:
        ctrl_open_conversation_intent_generator_dialog(
            self,
            ui_font_family=UI_FONT_FAMILY,
            ui_font_size=UI_FONT_SIZE,
        )

    def _generate_conversation_intent_in_dialog(self) -> None:
        ctrl_generate_conversation_intent_in_dialog(self)

    def _submit_conversation_intent_llm_worker(
        self,
        submit_tab_id: str,
        source_widget: ScrolledText,
        instruction_text: str,
        llm_prompt: str,
    ) -> None:
        ctrl_submit_conversation_intent_llm_worker(
            self,
            submit_tab_id,
            source_widget,
            instruction_text,
            llm_prompt,
        )

    def _on_submit_conversation_intent_llm_done(
        self,
        submit_tab_id: str,
        source_widget: ScrolledText,
        instruction_text: str,
        result_text: str,
        thinking_text: str,
        error_text: str,
        thinking_seen: bool,
        content_seen: bool,
    ) -> None:
        ctrl_on_submit_conversation_intent_llm_done(
            self,
            submit_tab_id,
            source_widget,
            instruction_text,
            result_text,
            thinking_text,
            error_text,
            thinking_seen,
            content_seen,
        )

    def _save_conversation_intent_dialog(self) -> None:
        ctrl_save_conversation_intent_dialog(self)

    @staticmethod
    def _build_intent_generation_prompt(customer_profile_text: str, workflow_text: str, count: int) -> str:
        return ctrl_build_intent_generation_prompt(customer_profile_text, workflow_text, count)

    def _append_intent_system_text(self, text: str) -> None:
        ctrl_append_intent_system_text(self, text)

    def _generate_intents_from_settings(self) -> None:
        ctrl_generate_intents_from_settings_removed(self)

    def _generate_intents_from_settings_worker(self, llm_prompt: str) -> None:
        return

    def _on_generate_intents_from_settings_done(
        self,
        result_text: str,
        thinking_text: str,
        error_text: str,
        thinking_seen: bool,
    ) -> None:
        return

    def _submit_settings_panel_llm(
        self,
        kind: str,
        kind_label: str,
        source_widget: ScrolledText,
    ) -> None:
        ctrl_submit_settings_panel_llm_removed(self, kind_label)

    def _submit_settings_panel_llm_worker(
        self,
        kind: str,
        kind_label: str,
        source_widget: ScrolledText,
        llm_prompt: str,
    ) -> None:
        return

    def _on_submit_settings_panel_llm_done(
        self,
        kind: str,
        kind_label: str,
        source_widget: ScrolledText,
        result_text: str,
        thinking_text: str,
        error_text: str,
        thinking_seen: bool,
    ) -> None:
        return

    def _open_customer_profile_dialog(self) -> None:
        ctrl_open_customer_profile_dialog_removed(self)

    def _build_dialog_summary_text(self, focus_hint: str = "") -> str:
        return ctrl_build_dialog_summary_text(self, focus_hint=focus_hint)

    def _build_next_dialog_strategy_text(self, focus_hint: str = "") -> str:
        return ctrl_build_next_dialog_strategy_text(self, focus_hint=focus_hint)

    def _build_dialog_summary_llm_prompt(
        self,
        conversation_text: str,
        extra_hint: str = "",
    ) -> str:
        template_text = self._get_dialog_summary_prompt_template()
        return ctrl_build_dialog_summary_llm_prompt(
            conversation_text,
            extra_hint,
            template_text=template_text,
        )

    def _build_next_dialog_strategy_llm_prompt(
        self,
        conversation_text: str,
        commitment_confirmation_text: str = "",
        extra_hint: str = "",
    ) -> str:
        template_text = self._get_dialog_strategy_prompt_template()
        return ctrl_build_next_dialog_strategy_llm_prompt(
            conversation_text,
            commitment_confirmation_text,
            extra_hint,
            template_text=template_text,
        )

    def _get_dialog_summary_prompt_template(self) -> str:
        return ctrl_get_dialog_summary_prompt_template(self)

    def _get_pending_items_prompt_template(self) -> str:
        return ctrl_get_pending_items_prompt_template(self)

    def _get_dialog_strategy_prompt_template(self) -> str:
        return ctrl_get_dialog_strategy_prompt_template(self)

    @staticmethod
    def _extract_pending_commitment_items(summary_text: str) -> list[str]:
        return ctrl_extract_pending_commitment_items(summary_text)

    @staticmethod
    def _format_commitment_confirmation_text(confirmed_rows: list[dict[str, str]]) -> str:
        return ctrl_format_commitment_confirmation_text(confirmed_rows)

    def _open_commitment_confirmation_dialog(
        self,
        parent: tk.Toplevel,
        pending_items: list[str],
    ) -> list[dict[str, str]] | None:
        return ctrl_open_commitment_confirmation_dialog(self, parent, pending_items)

    def _open_dialog_summary_modal(self) -> None:
        ctrl_open_dialog_summary_modal(self, ui_font_family=UI_FONT_FAMILY)

    def _open_workflow_dialog(self) -> None:
        ctrl_open_workflow_dialog_removed(self)

    def _open_settings_editor_dialog(
        self,
        kind: str,
        kind_label: str,
        source_widget: ScrolledText,
    ) -> None:
        ctrl_open_settings_editor_dialog(self, kind, kind_label, source_widget)

    def _close_settings_editor_dialog(self, dialog: dict[str, object], destroy_window: bool = True) -> None:
        ctrl_close_settings_editor_dialog(self, dialog, destroy_window=destroy_window)

    def _poll_editor_dialog_events(self, dialog: dict[str, object]) -> None:
        ctrl_poll_editor_dialog_events(self, dialog)

    def _build_dialog_llm_prompt(self, kind: str, instruction_text: str) -> str:
        return ctrl_build_dialog_llm_prompt(kind, instruction_text)

    def _submit_editor_dialog(self, dialog: dict[str, object]) -> None:
        ctrl_submit_editor_dialog(self, dialog)

    def _submit_editor_dialog_worker(self, dialog: dict[str, object], llm_prompt: str) -> None:
        ctrl_submit_editor_dialog_worker(self, dialog, llm_prompt)

    def _on_editor_dialog_submit_done(
        self,
        dialog: dict[str, object],
        result_text: str,
        thinking_text: str,
        error_text: str,
    ) -> None:
        ctrl_on_editor_dialog_submit_done(self, dialog, result_text, thinking_text, error_text)

    @staticmethod
    def _normalize_asr_command_text(text: str) -> str:
        lowered = (text or "").strip()
        for ch in (" ", "\t", "\r", "\n", ",", ".", "!", "?", ":", ";", "，", "。", "！", "？", "：", "；"):
            lowered = lowered.replace(ch, "")
        return lowered

    def _settings_asr_should_submit_customer_profile(self, text: str, command: str) -> bool:
        return (
            self._normalize_asr_command_text(text) == "提交"
            or self._normalize_asr_command_text(command) == "提交"
        )

    @staticmethod
    def _strip_llm_asr_debug_blocks(raw_text: str) -> str:
        lines: list[str] = []
        skip_block = False
        for line in (raw_text or "").splitlines():
            marker = line.strip()
            if (
                marker in {"[LLM_ASR_PROMPT_BEGIN]", "[LLM_ASR_THINKING_BEGIN]"}
                or marker.startswith("[LLM_PANEL_PROMPT_BEGIN]")
                or marker.startswith("[LLM_PANEL_THINKING_BEGIN]")
                or marker.startswith("[LLM_DIALOG_PROMPT_BEGIN]")
            ):
                skip_block = True
                continue
            if (
                marker in {"[LLM_ASR_PROMPT_END]", "[LLM_ASR_THINKING_END]"}
                or marker.startswith("[LLM_PANEL_PROMPT_END]")
                or marker.startswith("[LLM_PANEL_THINKING_END]")
                or marker.startswith("[LLM_DIALOG_PROMPT_END]")
            ):
                skip_block = False
                continue
            if marker.startswith("[LLM_ASR_"):
                continue
            if marker.startswith("[LLM_PANEL_"):
                continue
            if marker.startswith("[LLM_DIALOG_"):
                continue
            if skip_block:
                continue
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _strip_panel_llm_debug_blocks(raw_text: str) -> str:
        return ctrl_strip_panel_llm_debug_blocks(raw_text)

    def _build_system_instruction_prompt_for_submit(self) -> str:
        return ctrl_build_system_instruction_prompt_for_submit(self)

    def _append_system_instruction_text(self, text: str) -> None:
        ctrl_append_system_instruction_text(self, text)

    def _append_ai_analysis_text(self, text: str) -> None:
        ctrl_append_ai_analysis_text(self, text)

    @staticmethod
    def _append_text_to_widget(widget: ScrolledText, text: str) -> None:
        ctrl_append_text_to_widget(widget, text)

    def _set_llm_generation_frozen(self, frozen: bool) -> None:
        ctrl_set_llm_generation_frozen(self, frozen)

    def _append_llm_prompt_block_to_system_instruction(
        self,
        begin_tag: str,
        end_tag: str,
        llm_prompt: str,
    ) -> None:
        ctrl_append_llm_prompt_block_to_system_instruction(self, begin_tag, end_tag, llm_prompt)

    def _append_asr_submit_thinking_chunk(self, chunk: str) -> None:
        ctrl_append_asr_submit_thinking_chunk(self, chunk)

    def _trigger_customer_profile_submit_from_asr(self) -> None:
        ctrl_trigger_customer_profile_submit_from_asr(self)

    def _trigger_customer_profile_submit_from_asr_worker(self, llm_prompt: str) -> None:
        ctrl_trigger_customer_profile_submit_from_asr_worker(self, llm_prompt)

    def _on_customer_profile_submit_from_asr_done(
        self,
        result_text: str,
        thinking_text: str,
        error_text: str,
    ) -> None:
        ctrl_on_customer_profile_submit_from_asr_done(self, result_text, thinking_text, error_text)

    def _append_dialog_output_chunk(self, dialog: dict[str, object], text: str) -> None:
        ctrl_append_dialog_output_chunk(self, dialog, text)

    def _log_llm_prompts(self, kind_label: str, llm_prompt: str) -> None:
        ctrl_log_llm_prompts(self, kind_label, llm_prompt)

    @staticmethod
    def _extract_llm_text(value: object) -> str:
        return svc_extract_llm_text(value)

    def _call_direct_llm_for_system_instruction(
        self,
        llm_prompt: str,
        on_thinking_chunk=None,
        on_content_chunk=None,
    ) -> tuple[str, str]:
        return svc_call_ark_chat_completion(
            llm_prompt=llm_prompt,
            on_thinking_chunk=on_thinking_chunk,
            on_content_chunk=on_content_chunk,
        )

    def _call_deepseek_for_dialog_tasks(
        self,
        llm_prompt: str,
        on_thinking_chunk=None,
        on_content_chunk=None,
    ) -> tuple[str, str]:
        return svc_call_deepseek_chat_completion(
            llm_prompt=llm_prompt,
            on_thinking_chunk=on_thinking_chunk,
            on_content_chunk=on_content_chunk,
        )

    def _refresh_dialog_intent_queue_view(self) -> None:
        ctrl_refresh_intent_queue_view(self)

    def _sync_dialog_intent_strategy_for_active_customer(self) -> None:
        ctrl_sync_intent_strategy_for_active_customer(self)

    def _start_settings_asr(self) -> None:
        ctrl_start_settings_asr(self)

    def _begin_asr_wait(self) -> None:
        ctrl_begin_asr_wait(self)

    def _mark_asr_commit_seen(self) -> None:
        ctrl_mark_asr_commit_seen(self)

    def _check_asr_wait_timeout(self) -> None:
        ctrl_check_asr_wait_timeout(self)

    def _reset_asr_wait(self) -> None:
        ctrl_reset_asr_wait(self)

    def _log_asr_monitor(self, message: str) -> None:
        ctrl_log_asr_monitor(self, message)

    def _is_microphone_open(self) -> bool:
        return ctrl_is_microphone_open(self)

    def _set_microphone_open(self, source: str, opened: bool, reason: str = "") -> None:
        ctrl_set_microphone_open(self, source, opened, reason=reason)

    def _update_microphone_state_from_log(self, source: str, raw_line: str) -> None:
        ctrl_update_microphone_state_from_log(self, source, raw_line)

    def _get_asr_prefix(self, phase: str, ts_text: str) -> str:
        return ctrl_get_asr_prefix(self, phase, ts_text)

    def _start_settings_asr_stream_line(
        self,
        prefix: str,
        phase: str = "partial",
        widget: ScrolledText | None = None,
    ) -> None:
        ctrl_start_settings_asr_stream_line(self, prefix, phase=phase, widget=widget)

    def _replace_settings_asr_stream_text(self, text: str) -> None:
        ctrl_replace_settings_asr_stream_text(self, text)

    def _replace_settings_asr_stream_with_commit(self, ts_text: str, text: str) -> None:
        ctrl_replace_settings_asr_stream_with_commit(self, ts_text, text)

    def _close_settings_asr_stream_line(self) -> None:
        ctrl_close_settings_asr_stream_line(self)

    def _build_runtime_system_prompt(self) -> str:
        return ctrl_build_runtime_system_prompt(self)

    @staticmethod
    def _parse_profile_kv_rows(raw_text: str) -> list[tuple[str, str]]:
        return svc_parse_profile_kv_rows(raw_text)

    def _resolve_customer_jsonl_path(self) -> Path | None:
        return svc_resolve_customer_jsonl_path(
            workspace_dir=self._workspace_dir,
            ui_dir=Path(__file__).resolve().parent,
            cwd=Path.cwd(),
        )

    @staticmethod
    def _build_profile_text_from_slot_items(slot_items: list[object]) -> str:
        return svc_build_profile_text_from_slot_items(slot_items)

    def _pick_random_customer_profile_from_jsonl(self) -> tuple[str, str] | None:
        jsonl_path = self._resolve_customer_jsonl_path()
        if jsonl_path is None:
            messagebox.showerror("文件缺失", "未找到 customer.jsonl，请将其放在工作目录或 UI 目录。")
            return None

        try:
            profile_text = svc_pick_random_customer_profile_from_jsonl_path(jsonl_path)
        except Exception as exc:
            messagebox.showerror("读取失败", f"读取 customer.jsonl 失败：{exc}")
            return None

        if not profile_text:
            messagebox.showwarning("数据为空", "customer.jsonl 中未发现可用 SLOTS 数据。")
            return None

        return profile_text, jsonl_path.name

    @staticmethod
    def _parse_datetime_to_epoch(ts_text: str) -> float:
        return svc_parse_datetime_to_epoch(ts_text)

    def _find_customer_case_file(self, customer_name: str) -> Path | None:
        data_dir = self._get_data_dir()
        safe_name = self._sanitize_filename_component(customer_name)
        candidates = sorted(data_dir.glob(f"{safe_name}_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            return None
        for path in candidates:
            try:
                case_data = self._read_customer_case_file(path)
            except Exception:
                continue
            if str(case_data.get("customer_name", "")).strip() == customer_name:
                return path
        return candidates[0]

    def _build_customer_case_text(
        self,
        customer_name: str,
        created_time: str,
        updated_time: str,
        profile_text: str,
        records: list[dict[str, str]],
    ) -> str:
        lines: list[str] = [
            f"customer_name: {customer_name}",
            f"created_time: {created_time}",
            f"updated_time: {updated_time}",
            "",
            "### 客户画像 ###",
            (profile_text or "").strip(),
            "",
            "### 通话记录条目 ###",
        ]
        for entry in records:
            call_time = str(entry.get("call_time", "") or "").strip()
            call_record = str(entry.get("call_record", "") or "").strip()
            summary = str(entry.get("summary", "") or "").strip()
            commitments = str(entry.get("commitments", "") or "").strip()
            strategy = str(entry.get("strategy", "") or "").strip()
            lines.extend(
                [
                    "",
                    ">>> 记录开始",
                    f"call_time: {call_time}",
                    "### 通话记录 ###",
                    call_record,
                    "",
                    "### 对话总结 ###",
                    summary,
                    "",
                    "### 客户承诺-执行事项 ###",
                    commitments,
                    "",
                    "### 下一步对话策略 ###",
                    strategy,
                    "<<< 记录结束",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"

    def _read_customer_case_file(self, path: Path) -> dict[str, object]:
        return svc_read_customer_case_file(path)

    def _save_customer_case_file(
        self,
        path: Path,
        customer_name: str,
        created_time: str,
        updated_time: str,
        profile_text: str,
        records: list[dict[str, str]],
    ) -> None:
        svc_save_customer_case_file(
            path=path,
            customer_name=customer_name,
            created_time=created_time,
            updated_time=updated_time,
            profile_text=profile_text,
            records=records,
        )

    def _save_new_customer_record(self, profile_text: str, strategy_text: str) -> Path:
        return ctrl_save_new_customer_record(self, profile_text, strategy_text)

    def _create_new_customer_record_from_jsonl(self) -> None:
        ctrl_create_new_customer_record_from_jsonl(self, "")

    def _get_data_dir(self) -> Path:
        return ctrl_get_data_dir(self)

    def _build_new_tab_data_dir(self, tab_title: str) -> Path:
        return ctrl_build_new_tab_data_dir(self, tab_title)

    def _copy_tab_case_files(self, source_dir: Path, target_dir: Path) -> None:
        ctrl_copy_tab_case_files(self, source_dir, target_dir)

    @staticmethod
    def _sanitize_filename_component(text: str) -> str:
        return svc_sanitize_filename_component(text)

    def _extract_customer_name_from_profile_text(self, profile_text: str) -> str:
        return svc_extract_customer_name_from_profile_text(profile_text)

    def _save_dialog_summary_record(
        self,
        summary_content: str,
        strategy_content: str,
        commitments_content: str = "",
    ) -> Path:
        return ctrl_save_dialog_summary_record(self, summary_content, strategy_content, commitments_content)

    def _build_call_record_items(self) -> list[dict[str, str]]:
        return ctrl_build_call_record_items(self)

    def build_visible_customer_records(self, records: list[dict[str, str]]) -> list[dict[str, str]]:
        return ctrl_build_visible_customer_records(self, records)

    def _render_call_record_detail(self, record: dict[str, str]) -> None:
        ctrl_render_call_record_detail(self, record)

    def _clear_call_record_detail(self, message: str = "请选择左侧通话记录") -> None:
        ctrl_clear_call_record_detail(self, message=message)

    def _apply_call_record_profile_and_workflow(self, record: dict[str, str]) -> None:
        ctrl_apply_call_record_profile_and_workflow(self, record)

    def _load_call_records_into_list(self, force_reload: bool = False) -> None:
        ctrl_load_call_records_into_list(self, force_reload=force_reload)

    def _clear_customer_data_profile_table(self, message: str = "请选择左侧通话记录") -> None:
        ctrl_clear_customer_data_profile_table(self, message=message)

    def _clear_customer_data_call_entry_views(self, message: str = "请选择左侧通话记录") -> None:
        ctrl_clear_customer_data_call_entry_views(self, message=message)

    def _render_customer_data_call_entry_views(self, records: list[dict[str, str]]) -> None:
        ctrl_render_customer_data_call_entry_views(self, records)

    def _build_customer_case_cache_by_name(self) -> dict[str, dict[str, object]]:
        return ctrl_build_customer_case_cache_by_name(self)

    def _get_selected_customer_case_data(self, ensure_default_selection: bool = True) -> dict[str, object] | None:
        return ctrl_get_selected_customer_case_data(self, ensure_default_selection=ensure_default_selection)

    def _extract_latest_strategy_from_case_data(self, case_data: dict[str, object]) -> str:
        return ctrl_extract_latest_strategy_from_case_data(self, case_data, default_workflow="")

    def _prepare_call_context_from_customer_data_and_workflow_page(self) -> bool:
        return ctrl_prepare_call_context_from_customer_data_and_workflow_page(self, default_workflow="")

    def _load_customer_data_records_into_list(self, force_reload: bool = False) -> None:
        ctrl_load_customer_data_records_into_list(self, force_reload=force_reload)

    def _mark_conversation_tab_data_dirty(
        self,
        *,
        tab_id: str = "",
        call_records: bool = True,
        customer_data: bool = True,
    ) -> None:
        ctrl_mark_conversation_tab_data_dirty(
            self,
            tab_id=tab_id,
            call_records=call_records,
            customer_data=customer_data,
        )

    def _on_customer_data_record_selected(self, _event=None) -> None:
        ctrl_on_customer_data_record_selected(self, _event=_event)

    def _on_customer_data_tree_click(self, event=None) -> str | None:
        return ctrl_on_customer_data_tree_click(self, event=event)

    def _on_customer_data_tree_double_click(self, event=None) -> str | None:
        return ctrl_on_customer_data_tree_double_click(self, event=event)

    def _delete_customer_by_name(self, customer_name: str) -> None:
        ctrl_delete_customer_by_name(self, customer_name)

    def _open_customer_data_detail_window(
        self,
        customer_name: str,
        *,
        context=None,
        data_dir: Path | None = None,
        case_data: dict[str, object] | None = None,
    ) -> None:
        ctrl_open_customer_data_detail_window(
            self,
            customer_name,
            context=context,
            data_dir=data_dir,
            case_data=case_data,
        )

    def _open_call_record_detail_window(self, record: dict[str, str]) -> None:
        ctrl_open_call_record_detail_window(self, record)

    def _on_call_record_selected(self, _event=None, apply_profile_and_workflow: bool = True) -> None:
        ctrl_on_call_record_selected(self, _event=_event, apply_profile_and_workflow=apply_profile_and_workflow)

    def _on_call_record_tree_click(self, event=None) -> str | None:
        return ctrl_on_call_record_tree_click(self, event=event)

    def _on_call_record_call(self) -> None:
        ctrl_on_call_record_call(self)

    def _resize_profile_table_columns(self, tree: ttk.Treeview) -> None:
        ctrl_resize_profile_table_columns(self, tree)

    def _fill_profile_table_from_text(
        self,
        tree: ttk.Treeview,
        profile_text: str,
        empty_message: str = "暂无客户画像数据",
        auto_height: bool = False,
    ) -> None:
        started_at = time.perf_counter()
        ctrl_fill_profile_table_from_text(
            self,
            tree,
            profile_text,
            empty_message=empty_message,
            auto_height=auto_height,
        )
        self._log_ui_blocking_op(
            "fill_profile_table_from_text",
            started_at,
            extra=f"chars={len(profile_text)} auto_height={int(auto_height)}",
        )

    def _resize_dialog_profile_columns(self) -> None:
        ctrl_resize_dialog_profile_columns(self)

    def _resize_customer_data_profile_columns(self) -> None:
        ctrl_resize_customer_data_profile_columns(self)

    def _refresh_dialog_profile_table(self) -> None:
        ctrl_refresh_dialog_profile_table(self)

    def _refresh_system_instruction(self) -> None:
        ctrl_refresh_system_instruction(self)

    def _refresh_runtime_system_prompt_only(self) -> None:
        ctrl_refresh_runtime_system_prompt_only(self)

    def _on_conversation_workflow_text_edited(self, _event=None) -> None:
        ctrl_on_conversation_workflow_text_edited(self, _event=_event)

    def _reset_runtime_status(self) -> None:
        ctrl_reset_runtime_status(self)

    def _sync_conversation_profile_status(self) -> None:
        ctrl_sync_conversation_profile_status(self)

    @staticmethod
    def _safe_split(command: str) -> list[str]:
        return svc_safe_split_command(command)

    @staticmethod
    def _safe_join(tokens: list[str]) -> str:
        return svc_safe_join_tokens(tokens)

    def _ensure_mic_capture_command(self, command: str) -> str:
        return svc_ensure_mic_capture_command(command, log_monitor=self._log_asr_monitor)

    def _ensure_unbuffered_python_command(self, command: str) -> str:
        tokens = self._safe_split(command)
        if tokens:
            launcher = Path(str(tokens[0]).strip('"')).name.lower()
            if launcher in {"python", "python.exe", "py", "py.exe"} and not bool(getattr(sys, "frozen", False)):
                current_python = str(sys.executable or "").strip()
                if current_python:
                    tokens[0] = current_python
                    command = self._safe_join(tokens)
                    self._log_asr_monitor(f"pinned python launcher to current interpreter: {current_python}")
        return svc_ensure_unbuffered_python_command(command, log_monitor=self._log_asr_monitor)

    def _check_strict_webrtc_readiness(self, command: str) -> tuple[bool, str]:
        if isinstance(getattr(self, "strict_webrtc_required_var", None), tk.BooleanVar):
            if not bool(self.strict_webrtc_required_var.get()):
                return True, "Strict WebRTC preflight skipped by config."
        return svc_check_strict_webrtc_readiness(command=command, cwd=self._workspace_dir)

    @staticmethod
    def _clear_text(widget: ScrolledText) -> None:
        if not isinstance(widget, ScrolledText):
            return
        ctrl_clear_text(widget)

    def _append_line(self, widget: ScrolledText, line: str, max_lines: int = 800) -> None:
        if not isinstance(widget, ScrolledText):
            return
        started_at = time.perf_counter()
        if widget is getattr(self, "log_text", None):
            self._write_time_log_line(line)
            return
        ctrl_append_line(widget, line, max_lines=max_lines)
        self._write_runtime_log_line(line)
        self._log_ui_blocking_op("append_line", started_at, extra=f"chars={len(line)}")

    def _append_line_with_tag(self, widget: ScrolledText, line: str, tag: str, max_lines: int = 800) -> None:
        if not isinstance(widget, ScrolledText):
            return
        started_at = time.perf_counter()
        if widget is getattr(self, "log_text", None):
            self._write_time_log_line(line)
            return
        ctrl_append_line_with_tag(widget, line, tag=tag, max_lines=max_lines)
        self._write_runtime_log_line(line)
        self._log_ui_blocking_op("append_line_with_tag", started_at, extra=f"tag={tag} chars={len(line)}")

    def _set_text_content(self, widget: ScrolledText, text: str) -> None:
        if not isinstance(widget, ScrolledText):
            return
        started_at = time.perf_counter()
        ctrl_set_text_content(widget, text)
        self._log_ui_blocking_op("set_text_content", started_at, extra=f"chars={len(text)}")

    @staticmethod
    def _sanitize_inline_text(text: str) -> str:
        return ctrl_sanitize_inline_text(text)

    @staticmethod
    def _parse_intent_window(text: str) -> tuple[list[str], str]:
        return ctrl_parse_intent_window(text)

    def _append_tts_line(self, role: str, text: str) -> None:
        ctrl_append_tts_line(self, role, text)

    def _start_tts_stream_line(self, prefix: str) -> None:
        ctrl_start_tts_stream_line(self, prefix)

    def _append_tts_stream_text(self, text: str) -> None:
        ctrl_append_tts_stream_text(self, text)

    def _replace_tts_stream_text(self, text: str) -> None:
        ctrl_replace_tts_stream_text(self, text)

    def _close_tts_stream_line(self) -> None:
        ctrl_close_tts_stream_line(self)

    def _append_dialog_conversation_line(self, role: str, text: str) -> None:
        ctrl_append_dialog_conversation_line(self, role, text)

    def _render_dialog_conversation_history(self, text: str, customer_name: str = "") -> None:
        ctrl_render_dialog_conversation_history(self, text, customer_name=customer_name)

    def _append_dialog_session_separator(self) -> None:
        ctrl_append_dialog_session_separator(self)

    def _append_dialog_session_marker(self, marker_text: str, blank_lines_before: int = 5) -> None:
        ctrl_append_dialog_session_marker(self, marker_text, blank_lines_before=blank_lines_before)

    def _extract_dialog_current_session_text(self) -> str:
        return ctrl_extract_dialog_current_session_text(self)

    def _set_dialog_conversation_active_customer(self, customer_name: str) -> None:
        ctrl_set_dialog_conversation_active_customer(self, customer_name)

    def _refresh_dialog_conversation_for_active_customer(self) -> None:
        ctrl_refresh_dialog_conversation_for_active_customer(self)

    def _append_dialog_customer_intent(self, customer_text: str, intent_summary: str) -> None:
        ctrl_append_dialog_customer_intent(self, customer_text, intent_summary)

    def _start_dialog_agent_stream_line(self, prefix: str) -> None:
        ctrl_start_dialog_agent_stream_line(self, prefix)

    def _append_dialog_agent_stream_text(self, text: str) -> None:
        ctrl_append_dialog_agent_stream_text(self, text)

    def _replace_dialog_agent_stream_text(self, text: str) -> None:
        ctrl_replace_dialog_agent_stream_text(self, text)

    def _close_dialog_agent_stream_line(self) -> None:
        ctrl_close_dialog_agent_stream_line(self)

    def _start_asr_stream_line(self, prefix: str) -> None:
        ctrl_start_asr_stream_line(self, prefix)

    def _replace_asr_stream_text(self, text: str) -> None:
        ctrl_replace_asr_stream_text(self, text)
 
    def _close_asr_stream_line(self, tag: str = "") -> None:
        ctrl_close_asr_stream_line(self, tag=tag)

    def _trim_scrolled_text(self, widget: ScrolledText, max_lines: int = 800) -> None:
        started_at = time.perf_counter()
        ctrl_trim_scrolled_text(widget, max_lines=max_lines)
        self._log_ui_blocking_op("trim_scrolled_text", started_at, extra=f"max_lines={max_lines}")

    def _log_ui_blocking_op(self, label: str, started_at: float, *, threshold_ms: float = 50.0, extra: str = "") -> None:
        if not bool(getattr(self, "_debug_ui_block_logging", False)):
            return
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if elapsed_ms < threshold_ms:
            return
        suffix = f" {extra}" if extra else ""
        line = f"[UI_BLOCK] {label} {elapsed_ms:.1f}ms{suffix}"
        self._write_runtime_log_line(line)
        workspace_dir = getattr(self, "_workspace_dir", None)
        if isinstance(workspace_dir, Path):
            try:
                log_dir = workspace_dir / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                self._queue_async_log_write(log_dir / "ui_blocking.log", line)
            except Exception:
                pass
        self._write_time_log_line(line)

    def _start_ui_heartbeat_monitor(self, interval_ms: int = 50, warn_drift_ms: float = 120.0) -> None:
        expected_next = time.perf_counter() + (interval_ms / 1000.0)

        def _tick() -> None:
            nonlocal expected_next
            now = time.perf_counter()
            drift_ms = (now - expected_next) * 1000.0
            if drift_ms >= warn_drift_ms:
                self._log_ui_blocking_op("ui_heartbeat_drift", now - (drift_ms / 1000.0), threshold_ms=warn_drift_ms, extra=f"interval={interval_ms}")
            expected_next = now + (interval_ms / 1000.0)
            try:
                self.after(interval_ms, _tick)
            except Exception:
                pass

        try:
            self.after(interval_ms, _tick)
        except Exception:
            pass

    def _open_runtime_log_file(self) -> None:
        self._close_runtime_log_file()
        ts = datetime.now()
        log_dir = self._runtime_log_dir
        file_path = log_dir / f"session_{ts.strftime('%Y%m%d_%H%M%S_%f')}.log"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            self._runtime_log_file_path = file_path
        except Exception as exc:
            self._runtime_log_file_path = None
            self._log_asr_monitor(f"log_file_open_failed: {exc}")
            return
        self._write_runtime_log_line(f"# session_started_at={ts.isoformat(timespec='seconds')}")
        self._write_runtime_log_line(f"# session_log_path={file_path}")
        self._append_line(self.log_text, f"[{ts.strftime('%H:%M:%S')}] [LOG_FILE] {file_path}")

    def _write_runtime_log_line(self, line: str) -> None:
        if not line:
            return
        file_path = self._runtime_log_file_path
        if not isinstance(file_path, Path):
            return
        self._queue_async_log_write(file_path, line)

    def _write_runtime_log_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        for line in lines:
            self._write_runtime_log_line(line)

    def _close_runtime_log_file(self) -> None:
        self._runtime_log_file_path = None
 
    def _queue_async_log_write(self, file_path: Path, line: str) -> None:
        if not line:
            return
        try:
            self._async_log_queue.put_nowait((file_path, line))
        except Exception:
            pass

    def _async_log_writer_loop(self) -> None:
        while True:
            item = self._async_log_queue.get()
            if item is None:
                self._async_log_queue.task_done()
                break
            file_path, line = item
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with file_path.open("a", encoding="utf-8") as fp:
                    fp.write(line + "\n")
            except Exception:
                pass
            finally:
                self._async_log_queue.task_done()
        self._async_log_writer_stop.set()

    def _close_async_log_writer(self) -> None:
        if not self._async_log_writer_thread.is_alive():
            return
        try:
            self._async_log_queue.put_nowait(None)
        except Exception:
            pass
        try:
            self._async_log_queue.join()
        except Exception:
            pass
        self._async_log_writer_stop.wait(timeout=1.0)

    def _write_time_log_line(self, line: str) -> None:
        if not line:
            return
        self._queue_async_log_write(self._time_log_file_path, line)

    def _write_time_log_lines(self, lines: list[str]) -> None:
        for line in lines:
            self._write_time_log_line(line)

    def _refresh_time_log_view(self) -> None:
        widget = getattr(self, "log_text", None)
        file_path = getattr(self, "_time_log_file_path", None)
        if (not isinstance(widget, ScrolledText)) or (not isinstance(file_path, Path)):
            return
        if not file_path.exists():
            return
        try:
            current_size = file_path.stat().st_size
        except Exception:
            return
        if self._time_log_read_offset > current_size:
            self._time_log_read_offset = 0
        try:
            with file_path.open("r", encoding="utf-8") as fp:
                fp.seek(self._time_log_read_offset)
                chunk = fp.read()
                self._time_log_read_offset = fp.tell()
        except Exception:
            return
        if not chunk:
            return
        widget.configure(state="normal")
        widget.insert("end", chunk)
        self._trim_scrolled_text(widget, max_lines=TIME_LOG_MAX_LINES)
        widget.configure(state="disabled")
        widget.see("end")


def main() -> None:
    _enable_windows_dpi_awareness()
    app = MicChunkUiApp()
    app.mainloop()


if __name__ == "__main__":
    main()
