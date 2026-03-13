from __future__ import annotations

import tkinter.font as tkfont


def wrap_text_for_strategy_history_bubble(text: str, history_widget, max_width_px: int) -> str:
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
