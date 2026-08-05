"""Headless HTTP backend used by the React/Electron control room."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import tiktok_obs_controller as core
from tiktok_overlay import LocalOverlayServer


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
        idle_path = core.resolve_existing_media_path(core.get_idle_video_path("main"))
        self.overlay = LocalOverlayServer(idle_path)
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
            "gift": job.gift_name,
            "file": job.file_path.name,
            "priority": job.priority,
            "sound": job.sound_path.name if job.sound_path else "",
        }

    def config(self) -> dict[str, Any]:
        config = core.load_obs_config()
        idle_path = core.get_idle_video_path("main")
        config["idle_video_path"] = str(idle_path) if core.resolve_existing_media_path(idle_path).is_file() else ""
        return config

    def update_config(self, values: dict[str, Any]) -> dict[str, Any]:
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
        }
        for key in allowed:
            if key in values:
                config[key] = values[key]
        config["obs_port"] = int(config.get("obs_port", 4455))
        config.pop("idle_video_path", None)
        core.save_obs_config(config)
        core.TIKTOK_USERNAME = str(config["tiktok_username"]).strip().lstrip("@") or "mock_user"
        core.OBS_HOST = str(config["obs_host"]).strip()
        core.OBS_PORT = int(config["obs_port"])
        core.OBS_PASSWORD = str(config["obs_password"])
        core.SCENE_NAME = str(config["scene_name"]).strip()
        core.IDLE_SOURCE_NAME = str(config["idle_source_name"]).strip()
        core.ACTION_SOURCE_NAME = str(config["action_source_name"]).strip()
        core.OUTPUT_RATIO = str(config.get("output_ratio", "9:16"))
        return self.config()

    def mappings(self) -> list[dict[str, Any]]:
        result = []
        for gift, value in core.GIFT_MAPPING.items():
            videos, sound, action_name = core.resolve_gift_action_media(str(value[0]), str(value[2]))
            result.append(
                {
                    "gift": gift,
                    "action": str(value[0]),
                    "priority": int(value[1]),
                    "sound": str(value[2]),
                    "action_name": action_name,
                    "videos": videos,
                    "resolved_sound": sound,
                }
            )
        return result

    def save_mappings(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mapping: dict[str, tuple[str, int, str, str]] = {}
        for item in items:
            gift = str(item.get("gift", "")).strip().lower()
            action = str(item.get("action", "")).strip()
            if not gift or not action:
                continue
            mapping[gift] = (action, int(item.get("priority", 1)), str(item.get("sound", "")).strip(), "main")
        core.GIFT_MAPPING.clear()
        core.GIFT_MAPPING.update(mapping)
        core.save_gift_mapping(mapping)
        return self.mappings()

    async def _start_app(self, mock_mode: bool, enable_tiktok: bool) -> None:
        if self.app_task and not self.app_task.done():
            return
        self.app = core.TikTokObsApp(mock_mode=mock_mode, enable_tiktok=enable_tiktok, overlay=self.overlay)
        self.started_at = time.monotonic()
        self.app_task = asyncio.create_task(self.app.run())

    def start_system(self, payload: dict[str, Any]) -> None:
        if isinstance(payload.get("config"), dict):
            self.update_config(payload["config"])
        future = asyncio.run_coroutine_threadsafe(
            self._start_app(bool(payload.get("mock_mode")), bool(payload.get("enable_tiktok"))),
            self.loop,
        )
        future.result(timeout=5)

    def stop_system(self) -> None:
        task = self.app_task
        if task and not task.done():
            self.loop.call_soon_threadsafe(task.cancel)

    def submit(self, coroutine: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=5)

    def enqueue_gift(self, gift: str) -> None:
        if not self.app:
            raise RuntimeError("Hệ thống chưa chạy")
        self.submit(self.app.enqueue_gift(gift))

    def skip(self) -> None:
        if self.app:
            self.loop.call_soon_threadsafe(self.app.skip_current)

    def clear_queue(self) -> int:
        return self.app.queue.clear() if self.app else 0

    def set_idle_video(self, path_value: str) -> str:
        path = Path(path_value).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        core.set_idle_video_path("main", path)
        self.overlay.set_idle_path(core.resolve_existing_media_path(path))
        config = self.config()
        config.pop("idle_video_path", None)
        config["idle_video_paths"] = {"1": str(path)}
        config["idle_video_path_1"] = str(path)
        core.save_obs_config(config)
        if self.app and self.app.obs.is_connected:
            self.submit(self.app.obs.set_idle_video(path, "main"))
        return str(path)

    def status(self) -> dict[str, Any]:
        app = self.app
        running = bool(self.app_task and not self.app_task.done())
        queue_items = app.queue.get_items() if app else []
        current = self._serialize_job(app.current_job) if app and app.current_job else None
        progress = 0.0
        remaining = 0.0
        if app and app.current_job and app.current_job_duration > 0:
            elapsed = max(0.0, self.loop.time() - app.current_job_start_time)
            progress = min(1.0, elapsed / app.current_job_duration)
            remaining = max(0.0, app.current_job_duration - elapsed)
        return {
            "running": running,
            "mock_mode": bool(app and app.mock_mode),
            "tiktok_connected": bool(app and app.is_tiktok_connected),
            "obs_connected": bool(app and app.obs.is_connected),
            "overlay_online": self.overlay.is_running,
            "overlay_url": self.overlay.url if self.overlay.is_running else "",
            "overlay_error": self.overlay_error,
            "current": current,
            "queue": [self._serialize_job(item) for item in queue_items],
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
                runtime.enqueue_gift(str(body.get("gift", "")))
                result = {"ok": True}
            elif self.path == "/api/queue/skip":
                runtime.skip()
                result = {"ok": True}
            elif self.path == "/api/queue/clear":
                result = {"cleared": runtime.clear_queue()}
            elif self.path == "/api/config":
                result = runtime.update_config(body)
            elif self.path == "/api/mappings":
                items = body.get("items", [])
                if not isinstance(items, list):
                    raise ValueError("items must be a list")
                result = runtime.save_mappings(items)
            elif self.path == "/api/media/idle":
                result = {"path": runtime.set_idle_video(str(body.get("path", "")))}
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
