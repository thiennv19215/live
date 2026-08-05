"""OBS settings and character-layer operations for the desktop dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
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


class ObsSettingsMixin:
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

        overlay_box = tk.Frame(panel, bg="#0b1f1d", highlightbackground=COLOR_EMERALD, highlightthickness=1, padx=8, pady=6)
        overlay_box.pack(fill="x", pady=(0, 5))
        overlay_header = tk.Frame(overlay_box, bg="#0b1f1d")
        overlay_header.pack(fill="x")
        tk.Label(overlay_header, text="📡 BROWSER OVERLAY", font=("Segoe UI", 9, "bold"), fg=COLOR_EMERALD, bg="#0b1f1d").pack(side="left")
        tk.Label(overlay_header, textvariable=self.overlay_status, font=("Segoe UI", 7, "bold"), fg="#a7f3d0", bg="#0b1f1d").pack(side="right")
        tk.Label(overlay_box, textvariable=self.overlay_url, font=("Cascadia Mono", 8), fg=COLOR_CYAN, bg="#071613", anchor="w", padx=5, pady=3).pack(fill="x", pady=(3, 0))
        overlay_buttons = tk.Frame(overlay_box, bg="#0b1f1d")
        overlay_buttons.pack(fill="x", pady=(4, 0))
        tk.Button(overlay_buttons, text="COPY URL", font=("Segoe UI", 8, "bold"), bg=COLOR_EMERALD, fg="#042f2e", relief="flat", padx=8, pady=3, command=self.copy_overlay_url, cursor="hand2").pack(side="left", fill="x", expand=True, padx=(0, 3))
        tk.Button(overlay_buttons, text="MỞ PREVIEW", font=("Segoe UI", 8, "bold"), bg="#164e63", fg="#cffafe", relief="flat", padx=8, pady=3, command=self.open_overlay_preview, cursor="hand2").pack(side="left", fill="x", expand=True, padx=(3, 0))

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
        self.overlay.set_idle_path(None)
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
            self.overlay.set_idle_path(core.resolve_existing_media_path(path))
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
