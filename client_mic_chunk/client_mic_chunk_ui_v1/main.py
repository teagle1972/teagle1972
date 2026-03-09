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
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, LEFT, RIGHT, X, Y, messagebox
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable, Iterator, TextIO

import requests

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
    from .controllers.editor_dialog import (
        build_dialog_llm_prompt as ctrl_build_dialog_llm_prompt,
        close_settings_editor_dialog as ctrl_close_settings_editor_dialog,
        on_editor_dialog_submit_done as ctrl_on_editor_dialog_submit_done,
        open_settings_editor_dialog as ctrl_open_settings_editor_dialog,
        poll_editor_dialog_events as ctrl_poll_editor_dialog_events,
        submit_editor_dialog as ctrl_submit_editor_dialog,
        submit_editor_dialog_worker as ctrl_submit_editor_dialog_worker,
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
        DEFAULT_DIALOG_SUMMARY_PROMPT_TEMPLATE,
        DEFAULT_NEXT_DIALOG_STRATEGY_PROMPT_TEMPLATE,
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
        clear_call_record_detail as ctrl_clear_call_record_detail,
        clear_customer_data_call_entry_views as ctrl_clear_customer_data_call_entry_views,
        clear_customer_data_profile_table as ctrl_clear_customer_data_profile_table,
        extract_latest_strategy_from_case_data as ctrl_extract_latest_strategy_from_case_data,
        get_selected_customer_case_data as ctrl_get_selected_customer_case_data,
        load_call_records_into_list as ctrl_load_call_records_into_list,
        load_customer_data_records_into_list as ctrl_load_customer_data_records_into_list,
        on_call_record_call as ctrl_on_call_record_call,
        on_call_record_selected as ctrl_on_call_record_selected,
        on_customer_data_record_selected as ctrl_on_customer_data_record_selected,
        on_customer_data_tree_click as ctrl_on_customer_data_tree_click,
        on_customer_data_tree_double_click as ctrl_on_customer_data_tree_double_click,
        open_call_record_detail_window as ctrl_open_call_record_detail_window,
        prepare_call_context_from_customer_data_and_workflow_page as ctrl_prepare_call_context_from_customer_data_and_workflow_page,
        render_call_record_detail as ctrl_render_call_record_detail,
        render_customer_data_call_entry_views as ctrl_render_customer_data_call_entry_views,
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
except Exception:
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
        DEFAULT_DIALOG_SUMMARY_PROMPT_TEMPLATE,
        DEFAULT_NEXT_DIALOG_STRATEGY_PROMPT_TEMPLATE,
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
        clear_call_record_detail as ctrl_clear_call_record_detail,
        clear_customer_data_call_entry_views as ctrl_clear_customer_data_call_entry_views,
        clear_customer_data_profile_table as ctrl_clear_customer_data_profile_table,
        extract_latest_strategy_from_case_data as ctrl_extract_latest_strategy_from_case_data,
        get_selected_customer_case_data as ctrl_get_selected_customer_case_data,
        load_call_records_into_list as ctrl_load_call_records_into_list,
        load_customer_data_records_into_list as ctrl_load_customer_data_records_into_list,
        on_call_record_call as ctrl_on_call_record_call,
        on_call_record_selected as ctrl_on_call_record_selected,
        on_customer_data_record_selected as ctrl_on_customer_data_record_selected,
        on_customer_data_tree_click as ctrl_on_customer_data_tree_click,
        on_customer_data_tree_double_click as ctrl_on_customer_data_tree_double_click,
        open_call_record_detail_window as ctrl_open_call_record_detail_window,
        prepare_call_context_from_customer_data_and_workflow_page as ctrl_prepare_call_context_from_customer_data_and_workflow_page,
        render_call_record_detail as ctrl_render_call_record_detail,
        render_customer_data_call_entry_views as ctrl_render_customer_data_call_entry_views,
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

AUDIO_TUNING_SPECS: tuple[dict[str, object], ...] = (
    {
        "key": "chunk_ms",
        "label": "chunk_ms",
        "flag": "--chunk-ms",
        "default": "20",
        "type": "int",
        "min": 10,
        "max": 60,
        "unit": "ms",
        "desc": "麦克风分片时长",
    },
    {
        "key": "queue_size",
        "label": "queue_size",
        "flag": "--queue-size",
        "default": "128",
        "type": "int",
        "min": 64,
        "max": 512,
        "unit": "chunks",
        "desc": "发送队列容量",
    },
    {
        "key": "aec_ref_delay_ms",
        "label": "aec_ref_delay_ms",
        "flag": "--aec-ref-delay-ms",
        "default": "160",
        "type": "int",
        "min": 0,
        "max": 500,
        "unit": "ms",
        "desc": "AEC参考延迟",
    },
    {
        "key": "aec_max_suppress_gain",
        "label": "aec_max_suppress_gain",
        "flag": "--aec-max-suppress-gain",
        "default": "1.6",
        "type": "float",
        "min": 1.0,
        "max": 3.0,
        "unit": "ratio",
        "desc": "回声抑制增益上限",
    },
    {
        "key": "aec_near_end_protect_ratio",
        "label": "aec_near_end_protect_ratio",
        "flag": "--aec-near-end-protect-ratio",
        "default": "1.16",
        "type": "float",
        "min": 1.0,
        "max": 1.5,
        "unit": "ratio",
        "desc": "近端语音保护阈值",
    },
    {
        "key": "aec_tts_warmup_mute_ms",
        "label": "aec_tts_warmup_mute_ms",
        "flag": "--aec-tts-warmup-mute-ms",
        "default": "20",
        "type": "int",
        "min": 0,
        "max": 300,
        "unit": "ms",
        "desc": "TTS起播静音窗口",
    },
    {
        "key": "aec_tts_ref_wait_mute_ms",
        "label": "aec_tts_ref_wait_mute_ms",
        "flag": "--aec-tts-ref-wait-mute-ms",
        "default": "600",
        "type": "int",
        "min": 200,
        "max": 3000,
        "unit": "ms",
        "desc": "参考信号等待静音窗口",
    },
)

ASR_FIRST_PROFILE_OVERRIDES: dict[str, str] = {
    "queue_size": "128",
    "aec_ref_delay_ms": "160",
    "aec_max_suppress_gain": "1.6",
    "aec_near_end_protect_ratio": "1.16",
    "aec_tts_warmup_mute_ms": "20",
    "aec_tts_ref_wait_mute_ms": "600",
}
AGGRESSIVE_PROFILE_OVERRIDES: dict[str, str] = {
    "aec_max_suppress_gain": "2.4",
    "aec_near_end_protect_ratio": "1.18",
    "aec_tts_warmup_mute_ms": "120",
    "aec_tts_ref_wait_mute_ms": "2200",
}
RUNTIME_AUDIO_CONFIG_FILENAME = "_ui_audio_config.json"


@dataclass
class ConversationTabContext:
    tab_id: str
    title: str
    tab_frame: ttk.Frame
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
    dialog_intent_queue_text: ScrolledText | None
    dialog_strategy_text: ScrolledText | None
    conversation_workflow_text: ScrolledText | None
    conversation_strategy_history_text: ScrolledText | None
    conversation_strategy_input_text: tk.Text | None
    conversation_system_instruction_text: ScrolledText | None
    conversation_intent_text: ScrolledText | None
    conversation_customer_profile_text: ScrolledText | None
    conversation_summary_prompt_text: ScrolledText | None
    conversation_strategy_prompt_text: ScrolledText | None
    call_record_tree: ttk.Treeview | None
    call_record_summary_text: ScrolledText | None
    call_record_commitments_text: ScrolledText | None
    call_record_strategy_text: ScrolledText | None
    customer_data_record_tree: ttk.Treeview | None
    customer_data_profile_table: ttk.Treeview | None
    customer_data_calls_canvas: tk.Canvas | None
    customer_data_calls_container: ttk.Frame | None
    customer_data_call_entries_wrap: ttk.Frame | None
    call_record_item_by_iid: dict[str, dict[str, str]] = field(default_factory=dict)
    customer_data_customer_by_iid: dict[str, str] = field(default_factory=dict)
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
        self._event_history: list[dict] = []

        self._send_count = 0
        self._send_total_ms = 0
        self._control_endpoint = ""
        self._media_endpoint = ""
        self._single_endpoint = ""
        self._tts_stream_content_start = ""
        self._tts_stream_active = False
        self._asr_stream_content_start = ""
        self._asr_stream_active = False
        self._asr_history_lines: list[str] = []
        self._asr_wait_since = 0.0
        self._asr_first_commit_seen = False
        self._asr_wait_warned = False
        self._main_mic_open = False
        self._settings_mic_open = False
        self._dialog_agent_stream_active = False
        self._dialog_agent_stream_content_start = ""
        self._settings_asr_stream_active = False
        self._settings_asr_stream_phase = ""
        self._settings_asr_stream_line_start = ""
        self._settings_asr_stream_content_start = ""
        self._settings_asr_stream_widget: ScrolledText | None = None
        self._asr_submit_thinking_seen = False
        self._llm_submit_running = False
        self._llm_freeze_depth = 0
        self._llm_freeze_widget_style: dict[tk.Text, tuple[str, str, str, str]] = {}
        self._runtime_system_prompt = ""
        self._loaded_workflow_json_text = ""
        self._loaded_workflow_json_path = ""
        self._loaded_workflow_json_nodes = 0
        self._loaded_workflow_json_edges = 0
        self._loaded_workflow_payload: dict[str, object] | None = None
        self._flow_active_node_id = ""
        self._flow_hover_node_id = ""
        self._flow_tooltip_window: tk.Toplevel | None = None
        self._flow_tooltip_label: tk.Label | None = None
        self._editor_dialogs: list[dict[str, object]] = []
        self._event_backlog_high: deque[UiEvent] = deque()
        self._event_backlog_normal: deque[UiEvent] = deque()
        self._settings_event_backlog: deque[UiEvent] = deque()
        self._pending_log_lines: list[str] = []
        self._next_log_flush_at = 0.0
        self._send_done_summary_second = ""
        self._send_done_summary_count = 0
        self._send_done_summary_first_chunk = 0
        self._send_done_summary_last_chunk = 0
        self._send_done_summary_total_ms = 0
        self._send_done_summary_max_ms = 0
        self._send_done_summary_deadline = 0.0

        self._workspace_dir = Path(__file__).resolve().parent.parent
        self._runtime_log_dir = self._workspace_dir / "logs"
        self._runtime_log_file_path: Path | None = None
        self._runtime_log_file: TextIO | None = None
        self._default_command = FIXED_STARTUP_COMMAND
        self._settings_asr_command = FIXED_STARTUP_COMMAND
        self._runtime_audio_config_path = self._workspace_dir / RUNTIME_AUDIO_CONFIG_FILENAME
        self.flow_editor_panel: FlowEditorPanel | None = None
        self.flow_monitor_canvas: FlowCanvas | None = None
        self.flow_panes: ttk.Panedwindow | None = None
        self.flow_json_box: ttk.LabelFrame | None = None
        self._audio_config_loaded = False
        self.customer_profile_text: ScrolledText | None = None
        self.workflow_text: ScrolledText | None = None
        self.system_instruction_text: ScrolledText | None = None
        self.ai_analysis_text: ScrolledText | None = None
        self.call_record_tree: ttk.Treeview | None = None
        self.customer_data_record_tree: ttk.Treeview | None = None
        self.call_record_summary_text: ScrolledText | None = None
        self.call_record_commitments_text: ScrolledText | None = None
        self.call_record_strategy_text: ScrolledText | None = None
        self.customer_data_profile_table: ttk.Treeview | None = None
        self.customer_data_calls_canvas: tk.Canvas | None = None
        self.customer_data_calls_container: ttk.Frame | None = None
        self.customer_data_call_entries_wrap: ttk.Frame | None = None
        self.asr_text: ScrolledText | None = None
        self.asr_commit_text: ScrolledText | None = None
        self.tts_text: ScrolledText | None = None
        self.nlp_input_text: ScrolledText | None = None
        self.dialog_intent_text: ScrolledText | None = None
        self.dialog_intent_queue_text: ScrolledText | None = None
        self.dialog_strategy_text: ScrolledText | None = None
        self._dialog_intent_history: list[str] = []
        self._dialog_intent_state_by_customer: dict[str, dict[str, list[str]]] = {}
        self._dialog_intent_state_current_customer_key: str = ""
        self._current_session_customer_lines: list[str] = []
        self._current_session_dialog_lines: list[str] = []
        self.intent_text: ScrolledText | None = None
        self.intent_system_text: ScrolledText | None = None
        self.intent_prompt_text: ScrolledText | None = None
        self.profile_call_btn: ttk.Button | None = None
        self.conversation_profile_status_var: tk.StringVar | None = None
        self.conversation_profile_status_label: tk.Label | None = None
        self.monitor_process_status_label: tk.Label | None = None
        self.conversation_workflow_text: ScrolledText | None = None
        self.conversation_strategy_history_text: ScrolledText | None = None
        self.conversation_strategy_input_text: tk.Text | None = None
        self.conversation_system_instruction_text: ScrolledText | None = None
        self.conversation_intent_text: ScrolledText | None = None
        self.conversation_customer_profile_text: ScrolledText | None = None
        self.conversation_summary_prompt_text: ScrolledText | None = None
        self.conversation_strategy_prompt_text: ScrolledText | None = None
        self._dialog_summary_prompt_template_cache: str = DEFAULT_DIALOG_SUMMARY_PROMPT_TEMPLATE
        self._dialog_strategy_prompt_template_cache: str = DEFAULT_NEXT_DIALOG_STRATEGY_PROMPT_TEMPLATE
        self._prompt_templates_path = self._workspace_dir / "_prompt_templates.json"
        self._load_prompt_templates_from_file()
        self._conversation_workflow_syncing = False
        self._conversation_strategy_history: list[dict[str, str]] = []
        self._conversation_customer_profile_history: list[dict[str, str]] = []
        self._conversation_intent_generator_history: list[dict[str, str]] = []
        self._dialog_conversation_history_by_customer: dict[str, list[dict[str, str]]] = {}
        self._dialog_conversation_active_customer_key = ""
        self._call_record_item_by_iid: dict[str, dict[str, str]] = {}
        self._customer_data_customer_by_iid: dict[str, str] = {}
        self._customer_data_case_cache_by_name: dict[str, dict[str, object]] = {}
        self._customer_data_last_render_key = ""
        self._conversation_page_switcher = None
        self._main_notebook: ttk.Notebook | None = None
        self._conversation_tabs: dict[str, ConversationTabContext] = {}
        self._conversation_tab_id_by_frame_name: dict[str, str] = {}
        self._conversation_template_tab_id = ""
        self._active_conversation_tab_id = ""
        self._bound_conversation_tab_id = ""
        self._runtime_conversation_tab_id = ""
        self._conversation_tab_counter = 0
        self._tab_data_dir_override: Path | None = None
        self._conversation_tab_registry_tree: ttk.Treeview | None = None
        self._conversation_tab_registry_iid_to_tab_id: dict[str, str] = {}
        self._suspend_tab_registry_save = False
        self._snapshot_autosave_after_id: str | None = None
        self._snapshot_autosave_interval_ms = 3000
        self._conversation_strategy_dialog: dict[str, object] | None = None
        self._conversation_customer_profile_dialog: dict[str, object] | None = None
        self._conversation_intent_dialog: dict[str, object] | None = None

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

    def _build_variables(self) -> None:
        initial_env = str(os.getenv("MIC_CHUNK_SERVER_ENV", "local") or "").strip().lower()
        if initial_env not in {"local", "public"}:
            initial_env = "local"
        profile = self._normalize_aec_profile(os.getenv("MIC_CHUNK_AEC_PROFILE", "asr_first"))
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

    @staticmethod
    def _normalize_aec_profile(raw: str | None) -> str:
        profile = str(raw or "asr_first").strip().lower()
        if profile not in {"asr_first", "aggressive"}:
            return "asr_first"
        return profile

    def _get_profile_tuning_defaults(self, profile: str) -> dict[str, str]:
        normalized = self._normalize_aec_profile(profile)
        values = {str(spec["key"]): str(spec["default"]) for spec in AUDIO_TUNING_SPECS}
        if normalized == "aggressive":
            values.update(AGGRESSIVE_PROFILE_OVERRIDES)
        else:
            values.update(ASR_FIRST_PROFILE_OVERRIDES)
        return values

    @staticmethod
    def _format_numeric_for_option(value: float, value_type: str) -> str:
        if value_type == "int":
            return str(int(value))
        text = f"{float(value):.3f}".rstrip("0").rstrip(".")
        return text or "0"

    @staticmethod
    def _remove_command_option(tokens: list[str], flag: str) -> None:
        i = 0
        while i < len(tokens):
            token = str(tokens[i] or "")
            if token == flag:
                del tokens[i]
                if i < len(tokens):
                    nxt = str(tokens[i] or "")
                    if nxt and (not nxt.startswith("--")):
                        del tokens[i]
                continue
            if token.startswith(f"{flag}="):
                del tokens[i]
                continue
            i += 1

    @staticmethod
    def _read_command_option(tokens: list[str], flag: str) -> str:
        for idx, token in enumerate(tokens):
            token_text = str(token or "").strip()
            if token_text == flag:
                if idx + 1 >= len(tokens):
                    return ""
                value = str(tokens[idx + 1] or "").strip()
                if value.startswith("--"):
                    return ""
                return value
            if token_text.startswith(f"{flag}="):
                return token_text.split("=", 1)[1].strip()
        return ""

    def _set_audio_config_status(self, text: str) -> None:
        if isinstance(getattr(self, "audio_config_status_var", None), tk.StringVar):
            self.audio_config_status_var.set(str(text or "").strip() or "-")

    def _load_audio_config_from_command_text(self, command_text: str, update_status: bool = True) -> None:
        tokens = self._safe_split(command_text)
        if not tokens:
            return
        for spec in AUDIO_TUNING_SPECS:
            key = str(spec["key"])
            flag = str(spec["flag"])
            current = self._read_command_option(tokens, flag)
            if not current:
                continue
            var = getattr(self, f"audio_{key}_var", None)
            if isinstance(var, tk.StringVar):
                var.set(current)
        if update_status:
            self._set_audio_config_status("已从当前启动命令回填参数")

    def _load_audio_config_from_current_command(self, update_status: bool = True) -> None:
        command_text = (self.command_var.get() or "").strip()
        if not command_text:
            command_text = (self.conversation_command_var.get() or "").strip()
        self._load_audio_config_from_command_text(command_text, update_status=update_status)

    def _reset_audio_config_defaults_for_profile(self, apply_profile_overrides: bool = True, update_status: bool = True) -> None:
        profile = self._normalize_aec_profile(self.aec_profile_var.get())
        self.aec_profile_var.set(profile)
        defaults = self._get_profile_tuning_defaults(profile if apply_profile_overrides else "asr_first")
        for key, value in defaults.items():
            var = getattr(self, f"audio_{key}_var", None)
            if isinstance(var, tk.StringVar):
                var.set(str(value))
        if update_status:
            profile_label = "ASR优先" if profile == "asr_first" else "增强抑制"
            self._set_audio_config_status(f"已恢复默认值（{profile_label}）")

    def _reset_audio_config_defaults(self) -> None:
        self._reset_audio_config_defaults_for_profile(apply_profile_overrides=True, update_status=True)

    def _collect_validated_audio_tuning_values(self, *, show_error: bool) -> dict[str, str] | None:
        values: dict[str, str] = {}
        for spec in AUDIO_TUNING_SPECS:
            key = str(spec["key"])
            label = str(spec["label"])
            value_type = str(spec["type"])
            min_value = float(spec["min"])
            max_value = float(spec["max"])
            unit = str(spec["unit"])
            var = getattr(self, f"audio_{key}_var", None)
            raw = str(var.get() if isinstance(var, tk.StringVar) else "").strip()
            if not raw:
                raw = str(spec["default"])
            try:
                if value_type == "int":
                    parsed = float(int(raw))
                else:
                    parsed = float(raw)
            except Exception:
                if show_error:
                    messagebox.showerror(
                        "参数格式错误",
                        f"{label} 必须是数字，单位 {unit}，范围 {self._format_numeric_for_option(min_value, value_type)} ~ {self._format_numeric_for_option(max_value, value_type)}。",
                    )
                return None
            if (parsed < min_value) or (parsed > max_value):
                if show_error:
                    messagebox.showerror(
                        "参数超出范围",
                        f"{label} 超出范围，单位 {unit}，允许 {self._format_numeric_for_option(min_value, value_type)} ~ {self._format_numeric_for_option(max_value, value_type)}。",
                    )
                return None
            normalized = self._format_numeric_for_option(parsed, value_type)
            if isinstance(var, tk.StringVar):
                var.set(normalized)
            values[key] = normalized
        return values

    def _apply_audio_tuning_values_to_command(self, command_text: str, values: dict[str, str]) -> str:
        command = str(command_text or "").strip()
        if not command:
            return command
        tokens = self._safe_split(command)
        if not tokens:
            return command
        for spec in AUDIO_TUNING_SPECS:
            key = str(spec["key"])
            flag = str(spec["flag"])
            value = values.get(key, "")
            if not value:
                continue
            self._remove_command_option(tokens, flag)
            tokens.extend([flag, value])
        return self._safe_join(tokens)

    def _build_runtime_audio_config_payload(self, values: dict[str, str]) -> dict[str, object]:
        return {
            "strict_webrtc_required": bool(self.strict_webrtc_required_var.get()),
            "aec_profile": self._normalize_aec_profile(self.aec_profile_var.get()),
            "audio_tuning": values,
        }

    def _save_runtime_audio_config(self, values: dict[str, str] | None = None, *, silent: bool = False) -> bool:
        payload_values = values if isinstance(values, dict) else self._collect_validated_audio_tuning_values(show_error=not silent)
        if not isinstance(payload_values, dict):
            return False
        payload = self._build_runtime_audio_config_payload(payload_values)
        try:
            self._runtime_audio_config_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            if not silent:
                messagebox.showerror("保存失败", f"参数配置保存失败：{exc}")
            return False
        return True

    def _load_runtime_audio_config(self) -> bool:
        path = self._runtime_audio_config_path
        if not path.exists():
            self._set_audio_config_status("未发现已保存配置，已加载默认值")
            return False
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._set_audio_config_status(f"配置文件读取失败，已使用默认值: {exc}")
            return False
        if not isinstance(raw, dict):
            self._set_audio_config_status("配置文件格式异常，已使用默认值")
            return False
        self.strict_webrtc_required_var.set(bool(raw.get("strict_webrtc_required", True)))
        profile = self._normalize_aec_profile(str(raw.get("aec_profile", self.aec_profile_var.get()) or "asr_first"))
        self.aec_profile_var.set(profile)
        tuning_raw = raw.get("audio_tuning", {})
        defaults = self._get_profile_tuning_defaults(profile)
        if isinstance(tuning_raw, dict):
            for key, value in tuning_raw.items():
                key_text = str(key)
                if key_text in defaults:
                    defaults[key_text] = str(value)
        for key, value in defaults.items():
            var = getattr(self, f"audio_{key}_var", None)
            if isinstance(var, tk.StringVar):
                var.set(str(value))
        os.environ["MIC_CHUNK_AEC_PROFILE"] = profile
        self._set_audio_config_status(f"已加载参数配置: {path.name}")
        return True

    def _apply_audio_config_to_commands(
        self,
        *,
        save_config: bool = True,
        update_status: bool = True,
        show_error: bool = True,
    ) -> bool:
        values = self._collect_validated_audio_tuning_values(show_error=show_error)
        if values is None:
            return False
        profile = self._normalize_aec_profile(self.aec_profile_var.get())
        self.aec_profile_var.set(profile)
        os.environ["MIC_CHUNK_AEC_PROFILE"] = profile
        startup_command = str(self._default_command or FIXED_STARTUP_COMMAND).strip() or FIXED_STARTUP_COMMAND
        startup_command = self._apply_audio_tuning_values_to_command(startup_command, values)
        self.command_var.set(startup_command)
        self.conversation_command_var.set(startup_command)
        self._apply_server_env_to_command()
        self._apply_server_env_to_conversation_command()
        settings_asr_command = str(self.command_var.get() or startup_command).strip()
        self.settings_asr_command_var.set(settings_asr_command)
        self._settings_asr_command = settings_asr_command
        if save_config:
            if not self._save_runtime_audio_config(values, silent=False):
                return False
        if update_status:
            self._set_audio_config_status("参数已应用并保存")
        return True

    def _save_audio_config_from_ui(self) -> None:
        values = self._collect_validated_audio_tuning_values(show_error=True)
        if values is None:
            return
        profile = self._normalize_aec_profile(self.aec_profile_var.get())
        self.aec_profile_var.set(profile)
        os.environ["MIC_CHUNK_AEC_PROFILE"] = profile
        self._settings_asr_command = str(self.settings_asr_command_var.get() or self._settings_asr_command or "").strip()
        ok = self._save_runtime_audio_config(values, silent=False)
        if ok:
            self._set_audio_config_status("参数配置已保存")

    def _build_conversation_tab(
        self,
        parent: ttk.Frame,
        panel_bg: str,
        tab_title: str,
        command_value: str,
        env_value: str,
    ) -> ConversationTabContext:
        return ctrl_build_conversation_tab(
            self,
            parent,
            panel_bg,
            tab_title,
            command_value,
            env_value,
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
    ) -> str | None:
        return ctrl_create_conversation_tab_internal(
            self,
            tab_title,
            source_tab_id,
            data_dir=data_dir,
            copy_source_data=copy_source_data,
            select_new_tab=select_new_tab,
            persist=persist,
        )

    def _create_conversation_tab_from_settings(self) -> None:
        ctrl_create_conversation_tab_from_settings(self)

    def _resolve_whoami_base_url(self) -> str:
        command = (
            self.conversation_command_var.get().strip()
            or self.command_var.get().strip()
            or FIXED_STARTUP_COMMAND
        )
        tokens = self._safe_split(command)
        env = (self.conversation_server_env_var.get() or self.server_env_var.get() or "local").strip().lower()
        if env not in {"local", "public"}:
            env = "local"
        base_url = ""
        local_base_url = WHOAMI_LOCAL_BASE_URL
        public_base_url = WHOAMI_PUBLIC_BASE_URL
        i = 0
        while i < len(tokens):
            token = str(tokens[i]).strip()
            if token == "--server-env" and (i + 1) < len(tokens):
                value = str(tokens[i + 1]).strip().lower()
                if value in {"local", "public"}:
                    env = value
                i += 2
                continue
            if token == "--base-url" and (i + 1) < len(tokens):
                base_url = str(tokens[i + 1]).strip()
                i += 2
                continue
            if token == "--local-base-url" and (i + 1) < len(tokens):
                local_base_url = str(tokens[i + 1]).strip() or local_base_url
                i += 2
                continue
            if token == "--public-base-url" and (i + 1) < len(tokens):
                public_base_url = str(tokens[i + 1]).strip() or public_base_url
                i += 2
                continue
            i += 1
        resolved = base_url or (public_base_url if env == "public" else local_base_url)
        resolved = resolved.strip()
        if resolved.startswith("ws://"):
            resolved = "http://" + resolved[len("ws://") :]
        elif resolved.startswith("wss://"):
            resolved = "https://" + resolved[len("wss://") :]
        return resolved.rstrip("/")

    def _request_whoami_from_settings(self) -> None:
        base_url = self._resolve_whoami_base_url()
        if not base_url:
            messagebox.showerror("Whoami失败", "无法解析服务端地址。")
            return
        url = f"{base_url}/debug/whoami"
        ts_text = datetime.now().strftime("%H:%M:%S")
        self._append_line(self.log_text, f"[{ts_text}] [WHOAMI] request {url}")
        try:
            resp = requests.get(url, timeout=5.0)
            body_text = (resp.text or "").strip()
            payload: dict[str, object]
            try:
                parsed = resp.json()
                payload = parsed if isinstance(parsed, dict) else {"body": parsed}
            except Exception:
                payload = {"body": body_text[:800]}
            payload["status_code"] = resp.status_code
            self._append_line(
                self.log_text,
                f"[{ts_text}] [WHOAMI] response {json.dumps(payload, ensure_ascii=False)}",
            )
            host = str(payload.get("host", "") or "")
            pid = str(payload.get("pid", "") or "")
            revision = str(payload.get("revision", "") or "")
            log_dir = str(payload.get("log_dir", "") or "")
            log_file = str(payload.get("log_file", "") or "")
            messagebox.showinfo(
                "Whoami",
                (
                    f"host: {host}\n"
                    f"pid: {pid}\n"
                    f"revision: {revision}\n"
                    f"log_dir: {log_dir}\n"
                    f"log_file: {log_file}"
                ),
            )
        except Exception as exc:
            self._append_line(self.log_text, f"[{ts_text}] [WHOAMI] failed: {exc}")
            messagebox.showerror("Whoami失败", str(exc))

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

    def _save_persisted_conversation_tab_snapshots(self) -> None:
        ctrl_save_persisted_conversation_tab_snapshots(self)

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
        self._send_done_summary_second = ""
        self._send_done_summary_count = 0
        self._send_done_summary_first_chunk = 0
        self._send_done_summary_last_chunk = 0
        self._send_done_summary_total_ms = 0
        self._send_done_summary_max_ms = 0
        self._send_done_summary_deadline = 0.0

    def _flush_send_done_summary(self, force: bool = False) -> None:
        if self._send_done_summary_count <= 0:
            return
        if (not force) and time.monotonic() < self._send_done_summary_deadline:
            return

        avg_ms = self._send_done_summary_total_ms / max(self._send_done_summary_count, 1)
        if self._send_done_summary_count == 1:
            line = (
                f"[{self._send_done_summary_second}] "
                f"[send] chunk={self._send_done_summary_last_chunk} done in {int(avg_ms)}ms"
            )
        else:
            line = (
                f"[{self._send_done_summary_second}] [send] "
                f"chunks={self._send_done_summary_first_chunk}-{self._send_done_summary_last_chunk} "
                f"count={self._send_done_summary_count} avg={avg_ms:.1f}ms max={self._send_done_summary_max_ms}ms"
            )
        self._pending_log_lines.append(line)
        self._reset_send_done_summary()

    def _consume_send_done_log(self, ts_text: str, raw_line: str) -> bool:
        m = RE_SEND_DONE_LOG.match((raw_line or "").strip())
        if m is None:
            # Keep log timeline stable when switching to non-send lines.
            self._flush_send_done_summary(force=True)
            return False

        chunk = int(m.group("chunk"))
        cost_ms = int(m.group("ms"))
        if self._send_done_summary_count > 0 and ts_text != self._send_done_summary_second:
            self._flush_send_done_summary(force=True)

        if self._send_done_summary_count <= 0:
            self._send_done_summary_second = ts_text
            self._send_done_summary_first_chunk = chunk
            self._send_done_summary_last_chunk = chunk
            self._send_done_summary_total_ms = cost_ms
            self._send_done_summary_max_ms = cost_ms
            self._send_done_summary_count = 1
            self._send_done_summary_deadline = time.monotonic() + UI_SEND_DONE_SUMMARY_INTERVAL_SECONDS
            return True

        self._send_done_summary_last_chunk = chunk
        self._send_done_summary_total_ms += cost_ms
        if cost_ms > self._send_done_summary_max_ms:
            self._send_done_summary_max_ms = cost_ms
        self._send_done_summary_count += 1
        return True

    def _buffer_log_line(self, line: str) -> None:
        if not line:
            return
        self._pending_log_lines.append(line)
        # Guard against long UI pauses if logs spike quickly.
        if len(self._pending_log_lines) >= 120:
            self._flush_log_buffer(force=True)

    def _flush_log_buffer(self, force: bool = False) -> None:
        if not self._pending_log_lines:
            return
        now = time.monotonic()
        if (not force) and (now < self._next_log_flush_at):
            return

        lines = self._pending_log_lines
        self._pending_log_lines = []
        self.log_text.configure(state="normal")
        self.log_text.insert("end", "\n".join(lines) + "\n")
        self._trim_scrolled_text(self.log_text, max_lines=800)
        self.log_text.configure(state="disabled")
        self.log_text.see("end")
        self._write_runtime_log_lines(lines)
        self._next_log_flush_at = now + UI_LOG_FLUSH_INTERVAL_SECONDS

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
        self._apply_server_env_to_command_vars(self.command_var, self.server_env_var)

    def _apply_server_env_to_conversation_command(self) -> None:
        self._apply_server_env_to_command_vars(self.conversation_command_var, self.conversation_server_env_var)

    def _apply_server_env_to_command_vars(self, command_var: tk.StringVar, env_var: tk.StringVar) -> None:
        env = (env_var.get() or "local").strip().lower()
        if env not in {"local", "public"}:
            env = "local"
            env_var.set(env)

        command = (command_var.get() or "").strip()
        tokens = self._safe_split(command)
        if not tokens:
            return

        rebuilt: list[str] = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in {"--server-env", "--base-url"}:
                i += 2 if i + 1 < len(tokens) else 1
                continue
            rebuilt.append(token)
            i += 1

        rebuilt.extend(["--server-env", env])
        new_command = self._safe_join(rebuilt)
        if new_command != command:
            command_var.set(new_command)

    def _sync_server_env_from_command(self, command: str) -> None:
        self._sync_server_env_from_command_to_var(command, self.server_env_var)

    def _sync_conversation_server_env_from_command(self, command: str) -> None:
        self._sync_server_env_from_command_to_var(command, self.conversation_server_env_var)

    def _sync_server_env_from_command_to_var(self, command: str, env_var: tk.StringVar) -> None:
        tokens = self._safe_split(command)
        if not tokens:
            return
        env = ""
        if "--server-env" in tokens:
            idx = tokens.index("--server-env")
            if idx + 1 < len(tokens):
                env = str(tokens[idx + 1]).strip().lower()
        if not env and "--base-url" in tokens:
            idx = tokens.index("--base-url")
            if idx + 1 < len(tokens):
                base_url = str(tokens[idx + 1]).strip().lower()
                if base_url and ("127.0.0.1" not in base_url) and ("localhost" not in base_url):
                    env = "public"
                elif base_url:
                    env = "local"
        if env in {"local", "public"} and env != env_var.get():
            env_var.set(env)

    def _toggle_asr(self) -> None:
        enabled = not bool(self.asr_enabled_var.get())
        self.asr_enabled_var.set(enabled)
        self.asr_toggle_text_var.set("关闭ASR识别" if enabled else "开启ASR识别")
        if enabled:
            self._log_asr_monitor("switch_on")
            self._start_settings_asr()
        else:
            self._log_asr_monitor("switch_off")
            self._reset_asr_wait()
            self._stop_settings_asr()
            self._set_microphone_open("settings", False, reason="asr_switch_off")
            if self._bridge.running and self._main_mic_open:
                self._log_asr_monitor("switch_off stopping main process to close microphone")
                self._stop()
        self._refresh_system_instruction()

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
        panes = self.flow_panes
        flow_box = self.flow_json_box
        if not panes or not flow_box:
            return
        pane_ids = set(panes.panes())
        flow_box_id = str(flow_box)
        show_script = bool(self.flow_show_script_var.get())
        if show_script:
            if flow_box_id not in pane_ids:
                panes.add(flow_box, weight=2)
            return
        if flow_box_id in pane_ids:
            panes.forget(flow_box)

    def _flow_monitor_zoom_in(self) -> None:
        canvas = self.flow_monitor_canvas
        if canvas:
            canvas.zoom_in()
            self._apply_flow_monitor_active_node_style()

    def _flow_monitor_zoom_out(self) -> None:
        canvas = self.flow_monitor_canvas
        if canvas:
            canvas.zoom_out()
            self._apply_flow_monitor_active_node_style()

    def _flow_monitor_zoom_reset(self) -> None:
        canvas = self.flow_monitor_canvas
        if canvas:
            canvas.reset_zoom()
            self._apply_flow_monitor_active_node_style()

    def _apply_flow_monitor_active_node_style(self) -> None:
        canvas = self.flow_monitor_canvas
        active_node_id = str(self._flow_active_node_id or "").strip()
        if (not canvas) or (not active_node_id):
            return
        node = canvas.nodes.get(active_node_id)
        if not node or not node.shape_item_id:
            return
        canvas.itemconfigure(
            node.shape_item_id,
            outline="#dc2626",
            width=max(canvas.selected_line_width, canvas.base_line_width + 1),
        )

    def _lock_flow_monitor_interactions(self) -> None:
        if not self.flow_monitor_canvas:
            return
        for sequence in (
            "<ButtonPress-1>",
            "<B1-Motion>",
            "<ButtonRelease-1>",
            "<Double-Button-1>",
            "<Delete>",
            "<BackSpace>",
        ):
            self.flow_monitor_canvas.bind(sequence, lambda _event: "break")

    def _bind_flow_monitor_hover_events(self) -> None:
        if not self.flow_monitor_canvas:
            return
        self.flow_monitor_canvas.bind("<Motion>", self._on_flow_monitor_motion, add="+")
        self.flow_monitor_canvas.bind("<Leave>", self._on_flow_monitor_leave, add="+")

    def _restore_flow_monitor_highlight(self) -> None:
        canvas = self.flow_monitor_canvas
        active_node_id = str(self._flow_active_node_id or "").strip()
        if not canvas or not active_node_id:
            return
        if active_node_id not in canvas.nodes:
            return
        if canvas.selected_node_id == active_node_id and canvas.selected_edge_id is None:
            self._apply_flow_monitor_active_node_style()
            return
        canvas.selected_node_id = active_node_id
        canvas.selected_edge_id = None
        if hasattr(canvas, "_sync_selection_styles"):
            canvas._sync_selection_styles()  # type: ignore[attr-defined]
        self._apply_flow_monitor_active_node_style()

    def _flow_monitor_node_id_at(self, canvas_x: float, canvas_y: float) -> str:
        canvas = self.flow_monitor_canvas
        if not canvas:
            return ""
        item_ids = canvas.find_overlapping(canvas_x - 1, canvas_y - 1, canvas_x + 1, canvas_y + 1)
        for item_id in reversed(item_ids):
            node_id = canvas.item_to_node.get(item_id)
            if node_id:
                return str(node_id)
        return ""

    def _show_flow_tooltip(self, text: str, screen_x: int, screen_y: int) -> None:
        content = str(text or "").strip() or "(无 task_notes)"
        if not self._flow_tooltip_window:
            tip = tk.Toplevel(self)
            tip.withdraw()
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            label = tk.Label(
                tip,
                text=content,
                justify="left",
                anchor="nw",
                bg="#0f172a",
                fg="#f8fafc",
                relief="solid",
                borderwidth=1,
                padx=8,
                pady=6,
                wraplength=380,
            )
            label.pack(fill="both", expand=True)
            self._flow_tooltip_window = tip
            self._flow_tooltip_label = label
        if self._flow_tooltip_label:
            self._flow_tooltip_label.configure(text=content)
        if self._flow_tooltip_window:
            self._flow_tooltip_window.geometry(f"+{int(screen_x)}+{int(screen_y)}")
            self._flow_tooltip_window.deiconify()

    def _hide_flow_tooltip(self) -> None:
        if self._flow_tooltip_window:
            self._flow_tooltip_window.withdraw()
        self._flow_hover_node_id = ""

    def _on_flow_monitor_leave(self, _event: tk.Event) -> None:
        self._hide_flow_tooltip()
        self._restore_flow_monitor_highlight()

    def _on_flow_monitor_motion(self, event: tk.Event) -> None:
        canvas = self.flow_monitor_canvas
        if not canvas:
            return
        canvas_x = canvas.canvasx(event.x)
        canvas_y = canvas.canvasy(event.y)
        hover_node_id = self._flow_monitor_node_id_at(canvas_x, canvas_y)
        if not hover_node_id:
            self._hide_flow_tooltip()
            self._restore_flow_monitor_highlight()
            return
        node = canvas.nodes.get(hover_node_id)
        if node is None:
            self._hide_flow_tooltip()
            self._restore_flow_monitor_highlight()
            return
        self._flow_hover_node_id = hover_node_id
        self._show_flow_tooltip(
            text=f"节点ID: {hover_node_id}\n\n{str(node.task_notes or '').strip() or '(无 task_notes)'}",
            screen_x=event.x_root + 14,
            screen_y=event.y_root + 14,
        )
        self._restore_flow_monitor_highlight()

    @staticmethod
    def _to_float(value: object, fallback: float) -> float:
        try:
            return float(value)
        except Exception:
            return fallback

    @staticmethod
    def _coerce_node_type(value: object) -> str:
        raw = str(value or "").strip().lower()
        valid_types = {item.value for item in NodeType}
        if raw in valid_types:
            return raw
        return NodeType.PROCESS.value

    def _build_flow_graph_models(
        self,
        payload: dict[str, object],
    ) -> tuple[list[FlowNode], list[FlowEdge], dict[str, object], dict[str, object]]:
        raw_nodes = payload.get("nodes")
        raw_edges = payload.get("edges")
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise ValueError("workflow file must contain nodes(list) and edges(list)")

        nodes: list[FlowNode] = []
        node_ids: set[str] = set()
        for idx, item in enumerate(raw_nodes):
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("id") or "").strip()
            if (not node_id) or (node_id in node_ids):
                continue
            node_type = self._coerce_node_type(item.get("type"))
            fallback_x = 160.0 + float((idx % 4) * 220)
            fallback_y = 120.0 + float((idx // 4) * 150)
            node_payload = {
                "id": node_id,
                "type": node_type,
                "x": self._to_float(item.get("x"), fallback_x),
                "y": self._to_float(item.get("y"), fallback_y),
                "width": self._to_float(item.get("width"), 140.0),
                "height": self._to_float(item.get("height"), 84.0),
                "text": str(item.get("text") or "").strip() or node_id,
                "task_notes": str(item.get("task_notes") or ""),
            }
            try:
                node = FlowNode.from_dict(node_payload)
            except Exception:
                continue
            nodes.append(node)
            node_ids.add(node_id)

        if not nodes:
            raise ValueError("流程文件缺少有效节点。")

        edges: list[FlowEdge] = []
        edge_ids: set[str] = set()
        for idx, item in enumerate(raw_edges):
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id") or "").strip()
            target_id = str(item.get("target_id") or "").strip()
            if (source_id not in node_ids) or (target_id not in node_ids):
                continue
            base_edge_id = str(item.get("id") or "").strip() or f"edge_{idx + 1}"
            edge_id = base_edge_id
            duplicate_idx = 1
            while edge_id in edge_ids:
                duplicate_idx += 1
                edge_id = f"{base_edge_id}_{duplicate_idx}"
            edge_payload = {
                "id": edge_id,
                "source_id": source_id,
                "target_id": target_id,
                "text": str(item.get("text") or ""),
                "route_points": item.get("route_points", []),
                "source_anchor": item.get("source_anchor"),
                "target_anchor": item.get("target_anchor"),
            }
            try:
                edge = FlowEdge.from_dict(edge_payload)
            except Exception:
                continue
            edges.append(edge)
            edge_ids.add(edge_id)

        raw_display = payload.get("display_settings")
        raw_view = payload.get("view_state")
        display_settings = raw_display if isinstance(raw_display, dict) else {}
        view_state = raw_view if isinstance(raw_view, dict) else {}
        return nodes, edges, display_settings, view_state

    def _render_flow_monitor_graph(self, payload: dict[str, object]) -> None:
        if not self.flow_monitor_canvas:
            return
        self._hide_flow_tooltip()
        nodes, edges, display_settings, view_state = self._build_flow_graph_models(payload)
        self.flow_monitor_canvas.load_data(nodes, edges)
        if display_settings:
            line_thickness = max(1.0, self._to_float(display_settings.get("line_thickness"), 2.0))
            font_family = UI_FONT_FAMILY
            font_size = UI_FONT_SIZE
            node_text_color = str(display_settings.get("node_text_color") or "#111827").strip() or "#111827"
            edge_text_color = str(display_settings.get("edge_text_color") or "#374151").strip() or "#374151"
            self.flow_monitor_canvas.apply_display_settings(
                line_thickness=line_thickness,
                font_family=font_family,
                font_size=font_size,
                node_text_color=node_text_color,
                edge_text_color=edge_text_color,
            )
        if view_state:
            self.flow_monitor_canvas.apply_view_state(view_state)
        self.flow_monitor_canvas.selected_node_id = None
        self.flow_monitor_canvas.selected_edge_id = None
        if hasattr(self.flow_monitor_canvas, "_sync_selection_styles"):
            self.flow_monitor_canvas._sync_selection_styles()  # type: ignore[attr-defined]
        self._flow_active_node_id = ""

    def _center_flow_monitor_node(self, node_id: str) -> None:
        canvas = self.flow_monitor_canvas
        if not canvas:
            return
        node = canvas.nodes.get(node_id)
        if node is None:
            return
        canvas.update_idletasks()
        region_text = str(canvas.cget("scrollregion") or "").strip()
        if not region_text:
            return
        parts = region_text.split()
        if len(parts) != 4:
            return
        try:
            left, top, right, bottom = [float(item) for item in parts]
        except Exception:
            return
        total_width = max(1.0, right - left)
        total_height = max(1.0, bottom - top)
        view_width = max(1.0, float(canvas.winfo_width()))
        view_height = max(1.0, float(canvas.winfo_height()))
        max_x = max(1.0, total_width - view_width)
        max_y = max(1.0, total_height - view_height)
        x_target = max(0.0, min(max_x, (node.x - left) - view_width / 2.0))
        y_target = max(0.0, min(max_y, (node.y - top) - view_height / 2.0))
        canvas.xview_moveto(x_target / max_x if max_x > 0 else 0.0)
        canvas.yview_moveto(y_target / max_y if max_y > 0 else 0.0)

    def _highlight_flow_monitor_node(self, node_id: str, *, center: bool = True) -> bool:
        canvas = self.flow_monitor_canvas
        if not canvas:
            return False
        target_id = str(node_id or "").strip()
        if (not target_id) or (target_id not in canvas.nodes):
            return False
        canvas.selected_node_id = target_id
        canvas.selected_edge_id = None
        if hasattr(canvas, "_sync_selection_styles"):
            canvas._sync_selection_styles()  # type: ignore[attr-defined]
        if center:
            self._center_flow_monitor_node(target_id)
        self._flow_active_node_id = target_id
        self._apply_flow_monitor_active_node_style()
        return True

    def _handle_workflow_progress_event(self, payload: dict[str, object], ts_text: str) -> None:
        trigger = self._sanitize_inline_text(str(payload.get("trigger", ""))) or "-"
        reason = self._sanitize_inline_text(str(payload.get("reason", "")))
        from_node_id = self._sanitize_inline_text(str(payload.get("from_node_id", "")))
        jump_node_id = self._sanitize_inline_text(str(payload.get("jump_node_id", "")))
        cursor_node_id = self._sanitize_inline_text(str(payload.get("cursor_node_id", "")))
        route_node_id = self._sanitize_inline_text(str(payload.get("route_node_id", "")))
        content_node_id = self._sanitize_inline_text(str(payload.get("content_node_id", "")))
        matched_label = self._sanitize_inline_text(str(payload.get("matched_label", "")))
        intents_value = payload.get("intents", [])
        intents = [self._sanitize_inline_text(str(item)) for item in intents_value if str(item).strip()] if isinstance(intents_value, list) else []
        advanced = bool(payload.get("advanced", False))

        highlighted = False
        for candidate in (jump_node_id, content_node_id, cursor_node_id, route_node_id):
            if self._highlight_flow_monitor_node(candidate):
                highlighted = True
                break

        active_node = self._flow_active_node_id or content_node_id or cursor_node_id or route_node_id or "-"
        summary_parts = [
            f"当前节点={active_node}",
            f"trigger={trigger}",
            f"advanced={advanced}",
        ]
        if from_node_id:
            summary_parts.append(f"from={from_node_id}")
        if jump_node_id:
            summary_parts.append(f"jump={jump_node_id}")
        if matched_label:
            summary_parts.append(f"label={matched_label}")
        if intents:
            summary_parts.append(f"intents={','.join(intents)}")
        if reason:
            summary_parts.append(f"reason={reason}")
        if not highlighted and self.flow_monitor_canvas and self.flow_monitor_canvas.nodes:
            summary_parts.append("warning=目标节点未在图中找到")
        self.flow_summary_var.set(" | ".join(summary_parts))
        self._append_line(
            self.log_text,
            f"[{ts_text}] [FLOW_TRACK] {' | '.join(summary_parts)}",
        )

    def _load_workflow_json_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择流程文件",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = Path(path).read_text(encoding="utf-8-sig")
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc))
            return
        try:
            payload = json.loads(raw)
        except Exception as exc:
            messagebox.showerror("JSON无效", f"文件不是有效JSON：{exc}")
            return
        if not isinstance(payload, dict):
            messagebox.showerror("结构无效", "流程文件根节点必须是 JSON 对象。")
            return
        try:
            self._render_flow_monitor_graph(payload)
        except Exception as exc:
            messagebox.showerror("结构无效", str(exc))
            return
        nodes = payload.get("nodes")
        edges = payload.get("edges")
        nodes_count = len(nodes) if isinstance(nodes, list) else 0
        edges_count = len(edges) if isinstance(edges, list) else 0
        pretty = json.dumps(payload, ensure_ascii=False, indent=2)
        self._loaded_workflow_payload = payload
        self._loaded_workflow_json_text = pretty
        self._loaded_workflow_json_path = str(Path(path))
        self._loaded_workflow_json_nodes = nodes_count
        self._loaded_workflow_json_edges = edges_count
        self._flow_active_node_id = ""
        self.flow_path_var.set(self._loaded_workflow_json_path)
        self.flow_summary_var.set(f"已加载流程图，nodes={nodes_count} edges={edges_count}，等待执行信号。")
        self._set_text_content(self.flow_json_text, pretty)
        ts_text = datetime.now().strftime("%H:%M:%S")
        self._append_line(
            self.log_text,
            f"[{ts_text}] [FLOW] loaded path={self._loaded_workflow_json_path} nodes={nodes_count} edges={edges_count}",
        )

    def _clear_loaded_workflow_json(self) -> None:
        self._loaded_workflow_json_text = ""
        self._loaded_workflow_json_path = ""
        self._loaded_workflow_json_nodes = 0
        self._loaded_workflow_json_edges = 0
        self._loaded_workflow_payload = None
        self._flow_active_node_id = ""
        self._hide_flow_tooltip()
        self.flow_path_var.set("未加载")
        self.flow_summary_var.set("未加载流程文件")
        self._set_text_content(self.flow_json_text, "未加载流程文件。点击“加载流程文件”选择 workflow_json。")
        if self.flow_monitor_canvas:
            self.flow_monitor_canvas.clear()

    def _clear_intent_page_views(self) -> None:
        return

    def _submit_customer_profile_from_panel(self) -> None:
        messagebox.showinfo("功能已移除", "设置页“客户画像”子窗口及相关功能已移除。")

    def _submit_workflow_from_panel(self) -> None:
        messagebox.showinfo("功能已移除", "设置页“工作流程”子窗口及相关功能已移除。")

    def _open_conversation_customer_profile_dialog(self) -> None:
        self._open_conversation_customer_profile_generator_dialog()

    def _render_conversation_strategy_history_panel(self) -> None:
        ctrl_render_conversation_strategy_history_panel(self)

    def _get_conversation_strategy_history_for_tab(self, tab_id: str) -> list[dict[str, str]]:
        return ctrl_get_conversation_strategy_history_for_tab(self, tab_id)

    def _render_conversation_strategy_dialog_history(self, dialog: dict[str, object]) -> None:
        history_widget = dialog.get("history_text")
        if not isinstance(history_widget, ScrolledText):
            return
        tab_id = str(dialog.get("tab_id", "") or "")
        history = self._get_conversation_strategy_history_for_tab(tab_id)
        try:
            history_widget.configure(state="normal")
            history_widget.delete("1.0", "end")
        except Exception:
            return
        dialog["_cp_bubble_refs"] = []
        dialog.pop("_cp_active_left_bubble", None)
        if not history:
            try:
                history_widget.insert("end", "暂无历史记录\n", ("cs_hint",))
            except Exception:
                return
            history_widget.see("end")
            return
        for item in history:
            instruction = str(item.get("instruction", "") or "-")
            response = str(item.get("response", "") or "-")
            self._insert_customer_profile_bubble_row(
                history_widget,
                header="",
                body=instruction,
                is_right=True,
                keep_active=False,
            )
            self._insert_customer_profile_bubble_row(
                history_widget,
                header="",
                body=response,
                is_right=False,
                keep_active=False,
            )

    def _append_text_to_widget_with_tag(self, widget: ScrolledText, text: str, tag: str) -> None:
        if (not text) or (not isinstance(widget, ScrolledText)):
            return
        if self._try_append_customer_profile_bubble(widget, text, tag):
            return
        try:
            widget.configure(state="normal")
            widget.insert("end", text, (tag,))
            widget.see("end")
        except Exception:
            return

    def _try_append_customer_profile_bubble(self, widget: ScrolledText, text: str, tag: str) -> bool:
        dialog = None
        for _attr in ("_conversation_customer_profile_dialog", "_conversation_intent_dialog", "_conversation_strategy_dialog"):
            _d = getattr(self, _attr, None)
            if isinstance(_d, dict) and _d.get("output") is widget:
                dialog = _d
                break
        if not isinstance(dialog, dict):
            return False
        if tag not in {"cs_right_bubble", "cs_left_bubble"}:
            return False
        clean_text = str(text or "").replace("\r", "")
        if not clean_text:
            return True

        # When history is re-rendered via delete("1.0", "end"), reset bubble refs.
        try:
            is_empty = str(widget.index("end-1c")) == "1.0"
        except Exception:
            is_empty = False
        if is_empty:
            dialog["_cp_bubble_refs"] = []
            dialog.pop("_cp_active_left_bubble", None)

        lines = clean_text.split("\n")
        header = lines[0].strip() if lines else ""
        body = "\n".join(lines[1:]).strip("\n")
        is_right = tag == "cs_right_bubble"

        # New LLM bubble header line: start a live/empty bubble.
        if (not is_right) and self._is_llm_header_line(header) and (not body.strip()):
            self._insert_customer_profile_bubble_row(widget, header=header, body="", is_right=False, keep_active=True)
            return True

        # Stream chunks or thinking text: append to the current active left bubble.
        if (not is_right):
            active = dialog.get("_cp_active_left_bubble")
            if isinstance(active, dict) and (not self._is_instruction_header_line(header)) and (not self._is_llm_header_line(header)):
                self._append_customer_profile_bubble_text(widget, active, clean_text)
                return True

        # Full block render (history or immediate instruction/response).
        if self._is_instruction_header_line(header) or self._is_llm_header_line(header):
            self._insert_customer_profile_bubble_row(
                widget,
                header=header,
                body=body,
                is_right=is_right,
                keep_active=(not is_right),
            )
            return True

        # Fallback: still render as a bubble, preserving alignment.
        self._insert_customer_profile_bubble_row(
            widget,
            header="",
            body=clean_text.strip("\n"),
            is_right=is_right,
            keep_active=(not is_right),
        )
        return True

    @staticmethod
    def _is_instruction_header_line(text: str) -> bool:
        t = str(text or "").strip()
        return t.startswith("指令 ") or t.startswith("鎸囦护 ")

    @staticmethod
    def _is_llm_header_line(text: str) -> bool:
        t = str(text or "").strip()
        return t.startswith("LLM返回 ") or t.startswith("LLM杩斿洖 ")

    @staticmethod
    def _draw_rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> int:
        r = max(4, int(radius))
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return int(canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs))

    def _render_customer_profile_bubble_canvas(
        self,
        widget: ScrolledText,
        canvas: tk.Canvas,
        header: str,
        body: str,
        is_right: bool,
    ) -> int:
        _ww = widget.winfo_width()
        try:
            _tw = widget.winfo_toplevel().winfo_width()
            if _tw > 100:
                _ww = max(_ww, _tw - 60)
        except Exception:
            pass
        if _ww < 200:
            _ww = 900
        width = max(_ww, 200)
        max_bubble_width = max(240, int((width - 20) * 0.68))
        text_limit = max(180, max_bubble_width - 28)
        wrapped_body = self._wrap_text_for_strategy_history_bubble(
            text=body,
            history_widget=widget,
            max_width_px=text_limit,
        ).strip("\n")
        content = "\n".join(x for x in [header, wrapped_body] if x) if (header or wrapped_body) else ""
        try:
            font = tkfont.nametofont(str(widget.cget("font")))
        except Exception:
            font = tkfont.nametofont("TkDefaultFont")
        line_h = int(font.metrics("linespace") or 18)
        widest = 0
        for line in content.split("\n"):
            widest = max(widest, int(font.measure(line)))
        bubble_w = min(max_bubble_width, max(190, widest + 26))
        text_w = max(60, bubble_w - 26)
        fill = "#e9eef3" if is_right else "#f4f8ee"
        edge = "#c7d0db" if is_right else "#c8d7ba"
        # Measure actual rendered height via a temporary text item.
        canvas.configure(width=bubble_w + 2, height=1, bg=str(widget.cget("bg")), bd=0, highlightthickness=0)
        canvas.delete("all")
        _tmp = canvas.create_text(14, 12, anchor="nw", text=content, font=font, width=text_w)
        _bbox = canvas.bbox(_tmp)
        canvas.delete(_tmp)
        bubble_h = max(40, (_bbox[3] + 12) if _bbox else int(len(content.split("\n")) * line_h + 24))
        canvas.configure(width=bubble_w + 2, height=bubble_h + 2, bd=0, highlightthickness=0)
        canvas.delete("all")
        self._draw_rounded_rect(canvas, 1, 1, bubble_w, bubble_h, 12, fill=fill, outline=edge, width=1)
        canvas.create_text(14, 12, anchor="nw", text=content, fill="#1f2937", font=font, width=text_w)
        return bubble_h + 6

    def _insert_customer_profile_bubble_row(
        self,
        widget: ScrolledText,
        *,
        header: str,
        body: str,
        is_right: bool,
        keep_active: bool,
    ) -> None:
        dialog = None
        for _attr in ("_conversation_customer_profile_dialog", "_conversation_intent_dialog", "_conversation_strategy_dialog"):
            _d = getattr(self, _attr, None)
            if isinstance(_d, dict) and (_d.get("output") is widget or _d.get("history_text") is widget):
                dialog = _d
                break
        if not isinstance(dialog, dict):
            return
        bg = str(widget.cget("bg"))
        _ww = widget.winfo_width()
        try:
            _tw = widget.winfo_toplevel().winfo_width()
            if _tw > 100:
                _ww = max(_ww, _tw - 60)
        except Exception:
            pass
        if _ww < 200:
            _ww = 900
        width = max(_ww, 200)
        row = tk.Frame(widget, bg=bg, width=max(320, width - 20), height=1, bd=0, highlightthickness=0)
        row.pack_propagate(False)
        canvas = tk.Canvas(row, bd=0, highlightthickness=0, bg=bg)
        canvas.pack(anchor=("e" if is_right else "w"), padx=((0, 8) if is_right else (8, 0)), pady=(2, 2))
        row.configure(height=self._render_customer_profile_bubble_canvas(widget, canvas, header, body, is_right))

        def _scroll(event: tk.Event, _w: ScrolledText = widget) -> None:
            _w.yview_scroll(int(-1 * (event.delta / 120)), "units")

        row.bind("<MouseWheel>", _scroll)
        canvas.bind("<MouseWheel>", _scroll)

        widget.window_create("end", window=row)
        widget.insert("end", "\n")
        refs = dialog.setdefault("_cp_bubble_refs", [])
        if isinstance(refs, list):
            refs.append((row, canvas))
        if keep_active:
            dialog["_cp_active_left_bubble"] = {
                "row": row,
                "canvas": canvas,
                "header": str(header or ""),
                "text": str(body or ""),
                "is_right": bool(is_right),
            }
        widget.see("end")

    def _append_customer_profile_bubble_text(self, widget: ScrolledText, active: dict[str, object], chunk: str) -> None:
        row = active.get("row")
        canvas = active.get("canvas")
        if (not isinstance(row, tk.Frame)) or (not isinstance(canvas, tk.Canvas)):
            return
        current = str(active.get("text", "") or "") + str(chunk or "")
        active["text"] = current
        row.configure(
            height=self._render_customer_profile_bubble_canvas(
                widget,
                canvas,
                header=str(active.get("header", "")),
                body=current,
                is_right=bool(active.get("is_right", False)),
            )
        )
        widget.see("end")

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
        raw_text = str(text or "").replace("\r", "")
        max_px = max(120, int(max_width_px or 0))
        try:
            font = tkfont.nametofont(str(history_widget.cget("font")))
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

    def _update_conversation_strategy_dialog_history_tags(self, history_widget: ScrolledText) -> None:
        width = int(history_widget.winfo_width() or history_widget.winfo_reqwidth() or 900)
        side_gap = 14
        max_bubble_width = max(240, int(width * (2.0 / 3.0)))
        right_left_margin = max(side_gap, width - max_bubble_width - side_gap)
        left_right_margin = right_left_margin
        history_widget.tag_configure(
            "cs_left",
            justify="left",
            lmargin1=side_gap,
            lmargin2=side_gap,
            rmargin=left_right_margin,
            foreground="#6b7280",
            spacing1=6,
            spacing3=6,
        )
        history_widget.tag_configure(
            "cs_right",
            justify="right",
            lmargin1=right_left_margin,
            lmargin2=right_left_margin,
            rmargin=side_gap,
            foreground="#6b7280",
            spacing1=6,
            spacing3=6,
        )
        history_widget.tag_configure(
            "cs_right_bubble",
            justify="left",
            lmargin1=right_left_margin,
            lmargin2=right_left_margin,
            rmargin=side_gap,
            background="#e6e8eb",
            foreground="#111827",
            borderwidth=1,
            relief="flat",
            spacing1=6,
            spacing3=6,
        )
        history_widget.tag_configure(
            "cs_left_bubble",
            justify="left",
            lmargin1=side_gap,
            lmargin2=side_gap,
            rmargin=left_right_margin,
            background="#dcfce7",
            foreground="#111827",
            borderwidth=1,
            relief="flat",
            spacing1=6,
            spacing3=6,
        )

    def _update_customer_profile_dialog_history_tags(self, history_widget: ScrolledText) -> None:
        width = int(history_widget.winfo_width() or history_widget.winfo_reqwidth() or 900)
        side_gap = 16
        max_bubble_width = max(240, int(width * (2.0 / 3.0)))
        right_left_margin = max(side_gap, width - max_bubble_width - side_gap)
        left_right_margin = right_left_margin
        history_widget.tag_configure(
            "cs_right_bubble",
            justify="left",
            lmargin1=right_left_margin,
            lmargin2=right_left_margin,
            rmargin=side_gap,
            background="#e9eef3",
            foreground="#1f2937",
            borderwidth=1,
            relief="solid",
            spacing1=7,
            spacing3=8,
        )
        history_widget.tag_configure(
            "cs_left_bubble",
            justify="left",
            lmargin1=side_gap,
            lmargin2=side_gap,
            rmargin=left_right_margin,
            background="#f4f8ee",
            foreground="#1f2937",
            borderwidth=1,
            relief="solid",
            spacing1=7,
            spacing3=8,
        )
        history_widget.tag_configure(
            "cs_hint",
            justify="center",
            foreground="#6b7280",
            spacing1=10,
            spacing3=10,
        )

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
        history_widget = dialog.get("history_text")
        if not isinstance(history_widget, ScrolledText):
            return
        tab_id = str(dialog.get("tab_id", "") or "")
        history = self._get_conversation_customer_profile_history_for_tab(tab_id)
        try:
            history_widget.configure(state="normal")
            history_widget.delete("1.0", "end")
        except Exception:
            return
        dialog["_cp_bubble_refs"] = []
        dialog.pop("_cp_active_left_bubble", None)
        if not history:
            try:
                history_widget.insert("end", "暂无历史记录\n", ("cs_hint",))
            except Exception:
                return
            history_widget.see("end")
            return
        for item in history:
            instruction = str(item.get("instruction", "") or "-")
            response = str(item.get("response", "") or "-")
            self._insert_customer_profile_bubble_row(
                history_widget,
                header="",
                body=instruction,
                is_right=True,
                keep_active=False,
            )
            self._insert_customer_profile_bubble_row(
                history_widget,
                header="",
                body=response,
                is_right=False,
                keep_active=False,
            )

    def _prepare_live_conversation_customer_profile_response_bubble(self, source_widget: ScrolledText) -> None:
        dialog = getattr(self, "_conversation_customer_profile_dialog", None)
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

    def _append_live_conversation_customer_profile_thinking_chunk(self, source_widget: ScrolledText, chunk: str) -> None:
        self._append_text_to_widget_with_tag(source_widget, chunk, "cs_left_bubble")

    def _append_live_conversation_customer_profile_content_chunk(self, source_widget: ScrolledText, chunk: str) -> None:
        self._prepare_live_conversation_customer_profile_response_bubble(source_widget)
        self._append_text_to_widget_with_tag(source_widget, chunk, "cs_left_bubble")

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
        from tkinter import messagebox
        messagebox.showinfo("保存成功", "系统指令已保存并生效")

    def _save_conversation_customer_profile_from_panel(self) -> None:
        """保存客户画像内容到快照"""
        try:
            self._save_persisted_conversation_tab_snapshots()
            from tkinter import messagebox
            messagebox.showinfo("保存成功", "客户画像已保存")
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc))

    def _save_conversation_intent_from_panel(self) -> None:
        """保存客户意图内容到快照"""
        try:
            self._save_persisted_conversation_tab_snapshots()
            from tkinter import messagebox
            messagebox.showinfo("保存成功", "客户意图已保存")
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc))

    def _save_conversation_strategy_from_panel(self) -> None:
        """保存对话策略内容到快照"""
        try:
            self._save_persisted_conversation_tab_snapshots()
            from tkinter import messagebox
            messagebox.showinfo("保存成功", "对话策略已保存")
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc))

    def _load_prompt_templates_from_file(self) -> None:
        """从本地文件加载提示词模板，不存在则保留默认值"""
        try:
            path = getattr(self, "_prompt_templates_path", None)
            if path is None or not Path(path).exists():
                return
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            summary = str(raw.get("dialog_summary_prompt", "") or "").strip()
            strategy = str(raw.get("dialog_strategy_prompt", "") or "").strip()
            if summary:
                self._dialog_summary_prompt_template_cache = summary
            if strategy:
                self._dialog_strategy_prompt_template_cache = strategy
        except Exception:
            pass

    def _save_prompt_templates_to_file(self) -> None:
        """将当前提示词模板缓存写入本地文件"""
        try:
            path = getattr(self, "_prompt_templates_path", None)
            if path is None:
                return
            data = {
                "dialog_summary_prompt": self._dialog_summary_prompt_template_cache,
                "dialog_strategy_prompt": self._dialog_strategy_prompt_template_cache,
            }
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _save_dialog_summary_prompt_from_panel(self) -> None:
        """保存对话总结提示词模板"""
        try:
            widget = self.conversation_summary_prompt_text
            if widget:
                text = widget.get("1.0", "end-1c").strip()
                if text:
                    self._dialog_summary_prompt_template_cache = text
            self._save_prompt_templates_to_file()
            from tkinter import messagebox
            messagebox.showinfo("保存成功", "对话总结提示词已保存")
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc))

    def _save_dialog_strategy_prompt_from_panel(self) -> None:
        """保存对话策略提示词模板"""
        try:
            widget = self.conversation_strategy_prompt_text
            if widget:
                text = widget.get("1.0", "end-1c").strip()
                if text:
                    self._dialog_strategy_prompt_template_cache = text
            self._save_prompt_templates_to_file()
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
        history_widget = dialog.get("history_text")
        if not isinstance(history_widget, ScrolledText):
            return
        tab_id = str(dialog.get("tab_id", "") or "")
        history = self._get_conversation_intent_generator_history_for_tab(tab_id)
        try:
            history_widget.configure(state="normal")
            history_widget.delete("1.0", "end")
        except Exception:
            return
        dialog["_cp_bubble_refs"] = []
        dialog.pop("_cp_active_left_bubble", None)
        if not history:
            try:
                history_widget.insert("end", "暂无历史记录\n", ("cs_hint",))
            except Exception:
                return
            history_widget.see("end")
            return
        for item in history:
            instruction = str(item.get("instruction", "") or "-")
            response = str(item.get("response", "") or "-")
            self._insert_customer_profile_bubble_row(
                history_widget,
                header="",
                body=instruction,
                is_right=True,
                keep_active=False,
            )
            self._insert_customer_profile_bubble_row(
                history_widget,
                header="",
                body=response,
                is_right=False,
                keep_active=False,
            )

    def _prepare_live_conversation_intent_response_bubble(self, source_widget: ScrolledText) -> None:
        dialog = getattr(self, "_conversation_intent_dialog", None)
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

    def _append_live_conversation_intent_thinking_chunk(self, source_widget: ScrolledText, chunk: str) -> None:
        self._append_text_to_widget_with_tag(source_widget, chunk, "cs_left_bubble")

    def _append_live_conversation_intent_content_chunk(self, source_widget: ScrolledText, chunk: str) -> None:
        self._prepare_live_conversation_intent_response_bubble(source_widget)
        self._append_text_to_widget_with_tag(source_widget, chunk, "cs_left_bubble")

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
        messagebox.showinfo("功能已移除", "意图页面及其相关功能已移除。")

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
        messagebox.showinfo("功能已移除", f"设置页“{kind_label}”相关提交功能已移除。")

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
        messagebox.showinfo("功能已移除", "设置页“客户画像”编辑功能已移除。")

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
        widget = self.conversation_summary_prompt_text
        if isinstance(widget, ScrolledText):
            try:
                text = widget.get("1.0", "end-1c").strip()
                if text:
                    self._dialog_summary_prompt_template_cache = text
                    return text
            except Exception:
                pass
        return self._dialog_summary_prompt_template_cache or DEFAULT_DIALOG_SUMMARY_PROMPT_TEMPLATE

    def _get_dialog_strategy_prompt_template(self) -> str:
        widget = self.conversation_strategy_prompt_text
        if isinstance(widget, ScrolledText):
            try:
                text = widget.get("1.0", "end-1c").strip()
                if text:
                    self._dialog_strategy_prompt_template_cache = text
                    return text
            except Exception:
                pass
        return self._dialog_strategy_prompt_template_cache or DEFAULT_NEXT_DIALOG_STRATEGY_PROMPT_TEMPLATE

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
        messagebox.showinfo("功能已移除", "设置页“工作流程”编辑功能已移除。")

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

    def _render_call_record_detail(self, record: dict[str, str]) -> None:
        ctrl_render_call_record_detail(self, record)

    def _clear_call_record_detail(self, message: str = "请选择左侧通话记录") -> None:
        ctrl_clear_call_record_detail(self, message=message)

    def _apply_call_record_profile_and_workflow(self, record: dict[str, str]) -> None:
        ctrl_apply_call_record_profile_and_workflow(self, record)

    def _load_call_records_into_list(self) -> None:
        ctrl_load_call_records_into_list(self)

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

    def _load_customer_data_records_into_list(self) -> None:
        ctrl_load_customer_data_records_into_list(self)

    def _on_customer_data_record_selected(self, _event=None) -> None:
        ctrl_on_customer_data_record_selected(self, _event=_event)

    def _on_customer_data_tree_click(self, event=None) -> None:
        ctrl_on_customer_data_tree_click(self, event=event)

    def _on_customer_data_tree_double_click(self, event=None) -> None:
        ctrl_on_customer_data_tree_double_click(self, event=event)

    def _open_call_record_detail_window(self, record: dict[str, str]) -> None:
        ctrl_open_call_record_detail_window(self, record)

    def _on_call_record_selected(self, _event=None, apply_profile_and_workflow: bool = True) -> None:
        ctrl_on_call_record_selected(self, _event=_event, apply_profile_and_workflow=apply_profile_and_workflow)

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
        ctrl_fill_profile_table_from_text(
            self,
            tree,
            profile_text,
            empty_message=empty_message,
            auto_height=auto_height,
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
            if launcher in {"python", "python.exe", "py", "py.exe"}:
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
        ctrl_append_line(widget, line, max_lines=max_lines)
        self._write_runtime_log_line(line)

    def _append_line_with_tag(self, widget: ScrolledText, line: str, tag: str, max_lines: int = 800) -> None:
        if not isinstance(widget, ScrolledText):
            return
        ctrl_append_line_with_tag(widget, line, tag=tag, max_lines=max_lines)
        self._write_runtime_log_line(line)

    @staticmethod
    def _set_text_content(widget: ScrolledText, text: str) -> None:
        if not isinstance(widget, ScrolledText):
            return
        ctrl_set_text_content(widget, text)

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

    @staticmethod
    def _trim_scrolled_text(widget: ScrolledText, max_lines: int = 800) -> None:
        ctrl_trim_scrolled_text(widget, max_lines=max_lines)

    def _open_runtime_log_file(self) -> None:
        self._close_runtime_log_file()
        ts = datetime.now()
        log_dir = self._runtime_log_dir
        file_path = log_dir / f"session_{ts.strftime('%Y%m%d_%H%M%S_%f')}.log"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            self._runtime_log_file = file_path.open("w", encoding="utf-8", buffering=1)
            self._runtime_log_file_path = file_path
        except Exception as exc:
            self._runtime_log_file = None
            self._runtime_log_file_path = None
            self._log_asr_monitor(f"log_file_open_failed: {exc}")
            return
        self._write_runtime_log_line(f"# session_started_at={ts.isoformat(timespec='seconds')}")
        self._write_runtime_log_line(f"# session_log_path={file_path}")
        self._append_line(self.log_text, f"[{ts.strftime('%H:%M:%S')}] [LOG_FILE] {file_path}")

    def _write_runtime_log_line(self, line: str) -> None:
        if not line:
            return
        fp = self._runtime_log_file
        if fp is None:
            return
        try:
            fp.write(line + "\n")
        except Exception:
            try:
                fp.close()
            except Exception:
                pass
            self._runtime_log_file = None
            self._runtime_log_file_path = None

    def _write_runtime_log_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        for line in lines:
            self._write_runtime_log_line(line)

    def _close_runtime_log_file(self) -> None:
        fp = self._runtime_log_file
        self._runtime_log_file = None
        self._runtime_log_file_path = None
        if fp is None:
            return
        try:
            fp.flush()
            fp.close()
        except Exception:
            pass


def main() -> None:
    _enable_windows_dpi_awareness()
    app = MicChunkUiApp()
    app.mainloop()


if __name__ == "__main__":
    main()
