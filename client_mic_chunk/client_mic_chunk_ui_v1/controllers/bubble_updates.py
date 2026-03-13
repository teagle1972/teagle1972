from __future__ import annotations

import tkinter as tk


def append_customer_profile_bubble_text(app, widget, active: dict[str, object], chunk: str) -> None:
    row = active.get("row")
    canvas = active.get("canvas")
    if (not isinstance(row, tk.Frame)) or (not isinstance(canvas, tk.Canvas)):
        return
    current = str(active.get("text", "") or "") + str(chunk or "")
    active["text"] = current
    row.configure(
        height=app._render_customer_profile_bubble_canvas(
            widget,
            canvas,
            header=str(active.get("header", "")),
            body=current,
            is_right=bool(active.get("is_right", False)),
        )
    )
    widget.see("end")
