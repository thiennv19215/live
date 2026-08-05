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
from typing import Any, Callable

import tiktok_obs_controller as core

from tiktok_obs_gui_mapping import GiftMappingMixin
from tiktok_obs_gui_settings import ObsSettingsMixin
from tiktok_obs_gui_widgets import (
    BG_DARK,
    CARD_BG,
    COLOR_AMBER,
    COLOR_BLUE,
    COLOR_CYAN,
    COLOR_EMERALD,
    COLOR_PURPLE,
    COLOR_ROSE,
    PANEL_BG,
    PANEL_BORDER,
    TEXT_MAIN,
    TEXT_MUTED,
    CanvasProgressBar,
    ColorLogHandler,
    GiftMappingCard,
    StatusPill,
    StreamDeckButton,
    get_media_mapping_value,
    refresh_character_maps,
    shorten_filename,
)


class TikTokObsGui(ObsSettingsMixin, GiftMappingMixin):
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TikTok Live Control Room v3.1 - Stream Deck Edition")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = min(1380, max(1120, screen_width - 40))
        window_height = min(860, max(740, screen_height - 80))
        pos_x = max(0, (screen_width - window_width) // 2)
        pos_y = max(0, (screen_height - window_height) // 2)
        self.root.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")
        self.root.minsize(1120, 740)
        self.root.configure(bg=BG_DARK)

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.app: core.TikTokObsApp | None = None
        self.run_loop: asyncio.AbstractEventLoop | None = None
        self.run_future: asyncio.Future[None] | None = None
        self._closing = False
        self._close_deadline = 0.0

        self.recent_history: list[core.GiftJob] = []
        self._last_completed_job: core.GiftJob | None = None
        self.gift_cards: dict[str, GiftMappingCard] = {}
        self.deck_buttons: dict[str, StreamDeckButton] = {}
        self.idle_status_labels: dict[str, tk.Label] = {}
        self.idle_video_name_vars: dict[str, tk.StringVar] = {}
        self._pending_obs_operations: set[Any] = set()

        self.username = tk.StringVar(value=core.TIKTOK_USERNAME)
        self.obs_host = tk.StringVar(value=core.OBS_HOST)
        self.obs_port = tk.StringVar(value=str(core.OBS_PORT))
        self.obs_password = tk.StringVar(value=core.OBS_PASSWORD)
        self.scene_name = tk.StringVar(value=core.SCENE_NAME)
        self.idle_source = tk.StringVar(value=core.IDLE_SOURCE_NAME)
        self.action_source = tk.StringVar(value=core.ACTION_SOURCE_NAME)
        idle_path = core.get_idle_video_path("main")
        self.idle_video_name_vars["main"] = tk.StringVar(
            value=shorten_filename(core.resolve_existing_media_path(idle_path).name, 24)
        )

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
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        # Header Section
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))

        title_box = ttk.Frame(header)
        title_box.pack(side="left")
        ttk.Label(title_box, text="TikTok Live Control Room", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Một video nền · Quà đến là gọi hành động trên OBS", style="Subtitle.TLabel").pack(anchor="w")

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
        body.columnconfigure(0, weight=0, minsize=340)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Left Column: Cấu hình Hệ thống & Video Chờ (Nút Kết Nối Nổi Bật Ở Trên Cùng)
        self._build_settings_panel(body).grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        # Right Column: Stream Deck + Visual Gift Video Cards Grid + Logs
        right_panel = ttk.Frame(body)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.rowconfigure(1, weight=1)
        right_panel.columnconfigure(0, weight=1)

        # 1. Stream Deck Gift Test Buttons
        self._build_stream_deck(right_panel).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        # 2. Queue Table & Visual Gift Video Cards Split
        self._build_queue_and_visual_mapping(right_panel).grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        # 3. Logs Console
        self._build_log_console(right_panel).grid(row=2, column=0, sticky="ew")

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

        val_lbl = tk.Label(inner, textvariable=var, font=("Segoe UI", 10, "bold"), fg=TEXT_MAIN, bg=CARD_BG, anchor="w", width=28, wraplength=250, justify="left")
        val_lbl.pack(anchor="w")
        tk.Label(inner, text=title, font=("Segoe UI", 9), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w", pady=(2, 0))
        return val_lbl

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
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)

        header = ttk.Frame(panel, style="Panel.TFrame")
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(header, text="🎛 STREAM DECK", style="PanelTitle.TLabel").pack(side="left")
        ttk.Label(header, text="Bấm nhanh để kiểm tra quà và thứ tự FIFO", style="PanelMuted.TLabel").pack(side="left", padx=(10, 0))

        automation = ttk.Frame(panel, style="Panel.TFrame")
        automation.pack(fill="x", pady=(0, 7))
        ttk.Button(automation, text="⚡ Chạy combo 3 quà", style="Accent.TButton", command=self.run_e2e_combo_test).pack(side="right")
        ttk.Button(automation, text="Rose → Lion FIFO", style="Soft.TButton", command=self.run_e2e_interrupt_test).pack(side="right", padx=4)

        # 4 Interactive Stream Deck Buttons
        self.deck_grid = tk.Frame(panel, bg=PANEL_BG)
        self.deck_grid.pack(fill="x")

        buttons_data = [
            ("🌹", "Rose", COLOR_ROSE, "rose"),
            ("🍩", "Doughnut", COLOR_AMBER, "doughnut"),
            ("♪", "TikTok", COLOR_CYAN, "tiktok"),
            ("🦁", "Lion", COLOR_PURPLE, "lion"),
        ]

        for index, (emoji, title, color, gift_key) in enumerate(buttons_data):
            mapped = core.GIFT_MAPPING.get(gift_key)
            if mapped:
                fn = mapped[0]
                prio = mapped[1]
                sound_fn = mapped[2] if len(mapped) > 2 else ""
                sound_icon = " 🔊" if sound_fn else ""
                sub = f"Mức {prio} · {shorten_filename(fn, 14)}{sound_icon}"
            else:
                sub = "Priority: --"

            btn = StreamDeckButton(self.deck_grid, emoji, title, sub, color, command=lambda g=gift_key: self.test_gift(g))
            row, col = divmod(index, 2)
            btn.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 4, 4 if col == 0 else 0), pady=(0, 4 if row == 0 else 0))
            self.deck_grid.columnconfigure(col, weight=1, uniform="deck")
            self.deck_buttons[gift_key] = btn

        return panel

    def _build_queue_and_visual_mapping(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=0, minsize=370)
        frame.columnconfigure(1, weight=1, minsize=520)
        frame.rowconfigure(0, weight=1)

        # Left Sub-panel: Queue Chờ & Trạng Thái
        queue_panel = ttk.Frame(frame, style="Panel.TFrame", padding=10)
        queue_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        queue_panel.configure(width=370)
        queue_panel.grid_propagate(False)

        q_top = ttk.Frame(queue_panel, style="Panel.TFrame")
        q_top.pack(fill="x", pady=(0, 6))
        ttk.Label(q_top, text="📋 HÀNG ĐỢI PHÁT", style="PanelTitle.TLabel").pack(side="left")
        ttk.Label(q_top, textvariable=self.queue_count_text, style="PanelMuted.TLabel").pack(side="left", padx=(8, 0))
        ttk.Button(q_top, text="Xóa hàng đợi", style="Soft.TButton", command=self.clear_queue).pack(side="right")

        self.queue_tree = ttk.Treeview(queue_panel, columns=("status", "gift", "file", "prio"), show="headings", height=5)
        self.queue_tree.heading("status", text="Trạng Thái")
        self.queue_tree.heading("gift", text="Tên Quà")
        self.queue_tree.heading("file", text="File Video")
        self.queue_tree.heading("prio", text="Mức")

        self.queue_tree.column("status", width=85, anchor="center")
        self.queue_tree.column("gift", width=70)
        self.queue_tree.column("file", width=130)
        self.queue_tree.column("prio", width=40, anchor="center")
        self.queue_tree.pack(fill="both", expand=True)

        self.queue_tree.tag_configure("playing", background="#064e3b", foreground="#67e8c0")
        self.queue_tree.tag_configure("waiting", background="#1e293b", foreground="#f8fafc")
        self.queue_tree.tag_configure("done", background="#0f172a", foreground="#64748b")

        # Right Sub-panel: Visual Gift Mapping Cards Grid
        map_panel = ttk.Frame(frame, style="Panel.TFrame", padding=10)
        map_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        m_top = ttk.Frame(map_panel, style="Panel.TFrame")
        m_top.pack(fill="x", pady=(0, 4))
        ttk.Label(m_top, text="🎯 QUÀ & HÀNH ĐỘNG", style="PanelTitle.TLabel").pack(side="left")

        map_actions = ttk.Frame(map_panel, style="Panel.TFrame")
        map_actions.pack(fill="x", pady=(0, 6))

        btn_action_presets = tk.Button(map_actions, text="⚡ Kho Hành Động", font=("Segoe UI", 9, "bold"), bg="#1e293b", fg=COLOR_CYAN, activebackground=COLOR_CYAN, activeforeground="#000", relief="flat", padx=6, pady=2, command=self.prompt_manage_action_presets)
        btn_action_presets.pack(side="right", padx=(4, 0))

        btn_add = tk.Button(map_actions, text="➕ Thêm Quà", font=("Segoe UI", 9, "bold"), bg=COLOR_EMERALD, fg="#042f2e", activebackground="#34d399", relief="flat", padx=6, pady=2, command=self.prompt_add_new_gift)
        btn_add.pack(side="right", padx=(4, 0))

        btn_save = tk.Button(map_actions, text="💾 Lưu", font=("Segoe UI", 9, "bold"), bg="#1e293b", fg=TEXT_MAIN, activebackground=COLOR_CYAN, activeforeground="#000", relief="flat", padx=6, pady=2, command=self.save_mapping)
        btn_save.pack(side="right")

        # Scrollable container for Gift Mapping Cards
        canvas_map = tk.Canvas(map_panel, bg=PANEL_BG, highlightthickness=0)
        scroll_map = ttk.Scrollbar(map_panel, orient="vertical", command=canvas_map.yview)
        self.cards_container = tk.Frame(canvas_map, bg=PANEL_BG)

        cards_win_id = canvas_map.create_window((0, 0), window=self.cards_container, anchor="nw")
        self.cards_container.bind("<Configure>", lambda e: canvas_map.configure(scrollregion=canvas_map.bbox("all")))
        canvas_map.bind("<Configure>", lambda e: canvas_map.itemconfig(cards_win_id, width=e.width))
        canvas_map.configure(yscrollcommand=scroll_map.set)

        def _scroll_cards(event: tk.Event) -> None:
            canvas_map.yview_scroll(int(-event.delta / 120), "units")

        canvas_map.bind("<Enter>", lambda _: canvas_map.bind_all("<MouseWheel>", _scroll_cards))
        canvas_map.bind("<Leave>", lambda _: canvas_map.unbind_all("<MouseWheel>"))

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

    def _persist_runtime_config(self) -> None:
        try:
            port = int(self.obs_port.get())
        except ValueError:
            port = core.OBS_PORT
        idle_path = core.get_idle_video_path("main")
        assigned_paths = {"1": str(idle_path)} if core.resolve_existing_media_path(idle_path).is_file() else {}
        config = {
            "tiktok_username": self.username.get().strip().lstrip("@") or "mock_user",
            "obs_host": self.obs_host.get().strip(),
            "obs_port": port,
            "obs_password": self.obs_password.get(),
            "scene_name": self.scene_name.get().strip(),
            "idle_source_name": self.idle_source.get().strip(),
            "action_source_name": self.action_source.get().strip(),
            "character_count": 1,
            "idle_video_paths": assigned_paths,
        }
        if "1" in assigned_paths:
            config["idle_video_path_1"] = assigned_paths["1"]
        core.save_obs_config(config)

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
        self._persist_runtime_config()
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
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
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
            self.btn_stop.configure(state="disabled")

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
            logging.getLogger(__name__).info("🚀 RUNNING E2E FIFO COMBO: Rose -> Doughnut -> TikTok")
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
            logging.getLogger(__name__).info("🔥 RUNNING E2E FIFO TEST: Rose -> Lion")
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
            core.GIFT_MAPPING[gift] = (filename, prio, sound_filename, "main")
            vids, sound_filename, action_name = core.resolve_gift_action_media(filename, sound_filename)
            if len(vids) > 1:
                first_n = Path(vids[0]).name
                fn_display = f"{shorten_filename(first_n, 8)} (+{len(vids)-1} rnd)"
            elif len(vids) == 1 and vids[0]:
                fn_display = shorten_filename(Path(vids[0]).name, 12)
            else:
                fn_display = shorten_filename(action_name, 12)
            sound_icon = " 🔊" if sound_filename else ""
            if gift in self.deck_buttons:
                self.deck_buttons[gift].set_subtitle(f"Mức {prio} · {fn_display}{sound_icon}")
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
                if hasattr(self, "hero_emoji_lbl") and self.hero_emoji_lbl:
                    self.hero_emoji_lbl.configure(text=emoji)

                self.current_action_name.set(f"ĐANG PHÁT ACTION: {current_job.gift_name.upper()}")
                self.current_action_sub.set(f"File: {current_job.file_path.name} | Priority Level: {current_job.priority}")

                if self.run_loop and self.app.current_job_start_time > 0:
                    elapsed = self.run_loop.time() - self.app.current_job_start_time
                    dur = max(self.app.current_job_duration, 0.1)
                    rem = max(dur - elapsed, 0.0)
                    pct = min(100.0, (elapsed / dur) * 100.0)

                    if hasattr(self, "hero_progress") and self.hero_progress:
                        self.hero_progress.set_progress(pct)
                    self.timer_display.set(f"{rem:04.1f}s / {dur:04.1f}s")
            else:
                if hasattr(self, "hero_emoji_lbl") and self.hero_emoji_lbl:
                    self.hero_emoji_lbl.configure(text="💤")
                self.current_action_name.set("💤 ĐANG CHẠY VIDEO CHỜ (IDLE LOOP)")
                self.current_action_sub.set(f"Media Source: {core.IDLE_SOURCE_NAME} | File: {core.IDLE_VIDEO_PATH.name}")
                if hasattr(self, "hero_progress") and self.hero_progress:
                    self.hero_progress.set_progress(0.0)
                self.timer_display.set("LOOPING")

            self._refresh_queue_tree(current_job, queue_items)

        elif not (self.worker_thread and self.worker_thread.is_alive()):
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.pill_obs.set_status("OFFLINE", "offline")
            self.pill_tiktok.set_status("OFFLINE", "offline")
            self.sys_status_pill.set_status("OFFLINE", "offline")
            if hasattr(self, "hero_progress") and self.hero_progress:
                self.hero_progress.set_progress(0.0)
            self.timer_display.set("00.0s / 00.0s")
            self.current_action_name.set("IDLE (Chờ kết nối)")
            self.current_action_sub.set("Media Source: Disconnected")
            self._refresh_queue_tree(None, [])

        self.root.after(150, self._refresh_dashboard)

    def _refresh_queue_tree(self, active_job: core.GiftJob | None, queue_items: list[core.GiftJob]) -> None:
        tree_sig = (
            (active_job.gift_name, active_job.file_path.name) if active_job else None,
            tuple((j.gift_name, j.file_path.name) for j in queue_items),
            tuple((j.gift_name, j.file_path.name) for j in self.recent_history),
        )
        if getattr(self, "_last_tree_sig", None) == tree_sig:
            return
        self._last_tree_sig = tree_sig

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
        count = 0
        while count < 50:
            try:
                message, tag = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n", tag)
            self.log_text.see("end")
            try:
                line_count = int(self.log_text.index("end-1c").split(".")[0])
                if line_count > 300:
                    self.log_text.delete("1.0", f"{line_count - 300}.0")
            except Exception:
                pass
            self.log_text.configure(state="disabled")
            count += 1
        self.root.after(100, self._poll_logs)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._close_deadline = time.monotonic() + 4.0
        self.stop()
        self._wait_for_shutdown_before_close()

    def _wait_for_shutdown_before_close(self) -> None:
        worker_alive = bool(self.worker_thread and self.worker_thread.is_alive())
        if worker_alive and time.monotonic() < self._close_deadline:
            self.root.after(100, self._wait_for_shutdown_before_close)
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    TikTokObsGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
