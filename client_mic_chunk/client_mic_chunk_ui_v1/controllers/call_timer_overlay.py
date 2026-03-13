"""call_timer_overlay.py – 通话计时浮窗

收到 TTS 首包后弹出一个可拖动的圆形悬浮计时窗口，
以秒为单位（MM:SS 格式）显示本次通话时长。

公开 API：
    overlay = CallTimerOverlay(master_tk)
    overlay.start()   # 弹窗并开始计时
    overlay.freeze()  # 停止计时，窗口保留（通话结束时调用）
    overlay.stop()    # 销毁弹窗并归零（右键菜单"退出"时调用）
"""
from __future__ import annotations

import tkinter as tk

# ── 外观常量 ───────────────────────────────────────────────────────────────────
_CHROMA_KEY   = "#010101"   # 透明抠色（Windows -transparentcolor）
_SIZE         = 120         # 圆形直径，单位 px
_PAD          = 10          # 圆外留白（用于发光晕圈）
_TICK_MS      = 1000        # 每秒刷新

# 配色方案：暗夜极光
_C_GLOW       = ["#003355", "#00446e", "#005588", "#0066a0"]  # 4 层光晕
_C_MAIN_BG    = "#0b1829"   # 主圆底色（深海蓝）
_C_RING       = "#00ccff"   # 主环描边（青蓝）
_C_INNER_RING = "#0099bb"   # 内环（细线，层次感）
_C_HIGHLIGHT  = "#1a3a5c"   # 顶部高光弧（3D 效果）
_C_DOT_RED    = "#ff4444"   # 录音状态点（通话中）
_C_DOT_GRAY   = "#556677"   # 录音状态点（已结束）
_C_LABEL      = "#7ecfee"   # "通话中" 小字
_C_LABEL_END  = "#445566"   # "已结束" 小字
_C_TIMER      = "#ffffff"   # 计时数字（通话中）
_C_TIMER_END  = "#778899"   # 计时数字（已结束）


class CallTimerOverlay:
    """可拖动圆形通话计时浮窗。"""

    def __init__(self, master: tk.Tk) -> None:
        self._master      = master
        self._win:        tk.Toplevel | None = None
        self._canvas:     tk.Canvas   | None = None
        self._text_item:  int | None         = None
        self._label_item: int | None         = None
        self._dot_item:   int | None         = None
        self._elapsed     = 0
        self._after_id:   str | None         = None
        self._drag_offset: tuple[int, int] | None = None

    # ── 公开 API ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """弹出计时窗口并从 0 开始计时。"""
        self.stop()
        self._elapsed = 0
        self._create_window()
        self._tick()

    def freeze(self) -> None:
        """停止计时，窗口保留，外观切换为"已结束"样式。"""
        if self._after_id is not None:
            try:
                self._master.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

        canvas = self._canvas
        if canvas is None:
            return
        try:
            if self._dot_item is not None:
                canvas.itemconfig(self._dot_item, fill=_C_DOT_GRAY)
            if self._label_item is not None:
                canvas.itemconfig(self._label_item, text="已结束", fill=_C_LABEL_END)
            if self._text_item is not None:
                canvas.itemconfig(self._text_item, fill=_C_TIMER_END)
        except Exception:
            pass

    def stop(self) -> None:
        """停止计时并销毁窗口。"""
        if self._after_id is not None:
            try:
                self._master.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

        if self._win is not None:
            try:
                if self._win.winfo_exists():
                    self._win.destroy()
            except Exception:
                pass
            self._win = None

        self._canvas     = None
        self._text_item  = None
        self._label_item = None
        self._dot_item   = None
        self._elapsed    = 0
        self._drag_offset = None

    # ── 内部：创建窗口 ────────────────────────────────────────────────────────

    def _create_window(self) -> None:
        sz  = _SIZE
        pad = _PAD
        win_sz = sz + pad * 2          # 窗口总尺寸（含光晕留白）
        cx = cy = win_sz // 2          # 画布中心

        screen_w = int(self._master.winfo_screenwidth()  or 1920)
        screen_h = int(self._master.winfo_screenheight() or 1080)
        pos_x = screen_w - win_sz - screen_w // 20   # 距右边 1/20 屏宽
        pos_y = screen_h // 10                        # 距顶部 1/10 屏高

        win = tk.Toplevel(self._master)
        win.title("")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.configure(bg=_CHROMA_KEY)
        try:
            win.attributes("-transparentcolor", _CHROMA_KEY)
        except Exception:
            pass
        win.geometry(f"{win_sz}x{win_sz}+{pos_x}+{pos_y}")
        win.lift()

        canvas = tk.Canvas(
            win,
            width=win_sz, height=win_sz,
            bg=_CHROMA_KEY,
            highlightthickness=0, bd=0,
        )
        canvas.pack()

        r_main = sz // 2   # 主圆半径

        # ── 绘制图层（从外向内） ───────────────────────────────────────────────

        # 4 层渐变发光晕圈
        for i, glow_color in enumerate(_C_GLOW):
            r = r_main + pad - i * 2
            canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=glow_color, outline="",
            )

        # 主圆底色
        canvas.create_oval(
            cx - r_main, cy - r_main, cx + r_main, cy + r_main,
            fill=_C_MAIN_BG, outline="",
        )

        # 顶部高光弧（模拟球面反光）
        r_hl = r_main - 6
        canvas.create_arc(
            cx - r_hl, cy - r_hl, cx + r_hl, cy + r_hl,
            start=35, extent=110,
            fill=_C_HIGHLIGHT, outline="", style=tk.CHORD,
        )

        # 外环描边（青蓝主环）
        canvas.create_oval(
            cx - r_main, cy - r_main, cx + r_main, cy + r_main,
            fill="", outline=_C_RING, width=2,
        )

        # 内环细线
        r_inner = r_main - 7
        canvas.create_oval(
            cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner,
            fill="", outline=_C_INNER_RING, width=1,
        )

        # ── 文字图层 ───────────────────────────────────────────────────────────

        # 录音状态红点
        dot_item = canvas.create_oval(
            cx - 4, cy - 26, cx + 4, cy - 18,
            fill=_C_DOT_RED, outline="",
        )

        # "通话中" 小标签
        label_item = canvas.create_text(
            cx, cy - 8,
            text="通话中",
            fill=_C_LABEL,
            font=("微软雅黑", 7),
        )

        # 计时数字（会随 tick 更新）
        text_item = canvas.create_text(
            cx, cy + 14,
            text="00:00",
            fill=_C_TIMER,
            font=("微软雅黑", 17, "bold"),
        )

        self._win        = win
        self._canvas     = canvas
        self._text_item  = text_item
        self._label_item = label_item
        self._dot_item   = dot_item

        # ── 右键菜单 ──────────────────────────────────────────────────────────

        menu = tk.Menu(win, tearoff=0)
        menu.add_command(label="退出", command=self.stop)

        def _show_menu(event) -> None:
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        canvas.bind("<ButtonPress-3>", _show_menu)

        # ── 拖动支持 ──────────────────────────────────────────────────────────

        def _on_press(event) -> None:
            try:
                self._drag_offset = (
                    int(event.x_root) - int(win.winfo_x()),
                    int(event.y_root) - int(win.winfo_y()),
                )
            except Exception:
                self._drag_offset = None

        def _on_drag(event) -> None:
            if not isinstance(self._drag_offset, tuple):
                return
            try:
                nx = int(event.x_root) - self._drag_offset[0]
                ny = int(event.y_root) - self._drag_offset[1]
                win.geometry(f"+{max(0, nx)}+{max(0, ny)}")
            except Exception:
                pass

        def _on_release(_event=None) -> None:
            self._drag_offset = None

        canvas.bind("<ButtonPress-1>",  _on_press)
        canvas.bind("<B1-Motion>",      _on_drag)
        canvas.bind("<ButtonRelease-1>", _on_release)

    # ── 内部：计时刷新 ────────────────────────────────────────────────────────

    def _tick(self) -> None:
        win    = self._win
        canvas = self._canvas
        if win is None or canvas is None:
            return
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return

        m, s = divmod(self._elapsed, 60)
        time_str = f"{m:02d}:{s:02d}"

        if self._text_item is not None:
            try:
                canvas.itemconfig(self._text_item, text=time_str)
            except Exception:
                pass

        self._elapsed += 1
        self._after_id = self._master.after(_TICK_MS, self._tick)
