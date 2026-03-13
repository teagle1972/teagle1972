from __future__ import annotations

try:
    from ..models.conversation_tab import CallRecordPageState, clone_call_record_page_state
except Exception:
    from models.conversation_tab import CallRecordPageState, clone_call_record_page_state


def build_call_record_state_from_context(context) -> CallRecordPageState:
    state = getattr(context, "call_record_state", None)
    if isinstance(state, CallRecordPageState):
        return clone_call_record_page_state(state)
    return CallRecordPageState(
        items_cache=list(getattr(context, "call_record_items_cache", []) or []),
        cache_version=int(getattr(context, "call_record_cache_version", 0) or 0),
        list_dirty=bool(getattr(context, "call_record_list_dirty", True)),
        view_loaded=bool(getattr(context, "call_record_view_loaded", False)),
        source_signature=str(getattr(context, "call_record_source_signature", "") or ""),
        item_by_iid=dict(getattr(context, "call_record_item_by_iid", {}) or {}),
        item_by_id=dict(getattr(context, "call_record_item_by_id", {}) or {}),
        selected_record_id=str(getattr(context, "selected_call_record_id", "") or ""),
        selected_cache_version=int(getattr(context, "selected_call_record_cache_version", 0) or 0),
    )


def apply_call_record_state_to_context(context, state: CallRecordPageState | None) -> CallRecordPageState:
    cloned = clone_call_record_page_state(state)
    context.call_record_state = cloned
    context.call_record_items_cache = list(cloned.items_cache)
    context.call_record_cache_version = int(cloned.cache_version or 0)
    context.call_record_list_dirty = bool(cloned.list_dirty)
    context.call_record_view_loaded = bool(cloned.view_loaded)
    context.call_record_source_signature = str(cloned.source_signature or "")
    context.call_record_item_by_iid = dict(cloned.item_by_iid or {})
    context.call_record_item_by_id = dict(cloned.item_by_id or {})
    context.selected_call_record_id = str(cloned.selected_record_id or "")
    context.selected_call_record_cache_version = int(cloned.selected_cache_version or 0)
    return cloned


def build_call_record_state_from_app(app) -> CallRecordPageState:
    state = getattr(app, "_call_record_page_state", None)
    base = clone_call_record_page_state(state if isinstance(state, CallRecordPageState) else None)
    base.cache_version = int(getattr(app, "_call_record_cache_version", base.cache_version) or 0)
    base.source_signature = str(getattr(app, "_call_record_source_signature", base.source_signature) or "")
    base.item_by_iid = dict(getattr(app, "_call_record_item_by_iid", base.item_by_iid) or {})
    base.item_by_id = dict(getattr(app, "_call_record_item_by_id", base.item_by_id) or {})
    base.selected_record_id = str(getattr(app, "_selected_call_record_id", base.selected_record_id) or "")
    base.selected_cache_version = int(
        getattr(app, "_selected_call_record_cache_version", base.selected_cache_version) or 0
    )
    return base


def apply_call_record_state_to_app(app, state: CallRecordPageState | None) -> CallRecordPageState:
    cloned = clone_call_record_page_state(state)
    app._call_record_page_state = cloned
    app._call_record_cache_version = int(cloned.cache_version or 0)
    app._call_record_source_signature = str(cloned.source_signature or "")
    app._call_record_item_by_iid = dict(cloned.item_by_iid or {})
    app._call_record_item_by_id = dict(cloned.item_by_id or {})
    app._selected_call_record_id = str(cloned.selected_record_id or "")
    app._selected_call_record_cache_version = int(cloned.selected_cache_version or 0)
    return cloned


def make_empty_call_record_state() -> CallRecordPageState:
    return CallRecordPageState()
