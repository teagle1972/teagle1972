from __future__ import annotations

import tkinter.font as tkfont


def render_customer_profile_bubble_canvas(
    app,
    widget,
    canvas,
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
    wrapped_body = app._wrap_text_for_strategy_history_bubble(
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
    fill = "#e9eef3" if is_right else str(widget.cget("bg"))
    edge = "#c7d0db" if is_right else ""
    # Measure actual rendered height via a temporary text item.
    canvas.configure(width=bubble_w + 2, height=1, bg=str(widget.cget("bg")), bd=0, highlightthickness=0)
    canvas.delete("all")
    _tmp = canvas.create_text(14, 12, anchor="nw", text=content, font=font, width=text_w)
    _bbox = canvas.bbox(_tmp)
    canvas.delete(_tmp)
    bubble_h = max(40, (_bbox[3] + 12) if _bbox else int(len(content.split("\n")) * line_h + 24))
    canvas.configure(width=bubble_w + 2, height=bubble_h + 2, bd=0, highlightthickness=0)
    canvas.delete("all")
    app._draw_rounded_rect(canvas, 1, 1, bubble_w, bubble_h, 12, fill=fill, outline=edge, width=1)
    canvas.create_text(14, 12, anchor="nw", text=content, fill="#1f2937", font=font, width=text_w)
    return bubble_h + 6
