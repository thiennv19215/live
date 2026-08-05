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
import ctypes
import heapq
import itertools
import logging
import os
import random
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
IDLE_VIDEO_PATH_1 = VIDEO_DIRECTORY / "idle_loop_1.mp4"
IDLE_VIDEO_PATH_2 = VIDEO_DIRECTORY / "idle_loop_2.mp4"
IDLE_VIDEO_PATH_3 = VIDEO_DIRECTORY / "idle_loop_3.mp4"
IDLE_VIDEO_PATH_4 = VIDEO_DIRECTORY / "idle_loop_4.mp4"
IDLE_VIDEO_PATH = IDLE_VIDEO_PATH_1
ACTION_DEFAULT_DURATION = 10.0
TIKTOK_RECONNECT_DELAY = 5.0
OBS_RECONNECT_DELAY = 3.0

import json

OBS_CONFIG_FILE = APP_DIRECTORY / "obs_config.json"


def load_obs_config() -> dict[str, Any]:
    default_cfg = {
        "tiktok_username": "your_tiktok_username",
        "obs_host": "127.0.0.1",
        "obs_port": 4455,
        "obs_password": "your_obs_websocket_password",
        "scene_name": "Main Scene",
        "idle_source_name": "Idle_Source",
        "action_source_name": "Action_Source",
    }
    if OBS_CONFIG_FILE.is_file():
        try:
            with open(OBS_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_cfg.update(data)
        except Exception:
            pass
    return default_cfg


def save_obs_config(config: dict[str, Any]) -> None:
    try:
        with open(OBS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


_saved_obs_cfg = load_obs_config()
TIKTOK_USERNAME = str(_saved_obs_cfg.get("tiktok_username", TIKTOK_USERNAME))
OBS_HOST = str(_saved_obs_cfg.get("obs_host", OBS_HOST))
OBS_PORT = int(_saved_obs_cfg.get("obs_port", OBS_PORT))
OBS_PASSWORD = str(_saved_obs_cfg.get("obs_password", OBS_PASSWORD))
SCENE_NAME = str(_saved_obs_cfg.get("scene_name", SCENE_NAME))
IDLE_SOURCE_NAME = str(_saved_obs_cfg.get("idle_source_name", IDLE_SOURCE_NAME))
ACTION_SOURCE_NAME = str(_saved_obs_cfg.get("action_source_name", ACTION_SOURCE_NAME))

QUEUE_TEXT_SOURCE_NAME = "Queue_Text_Source"
ENABLE_QUEUE_TEXT_SOURCE = False  # Đặt False nếu chỉ muốn OBS phát Video hiệu ứng khi có quà, không hiện Text Hàng chờ
QUEUE_FILE_PATH = APP_DIRECTORY / "queue_status.txt"

CHAR_SHORT_TAGS = {
    "char1": "[NV 1]",
    "char2": "[NV 2]",
    "char3": "[NV 3]",
    "char4": "[NV 4]",
    "all": "[Tất cả]",
}

CONFIG_FILE = APP_DIRECTORY / "gift_config.json"
ACTION_PRESETS_FILE = APP_DIRECTORY / "action_presets.json"

AUDIO_SOURCE_NAME = "Audio_Action_Source"


@dataclass
class ActionPreset:
    id: str
    name: str
    videos: list[str]
    sound_filename: str = ""


DEFAULT_ACTION_PRESETS: dict[str, dict[str, Any]] = {
    "action_dance_rose": {
        "name": "💃 Nhảy Rose Hot Trend",
        "videos": ["cho_1_sui.png", "Dog_doing_funny_trick_dance_202608040341.mp4"],
        "sound_filename": "",
    },
    "action_funny_doughnut": {
        "name": "🍩 Ăn Mừng Vui Nhộn",
        "videos": ["cho_2_trong_chuoi.png"],
        "sound_filename": "",
    },
    "action_dance_tiktok": {
        "name": "♪ Nhảy TikTok Sôi Động",
        "videos": ["3_cho_nhay_tiktok.mp4"],
        "sound_filename": "",
    },
    "action_lion_transform": {
        "name": "🦁 Biến Hình Sư Tử",
        "videos": ["3_cho_bien_su_tu.mp4"],
        "sound_filename": "",
    },
}


def parse_video_filenames(val: str | list[str] | Any) -> list[str]:
    """Tach danh sach cac file video tu chuoi (phan cach boi dau phay) hoac list."""
    if isinstance(val, list):
        items = [str(x).strip() for x in val if str(x).strip()]
        return items if items else [""]
    if isinstance(val, str):
        items = [x.strip() for x in val.split(",") if x.strip()]
        return items if items else [""]
    return [str(val).strip()]


def select_random_video_filename(val: str | list[str] | Any) -> str:
    """Chon ngau nhien 1 file video tu danh sach cac file media duoc gan cho qua."""
    files = parse_video_filenames(val)
    valid_files = [f for f in files if f]
    return random.choice(valid_files) if valid_files else ""


def load_action_presets() -> dict[str, ActionPreset]:
    presets: dict[str, ActionPreset] = {}
    data = DEFAULT_ACTION_PRESETS.copy()
    if ACTION_PRESETS_FILE.is_file():
        try:
            with open(ACTION_PRESETS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass

    for aid, val in data.items():
        if isinstance(val, dict):
            name = str(val.get("name", aid))
            raw_vids = val.get("videos", [])
            vids = parse_video_filenames(raw_vids)
            sound_fn = str(val.get("sound_filename", ""))
            presets[aid] = ActionPreset(id=aid, name=name, videos=vids, sound_filename=sound_fn)
    return presets


def save_action_presets(presets: dict[str, ActionPreset | dict[str, Any]]) -> None:
    try:
        data = {}
        for aid, preset in presets.items():
            if isinstance(preset, ActionPreset):
                data[aid] = {
                    "name": preset.name,
                    "videos": preset.videos,
                    "sound_filename": preset.sound_filename,
                }
            elif isinstance(preset, dict):
                data[aid] = preset
        with open(ACTION_PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


ACTION_PRESETS = load_action_presets()

DEFAULT_GIFT_MAPPING: dict[str, tuple[str, int, str, str]] = {
    "rose": ("action_dance_rose", 1, "", "char1"),
    "doughnut": ("action_funny_doughnut", 2, "", "char2"),
    "perfume": ("action_funny_doughnut", 2, "", "char2"),
    "tiktok": ("action_dance_tiktok", 3, "", "char3"),
    "lion": ("action_lion_transform", 5, "", "all"),
}


def resolve_gift_action_media(mapping_val: str, sound_mapped_val: str = "") -> tuple[list[str], str, str]:
    """
    Tra cuu tu mapping_val (co the la action_id hoac chuoi video).
    Tra ve: (danh_sach_video_filenames, sound_filename, action_display_name).
    """
    mapping_key = str(mapping_val).strip()
    if mapping_key in ACTION_PRESETS:
        preset = ACTION_PRESETS[mapping_key]
        sound = sound_mapped_val or preset.sound_filename
        return preset.videos, sound, preset.name

    for aid, preset in ACTION_PRESETS.items():
        if aid.lower() == mapping_key.lower():
            sound = sound_mapped_val or preset.sound_filename
            return preset.videos, sound, preset.name

    vids = parse_video_filenames(mapping_val)
    return vids, sound_mapped_val, "Custom Video"


def load_gift_mapping() -> dict[str, tuple[str, int, str, str]]:
    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                res: dict[str, tuple[str, int, str, str]] = {}
                for k, v in data.items():
                    gift_key = str(k).lower().strip()
                    raw_fn = v[0]
                    if isinstance(raw_fn, list):
                        fn = ", ".join(str(x).strip() for x in raw_fn if str(x).strip())
                    else:
                        fn = str(raw_fn).strip()
                    prio = int(v[1])
                    sound_fn = str(v[2]) if len(v) > 2 else ""
                    target_char = str(v[3]) if len(v) > 3 else "char1"
                    res[gift_key] = (fn, prio, sound_fn, target_char)
                return res
        except Exception:
            pass
    return DEFAULT_GIFT_MAPPING.copy()


def save_gift_mapping(mapping: dict[str, Any]) -> None:
    try:
        data = {}
        for k, v in mapping.items():
            fn = str(v[0]).strip()
            prio = int(v[1])
            sound_fn = str(v[2]) if len(v) > 2 else ""
            target_char = str(v[3]) if len(v) > 3 else "char1"
            data[str(k).lower().strip()] = [fn, prio, sound_fn, target_char]
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


GIFT_MAPPING = load_gift_mapping()

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


def resolve_existing_sound_path(file_path: Path) -> Path:
    """Neu file_path ton tai thi tra ve file_path. Neu khong, thu tim file cung ten trong VIDEO_DIRECTORY."""
    if not str(file_path).strip():
        return file_path
    if file_path.is_file():
        return file_path

    if not file_path.is_absolute():
        abs_path = VIDEO_DIRECTORY / file_path
        if abs_path.is_file():
            return abs_path

    stem = file_path.stem
    parent = file_path.parent if file_path.is_absolute() and file_path.parent.exists() else VIDEO_DIRECTORY

    possible_extensions = [".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac", ".wma"]
    for ext in possible_extensions:
        alt_path = parent / f"{stem}{ext}"
        if alt_path.is_file():
            return alt_path

    return file_path


def play_sound_file(sound_path: Path) -> None:
    """Phat file am thanh (.mp3, .wav, ...) qua Windows MCI Sound API."""
    if not sound_path or not sound_path.is_file():
        return
    try:
        if sys.platform == "win32":
            alias = "tiktok_gift_sound"
            ctypes.windll.winmm.mciSendStringW(f"close {alias}", None, 0, 0)
            abs_path = str(sound_path.resolve()).replace("/", "\\")
            res = ctypes.windll.winmm.mciSendStringW(f'open "{abs_path}" type mpegvideo alias {alias}', None, 0, 0)
            if res != 0:
                res = ctypes.windll.winmm.mciSendStringW(f'open "{abs_path}" alias {alias}', None, 0, 0)
            if res == 0:
                ctypes.windll.winmm.mciSendStringW(f"play {alias} from 0", None, 0, 0)
                LOGGER.info("Da phat am thanh hieu ung: %s", sound_path.name)
    except Exception as exc:
        LOGGER.warning("Khong the phat file am thanh %s: %s", sound_path.name, exc)


def stop_sound_file() -> None:
    """Dung phat am thanh hieu ung qua Windows MCI."""
    try:
        if sys.platform == "win32":
            alias = "tiktok_gift_sound"
            ctypes.windll.winmm.mciSendStringW(f"stop {alias}", None, 0, 0)
            ctypes.windll.winmm.mciSendStringW(f"close {alias}", None, 0, 0)
    except Exception:
        pass


@dataclass(frozen=True)
class GiftJob:
    gift_name: str
    file_path: Path
    priority: int
    sound_path: Path | None = None
    target_char: str = "char1"


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

                # 2. Cập nhật cache và đảm bảo 2 Nguồn mặc định (Idle_Source & Action_Source) tồn tại trong OBS
                await self.ensure_default_sources_exist()
                # 3. Dọn dẹp dữ liệu cũ trên OBS: Ẩn tất cả Action Source cũ và bật lại Video Nền sạch
                await self.reset_obs_display_state()
            except Exception as exc:
                LOGGER.warning("Auto-setup OBS Media Sources: %s", exc)

    async def reset_obs_display_state(self) -> None:
        """Dọn dẹp sạch toàn bộ hiển thị OBS khi khởi động/kết nối lại: Ẩn Action sources, Bật Idle sources."""
        if self.mock_mode or not self._client:
            return

        try:
            await self._refresh_scene_items_cache()
            action_sources = ["Action_Source_All", ACTION_SOURCE_NAME] + [f"Action_Source_{i}" for i in range(1, 5)]
            idle_sources = [IDLE_SOURCE_NAME] + [f"Idle_Source_{i}" for i in range(1, 5)]

            # 1. Ẩn toàn bộ Action sources & dừng media cũ
            for asrc in action_sources:
                iid = await self._get_scene_item_id(asrc)
                if iid is not None:
                    with contextlib.suppress(Exception):
                        await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=iid, enabled=False)
                        await self._request("trigger_media_input_action", name=asrc, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP")

            # 2. Bật lại toàn bộ Idle sources nền
            for isrc in idle_sources:
                iid = await self._get_scene_item_id(isrc)
                if iid is not None:
                    with contextlib.suppress(Exception):
                        await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=iid, enabled=True)
                        await self._request("trigger_media_input_action", name=isrc, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")

            LOGGER.info("[OBS] Da tu dong don dep du lieu cu tren OBS va khoi phục Che Do Cho sach")
        except Exception as exc:
            LOGGER.debug("reset_obs_display_state exception: %s", exc)

    async def ensure_default_sources_exist(self) -> None:
        if self.mock_mode or not self._client:
            return
        try:
            await self._refresh_scene_items_cache()
            existing = getattr(self, "existing_inputs", [])

            needed = []
            if IDLE_SOURCE_NAME not in existing:
                needed.append((IDLE_SOURCE_NAME, True))
            if ACTION_SOURCE_NAME not in existing:
                needed.append((ACTION_SOURCE_NAME, False))

            if not needed:
                return

            possible_kinds = ["ffmpeg_source", "vlc_source"]
            for src_name, default_enabled in needed:
                for kind in possible_kinds:
                    try:
                        await asyncio.to_thread(
                            self._client.create_input,
                            sceneName=SCENE_NAME,
                            inputName=src_name,
                            inputKind=kind,
                            inputSettings={},
                            sceneItemEnabled=default_enabled,
                        )
                        LOGGER.info("Tu dong tao Nguon chuẩn '%s' trong OBS Scene '%s'", src_name, SCENE_NAME)
                        break
                    except Exception:
                        continue

            await self._refresh_scene_items_cache()
        except Exception as exc:
            LOGGER.debug("ensure_default_sources_exist exception: %s", exc)

    async def _refresh_scene_items_cache(self) -> dict[str, int]:
        if self.mock_mode or not self._client:
            return {}

        inputs_list = []
        try:
            input_list_resp = await asyncio.to_thread(self._client.get_input_list)
            raw_inputs = getattr(input_list_resp, "inputs", [])
            for inp in raw_inputs:
                name = inp.get("inputName") or inp.get("input_name") if isinstance(inp, dict) else (getattr(inp, "input_name", None) or getattr(inp, "inputName", None))
                if name:
                    inputs_list.append(str(name))
        except Exception as exc:
            LOGGER.debug("Loi get_input_list: %s", exc)

        self.existing_inputs = inputs_list

        cache: dict[str, int] = {}
        try:
            resp = await asyncio.to_thread(self._client.get_scene_item_list, SCENE_NAME)
            raw_items = getattr(resp, "scene_items", []) or getattr(resp, "sceneItems", [])
            for item in raw_items:
                if isinstance(item, dict):
                    s_name = item.get("sourceName") or item.get("source_name")
                    s_id = item.get("sceneItemId") or item.get("scene_item_id")
                else:
                    s_name = getattr(item, "source_name", None) or getattr(item, "sourceName", None)
                    s_id = getattr(item, "scene_item_id", None) or getattr(item, "sceneItemId", None)
                if s_name and s_id is not None:
                    cache[str(s_name)] = int(s_id)
        except Exception as exc:
            LOGGER.debug("Loi get_scene_item_list: %s", exc)

        self._scene_items_cache = cache
        return cache

    async def close(self) -> None:
        async with self._lock:
            self.is_connected = False
            if self._client is not None and not self.mock_mode:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(self._client.disconnect)
            self._client = None
            self._action_scene_item_id = None
            self._idle_scene_item_id = None
            self._scene_items_cache = None

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
        if not hasattr(self, "_scene_items_cache") or self._scene_items_cache is None:
            await self._refresh_scene_items_cache()
        return self._scene_items_cache.get(source_name) if self._scene_items_cache else None

    def _get_sources_for_target(self, target_char: str = "char1") -> tuple[str, str]:
        target = str(target_char).lower().strip()
        idx_map = {"char1": "1", "1": "1", "char2": "2", "2": "2", "char3": "3", "3": "3", "char4": "4", "4": "4"}
        inputs = getattr(self, "existing_inputs", [])
        if target in idx_map:
            idx = idx_map[target]
            idle_candidate = f"Idle_Source_{idx}"
            action_candidate = f"Action_Source_{idx}"
            if self.mock_mode or not inputs or (idle_candidate in inputs or action_candidate in inputs):
                return (idle_candidate, action_candidate)
            return (IDLE_SOURCE_NAME, ACTION_SOURCE_NAME)
        elif target == "all":
            if self.mock_mode or not inputs or ("Action_Source_All" in inputs):
                return ("Action_Source_All", "Action_Source_All")
            return (ACTION_SOURCE_NAME, ACTION_SOURCE_NAME)
        return (IDLE_SOURCE_NAME, ACTION_SOURCE_NAME)

    async def _set_action_visible(self, visible: bool, target_char: str = "char1") -> None:
        if self.mock_mode:
            LOGGER.info("[MOCK OBS] Target %s: Set action visible = %s, idle visible = %s", target_char, visible, not visible)
            return

        target_norm = str(target_char).lower().strip()
        if target_norm == "all":
            action_item_id = await self._get_scene_item_id("Action_Source_All") or await self._get_scene_item_id(ACTION_SOURCE_NAME)
            target_action_source = "Action_Source_All" if (await self._get_scene_item_id("Action_Source_All")) is not None else ACTION_SOURCE_NAME
            idle_sources = [f"Idle_Source_{i}" for i in range(1, 5)] + [IDLE_SOURCE_NAME]

            if visible:
                if action_item_id is not None:
                    await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=action_item_id, enabled=True)
                for isrc in idle_sources:
                    iid = await self._get_scene_item_id(isrc)
                    if iid is not None:
                        with contextlib.suppress(Exception):
                            await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=iid, enabled=False)
                with contextlib.suppress(Exception):
                    await self._request("trigger_media_input_action", name=target_action_source, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")
            else:
                if action_item_id is not None:
                    await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=action_item_id, enabled=False)
                with contextlib.suppress(Exception):
                    await self._request("trigger_media_input_action", name=target_action_source, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP")
                for isrc in idle_sources:
                    iid = await self._get_scene_item_id(isrc)
                    if iid is not None:
                        with contextlib.suppress(Exception):
                            await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=iid, enabled=True)
                            await self._request("trigger_media_input_action", name=isrc, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")
        else:
            idle_name, action_name = self._get_sources_for_target(target_char)
            action_item_id = await self._get_scene_item_id(action_name) or await self._get_scene_item_id(ACTION_SOURCE_NAME)
            idle_item_id = await self._get_scene_item_id(idle_name) or await self._get_scene_item_id(IDLE_SOURCE_NAME)
            target_action_source = action_name if (await self._get_scene_item_id(action_name)) is not None else ACTION_SOURCE_NAME
            target_idle_source = idle_name if (await self._get_scene_item_id(idle_name)) is not None else IDLE_SOURCE_NAME

            if visible:
                # 1. Bật Action Video và cho phát ngay ở lớp trên (Overlapping Layer)
                if action_item_id is not None:
                    await self._request(
                        "set_scene_item_enabled",
                        scene_name=SCENE_NAME,
                        item_id=action_item_id,
                        enabled=True,
                    )
                with contextlib.suppress(Exception):
                    await self._request("trigger_media_input_action", name=target_action_source, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")

                # Chờ 100ms để OBS decoder nạp frame 1 của Action Video đè lên màn hình
                await asyncio.sleep(0.1)

                # 2. Sau khi Action Video đã che màn hình, mới ân Nguồn Video Nền Idle (Triệt tiêu 100% chớp nháy)
                idle_candidates = [target_idle_source, idle_name, IDLE_SOURCE_NAME] + [f"Idle_Source_{i}" for i in range(1, 5)]
                for isrc in idle_candidates:
                    iid = await self._get_scene_item_id(isrc)
                    if iid is not None:
                        with contextlib.suppress(Exception):
                            await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=iid, enabled=False)
                            await self._request("trigger_media_input_action", name=isrc, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PAUSE")
            else:
                # 1. Bật Video Nền Idle lên trước ở phía dưới
                if idle_item_id is not None:
                    await self._request(
                        "set_scene_item_enabled",
                        scene_name=SCENE_NAME,
                        item_id=idle_item_id,
                        enabled=True,
                    )
                    with contextlib.suppress(Exception):
                        await self._request("trigger_media_input_action", name=target_idle_source, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")

                # Chờ 100ms để Nguồn Video Nền sẵn sàng render frame bên dưới
                await asyncio.sleep(0.1)

                # 2. Tắt Action Video sau khi Video Nền đã hiển thị sẵn sàng
                if action_item_id is not None:
                    await self._request(
                        "set_scene_item_enabled",
                        scene_name=SCENE_NAME,
                        item_id=action_item_id,
                        enabled=False,
                    )
                with contextlib.suppress(Exception):
                    await self._request("trigger_media_input_action", name=target_action_source, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP")

        # Studio Mode
        with contextlib.suppress(Exception):
            sm_resp = await self._request("get_studio_mode_enabled")
            if getattr(sm_resp, "studio_mode_enabled", False):
                await self._request("trigger_studio_mode_transition")
                LOGGER.info("[OBS Studio Mode] Tu dong Transition tu Preview sang Program")

    def _resolve_real_source_name(self, preferred_name: str, fallback_default: str) -> str:
        inputs = getattr(self, "existing_inputs", [])
        if not inputs or self.mock_mode:
            return preferred_name or fallback_default
        if preferred_name in inputs:
            return preferred_name
        if fallback_default in inputs:
            return fallback_default
        return inputs[0]

    async def play_action(self, video_path: Path, sound_path: Path | None = None, target_char: str = "char1") -> None:
        video_path = resolve_existing_media_path(video_path)
        if not self.mock_mode and not video_path.is_file():
            LOGGER.warning("Chua tim thay file video/anh: %s", video_path)

        idle_name, action_name = self._get_sources_for_target(target_char)
        target_action_source = self._resolve_real_source_name(action_name, ACTION_SOURCE_NAME)

        LOGGER.info("[OBS] Phat action video (%s): %s tren Nguon %s", target_char, video_path.name, target_action_source)
        if sound_path and sound_path.is_file():
            play_sound_file(sound_path)

        if not self.mock_mode and video_path.is_file():
            clean_path = str(video_path.resolve()).replace("\\", "/")
            is_image = video_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp")
            with contextlib.suppress(Exception):
                await self._request(
                    "set_input_settings",
                    name=target_action_source,
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
        await self._set_action_visible(True, target_char=target_char)

    async def set_idle_video(self, video_path: Path, target_char: str = "char1") -> None:
        video_path = resolve_existing_media_path(video_path)
        idle_name, _ = self._get_sources_for_target(target_char)
        target_idle_source = self._resolve_real_source_name(idle_name, IDLE_SOURCE_NAME)
        LOGGER.info("[OBS] Cau hinh Video Cho (%s): %s tren Nguon %s", target_char, video_path.name, target_idle_source)
        if not self.mock_mode and video_path.is_file():
            clean_path = str(video_path.resolve()).replace("\\", "/")
            is_image = video_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp")
            with contextlib.suppress(Exception):
                await self._request(
                    "set_input_settings",
                    name=target_idle_source,
                    settings={
                        "local_file": clean_path,
                        "file": clean_path,
                        "is_local_file": True,
                        "clear_on_media_end": False,
                        "looping": True,
                    },
                    overlay=True,
                )

    async def stop_action(self, target_char: str = "char1") -> None:
        stop_sound_file()
        LOGGER.info("[OBS] An action video %s (quay ve Idle)", target_char)
        await self._set_action_visible(False, target_char=target_char)

    async def update_queue_text(self, current_job: GiftJob | None, queue_items: list[GiftJob]) -> None:
        lines: list[str] = []
        if current_job:
            ctag = CHAR_SHORT_TAGS.get(current_job.target_char, f"[{current_job.target_char}]")
            lines.append(f"🎬 ĐANG PHÁT: {current_job.gift_name.title()} {ctag}")
        else:
            lines.append("🎬 ĐANG PHÁT: (Chờ quà...)")

        if queue_items:
            lines.append(f"⏳ HÀNG CHỜ ({len(queue_items)}):")
            for idx, job in enumerate(queue_items[:5], 1):
                ctag = CHAR_SHORT_TAGS.get(job.target_char, f"[{job.target_char}]")
                lines.append(f"  {idx}. {job.gift_name.title()} {ctag}")
            if len(queue_items) > 5:
                lines.append(f"  ... và {len(queue_items) - 5} món nữa")
        else:
            lines.append("⏳ HÀNG CHỜ: Trống")

        text_content = "\n".join(lines)

        try:
            with open(QUEUE_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(text_content)
        except Exception:
            pass

        if ENABLE_QUEUE_TEXT_SOURCE and not self.mock_mode:
            with contextlib.suppress(Exception):
                await self._request(
                    "set_input_settings",
                    name=QUEUE_TEXT_SOURCE_NAME,
                    settings={"text": text_content},
                    overlay=True,
                )


def get_video_duration(video_path: Path) -> float:
    """Lay duration bang ffprobe; neu file khong ton tai thi fallback 0.5s de khong nghien hang cho."""
    if not video_path.is_file():
        return 0.5

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

        action_target = mapping[0]
        priority = int(mapping[1])
        sound_filename = mapping[2] if len(mapping) > 2 else ""
        target_char = str(mapping[3]) if len(mapping) > 3 else "char1"

        video_files, resolved_sound_fn, action_name = resolve_gift_action_media(action_target, sound_filename)
        filename = random.choice([v for v in video_files if v]) if video_files else ""

        p = Path(filename)
        video_path = p if p.is_absolute() else (VIDEO_DIRECTORY / filename)
        resolved_path = resolve_existing_media_path(video_path)

        if not resolved_path.is_file():
            LOGGER.warning("⚠️ CHÚ Ý: File media cho quà '%s' chưa tồn tại trên ổ đĩa: %s", gift_name, video_path)

        resolved_sound_path: Path | None = None
        if resolved_sound_fn:
            sp = Path(resolved_sound_fn)
            sound_path = sp if sp.is_absolute() else (VIDEO_DIRECTORY / resolved_sound_fn)
            resolved_sound_path = resolve_existing_sound_path(sound_path)
            if not resolved_sound_path.is_file():
                LOGGER.warning("⚠️ CHÚ Ý: File âm thanh cho quà '%s' chưa tồn tại: %s", gift_name, sound_path)

        job = GiftJob(gift_name, resolved_path, priority, resolved_sound_path, target_char)
        await self.queue.put(job)
        if len(video_files) > 1:
            LOGGER.info("Them vao queue [%s - Random %d điệu]: %s -> %s (priority=%s, target=%s, sound=%s)", action_name, len(video_files), gift_name, resolved_path.name, priority, target_char, resolved_sound_path.name if resolved_sound_path else "None")
        else:
            LOGGER.info("Them vao queue [%s]: %s -> %s (priority=%s, target=%s, sound=%s)", action_name, gift_name, resolved_path.name, priority, target_char, resolved_sound_path.name if resolved_sound_path else "None")
        await self.update_queue_display()

    async def update_queue_display(self) -> None:
        queue_items = self.queue.get_items()
        await self.obs.update_queue_text(self.current_job, queue_items)

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

        await self.update_queue_display()

        try:
            await self.obs.play_action(job.file_path, sound_path=job.sound_path, target_char=job.target_char)
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
            stop_sound_file()
            self._current_interrupt = None
            self.current_job = None
            self.current_job_start_time = 0.0
            self.current_job_duration = 0.0
            await self.update_queue_display()
            with contextlib.suppress(Exception):
                await self.obs.stop_action(target_char=job.target_char)

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
            with contextlib.suppress(Exception):
                await self.obs.set_idle_video(IDLE_VIDEO_PATH_1, "char1")
                await self.obs.set_idle_video(IDLE_VIDEO_PATH_2, "char2")
                await self.obs.set_idle_video(IDLE_VIDEO_PATH_3, "char3")
                await self.obs.set_idle_video(IDLE_VIDEO_PATH_4, "char4")
            await self.update_queue_display()
        except Exception as exc:
            LOGGER.error("Auto-setup OBS khi khoi dong: %s", exc)

        worker_task = asyncio.create_task(self.worker())
        LOGGER.info("Tien trinh xu ly Hang Cho (Worker Task) da san sang hoat dong!")

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

