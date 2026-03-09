from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

_SCROLLBAR_STYLE = "App.Vertical.TScrollbar"


class TtlScrolledText(ScrolledText):
    """ScrolledText backed by ttk.Scrollbar instead of tk.Scrollbar.

    All existing ``isinstance(w, ScrolledText)`` checks continue to pass
    because this class inherits from ScrolledText.
    """

    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        # ScrolledText already created a tk.Scrollbar in self.vbar.
        # Remove it and replace with a styled ttk.Scrollbar.
        self.vbar.pack_forget()
        self.vbar.destroy()
        self.vbar = ttk.Scrollbar(
            self.frame,
            orient=tk.VERTICAL,
            command=self.yview,
            style=_SCROLLBAR_STYLE,
        )
        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.configure(yscrollcommand=self.vbar.set)
