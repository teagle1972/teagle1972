from __future__ import annotations


def update_conversation_strategy_dialog_history_tags(history_widget) -> None:
    width = int(history_widget.winfo_width() or history_widget.winfo_reqwidth() or 900)
    side_gap = 14
    max_bubble_width = max(240, int(width * (2.0 / 3.0)))
    right_left_margin = max(side_gap, width - max_bubble_width - side_gap)
    left_right_margin = right_left_margin
    history_widget.tag_configure(
        "cs_left",
        justify="left",
        lmargin1=side_gap,
        lmargin2=side_gap,
        rmargin=left_right_margin,
        foreground="#6b7280",
        spacing1=6,
        spacing3=6,
    )
    history_widget.tag_configure(
        "cs_right",
        justify="right",
        lmargin1=right_left_margin,
        lmargin2=right_left_margin,
        rmargin=side_gap,
        foreground="#6b7280",
        spacing1=6,
        spacing3=6,
    )
    history_widget.tag_configure(
        "cs_right_bubble",
        justify="left",
        lmargin1=right_left_margin,
        lmargin2=right_left_margin,
        rmargin=side_gap,
        foreground="#111827",
        spacing1=6,
        spacing3=6,
    )
    history_widget.tag_configure(
        "cs_left_bubble",
        justify="left",
        lmargin1=side_gap,
        lmargin2=side_gap,
        rmargin=left_right_margin,
        foreground="#111827",
        spacing1=6,
        spacing3=6,
    )


def update_customer_profile_dialog_history_tags(history_widget) -> None:
    width = int(history_widget.winfo_width() or history_widget.winfo_reqwidth() or 900)
    side_gap = 16
    max_bubble_width = max(240, int(width * (2.0 / 3.0)))
    right_left_margin = max(side_gap, width - max_bubble_width - side_gap)
    left_right_margin = right_left_margin
    history_widget.tag_configure(
        "cs_right_bubble",
        justify="left",
        lmargin1=right_left_margin,
        lmargin2=right_left_margin,
        rmargin=side_gap,
        background="#e9eef3",
        foreground="#1f2937",
        borderwidth=1,
        relief="solid",
        spacing1=7,
        spacing3=8,
    )
    history_widget.tag_configure(
        "cs_left_bubble",
        justify="left",
        lmargin1=side_gap,
        lmargin2=side_gap,
        rmargin=left_right_margin,
        background="#f4f8ee",
        foreground="#1f2937",
        borderwidth=1,
        relief="solid",
        spacing1=7,
        spacing3=8,
    )
    history_widget.tag_configure(
        "cs_hint",
        justify="center",
        foreground="#6b7280",
        spacing1=10,
        spacing3=10,
    )
