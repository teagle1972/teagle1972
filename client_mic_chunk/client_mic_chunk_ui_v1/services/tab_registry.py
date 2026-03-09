from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def get_conversation_tab_registry_path(workspace_dir: Path) -> Path:
    root = workspace_dir / "Data" / "_tabs"
    root.mkdir(parents=True, exist_ok=True)
    return root / "tabs_registry.json"


def read_conversation_tab_registry_entries(path: Path) -> list[dict[str, str]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    items: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip()
        if not title:
            continue
        data_dir_text = str(item.get("data_dir", "") or "").strip()
        items.append({"title": title, "data_dir": data_dir_text})
    return items


def save_conversation_tab_registry_entries(path: Path, entries: list[dict[str, str]]) -> None:
    payload = json.dumps(entries, ensure_ascii=False, indent=2)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    bak_path = path.with_suffix(path.suffix + ".bak")
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        if path.exists():
            try:
                shutil.copy2(path, bak_path)
            except Exception:
                pass
        try:
            os.replace(tmp_path, path)
        except Exception:
            path.write_text(payload, encoding="utf-8")
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def write_conversation_tab_meta(data_dir: Path, title: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    meta_path = data_dir / "_tab_meta.json"
    meta_path.write_text(
        json.dumps({"title": str(title or "").strip() or data_dir.name}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
