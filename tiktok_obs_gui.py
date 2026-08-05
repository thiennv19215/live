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


def get_media_mapping_value(filename: str) -> str:
    """Keep external files absolute so mappings still work after restarting the app."""
    path = Path(filename).resolve()
    try:
        return str(path.relative_to(core.VIDEO_DIRECTORY.resolve()))
    except ValueError:
        return str(path)


CHAR_DISPLAY_MAP: dict[str, str] = {}
CHAR_VALUE_MAP: dict[str, str] = {}
CHAR_SHORT_TAGS: dict[str, str] = {}


def refresh_character_maps() -> None:
    CHAR_DISPLAY_MAP.clear()
    CHAR_VALUE_MAP.clear()
    CHAR_SHORT_TAGS.clear()
    for idx in range(1, core.CHARACTER_COUNT + 1):
        key = f"char{idx}"
        display = f"🎭 Nhân vật {idx}"
        CHAR_DISPLAY_MAP[key] = display
        CHAR_VALUE_MAP[display] = key
        CHAR_VALUE_MAP[key] = key
        CHAR_SHORT_TAGS[key] = f"[NV {idx}]"
    CHAR_DISPLAY_MAP["all"] = "🎉 Tất cả nhân vật"
    CHAR_VALUE_MAP["🎉 Tất cả nhân vật"] = "all"
    CHAR_VALUE_MAP["all"] = "all"
    CHAR_SHORT_TAGS["all"] = "[Tất cả]"


refresh_character_maps()


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


class ToolTip:
    """Hiển thị gợi ý popup khi di chuột qua widget."""

    def __init__(self, widget: tk.Widget, text_func: callable) -> None:
        self.widget = widget
        self.text_func = text_func
        self.tip_window: tk.Toplevel | None = None
        self.widget.bind("<Enter>", self.show_tip, add="+")
        self.widget.bind("<Leave>", self.hide_tip, add="+")

    def show_tip(self, event=None) -> None:
        self.hide_tip()
        try:
            text = self.text_func()
        except Exception:
            return
        if not text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(tw, text=text, justify="left", bg="#090d16", fg="#38bdf8", relief="solid", borderwidth=1, font=("Segoe UI", 9), padx=10, pady=8)
        lbl.pack()

    def hide_tip(self, event=None) -> None:
        if self.tip_window:
            with contextlib.suppress(Exception):
                self.tip_window.destroy()
            self.tip_window = None


class GiftMappingCard(tk.Frame):
    """Thẻ gán một hành động được gọi khi TikTok gửi món quà tương ứng."""

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
        self.prio_var = tk.StringVar(value=str(priority))

        # Header keeps identity and destructive actions separate from configuration.
        row0 = tk.Frame(self, bg=CARD_BG)
        row0.pack(fill="x", pady=(0, 5))

        lbl_icon = tk.Label(row0, text=emoji, font=("Segoe UI Emoji", 14), bg=CARD_BG)
        lbl_icon.pack(side="left", padx=(0, 6))

        lbl_title = tk.Label(row0, text=gift_key.title(), font=("Segoe UI", 10, "bold"), fg=COLOR_CYAN, bg=CARD_BG)
        lbl_title.pack(side="left")

        # Delete & Test Buttons
        btn_del = tk.Button(row0, text="🗑", font=("Segoe UI", 9, "bold"), bg="#334155", fg=COLOR_ROSE, activebackground=COLOR_ROSE, activeforeground="#fff", relief="flat", padx=5, pady=2, command=self._delete, cursor="hand2")
        btn_del.pack(side="right", padx=(4, 0))

        btn_test = tk.Button(row0, text="▶ Test", font=("Segoe UI", 8, "bold"), bg=COLOR_EMERALD, fg="#042f2e", activebackground="#34d399", relief="flat", padx=6, pady=2, command=lambda: self.on_test(self.gift_key), cursor="hand2")
        btn_test.pack(side="right", padx=(4, 0))

        settings_row = tk.Frame(self, bg="#111c2d", padx=6, pady=4)
        settings_row.pack(fill="x", pady=(0, 5))

        trigger_box = tk.Frame(settings_row, bg="#111c2d")
        trigger_box.pack(side="left", fill="x", expand=True)
        tk.Label(trigger_box, text="⚡ Nhận quà → gọi hành động", font=("Segoe UI", 8, "bold"), fg=COLOR_EMERALD, bg="#111c2d").pack(side="left")

        prio_box = tk.Frame(settings_row, bg="#111c2d")
        prio_box.pack(side="right")
        tk.Label(prio_box, text="Mức", font=("Segoe UI", 8), fg=TEXT_MUTED, bg="#111c2d").pack(side="left", padx=(0, 4))
        spn = tk.Spinbox(prio_box, from_=1, to=10, textvariable=self.prio_var, width=2, bg="#0d131f", fg="#fff", buttonbackground="#1e293b", relief="flat", command=self._notify_change)
        spn.pack(side="left")

        # --- ROW 1: Media Chips (Clickable Video Button & Clickable Sound Button) ---
        row1 = tk.Frame(self, bg=CARD_BG)
        row1.pack(fill="x")

        # Video Button Chip (Click trực tiếp để chọn Video!)
        self.btn_video_chip = tk.Button(
            row1,
            text=self._format_video_label(),
            font=("Segoe UI", 8, "bold"),
            bg="#0d1527",
            fg=self._video_status_color(),
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
        ToolTip(self.btn_video_chip, self._get_video_tooltip_text)

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

    def _video_status_color(self) -> str:
        videos, _, _ = core.resolve_gift_action_media(self.file_var.get().strip(), self.sound_var.get().strip())
        for filename in videos:
            path = Path(filename)
            candidate = path if path.is_absolute() else core.VIDEO_DIRECTORY / path
            if core.resolve_existing_media_path(candidate).is_file():
                return COLOR_CYAN
        return COLOR_ROSE

    def _refresh_video_chip(self) -> None:
        self.btn_video_chip.configure(text=self._format_video_label(), fg=self._video_status_color())

    def _get_video_tooltip_text(self) -> str:
        val = self.file_var.get().strip()
        if val in core.ACTION_PRESETS:
            preset = core.ACTION_PRESETS[val]
            lines = [f"⚡ HÀNH ĐỘNG: {preset.name}"]
            lines.append(f"Kho {len(preset.videos)} điệu nhảy random:")
            for idx, f in enumerate(preset.videos, 1):
                lines.append(f"  {idx}. {Path(f).name}")
            lines.append("\n👉 Click vào nút để chọn lại Hành Động hoặc gán Video trực tiếp.")
            return "\n".join(lines)

        files = core.parse_video_filenames(val)
        valid_files = [f for f in files if f]
        if not valid_files:
            return "🎥 Chưa gán Hành động/Video nào cho quà này.\n👉 Click nút để gán."
        if len(valid_files) == 1:
            return f"🎥 Video đang gán cho {self.gift_key.title()}:\n  • {valid_files[0]}\n\n💡 Mẹo: Click nút để chọn Hành Động từ Kho hoặc gán nhiều video."
        lines = [f"🎥 Danh sách {len(valid_files)} điệu nhảy random của quà {self.gift_key.title()}:"]
        for idx, f in enumerate(valid_files, 1):
            lines.append(f"  {idx}. {Path(f).name}")
        lines.append("\n👉 Click vào nút để chọn lại hoặc thay đổi danh sách video.")
        return "\n".join(lines)

    def _format_video_label(self) -> str:
        val = self.file_var.get().strip()
        if val in core.ACTION_PRESETS:
            preset = core.ACTION_PRESETS[val]
            return f"⚡ {shorten_filename(preset.name, 20)} · {len(preset.videos)} điệu"
        elif val:
            files = core.parse_video_filenames(val)
            if len(files) > 1:
                first_name = Path(files[0]).name
                return f"🎥 Video ({len(files)} điệu): {shorten_filename(first_name, 10)} (+{len(files)-1} random)"
            elif len(files) == 1 and files[0]:
                return f"🎥 Video: {shorten_filename(files[0], 16)}"
        return "🎥 Chọn video / hành động"

    def _format_sound_label(self) -> str:
        val = self.sound_var.get()
        if val:
            return f"🎵 Tiếng: {shorten_filename(val, 14)}"
        return "🎵 Chưa có âm thanh"

    def _clear_sound(self) -> None:
        self.sound_var.set("")
        self.btn_sound_chip.configure(text=self._format_sound_label(), fg=TEXT_DARK)
        self.btn_clear_sound.pack_forget()
        self._notify_change()

    def _delete(self) -> None:
        if hasattr(self, "on_delete") and self.on_delete:
            self.on_delete(self.gift_key)

    def get_target_char_value(self) -> str:
        return "main"

    def _notify_change(self) -> None:
        if self.on_choose_file:
            self.on_choose_file(self.gift_key, self.file_var.get(), self.get_priority(), self.sound_var.get(), self.get_target_char_value())

    def _choose_video(self) -> None:
        top = self.winfo_toplevel()
        dlg = tk.Toplevel(top)
        dlg.title(f"Gán Hành Động / Video cho Quà {self.gift_key.title()}")
        dlg.geometry("520x430")
        dlg.resizable(False, False)
        dlg.configure(bg="#0f172a")
        dlg.transient(top)

        tk.Label(dlg, text=f"🎬 GÁN HÀNH ĐỘNG CHO QUÀ {self.gift_key.upper()}", font=("Segoe UI", 11, "bold"), fg=COLOR_CYAN, bg="#0f172a").pack(anchor="w", padx=16, pady=(14, 10))

        # Option 1: Chọn từ Kho Hành Động (Action Presets)
        preset_frame = tk.LabelFrame(dlg, text=" ⚡ Tùy chọn 1: Chọn từ Kho Hành Động (Action Presets) ", font=("Segoe UI", 9, "bold"), fg=COLOR_EMERALD, bg="#0f172a", padx=12, pady=10)
        preset_frame.pack(fill="x", padx=16, pady=6)

        action_names = {aid: f"{p.name} ({len(p.videos)} điệu nhảy)" for aid, p in core.ACTION_PRESETS.items()}
        cb_values = list(action_names.values())

        curr_val = self.file_var.get().strip()
        curr_action_display = action_names.get(curr_val, cb_values[0] if cb_values else "")
        action_var = tk.StringVar(value=curr_action_display)

        cb_action = ttk.Combobox(preset_frame, values=cb_values, textvariable=action_var, state="readonly", font=("Segoe UI", 9))
        cb_action.pack(fill="x", pady=(4, 8))

        def _apply_preset() -> None:
            sel_display = action_var.get()
            selected_aid = None
            for aid, disp in action_names.items():
                if disp == sel_display:
                    selected_aid = aid
                    break
            if selected_aid:
                self.file_var.set(selected_aid)
                self._refresh_video_chip()
                self._notify_change()
                dlg.destroy()

        tk.Button(preset_frame, text="✔ Gán Hành Động Này", font=("Segoe UI", 9, "bold"), bg=COLOR_EMERALD, fg="#042f2e", relief="flat", padx=10, pady=4, command=_apply_preset).pack(anchor="e")

        # Option 2: Chọn File Video Trực Tiếp
        direct_frame = tk.LabelFrame(dlg, text=" 🎥 Tùy chọn 2: Chọn trực tiếp File Video trên máy ", font=("Segoe UI", 9, "bold"), fg=COLOR_CYAN, bg="#0f172a", padx=12, pady=10)
        direct_frame.pack(fill="x", padx=16, pady=6)

        tk.Label(direct_frame, text="Chọn 1 hoặc nhiều file video (giữ phím Ctrl để chọn nhiều file):", font=("Segoe UI", 8), fg=TEXT_MUTED, bg="#0f172a").pack(anchor="w", pady=(0, 6))

        def _browse_files() -> None:
            filenames = filedialog.askopenfilenames(
                parent=dlg,
                title=f"Chọn video cho quà {self.gift_key.title()}",
                filetypes=[("Media Files", "*.mp4 *.mov *.mkv *.webm *.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
            )
            if filenames:
                mapped_vals = []
                for filename in filenames:
                    mapped_vals.append(get_media_mapping_value(filename))
                combined_val = ", ".join(mapped_vals)
                self.file_var.set(combined_val)
                self._refresh_video_chip()
                self._notify_change()
                dlg.destroy()

        tk.Button(direct_frame, text="📂 Chọn File Video...", font=("Segoe UI", 9, "bold"), bg=COLOR_AMBER, fg="#000", relief="flat", padx=10, pady=4, command=_browse_files).pack(anchor="e")

        tk.Button(dlg, text="Hủy / Đóng", font=("Segoe UI", 9), bg="#334155", fg="#fff", relief="flat", padx=12, pady=4, command=dlg.destroy).pack(side="right", padx=16, pady=10)
        with contextlib.suppress(Exception):
            dlg.lift()
            dlg.after_idle(dlg.focus_set)

    def _choose_sound(self) -> None:
        top = self.winfo_toplevel()
        filename = filedialog.askopenfilename(
            parent=top,
            title=f"Chọn file âm thanh (.mp3, .wav) cho quà {self.gift_key.title()}",
            filetypes=[("Audio Files", "*.mp3 *.wav *.aac *.m4a *.ogg *.flac *.wma"), ("All files", "*.*")],
        )
        if filename:
            mapped_val = get_media_mapping_value(filename)
            self.sound_var.set(mapped_val)
            self.btn_sound_chip.configure(text=self._format_sound_label(), fg=COLOR_AMBER)
            if not self.btn_clear_sound.winfo_manager():
                self.btn_clear_sound.pack(side="left")
            self._notify_change()
        with contextlib.suppress(Exception):
            top.lift()
            top.after_idle(top.focus_set)

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
        icon_box = tk.Label(self, text=emoji, font=("Segoe UI Emoji", 16), bg=bg_color, fg="#ffffff", width=2, height=2)
        icon_box.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=2, pady=2)

        # Title Label
        lbl_title = tk.Label(self, text=title, font=("Segoe UI", 10, "bold"), fg=TEXT_MAIN, bg=CARD_BG, anchor="w")
        lbl_title.grid(row=0, column=1, sticky="w", padx=(7, 4), pady=(4, 0))

        # Subtitle Label
        lbl_sub = tk.Label(self, text=subtitle, font=("Segoe UI", 8), fg=TEXT_MUTED, bg=CARD_BG, anchor="w")
        lbl_sub.grid(row=1, column=1, sticky="w", padx=(7, 4), pady=(0, 4))

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

    def _build_settings_panel(self, parent: ttk.Frame) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)

        ttk.Label(panel, text="⚙ CẤU HÌNH CONTROL ROOM", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 6))

        # 🚀 ACTION BUTTONS AT THE VERY TOP
        btn_box = tk.Frame(panel, bg=PANEL_BG)
        btn_box.pack(fill="x", pady=(0, 8))

        self.btn_start = ttk.Button(btn_box, text="▶  BẮT ĐẦU KẾT NỐI", style="Primary.TButton", command=self.start)
        self.btn_start.pack(fill="x")
        self.btn_stop = ttk.Button(btn_box, text="■  DỪNG HỆ THỐNG", style="Danger.TButton", command=self.stop, state="disabled")
        self.btn_stop.pack(fill="x", pady=(4, 0))

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

        # One shared looping background keeps OBS setup and gift actions predictable.
        idle_box = tk.Frame(panel, bg=CARD_BG, highlightbackground=COLOR_CYAN, highlightthickness=1, padx=10, pady=8)
        idle_box.pack(fill="x", pady=(0, 8))

        idle_header = tk.Frame(idle_box, bg=CARD_BG)
        idle_header.pack(fill="x")
        tk.Label(idle_header, text="🎬 VIDEO NỀN ĐANG CHẠY", font=("Segoe UI", 9, "bold"), fg=COLOR_CYAN, bg=CARD_BG).pack(side="left")
        tk.Label(idle_box, text="Một video duy nhất lặp liên tục trên Idle_Source. Khi có quà, Action_Source sẽ phát hành động rồi tự quay lại nền.", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=CARD_BG, wraplength=300, justify="left").pack(anchor="w", pady=(2, 7))

        idle_row = tk.Frame(idle_box, bg=CARD_BG)
        idle_row.pack(fill="x")
        idle_path = core.get_idle_video_path("main")
        is_ready = core.resolve_existing_media_path(idle_path).is_file()
        status_lbl = tk.Label(idle_row, text="●" if is_ready else "!", width=2, font=("Segoe UI", 8, "bold"), fg=COLOR_EMERALD if is_ready else COLOR_ROSE, bg=CARD_BG)
        status_lbl.pack(side="left")
        self.idle_status_labels["main"] = status_lbl
        tk.Label(idle_row, textvariable=self.idle_video_name_vars["main"], font=("Segoe UI", 8, "bold"), fg=COLOR_EMERALD, bg="#0d131f", padx=6, pady=5, anchor="w").pack(side="left", fill="x", expand=True, padx=(3, 5))
        tk.Button(idle_row, text="Xóa", font=("Segoe UI", 8, "bold"), bg="#334155", fg=COLOR_ROSE, relief="flat", padx=7, pady=3, command=self.clear_idle_video, cursor="hand2").pack(side="right", padx=(0, 3))
        tk.Button(idle_row, text="📂 Chọn", font=("Segoe UI", 8, "bold"), bg=COLOR_CYAN, fg="#083344", relief="flat", padx=7, pady=3, command=self.choose_idle_video, cursor="hand2").pack(side="right")

        tk.Button(idle_box, text="⟳ GỬI VIDEO NỀN SANG OBS", font=("Segoe UI", 8, "bold"), bg="#164e63", fg="#cffafe", activebackground=COLOR_CYAN, activeforeground="#083344", relief="flat", pady=5, command=self.sync_all_videos_to_obs).pack(fill="x", pady=(7, 0))

        # Dedicated OBS Settings & Open Folder Buttons
        btn_obs_cfg = tk.Button(panel, text="⚙ Cài Đặt Kết Nối OBS Studio", font=("Segoe UI", 9, "bold"), bg="#1e293b", fg=COLOR_CYAN, activebackground=COLOR_CYAN, activeforeground="#000", relief="flat", padx=6, pady=5, command=self.open_obs_settings_dialog)
        btn_obs_cfg.pack(fill="x", pady=(4, 4))

        ttk.Button(panel, text="📁 Mở Thư Mục Videos", style="Soft.TButton", command=self.open_video_folder).pack(fill="x")
        return panel

    def _refresh_idle_file_statuses(self) -> None:
        path = core.get_idle_video_path("main")
        label = self.idle_status_labels.get("main")
        if label:
            ready = core.resolve_existing_media_path(path).is_file()
            label.configure(text="●" if ready else "!", fg=COLOR_EMERALD if ready else COLOR_ROSE)

    def _render_idle_character_rows(self) -> None:
        if self.idle_rows_container is None:
            return
        for widget in self.idle_rows_container.winfo_children():
            widget.destroy()
        self.idle_status_labels.clear()
        for idx in range(1, core.CHARACTER_COUNT + 1):
            char = f"char{idx}"
            path = core.get_idle_video_path(idx)
            idle_var = self.idle_video_name_vars.setdefault(
                char,
                tk.StringVar(value=shorten_filename(core.resolve_existing_media_path(path).name, 16)),
            )
            row = tk.Frame(self.idle_rows_container, bg=CARD_BG)
            row.pack(fill="x", pady=1)
            is_ready = core.resolve_existing_media_path(path).is_file()
            status_lbl = tk.Label(row, text="●" if is_ready else "!", width=2, font=("Segoe UI", 8, "bold"), fg=COLOR_EMERALD if is_ready else COLOR_ROSE, bg=CARD_BG)
            status_lbl.pack(side="left")
            self.idle_status_labels[char] = status_lbl
            tk.Label(row, text=f"NV{idx}", width=4, font=("Segoe UI", 8, "bold"), fg=COLOR_CYAN, bg=CARD_BG).pack(side="left")
            tk.Label(row, textvariable=idle_var, font=("Segoe UI", 8, "bold"), fg=COLOR_EMERALD, bg="#0d131f", padx=5, pady=3, anchor="w").pack(side="left", fill="x", expand=True, padx=(3, 5))
            tk.Button(row, text="🗑", font=("Segoe UI", 8, "bold"), bg="#334155", fg=COLOR_ROSE, relief="flat", padx=5, pady=2, command=lambda selected=char: self.clear_idle_video(selected), cursor="hand2").pack(side="right", padx=(0, 3))
            tk.Button(row, text="📂", font=("Segoe UI", 8, "bold"), bg=COLOR_CYAN, fg="#083344", relief="flat", padx=6, pady=2, command=lambda selected=char: self.choose_idle_video(selected), cursor="hand2").pack(side="right")

    def _submit_obs_operation(
        self,
        label: str,
        coroutine: Any,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        status_char: str | None = None,
    ) -> None:
        if not self.run_loop:
            raise RuntimeError("OBS event loop chưa sẵn sàng")
        if status_char and status_char in self.idle_status_labels:
            self.idle_status_labels[status_char].configure(text="…", fg=COLOR_AMBER)
        future = asyncio.run_coroutine_threadsafe(coroutine, self.run_loop)
        self._pending_obs_operations.add(future)

        def _done(done_future: Any) -> None:
            def _finish_on_ui() -> None:
                self._pending_obs_operations.discard(done_future)
                try:
                    result = done_future.result()
                    if status_char and status_char in self.idle_status_labels:
                        self.idle_status_labels[status_char].configure(text="●", fg=COLOR_EMERALD)
                    logging.getLogger(__name__).info("OBS hoàn tất: %s", label)
                    if on_success:
                        on_success(result)
                except Exception as exc:
                    if status_char and status_char in self.idle_status_labels:
                        self.idle_status_labels[status_char].configure(text="!", fg=COLOR_ROSE)
                    logging.getLogger(__name__).error("OBS thất bại [%s]: %s", label, exc)
                    if on_error:
                        on_error(exc)

            with contextlib.suppress(tk.TclError):
                self.root.after(0, _finish_on_ui)

        future.add_done_callback(_done)

    def clear_idle_video(self) -> None:
        core.set_idle_video_path("main", core.VIDEO_DIRECTORY / "__unassigned_idle__.mp4")
        self.idle_video_name_vars["main"].set("(Chưa chọn video nền)")
        self._persist_runtime_config()
        label = self.idle_status_labels.get("main")
        if label:
            label.configure(text="!", fg=COLOR_ROSE)
        if self.app and self.run_loop and self.app.obs.is_connected and not self.app.mock_mode:
            def _keep_cleared_status(_: Any) -> None:
                current_label = self.idle_status_labels.get("main")
                if current_label:
                    current_label.configure(text="!", fg=COLOR_ROSE)

            self._submit_obs_operation(
                "xóa video nền khỏi Idle_Source",
                self.app.obs.clear_idle_video("main"),
                on_success=_keep_cleared_status,
                status_char="main",
            )
        logging.getLogger(__name__).info("Đã bỏ gán video nền chung")

    def sync_all_videos_to_obs(self) -> None:
        if not self.app or not self.run_loop:
            self.status_text.set("HÃY BẤM BẮT ĐẦU KẾT NỐI TRƯỚC")
            logging.getLogger(__name__).warning("Hệ thống chưa chạy; chưa thể gửi video nền sang OBS")
            return
        if self.app.mock_mode:
            self.status_text.set("MOCK MODE KHÔNG GỬI VIDEO SANG OBS THẬT")
            return
        self.idle_status_labels["main"].configure(text="…", fg=COLOR_AMBER)
        self.status_text.set("ĐANG KẾT NỐI VÀ GỬI VIDEO NỀN SANG OBS...")

        async def _connect_and_sync() -> dict[str, list[str]]:
            if not self.app.obs.is_connected:
                await self.app.obs.connect()
            return await self.app.obs.sync_all_idle_videos()

        def _sync_done(result: dict[str, list[str]]) -> None:
            synced = bool(result["synced"])
            self.idle_status_labels["main"].configure(text="●" if synced else "!", fg=COLOR_EMERALD if synced else COLOR_ROSE)
            self.status_text.set("VIDEO NỀN ĐÃ CHẠY TRÊN OBS" if synced else "CHƯA CÓ VIDEO NỀN HỢP LỆ")
            logging.getLogger(__name__).info(
                "Đồng bộ video nền OBS: %s thành công, %s chưa chọn, %s lỗi",
                len(result["synced"]),
                len(result["skipped"]),
                len(result["errors"]),
            )

        def _sync_failed(exc: Exception) -> None:
            self.status_text.set("ĐỒNG BỘ OBS THẤT BẠI")
            self._refresh_idle_file_statuses()
            logging.getLogger(__name__).error("Không thể đồng bộ toàn bộ video sang OBS: %s", exc)

        self._submit_obs_operation(
            "kết nối và đồng bộ video nền chung",
            _connect_and_sync(),
            on_success=_sync_done,
            on_error=_sync_failed,
        )

    def add_character(self) -> None:
        if core.CHARACTER_COUNT >= 12:
            messagebox.showwarning("Giới hạn", "Hỗ trợ tối đa 12 nhân vật.", parent=self.root)
            return
        new_index = core.CHARACTER_COUNT + 1
        core.set_character_count(new_index)
        refresh_character_maps()
        self.idle_video_name_vars[f"char{new_index}"] = tk.StringVar(
            value=shorten_filename(core.get_idle_video_path(new_index).name, 16)
        )
        self._persist_runtime_config()
        self._render_idle_character_rows()
        self._refresh_cards_container()
        self._refresh_stream_deck_grid()
        logging.getLogger(__name__).info("Đã thêm Nhân vật %s", new_index)

    def remove_last_character(self) -> None:
        if core.CHARACTER_COUNT <= 1:
            messagebox.showwarning("Không thể xóa", "Phải giữ lại ít nhất một nhân vật.", parent=self.root)
            return
        remove_index = core.CHARACTER_COUNT
        remove_key = f"char{remove_index}"
        if time.monotonic() > self._remove_character_armed_until:
            self._remove_character_armed_until = time.monotonic() + 3.0
            if self.remove_character_button:
                self.remove_character_button.configure(text=f"Xóa NV{remove_index}?", width=9, bg=COLOR_ROSE, fg="#fff")

                def _reset_remove_button() -> None:
                    if time.monotonic() >= self._remove_character_armed_until and self.remove_character_button:
                        self.remove_character_button.configure(text="−", width=3, bg="#334155", fg=COLOR_ROSE)

                self.root.after(3100, _reset_remove_button)
            logging.getLogger(__name__).warning("Bấm nút xóa lần nữa trong 3 giây để xác nhận xóa NV%s", remove_index)
            return
        self._remove_character_armed_until = 0.0
        if self.remove_character_button:
            self.remove_character_button.configure(text="…", width=3, state="disabled")
        affected = [gift for gift, mapped in core.GIFT_MAPPING.items() if len(mapped) > 3 and mapped[3] == remove_key]

        def _finalize_remove(_: Any = None) -> None:
            for gift in affected:
                mapped = core.GIFT_MAPPING[gift]
                core.GIFT_MAPPING[gift] = (mapped[0], mapped[1], mapped[2] if len(mapped) > 2 else "", "char1")
            if affected:
                core.save_gift_mapping(core.GIFT_MAPPING)
            core.set_character_count(remove_index - 1)
            core.IDLE_VIDEO_PATHS.pop(remove_index, None)
            refresh_character_maps()
            self.idle_video_name_vars.pop(remove_key, None)
            self._persist_runtime_config()
            self._render_idle_character_rows()
            self._refresh_cards_container()
            if self.remove_character_button:
                self.remove_character_button.configure(text="−", width=3, state="normal", bg="#334155", fg=COLOR_ROSE)
            logging.getLogger(__name__).info("Đã xóa Nhân vật %s", remove_index)

        def _remove_failed(_: Exception) -> None:
            if self.remove_character_button:
                self.remove_character_button.configure(text="−", width=3, state="normal", bg="#334155", fg=COLOR_ROSE)

        if self.app and self.run_loop and self.app.obs.is_connected and not self.app.mock_mode:
            self._submit_obs_operation(
                f"xóa source Nhân vật {remove_index}",
                self.app.obs.remove_character_layer(remove_index),
                on_success=_finalize_remove,
                on_error=_remove_failed,
                status_char=remove_key,
            )
        else:
            _finalize_remove()

    def setup_character_layers(self) -> None:
        if not self.app or not self.run_loop or not self.app.obs.is_connected or self.app.mock_mode:
            messagebox.showwarning("Chưa kết nối OBS", "Hãy kết nối OBS thật trước khi tạo source layer.", parent=self.root)
            return
        self._submit_obs_operation(
            "đồng bộ source cho các nhân vật có video",
            self.app.obs.sync_all_idle_videos(),
            on_success=lambda created: logging.getLogger(__name__).info(
                "OBS đã đồng bộ source nhân vật có video: %s",
                len(created["synced"]),
            ),
        )

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

    def choose_idle_video(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Chọn video nền chạy liên tục",
            filetypes=[("Media Files", "*.mp4 *.mov *.mkv *.webm *.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        if filename:
            path = Path(filename)
            core.set_idle_video_path("main", path)
            self.idle_video_name_vars["main"].set(shorten_filename(path.name, 24))
            self._persist_runtime_config()
            self._refresh_idle_file_statuses()
            logging.getLogger(__name__).info("Đã chọn video nền chung: %s", path.name)
            if self.app and self.run_loop and self.app.obs.is_connected:
                self._submit_obs_operation(
                    f"gán {path.name} cho Idle_Source",
                    self.app.obs.set_idle_video(path, "main"),
                    status_char="main",
                )
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

    def prompt_manage_action_presets(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("⚡ QUẢN LÝ KHO HÀNH ĐỘNG (ACTION PRESETS)")
        dlg.geometry("760x600")
        dlg.resizable(True, True)
        dlg.configure(bg="#0f172a")
        dlg.transient(self.root)
        dlg.grab_set()

        top_f = tk.Frame(dlg, bg="#0f172a", padx=16, pady=12)
        top_f.pack(fill="x")
        tk.Label(top_f, text="⚡ QUẢN LÝ KHO HÀNH ĐỘNG (ACTION PRESETS)", font=("Segoe UI", 12, "bold"), fg=COLOR_CYAN, bg="#0f172a").pack(side="left")

        preview_box = tk.Frame(dlg, bg="#0f172a", padx=16)
        preview_box.pack(fill="x", pady=(0, 8))
        tk.Label(preview_box, text="Mỗi hành động được phát trên Action_Source dùng chung và tự quay lại video nền.", font=("Segoe UI", 8), fg=TEXT_MUTED, bg="#0f172a").pack(side="left")

        def _add_new_preset() -> None:
            new_dlg = tk.Toplevel(dlg)
            new_dlg.title("➕ Tạo Hành Động Mới")
            new_dlg.geometry("450x200")
            new_dlg.configure(bg="#0f172a")
            new_dlg.transient(dlg)
            new_dlg.grab_set()

            tk.Label(new_dlg, text="Tên Hành Động Mới (Ví dụ: Nhảy Hot Trend 2026):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").pack(anchor="w", padx=16, pady=(16, 4))
            name_ent = tk.Entry(new_dlg, bg="#182335", fg="#fff", insertbackground="#fff", font=("Segoe UI", 10))
            name_ent.pack(fill="x", padx=16, ipady=4)
            name_ent.focus_set()

            def _save_new() -> None:
                nname = name_ent.get().strip()
                if not nname:
                    messagebox.showwarning("Cảnh báo", "Vui lòng nhập tên Hành Động.", parent=new_dlg)
                    return
                aid = f"action_{len(core.ACTION_PRESETS)+1}_{nname.lower().replace(' ', '_')}"
                core.ACTION_PRESETS[aid] = core.ActionPreset(id=aid, name=nname, videos=[])
                core.save_action_presets(core.ACTION_PRESETS)
                new_dlg.destroy()
                _render_list()

            tk.Button(new_dlg, text="✔ Tạo Ngay", font=("Segoe UI", 9, "bold"), bg=COLOR_EMERALD, fg="#042f2e", relief="flat", padx=10, pady=4, command=_save_new).pack(side="right", padx=16, pady=20)

        tk.Button(top_f, text="➕ Tạo Hành Động Mới", font=("Segoe UI", 9, "bold"), bg=COLOR_EMERALD, fg="#042f2e", relief="flat", padx=8, pady=3, command=_add_new_preset).pack(side="right")

        list_frame = tk.Frame(dlg, bg="#0d131f", padx=12, pady=10)
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        def _render_list() -> None:
            for w in list_frame.winfo_children():
                w.destroy()

            for aid, preset in core.ACTION_PRESETS.items():
                card = tk.Frame(list_frame, bg="#182335", highlightbackground="#334155", highlightthickness=1, padx=10, pady=8)
                card.pack(fill="x", pady=4)

                left = tk.Frame(card, bg="#182335")
                left.pack(side="left", fill="x", expand=True)

                tk.Label(left, text=preset.name, font=("Segoe UI", 10, "bold"), fg=COLOR_CYAN, bg="#182335", anchor="w").pack(anchor="w")
                media_row = tk.Frame(left, bg="#182335")
                media_row.pack(fill="x", pady=(4, 0))
                if preset.videos:
                    for video in preset.videos[:3]:
                        tk.Label(media_row, text=f"▶ {shorten_filename(Path(video).name, 14)}", font=("Cascadia Mono", 7, "bold"), fg="#cffafe", bg="#164e63", padx=5, pady=2).pack(side="left", padx=(0, 4))
                    if len(preset.videos) > 3:
                        tk.Label(media_row, text=f"+{len(preset.videos) - 3}", font=("Segoe UI", 7, "bold"), fg=TEXT_MAIN, bg="#334155", padx=5, pady=2).pack(side="left")
                else:
                    tk.Label(media_row, text="Chưa có video", font=("Segoe UI", 8, "italic"), fg=COLOR_ROSE, bg="#182335").pack(side="left")
                sound_text = Path(preset.sound_filename).name if preset.sound_filename else "Không có âm thanh riêng"
                tk.Label(left, text=f"🔊 {sound_text}", font=("Segoe UI", 8), fg=COLOR_AMBER if preset.sound_filename else TEXT_MUTED, bg="#182335", anchor="w").pack(anchor="w", pady=(4, 0))

                right = tk.Frame(card, bg="#182335")
                right.pack(side="right")

                def _choose_vids(target_aid=aid) -> None:
                    fns = filedialog.askopenfilenames(
                        parent=dlg,
                        title=f"Chọn video cho {core.ACTION_PRESETS[target_aid].name} (Giữ Ctrl để chọn nhiều file)",
                        filetypes=[("Media Files", "*.mp4 *.mov *.mkv *.webm *.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
                    )
                    if fns:
                        mapped_vals = []
                        for filename in fns:
                            mapped_vals.append(get_media_mapping_value(filename))
                        core.ACTION_PRESETS[target_aid].videos = mapped_vals
                        core.save_action_presets(core.ACTION_PRESETS)
                        _render_list()

                def _choose_sound(target_aid=aid) -> None:
                    filename = filedialog.askopenfilename(
                        parent=dlg,
                        title=f"Chọn âm thanh cho {core.ACTION_PRESETS[target_aid].name}",
                        filetypes=[("Audio Files", "*.mp3 *.wav *.aac *.m4a *.ogg *.flac *.wma"), ("All files", "*.*")],
                    )
                    if filename:
                        core.ACTION_PRESETS[target_aid].sound_filename = get_media_mapping_value(filename)
                        core.save_action_presets(core.ACTION_PRESETS)
                        _render_list()

                def _preview(target_aid=aid) -> None:
                    if not self.app or not self.run_loop:
                        messagebox.showwarning("Chưa chạy hệ thống", "Hãy bấm Bắt đầu trước khi xem thử hành động.", parent=dlg)
                        return
                    future = asyncio.run_coroutine_threadsafe(
                        self.app.enqueue_action_preset(target_aid, "main"),
                        self.run_loop,
                    )

                    def _preview_done(done_future: Any) -> None:
                        try:
                            if not done_future.result():
                                self.root.after(0, lambda: messagebox.showwarning("Không thể xem thử", "Hành động chưa có video hợp lệ.", parent=dlg))
                        except Exception as exc:
                            logging.getLogger(__name__).error("Lỗi xem thử hành động: %s", exc)

                    future.add_done_callback(_preview_done)

                def _del_preset(target_aid=aid) -> None:
                    if len(core.ACTION_PRESETS) <= 1:
                        messagebox.showwarning("Cảnh báo", "Không thể xóa Hành động cuối cùng.", parent=dlg)
                        return
                    if messagebox.askyesno("Xóa Hành Động", f"Bạn có chắc muốn xóa {core.ACTION_PRESETS[target_aid].name}?", parent=dlg):
                        del core.ACTION_PRESETS[target_aid]
                        core.save_action_presets(core.ACTION_PRESETS)
                        _render_list()

                tk.Button(right, text="▶ Xem thử", font=("Segoe UI", 8, "bold"), bg=COLOR_EMERALD, fg="#042f2e", relief="flat", padx=6, pady=2, command=_preview).pack(anchor="e", pady=1)
                tk.Button(right, text="📂 Video", font=("Segoe UI", 8, "bold"), bg=COLOR_AMBER, fg="#000", relief="flat", padx=6, pady=2, command=_choose_vids).pack(anchor="e", pady=1)
                tk.Button(right, text="🔊 Âm thanh", font=("Segoe UI", 8, "bold"), bg="#1e293b", fg=COLOR_AMBER, relief="flat", padx=6, pady=2, command=_choose_sound).pack(anchor="e", pady=1)
                tk.Button(right, text="🗑 Xóa", font=("Segoe UI", 8, "bold"), bg="#334155", fg=COLOR_ROSE, relief="flat", padx=6, pady=2, command=_del_preset).pack(anchor="e", pady=1)

        _render_list()

        def _close_and_refresh() -> None:
            self._refresh_cards_container()
            self._refresh_stream_deck_grid()
            dlg.destroy()

        tk.Button(dlg, text="✔ ĐÃ XONG / ĐÓNG", font=("Segoe UI", 10, "bold"), bg=COLOR_EMERALD, fg="#042f2e", relief="flat", padx=12, pady=6, command=_close_and_refresh).pack(side="right", padx=16, pady=10)

    def prompt_add_new_gift(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("➕ Thêm Món Quà Mới")
        dlg.geometry("460x350")
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
        tk.Label(prio_frame, text="Mức quà (chỉ để phân loại):", font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0f172a").pack(side="left")
        prio_var = tk.StringVar(value="1")
        spn_prio = tk.Spinbox(prio_frame, from_=1, to=10, textvariable=prio_var, width=4, bg="#182335", fg="#fff", buttonbackground="#1e293b", relief="flat")
        spn_prio.pack(side="left", padx=8)

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
            mapped_val = get_media_mapping_value(fn)

            s_fn = sound_path_var.get().strip()
            sound_mapped_val = ""
            if s_fn:
                sound_mapped_val = get_media_mapping_value(s_fn)

            core.GIFT_MAPPING[key] = (mapped_val, prio, sound_mapped_val, "main")
            core.save_gift_mapping(core.GIFT_MAPPING)

            self._refresh_cards_container()
            self._refresh_stream_deck_grid()
            logging.getLogger(__name__).info("➕ Đã thêm món quà mới: '%s' -> %s (Mức %s, Sound: %s)", key.title(), path.name, prio, sound_mapped_val or "Không")
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
            ("🌹", "Rose", COLOR_ROSE, "rose"),
            ("🍩", "Doughnut", COLOR_AMBER, "doughnut"),
            ("♪", "TikTok", COLOR_CYAN, "tiktok"),
            ("🦁", "Lion", COLOR_PURPLE, "lion"),
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
                sound_icon = " 🔊" if sound_fn else ""
                vids, sound_fn, action_name = core.resolve_gift_action_media(fn, sound_fn)
                if len(vids) > 1:
                    first_n = Path(vids[0]).name
                    fn_display = f"{shorten_filename(first_n, 8)} (+{len(vids)-1} rnd)"
                elif len(vids) == 1 and vids[0]:
                    fn_display = shorten_filename(Path(vids[0]).name, 12)
                else:
                    fn_display = shorten_filename(action_name, 12)
                sub = f"Mức {prio} · {fn_display}{sound_icon}"
            else:
                sub = "Priority: --"

            btn = StreamDeckButton(self.deck_grid, emoji, title, sub, color, command=lambda g=gift_key: self.test_gift(g))
            btn.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 4, 4 if col < 3 else 0))
            self.deck_grid.columnconfigure(col, weight=1)
            self.deck_buttons[gift_key] = btn

    def update_card_mapping(self, gift_key: str, filename: str, priority: int, sound_filename: str = "", target_char: str = "main") -> None:
        core.GIFT_MAPPING[gift_key] = (filename, priority, sound_filename, "main")
        core.save_gift_mapping(core.GIFT_MAPPING)
        vids, sound_filename, action_name = core.resolve_gift_action_media(filename, sound_filename)
        if len(vids) > 1:
            first_n = Path(vids[0]).name
            fn_display = f"{shorten_filename(first_n, 8)} (+{len(vids)-1} rnd)"
        elif len(vids) == 1 and vids[0]:
            fn_display = shorten_filename(Path(vids[0]).name, 12)
        else:
            fn_display = shorten_filename(action_name, 12)
        sound_icon = " 🔊" if sound_filename else ""
        if gift_key in self.deck_buttons:
            self.deck_buttons[gift_key].set_subtitle(f"Mức {priority} · {fn_display}{sound_icon}")
        logging.getLogger(__name__).info("Đã cập nhật quà %s: %s (Mức %s, Sound: %s)", gift_key.title(), fn_display, priority, sound_filename or "Không")

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
