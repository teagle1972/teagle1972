from __future__ import annotations

import tkinter as tk
from tkinter.scrolledtext import ScrolledText


def insert_customer_profile_bubble_row(
    app,
    widget: ScrolledText,
    *,
    header: str,
    body: str,
    is_right: bool,
    keep_active: bool,
) -> None:
    dialog = None
    for _attr in ("_conversation_customer_profile_dialog", "_conversation_intent_dialog", "_conversation_strategy_dialog"):
        _d = getattr(app, _attr, None)
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
    row.configure(height=app._render_customer_profile_bubble_canvas(widget, canvas, header, body, is_right))

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
