from __future__ import annotations

from tkinter import ttk


def resize_profile_table_columns(app, tree: ttk.Treeview) -> None:
    width = tree.winfo_width()
    if width <= 0:
        return
    content_width = max(width - 24, 660)
    col_width = max(content_width // 6, 110)
    for col in ("field_1", "value_1", "field_2", "value_2", "field_3", "value_3"):
        tree.column(col, width=col_width)


def fill_profile_table_from_text(
    app,
    tree: ttk.Treeview,
    profile_text: str,
    empty_message: str = "暂无客户画像数据",
    auto_height: bool = False,
) -> None:
    rows = app._parse_profile_kv_rows(profile_text)
    app._resize_profile_table_columns(tree)
    tree.delete(*tree.get_children())
    if auto_height:
        tree.configure(height=max(4, len(rows) + 1))
    if not rows:
        tree.insert("", "end", values=(empty_message, "", "", "", "", ""), tags=("profile_even",))
        return
    idx = 0
    while idx < len(rows):
        key_1, value_1 = rows[idx]
        if idx + 1 < len(rows):
            key_2, value_2 = rows[idx + 1]
        else:
            key_2, value_2 = "", ""
        if idx + 2 < len(rows):
            key_3, value_3 = rows[idx + 2]
        else:
            key_3, value_3 = "", ""
        tag = "profile_even" if (idx // 3) % 2 == 0 else "profile_odd"
        tree.insert("", "end", values=(key_1, value_1, key_2, value_2, key_3, value_3), tags=(tag,))
        idx += 3


def resize_dialog_profile_columns(app) -> None:
    tree = app.dialog_profile_table
    app._resize_profile_table_columns(tree)


def resize_customer_data_profile_columns(app) -> None:
    tree = app.customer_data_profile_table
    if isinstance(tree, ttk.Treeview):
        app._resize_profile_table_columns(tree)


def refresh_dialog_profile_table(app) -> None:
    profile_text = app.customer_profile_text.get("1.0", "end-1c") or ""
    app._fill_profile_table_from_text(app.dialog_profile_table, profile_text=profile_text, auto_height=True)
