"""Gift mapping and action-preset management for the desktop dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

import tiktok_obs_controller as core

from tiktok_obs_gui_widgets import (
    BG_DARK,
    CARD_BG,
    CARD_HOVER,
    CHAR_DISPLAY_MAP,
    CHAR_SHORT_TAGS,
    CHAR_VALUE_MAP,
    COLOR_AMBER,
    COLOR_BLUE,
    COLOR_CYAN,
    COLOR_EMERALD,
    COLOR_PURPLE,
    COLOR_ROSE,
    PANEL_BG,
    PANEL_BORDER,
    TEXT_DARK,
    TEXT_MAIN,
    TEXT_MUTED,
    GiftMappingCard,
    StreamDeckButton,
    get_char_display_name,
    get_char_value_from_display,
    get_media_mapping_value,
    refresh_character_maps,
    shorten_filename,
)


class GiftMappingMixin:
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
