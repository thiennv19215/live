"""Reusable Tkinter widgets and display helpers for the TikTok OBS dashboard."""

from __future__ import annotations

import contextlib
import logging
import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

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
