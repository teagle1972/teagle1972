from __future__ import annotations

import json
import random
import re
from datetime import datetime
from pathlib import Path


PROFILE_HEADER = "### 客户画像 ###"
RECORDS_HEADER = "### 通话记录条目 ###"
CALL_RECORD_HEADER = "### 通话记录 ###"
SUMMARY_HEADER = "### 对话总结 ###"
COMMITMENTS_HEADER = "### 客户承诺-执行事项 ###"
STRATEGY_HEADER = "### 下一步对话策略 ###"
CALL_COST_LABEL = "call_cost"


_HEADER_ALIASES = {
    "profile": {PROFILE_HEADER, "### 客户画像###", "### 瀹㈡埛鐢诲儚 ###"},
    "records": {RECORDS_HEADER, "### 通话记录条目###", "### 閫氳瘽璁板綍鏉＄洰 ###"},
    "call_record": {CALL_RECORD_HEADER, "### 閫氳瘽璁板綍 ###"},
    "summary": {SUMMARY_HEADER, "### 瀵硅瘽鎬荤粨 ###"},
    "commitments": {COMMITMENTS_HEADER, "### 客户承-执事项 ###", "### 瀹㈡埛鎵胯-鎵ц浜嬮」 ###"},
    "strategy": {STRATEGY_HEADER, "### 一曰 ###", "### 涓嬩竴姝ヨ瘽绛?###"},
}


def _split_kv(line: str) -> tuple[str, str] | None:
    for sep in ("：", ":"):
        if sep in line:
            key, value = line.split(sep, 1)
            key = key.strip().rstrip("，,。；;")
            value = value.strip().rstrip("，,。；;")
            if key:
                return key, value
    return None


def parse_profile_kv_rows(raw_text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for raw_line in (raw_text or "").splitlines():
        line = raw_line.strip()
        if (not line) or line.startswith("["):
            continue
        row = _split_kv(line)
        if row is not None:
            rows.append(row)
    return rows


def resolve_customer_jsonl_path(workspace_dir: Path, ui_dir: Path, cwd: Path) -> Path | None:
    candidates = [
        workspace_dir / "customer.jsonl",
        ui_dir / "customer.jsonl",
        cwd / "customer.jsonl",
    ]
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists() and path.is_file():
            return path
    return None


def build_profile_text_from_slot_items(slot_items: list[object]) -> str:
    rows: list[str] = []
    for raw in slot_items:
        text = str(raw or "").strip()
        if not text:
            continue
        text = text.replace("<EOT>", "").strip()
        if "<FIELD>" in text:
            text = text.split("<FIELD>", 1)[1].strip()
        row = _split_kv(text)
        if row is None:
            continue
        left, right = row
        if "_" in left:
            prefix, maybe_key = left.split("_", 1)
            if prefix.isdigit():
                left = maybe_key.strip()
        if (not left) or (not right):
            continue
        rows.append(f"{left}：{right},")
    if not rows:
        return ""
    return "【客户画像】\n" + "\n".join(rows)


def pick_random_customer_profile_from_jsonl_path(jsonl_path: Path) -> str | None:
    candidates: list[list[object]] = []
    with jsonl_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = (raw_line or "").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            slots = obj.get("SLOTS")
            if isinstance(slots, list) and slots:
                candidates.append(slots)
    if not candidates:
        return None
    return build_profile_text_from_slot_items(random.choice(candidates))


def parse_datetime_to_epoch(ts_text: str) -> float:
    text = str(ts_text or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        return 0.0


def sanitize_filename_component(text: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", (text or "").strip())
    name = re.sub(r"\s+", "_", name)
    return name or "unknown_customer"


def extract_customer_name_from_profile_text(profile_text: str) -> str:
    rows = parse_profile_kv_rows(profile_text or "")
    preferred = {"客户姓名", "姓名", "customer_name", "name"}
    for key, value in rows:
        if key in preferred and value:
            return value.strip().rstrip(",，")
    for key, value in rows:
        key_l = key.lower()
        if (("客户" in key) and ("姓名" in key or "名称" in key)) or ("customer" in key_l and "name" in key_l):
            if value:
                return value.strip().rstrip(",，")
    return "unknown_customer"


def build_customer_case_text(
    customer_name: str,
    created_time: str,
    updated_time: str,
    profile_text: str,
    records: list[dict[str, str]],
) -> str:
    lines: list[str] = [
        f"客户名称：{customer_name}",
        f"创建时间：{created_time}",
        f"更新时间：{updated_time}",
        "",
        PROFILE_HEADER,
        (profile_text or "").strip(),
        "",
        RECORDS_HEADER,
    ]
    for entry in records:
        call_time = str(entry.get("call_time", "") or "").strip()
        call_cost = str(entry.get("call_cost", "") or "").strip()
        billing_duration = str(entry.get("billing_duration", "") or "").strip()
        price_per_minute = str(entry.get("price_per_minute", "") or "").strip()
        call_record = str(entry.get("call_record", "") or "").strip()
        summary = str(entry.get("summary", "") or "").strip()
        commitments = str(entry.get("commitments", "") or "").strip()
        strategy = str(entry.get("strategy", "") or "").strip()
        lines.extend(
            [
                "",
                ">>> 记录开始",
                f"通话时间：{call_time}",
                f"{CALL_COST_LABEL}: {call_cost}",
                f"billing_duration: {billing_duration}",
                f"price_per_minute: {price_per_minute}",
                CALL_RECORD_HEADER,
                call_record,
                "",
                SUMMARY_HEADER,
                summary,
                "",
                COMMITMENTS_HEADER,
                commitments,
                "",
                STRATEGY_HEADER,
                strategy,
                "<<< 记录结束",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _match_header(line: str, key: str) -> bool:
    return line in _HEADER_ALIASES.get(key, set())


def read_customer_case_file(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    record_data: dict[str, object] = {
        "customer_name": "",
        "created_time": "",
        "updated_time": "",
        "customer_profile": "",
        "records": [],
        "path": str(path),
    }

    section_start = len(lines)
    for idx, line in enumerate(lines):
        if line.startswith("### ") or line.startswith(">>> "):
            section_start = idx
            break

    for line in lines[:section_start]:
        kv = _split_kv(line)
        if kv is None:
            continue
        key, value = kv
        key_l = key.lower()
        if (not record_data["customer_name"]) and ((("客户" in key) and ("名称" in key or "姓名" in key)) or ("customer" in key_l and "name" in key_l)):
            record_data["customer_name"] = value
        elif (not record_data["created_time"]) and (("创建" in key) or ("created" in key_l)):
            record_data["created_time"] = value
        elif (not record_data["updated_time"]) and (("更新" in key) or ("updated" in key_l) or ("最后通话" in key)):
            record_data["updated_time"] = value

    current_block = ""
    buffer: list[str] = []
    current_entry: dict[str, str] | None = None
    all_entries: list[dict[str, str]] = []

    def _new_entry() -> dict[str, str]:
        return {"call_time": "", "call_cost": "", "billing_duration": "", "price_per_minute": "", "call_record": "", "summary": "", "commitments": "", "strategy": ""}

    def _flush_block() -> None:
        nonlocal buffer, current_block, current_entry
        value = "\n".join(buffer).strip()
        if current_block == "profile":
            record_data["customer_profile"] = value
        elif current_entry is not None and current_block in {"call_record", "summary", "commitments", "strategy"}:
            current_entry[current_block] = value
        buffer = []

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith(">>>"):
            _flush_block()
            if current_entry is not None:
                all_entries.append(current_entry)
            current_entry = _new_entry()
            current_block = ""
            continue
        if stripped.startswith("<<<"):
            _flush_block()
            if current_entry is not None:
                all_entries.append(current_entry)
                current_entry = None
            current_block = ""
            continue

        kv = _split_kv(stripped)
        if kv is not None:
            k, v = kv
            k_l = k.lower()
            if "通话时间" in k or k_l in {"call_time", "time"}:
                if current_entry is None:
                    current_entry = _new_entry()
                current_entry["call_time"] = v
                continue
            if k_l in {"call_cost", "cost", "fee"}:
                if current_entry is None:
                    current_entry = _new_entry()
                current_entry["call_cost"] = v.replace("楼", "¥")
                continue
            if k_l == "billing_duration":
                if current_entry is None:
                    current_entry = _new_entry()
                current_entry["billing_duration"] = v
                continue
            if k_l == "price_per_minute":
                if current_entry is None:
                    current_entry = _new_entry()
                current_entry["price_per_minute"] = v
                continue

        _flush_before_switch = False
        if _match_header(stripped, "profile"):
            _flush_before_switch = True
            next_block = "profile"
        elif _match_header(stripped, "call_record"):
            _flush_before_switch = True
            next_block = "call_record"
        elif _match_header(stripped, "summary"):
            _flush_before_switch = True
            next_block = "summary"
        elif _match_header(stripped, "commitments"):
            _flush_before_switch = True
            next_block = "commitments"
        elif _match_header(stripped, "strategy"):
            _flush_before_switch = True
            next_block = "strategy"
        else:
            next_block = ""

        if _flush_before_switch:
            _flush_block()
            if next_block in {"call_record", "summary", "commitments", "strategy"} and current_entry is None:
                current_entry = _new_entry()
            current_block = next_block
            continue

        if current_block:
            buffer.append(line)

    _flush_block()
    if current_entry is not None:
        all_entries.append(current_entry)

    # 清理空记录
    cleaned: list[dict[str, str]] = []
    for entry in all_entries:
        if any(str(entry.get(k, "") or "").strip() for k in ("call_time", "call_record", "summary", "commitments", "strategy", "call_cost")):
            cleaned.append(
                {
                    "call_time": str(entry.get("call_time", "") or "").strip(),
                    "call_cost": str(entry.get("call_cost", "") or "").strip(),
                    "billing_duration": str(entry.get("billing_duration", "") or "").strip(),
                    "price_per_minute": str(entry.get("price_per_minute", "") or "").strip(),
                    "call_record": str(entry.get("call_record", "") or "").strip(),
                    "summary": str(entry.get("summary", "") or "").strip(),
                    "commitments": str(entry.get("commitments", "") or "").strip(),
                    "strategy": str(entry.get("strategy", "") or "").strip(),
                }
            )

    record_data["records"] = cleaned

    stat = path.stat()
    customer_name = str(record_data.get("customer_name", "")).strip()
    if not customer_name:
        customer_name = path.stem.split("_", 1)[0] if "_" in path.stem else path.stem
        record_data["customer_name"] = customer_name
    created_time = str(record_data.get("created_time", "")).strip()
    updated_time = str(record_data.get("updated_time", "")).strip()
    if not created_time:
        created_time = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        record_data["created_time"] = created_time
    if not updated_time:
        updated_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        record_data["updated_time"] = updated_time

    return record_data


def save_customer_case_file(
    path: Path,
    customer_name: str,
    created_time: str,
    updated_time: str,
    profile_text: str,
    records: list[dict[str, str]],
) -> None:
    content = build_customer_case_text(
        customer_name=customer_name,
        created_time=created_time,
        updated_time=updated_time,
        profile_text=profile_text,
        records=records,
    )
    path.write_text(content, encoding="utf-8")
