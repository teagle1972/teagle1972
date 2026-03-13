from __future__ import annotations

from tkinter import messagebox


def submit_customer_profile_from_panel(_app) -> None:
    messagebox.showinfo("功能已移除", "设置页“客户画像”子窗口及相关功能已移除。")


def submit_workflow_from_panel(_app) -> None:
    messagebox.showinfo("功能已移除", "设置页“工作流程”子窗口及相关功能已移除。")


def generate_intents_from_settings(_app) -> None:
    messagebox.showinfo("功能已移除", "意图页面及其相关功能已移除。")


def submit_settings_panel_llm(_app, kind_label: str) -> None:
    messagebox.showinfo("功能已移除", f"设置页“{kind_label}”相关提交功能已移除。")


def open_customer_profile_dialog(_app) -> None:
    messagebox.showinfo("功能已移除", "设置页“客户画像”编辑功能已移除。")


def open_workflow_dialog(_app) -> None:
    messagebox.showinfo("功能已移除", "设置页“工作流程”编辑功能已移除。")
