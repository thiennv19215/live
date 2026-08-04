"""Dashboard desktop phím bấm Cyber Control Deck cao cấp v3.1 cho tiktok_obs_controller.py."""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import tiktok_obs_controller as core

# Color Palette System
BG_DARK = "#080c14"
PANEL_BG = "#121a29"
PANEL_BORDER = "#1e2c42"
CARD_BG = "#172338"
CARD_HOVER = "#20304d"
TEXT_MAIN = "#f8fafc"
TEXT_MUTED = "#94a3b8"
TEXT_DARK = "#64748b"

COLOR_CYAN = "#00f2fe"
COLOR_EMERALD = "#10b981"
COLOR_AMBER = "#f59e0b"
COLOR_ROSE = "#f43f5e"
COLOR_PURPLE = "#a855f7"
COLOR_BLUE = "#3b82f6"


class ColorLogHandler(logging.Handler):
    """Handler đệm log và hỗ trợ phân loại màu trong console GUI."""

    def __init__(self, output: queue.Queue[tuple[str, str]]) -> None:
        super().__init__()
        self.output = output

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        level = record.levelname.lower()
        if "phat qua" in msg.lower() or "them vao queue" in msg.lower() or "action video" in msg.lower():
            tag = "gift"
        elif level in ("error", "critical"):
            tag = "error"
        elif level == "warning":
            tag = "warning"
        elif "mock" in msg.lower() or "ket noi" in msg.lower() or "video cho" in msg.lower():
            tag = "system"
        else:
            tag = "info"
        self.output.put_nowait((msg, tag))


class StatusPill(tk.Canvas):
    """Canvas hiển thị viên con nhộng đèn LED trạng thái phát sáng."""

    def __init__(self, parent: tk.Widget, text: str = "OFFLINE", state_type: str = "offline", width: int = 120, height: int = 28) -> None:
        super().__init__(parent, width=width, height=height, bg=CARD_BG, highlightthickness=0)
        self.text = text
        self.state_type = state_type
        self.draw()

    def set_status(self, text: str, state_type: str) -> None:
        if self.text != text or self.state_type != state_type:
            self.text = text
            self.state_type = state_type
            self.draw()

    def draw(self) -> None:
        self.delete("all")
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()

        colors = {
            "online": (COLOR_EMERALD, "#064e3b", "#ecfdf5"),
            "mock": (COLOR_CYAN, "#0e7490", "#cffafe"),
            "warning": (COLOR_AMBER, "#78350f", "#fef3c7"),
            "offline": (COLOR_ROSE, "#881337", "#ffe4e6"),
        }
        dot_color, bg_pill, fg_text = colors.get(self.state_type, colors["offline"])

        # Draw Pill Background
        self.create_oval(2, 2, h - 2, h - 2, fill=bg_pill, outline=dot_color, width=1)
        self.create_oval(w - h + 2, 2, w - 2, h - 2, fill=bg_pill, outline=dot_color, width=1)
        self.create_rectangle(h / 2, 2, w - h / 2, h - 2, fill=bg_pill, outline="")

        # Draw Glowing LED Dot
        dot_r = 4
        cx, cy = 14, h / 2
        self.create_oval(cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r, fill=dot_color, outline="")

        # Draw Text
        self.create_text(cx + 10, cy, text=self.text, fill=fg_text, anchor="w", font=("Segoe UI", 9, "bold"))


class CanvasProgressBar(tk.Canvas):
    """Thanh progress bar bo góc chạy mịn vẽ bằng Canvas."""

    def __init__(self, parent: tk.Widget, height: int = 14) -> None:
        super().__init__(parent, height=height, bg=PANEL_BG, highlightthickness=0)
        self.progress = 0.0
        self.bind("<Configure>", lambda _: self.draw())

    def set_progress(self, pct: float) -> None:
        pct = max(0.0, min(100.0, pct))
        if abs(self.progress - pct) > 0.5:
            self.progress = pct
            self.draw()

    def draw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10:
            return

        # Background Trough
        r = h / 2
        self.create_oval(0, 0, h, h, fill="#0f172a", outline="")
        self.create_oval(w - h, 0, w, h, fill="#0f172a", outline="")
        self.create_rectangle(r, 0, w - r, h, fill="#0f172a", outline="")

        # Foreground Fill
        fill_w = (w * self.progress) / 100.0
        if fill_w > 4:
            fw = max(fill_w, h)
            self.create_oval(0, 0, h, h, fill=COLOR_CYAN, outline="")
            if fw > h:
                self.create_oval(fw - h, 0, fw, h, fill=COLOR_CYAN, outline="")
                self.create_rectangle(r, 0, fw - r, h, fill=COLOR_CYAN, outline="")


class GiftMappingCard(tk.Frame):
    """Thẻ quản lý chọn file video & priority cho từng món quà."""

    def __init__(
        self,
        parent: tk.Widget,
        gift_key: str,
        video_filename: str,
        priority: int,
        on_choose_file: callable,
        on_test: callable,
    ) -> None:
        super().__init__(parent, bg=CARD_BG, highlightbackground=PANEL_BORDER, highlightthickness=1, padx=10, pady=8)
        self.gift_key = gift_key
        self.on_choose_file = on_choose_file
        self.on_test = on_test

        emoji_map = {"rose": "🌹", "doughnut": "🍩", "perfume": "🧴", "tiktok": "♪", "lion": "🦁"}
        emoji = emoji_map.get(gift_key.lower(), "🎁")

        self.columnconfigure(1, weight=1)

        # Emoji Icon
        lbl_icon = tk.Label(self, text=emoji, font=("Segoe UI Emoji", 16), bg=CARD_BG)
        lbl_icon.grid(row=0, column=0, rowspan=2, padx=(0, 8), sticky="w")

        # Gift Title
        lbl_title = tk.Label(self, text=gift_key.title(), font=("Segoe UI", 10, "bold"), fg=COLOR_CYAN, bg=CARD_BG)
        lbl_title.grid(row=0, column=1, sticky="w")

        # Video File Name Display / Entry
        self.file_var = tk.StringVar(value=video_filename)
        lbl_file = tk.Label(self, textvariable=self.file_var, font=("Segoe UI", 8), fg=TEXT_MUTED, bg=CARD_BG, anchor="w")
        lbl_file.grid(row=1, column=1, sticky="w")

        # Priority Spinbox / Entry
        prio_frame = tk.Frame(self, bg=CARD_BG)
        prio_frame.grid(row=0, column=2, rowspan=2, padx=6)
        tk.Label(prio_frame, text="Prio:", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=CARD_BG).pack(side="left")
        self.prio_var = tk.StringVar(value=str(priority))
        spn = tk.Spinbox(prio_frame, from_=1, to=10, textvariable=self.prio_var, width=3, bg="#0d131f", fg="#fff", buttonbackground="#1e293b", relief="flat")
        spn.pack(side="left", padx=2)

        # Choose File Button
        btn_choose = tk.Button(self, text="📂 Chọn Video", font=("Segoe UI", 8, "bold"), bg="#1e293b", fg=TEXT_MAIN, activebackground=COLOR_CYAN, activeforeground="#000", relief="flat", padx=6, pady=3, command=self._choose)
        btn_choose.grid(row=0, column=3, rowspan=2, padx=4)

        # Test Button
        btn_test = tk.Button(self, text="▶ Test", font=("Segoe UI", 8, "bold"), bg=COLOR_EMERALD, fg="#042f2e", activebackground="#34d399", relief="flat", padx=6, pady=3, command=lambda: self.on_test(self.gift_key))
        btn_test.grid(row=0, column=4, rowspan=2, padx=(0, 2))

    def _choose(self) -> None:
        filename = filedialog.askopenfilename(title=f"Chọn video cho quà {self.gift_key.title()}", filetypes=[("Media Files", "*.mp4 *.mov *.mkv *.webm *.png *.jpg *.jpeg *.webp"), ("All files", "*.*")])
        if filename:
            path = Path(filename)
            core.VIDEO_DIRECTORY = path.parent
            mapped_val = path.name if path.parent == core.VIDEO_DIRECTORY else str(path)
            self.file_var.set(path.name)
            self.on_choose_file(self.gift_key, mapped_val, self.get_priority())

    def get_priority(self) -> int:
        try:
            return int(self.prio_var.get())
        except ValueError:
            return 1


class StreamDeckButton(tk.Frame):
    """Nút bấm Stream Deck tùy chỉnh có hiệu ứng hover & priority tag."""

    def __init__(self, parent: tk.Widget, emoji: str, title: str, subtitle: str, bg_color: str, command: callable) -> None:
        super().__init__(parent, bg=CARD_BG, highlightbackground=PANEL_BORDER, highlightthickness=1, cursor="hand2")
        self.command = command
        self.bg_normal = CARD_BG
        self.bg_hover = CARD_HOVER

        self.columnconfigure(1, weight=1)

        # Left Emoji Icon Box
        icon_box = tk.Label(self, text=emoji, font=("Segoe UI Emoji", 18), bg=bg_color, fg="#ffffff", width=3, height=2)
        icon_box.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=2, pady=2)

        # Title Label
        lbl_title = tk.Label(self, text=title, font=("Segoe UI", 10, "bold"), fg=TEXT_MAIN, bg=CARD_BG, anchor="w")
        lbl_title.grid(row=0, column=1, sticky="w", padx=(8, 6), pady=(4, 0))

        # Subtitle Label
        lbl_sub = tk.Label(self, text=subtitle, font=("Segoe UI", 8), fg=TEXT_MUTED, bg=CARD_BG, anchor="w")
        lbl_sub.grid(row=1, column=1, sticky="w", padx=(8, 6), pady=(0, 4))

        # Bind hover & click for all children
        for widget in (self, icon_box, lbl_title, lbl_sub):
            widget.bind("<Enter>", self.on_enter)
            widget.bind("<Leave>", self.on_leave)
            widget.bind("<Button-1>", lambda _: self.command())

        self.lbl_title = lbl_title
        self.lbl_sub = lbl_sub

    def on_enter(self, _: tk.Event) -> None:
        self.configure(bg=self.bg_hover, highlightbackground=COLOR_CYAN)
        self.lbl_title.configure(bg=self.bg_hover)
        self.lbl_sub.configure(bg=self.bg_hover)

    def on_leave(self, _: tk.Event) -> None:
        self.configure(bg=self.bg_normal, highlightbackground=PANEL_BORDER)
        self.lbl_title.configure(bg=self.bg_normal)
        self.lbl_sub.configure(bg=self.bg_normal)


class TikTokObsGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TikTok Live Control Room v3.1 - Stream Deck Edition")
        self.root.geometry("1320x880")
        self.root.minsize(1100, 740)
        self.root.configure(bg=BG_DARK)

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.app: core.TikTokObsApp | None = None
        self.run_loop: asyncio.AbstractEventLoop | None = None
        self.run_future: asyncio.Future[None] | None = None

        self.recent_history: list[core.GiftJob] = []
        self._last_completed_job: core.GiftJob | None = None
        self.gift_cards: dict[str, GiftMappingCard] = {}

        self.username = tk.StringVar(value=core.TIKTOK_USERNAME)
        self.obs_host = tk.StringVar(value=core.OBS_HOST)
        self.obs_port = tk.StringVar(value=str(core.OBS_PORT))
        self.obs_password = tk.StringVar(value=core.OBS_PASSWORD)
        self.scene_name = tk.StringVar(value=core.SCENE_NAME)
        self.idle_source = tk.StringVar(value=core.IDLE_SOURCE_NAME)
        self.action_source = tk.StringVar(value=core.ACTION_SOURCE_NAME)
        self.idle_video_name = tk.StringVar(value=core.resolve_existing_media_path(core.IDLE_VIDEO_PATH).name)

        # Mặc định False để kết nối OBS thật khi bấm nút
        self.mock_mode_var = tk.BooleanVar(value=False)
        self.enable_tiktok_var = tk.BooleanVar(value=False)

        self.status_text = tk.StringVar(value="SẴN SÀNG KHỞI ĐỘNG")
        self.current_action_name = tk.StringVar(value="💤 ĐANG CHẠY VIDEO CHỜ (IDLE LOOP)")
        self.current_action_sub = tk.StringVar(value=f"Media Source: Idle_Source | File: {core.IDLE_VIDEO_PATH.name}")
        self.timer_display = tk.StringVar(value="LOOPING")
        self.queue_count_text = tk.StringVar(value="0 món chờ")

        self._build_style()
        self._build_ui()
        self._install_logging()
        self.root.after(100, self._poll_logs)
        self.root.after(150, self._refresh_dashboard)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=BG_DARK)
        style.configure("Panel.TFrame", background=PANEL_BG)

        style.configure("TLabel", background=BG_DARK, foreground=TEXT_MAIN, font=("Segoe UI", 10))
        style.configure("PanelTitle.TLabel", background=PANEL_BG, foreground=COLOR_CYAN, font=("Segoe UI", 11, "bold"))
        style.configure("Title.TLabel", background=BG_DARK, foreground=TEXT_MAIN, font=("Segoe UI", 22, "bold"))
        style.configure("Subtitle.TLabel", background=BG_DARK, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        style.configure("PanelMuted.TLabel", background=PANEL_BG, foreground=TEXT_MUTED, font=("Segoe UI", 8))

        style.configure("TEntry", fieldbackground="#182335", foreground="#ffffff", insertcolor="#ffffff", bordercolor=PANEL_BORDER, padding=4)
        style.configure("TCheckbutton", background=PANEL_BG, foreground=COLOR_CYAN, font=("Segoe UI", 8, "bold"))

        # Treeview Styling
        style.configure("Treeview", background="#0d131f", fieldbackground="#0d131f", foreground="#e2e8f0", rowheight=30, borderwidth=0)
        style.configure("Treeview.Heading", background="#1a2536", foreground=COLOR_CYAN, relief="flat", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#0284c7")], foreground=[("selected", "#ffffff")])

        # Buttons Styling
        style.configure("Primary.TButton", background=COLOR_EMERALD, foreground="#042f2e", padding=9, font=("Segoe UI", 10, "bold"))
        style.configure("Danger.TButton", background=COLOR_ROSE, foreground="#ffffff", padding=7, font=("Segoe UI", 9, "bold"))
        style.configure("Accent.TButton", background=COLOR_CYAN, foreground="#083344", padding=7, font=("Segoe UI", 9, "bold"))
        style.configure("Soft.TButton", background="#1e293b", foreground="#f1f5f9", padding=5, font=("Segoe UI", 8))

        style.map("Primary.TButton", background=[("active", "#34d399")])
        style.map("Danger.TButton", background=[("active", "#fb7185")])
        style.map("Accent.TButton", background=[("active", "#38bdf8")])

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        # Header Section
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))

        title_box = ttk.Frame(header)
        title_box.pack(side="left")
        ttk.Label(title_box, text="TikTok Live Control Room", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Visual Video Selection & Real-Time OBS Automation Suite v3.1", style="Subtitle.TLabel").pack(anchor="w")

        # Top Right Global Status Indicator
        self.sys_status_pill = StatusPill(header, text="OFFLINE", state_type="offline", width=140, height=32)
        self.sys_status_pill.pack(side="right", pady=4)

        # Metrics Overview Row (4 Status Cards)
        metrics = ttk.Frame(outer)
        metrics.pack(fill="x", pady=(0, 12))

        self.pill_tiktok = self._create_metric_card(metrics, "TikTok Live Connection", 0, COLOR_PURPLE)
        self.pill_obs = self._create_metric_card(metrics, "OBS WebSocket v5", 1, COLOR_BLUE)
        self.card_current_val = self._create_metric_card_custom(metrics, "Đang Phát Effect", self.current_action_name, 2, COLOR_EMERALD)
        self.card_queue_val = self._create_metric_card_custom(metrics, "Hàng Đợi Chờ", self.queue_count_text, 3, COLOR_AMBER)

        for col in range(4):
            metrics.columnconfigure(col, weight=1)

        # Main Split Body
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Left Column: Cấu hình Hệ thống & Video Chờ (Nút Kết Nối Nổi Bật Ở Trên Cùng)
        self._build_settings_panel(body).grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        # Right Column: Hero Live Player + Stream Deck + Visual Gift Video Cards Grid + Logs
        right_panel = ttk.Frame(body)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.rowconfigure(2, weight=1)
        right_panel.columnconfigure(0, weight=1)

        # 1. Hero Player Card (Video đang phát / Video chờ)
        self._build_hero_player(right_panel).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        # 2. Stream Deck Gift Test Buttons
        self._build_stream_deck(right_panel).grid(row=1, column=0, sticky="ew", pady=(0, 10))

        # 3. Queue Table & Visual Gift Video Cards Split
        self._build_queue_and_visual_mapping(right_panel).grid(row=2, column=0, sticky="nsew", pady=(0, 10))

        # 4. Logs Console
        self._build_log_console(right_panel).grid(row=3, column=0, sticky="ew")

    def _create_metric_card(self, parent: ttk.Frame, title: str, col: int, accent_color: str) -> StatusPill:
        card = tk.Frame(parent, bg=CARD_BG, highlightbackground=PANEL_BORDER, highlightthickness=1)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 5, 5 if col < 3 else 0))

        strip = tk.Frame(card, bg=accent_color, height=3)
        strip.pack(fill="x")

        inner = tk.Frame(card, bg=CARD_BG, padx=10, pady=8)
        inner.pack(fill="both", expand=True)

        pill = StatusPill(inner, text="OFFLINE", state_type="offline", width=125, height=26)
        pill.pack(anchor="w")
        tk.Label(inner, text=title, font=("Segoe UI", 9), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w", pady=(3, 0))
        return pill

    def _create_metric_card_custom(self, parent: ttk.Frame, title: str, var: tk.StringVar, col: int, accent_color: str) -> tk.Label:
        card = tk.Frame(parent, bg=CARD_BG, highlightbackground=PANEL_BORDER, highlightthickness=1)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 5, 5 if col < 3 else 0))

        strip = tk.Frame(card, bg=accent_color, height=3)
        strip.pack(fill="x")

        inner = tk.Frame(card, bg=CARD_BG, padx=10, pady=8)
        inner.pack(fill="both", expand=True)

        val_lbl = tk.Label(inner, textvariable=var, font=("Segoe UI", 11, "bold"), fg=TEXT_MAIN, bg=CARD_BG, anchor="w")
        val_lbl.pack(anchor="w")
        tk.Label(inner, text=title, font=("Segoe UI", 9), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w", pady=(2, 0))
        return val_lbl

    def _build_settings_panel(self, parent: ttk.Frame) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=12)

        ttk.Label(panel, text="⚙ CẤU HÌNH CONTROL ROOM", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 8))

        # 🚀 ACTION BUTTONS PLACED AT THE VERY TOP FOR EASY ACCESS
        btn_box = tk.Frame(panel, bg=PANEL_BG)
        btn_box.pack(fill="x", pady=(0, 10))

        ttk.Button(btn_box, text="▶  BẮT ĐẦU KẾT NỐI", style="Primary.TButton", command=self.start).pack(fill="x")
        ttk.Button(btn_box, text="■  DỪNG HỆ THỐNG", style="Danger.TButton", command=self.stop).pack(fill="x", pady=(5, 0))

        # Mock mode & TikTok Checkbox Frame
        chk_frame = tk.Frame(panel, bg="#1a2638", padx=8, pady=5)
        chk_frame.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(chk_frame, text="🧪 Bật Giả Lập (Mock Mode)", variable=self.mock_mode_var).pack(anchor="w")
        ttk.Checkbutton(chk_frame, text="📡 Kết Nối TikTok Live (Realtime)", variable=self.enable_tiktok_var).pack(anchor="w", pady=(3, 0))

        # IDLE VIDEO SELECTION CARD
        idle_box = tk.Frame(panel, bg=CARD_BG, highlightbackground=COLOR_CYAN, highlightthickness=1, padx=8, pady=6)
        idle_box.pack(fill="x", pady=(0, 8))

        tk.Label(idle_box, text="💤 VIDEO CHỜ (IDLE LOOP)", font=("Segoe UI", 8, "bold"), fg=COLOR_CYAN, bg=CARD_BG).pack(anchor="w")
        
        idle_row = tk.Frame(idle_box, bg=CARD_BG)
        idle_row.pack(fill="x", pady=(3, 0))

        tk.Label(idle_row, textvariable=self.idle_video_name, font=("Segoe UI", 8, "bold"), fg=TEXT_MAIN, bg="#0d131f", padx=5, pady=3, anchor="w").pack(side="left", fill="x", expand=True)
        btn_pick_idle = tk.Button(idle_row, text="📂 Chọn", font=("Segoe UI", 8, "bold"), bg=COLOR_AMBER, fg="#000", relief="flat", padx=5, pady=2, command=self.choose_idle_video)
        btn_pick_idle.pack(side="right", padx=(4, 0))

        # Config Fields
        fields = [
            ("TikTok Username", self.username),
            ("OBS Host", self.obs_host),
            ("OBS Port", self.obs_port),
            ("OBS Password", self.obs_password),
            ("Scene Name", self.scene_name),
            ("Idle Source", self.idle_source),
            ("Action Source", self.action_source),
        ]
        for label, variable in fields:
            ttk.Label(panel, text=label, style="PanelMuted.TLabel").pack(anchor="w", pady=(2, 0))
            show = "*" if "Password" in label else ""
            ttk.Entry(panel, textvariable=variable, show=show, width=26).pack(fill="x")

        ttk.Button(panel, text="📁 Mở Thư Mục Videos", style="Soft.TButton", command=self.open_video_folder).pack(fill="x", pady=(10, 0))
        return panel

    def choose_idle_video(self) -> None:
        filename = filedialog.askopenfilename(title="Chọn Video Chờ (Idle Loop Video)", filetypes=[("Media Files", "*.mp4 *.mov *.mkv *.webm *.png *.jpg *.jpeg *.webp"), ("All files", "*.*")])
        if filename:
            path = Path(filename)
            core.IDLE_VIDEO_PATH = path
            core.VIDEO_DIRECTORY = path.parent
            self.idle_video_name.set(path.name)
            logging.getLogger(__name__).info("Đã chọn Video Chờ mới: %s", path.name)
            if self.app and self.run_loop:
                asyncio.run_coroutine_threadsafe(self.app.obs.set_idle_video(path), self.run_loop)

    def _build_hero_player(self, parent: ttk.Frame) -> tk.Frame:
        card = tk.Frame(parent, bg=CARD_BG, highlightbackground=COLOR_CYAN, highlightthickness=1, padx=14, pady=12)

        top_row = tk.Frame(card, bg=CARD_BG)
        top_row.pack(fill="x")

        # Big Gift Emoji / Idle Box
        self.hero_emoji_lbl = tk.Label(top_row, text="💤", font=("Segoe UI Emoji", 24), bg="#213047", fg="#ffffff", width=2, height=1)
        self.hero_emoji_lbl.pack(side="left", padx=(0, 12))

        # Title & Subtitle Box
        mid_box = tk.Frame(top_row, bg=CARD_BG)
        mid_box.pack(side="left", fill="both", expand=True)

        tk.Label(mid_box, textvariable=self.current_action_name, font=("Segoe UI", 13, "bold"), fg=COLOR_CYAN, bg=CARD_BG, anchor="w").pack(anchor="w")
        tk.Label(mid_box, textvariable=self.current_action_sub, font=("Segoe UI", 9), fg=TEXT_MUTED, bg=CARD_BG, anchor="w").pack(anchor="w", pady=(2, 0))

        # Right Side Container for Timer + Skip Button
        right_timer_box = tk.Frame(top_row, bg=CARD_BG)
        right_timer_box.pack(side="right", anchor="e")

        btn_skip = tk.Button(
            right_timer_box,
            text="⏭ Bỏ Qua (Skip)",
            font=("Segoe UI", 9, "bold"),
            bg="#334155",
            fg=TEXT_MAIN,
            activebackground=COLOR_ROSE,
            activeforeground="#fff",
            relief="flat",
            padx=8,
            pady=3,
            command=self.skip_action,
        )
        btn_skip.pack(side="right", padx=(8, 0))

        tk.Label(
            right_timer_box,
            textvariable=self.timer_display,
            font=("Cascadia Mono", 13, "bold"),
            fg=COLOR_EMERALD,
            bg=CARD_BG,
        ).pack(side="right")

        # Custom Canvas Progress Bar
        self.hero_progress = CanvasProgressBar(card, height=10)
        self.hero_progress.pack(fill="x", pady=(10, 0))

        return card

    def skip_action(self) -> None:
        if self.app:
            self.app.skip_current()

    def _build_stream_deck(self, parent: ttk.Frame) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=12)

        header = ttk.Frame(panel, style="Panel.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="🎛 STREAM DECK - BẮN QÙA THỬ NGHIỆM REALTIME", style="PanelTitle.TLabel").pack(side="left")

        # Automation Combo buttons
        ttk.Button(header, text="⚡ Test Combo (Rose -> Doughnut -> TikTok)", style="Accent.TButton", command=self.run_e2e_combo_test).pack(side="right")
        ttk.Button(header, text="🔥 Test Ngắt Ưu Tiên Lion", style="Soft.TButton", command=self.run_e2e_interrupt_test).pack(side="right", padx=4)

        # 4 Interactive Stream Deck Buttons
        deck_grid = tk.Frame(panel, bg=PANEL_BG)
        deck_grid.pack(fill="x")

        buttons_data = [
            ("🌹", "Rose (Hoa Hồng)", "Priority: 1 | cho_1_sui.mp4", COLOR_ROSE, "rose"),
            ("🍩", "Doughnut (Bánh)", "Priority: 2 | cho_2_trong_chuoi.mp4", COLOR_AMBER, "doughnut"),
            ("♪", "TikTok", "Priority: 3 | 3_cho_nhay_tiktok.mp4", COLOR_CYAN, "tiktok"),
            ("🦁", "Lion (Sư Tử - Ngắt)", "Priority: 5 | 3_cho_bien_su_tu.mp4", COLOR_PURPLE, "lion"),
        ]

        for col, (emoji, title, sub, color, gift_key) in enumerate(buttons_data):
            btn = StreamDeckButton(deck_grid, emoji, title, sub, color, command=lambda g=gift_key: self.test_gift(g))
            btn.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 4, 4 if col < 3 else 0))
            deck_grid.columnconfigure(col, weight=1)

        return panel

    def _build_queue_and_visual_mapping(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        # Left Sub-panel: Queue Chờ & Trạng Thái
        queue_panel = ttk.Frame(frame, style="Panel.TFrame", padding=10)
        queue_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        q_top = ttk.Frame(queue_panel, style="Panel.TFrame")
        q_top.pack(fill="x", pady=(0, 6))
        ttk.Label(q_top, text="📋 HÀNG ĐỢI & TRẠNG THÁI PHÁT QÙA", style="PanelTitle.TLabel").pack(side="left")
        ttk.Button(q_top, text="🧹 Xóa Queue", style="Soft.TButton", command=self.clear_queue).pack(side="right")

        self.queue_tree = ttk.Treeview(queue_panel, columns=("status", "gift", "file", "prio"), show="headings", height=5)
        self.queue_tree.heading("status", text="Trạng Thái")
        self.queue_tree.heading("gift", text="Tên Qùa")
        self.queue_tree.heading("file", text="File Video")
        self.queue_tree.heading("prio", text="Priority")

        self.queue_tree.column("status", width=105, anchor="center")
        self.queue_tree.column("gift", width=95)
        self.queue_tree.column("file", width=180)
        self.queue_tree.column("prio", width=55, anchor="center")
        self.queue_tree.pack(fill="both", expand=True)

        self.queue_tree.tag_configure("playing", background="#064e3b", foreground="#67e8c0")
        self.queue_tree.tag_configure("waiting", background="#1e293b", foreground="#f8fafc")
        self.queue_tree.tag_configure("done", background="#0f172a", foreground="#64748b")

        # Right Sub-panel: Visual Gift Mapping Cards Grid
        map_panel = ttk.Frame(frame, style="Panel.TFrame", padding=10)
        map_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        m_top = ttk.Frame(map_panel, style="Panel.TFrame")
        m_top.pack(fill="x", pady=(0, 6))
        ttk.Label(m_top, text="🎯 THẺ QUẢN LÝ CHỌN VIDEO QÙA", style="PanelTitle.TLabel").pack(side="left")
        ttk.Button(m_top, text="💾 Lưu Tất Cả Mapping", style="Soft.TButton", command=self.save_mapping).pack(side="right")

        # Scrollable container for Gift Mapping Cards
        canvas_map = tk.Canvas(map_panel, bg=PANEL_BG, highlightthickness=0)
        scroll_map = ttk.Scrollbar(map_panel, orient="vertical", command=canvas_map.yview)
        cards_container = tk.Frame(canvas_map, bg=PANEL_BG)

        cards_container.bind("<Configure>", lambda e: canvas_map.configure(scrollregion=canvas_map.bbox("all")))
        canvas_map.create_window((0, 0), window=cards_container, anchor="nw")
        canvas_map.configure(yscrollcommand=scroll_map.set)

        canvas_map.pack(side="left", fill="both", expand=True)
        scroll_map.pack(side="right", fill="y")

        # Populate Gift Mapping Cards
        for gift, (filename, priority) in core.GIFT_MAPPING.items():
            card = GiftMappingCard(
                cards_container,
                gift_key=gift,
                video_filename=filename,
                priority=priority,
                on_choose_file=self.update_card_mapping,
                on_test=self.test_gift,
            )
            card.pack(fill="x", pady=3)
            self.gift_cards[gift] = card

        return frame

    def update_card_mapping(self, gift_key: str, filename: str, priority: int) -> None:
        core.GIFT_MAPPING[gift_key] = (filename, priority)
        logging.getLogger(__name__).info("Đã cập nhật video cho quà %s: %s (Priority %s)", gift_key.title(), filename, priority)

    def _build_log_console(self, parent: ttk.Frame) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=8)

        top = ttk.Frame(panel, style="Panel.TFrame")
        top.pack(fill="x", pady=(0, 4))
        ttk.Label(top, text="💻 REALTIME LOG CONSOLE", style="PanelTitle.TLabel").pack(side="left")
        ttk.Button(top, text="🗑 Clear Console", style="Soft.TButton", command=self.clear_logs).pack(side="right")

        self.log_text = tk.Text(panel, bg="#080d1a", fg="#cbd5e1", insertbackground="#fff", relief="flat", font=("Cascadia Mono", 9), wrap="word", height=4)
        self.log_text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(panel, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set, state="disabled")

        self.log_text.tag_config("info", foreground="#38bdf8")
        self.log_text.tag_config("gift", foreground="#34d399", font=("Cascadia Mono", 9, "bold"))
        self.log_text.tag_config("warning", foreground="#fbbf24")
        self.log_text.tag_config("error", foreground="#f87171", font=("Cascadia Mono", 9, "bold"))
        self.log_text.tag_config("system", foreground="#c084fc")

        return panel

    def _install_logging(self) -> None:
        handler = ColorLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(handler)

    def _apply_config(self) -> bool:
        if not self.mock_mode_var.get():
            try:
                port = int(self.obs_port.get())
            except ValueError:
                messagebox.showerror("Sai cấu hình", "OBS port phải là số.")
                return False
            if not self.username.get().strip() or not self.scene_name.get().strip():
                messagebox.showerror("Thiếu thông tin", "Hãy nhập TikTok username và Scene name.")
                return False
            core.OBS_PORT = port

        core.TIKTOK_USERNAME = self.username.get().strip().lstrip("@") or "mock_user"
        core.OBS_HOST = self.obs_host.get().strip()
        core.OBS_PASSWORD = self.obs_password.get()
        core.SCENE_NAME = self.scene_name.get().strip()
        core.IDLE_SOURCE_NAME = self.idle_source.get().strip()
        core.ACTION_SOURCE_NAME = self.action_source.get().strip()
        return True

    def start(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if not self._apply_config():
            return
        is_mock = self.mock_mode_var.get()
        enable_tiktok = self.enable_tiktok_var.get()
        self.status_text.set("ĐANG KẾT NỐI..." + (" (MOCK)" if is_mock else ""))
        self.sys_status_pill.set_status("CONNECTING", "warning")
        self.worker_thread = threading.Thread(target=self._run_async, args=(is_mock, enable_tiktok), daemon=True)
        self.worker_thread.start()

    def _run_async(self, mock_mode: bool, enable_tiktok: bool) -> None:
        self.run_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.run_loop)
        self.app = core.TikTokObsApp(mock_mode=mock_mode, enable_tiktok=enable_tiktok)
        self.run_future = self.run_loop.create_task(self.app.run())
        try:
            self.run_loop.run_until_complete(self.run_future)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logging.getLogger(__name__).error("⚠️ Lỗi kết nối OBS / Tiến trình: %s", exc)
            err_msg = str(exc)
            def _prompt_mock():
                ans = messagebox.askyesno(
                    "Lỗi Kết Nối OBS Studio",
                    f"Không thể kết nối với OBS Studio:\n{err_msg}\n\n"
                    f"Bạn có muốn tự động chuyển sang CHẾ ĐỘ GIẢ LẬP (Mock Mode) để test thử giao diện và quy trình xử lý không?"
                )
                if ans:
                    self.stop()
                    self.mock_mode_var.set(True)
                    self.root.after(200, self.start)
            self.root.after(0, _prompt_mock)
        finally:
            self.run_loop.close()
            self.run_loop = None
            self.run_future = None
            self.app = None
            self.worker_thread = None

    def stop(self) -> None:
        if self.run_loop and self.run_future and not self.run_future.done():
            self.run_loop.call_soon_threadsafe(self.run_future.cancel)
            self.status_text.set("ĐANG DỪNG...")

    def _check_connection_and_prompt(self, action_name: str, on_connected: callable) -> None:
        if not self.app or not self.run_loop or not self.app.obs.is_connected:
            ans = messagebox.askyesno(
                "Chưa Kết Nối OBS Studio",
                f"Hệ thống chưa kết nối thành công tới OBS Studio.\n\n"
                f"Bạn có muốn TỰ ĐỘNG BẬT CHẾ ĐỘ GIẢ LẬP (Mock Mode) để Test '{action_name}' ngay không?"
            )
            if ans:
                self.stop()
                self.mock_mode_var.set(True)
                self.root.after(200, self.start)
                self.root.after(600, on_connected)
            return

        on_connected()

    def test_gift(self, gift: str) -> None:
        def _do() -> None:
            if self.app and self.run_loop:
                asyncio.run_coroutine_threadsafe(self.app.enqueue_gift(gift), self.run_loop)

        self._check_connection_and_prompt(f"Qùa {gift.title()}", _do)

    def run_e2e_combo_test(self) -> None:
        async def _combo() -> None:
            logging.getLogger(__name__).info("🚀 RUNNING E2E GIFT COMBO: Rose -> Doughnut -> TikTok")
            await self.app.enqueue_gift("rose")
            await asyncio.sleep(0.4)
            await self.app.enqueue_gift("doughnut")
            await asyncio.sleep(0.4)
            await self.app.enqueue_gift("tiktok")

        def _do() -> None:
            if self.app and self.run_loop:
                asyncio.run_coroutine_threadsafe(_combo(), self.run_loop)

        self._check_connection_and_prompt("Combo Test", _do)

    def run_e2e_interrupt_test(self) -> None:
        async def _interrupt() -> None:
            logging.getLogger(__name__).info("🔥 RUNNING E2E LION INTERRUPT TEST: Rose -> Lion")
            await self.app.enqueue_gift("rose")
            await asyncio.sleep(1.2)
            await self.app.enqueue_gift("lion")

        def _do() -> None:
            if self.app and self.run_loop:
                asyncio.run_coroutine_threadsafe(_interrupt(), self.run_loop)

        self._check_connection_and_prompt("Lion Interrupt Test", _do)

    def clear_queue(self) -> None:
        if self.app:
            cleared = self.app.queue.clear()
            self.recent_history.clear()
            logging.getLogger(__name__).info("Đã xóa %s món trong queue chờ", cleared)

    def clear_logs(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def save_mapping(self) -> None:
        for gift, card in self.gift_cards.items():
            filename = card.file_var.get().strip()
            prio = card.get_priority()
            core.GIFT_MAPPING[gift] = (filename, prio)
        logging.getLogger(__name__).info("Đã cập nhật toàn bộ Gift Mapping Cards Matrix")

    def open_video_folder(self) -> None:
        core.VIDEO_DIRECTORY.mkdir(parents=True, exist_ok=True)
        os.startfile(core.VIDEO_DIRECTORY)

    def _refresh_dashboard(self) -> None:
        if self.app:
            # Update Pills
            if self.app.obs.is_connected:
                self.pill_obs.set_status("ONLINE (MOCK)" if self.app.mock_mode else "ONLINE", "mock" if self.app.mock_mode else "online")
            else:
                self.pill_obs.set_status("OFFLINE", "offline")

            if self.app.is_tiktok_connected:
                self.pill_tiktok.set_status("ONLINE (MOCK)" if self.app.mock_mode else "ONLINE", "mock" if self.app.mock_mode else "online")
            elif not self.enable_tiktok_var.get():
                self.pill_tiktok.set_status("STANDBY", "warning")
            else:
                self.pill_tiktok.set_status("OFFLINE", "offline")

            self.sys_status_pill.set_status("RUNNING (MOCK)" if self.app.mock_mode else "RUNNING", "mock" if self.app.mock_mode else "online")

            queue_items = self.app.queue.get_items()
            self.queue_count_text.set(f"{len(queue_items)} món chờ")

            current_job = self.app.current_job

            # Track completed history
            if self._last_completed_job and self._last_completed_job != current_job:
                if self._last_completed_job not in self.recent_history:
                    self.recent_history.insert(0, self._last_completed_job)
                    if len(self.recent_history) > 4:
                        self.recent_history.pop()

            self._last_completed_job = current_job

            if current_job:
                emoji_map = {"rose": "🌹", "doughnut": "🍩", "tiktok": "♪", "lion": "🦁"}
                emoji = emoji_map.get(current_job.gift_name, "🎬")
                self.hero_emoji_lbl.configure(text=emoji)

                self.current_action_name.set(f"ĐANG PHÁT ACTION: {current_job.gift_name.upper()}")
                self.current_action_sub.set(f"File: {current_job.file_path.name} | Priority Level: {current_job.priority}")

                if self.run_loop and self.app.current_job_start_time > 0:
                    elapsed = self.run_loop.time() - self.app.current_job_start_time
                    dur = max(self.app.current_job_duration, 0.1)
                    rem = max(dur - elapsed, 0.0)
                    pct = min(100.0, (elapsed / dur) * 100.0)

                    self.hero_progress.set_progress(pct)
                    self.timer_display.set(f"{rem:04.1f}s / {dur:04.1f}s")
            else:
                self.hero_emoji_lbl.configure(text="💤")
                self.current_action_name.set("💤 ĐANG CHẠY VIDEO CHỜ (IDLE LOOP)")
                self.current_action_sub.set(f"Media Source: {core.IDLE_SOURCE_NAME} | File: {core.IDLE_VIDEO_PATH.name}")
                self.hero_progress.set_progress(0.0)
                self.timer_display.set("LOOPING")

            self._refresh_queue_tree(current_job, queue_items)

        elif not (self.worker_thread and self.worker_thread.is_alive()):
            self.pill_obs.set_status("OFFLINE", "offline")
            self.pill_tiktok.set_status("OFFLINE", "offline")
            self.sys_status_pill.set_status("OFFLINE", "offline")
            self.hero_progress.set_progress(0.0)
            self.timer_display.set("00.0s / 00.0s")
            self.current_action_name.set("IDLE (Chờ kết nối)")
            self.current_action_sub.set("Media Source: Disconnected")
            self._refresh_queue_tree(None, [])

        self.root.after(150, self._refresh_dashboard)

    def _refresh_queue_tree(self, active_job: core.GiftJob | None, queue_items: list[core.GiftJob]) -> None:
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)

        # 1. Currently Playing Job Row
        if active_job:
            self.queue_tree.insert("", "end", values=("▶ ĐANG PHÁT", active_job.gift_name.title(), active_job.file_path.name, active_job.priority), tags=("playing",))

        # 2. Waiting Jobs Rows
        for job in queue_items:
            self.queue_tree.insert("", "end", values=("⏳ ĐANG CHỜ", job.gift_name.title(), job.file_path.name, job.priority), tags=("waiting",))

        # 3. Recent History Completed Rows
        for job in self.recent_history:
            self.queue_tree.insert("", "end", values=("✅ ĐÃ PHÁT", job.gift_name.title(), job.file_path.name, job.priority), tags=("done",))

    def _poll_logs(self) -> None:
        while True:
            try:
                message, tag = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n", tag)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(100, self._poll_logs)

    def close(self) -> None:
        self.stop()
        self.root.after(250, self.root.destroy)


def main() -> None:
    root = tk.Tk()
    TikTokObsGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
