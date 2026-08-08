"""Headless HTTP backend used by the React/Electron control room."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import re
import threading
import time
from collections import deque
from functools import wraps
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import tiktok_obs_controller as core
from tiktok_overlay import LocalOverlayServer


def catalog_locked(method: Callable[..., Any]) -> Callable[..., Any]:
    """Serialize catalog readers and writers served by ThreadingHTTPServer."""

    @wraps(method)
    def guarded(self: "BackendRuntime", *args: Any, **kwargs: Any) -> Any:
        lock = getattr(self, "_catalog_lock", None)
        if lock is None:
            lock = self._catalog_lock = threading.RLock()
        with lock:
            return method(self, *args, **kwargs)

    return guarded


class RecentLogHandler(logging.Handler):
    def __init__(self, limit: int = 300) -> None:
        super().__init__()
        self.records: deque[dict[str, Any]] = deque(maxlen=limit)
        self._counter = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock:
            self._counter += 1
            self.records.append(
                {
                    "id": self._counter,
                    "level": record.levelname.lower(),
                    "message": self.format(record),
                }
            )

    def snapshot(self, after: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return [item.copy() for item in self.records if item["id"] > after]


class BackendRuntime:
    def __init__(self) -> None:
        self._catalog_lock = threading.RLock()
        idle_path = core.resolve_existing_media_path(core.get_idle_video_path("main"))
        self.overlay = LocalOverlayServer(idle_path)
        initial_config = core.load_obs_config()
        self.overlay.set_idle_video_muted(bool(initial_config.get("idle_video_muted", False)))
        background_music = core.resolve_existing_media_path(Path(str(initial_config.get("background_music_path", ""))))
        self.overlay.set_background_music(
            background_music if background_music.is_file() else None,
            muted=bool(initial_config.get("background_music_muted", False)),
        )
        self.overlay_error = ""
        try:
            self.overlay.start()
        except OSError as exc:
            self.overlay_error = str(exc)

        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_loop, name="backend-asyncio", daemon=True)
        self.loop_thread.start()
        self.app: core.TikTokObsApp | None = None
        self.app_task: asyncio.Task[None] | None = None
        self._gift_catalog: list[dict[str, Any]] = []
        self._gift_catalog_updated_at = 0.0
        self.started_at = 0.0
        self.log_handler = RecentLogHandler()
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(self.log_handler)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    @staticmethod
    def _serialize_job(job: core.GiftJob) -> dict[str, Any]:
        return {
            "id": job.history_id,
            "gift": job.gift_name,
            "event_type": getattr(job, "event_type", "gift"),
            "event_value": getattr(job, "event_value", ""),
            "file": job.file_path.name,
            "priority": job.priority,
            "sound": job.sound_path.name if job.sound_path else "",
            "sender": job.sender,
            "count": job.repeat_count,
            "diamonds": job.diamonds,
            "timestamp": job.timestamp,
        }

    def config(self) -> dict[str, Any]:
        config = core.load_obs_config()
        config.setdefault("gift_guide_enabled", False)
        config.setdefault("gift_guide_title", "Gifts")
        config.setdefault("gift_guide_message", "")
        config.setdefault("gift_panel_position", {"x": 4, "y": 20})
        config.setdefault("background_music_muted", False)
        config.setdefault("idle_video_muted", False)
        configured_music = core.resolve_existing_media_path(Path(str(config.get("background_music_path", ""))))
        config["background_music_path"] = str(configured_music) if configured_music.is_file() else ""
        idle_path = core.get_idle_video_path("main")
        config["idle_video_path"] = str(idle_path) if core.resolve_existing_media_path(idle_path).is_file() else ""
        return config

    def update_config(self, values: dict[str, Any]) -> dict[str, Any]:
        stored_background_music = core.load_obs_config().get("background_music_path", "")
        config = self.config()
        allowed = {
            "tiktok_username",
            "obs_host",
            "obs_port",
            "obs_password",
            "scene_name",
            "idle_source_name",
            "action_source_name",
            "output_ratio",
            "mock_mode",
            "enable_tiktok",
            "enable_obs",
            "gift_guide_enabled",
            "gift_guide_title",
            "gift_guide_message",
            "gift_panel_position",
            "background_music_muted",
            "idle_video_muted",
        }
        for key in allowed:
            if key in values:
                config[key] = values[key]
        config["obs_port"] = int(config.get("obs_port", 4455))
        config["gift_guide_enabled"] = bool(config.get("gift_guide_enabled", False))
        config["gift_guide_title"] = str(config.get("gift_guide_title", ""))[:80].strip() or "Gifts"
        config["gift_guide_message"] = str(config.get("gift_guide_message", ""))[:160].strip()
        config["background_music_muted"] = bool(config.get("background_music_muted", False))
        config["idle_video_muted"] = bool(config.get("idle_video_muted", False))
        position = config.get("gift_panel_position", {})
        if not isinstance(position, dict):
            position = {}
        try:
            x = float(position.get("x", 4))
            y = float(position.get("y", 20))
        except (TypeError, ValueError):
            x, y = 4, 20
        config["gift_panel_position"] = {"x": max(0, min(95, round(x, 2))), "y": max(0, min(92, round(y, 2)))}
        config.pop("idle_video_path", None)
        config.pop("background_music_path", None)
        if stored_background_music:
            config["background_music_path"] = stored_background_music
        core.save_obs_config(config)
        core.TIKTOK_USERNAME = str(config["tiktok_username"]).strip().lstrip("@") or "mock_user"
        core.OBS_HOST = str(config["obs_host"]).strip()
        core.OBS_PORT = int(config["obs_port"])
        core.OBS_PASSWORD = str(config["obs_password"])
        core.SCENE_NAME = str(config["scene_name"]).strip()
        core.IDLE_SOURCE_NAME = str(config["idle_source_name"]).strip()
        core.ACTION_SOURCE_NAME = str(config["action_source_name"]).strip()
        core.OUTPUT_RATIO = str(config.get("output_ratio", "9:16"))
        core.IDLE_VIDEO_MUTED = bool(config.get("idle_video_muted", False))
        stored_config = core.load_obs_config()
        music_path = core.resolve_existing_media_path(Path(str(stored_config.get("background_music_path", ""))))
        if hasattr(self, "overlay"):
            self.overlay.set_idle_video_muted(core.IDLE_VIDEO_MUTED)
            self.overlay.set_background_music(
                music_path if music_path.is_file() else None,
                muted=bool(stored_config.get("background_music_muted", False)),
            )
        if self.app and self.app.enable_obs and self.app.obs.is_connected:
            try:
                self.submit(self.app.obs.set_idle_video_muted(core.IDLE_VIDEO_MUTED))
            except Exception:
                logging.getLogger(__name__).warning("Không thể cập nhật tắt tiếng video nền trên OBS", exc_info=True)
        if self.app and hasattr(self.app, "client"):
            self.app.client._unique_id = core.TIKTOK_USERNAME
        return self.config()

    @catalog_locked
    def mappings(self) -> list[dict[str, Any]]:
        result = []
        for trigger_key, value in core.GIFT_MAPPING.items():
            event_type, condition = core.parse_trigger_key(trigger_key)
            videos, sound, action_name = core.resolve_gift_action_media(str(value[0]), str(value[2]))
            available_videos = [
                video for video in videos
                if video and core.resolve_existing_media_path(Path(video)).is_file()
            ]
            missing_videos = [video for video in videos if video and video not in available_videos]
            action_id = str(value[0]) if str(value[0]) in core.ACTION_PRESETS else ""
            enabled = core.mapping_enabled(value)
            if not enabled:
                readiness = "Đã tắt"
            elif not str(value[0]).strip():
                readiness = "Chưa chọn hành động"
            elif not videos or not any(str(video).strip() for video in videos):
                readiness = "Hành động chưa có video"
            elif not available_videos:
                readiness = "Không tìm thấy file video"
            elif missing_videos:
                readiness = f"Sẵn sàng {len(available_videos)}/{len(videos)} video"
            else:
                readiness = f"Sẵn sàng {len(available_videos)} video"
            result.append(
                {
                    "gift": trigger_key,
                    "trigger_key": trigger_key,
                    "event_type": event_type,
                    "condition": condition,
                    "event_label": core.trigger_event_label(event_type, condition),
                    "action": str(value[0]),
                    "action_id": action_id,
                    "priority": int(value[1]),
                    "sound": str(value[2]),
                    "action_name": action_name,
                    "videos": videos,
                    "resolved_sound": sound,
                    "active": bool(enabled and available_videos),
                    "enabled": enabled,
                    "cooldown_seconds": core.mapping_cooldown(value),
                    "available_video_count": len(available_videos),
                    "missing_videos": missing_videos,
                    "readiness": readiness,
                }
            )
        return result

    @staticmethod
    def _gift_catalog_items(payload: Any) -> list[dict[str, Any]]:
        """Normalise TikTok's gift-list response for the renderer."""
        candidates = payload.get("gifts", []) if isinstance(payload, dict) else []
        if not isinstance(candidates, list):
            candidates = []
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for gift in candidates:
            if not isinstance(gift, dict):
                continue
            name = str(gift.get("name") or gift.get("gift_name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            image = gift.get("image") or gift.get("icon") or {}
            urls = image.get("url_list", []) if isinstance(image, dict) else []
            image_url = next((str(url) for url in urls if url), "") if isinstance(urls, list) else ""
            seen.add(key)
            items.append({
                "id": str(gift.get("id") or gift.get("gift_id") or key),
                "name": name,
                "key": key,
                "diamonds": int(gift.get("diamond_count") or 0),
                "image_url": image_url,
            })
        return sorted(items, key=lambda item: (item["diamonds"], item["name"].lower()))

    async def _refresh_gift_catalog(self) -> list[dict[str, Any]]:
        if not self.app or not self.app.is_tiktok_connected:
            raise RuntimeError("Hãy kết nối TikTok trực tiếp trước khi tải danh sách quà")
        payload = await self.app.client._web.fetch_gift_list()
        items = self._gift_catalog_items(payload)
        if not items:
            raise RuntimeError("TikTok không trả về danh sách quà cho room hiện tại")
        self._gift_catalog = items
        self._gift_catalog_updated_at = time.time()
        return items

    def gift_catalog(self) -> dict[str, Any]:
        return {"items": self._gift_catalog, "updated_at": self._gift_catalog_updated_at}

    def refresh_gift_catalog(self) -> dict[str, Any]:
        future = asyncio.run_coroutine_threadsafe(self._refresh_gift_catalog(), self.loop)
        return {"items": future.result(timeout=20), "updated_at": self._gift_catalog_updated_at}

    @catalog_locked
    def actions(self) -> list[dict[str, Any]]:
        result = []
        for preset in core.ACTION_PRESETS.values():
            available_videos = [
                video for video in preset.videos
                if video and core.resolve_existing_media_path(Path(video)).is_file()
            ]
            result.append({
                "id": preset.id,
                "name": preset.name,
                "videos": list(preset.videos),
                "sound": preset.sound_filename,
                "active": bool(available_videos),
                "available_video_count": len(available_videos),
            })
        return result

    @staticmethod
    def _action_id(value: str, fallback: str = "action") -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
        return normalized or fallback

    @catalog_locked
    def save_actions(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        presets: dict[str, core.ActionPreset] = {}
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            action_id = self._action_id(str(item.get("id", "")), f"action_{index}")
            if action_id in presets:
                raise ValueError(f"Trung ma hanh dong: {action_id}")
            videos = [value for value in core.parse_video_filenames(item.get("videos", [])) if value]
            presets[action_id] = core.ActionPreset(
                id=action_id,
                name=str(item.get("name", "")).strip() or action_id,
                videos=videos,
                sound_filename=str(item.get("sound", "")).strip(),
            )
        core.ACTION_PRESETS.clear()
        core.ACTION_PRESETS.update(presets)
        core.save_action_presets(presets)
        return self.actions()

    @catalog_locked
    def save_mappings(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mapping: dict[str, tuple[str, int, str, str]] = {}
        migrated_presets = False
        for item in items:
            event_type = str(item.get("event_type", "gift")).strip().lower()
            condition = str(item.get("condition", item.get("gift", ""))).strip()
            trigger_key = core.make_trigger_key(event_type, condition)
            action = str(item.get("action_id") or item.get("action", "")).strip()
            if not action:
                continue
            if trigger_key in mapping:
                raise ValueError(f"Trùng luật sự kiện: {core.trigger_event_label(event_type, condition)}")
            if action not in core.ACTION_PRESETS:
                # Convert a legacy direct-media assignment into a reusable
                # action preset the next time the mapping is saved.
                videos = [value for value in core.parse_video_filenames(item.get("videos") or action) if value]
                action_id = self._action_id(
                    f"gift_{condition}" if event_type == "gift" else f"trigger_{event_type}_{condition}"
                )
                suffix = 2
                base_id = action_id
                while action_id in core.ACTION_PRESETS:
                    existing = core.ACTION_PRESETS[action_id]
                    if existing.videos == videos:
                        break
                    action_id = f"{base_id}_{suffix}"
                    suffix += 1
                core.ACTION_PRESETS[action_id] = core.ActionPreset(
                    id=action_id,
                    name=str(item.get("action_name", "")).strip() or core.trigger_event_label(event_type, condition),
                    videos=videos,
                    sound_filename=str(item.get("sound", "")).strip(),
                )
                action = action_id
                migrated_presets = True
            cooldown = max(0.0, min(3600.0, float(item.get("cooldown_seconds", 0) or 0)))
            enabled = bool(item.get("enabled", True))
            mapping[trigger_key] = (
                action,
                int(item.get("priority", 1)),
                str(item.get("sound", "")).strip(),
                "main",
                cooldown,
                enabled,
            )
        if migrated_presets:
            core.save_action_presets(core.ACTION_PRESETS)
        core.GIFT_MAPPING.clear()
        core.GIFT_MAPPING.update(mapping)
        core.save_gift_mapping(mapping)
        return self.mappings()

    @staticmethod
    def _restore_catalog_file(path: Path, contents: bytes | None) -> None:
        if contents is None:
            path.unlink(missing_ok=True)
            return
        temporary = path.with_name(f".{path.name}.rollback")
        temporary.write_bytes(contents)
        temporary.replace(path)

    def save_catalog(
        self,
        action_items: list[dict[str, Any]],
        mapping_items: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Save actions and gift mappings as one logical operation."""
        lock = getattr(self, "_catalog_lock", None)
        if lock is None:
            lock = self._catalog_lock = threading.RLock()

        with lock:
            previous_actions = core.ACTION_PRESETS.copy()
            previous_mappings = core.GIFT_MAPPING.copy()
            action_file = core.ACTION_PRESETS_FILE
            mapping_file = core.CONFIG_FILE
            previous_action_file = action_file.read_bytes() if action_file.is_file() else None
            previous_mapping_file = mapping_file.read_bytes() if mapping_file.is_file() else None
            try:
                actions = self.save_actions(action_items)
                mappings = self.save_mappings(mapping_items)
            except Exception:
                core.ACTION_PRESETS.clear()
                core.ACTION_PRESETS.update(previous_actions)
                core.GIFT_MAPPING.clear()
                core.GIFT_MAPPING.update(previous_mappings)
                try:
                    self._restore_catalog_file(action_file, previous_action_file)
                    self._restore_catalog_file(mapping_file, previous_mapping_file)
                except Exception:
                    logging.getLogger(__name__).exception("Khong the rollback kho hanh dong")
                raise
            return {"actions": actions, "mappings": mappings}

    def validate_configuration(self) -> dict[str, Any]:
        """Return user-facing configuration problems without starting a live session."""
        mappings = self.mappings()
        issues = [
            {
                "trigger_key": item["trigger_key"],
                "label": item["event_label"],
                "reason": item["readiness"],
                "missing_videos": item["missing_videos"],
            }
            for item in mappings
            if not item["active"]
        ]
        active_count = sum(1 for item in mappings if item["active"])
        warnings: list[str] = []
        if not mappings:
            warnings.append("Chưa có luật tương tác nào")
        if mappings and not active_count:
            warnings.append("Không có luật nào sẵn sàng để nhận sự kiện")
        if not self.config().get("idle_video_path"):
            warnings.append("Chưa có video nền hợp lệ")
        return {
            "valid": not issues and bool(mappings),
            "active_count": active_count,
            "inactive_count": len(issues),
            "issues": issues,
            "warnings": warnings,
        }

    async def _start_app(self, mock_mode: bool, enable_tiktok: bool, enable_obs: bool) -> None:
        if self.app_task and not self.app_task.done():
            return
        self.app = core.TikTokObsApp(
            mock_mode=mock_mode,
            enable_tiktok=enable_tiktok,
            enable_obs=enable_obs,
            overlay=self.overlay,
        )
        self.started_at = time.monotonic()
        self.app_task = asyncio.create_task(self.app.run())

    async def _stop_app(self) -> None:
        task = self.app_task
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self.app_task is task:
            self.app_task = None
            self.app = None

    def start_system(self, payload: dict[str, Any]) -> None:
        if isinstance(payload.get("config"), dict):
            self.update_config(payload["config"])
        future = asyncio.run_coroutine_threadsafe(
            self._start_app(
                bool(payload.get("mock_mode")),
                bool(payload.get("enable_tiktok")),
                bool(payload.get("enable_obs", False)),
            ),
            self.loop,
        )
        future.result(timeout=5)

    def stop_system(self) -> None:
        self.submit(self._stop_app())

    def submit(self, coroutine: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=5)

    def enqueue_gift(
        self,
        gift: str,
        sender: str = "Người xem",
        repeat_count: int = 1,
        diamonds: int = 0,
        video_index: int | None = None,
    ) -> None:
        if not self.app:
            raise RuntimeError("Hệ thống chưa chạy")
        self.submit(self.app.enqueue_gift(gift, sender=sender, repeat_count=repeat_count, diamonds=diamonds, video_index=video_index))

    def enqueue_gifts(self, gift: str, count: int, sender: str = "Người xem", diamonds: int = 0) -> int:
        if not self.app:
            raise RuntimeError("Hệ thống chưa chạy")

        async def enqueue_batch() -> int:
            per_diamond = diamonds // max(1, count)
            for _ in range(count):
                await self.app.enqueue_gift(gift, sender=sender, repeat_count=1, diamonds=per_diamond)
            return count

        return int(self.submit(enqueue_batch()))

    def enqueue_trigger(self, trigger_key: str, sender: str = "Người xem thử") -> bool:
        if not self.app:
            raise RuntimeError("Hệ thống chưa chạy")
        return bool(self.submit(self.app.enqueue_trigger(trigger_key, sender=sender)))

    def preview_media(self, path_value: str, action_id: str = "") -> dict[str, str]:
        if not self.app:
            raise RuntimeError("Hệ thống chưa chạy")
        app = self.app
        path = core.resolve_existing_media_path(Path(path_value).expanduser().resolve())
        if not path.is_file():
            raise FileNotFoundError(path)

        preset = core.ACTION_PRESETS.get(str(action_id).strip())
        sound_path: Path | None = None
        label = path.name
        if preset:
            label = preset.name or label
            if preset.sound_filename:
                candidate = Path(preset.sound_filename)
                if not candidate.is_absolute():
                    candidate = core.VIDEO_DIRECTORY / candidate
                resolved_sound = core.resolve_existing_sound_path(candidate)
                if resolved_sound.is_file():
                    sound_path = resolved_sound

        async def enqueue() -> None:
            await app.queue.put(core.GiftJob(
                gift_name=label,
                file_path=path,
                priority=1,
                sound_path=sound_path,
                target_char="main",
                sender="Phát thử video",
                event_type="manual",
                event_value=path.name,
            ))
            await app.update_queue_display()

        self.submit(enqueue())
        return {"path": str(path), "action_id": str(action_id).strip()}

    def clear_queue(self) -> int:
        return int(self.submit(self.app.clear_all_playback())) if self.app else 0

    def clear_gift_history(self) -> int:
        if not self.app:
            return 0
        count = len(self.app.gift_history)
        self.app.gift_history.clear()
        return count

    def set_idle_video(self, path_value: str) -> str:
        path = Path(path_value).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        core.set_idle_video_path("main", path)
        self.overlay.set_idle_path(core.resolve_existing_media_path(path))
        config = self.config()
        config.pop("idle_video_path", None)
        stored_path = core.media_reference(path)
        config["idle_video_paths"] = {"1": stored_path}
        config["idle_video_path_1"] = stored_path
        core.save_obs_config(config)
        if self.app and self.app.enable_obs and self.app.obs.is_connected:
            self.submit(self.app.obs.set_idle_video(path, "main"))
        return str(path)

    def clear_idle_video(self) -> str:
        """Remove the configured idle media and blank every live output."""
        unassigned_path = core.VIDEO_DIRECTORY / "__unassigned_idle_1__.mp4"
        core.set_idle_video_path("main", unassigned_path)
        self.overlay.set_idle_path(None)

        config = core.load_obs_config()
        config.pop("idle_video_path", None)
        config.pop("idle_video_path_1", None)
        config["idle_video_paths"] = {}
        core.save_obs_config(config)

        if self.app and self.app.enable_obs and self.app.obs.is_connected:
            self.submit(self.app.obs.clear_idle_video("main"))
        return ""

    def set_background_music(self, path_value: str) -> dict[str, Any]:
        path = Path(path_value).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
            raise ValueError("File nhạc nền không được hỗ trợ")
        config = core.load_obs_config()
        config["background_music_path"] = core.media_reference(path)
        config.setdefault("background_music_muted", False)
        core.save_obs_config(config)
        self.overlay.set_background_music(path, muted=bool(config["background_music_muted"]))
        return self.config()

    def status(self) -> dict[str, Any]:
        app = self.app
        configured_mappings = self.mappings()
        active_triggers = [
            {
                "trigger_key": item["trigger_key"],
                "event_type": item["event_type"],
                "condition": item["condition"],
                "event_label": item["event_label"],
                "action_name": item["action_name"],
                "priority": item["priority"],
                "video_count": item["available_video_count"],
            }
            for item in configured_mappings
            if item["active"]
        ]
        active_gifts = [
            {**item, "gift": item["condition"]}
            for item in active_triggers
            if item["event_type"] == "gift"
        ]
        running = bool(self.app_task and not self.app_task.done())
        queue_items = app.queue.get_items() if app else []
        current = self._serialize_job(app.current_job) if app and app.current_job else None
        progress = 0.0
        remaining = 0.0
        if app and app.current_job and app.current_job_duration > 0:
            elapsed = max(0.0, self.loop.time() - app.current_job_start_time)
            progress = min(1.0, elapsed / app.current_job_duration)
            remaining = max(0.0, app.current_job_duration - elapsed)
        gift_history: list[dict[str, Any]] = []
        if app:
            try:
                gift_history = list(app.gift_history)
            except RuntimeError:
                gift_history = []
        return {
            "running": running,
            "mock_mode": bool(app and app.mock_mode),
            "tiktok_connected": bool(app and app.is_tiktok_connected),
            "obs_connected": bool(app and app.obs.is_connected),
            "obs_enabled": bool(app and app.enable_obs),
            "overlay_online": self.overlay.is_running,
            "overlay_url": self.overlay.url if self.overlay.is_running else "",
            "overlay_error": self.overlay_error,
            "current": current,
            "queue": [self._serialize_job(item) for item in queue_items],
            "gift_history": gift_history,
            "active_triggers": active_triggers,
            "active_gifts": active_gifts,
            "inactive_trigger_count": len(configured_mappings) - len(active_triggers),
            "inactive_gift_count": len([item for item in configured_mappings if item["event_type"] == "gift" and not item["active"]]),
            "playback_state": "action" if current else "idle",
            "queue_pending": len(queue_items),
            "queue_total": len(queue_items) + (1 if current else 0),
            "progress": progress,
            "remaining": remaining,
            "uptime": max(0.0, time.monotonic() - self.started_at) if running else 0.0,
        }

    def shutdown(self) -> None:
        self.stop_system()
        deadline = time.monotonic() + 3
        while self.app_task and not self.app_task.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.overlay.stop()
        logging.getLogger().removeHandler(self.log_handler)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join(timeout=2)


class BackendApiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], runtime: BackendRuntime) -> None:
        self.runtime = runtime
        super().__init__(address, BackendRequestHandler)


class BackendRequestHandler(BaseHTTPRequestHandler):
    server: BackendApiServer

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _headers(self, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def _json(self, payload: Any, status: int = 200) -> None:
        self._headers(status)
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def do_OPTIONS(self) -> None:
        self._headers(204)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        runtime = self.server.runtime
        try:
            if parsed.path == "/api/status":
                self._json(runtime.status())
            elif parsed.path == "/api/config":
                self._json(runtime.config())
            elif parsed.path == "/api/mappings":
                self._json(runtime.mappings())
            elif parsed.path == "/api/actions":
                self._json(runtime.actions())
            elif parsed.path == "/api/gifts":
                self._json(runtime.gift_catalog())
            elif parsed.path == "/api/validation":
                self._json(runtime.validate_configuration())
            elif parsed.path == "/api/logs":
                after = int(parse_qs(parsed.query).get("after", ["0"])[0])
                self._json(runtime.log_handler.snapshot(after))
            elif parsed.path == "/health":
                self._json({"ok": True})
            else:
                self._json({"error": "Not found"}, 404)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        runtime = self.server.runtime
        try:
            body = self._body()
            if self.path == "/api/system/start":
                runtime.start_system(body)
                result: Any = runtime.status()
            elif self.path == "/api/system/stop":
                runtime.stop_system()
                result = {"ok": True}
            elif self.path == "/api/queue/test":
                sender = str(body.get("sender", "")).strip() or "Người xem thử"
                count = max(1, min(20, int(body.get("count", 1))))
                diamonds = max(0, int(body.get("diamonds", 0)))
                v_idx = body.get("videoIndex")
                video_index = int(v_idx) if v_idx is not None else None
                runtime.enqueue_gift(str(body.get("gift", "")), sender=sender, repeat_count=count, diamonds=diamonds, video_index=video_index)
                result = {"ok": True}
            elif self.path == "/api/queue/test-batch":
                sender = str(body.get("sender", "")).strip() or "Người xem thử"
                count = max(1, min(20, int(body.get("count", 1))))
                diamonds = max(0, int(body.get("diamonds", 0)))
                result = {"enqueued": runtime.enqueue_gifts(str(body.get("gift", "")), count, sender=sender, diamonds=diamonds)}
            elif self.path == "/api/triggers/test":
                sender = str(body.get("sender", "")).strip() or "Người xem thử"
                trigger_key = str(body.get("trigger_key", "")).strip().lower()
                if not trigger_key:
                    raise ValueError("Thiếu trigger_key")
                result = {"enqueued": runtime.enqueue_trigger(trigger_key, sender=sender)}
            elif self.path == "/api/queue/clear":
                result = {"cleared": runtime.clear_queue()}
            elif self.path == "/api/queue/clear-history":
                result = {"cleared": runtime.clear_gift_history()}
            elif self.path == "/api/config":
                result = runtime.update_config(body)
            elif self.path == "/api/mappings":
                items = body.get("items", [])
                if not isinstance(items, list):
                    raise ValueError("items must be a list")
                result = runtime.save_mappings(items)
            elif self.path == "/api/actions":
                items = body.get("items", [])
                if not isinstance(items, list):
                    raise ValueError("items must be a list")
                result = runtime.save_actions(items)
            elif self.path == "/api/catalog":
                actions = body.get("actions", [])
                mappings = body.get("mappings", [])
                if not isinstance(actions, list) or not isinstance(mappings, list):
                    raise ValueError("actions and mappings must be lists")
                result = runtime.save_catalog(actions, mappings)
            elif self.path == "/api/gifts/refresh":
                result = runtime.refresh_gift_catalog()
            elif self.path == "/api/media/idle":
                result = {"path": runtime.set_idle_video(str(body.get("path", "")))}
            elif self.path == "/api/media/idle/clear":
                result = {"path": runtime.clear_idle_video()}
            elif self.path == "/api/media/background":
                result = runtime.set_background_music(str(body.get("path", "")))
            elif self.path == "/api/media/preview":
                result = runtime.preview_media(str(body.get("path", "")), str(body.get("action_id", "")))
            elif self.path == "/api/shutdown":
                result = {"ok": True}
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._json({"error": "Not found"}, 404)
                return
            self._json(result)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:
            logging.getLogger(__name__).exception("Backend API error")
            self._json({"error": str(exc)}, 500)


def serve(host: str = "127.0.0.1", port: int = 8766) -> None:
    runtime = BackendRuntime()
    server = BackendApiServer((host, port), runtime)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        runtime.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
