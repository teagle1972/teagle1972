from __future__ import annotations

try:
    from ..models.conversation_tab import CustomerDataPageState, clone_customer_data_page_state
except Exception:
    from models.conversation_tab import CustomerDataPageState, clone_customer_data_page_state


def build_customer_data_state_from_context(context) -> CustomerDataPageState:
    state = getattr(context, "customer_data_state", None)
    if isinstance(state, CustomerDataPageState):
        return clone_customer_data_page_state(state)
    return CustomerDataPageState(
        items_cache=list(getattr(context, "customer_data_items_cache", []) or []),
        cache_version=int(getattr(context, "customer_data_cache_version", 0) or 0),
        list_dirty=bool(getattr(context, "customer_data_list_dirty", True)),
        view_loaded=bool(getattr(context, "customer_data_view_loaded", False)),
        source_signature=str(getattr(context, "customer_data_source_signature", "") or ""),
        customer_by_iid=dict(getattr(context, "customer_data_customer_by_iid", {}) or {}),
        case_by_iid=dict(getattr(context, "customer_data_case_by_iid", {}) or {}),
        case_cache_by_name=dict(getattr(context, "customer_data_case_cache_by_name", {}) or {}),
        selected_customer_name=str(getattr(context, "selected_customer_name", "") or ""),
        selected_cache_version=int(getattr(context, "selected_customer_cache_version", 0) or 0),
    )


def apply_customer_data_state_to_context(context, state: CustomerDataPageState | None) -> CustomerDataPageState:
    cloned = clone_customer_data_page_state(state)
    context.customer_data_state = cloned
    context.customer_data_items_cache = list(cloned.items_cache)
    context.customer_data_cache_version = int(cloned.cache_version or 0)
    context.customer_data_list_dirty = bool(cloned.list_dirty)
    context.customer_data_view_loaded = bool(cloned.view_loaded)
    context.customer_data_source_signature = str(cloned.source_signature or "")
    context.customer_data_customer_by_iid = dict(cloned.customer_by_iid or {})
    context.customer_data_case_by_iid = dict(cloned.case_by_iid or {})
    context.customer_data_case_cache_by_name = dict(cloned.case_cache_by_name or {})
    context.selected_customer_name = str(cloned.selected_customer_name or "")
    context.selected_customer_cache_version = int(cloned.selected_cache_version or 0)
    return cloned


def build_customer_data_state_from_app(app) -> CustomerDataPageState:
    state = getattr(app, "_customer_data_page_state", None)
    base = clone_customer_data_page_state(state if isinstance(state, CustomerDataPageState) else None)
    base.cache_version = int(getattr(app, "_customer_data_cache_version", base.cache_version) or 0)
    base.source_signature = str(getattr(app, "_customer_data_source_signature", base.source_signature) or "")
    base.customer_by_iid = dict(getattr(app, "_customer_data_customer_by_iid", base.customer_by_iid) or {})
    base.case_by_iid = dict(getattr(app, "_customer_data_case_by_iid", base.case_by_iid) or {})
    base.case_cache_by_name = dict(getattr(app, "_customer_data_case_cache_by_name", base.case_cache_by_name) or {})
    base.selected_customer_name = str(getattr(app, "_selected_customer_name", base.selected_customer_name) or "")
    base.selected_cache_version = int(
        getattr(app, "_selected_customer_cache_version", base.selected_cache_version) or 0
    )
    return base


def apply_customer_data_state_to_app(app, state: CustomerDataPageState | None) -> CustomerDataPageState:
    cloned = clone_customer_data_page_state(state)
    app._customer_data_page_state = cloned
    app._customer_data_cache_version = int(cloned.cache_version or 0)
    app._customer_data_source_signature = str(cloned.source_signature or "")
    app._customer_data_customer_by_iid = dict(cloned.customer_by_iid or {})
    app._customer_data_case_by_iid = dict(cloned.case_by_iid or {})
    app._customer_data_case_cache_by_name = dict(cloned.case_cache_by_name or {})
    app._selected_customer_name = str(cloned.selected_customer_name or "")
    app._selected_customer_cache_version = int(cloned.selected_cache_version or 0)
    return cloned


def make_empty_customer_data_state() -> CustomerDataPageState:
    return CustomerDataPageState()
