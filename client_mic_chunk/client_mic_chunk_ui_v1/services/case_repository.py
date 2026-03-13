from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable
import unicodedata


def normalize_customer_lookup_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    cleaned_chars: list[str] = []
    for ch in normalized:
        if ch in {"\ufeff", "\u200b", "\u200c", "\u200d", "\u2060"}:
            continue
        if unicodedata.category(ch).startswith("C"):
            continue
        if ch.isspace():
            continue
        cleaned_chars.append(ch)
    return "".join(cleaned_chars).strip()


def lookup_case_payload_by_name(cache: dict[str, object], customer_name: str) -> dict[str, object] | None:
    if not isinstance(cache, dict):
        return None
    target_name = normalize_customer_lookup_key(customer_name)
    if not target_name:
        return None
    direct = cache.get(target_name)
    if isinstance(direct, dict):
        return direct
    for key, value in cache.items():
        if normalize_customer_lookup_key(str(key or "")) == target_name and isinstance(value, dict):
            return value
    return None


def get_case_source_dirs(app, preferred_dir: Path | None = None) -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()
    candidates: list[Path] = []
    if isinstance(preferred_dir, Path):
        candidates.append(preferred_dir)
    else:
        current_dir = app._get_data_dir()
        if isinstance(current_dir, Path):
            candidates.append(current_dir)
    for path in candidates:
        try:
            normalized = str(path.resolve())
        except Exception:
            normalized = str(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        if path.exists() and path.is_dir():
            dirs.append(path)
    return dirs


def iter_case_files(app, preferred_dir: Path | None = None) -> list[Path]:
    file_map: dict[str, Path] = {}
    for data_dir in get_case_source_dirs(app, preferred_dir=preferred_dir):
        for path in data_dir.glob("*.txt"):
            key = str(path.resolve()) if path.exists() else str(path)
            file_map[key] = path
    return sorted(file_map.values(), key=lambda p: p.stat().st_mtime, reverse=True)


def build_customer_case_cache_by_name_from_dir(app, data_dir: Path | None) -> dict[str, dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    files = iter_case_files(app, preferred_dir=data_dir)
    for path in files:
        try:
            case_data = app._read_customer_case_file(path)
        except Exception as exc:
            app._append_line(
                app.log_text,
                f"[{datetime.now().strftime('%H:%M:%S')}] [CUSTOMER_DATA] read failed: {path.name} {exc}",
            )
            continue
        customer_name = normalize_customer_lookup_key(str(case_data.get("customer_name", "未知客户") or "未知客户"))
        if not customer_name:
            customer_name = normalize_customer_lookup_key(path.stem.rsplit("_", 1)[0] if "_" in path.stem else path.stem) or "未知客户"
        profile_text = str(case_data.get("customer_profile", "") or "")
        created_time = str(case_data.get("created_time", "") or "")
        updated_time = str(case_data.get("updated_time", "") or "")
        records = list(case_data.get("records", []))

        payload = grouped.get(customer_name)
        if payload is None:
            payload = {
                "customer_name": customer_name,
                "customer_profile": profile_text,
                "created_time": created_time,
                "updated_time": updated_time,
                "records": [],
            }
            grouped[customer_name] = payload
        else:
            if (not str(payload.get("customer_profile", "")).strip()) and profile_text.strip():
                payload["customer_profile"] = profile_text
            existing_created = str(payload.get("created_time", "") or "")
            if (not existing_created) or (
                created_time and app._parse_datetime_to_epoch(created_time) < app._parse_datetime_to_epoch(existing_created)
            ):
                payload["created_time"] = created_time
            existing_updated = str(payload.get("updated_time", "") or "")
            if app._parse_datetime_to_epoch(updated_time) > app._parse_datetime_to_epoch(existing_updated):
                payload["updated_time"] = updated_time

        merged_records = payload.get("records", [])
        if isinstance(merged_records, list):
            for entry in records:
                merged_records.append(
                    {
                        "call_time": str(entry.get("call_time", "") or ""),
                        "call_cost": str(entry.get("call_cost", "") or ""),
                        "billing_duration": str(entry.get("billing_duration", "") or ""),
                        "billing_duration_seconds": str(entry.get("billing_duration_seconds", "") or ""),
                        "price_per_minute": str(entry.get("price_per_minute", "") or ""),
                        "call_record": str(entry.get("call_record", "") or ""),
                        "summary": str(entry.get("summary", "") or ""),
                        "commitments": str(entry.get("commitments", "") or ""),
                        "strategy": str(entry.get("strategy", "") or ""),
                    }
                )
    return grouped


def _build_call_record_id(path_text: str, entry_index: str) -> str:
    return f"{str(path_text or '').strip()}::{str(entry_index or '').strip()}"


def build_visible_customer_record_indices(app, records: list[dict[str, str]]) -> list[int]:
    normalized_records = list(records or [])
    if len(normalized_records) <= 1:
        return []
    earliest_index = min(
        range(len(normalized_records)),
        key=lambda idx: (
            app._parse_datetime_to_epoch(str(normalized_records[idx].get("call_time", "") or "")),
            idx,
        ),
    )
    return [idx for idx in range(len(normalized_records)) if idx != earliest_index]


def build_visible_customer_records(app, records: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized_records = list(records or [])
    return [normalized_records[idx] for idx in build_visible_customer_record_indices(app, normalized_records)]


def build_call_record_items(app, *, log_debug: Callable[[str], None] | None = None) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    files = iter_case_files(app)
    if callable(log_debug):
        log_debug(
            "call-record source-files "
            f"count={len(files)} "
            f"dirs={[str(p) for p in get_case_source_dirs(app)]}",
        )
    for path in files:
        try:
            case_data = app._read_customer_case_file(path)
        except Exception as exc:
            app._append_line(
                app.log_text,
                f"[{datetime.now().strftime('%H:%M:%S')}] [CALL_RECORD] read failed: {path.name} {exc}",
            )
            continue
        customer_name = str(case_data.get("customer_name", "未知客户"))
        profile_text = str(case_data.get("customer_profile", "") or "")
        records = list(case_data.get("records", []))
        for idx in build_visible_customer_record_indices(app, records):
            entry = records[idx]
            call_time = str(entry.get("call_time", "") or "").strip() or str(case_data.get("updated_time", "") or "")
            call_cost_text = str(entry.get("call_cost", "") or "").strip()
            billing_duration_text = str(entry.get("billing_duration", "") or "").strip() or "-"
            price_per_minute_text = str(entry.get("price_per_minute", "") or "").strip() or "-"
            items.append(
                {
                    "record_id": _build_call_record_id(str(path), str(idx)),
                    "customer_name": customer_name,
                    "last_call_time": call_time or "-",
                    "call_cost": call_cost_text,
                    "billing_duration": billing_duration_text,
                    "price_per_minute": price_per_minute_text,
                    "customer_profile": profile_text,
                    "call_record": str(entry.get("call_record", "") or ""),
                    "summary": str(entry.get("summary", "") or ""),
                    "commitments": str(entry.get("commitments", "") or ""),
                    "strategy": str(entry.get("strategy", "") or ""),
                    "path": str(path),
                    "entry_index": str(idx),
                }
            )
    items.sort(key=lambda item: app._parse_datetime_to_epoch(item.get("last_call_time", "")), reverse=True)
    return items


def read_customer_case_data_from_files(app, customer_name: str, *, data_dir: Path | None = None) -> dict[str, object] | None:
    target_name = normalize_customer_lookup_key(customer_name)
    if not target_name:
        return None
    files = iter_case_files(app, preferred_dir=data_dir)
    matched_by_filename: Path | None = None
    for path in files:
        stem_name = path.stem.rsplit("_", 1)[0]
        if normalize_customer_lookup_key(stem_name) == target_name:
            matched_by_filename = path
            break
    if matched_by_filename is not None:
        try:
            payload = app._read_customer_case_file(matched_by_filename)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    for path in files:
        try:
            payload = app._read_customer_case_file(path)
        except Exception:
            continue
        payload_name = normalize_customer_lookup_key(str(payload.get("customer_name", "") or ""))
        if payload_name == target_name:
            return payload
    try:
        cache_by_name = build_customer_case_cache_by_name_from_dir(app, data_dir)
    except Exception:
        return None
    payload = lookup_case_payload_by_name(cache_by_name, target_name)
    if isinstance(payload, dict):
        return payload
    return None


def build_customer_case_cache_by_name(app) -> dict[str, dict[str, object]]:
    return build_customer_case_cache_by_name_from_dir(app, None)
