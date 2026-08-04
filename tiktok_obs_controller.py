"""
Dieu khien OBS Studio bang su kien qua tang TikTok Live.

Cai dat:
    pip install TikTokLive obsws-python

Yêu cau:
    - OBS Studio dang chay.
    - Bat obs-websocket trong OBS (Tools > WebSocket Server Settings).
    - OBS co mot Scene chinh voi hai Media Source:
        * Idle_Source: video cho dung yen, bat Loop.
        * Action_Source: media source nam de len Idle_Source, ban dau an.
    - Co ffprobe trong PATH de lay dung duration video. Neu khong co,
      script se dung ACTION_DEFAULT_DURATION.

Luu y ve thu vien:
    Goi pip dung la "obsws-python". Day la client Python cho OBS WebSocket
    v5, thuong duoc nham voi goi cu "obs-websocket-py" cua giao thuc v4.
"""

from __future__ import annotations

import asyncio
import contextlib
import heapq
import itertools
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, GiftEvent
from obsws_python import ReqClient


# ============================== Cau hinh ===============================
TIKTOK_USERNAME = "your_tiktok_username"
OBS_HOST = "127.0.0.1"
OBS_PORT = 4455
OBS_PASSWORD = "your_obs_websocket_password"
SCENE_NAME = "Main Scene"

IDLE_SOURCE_NAME = "Idle_Source"
ACTION_SOURCE_NAME = "Action_Source"
APP_DIRECTORY = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
VIDEO_DIRECTORY = APP_DIRECTORY / "videos"
ACTION_DEFAULT_DURATION = 10.0
TIKTOK_RECONNECT_DELAY = 5.0
OBS_RECONNECT_DELAY = 3.0

IDLE_VIDEO_PATH = VIDEO_DIRECTORY / "idle_loop.mp4"

GIFT_MAPPING: dict[str, tuple[str, int]] = {
    "rose": ("cho_1_sui.png", 1),
    "doughnut": ("cho_2_trong_chuoi.png", 2),
    "perfume": ("cho_2_trong_chuoi.png", 2),
    "tiktok": ("3_cho_nhay_tiktok.mp4", 3),
    "lion": ("3_cho_bien_su_tu.mp4", 5),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
LOGGER = logging.getLogger("tiktok-obs")


def resolve_existing_media_path(file_path: Path) -> Path:
    """Neu file_path ton tai thi tra ve file_path. Neu khong, thu tim file cung ten voi dinh dang khac (.mp4, .png, v.v.)."""
    if file_path.is_file():
        return file_path

    if not file_path.is_absolute():
        abs_path = VIDEO_DIRECTORY / file_path
        if abs_path.is_file():
            return abs_path

    stem = file_path.stem
    parent = file_path.parent if file_path.is_absolute() and file_path.parent.exists() else VIDEO_DIRECTORY

    possible_extensions = [".mp4", ".png", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".webp"]
    for ext in possible_extensions:
        alt_path = parent / f"{stem}{ext}"
        if alt_path.is_file():
            return alt_path

    return file_path


@dataclass(frozen=True)
class GiftJob:
    gift_name: str
    file_path: Path
    priority: int


class PriorityGiftQueue:
    """Bao ngoai bang heap de uu tien cao hon duoc xu ly truoc."""

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, GiftJob]] = []
        self._sequence = itertools.count()
        self._condition = asyncio.Condition()
        self._unfinished_tasks = 0

    async def put(self, job: GiftJob) -> None:
        async with self._condition:
            heapq.heappush(self._heap, (-job.priority, next(self._sequence), job))
            self._unfinished_tasks += 1
            self._condition.notify()

    async def get(self) -> GiftJob:
        async with self._condition:
            await self._condition.wait_for(lambda: len(self._heap) > 0)
            _, _, job = heapq.heappop(self._heap)
            return job

    def task_done(self) -> None:
        if self._unfinished_tasks > 0:
            self._unfinished_tasks -= 1

    def clear(self) -> int:
        count = len(self._heap)
        self._heap.clear()
        self._unfinished_tasks = 0
        return count

    def get_items(self) -> list[GiftJob]:
        return [item[2] for item in sorted(self._heap)]

    def __len__(self) -> int:
        return len(self._heap)


class ObsController:
    """Quan ly ket noi OBS va tu dong reconnect khi request bi loi."""

    def __init__(self, mock_mode: bool = False) -> None:
        self.mock_mode = mock_mode
        self._client: ReqClient | None = None
        self._action_scene_item_id: int | None = None
        self._idle_scene_item_id: int | None = None
        self._lock = asyncio.Lock()
        self.is_connected: bool = False

    async def connect(self) -> None:
        async with self._lock:
            if self.is_connected:
                return
            if self.mock_mode:
                self.is_connected = True
                LOGGER.info("Da kich hoat Che Do Gia Lap OBS (Mock Mode)")
                return

            self._client = await asyncio.to_thread(
                ReqClient,
                host=OBS_HOST,
                port=OBS_PORT,
                password=OBS_PASSWORD,
                timeout=2,
            )
            self.is_connected = True
            LOGGER.info("Da ket noi OBS WebSocket v5 tai %s:%s", OBS_HOST, OBS_PORT)

            try:
                # 1. Tu dong nhan dien Scene hien tai trong OBS Studio
                scene_list_resp = await asyncio.to_thread(self._client.get_scene_list)
                available_scenes = [sc["sceneName"] for sc in scene_list_resp.scenes]
                global SCENE_NAME
                if SCENE_NAME not in available_scenes and available_scenes:
                    try:
                        current_scene_resp = await asyncio.to_thread(self._client.get_current_program_scene)
                        curr_name = current_scene_resp.current_program_scene_name
                        SCENE_NAME = curr_name if curr_name in available_scenes else available_scenes[0]
                    except Exception:
                        SCENE_NAME = available_scenes[0]
                    LOGGER.info("Tu dong chon Scene dang mo trong OBS: '%s'", SCENE_NAME)

                # 2. Dam bao Nguon Idle_Source & Action_Source ton tai trong OBS
                input_list_resp = await asyncio.to_thread(self._client.get_input_list)
                existing_inputs = [inp["inputName"] for inp in input_list_resp.inputs]

                if IDLE_SOURCE_NAME not in existing_inputs:
                    LOGGER.info("Tu dong tao Nguon '%s' trong OBS Scene '%s'", IDLE_SOURCE_NAME, SCENE_NAME)
                    await asyncio.to_thread(
                        self._client.create_input,
                        sceneName=SCENE_NAME,
                        inputName=IDLE_SOURCE_NAME,
                        inputKind="ffmpeg_source",
                        inputSettings={},
                        sceneItemEnabled=True,
                    )

                if ACTION_SOURCE_NAME not in existing_inputs:
                    LOGGER.info("Tu dong tao Nguon '%s' trong OBS Scene '%s'", ACTION_SOURCE_NAME, SCENE_NAME)
                    await asyncio.to_thread(
                        self._client.create_input,
                        sceneName=SCENE_NAME,
                        inputName=ACTION_SOURCE_NAME,
                        inputKind="ffmpeg_source",
                        inputSettings={},
                        sceneItemEnabled=False,
                    )

                # 3. Dam bao Nguon duoc gan (Attach) vao SceneItem list cua SCENE_NAME
                scene_items_resp = await asyncio.to_thread(self._client.get_scene_item_list, SCENE_NAME)
                scene_item_names = [item["sourceName"] for item in scene_items_resp.scene_items]

                if IDLE_SOURCE_NAME not in scene_item_names:
                    await asyncio.to_thread(
                        self._client.create_scene_item,
                        scene_name=SCENE_NAME,
                        source_name=IDLE_SOURCE_NAME,
                        enabled=True,
                    )

                if ACTION_SOURCE_NAME not in scene_item_names:
                    await asyncio.to_thread(
                        self._client.create_scene_item,
                        scene_name=SCENE_NAME,
                        source_name=ACTION_SOURCE_NAME,
                        enabled=False,
                    )

                # 4. Lay item id cho ca Action_Source va Idle_Source
                try:
                    resp_action = await asyncio.to_thread(
                        self._client.get_scene_item_id,
                        SCENE_NAME,
                        ACTION_SOURCE_NAME,
                    )
                    self._action_scene_item_id = resp_action.scene_item_id
                except Exception as exc:
                    LOGGER.warning("Khong tim thay SceneItemId cho %s: %s", ACTION_SOURCE_NAME, exc)

                try:
                    resp_idle = await asyncio.to_thread(
                        self._client.get_scene_item_id,
                        SCENE_NAME,
                        IDLE_SOURCE_NAME,
                    )
                    self._idle_scene_item_id = resp_idle.scene_item_id
                except Exception as exc:
                    LOGGER.warning("Khong tim thay SceneItemId cho %s: %s", IDLE_SOURCE_NAME, exc)

                if self._action_scene_item_id is not None:
                    await asyncio.to_thread(
                        self._client.set_scene_item_enabled,
                        scene_name=SCENE_NAME,
                        item_id=self._action_scene_item_id,
                        enabled=False,
                    )
                if self._idle_scene_item_id is not None:
                    await asyncio.to_thread(
                        self._client.set_scene_item_enabled,
                        scene_name=SCENE_NAME,
                        item_id=self._idle_scene_item_id,
                        enabled=True,
                    )
            except Exception as exc:
                LOGGER.warning("Auto-setup OBS Media Sources: %s", exc)

    async def close(self) -> None:
        async with self._lock:
            self.is_connected = False
            if self._client is not None and not self.mock_mode:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(self._client.disconnect)
            self._client = None
            self._action_scene_item_id = None
            self._idle_scene_item_id = None

    async def _request(self, method_name: str, **kwargs: Any) -> Any:
        if self.mock_mode:
            return True
        for attempt in range(2):
            try:
                await self.connect()
                client = self._client
                if client is None:
                    raise ConnectionError("OBS client chua san sang")
                return await asyncio.to_thread(getattr(client, method_name), **kwargs)
            except Exception as exc:
                LOGGER.warning("OBS request %s loi: %s", method_name, exc)
                await self.close()
                if attempt == 0:
                    await asyncio.sleep(OBS_RECONNECT_DELAY)
        raise ConnectionError(f"Khong the gui request OBS: {method_name}")

    async def _get_scene_item_id(self, source_name: str) -> int | None:
        if self.mock_mode:
            return 1
        try:
            resp = await self._request("get_scene_item_id", scene_name=SCENE_NAME, source_name=source_name)
            return getattr(resp, "scene_item_id", None)
        except Exception as exc:
            LOGGER.warning("Khong the lay SceneItemId cho '%s' trong Scene '%s': %s", source_name, SCENE_NAME, exc)
            return None

    async def _set_action_visible(self, visible: bool) -> None:
        if self.mock_mode:
            LOGGER.info("[MOCK OBS] Set action visible = %s, idle visible = %s", visible, not visible)
            return

        action_item_id = await self._get_scene_item_id(ACTION_SOURCE_NAME)
        idle_item_id = await self._get_scene_item_id(IDLE_SOURCE_NAME)

        if visible:
            # Bat Action, An Idle
            if action_item_id is not None:
                await self._request(
                    "set_scene_item_enabled",
                    scene_name=SCENE_NAME,
                    item_id=action_item_id,
                    enabled=True,
                )
            if idle_item_id is not None:
                await self._request(
                    "set_scene_item_enabled",
                    scene_name=SCENE_NAME,
                    item_id=idle_item_id,
                    enabled=False,
                )
            with contextlib.suppress(Exception):
                await self._request("trigger_media_input_action", name=ACTION_SOURCE_NAME, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")
        else:
            # An Action, Bat Idle
            if action_item_id is not None:
                await self._request(
                    "set_scene_item_enabled",
                    scene_name=SCENE_NAME,
                    item_id=action_item_id,
                    enabled=False,
                )

            # Dung Action Source media input de khong phat ngam
            with contextlib.suppress(Exception):
                await self._request("trigger_media_input_action", name=ACTION_SOURCE_NAME, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP")

            if idle_item_id is not None:
                await self._request(
                    "set_scene_item_enabled",
                    scene_name=SCENE_NAME,
                    item_id=idle_item_id,
                    enabled=True,
                )
            with contextlib.suppress(Exception):
                await self._request("trigger_media_input_action", name=IDLE_SOURCE_NAME, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")

        # Studio Mode
        with contextlib.suppress(Exception):
            sm_resp = await self._request("get_studio_mode_enabled")
            if getattr(sm_resp, "studio_mode_enabled", False):
                await self._request("trigger_studio_mode_transition")
                LOGGER.info("[OBS Studio Mode] Tu dong Transition tu Preview sang Program")

    async def play_action(self, video_path: Path) -> None:
        video_path = resolve_existing_media_path(video_path)
        if not self.mock_mode and not video_path.is_file():
            LOGGER.warning("Chua tim thay file video/anh: %s", video_path)

        LOGGER.info("[OBS] Phat action video: %s", video_path.name)
        if not self.mock_mode and video_path.is_file():
            clean_path = str(video_path.resolve()).replace("\\", "/")
            is_image = video_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp")
            await self._request(
                "set_input_settings",
                name=ACTION_SOURCE_NAME,
                settings={
                    "local_file": clean_path,
                    "file": clean_path,
                    "restart_on_activate": True,
                    "is_local_file": True,
                    "clear_on_media_end": False,
                    "looping": is_image,
                },
                overlay=True,
            )
        await self._set_action_visible(True)

    async def set_idle_video(self, video_path: Path) -> None:
        video_path = resolve_existing_media_path(video_path)
        LOGGER.info("[OBS] Cau hinh Video Cho (Idle): %s", video_path.name)
        if not self.mock_mode and video_path.is_file():
            clean_path = str(video_path.resolve()).replace("\\", "/")
            is_image = video_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp")
            await self._request(
                "set_input_settings",
                name=IDLE_SOURCE_NAME,
                settings={
                    "local_file": clean_path,
                    "file": clean_path,
                    "is_local_file": True,
                    "clear_on_media_end": False,
                    "looping": True,
                },
                overlay=True,
            )

    async def stop_action(self) -> None:
        LOGGER.info("[OBS] An action video (quay ve Idle)")
        await self._set_action_visible(False)


def get_video_duration(video_path: Path) -> float:
    """Lay duration bang ffprobe; neu la file anh hoac khong co ffprobe thi fallback 3.0s/10.0s."""
    if not video_path.is_file():
        return ACTION_DEFAULT_DURATION

    if video_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        return 3.0

    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=2.0)
        duration = float(result.stdout.strip())
        return max(duration, 0.1)
    except (FileNotFoundError, ValueError, subprocess.SubprocessError, OSError):
        return ACTION_DEFAULT_DURATION


class TikTokObsApp:
    def __init__(self, mock_mode: bool = False, enable_tiktok: bool = False) -> None:
        self.mock_mode = mock_mode
        self.enable_tiktok = enable_tiktok
        self.queue = PriorityGiftQueue()
        self.obs = ObsController(mock_mode=mock_mode)
        self._stop_event = asyncio.Event()
        self._current_interrupt: asyncio.Event | None = None
        self.is_tiktok_connected: bool = False
        self.current_job: GiftJob | None = None
        self.current_job_start_time: float = 0.0
        self.current_job_duration: float = 0.0

        self.client = TikTokLiveClient(unique_id=TIKTOK_USERNAME)
        self.client.add_listener(ConnectEvent, self.on_connect)
        self.client.add_listener(DisconnectEvent, self.on_disconnect)
        self.client.add_listener(GiftEvent, self.on_gift)

    async def on_connect(self, _: ConnectEvent) -> None:
        self.is_tiktok_connected = True
        LOGGER.info("Da ket noi TikTok Live: @%s", TIKTOK_USERNAME)

    async def on_disconnect(self, _: DisconnectEvent) -> None:
        self.is_tiktok_connected = False
        LOGGER.warning("TikTok Live da ngat ket noi; se thu ket noi lai")

    async def on_gift(self, event: GiftEvent) -> None:
        if getattr(event, "repeat_end", True) is False:
            return

        gift_name = str(getattr(event.gift, "name", "")).strip().lower()
        await self.enqueue_gift(gift_name)

    async def enqueue_gift(self, gift_name: str) -> None:
        """Them mot gift vao queue theo thu tu uu tien; khong ngat video dang phat."""
        gift_name = gift_name.strip().lower()
        mapping = GIFT_MAPPING.get(gift_name)
        if mapping is None:
            LOGGER.info("Bo qua qua tang chua map: %s", gift_name or "(khong ten)")
            return

        filename, priority = mapping
        p = Path(filename)
        video_path = p if p.is_absolute() else (VIDEO_DIRECTORY / filename)
        resolved_path = resolve_existing_media_path(video_path)

        if not resolved_path.is_file():
            LOGGER.warning("⚠️ CHÚ Ý: File media cho quà '%s' chưa tồn tại trên ổ đĩa: %s", gift_name, video_path)

        job = GiftJob(gift_name, resolved_path, priority)
        await self.queue.put(job)
        LOGGER.info("Them vao queue: %s -> %s (priority=%s)", gift_name, resolved_path.name, priority)

    def skip_current(self) -> None:
        """Ngat ngay video dang phat de chuyen sang mon tiep theo trong queue."""
        if self._current_interrupt is not None:
            LOGGER.info("Nguoi dung yeu cau Bo Qua (Skip) video hien tai")
            self._current_interrupt.set()

    async def _play_job(self, job: GiftJob) -> None:
        interrupt = asyncio.Event()
        self._current_interrupt = interrupt
        self.current_job = job
        self.current_job_start_time = asyncio.get_event_loop().time()
        self.current_job_duration = get_video_duration(job.file_path)

        try:
            await self.obs.play_action(job.file_path)
            sleep_task = asyncio.create_task(asyncio.sleep(self.current_job_duration))
            interrupt_task = asyncio.create_task(interrupt.wait())
            done, pending = await asyncio.wait(
                {sleep_task, interrupt_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if interrupt_task in done:
                LOGGER.info("Video %s bi ngat boi qua uu tien cao", job.gift_name)
        finally:
            self._current_interrupt = None
            self.current_job = None
            self.current_job_start_time = 0.0
            self.current_job_duration = 0.0
            with contextlib.suppress(Exception):
                await self.obs.stop_action()

    async def worker(self) -> None:
        while not self._stop_event.is_set():
            job = await self.queue.get()
            try:
                LOGGER.info("Dang phat qua %s (priority=%s)", job.gift_name, job.priority)
                await self._play_job(job)
            except Exception:
                LOGGER.exception("Loi khi xu ly qua %s", job.gift_name)
            finally:
                self.queue.task_done()

    async def tiktok_loop(self) -> None:
        if self.mock_mode:
            self.is_tiktok_connected = True
            LOGGER.info("[MOCK MODE] Gia lap TikTok Live Connected: @%s", TIKTOK_USERNAME)
            await self._stop_event.wait()
            return

        if not self.enable_tiktok or TIKTOK_USERNAME in ("your_tiktok_username", "mock_user", ""):
            self.is_tiktok_connected = False
            LOGGER.info("TikTok Live dang o che do Standby (Thu nghiem phim bam Stream Deck). Bật Tích chọn 'Kết nối TikTok Live' khi livestream thuc te!")
            await self._stop_event.wait()
            return

        while not self._stop_event.is_set():
            try:
                await self.client.connect()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.is_tiktok_connected = False
                LOGGER.warning("TikTok connect loi: %s; thu lai sau %ss", exc, TIKTOK_RECONNECT_DELAY)
                await asyncio.sleep(TIKTOK_RECONNECT_DELAY)

    async def run(self) -> None:
        try:
            await self.obs.connect()
            await self.obs.set_idle_video(IDLE_VIDEO_PATH)
        except Exception as exc:
            LOGGER.error("Khong the ket noi OBS: %s", exc)
            if not self.mock_mode:
                raise

        worker_task = asyncio.create_task(self.worker())
        try:
            await self.tiktok_loop()
        finally:
            self._stop_event.set()
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
            await self.obs.close()


async def main() -> None:
    if TIKTOK_USERNAME == "your_tiktok_username":
        raise SystemExit("Hay sua TIKTOK_USERNAME truoc khi chay script.")
    try:
        await TikTokObsApp().run()
    except KeyboardInterrupt:
        LOGGER.info("Da dung boi nguoi dung")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

