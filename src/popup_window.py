"""
Pry 弹窗通知模块 — 统一暗色主题、自适应尺寸、智能显示时长
"""
import tkinter as tk
import queue
import time
import ctypes
import os
import re
from PIL import Image
import pystray
from pystray import MenuItem as item

try:
    # 强制开启最高等级的 DPI 适配 (Per Monitor DPI Aware)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


# ========== 配置 ==========

# 统一暗色主题
THEME = {
    "bg": "#1A1A2E",           # 深色背景
    "bg_card": "#16213E",      # 卡片背景（稍浅）
    "fg": "#E8E8E8",           # 主文本颜色
    "fg_dim": "#8A8A9A",       # 次要文本颜色
    "accent": "#0F3460",       # 强调色（边框）
    "highlight": "#E94560",    # 高亮色（进度条）
    "border_radius": 12,       # 圆角半径（模拟）
}

# Action 映射为更有意义的标题
ACTION_LABELS = {
    "suggest": "💡 回复建议",
    "roast":   "🔥 吐槽时间",
    "think":   "💭 深度洞察",
    "vibe":    "🎵 氛围感知",
    "warn":    "⚠️ 风险预警",
}

# 弹窗参数
POPUP_WIDTH = 380
POPUP_MIN_HEIGHT = 70
POPUP_MAX_HEIGHT = 280
POPUP_MARGIN_RIGHT = 24
POPUP_MARGIN_BOTTOM = 48
FONT_FAMILY = "Microsoft YaHei UI"
FONT_SIZE_TITLE = 10
FONT_SIZE_BODY = 11


class PopupWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # 隐藏主窗口
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)

        self.queue = queue.Queue()
        self._current_popup = None  # 当前活跃弹窗引用
        self._fade_out_id = None   # 当前自动关闭的 after id

    # ========== 公开接口 ==========

    def show(self, action, content):
        """主入口，将消息入队（线程安全）"""
        self.queue.put({"action": action, "content": content})

    def start(self):
        """启动 UI 主循环（必须在主线程调用）"""
        self._setup_tray()
        self._run_loop()
        self.root.mainloop()

    # ========== 弹窗创建 ==========

    def _dismiss_current(self):
        """立即销毁当前活跃弹窗"""
        if self._current_popup and self._current_popup.winfo_exists():
            # 取消自动关闭定时器
            if self._fade_out_id:
                try:
                    self._current_popup.after_cancel(self._fade_out_id)
                except Exception:
                    pass
                self._fade_out_id = None
            self._current_popup.destroy()
        self._current_popup = None

    def _create_popup(self, action, content):
        """创建一个新弹窗，自动关闭旧弹窗"""
        # 先关闭旧弹窗
        self._dismiss_current()

        label_text = ACTION_LABELS.get(action, f"💬 {action}")

        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.0)
        popup.configure(bg=THEME["bg"])

        # ---- 内容布局 ----
        # 外层容器（带边框颜色模拟）
        outer = tk.Frame(popup, bg=THEME["accent"], padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        card = tk.Frame(outer, bg=THEME["bg_card"], padx=16, pady=12)
        card.pack(fill=tk.BOTH, expand=True)

        # 标题行
        header_frame = tk.Frame(card, bg=THEME["bg_card"])
        header_frame.pack(fill=tk.X)

        tk.Label(
            header_frame, text=label_text,
            font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
            bg=THEME["bg_card"], fg=THEME["fg_dim"],
            anchor="w"
        ).pack(side=tk.LEFT)

        # 关闭按钮 ×
        close_btn = tk.Label(
            header_frame, text="✕",
            font=(FONT_FAMILY, 9),
            bg=THEME["bg_card"], fg=THEME["fg_dim"],
            cursor="hand2"
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self._fade_out(popup))

        # 分隔线
        tk.Frame(card, bg=THEME["accent"], height=1).pack(fill=tk.X, pady=(8, 8))

        # 内容文本
        content_label = tk.Label(
            card, text=content,
            font=(FONT_FAMILY, FONT_SIZE_BODY),
            bg=THEME["bg_card"], fg=THEME["fg"],
            justify=tk.LEFT, anchor="nw",
            wraplength=POPUP_WIDTH - 36  # 减去两侧 padding
        )
        content_label.pack(fill=tk.BOTH, expand=True, anchor="nw")

        # suggest 类型显示复制提示
        if action == "suggest":
            tk.Label(
                card, text="点击复制",
                font=(FONT_FAMILY, 8),
                bg=THEME["bg_card"], fg=THEME["fg_dim"],
                anchor="e"
            ).pack(fill=tk.X, pady=(4, 0))

        # 进度条（显示剩余时间）
        progress_frame = tk.Frame(card, bg=THEME["bg_card"], height=3)
        progress_frame.pack(fill=tk.X, pady=(8, 0))
        progress_bar = tk.Frame(progress_frame, bg=THEME["highlight"], height=3)
        progress_bar.place(relwidth=1.0, relheight=1.0)

        # ---- 计算自适应尺寸 ----
        popup.update_idletasks()  # 让 tk 计算实际所需尺寸
        needed_height = card.winfo_reqheight() + 2  # +2 for outer border
        height = max(POPUP_MIN_HEIGHT, min(needed_height, POPUP_MAX_HEIGHT))

        # ---- 定位：右下角 ----
        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()
        x = screen_w - POPUP_WIDTH - POPUP_MARGIN_RIGHT
        y = screen_h - height - POPUP_MARGIN_BOTTOM
        popup.geometry(f"{POPUP_WIDTH}x{height}+{x}+{y}")

        # ---- 点击复制功能 (suggest) ----
        if action == "suggest":
            def on_click(e):
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(content)
                    content_label.config(text="✅ 已复制到剪贴板")
                    popup.after(800, lambda: self._fade_out(popup))
                except Exception:
                    pass

            popup.bind("<Button-1>", on_click)
            content_label.bind("<Button-1>", on_click)
            card.bind("<Button-1>", on_click)
        else:
            popup.bind("<Button-1>", lambda e: self._fade_out(popup))

        # ---- 智能显示时长 ----
        # 基础 5 秒 + 每 20 个字符 +1 秒，最长 15 秒
        display_seconds = min(5 + len(content) // 20, 15)
        display_ms = display_seconds * 1000

        # ---- 进度条动画 ----
        self._animate_progress(progress_bar, display_ms)

        # ---- 淡入 ----
        self._fade_in(popup)

        # ---- 定时自动关闭 ----
        self._fade_out_id = popup.after(display_ms, lambda: self._fade_out(popup))

        # 记录当前弹窗
        self._current_popup = popup

    # ========== 动画 ==========

    def _fade_in(self, window):
        """淡入动画"""
        alpha = [0.0]

        def step():
            if not window.winfo_exists():
                return
            if alpha[0] < 0.95:
                alpha[0] += 0.06
                window.attributes("-alpha", min(alpha[0], 0.95))
                window.after(12, step)
            else:
                window.attributes("-alpha", 0.95)

        step()

    def _fade_out(self, window):
        """淡出动画"""
        if not window.winfo_exists():
            return
        alpha = [float(window.attributes("-alpha"))]

        def step():
            if alpha[0] > 0.05:
                alpha[0] -= 0.06
                if window.winfo_exists():
                    window.attributes("-alpha", max(alpha[0], 0.0))
                    window.after(12, step)
            else:
                if window.winfo_exists():
                    window.destroy()
                if self._current_popup == window:
                    self._current_popup = None

        step()

    def _animate_progress(self, bar, total_ms):
        """进度条从满到空动画"""
        start_time = time.time()
        total_s = total_ms / 1000.0

        def step():
            if not bar.winfo_exists():
                return
            elapsed = time.time() - start_time
            ratio = max(0, 1.0 - elapsed / total_s)
            bar.place(relwidth=ratio, relheight=1.0)
            if ratio > 0:
                bar.after(50, step)

        step()

    # ========== 事件循环 ==========

    def _run_loop(self):
        """检测队列并处理显示"""
        try:
            while True:
                msg = self.queue.get_nowait()
                self._create_popup(msg["action"], msg["content"])
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._run_loop)

    # ========== 系统托盘 ==========

    def _setup_tray(self):
        """初始化系统托盘"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ico_path = os.path.join(base_dir, "src", "pry.ico")

        if os.path.exists(ico_path):
            icon_img = Image.open(ico_path)
        else:
            icon_img = Image.new('RGB', (64, 64), color=(15, 52, 96))

        def on_exit(icon, item):
            icon.stop()
            self.root.quit()
            os._exit(0)

        menu = (
            item('Pry 运行中 🕶️', lambda: None, enabled=False),
            item('退出', on_exit),
        )

        self.tray = pystray.Icon("pry", icon_img, "Pry", menu)
        self.tray.run_detached()


# ========== 独立测试 ==========

if __name__ == "__main__":
    import threading

    pw = PopupWindow()

    def test_msgs():
        time.sleep(1)

        # 测试 1: 短内容
        pw.show("suggest", "试试回：好哒，没问题")
        time.sleep(3)

        # 测试 2: 中等内容（应该替换掉上一个）
        pw.show("roast", "这人的回复也太敷衍了吧？就一个'嗯'字打发你？你值得更走心的回复。")
        time.sleep(4)

        # 测试 3: 长内容（验证自适应高度和更长显示时间）
        pw.show("think",
                "我注意到对方最近三条消息的回复间隔越来越长（从2分钟到15分钟），"
                "而且语气从热情变得很敷衍。结合之前的聊天记录来看，"
                "对方可能正在忙别的事情，或者对当前话题失去了兴趣。"
                "建议换一个对方可能感兴趣的话题试试。")
        time.sleep(6)

        # 测试 4: 警告
        pw.show("warn", "对方的措辞带有明显的情绪操控迹象，注意保护自己的边界。")

    threading.Thread(target=test_msgs, daemon=True).start()
    pw.start()
