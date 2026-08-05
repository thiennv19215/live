"""Dashboard desktop phím bấm Cyber Control Deck cao cấp v3.1 cho tiktok_obs_controller.py."""

from __future__ import annotations

import asyncio
import contextlib
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


def shorten_filename(filename: str, max_chars: int = 24) -> str:
    name = Path(filename).name
    if len(name) <= max_chars:
        return name
    ext = Path(name).suffix
    stem = Path(name).stem
    avail = max_chars - len(ext) - 3
    if avail < 4:
        return name[: max_chars - 3] + "..."
    half = avail // 2
    return f"{stem[:half]}...{stem[-(avail - half):]}{ext}"


CHAR_DISPLAY_MAP = {
    "char1": "🎭 Nhân vật 1",
    "char2": "🎭 Nhân vật 2",
    "char3": "🎭 Nhân vật 3",
    "char4": "🎭 Nhân vật 4",
    "all": "🎉 Tất cả nhân vật",
}

CHAR_VALUE_MAP = {
    "🎭 Nhân vật 1": "char1",
    "🎭 Nhân vật 2": "char2",
    "🎭 Nhân vật 3": "char3",
    "🎭 Nhân vật 4": "char4",
    "🎉 Tất cả nhân vật": "all",
    "char1": "char1",
    "char2": "char2",
    "char3": "char3",
    "char4": "char4",
    "all": "all",
}

CHAR_SHORT_TAGS = {
    "char1": "[NV 1]",
    "char2": "[NV 2]",
    "char3": "[NV 3]",
    "char4": "[NV 4]",
    "all": "[Tất cả]",
}


def get_char_display_name(key: str) -> str:
    k = str(key).lower().strip()
    return CHAR_DISPLAY_MAP.get(k, CHAR_DISPLAY_MAP["char1"])


def get_char_value_from_display(display: str) -> str:
    return CHAR_VALUE_MAP.get(display, "char1")


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
    """Thẻ quản lý chọn file video, âm thanh, nhân vật & priority cho từng món quà."""

    def __init__(
        self,
        parent: tk.Widget,
        gift_key: str,
        video_filename: str,
        priority: int,
        sound_filename: str = "",
        target_char: str = "char1",
        on_choose_file: callable = None,
        on_test: callable = None,
    ) -> None:
        super().__init__(parent, bg=CARD_BG, highlightbackground=PANEL_BORDER, highlightthickness=1, padx=10, pady=8)
        self.gift_key = gift_key
        self.on_choose_file = on_choose_file
        self.on_test = on_test

        emoji_map = {"rose": "🌹", "doughnut": "🍩", "perfume": "🧴", "tiktok": "♪", "lion": "🦁"}
        emoji = emoji_map.get(gift_key.lower(), "🎁")

        self.file_var = tk.StringVar(value=video_filename)
        self.sound_var = tk.StringVar(value=sound_filename)
        self.target_char_display_var = tk.StringVar(value=get_char_display_name(target_char))
        self.prio_var = tk.StringVar(value=str(priority))

        # --- ROW 0: Top Header (Emoji + Title + Target Combo + Prio Spinbox + Action Buttons) ---
        row0 = tk.Frame(self, bg=CARD_BG)
        row0.pack(fill="x", pady=(0, 6))

        lbl_icon = tk.Label(row0, text=emoji, font=("Segoe UI Emoji", 14), bg=CARD_BG)
        lbl_icon.pack(side="left", padx=(0, 6))

        lbl_title = tk.Label(row0, text=gift_key.title(), font=("Segoe UI", 10, "bold"), fg=COLOR_CYAN, bg=CARD_BG)
        lbl_title.pack(side="left")

        # Delete & Test Buttons
        btn_del = tk.Button(row0, text="🗑", font=("Segoe UI", 9, "bold"), bg="#334155", fg=COLOR_ROSE, activebackground=COLOR_ROSE, activeforeground="#fff", relief="flat", padx=5, pady=2, command=self._delete, cursor="hand2")
        btn_del.pack(side="right", padx=(4, 0))

        btn_test = tk.Button(row0, text="▶ Test", font=("Segoe UI", 8, "bold"), bg=COLOR_EMERALD, fg="#042f2e", activebackground="#34d399", relief="flat", padx=6, pady=2, command=lambda: self.on_test(self.gift_key), cursor="hand2")
        btn_test.pack(side="right", padx=(4, 0))

        # Priority Spinbox
        prio_box = tk.Frame(row0, bg=CARD_BG)
        prio_box.pack(side="right", padx=4)
        tk.Label(prio_box, text="Ưu tiên:", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=CARD_BG).pack(side="left", padx=(0, 2))
        spn = tk.Spinbox(prio_box, from_=1, to=10, textvariable=self.prio_var, width=2, bg="#0d131f", fg="#fff", buttonbackground="#1e293b", relief="flat", command=self._notify_change)
        spn.pack(side="left")

        # Target Character Combobox
        char_box = tk.Frame(row0, bg=CARD_BG)
        char_box.pack(side="right", padx=4)
        tk.Label(char_box, text="Nhân vật:", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=CARD_BG).pack(side="left", padx=(0, 2))
        cb_char = ttk.Combobox(char_box, values=list(CHAR_DISPLAY_MAP.values()), textvariable=self.target_char_display_var, width=13, state="readonly")
        cb_char.pack(side="left")
        cb_char.bind("<<ComboboxSelected>>", lambda _: self._notify_change())

        # --- ROW 1: Media Chips (Clickable Video Button & Clickable Sound Button) ---
        row1 = tk.Frame(self, bg=CARD_BG)
        row1.pack(fill="x")

        # Video Button Chip (Click trực tiếp để chọn Video!)
        self.btn_video_chip = tk.Button(
            row1,
            text=self._format_video_label(),
            font=("Segoe UI", 8, "bold"),
            bg="#0d1527",
            fg=COLOR_CYAN,
            activebackground=COLOR_CYAN,
            activeforeground="#000",
            relief="groove",
            borderwidth=1,
            padx=6,
            pady=3,
            cursor="hand2",
            command=self._choose_video,
        )
        self.btn_video_chip.pack(side="left", fill="x", expand=True, padx=(0, 4))

        # Sound Button Chip (Click trực tiếp để chọn Âm Thanh!)
        self.btn_sound_chip = tk.Button(
            row1,
            text=self._format_sound_label(),
            font=("Segoe UI", 8, "bold"),
            bg="#0d1527",
            fg=COLOR_AMBER if sound_filename else TEXT_DARK,
            activebackground=COLOR_AMBER,
            activeforeground="#000",
            relief="groove",
            borderwidth=1,
            padx=6,
            pady=3,
            cursor="hand2",
            command=self._choose_sound,
        )
        self.btn_sound_chip.pack(side="left", fill="x", expand=True, padx=(0, 2))

        # Clear Sound Button (✕)
        self.btn_clear_sound = tk.Button(
            row1,
            text="✕",
            font=("Segoe UI", 8, "bold"),
            bg="#334155",
            fg=COLOR_ROSE,
            activebackground=COLOR_ROSE,
            activeforeground="#fff",
            relief="flat",
            padx=4,
            pady=2,
            cursor="hand2",
            command=self._clear_sound,
        )
        if sound_filename:
            self.btn_clear_sound.pack(side="left")

        for widget in (self, row0, row1, lbl_icon, lbl_title):
            widget.bind("<Enter>", lambda _: self.configure(bg=CARD_HOVER))
            widget.bind("<Leave>", lambda _: self.configure(bg=CARD_BG))

    def _format_video_label(self) -> str:
        val = self.file_var.get()
        if val:
            return f"🎥 Video: {shorten_filename(val, 16)}"
        return "🎥 Click Chọn Video..."

    def _format_sound_label(self) -> str:
        val = self.sound_var.get()
        if val:
            return f"🎵 Tiếng: {shorten_filename(val, 14)}"
        return "🎵 Click Chọn Âm Thanh (.mp3)..."

    def _clear_sound(self) -> None:
        self.sound_var.set("")
        self.btn_sound_chip.configure(text=self._format_sound_label(), fg=TEXT_DARK)
        self.btn_clear_sound.pack_forget()
        self._notify_change()

    def _delete(self) -> None:
        if hasattr(self, "on_delete") and self.on_delete:
            self.on_delete(self.gift_key)

    def get_target_char_value(self) -> str:
        return get_char_value_from_display(self.target_char_display_var.get())

    def _notify_change(self) -> None:
        if self.on_choose_file:
            self.on_choose_file(self.gift_key, self.file_var.get(), self.get_priority(), self.sound_var.get(), self.get_target_char_value())

    def _choose_video(self) -> None:
        top = self.winfo_toplevel()
        filename = filedialog.askopenfilename(
            parent=top,
            title=f"Chọn video cho quà {self.gift_key.title()}",
            filetypes=[("Media Files", "*.mp4 *.mov *.mkv *.webm *.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        if filename:
            path = Path(filename)
            core.VIDEO_DIRECTORY = path.parent
            mapped_val = path.name if path.parent == core.VIDEO_DIRECTORY else str(path)
            self.file_var.set(mapped_val)
            self.btn_video_chip.configure(text=self._format_video_label(), fg=COLOR_CYAN)
            self._notify_change()
        with contextlib.suppress(Exception):
            top.lift()
            top.focus_force()

    def _choose_sound(self) -> None:
        top = self.winfo_toplevel()
        filename = filedialog.askopenfilename(
            parent=top,
            title=f"Chọn file âm thanh (.mp3, .wav) cho quà {self.gift_key.title()}",
            filetypes=[("Audio Files", "*.mp3 *.wav *.aac *.m4a *.ogg *.flac *.wma"), ("All files", "*.*")],
        )
        if filename:
            path = Path(filename)
            core.VIDEO_DIRECTORY = path.parent
            mapped_val = path.name if path.parent == core.VIDEO_DIRECTORY else str(path)
            self.sound_var.set(mapped_val)
            self.btn_sound_chip.configure(text=self._format_sound_label(), fg=COLOR_AMBER)
            if not self.btn_clear_sound.winfo_manager():
                self.btn_clear_sound.pack(side="left")
            self._notify_change()
        with contextlib.suppress(Exception):
            top.lift()
            top.focus_force()

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

    def set_subtitle(self, subtitle: str) -> None:
        self.lbl_sub.configure(text=subtitle)

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
        self.deck_buttons: dict[str, StreamDeckButton] = {}

        self.username = tk.StringVar(value=core.TIKTOK_USERNAME)
        self.obs_host = tk.StringVar(value=core.OBS_HOST)
        self.obs_port = tk.StringVar(value=str(core.OBS_PORT))
        self.obs_password = tk.StringVar(value=core.OBS_PASSWORD)
        self.scene_name = tk.StringVar(value=core.SCENE_NAME)
        self.idle_source = tk.StringVar(value=core.IDLE_SOURCE_NAME)
        self.action_source = tk.StringVar(value=core.ACTION_SOURCE_NAME)
        self.idle_video_1_name = tk.StringVar(value=shorten_filename(core.resolve_existing_media_path(core.IDLE_VIDEO_PATH_1).name, 16))
        self.idle_video_2_name = tk.StringVar(value=shorten_filename(core.resolve_existing_media_path(core.IDLE_VIDEO_PATH_2).name, 16))
        self.idle_video_3_name = tk.StringVar(value=shorten_filename(core.resolve_existing_media_path(core.IDLE_VIDEO_PATH_3).name, 16))
        self.idle_video_4_name = tk.StringVar(value=shorten_filename(core.resolve_existing_media_path(core.IDLE_VIDEO_PATH_4).name, 16))

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
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)

        ttk.Label(panel, text="⚙ CẤU HÌNH CONTROL ROOM", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 6))

        # 🚀 ACTION BUTTONS AT THE VERY TOP
        btn_box = tk.Frame(panel, bg=PANEL_BG)
        btn_box.pack(fill="x", pady=(0, 8))

        ttk.Button(btn_box, text="▶  BẮT ĐẦU KẾT NỐI", style="Primary.TButton", command=self.start).pack(fill="x")
        ttk.Button(btn_box, text="■  DỪNG HỆ THỐNG", style="Danger.TButton", command=self.stop).pack(fill="x", pady=(4, 0))

        # Checkboxes Frame
        chk_frame = tk.Frame(panel, bg="#1a2638", padx=6, pady=4)
        chk_frame.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(chk_frame, text="🧪 Bật Giả Lập (Mock Mode)", variable=self.mock_mode_var).pack(anchor="w")
        ttk.Checkbutton(chk_frame, text="📡 Kết Nối TikTok Live (Realtime)", variable=self.enable_tiktok_var).pack(anchor="w", pady=(2, 0))

        # TikTok Username Input
        u_box = tk.Frame(panel, bg=PANEL_BG)
        u_box.pack(fill="x", pady=(0, 8))
        ttk.Label(u_box, text="TikTok Username (Host Live):", style="PanelMuted.TLabel").pack(anchor="w", pady=(0, 2))
        ttk.Entry(u_box, textvariable=self.username).pack(fill="x")

        # IDLE VIDEO SELECTION CARD (SINGLE MAIN BACKGROUND)
        idle_box = tk.Frame(panel, bg=CARD_BG, highlightbackground=COLOR_CYAN, highlightthickness=1, padx=10, pady=8)
        idle_box.pack(fill="x", pady=(0, 8))

        tk.Label(idle_box, text="💤 VIDEO CHỜ NỀN LIVESTREAM (IDLE LOOP)", font=("Segoe UI", 9, "bold"), fg=COLOR_CYAN, bg=CARD_BG).pack(anchor="w", pady=(0, 4))

        idle_main_row = tk.Frame(idle_box, bg=CARD_BG)
        idle_main_row.pack(fill="x", pady=2)
        tk.Label(idle_main_row, textvariable=self.idle_video_1_name, font=("Segoe UI", 9, "bold"), fg=COLOR_EMERALD, bg="#0d131f", padx=6, pady=4, anchor="w").pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_pick_main = tk.Button(idle_main_row, text="📂 Chọn Video Nền", font=("Segoe UI", 9, "bold"), bg=COLOR_CYAN, fg="#083344", activebackground="#38bdf8", relief="flat", padx=8, pady=3, command=lambda: self.choose_idle_video("main"), cursor="hand2")
        btn_pick_main.pack(side="right")

        # Dedicated OBS Settings & Open Folder Buttons
        btn_obs_cfg = tk.Button(panel, text="⚙ Cài Đặt Kết Nối OBS Studio", font=("Segoe UI", 9, "bold"), bg="#1e293b", fg=COLOR_CYAN, activebackground=COLOR_CYAN, activeforeground="#000", relief="flat", padx=6, pady=5, command=self.open_obs_settings_dialog)
        btn_obs_cfg.pack(fill="x", pady=(4, 4))

        ttk.Button(panel, text="📁 Mở Thư Mục Videos", style="Soft.TButton", command=self.open_video_folder).pack(fill="x")
        return panel

    def open_obs_settings_dialog(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("⚙ Cấu Hình Kết Nối OBS Studio & Scene")
        dlg.geometry("480x350")
        dlg.resizable(False, False)
        dlg.configure(bg="#0f172a")
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="⚙ CẤU HÌNH OBS STUDIO WEBSOCKET V5", font=("Segoe UI", 11, "bold"), fg=COLOR_CYAN, bg="#0f172a").pack(anchor="w", padx=16, pady=(14, 10))

        form = tk.Frame(dlg, bg="#0f172a", padx=16)
        form.pack(fill="x")
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        # Host & Port
        tk.Label(form, text="OBS Host:", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").grid(row=0, column=0, sticky="w")
        tk.Label(form, text="OBS Port:", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").grid(row=0, column=1, sticky="w", padx=(6, 0))
        e_host = tk.Entry(form, bg="#182335", fg="#fff", insertbackground="#fff", font=("Segoe UI", 10), relief="flat")
        e_host.insert(0, self.obs_host.get())
        e_host.grid(row=1, column=0, sticky="ew", pady=(2, 6))

        e_port = tk.Entry(form, bg="#182335", fg="#fff", insertbackground="#fff", font=("Segoe UI", 10), relief="flat")
        e_port.insert(0, self.obs_port.get())
        e_port.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(2, 6))

        # Password & Scene Name
        tk.Label(form, text="OBS Mật khẩu (Password):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").grid(row=2, column=0, sticky="w")
        tk.Label(form, text="Tên Scene (Scene Name):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").grid(row=2, column=1, sticky="w", padx=(6, 0))
        e_pass = tk.Entry(form, bg="#182335", fg="#fff", insertbackground="#fff", font=("Segoe UI", 10), show="*", relief="flat")
        e_pass.insert(0, self.obs_password.get())
        e_pass.grid(row=3, column=0, sticky="ew", pady=(2, 6))

        e_scene = tk.Entry(form, bg="#182335", fg="#fff", insertbackground="#fff", font=("Segoe UI", 10), relief="flat")
        e_scene.insert(0, self.scene_name.get())
        e_scene.grid(row=3, column=1, sticky="ew", padx=(6, 0), pady=(2, 6))

        # Idle & Action Sources
        tk.Label(form, text="Nguồn Video Chờ (Idle Source):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").grid(row=4, column=0, sticky="w")
        tk.Label(form, text="Nguồn Hiệu Ứng (Action Source):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").grid(row=4, column=1, sticky="w", padx=(6, 0))
        e_idle = tk.Entry(form, bg="#182335", fg="#fff", insertbackground="#fff", font=("Segoe UI", 10), relief="flat")
        e_idle.insert(0, self.idle_source.get())
        e_idle.grid(row=5, column=0, sticky="ew", pady=(2, 6))

        e_action = tk.Entry(form, bg="#182335", fg="#fff", insertbackground="#fff", font=("Segoe UI", 10), relief="flat")
        e_action.insert(0, self.action_source.get())
        e_action.grid(row=5, column=1, sticky="ew", padx=(6, 0), pady=(2, 6))

        btn_box = tk.Frame(dlg, bg="#0f172a", padx=16, pady=16)
        btn_box.pack(fill="x", side="bottom")

        def _save_obs() -> None:
            try:
                p = int(e_port.get().strip())
            except ValueError:
                messagebox.showerror("Lỗi", "OBS Port phải là dạng số.", parent=dlg)
                return

            self.obs_host.set(e_host.get().strip())
            self.obs_port.set(str(p))
            self.obs_password.set(e_pass.get())
            self.scene_name.set(e_scene.get().strip())
            self.idle_source.set(e_idle.get().strip())
            self.action_source.set(e_action.get().strip())

            self._apply_config()
            messagebox.showinfo("Thành công", "Đã lưu cài đặt kết nối OBS Studio!", parent=dlg)
            dlg.destroy()

        tk.Button(btn_box, text="✔ LƯU CẤU HÌNH OBS", font=("Segoe UI", 10, "bold"), bg=COLOR_EMERALD, fg="#042f2e", relief="flat", padx=12, pady=6, command=_save_obs).pack(side="right")
        tk.Button(btn_box, text="Hủy", font=("Segoe UI", 9), bg="#334155", fg="#fff", relief="flat", padx=10, pady=6, command=dlg.destroy).pack(side="right", padx=(0, 6))

    def choose_idle_video(self, target_char: str = "char1") -> None:
        char_label = "Nền Chung" if target_char == "main" else get_char_display_name(target_char)
        filename = filedialog.askopenfilename(
            parent=self.root,
            title=f"Chọn Video Chờ (Idle Loop) cho {char_label}",
            filetypes=[("Media Files", "*.mp4 *.mov *.mkv *.webm *.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        if filename:
            path = Path(filename)
            core.VIDEO_DIRECTORY = path.parent
            if target_char == "main":
                core.IDLE_VIDEO_PATH = path
                core.IDLE_VIDEO_PATH_1 = path
                core.IDLE_VIDEO_PATH_2 = path
                core.IDLE_VIDEO_PATH_3 = path
                core.IDLE_VIDEO_PATH_4 = path
                short_n = shorten_filename(path.name, 16)
                self.idle_video_1_name.set(short_n)
                self.idle_video_2_name.set(short_n)
                self.idle_video_3_name.set(short_n)
                self.idle_video_4_name.set(short_n)
            elif target_char == "char2":
                core.IDLE_VIDEO_PATH_2 = path
                self.idle_video_2_name.set(shorten_filename(path.name, 16))
            elif target_char == "char3":
                core.IDLE_VIDEO_PATH_3 = path
                self.idle_video_3_name.set(shorten_filename(path.name, 16))
            elif target_char == "char4":
                core.IDLE_VIDEO_PATH_4 = path
                self.idle_video_4_name.set(shorten_filename(path.name, 16))
            else:
                core.IDLE_VIDEO_PATH_1 = path
                core.IDLE_VIDEO_PATH = path
                self.idle_video_1_name.set(shorten_filename(path.name, 16))

            logging.getLogger(__name__).info("Đã chọn Video Chờ mới cho %s: %s", char_label, path.name)
            if self.app and self.run_loop:
                if target_char == "main":
                    for c in ("char1", "char2", "char3", "char4", "main"):
                        asyncio.run_coroutine_threadsafe(self.app.obs.set_idle_video(path, c), self.run_loop)
                else:
                    asyncio.run_coroutine_threadsafe(self.app.obs.set_idle_video(path, target_char), self.run_loop)
        with contextlib.suppress(Exception):
            self.root.lift()
            self.root.focus_force()

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
            ("🌹", "Rose (Hoa Hồng)", COLOR_ROSE, "rose"),
            ("🍩", "Doughnut (Bánh)", COLOR_AMBER, "doughnut"),
            ("♪", "TikTok", COLOR_CYAN, "tiktok"),
            ("🦁", "Lion (Sư Tử - Ngắt)", COLOR_PURPLE, "lion"),
        ]

        for col, (emoji, title, color, gift_key) in enumerate(buttons_data):
            mapped = core.GIFT_MAPPING.get(gift_key)
            if mapped:
                fn = mapped[0]
                prio = mapped[1]
                sound_fn = mapped[2] if len(mapped) > 2 else ""
                sound_icon = " 🔊" if sound_fn else ""
                sub = f"Prio: {prio} | {shorten_filename(fn, 14)}{sound_icon}"
            else:
                sub = "Priority: --"

            btn = StreamDeckButton(deck_grid, emoji, title, sub, color, command=lambda g=gift_key: self.test_gift(g))
            btn.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 4, 4 if col < 3 else 0))
            deck_grid.columnconfigure(col, weight=1)
            self.deck_buttons[gift_key] = btn

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

        btn_add = tk.Button(m_top, text="➕ Thêm Quà Mới", font=("Segoe UI", 9, "bold"), bg=COLOR_EMERALD, fg="#042f2e", activebackground="#34d399", relief="flat", padx=6, pady=2, command=self.prompt_add_new_gift)
        btn_add.pack(side="right", padx=(4, 0))

        btn_save = tk.Button(m_top, text="💾 Lưu Mapping", font=("Segoe UI", 9, "bold"), bg="#1e293b", fg=TEXT_MAIN, activebackground=COLOR_CYAN, activeforeground="#000", relief="flat", padx=6, pady=2, command=self.save_mapping)
        btn_save.pack(side="right")

        # Scrollable container for Gift Mapping Cards
        canvas_map = tk.Canvas(map_panel, bg=PANEL_BG, highlightthickness=0)
        scroll_map = ttk.Scrollbar(map_panel, orient="vertical", command=canvas_map.yview)
        self.cards_container = tk.Frame(canvas_map, bg=PANEL_BG)

        cards_win_id = canvas_map.create_window((0, 0), window=self.cards_container, anchor="nw")
        self.cards_container.bind("<Configure>", lambda e: canvas_map.configure(scrollregion=canvas_map.bbox("all")))
        canvas_map.bind("<Configure>", lambda e: canvas_map.itemconfig(cards_win_id, width=e.width))
        canvas_map.configure(yscrollcommand=scroll_map.set)

        canvas_map.pack(side="left", fill="both", expand=True)
        scroll_map.pack(side="right", fill="y")

        self._refresh_cards_container()
        return frame

    def _refresh_cards_container(self) -> None:
        for widget in self.cards_container.winfo_children():
            widget.destroy()
        self.gift_cards.clear()

        for gift, mapped in core.GIFT_MAPPING.items():
            filename = mapped[0]
            priority = mapped[1]
            sound_filename = mapped[2] if len(mapped) > 2 else ""
            target_char = mapped[3] if len(mapped) > 3 else "char1"
            card = GiftMappingCard(
                self.cards_container,
                gift_key=gift,
                video_filename=filename,
                priority=priority,
                sound_filename=sound_filename,
                target_char=target_char,
                on_choose_file=self.update_card_mapping,
                on_test=self.test_gift,
            )
            card.on_delete = self.delete_gift_mapping
            card.pack(fill="x", pady=3)
            self.gift_cards[gift] = card

    def prompt_add_new_gift(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("➕ Thêm Món Quà Mới")
        dlg.geometry("460x390")
        dlg.resizable(False, False)
        dlg.configure(bg="#0f172a")
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="➕ THÊM QÙA TẶNG TIKTOK MỚI", font=("Segoe UI", 11, "bold"), fg=COLOR_CYAN, bg="#0f172a").pack(anchor="w", padx=16, pady=(14, 10))

        form = tk.Frame(dlg, bg="#0f172a", padx=16)
        form.pack(fill="x")

        tk.Label(form, text="Tên quà TikTok (ví dụ: heart, cap, galaxy):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").pack(anchor="w", pady=(4, 2))
        gift_entry = tk.Entry(form, bg="#182335", fg="#ffffff", insertbackground="#fff", font=("Segoe UI", 10), relief="flat")
        gift_entry.pack(fill="x", ipady=4)
        gift_entry.focus_set()

        prio_frame = tk.Frame(form, bg="#0f172a")
        prio_frame.pack(fill="x", pady=(8, 4))
        tk.Label(prio_frame, text="Cấp độ ưu tiên (Priority 1-10):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").pack(side="left")
        prio_var = tk.StringVar(value="1")
        spn_prio = tk.Spinbox(prio_frame, from_=1, to=10, textvariable=prio_var, width=4, bg="#182335", fg="#fff", buttonbackground="#1e293b", relief="flat")
        spn_prio.pack(side="left", padx=8)

        # Target Character Selector
        char_sel_frame = tk.Frame(form, bg="#0f172a")
        char_sel_frame.pack(fill="x", pady=(6, 0))
        tk.Label(char_sel_frame, text="Áp dụng cho Nhân vật:", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").pack(side="left")
        target_char_display_var = tk.StringVar(value=get_char_display_name("char1"))
        cb_target_char = ttk.Combobox(char_sel_frame, values=list(CHAR_DISPLAY_MAP.values()), textvariable=target_char_display_var, width=18, state="readonly")
        cb_target_char.pack(side="left", padx=8)

        # File Media
        file_path_var = tk.StringVar(value="")
        file_frame = tk.Frame(form, bg="#0f172a")
        file_frame.pack(fill="x", pady=(6, 0))
        tk.Label(file_frame, text="File Media (Video/Ảnh):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").pack(anchor="w", pady=(0, 2))

        file_row = tk.Frame(file_frame, bg="#0f172a")
        file_row.pack(fill="x")
        lbl_file_path = tk.Label(file_row, textvariable=file_path_var, font=("Segoe UI", 8), fg=COLOR_CYAN, bg="#182335", anchor="w", padx=6, pady=4)
        lbl_file_path.pack(side="left", fill="x", expand=True)

        def _browse_video() -> None:
            fn = filedialog.askopenfilename(
                parent=dlg,
                title="Chọn Video / Ảnh cho quà",
                filetypes=[("Media Files", "*.mp4 *.mov *.mkv *.webm *.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
            )
            if fn:
                file_path_var.set(fn)
            with contextlib.suppress(Exception):
                dlg.lift()
                dlg.focus_force()

        tk.Button(file_row, text="📂 Chọn Video", font=("Segoe UI", 8, "bold"), bg=COLOR_AMBER, fg="#000", relief="flat", padx=6, pady=3, command=_browse_video).pack(side="right", padx=(4, 0))

        # File Sound
        sound_path_var = tk.StringVar(value="")
        sound_frame = tk.Frame(form, bg="#0f172a")
        sound_frame.pack(fill="x", pady=(6, 0))
        tk.Label(sound_frame, text="File Âm thanh đi kèm (Tùy chọn .mp3, .wav):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").pack(anchor="w", pady=(0, 2))

        sound_row = tk.Frame(sound_frame, bg="#0f172a")
        sound_row.pack(fill="x")
        lbl_sound_path = tk.Label(sound_row, textvariable=sound_path_var, font=("Segoe UI", 8), fg=COLOR_AMBER, bg="#182335", anchor="w", padx=6, pady=4)
        lbl_sound_path.pack(side="left", fill="x", expand=True)

        def _browse_sound() -> None:
            fn = filedialog.askopenfilename(
                parent=dlg,
                title="Chọn tệp âm thanh cho quà",
                filetypes=[("Audio Files", "*.mp3 *.wav *.aac *.m4a *.ogg *.flac *.wma"), ("All files", "*.*")],
            )
            if fn:
                sound_path_var.set(fn)
            with contextlib.suppress(Exception):
                dlg.lift()
                dlg.focus_force()

        tk.Button(sound_row, text="🎵 Chọn Tiếng", font=("Segoe UI", 8, "bold"), bg="#1e293b", fg=COLOR_AMBER, relief="flat", padx=6, pady=3, command=_browse_sound).pack(side="right", padx=(4, 0))

        btn_box = tk.Frame(dlg, bg="#0f172a", padx=16, pady=16)
        btn_box.pack(fill="x", side="bottom")

        def _confirm() -> None:
            key = gift_entry.get().strip().lower()
            if not key:
                messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập tên quà TikTok.", parent=dlg)
                return
            fn = file_path_var.get().strip()
            if not fn:
                messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn file media cho quà.", parent=dlg)
                return
            try:
                prio = int(prio_var.get())
            except ValueError:
                prio = 1

            path = Path(fn)
            core.VIDEO_DIRECTORY = path.parent
            mapped_val = path.name if path.parent == core.VIDEO_DIRECTORY else str(path)

            s_fn = sound_path_var.get().strip()
            sound_mapped_val = ""
            if s_fn:
                spath = Path(s_fn)
                sound_mapped_val = spath.name if spath.parent == core.VIDEO_DIRECTORY else str(spath)

            target_char = get_char_value_from_display(target_char_display_var.get())

            core.GIFT_MAPPING[key] = (mapped_val, prio, sound_mapped_val, target_char)
            core.save_gift_mapping(core.GIFT_MAPPING)

            self._refresh_cards_container()
            self._refresh_stream_deck_grid()
            logging.getLogger(__name__).info("➕ Đã thêm món quà mới: '%s' -> %s (Priority %s, Target: %s, Sound: %s)", key.title(), path.name, prio, get_char_display_name(target_char), sound_mapped_val or "Không")
            dlg.destroy()

        tk.Button(btn_box, text="✔ XÁC NHẬN THÊM", font=("Segoe UI", 10, "bold"), bg=COLOR_EMERALD, fg="#042f2e", relief="flat", padx=12, pady=6, command=_confirm).pack(side="right")
        tk.Button(btn_box, text="Hủy", font=("Segoe UI", 9), bg="#334155", fg="#fff", relief="flat", padx=10, pady=6, command=dlg.destroy).pack(side="right", padx=(0, 6))

    def delete_gift_mapping(self, gift_key: str) -> None:
        ans = messagebox.askyesno("Xóa Quà", f"Bạn có chắc muốn xóa quà '{gift_key.title()}' khỏi danh sách mapping?")
        if ans:
            if gift_key in core.GIFT_MAPPING:
                del core.GIFT_MAPPING[gift_key]
                core.save_gift_mapping(core.GIFT_MAPPING)
            self._refresh_cards_container()
            self._refresh_stream_deck_grid()
            logging.getLogger(__name__).info("🗑 Đã xóa món quà: '%s'", gift_key.title())

    def _refresh_stream_deck_grid(self) -> None:
        if not hasattr(self, "deck_grid") or not self.deck_grid:
            return
        for widget in self.deck_grid.winfo_children():
            widget.destroy()
        self.deck_buttons.clear()

        buttons_data = [
            ("🌹", "Rose (Hoa Hồng - NV 1)", COLOR_ROSE, "rose"),
            ("🍩", "Doughnut (Bánh - NV 2)", COLOR_AMBER, "doughnut"),
            ("♪", "TikTok (Nhảy - NV 3)", COLOR_CYAN, "tiktok"),
            ("🦁", "Lion (Sư Tử - Tất Cả)", COLOR_PURPLE, "lion"),
        ]
        for gift in core.GIFT_MAPPING.keys():
            if gift not in [b[3] for b in buttons_data]:
                emoji_map = {"rose": "🌹", "doughnut": "🍩", "perfume": "🧴", "tiktok": "♪", "lion": "🦁"}
                emoji = emoji_map.get(gift, "🎁")
                buttons_data.append((emoji, gift.title(), COLOR_CYAN, gift))

        for col, (emoji, title, color, gift_key) in enumerate(buttons_data):
            mapped = core.GIFT_MAPPING.get(gift_key)
            if mapped:
                fn = mapped[0]
                prio = mapped[1]
                sound_fn = mapped[2] if len(mapped) > 2 else ""
                target_char = mapped[3] if len(mapped) > 3 else "char1"
                sound_icon = " 🔊" if sound_fn else ""
                char_tag = f" {CHAR_SHORT_TAGS.get(target_char, '[Chó 1]')}"
                sub = f"Prio: {prio}{char_tag} | {shorten_filename(fn, 12)}{sound_icon}"
            else:
                sub = "Priority: --"

            btn = StreamDeckButton(self.deck_grid, emoji, title, sub, color, command=lambda g=gift_key: self.test_gift(g))
            btn.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 4, 4 if col < 3 else 0))
            self.deck_grid.columnconfigure(col, weight=1)
            self.deck_buttons[gift_key] = btn

    def update_card_mapping(self, gift_key: str, filename: str, priority: int, sound_filename: str = "", target_char: str = "char1") -> None:
        core.GIFT_MAPPING[gift_key] = (filename, priority, sound_filename, target_char)
        core.save_gift_mapping(core.GIFT_MAPPING)
        fn_name = Path(filename).name
        sound_icon = " 🔊" if sound_filename else ""
        char_tag = f" {CHAR_SHORT_TAGS.get(target_char, '[Chó 1]')}"
        if gift_key in self.deck_buttons:
            self.deck_buttons[gift_key].set_subtitle(f"Prio: {priority}{char_tag} | {shorten_filename(fn_name, 12)}{sound_icon}")
        logging.getLogger(__name__).info("Đã cập nhật quà %s: %s (Priority %s, Target: %s, Sound: %s)", gift_key.title(), fn_name, priority, get_char_display_name(target_char), sound_filename or "Không")

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
            sound_filename = card.sound_var.get().strip()
            target_char = card.get_target_char_value()
            core.GIFT_MAPPING[gift] = (filename, prio, sound_filename, target_char)
            fn_name = Path(filename).name
            sound_icon = " 🔊" if sound_filename else ""
            char_tag = f" {CHAR_SHORT_TAGS.get(target_char, '[Chó 1]')}"
            if gift in self.deck_buttons:
                self.deck_buttons[gift].set_subtitle(f"Prio: {prio}{char_tag} | {shorten_filename(fn_name, 12)}{sound_icon}")
        core.save_gift_mapping(core.GIFT_MAPPING)
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
