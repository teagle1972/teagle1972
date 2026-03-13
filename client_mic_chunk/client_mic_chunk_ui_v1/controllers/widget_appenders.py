from __future__ import annotations

from tkinter.scrolledtext import ScrolledText


def append_text_to_widget_with_tag(app, widget, text: str, tag: str) -> None:
    if (not text) or (not isinstance(widget, ScrolledText)):
        return
    if app._try_append_customer_profile_bubble(widget, text, tag):
        return
    try:
        widget.configure(state="normal")
        widget.insert("end", text, (tag,))
        widget.see("end")
    except Exception:
        return
