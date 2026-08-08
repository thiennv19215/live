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
from collections import deque
import contextlib
import ctypes
import logging
import os
import random
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent,
    ConnectEvent,
    DisconnectEvent,
    FollowEvent,
    GiftEvent,
    JoinEvent,
    LikeEvent,
    ShareEvent,
    SubNotifyEvent,
)
from obsws_python import ReqClient
from obsws_python.error import OBSSDKTimeoutError
from websocket import WebSocketConnectionClosedException, WebSocketTimeoutException

from tiktok_overlay import LocalOverlayServer


# ============================== Cau hinh ===============================
TIKTOK_USERNAME = "your_tiktok_username"
OBS_HOST = "127.0.0.1"
OBS_PORT = 4455
OBS_PASSWORD = "your_obs_websocket_password"
SCENE_NAME = "Main Scene"

IDLE_SOURCE_NAME = "Idle_Source"
ACTION_SOURCE_NAME = "Action_Source"
APP_DIRECTORY = Path(
    os.environ.get("TIKTOK_LIVE_DATA_DIR")
    or (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent)
).resolve()
VIDEO_DIRECTORY = APP_DIRECTORY / "videos"
IDLE_VIDEO_PATH_1 = VIDEO_DIRECTORY / "idle_loop_1.mp4"
IDLE_VIDEO_PATH_2 = VIDEO_DIRECTORY / "idle_loop_2.mp4"
IDLE_VIDEO_PATH_3 = VIDEO_DIRECTORY / "idle_loop_3.mp4"
IDLE_VIDEO_PATH_4 = VIDEO_DIRECTORY / "idle_loop_4.mp4"
IDLE_VIDEO_PATH = IDLE_VIDEO_PATH_1
ACTION_DEFAULT_DURATION = 10.0
# Give the overlay/decoder a short idle window before the next queued action.
QUEUE_ACTION_COOLDOWN = 2.0
TIKTOK_RECONNECT_DELAY = 5.0
OBS_RECONNECT_DELAY = 3.0

import json

OBS_CONFIG_FILE = APP_DIRECTORY / "obs_config.json"


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON without leaving a partially-written configuration file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(3):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.05)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def media_reference(path_value: str | Path) -> str:
    """Prefer a portable path relative to the managed videos directory."""
    raw = str(path_value).strip()
    if not raw:
        return ""
    path = Path(raw)
    try:
        return str(path.resolve().relative_to(VIDEO_DIRECTORY.resolve()))
    except (OSError, ValueError):
        return raw


def resolve_configured_media_path(path_value: str | Path) -> Path:
    path = Path(str(path_value))
    return path if path.is_absolute() else VIDEO_DIRECTORY / path


def load_obs_config() -> dict[str, Any]:
    default_cfg = {
        "tiktok_username": "your_tiktok_username",
        "obs_host": "127.0.0.1",
        "obs_port": 4455,
        "obs_password": "your_obs_websocket_password",
        "scene_name": "Main Scene",
        "idle_source_name": "Idle_Source",
        "action_source_name": "Action_Source",
        "character_count": 1,
        "output_ratio": "9:16",
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
    atomic_write_json(OBS_CONFIG_FILE, config)


_saved_obs_cfg = load_obs_config()
TIKTOK_USERNAME = str(_saved_obs_cfg.get("tiktok_username", TIKTOK_USERNAME))
OBS_HOST = str(_saved_obs_cfg.get("obs_host", OBS_HOST))
OBS_PORT = int(_saved_obs_cfg.get("obs_port", OBS_PORT))
OBS_PASSWORD = str(_saved_obs_cfg.get("obs_password", OBS_PASSWORD))
SCENE_NAME = str(_saved_obs_cfg.get("scene_name", SCENE_NAME))
IDLE_SOURCE_NAME = str(_saved_obs_cfg.get("idle_source_name", IDLE_SOURCE_NAME))
ACTION_SOURCE_NAME = str(_saved_obs_cfg.get("action_source_name", ACTION_SOURCE_NAME))
OUTPUT_RATIO = str(_saved_obs_cfg.get("output_ratio", "9:16"))
IDLE_VIDEO_MUTED = bool(_saved_obs_cfg.get("idle_video_muted", False))
CHARACTER_COUNT = 1
_saved_idle_paths = _saved_obs_cfg.get("idle_video_paths", {})
_has_dynamic_idle_paths = "idle_video_paths" in _saved_obs_cfg and isinstance(_saved_idle_paths, dict)
IDLE_VIDEO_PATHS: dict[int, Path] = {}
for _idx in range(1, CHARACTER_COUNT + 1):
    _legacy_path = _saved_obs_cfg.get(f"idle_video_path_{_idx}")
    if _has_dynamic_idle_paths:
        _configured_path = _saved_idle_paths.get(str(_idx), VIDEO_DIRECTORY / f"__unassigned_idle_{_idx}__.mp4")
    else:
        _configured_path = _legacy_path or (VIDEO_DIRECTORY / f"idle_loop_{_idx}.mp4")
    IDLE_VIDEO_PATHS[_idx] = resolve_configured_media_path(_configured_path)
IDLE_VIDEO_PATH_1 = IDLE_VIDEO_PATHS.get(1, IDLE_VIDEO_PATH_1)
IDLE_VIDEO_PATH_2 = IDLE_VIDEO_PATHS.get(2, IDLE_VIDEO_PATH_2)
IDLE_VIDEO_PATH_3 = IDLE_VIDEO_PATHS.get(3, IDLE_VIDEO_PATH_3)
IDLE_VIDEO_PATH_4 = IDLE_VIDEO_PATHS.get(4, IDLE_VIDEO_PATH_4)
IDLE_VIDEO_PATH = IDLE_VIDEO_PATH_1


def get_character_ids() -> list[str]:
    return [f"char{idx}" for idx in range(1, CHARACTER_COUNT + 1)]


def get_idle_video_path(target: int | str) -> Path:
    raw = str(target).lower().strip().removeprefix("char")
    try:
        idx = int(raw)
    except ValueError:
        idx = 1
    return IDLE_VIDEO_PATHS.get(idx, VIDEO_DIRECTORY / f"idle_loop_{idx}.mp4")


def set_idle_video_path(target: int | str, path: Path) -> None:
    global IDLE_VIDEO_PATH, IDLE_VIDEO_PATH_1, IDLE_VIDEO_PATH_2, IDLE_VIDEO_PATH_3, IDLE_VIDEO_PATH_4
    raw_target = str(target).lower().strip()
    idx = 1 if raw_target in ("main", "idle", "background") else int(raw_target.removeprefix("char"))
    IDLE_VIDEO_PATHS[idx] = Path(path)
    if idx == 1:
        IDLE_VIDEO_PATH = IDLE_VIDEO_PATH_1 = Path(path)
    elif idx == 2:
        IDLE_VIDEO_PATH_2 = Path(path)
    elif idx == 3:
        IDLE_VIDEO_PATH_3 = Path(path)
    elif idx == 4:
        IDLE_VIDEO_PATH_4 = Path(path)


def set_character_count(count: int) -> None:
    global CHARACTER_COUNT, CHAR_SHORT_TAGS
    CHARACTER_COUNT = max(1, int(count))
    for idx in range(1, CHARACTER_COUNT + 1):
        IDLE_VIDEO_PATHS.setdefault(idx, VIDEO_DIRECTORY / f"idle_loop_{idx}.mp4")
    CHAR_SHORT_TAGS = {f"char{idx}": f"[NV {idx}]" for idx in range(1, CHARACTER_COUNT + 1)}
    CHAR_SHORT_TAGS["all"] = "[Tat ca]"

QUEUE_TEXT_SOURCE_NAME = "Queue_Text_Source"
ENABLE_QUEUE_TEXT_SOURCE = False  # Đặt False nếu chỉ muốn OBS phát Video hiệu ứng khi có quà, không hiện Text Hàng chờ
QUEUE_FILE_PATH = APP_DIRECTORY / "queue_status.txt"

CHAR_SHORT_TAGS = {f"char{idx}": f"[NV {idx}]" for idx in range(1, CHARACTER_COUNT + 1)}
CHAR_SHORT_TAGS["all"] = "[Tất cả]"

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
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [x.strip() for x in val.split(",") if x.strip()]
    item = str(val).strip()
    return [item] if item else []


def select_random_video_filename(val: str | list[str] | Any) -> str:
    """Chon ngau nhien 1 file video tu danh sach cac file media duoc gan cho qua."""
    files = parse_video_filenames(val)
    valid_files = [f for f in files if f]
    return random.choice(valid_files) if valid_files else ""


def load_action_presets() -> dict[str, ActionPreset]:
    presets: dict[str, ActionPreset] = {}
    data: dict[str, Any] = DEFAULT_ACTION_PRESETS.copy()
    if ACTION_PRESETS_FILE.is_file():
        try:
            with open(ACTION_PRESETS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict) and isinstance(loaded.get("actions"), dict):
                    # Version 2 is authoritative so actions can also be deleted.
                    data = loaded["actions"]
                elif isinstance(loaded, dict):
                    # Legacy files stored presets directly at the root.
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
    data: dict[str, dict[str, Any]] = {}
    for aid, preset in presets.items():
        if isinstance(preset, ActionPreset):
            data[aid] = {
                "name": preset.name,
                "videos": [media_reference(item) for item in preset.videos if item],
                "sound_filename": media_reference(preset.sound_filename) if preset.sound_filename else "",
            }
        elif isinstance(preset, dict):
            data[aid] = {
                "name": str(preset.get("name", aid)),
                "videos": [media_reference(item) for item in parse_video_filenames(preset.get("videos", [])) if item],
                "sound_filename": media_reference(preset.get("sound_filename", "")) if preset.get("sound_filename") else "",
            }
    atomic_write_json(ACTION_PRESETS_FILE, {"version": 2, "actions": data})


ACTION_PRESETS = load_action_presets()

DEFAULT_GIFT_MAPPING: dict[str, tuple[str, int, str, str]] = {
    "rose": ("action_dance_rose", 1, "", "main"),
    "doughnut": ("action_funny_doughnut", 2, "", "main"),
    "perfume": ("action_funny_doughnut", 2, "", "main"),
    "tiktok": ("action_dance_tiktok", 3, "", "main"),
    "lion": ("action_lion_transform", 5, "", "main"),
}

SUPPORTED_TRIGGER_EVENTS = {"gift", "comment", "follow", "share", "like", "join", "subscribe"}
TRIGGER_EVENT_LABELS = {
    "gift": "Quà tặng",
    "comment": "Bình luận",
    "follow": "Theo dõi",
    "share": "Chia sẻ live",
    "like": "Lượt thích",
    "join": "Vào phòng live",
    "subscribe": "Đăng ký LIVE",
}


def make_trigger_key(event_type: str, condition: str = "") -> str:
    event_name = str(event_type or "gift").strip().lower()
    if event_name not in SUPPORTED_TRIGGER_EVENTS:
        raise ValueError(f"Loại sự kiện TikTok không được hỗ trợ: {event_name}")
    normalized = str(condition).strip().lower()
    if event_name == "gift":
        if not normalized:
            raise ValueError("Quà tặng cần có tên quà")
        return normalized
    if event_name == "comment" and not normalized:
        raise ValueError("Sự kiện bình luận cần có từ khóa")
    if event_name == "like":
        try:
            normalized = str(max(1, int(normalized or "1")))
        except ValueError as exc:
            raise ValueError("Ngưỡng lượt thích phải là số") from exc
    return f"@{event_name}:{normalized or '*'}"


def parse_trigger_key(trigger_key: str) -> tuple[str, str]:
    key = str(trigger_key).strip().lower()
    if key.startswith("@") and ":" in key:
        event_type, condition = key[1:].split(":", 1)
        if event_type in SUPPORTED_TRIGGER_EVENTS:
            return event_type, "" if condition == "*" else condition
    return "gift", key


def trigger_event_label(event_type: str, condition: str = "") -> str:
    label = TRIGGER_EVENT_LABELS.get(event_type, event_type.title())
    if event_type == "gift":
        return f"Quà: {condition.title()}"
    if event_type == "comment":
        return f'Bình luận chứa: "{condition}"'
    if event_type == "like":
        return f"Ít nhất {condition or '1'} lượt thích"
    return label


def trigger_matches(trigger_key: str, event_type: str, value: str = "", count: int = 1) -> bool:
    rule_type, condition = parse_trigger_key(trigger_key)
    if rule_type != str(event_type).strip().lower():
        return False
    normalized_value = str(value).strip().lower()
    if rule_type == "gift":
        return normalized_value == condition
    if rule_type == "comment":
        return bool(condition) and condition in normalized_value
    if rule_type == "like":
        return int(count or 0) >= int(condition or "1")
    return True


def mapping_cooldown(mapping: tuple[Any, ...]) -> float:
    try:
        return max(0.0, float(mapping[4])) if len(mapping) > 4 else 0.0
    except (TypeError, ValueError):
        return 0.0


def mapping_enabled(mapping: tuple[Any, ...]) -> bool:
    return bool(mapping[5]) if len(mapping) > 5 else True


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
                if isinstance(data, dict) and isinstance(data.get("mappings"), list):
                    entries = (
                        (str(item.get("gift_name", "")), item)
                        for item in data["mappings"]
                        if isinstance(item, dict)
                    )
                elif isinstance(data, dict):
                    entries = data.items()
                else:
                    entries = []

                for k, v in entries:
                    raw_key = str(k).lower().strip()
                    if not raw_key:
                        continue
                    if isinstance(v, dict):
                        event_type = str(v.get("event_type", "gift")).strip().lower()
                        condition = str(v.get("condition", raw_key)).strip()
                        trigger_key = make_trigger_key(event_type, condition) if event_type != "gift" else raw_key
                        raw_fn = v.get("action_id", v.get("action", ""))
                        prio = int(v.get("priority", 1))
                        sound_fn = str(v.get("sound_override", v.get("sound", "")))
                        target = str(v.get("target", "main"))
                        cooldown = max(0.0, float(v.get("cooldown_seconds", 0) or 0))
                        enabled = bool(v.get("enabled", True))
                    elif isinstance(v, (list, tuple)) and v:
                        trigger_key = raw_key
                        raw_fn = v[0]
                        prio = int(v[1]) if len(v) > 1 else 1
                        sound_fn = str(v[2]) if len(v) > 2 else ""
                        target = str(v[3]) if len(v) > 3 else "main"
                        cooldown = max(0.0, float(v[4])) if len(v) > 4 else 0.0
                        enabled = bool(v[5]) if len(v) > 5 else True
                    else:
                        continue
                    if isinstance(raw_fn, list):
                        fn = ", ".join(str(x).strip() for x in raw_fn if str(x).strip())
                    else:
                        fn = str(raw_fn).strip()
                    res[trigger_key] = (fn, prio, sound_fn, target, cooldown, enabled)
                return res
        except Exception:
            pass
    return DEFAULT_GIFT_MAPPING.copy()


def save_gift_mapping(mapping: dict[str, Any]) -> None:
    items = []
    for k, v in mapping.items():
        trigger_key = str(k).lower().strip()
        if not trigger_key:
            continue
        event_type, condition = parse_trigger_key(trigger_key)
        action_value = str(v[0]).strip()
        # A preset id is portable by definition. Legacy direct media mappings
        # remain portable until the backend migrates them into a preset.
        action_id = action_value if action_value in ACTION_PRESETS else ", ".join(
            media_reference(item) for item in parse_video_filenames(action_value) if item
        )
        items.append(
            {
                "gift_name": trigger_key,
                "event_type": event_type,
                "condition": condition,
                "action_id": action_id,
                "priority": int(v[1]),
                "sound_override": media_reference(v[2]) if len(v) > 2 and v[2] else "",
                "target": str(v[3]) if len(v) > 3 else "main",
                "cooldown_seconds": mapping_cooldown(v),
                "enabled": mapping_enabled(v),
            }
        )
    atomic_write_json(CONFIG_FILE, {"version": 3, "mappings": items})


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
    target_char: str = "main"
    sender: str = "Người xem"
    repeat_count: int = 1
    diamonds: int = 0
    timestamp: str = ""
    event_type: str = "gift"
    event_value: str = ""



class PriorityGiftQueue:
    """Hang doi FIFO: qua den truoc duoc xu ly truoc."""

    def __init__(self) -> None:
        self._items: deque[GiftJob] = deque()
        self._condition = asyncio.Condition()
        self._unfinished_tasks = 0

    async def put(self, job: GiftJob) -> None:
        async with self._condition:
            self._items.append(job)
            self._unfinished_tasks += 1
            self._condition.notify()

    async def get(self) -> GiftJob:
        async with self._condition:
            await self._condition.wait_for(lambda: len(self._items) > 0)
            return self._items.popleft()

    def task_done(self) -> None:
        if self._unfinished_tasks > 0:
            self._unfinished_tasks -= 1

    def clear(self) -> int:
        count = len(self._items)
        self._items.clear()
        self._unfinished_tasks = 0
        return count

    async def clear_async(self) -> int:
        async with self._condition:
            return self.clear()

    def get_items(self) -> list[GiftJob]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)


def should_enqueue_gift_event(event: GiftEvent) -> bool:
    """Return True once per gift, waiting for a streak to finish when needed.

    TikTokLive versions expose streak state in slightly different forms.  Only
    consult repeat/streak flags for streakable gifts; regular gifts must still
    be handled even when a protobuf default exposes ``repeat_end`` as false/0.
    """
    gift = getattr(event, "gift", None)
    if not bool(getattr(gift, "streakable", False)):
        return True

    streaking = getattr(event, "streaking", None)
    if streaking is not None:
        return not bool(streaking)

    repeat_end = getattr(event, "repeat_end", False)
    return bool(repeat_end)


class ObsController:
    """Quan ly ket noi OBS va tu dong reconnect khi request bi loi."""

    def __init__(self, mock_mode: bool = False) -> None:
        self.mock_mode = mock_mode
        self._client: ReqClient | None = None
        self._action_scene_item_id: int | None = None
        self._idle_scene_item_id: int | None = None
        self._scene_items_cache: dict[str, int] | None = None
        self._scene_item_count = 0
        self._scene_item_indices: dict[str, int] = {}
        self.existing_inputs: list[str] = []
        self._lock = asyncio.Lock()
        self._display_lock = asyncio.Lock()
        self._media_config_lock = asyncio.Lock()
        self._connection_generation = 0
        self._connecting = False
        self._looping_action_sources: set[str] = set()
        self.is_connected: bool = False

    async def connect(self, reset_display: bool = True) -> None:
        async with self._lock:
            if self.is_connected:
                return
            if self.mock_mode:
                self.is_connected = True
                LOGGER.info("Da kich hoat Che Do Gia Lap OBS (Mock Mode)")
                return
            self._connecting = True
            try:
                self._client = await asyncio.to_thread(
                    ReqClient,
                    host=OBS_HOST,
                    port=OBS_PORT,
                    password=OBS_PASSWORD,
                    timeout=2,
                )
                scene_list_resp = await asyncio.to_thread(self._client.get_scene_list)
                available_scenes = [sc["sceneName"] for sc in scene_list_resp.scenes]
                if not available_scenes:
                    raise RuntimeError("OBS khong co Scene nao de phat media")

                global SCENE_NAME
                if SCENE_NAME not in available_scenes:
                    try:
                        current_scene_resp = await asyncio.to_thread(self._client.get_current_program_scene)
                        curr_name = current_scene_resp.current_program_scene_name
                        SCENE_NAME = curr_name if curr_name in available_scenes else available_scenes[0]
                    except Exception:
                        SCENE_NAME = available_scenes[0]
                    LOGGER.info("Tu dong chon Scene dang mo trong OBS: '%s'", SCENE_NAME)

                await self.ensure_default_sources_exist()
                await self._validate_obs_setup()

                self._connection_generation += 1
                self.is_connected = True
                LOGGER.info("Da ket noi va xac minh OBS WebSocket v5 tai %s:%s", OBS_HOST, OBS_PORT)

                LOGGER.info("[OBS] Che do don gian: Idle_Source nen chung + Action_Source kich hoat")
            except Exception as exc:
                self.is_connected = False
                client, self._client = self._client, None
                if client is not None:
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(client.disconnect)
                LOGGER.error("OBS chua san sang: %s", exc)
                raise ConnectionError(f"Khong the xac minh Scene/Source OBS: {exc}") from exc
            finally:
                self._connecting = False

        # Run requests after releasing _lock so their reconnect path can call connect().
        if reset_display:
            await self.reset_obs_display_state()

    async def _validate_obs_setup(self) -> None:
        await self._refresh_scene_items_cache()
        scene_items = self._scene_items_cache or {}
        missing = [
            name for name in (IDLE_SOURCE_NAME, ACTION_SOURCE_NAME)
            if name not in self.existing_inputs or name not in scene_items
        ]
        if missing:
            raise RuntimeError("Thieu Media Source bat buoc trong Scene '%s': %s" % (SCENE_NAME, ", ".join(missing)))

    async def reset_obs_display_state(self) -> None:
        """Đưa OBS về video nền chung và ẩn source hành động."""
        if self.mock_mode or not self._client:
            return

        try:
            await self._refresh_scene_items_cache()
            action_id = await self._get_scene_item_id(ACTION_SOURCE_NAME)
            idle_id = await self._get_scene_item_id(IDLE_SOURCE_NAME)
            if action_id is not None:
                await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=action_id, enabled=False)
                with contextlib.suppress(Exception):
                    await self._request("trigger_media_input_action", name=ACTION_SOURCE_NAME, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP")
            if idle_id is not None:
                await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=idle_id, enabled=True)
                await self._request("set_input_mute", name=IDLE_SOURCE_NAME, muted=IDLE_VIDEO_MUTED)
                with contextlib.suppress(Exception):
                    await self._request("trigger_media_input_action", name=IDLE_SOURCE_NAME, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY")
            LOGGER.info("[OBS] Da reset ve 1 video nen chung")
        except Exception as exc:
            LOGGER.debug("reset_obs_display_state exception: %s", exc)

    async def ensure_default_sources_exist(self) -> None:
        if self.mock_mode or not self._client:
            return
        await self._refresh_scene_items_cache()
        scene_items = self._scene_items_cache or {}

        for source_name, enabled in (
            (IDLE_SOURCE_NAME, True),
            (ACTION_SOURCE_NAME, False),
        ):
            if source_name in scene_items:
                continue

            try:
                if source_name in self.existing_inputs:
                    await self._request(
                        "create_scene_item",
                        scene_name=SCENE_NAME,
                        source_name=source_name,
                        enabled=enabled,
                    )
                    LOGGER.info("[OBS] Da dua source co san '%s' vao Scene '%s'", source_name, SCENE_NAME)
                else:
                    await self._request(
                        "create_input",
                        sceneName=SCENE_NAME,
                        inputName=source_name,
                        inputKind="ffmpeg_source",
                        inputSettings={},
                        sceneItemEnabled=enabled,
                    )
                    LOGGER.info("[OBS] Da tu dong tao source '%s' trong Scene '%s'", source_name, SCENE_NAME)
            except Exception as exc:
                raise RuntimeError(
                    "Khong the tu dong tao/gan Media Source '%s' vao Scene '%s': %s"
                    % (source_name, SCENE_NAME, exc)
                ) from exc

            await self._refresh_scene_items_cache()
            scene_items = self._scene_items_cache or {}

    async def ensure_character_layer_sources_exist(
        self,
        character_indices: list[int] | None = None,
        *,
        remove_inactive: bool = False,
    ) -> list[str]:
        """Reconcile layered OBS sources for characters that have real media."""
        if self.mock_mode or not self._client:
            return []

        await self._refresh_scene_items_cache()
        active_indices = sorted({
            idx for idx in (
                character_indices
                if character_indices is not None
                else [
                    candidate
                    for candidate in range(1, CHARACTER_COUNT + 1)
                    if resolve_existing_media_path(get_idle_video_path(candidate)).is_file()
                ]
            )
            if 1 <= idx <= CHARACTER_COUNT
        })

        if remove_inactive:
            active_set = set(active_indices)
            removable: list[tuple[str, int]] = []
            for source_name, item_id in (self._scene_items_cache or {}).items():
                for prefix in ("Idle_Source_", "Action_Source_"):
                    suffix = source_name.removeprefix(prefix)
                    if source_name.startswith(prefix) and suffix.isdigit() and int(suffix) not in active_set:
                        removable.append((source_name, item_id))
                        break
            if not active_indices and "Action_Source_All" in (self._scene_items_cache or {}):
                removable.append(("Action_Source_All", self._scene_items_cache["Action_Source_All"]))
            for source_name, item_id in removable:
                try:
                    await self._request("remove_scene_item", scene_name=SCENE_NAME, item_id=item_id)
                    LOGGER.info("[OBS] Da go source khong co video: %s", source_name)
                except Exception as exc:
                    LOGGER.warning("Khong the go source khong con video %s: %s", source_name, exc)
            if removable:
                await self._refresh_scene_items_cache()

        created: list[str] = []
        source_specs = []
        for idx in active_indices:
            source_specs.append((f"Idle_Source_{idx}", True))
            source_specs.append((f"Action_Source_{idx}", False))
        if active_indices:
            source_specs.append(("Action_Source_All", False))

        for source_name, enabled in source_specs:
            if source_name in (self._scene_items_cache or {}):
                continue
            try:
                if source_name in self.existing_inputs:
                    await self._request(
                        "create_scene_item",
                        scene_name=SCENE_NAME,
                        source_name=source_name,
                        enabled=enabled,
                    )
                else:
                    await self._request(
                        "create_input",
                        sceneName=SCENE_NAME,
                        inputName=source_name,
                        inputKind="ffmpeg_source",
                        inputSettings={},
                        sceneItemEnabled=enabled,
                    )
                created.append(source_name)
            except Exception as exc:
                LOGGER.warning("Khong the tao source layer %s: %s", source_name, exc)

        await self._refresh_scene_items_cache()
        await self.reset_obs_display_state()
        LOGGER.info("[OBS] Da san sang source layer nhan vat; tao/gan moi: %s", ", ".join(created) or "khong co")
        return created

    async def remove_character_layer(self, index: int) -> list[str]:
        """Remove one character's scene items while keeping reusable OBS inputs."""
        if index < 1:
            raise ValueError("Chi so nhan vat khong hop le")
        if self.mock_mode:
            return [f"Idle_Source_{index}", f"Action_Source_{index}"]
        async with self._media_config_lock:
            await self._refresh_scene_items_cache()
            removed: list[str] = []
            for source_name in (f"Idle_Source_{index}", f"Action_Source_{index}"):
                item_id = await self._get_scene_item_id(source_name)
                if item_id is None:
                    continue
                await self._request("remove_scene_item", scene_name=SCENE_NAME, item_id=item_id)
                removed.append(source_name)
            await self._refresh_scene_items_cache()
            return removed

    async def _refresh_scene_items_cache(self) -> dict[str, int]:
        if self.mock_mode or not self._client:
            return {}

        inputs_list = []
        input_list_resp = await self._request("get_input_list")
        raw_inputs = getattr(input_list_resp, "inputs", [])
        for inp in raw_inputs:
            name = inp.get("inputName") or inp.get("input_name") if isinstance(inp, dict) else (getattr(inp, "input_name", None) or getattr(inp, "inputName", None))
            if name:
                inputs_list.append(str(name))

        self.existing_inputs = inputs_list

        cache: dict[str, int] = {}
        resp = await self._request("get_scene_item_list", name=SCENE_NAME)
        raw_items = getattr(resp, "scene_items", []) or getattr(resp, "sceneItems", [])
        self._scene_item_count = len(raw_items)
        indices: dict[str, int] = {}
        for item in raw_items:
            if isinstance(item, dict):
                s_name = item.get("sourceName") or item.get("source_name")
                s_id = item.get("sceneItemId") or item.get("scene_item_id")
                s_index = item.get("sceneItemIndex")
                if s_index is None:
                    s_index = item.get("scene_item_index")
            else:
                s_name = getattr(item, "source_name", None) or getattr(item, "sourceName", None)
                s_id = getattr(item, "scene_item_id", None) or getattr(item, "sceneItemId", None)
                s_index = getattr(item, "scene_item_index", None)
                if s_index is None:
                    s_index = getattr(item, "sceneItemIndex", None)
            if s_name and s_id is not None:
                cache[str(s_name)] = int(s_id)
                if s_index is not None:
                    indices[str(s_name)] = int(s_index)

        self._scene_items_cache = cache
        self._scene_item_indices = indices
        return cache

    async def close(self) -> None:
        async with self._lock:
            await self._drop_connection()

    async def _drop_connection(self) -> None:
        """Disconnect without taking _lock so request recovery cannot self-deadlock."""
        self.is_connected = False
        if self._client is not None and not self.mock_mode:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self._client.disconnect)
        self._client = None
        self._action_scene_item_id = None
        self._idle_scene_item_id = None
        self._scene_items_cache = None
        self._scene_item_count = 0
        self._scene_item_indices = {}
        self.existing_inputs = []

    async def _request(self, method_name: str, **kwargs: Any) -> Any:
        if self.mock_mode:
            return True
        for attempt in range(2):
            try:
                # connect() runs OBS setup while holding its lock. Calling it again
                # from that setup would deadlock, so reuse the live client directly.
                if self._client is None:
                    await self.connect(reset_display=False)
                client = self._client
                if client is None:
                    raise ConnectionError("OBS client chua san sang")
                return await asyncio.to_thread(getattr(client, method_name), **kwargs)
            except (
                ConnectionError,
                OSError,
                EOFError,
                OBSSDKTimeoutError,
                WebSocketConnectionClosedException,
                WebSocketTimeoutException,
            ) as exc:
                LOGGER.warning("OBS socket loi %s: %s", method_name, exc)
                await self._drop_connection()
                if self._connecting:
                    raise ConnectionError(f"Mat ket noi OBS khi dang xac minh: {method_name}") from exc
                if attempt == 0:
                    await asyncio.sleep(OBS_RECONNECT_DELAY)
            except Exception as exc:
                LOGGER.debug("OBS request %s API info: %s", method_name, exc)
                raise
        raise ConnectionError(f"Khong the gui request OBS: {method_name}")

    async def _get_scene_item_id(self, source_name: str) -> int | None:
        if self.mock_mode:
            return 1
        if not hasattr(self, "_scene_items_cache") or self._scene_items_cache is None:
            await self._refresh_scene_items_cache()
        item_id = self._scene_items_cache.get(source_name) if self._scene_items_cache else None
        if item_id is None:
            # Source may have been added after the previous cache refresh.
            await self._refresh_scene_items_cache()
            item_id = self._scene_items_cache.get(source_name) if self._scene_items_cache else None
        return item_id

    def _get_complete_layer_indices(self, scene_items: dict[str, int] | None = None) -> list[int]:
        items = scene_items if scene_items is not None else (self._scene_items_cache or {})
        return [
            idx
            for idx in range(1, CHARACTER_COUNT + 1)
            if f"Idle_Source_{idx}" in items and f"Action_Source_{idx}" in items
        ]

    def _get_sources_for_target(self, target_char: str = "char1") -> tuple[str, str]:
        return (IDLE_SOURCE_NAME, ACTION_SOURCE_NAME)

    async def _move_action_above_idle(self, action_name: str, idle_names: list[str]) -> None:
        action_item_id = await self._get_scene_item_id(action_name)
        if action_item_id is None or self.mock_mode or self._scene_item_count <= 0:
            return
        with contextlib.suppress(Exception):
            await self._request(
                "set_scene_item_index",
                scene_name=SCENE_NAME,
                item_id=action_item_id,
                item_index=self._scene_item_count - 1,
            )

    async def _move_action_behind_idle(self) -> None:
        """Đặt action dưới video nền trong lúc OBS mở và giải mã file mới."""
        action_item_id = await self._get_scene_item_id(ACTION_SOURCE_NAME)
        idle_index = self._scene_item_indices.get(IDLE_SOURCE_NAME)
        if action_item_id is None or idle_index is None or self.mock_mode:
            return
        with contextlib.suppress(Exception):
            await self._request(
                "set_scene_item_index",
                scene_name=SCENE_NAME,
                item_id=action_item_id,
                item_index=max(0, idle_index - 1),
            )

    async def _preload_action_source(self) -> bool:
        """Khởi động action phía sau nền và chờ decoder OBS sẵn sàng."""
        if self.mock_mode:
            return False
        action_item_id = await self._get_scene_item_id(ACTION_SOURCE_NAME)
        if action_item_id is None:
            return False

        await self._move_action_behind_idle()
        await self._request(
            "set_scene_item_enabled",
            scene_name=SCENE_NAME,
            item_id=action_item_id,
            enabled=True,
        )
        await self._request(
            "trigger_media_input_action",
            name=ACTION_SOURCE_NAME,
            action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART",
        )

        deadline = asyncio.get_running_loop().time() + 1.5
        while asyncio.get_running_loop().time() < deadline:
            try:
                status = await self._request("get_media_input_status", name=ACTION_SOURCE_NAME)
                state = str(getattr(status, "media_state", "")).upper()
                if state in {"OBS_MEDIA_STATE_PLAYING", "OBS_MEDIA_STATE_PAUSED"}:
                    LOGGER.info("[OBS] Action da preload xong; chuyen canh khong khung")
                    return True
                if state == "OBS_MEDIA_STATE_ERROR":
                    break
            except Exception as exc:
                LOGGER.warning("[OBS] Khong doc duoc trang thai preload: %s", exc)
                break
            await asyncio.sleep(0.08)

        LOGGER.warning("[OBS] Preload chua san sang sau 1.5s; hien thi action bang co che fallback")
        return False

    async def _set_action_visible(
        self,
        visible: bool,
        target_char: str = "char1",
        *,
        restart_media: bool = True,
    ) -> None:
        """Apply a complete display state, replaying it if a request reconnects mid-sequence."""
        async with self._display_lock:
            for _ in range(3):
                generation = self._connection_generation
                await self._set_action_visible_once(visible, target_char, restart_media=restart_media)
                if self._connection_generation == generation:
                    return
                LOGGER.info("[OBS] Ket noi lai giua luc doi source; ap dung lai toan bo trang thai")
            raise ConnectionError("OBS lien tuc reconnect khi dang doi Action/Idle; khong the xac lap trang thai an toan")

    async def _set_action_visible_once(
        self,
        visible: bool,
        target_char: str = "char1",
        *,
        restart_media: bool = True,
    ) -> None:
        if self.mock_mode:
            LOGGER.info("[MOCK OBS] Set shared action visible = %s", visible)
            return

        action_item_id = await self._get_scene_item_id(ACTION_SOURCE_NAME)
        idle_item_id = await self._get_scene_item_id(IDLE_SOURCE_NAME)
        if visible:
            # Idle_Source được giữ chạy liên tục bên dưới Action_Source để chuyển cảnh mượt 0ms không vệt đen.
            if idle_item_id is not None:
                await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=idle_item_id, enabled=True)
                await self._request("set_input_mute", name=IDLE_SOURCE_NAME, muted=True)
                with contextlib.suppress(Exception):
                    await self._request("trigger_media_input_action", name=IDLE_SOURCE_NAME, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY")
            await self._move_action_above_idle(ACTION_SOURCE_NAME, [IDLE_SOURCE_NAME])
            if action_item_id is not None:
                await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=action_item_id, enabled=True)
            if restart_media:
                with contextlib.suppress(Exception):
                    await self._request("trigger_media_input_action", name=ACTION_SOURCE_NAME, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")
                await asyncio.sleep(0.05)
        else:
            if idle_item_id is not None:
                await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=idle_item_id, enabled=True)
                with contextlib.suppress(Exception):
                    await self._request("trigger_media_input_action", name=IDLE_SOURCE_NAME, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY")
            if action_item_id is not None:
                await self._request("set_scene_item_enabled", scene_name=SCENE_NAME, item_id=action_item_id, enabled=False)
            with contextlib.suppress(Exception):
                await self._request("trigger_media_input_action", name=ACTION_SOURCE_NAME, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP")
            if idle_item_id is not None:
                await self._request("set_input_mute", name=IDLE_SOURCE_NAME, muted=IDLE_VIDEO_MUTED)

    def _resolve_real_source_name(self, preferred_name: str, fallback_default: str) -> str:
        inputs = getattr(self, "existing_inputs", [])
        if self.mock_mode:
            return preferred_name or fallback_default
        if preferred_name in inputs:
            return preferred_name
        if fallback_default in inputs:
            return fallback_default
        raise RuntimeError(
            "Khong tim thay OBS Media Source '%s' hoac '%s'; huy thao tac de tranh ghi nham source"
            % (preferred_name, fallback_default)
        )

    async def play_action(self, video_path: Path, sound_path: Path | None = None, target_char: str = "char1") -> None:
        video_path = resolve_existing_media_path(video_path)
        if not self.mock_mode and not video_path.is_file():
            LOGGER.warning("Chua tim thay file video/anh: %s", video_path)

        if not self.mock_mode:
            # OBS assigns a new scene-item ID when a source is deleted/recreated.
            await self._refresh_scene_items_cache()

        target_action_source = (
            ACTION_SOURCE_NAME
            if self.mock_mode
            else self._resolve_real_source_name(ACTION_SOURCE_NAME, ACTION_SOURCE_NAME)
        )

        LOGGER.info("[OBS] Kich hoat action: %s tren Nguon %s", video_path.name, target_action_source)
        preloaded = False

        if not self.mock_mode and video_path.is_file():
            clean_path = str(video_path.resolve()).replace("\\", "/")
            is_image = video_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp")
            if is_image:
                self._looping_action_sources.add(target_action_source)
            else:
                self._looping_action_sources.discard(target_action_source)
            await self._request(
                "set_input_settings",
                name=target_action_source,
                settings={
                    "local_file": clean_path,
                    "file": clean_path,
                    "restart_on_activate": True,
                    "is_local_file": True,
                    "clear_on_media_end": False,
                    "close_when_inactive": False,
                    "looping": is_image,
                },
                overlay=True,
            )
            await self._verify_input_file(target_action_source, clean_path)
            LOGGER.info("[OBS] Da xac nhan file action tren %s", target_action_source)
            if not is_image:
                preloaded = await self._preload_action_source()
        if sound_path and sound_path.is_file():
            play_sound_file(sound_path)
        await self._set_action_visible(
            True,
            target_char="main",
            restart_media=not preloaded,
        )

    async def wait_for_action_end(self, target_char: str, fallback_duration: float) -> None:
        """Poll OBS playback state, using duration only as a bounded fallback."""
        if self.mock_mode:
            await asyncio.sleep(fallback_duration)
            return

        target_action_source = (
            ACTION_SOURCE_NAME
            if self.mock_mode
            else self._resolve_real_source_name(ACTION_SOURCE_NAME, ACTION_SOURCE_NAME)
        )
        if target_action_source in self._looping_action_sources:
            await asyncio.sleep(fallback_duration)
            return

        timeout = max(fallback_duration + 5.0, fallback_duration * 1.5)
        deadline = asyncio.get_running_loop().time() + timeout
        saw_active_state = False
        active_states = {"OBS_MEDIA_STATE_OPENING", "OBS_MEDIA_STATE_BUFFERING", "OBS_MEDIA_STATE_PLAYING", "OBS_MEDIA_STATE_PAUSED"}
        terminal_states = {"OBS_MEDIA_STATE_ENDED", "OBS_MEDIA_STATE_STOPPED", "OBS_MEDIA_STATE_ERROR"}

        while asyncio.get_running_loop().time() < deadline:
            try:
                status = await self._request("get_media_input_status", name=target_action_source)
                media_state = str(getattr(status, "media_state", "")).upper()
            except Exception as exc:
                LOGGER.warning("[OBS] Khong doc duoc trang thai media %s: %s; dung duration fallback", target_action_source, exc)
                await asyncio.sleep(fallback_duration)
                return

            if media_state in active_states:
                saw_active_state = True
            elif saw_active_state and media_state in terminal_states:
                LOGGER.info("[OBS] Media da ket thuc (%s): %s", media_state, target_action_source)
                return
            await asyncio.sleep(0.15)

        LOGGER.warning("[OBS] Media %s khong vao trang thai ket thuc sau %.1fs; dung watchdog timeout", target_action_source, timeout)

    def _preferred_idle_source(self, target_char: str) -> str:
        return IDLE_SOURCE_NAME

    async def _verify_input_file(self, source_name: str, expected_path: str) -> None:
        response = await self._request("get_input_settings", name=source_name)
        settings = getattr(response, "input_settings", None)
        if not isinstance(settings, dict):
            return
        actual = str(settings.get("local_file") or settings.get("file") or "").replace("\\", "/")
        if actual != expected_path:
            raise RuntimeError(f"OBS khong xac nhan duong dan cho {source_name}: '{actual}'")

    async def set_idle_video(self, video_path: Path, target_char: str = "char1") -> None:
        video_path = resolve_existing_media_path(video_path)
        if not self.mock_mode and not video_path.is_file():
            raise FileNotFoundError(f"Khong tim thay video Idle: {video_path}")
        async with self._media_config_lock:
            if not self.mock_mode:
                await self._refresh_scene_items_cache()
            target_idle_source = (
                IDLE_SOURCE_NAME
                if self.mock_mode
                else self._resolve_real_source_name(IDLE_SOURCE_NAME, IDLE_SOURCE_NAME)
            )
            LOGGER.info("[OBS] Cau hinh video nen chung: %s tren Nguon %s", video_path.name, target_idle_source)
            if self.mock_mode:
                return
            clean_path = str(video_path.resolve()).replace("\\", "/")
            is_image = video_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp")
            await self._request(
                "set_input_settings",
                name=target_idle_source,
                settings={
                    "local_file": clean_path,
                    "file": clean_path,
                    "is_local_file": True,
                    "clear_on_media_end": False,
                    "looping": True,
                    "restart_on_activate": False,
                    "close_when_inactive": False,
                },
                overlay=True,
            )
            await self._verify_input_file(target_idle_source, clean_path)
            await self._request("set_input_mute", name=target_idle_source, muted=IDLE_VIDEO_MUTED)
            LOGGER.info("[OBS] Da xac nhan Video Cho tren %s", target_idle_source)

    async def set_idle_video_muted(self, muted: bool) -> None:
        target_idle_source = (
            IDLE_SOURCE_NAME
            if self.mock_mode
            else self._resolve_real_source_name(IDLE_SOURCE_NAME, IDLE_SOURCE_NAME)
        )
        if self.mock_mode:
            return
        await self._request("set_input_mute", name=target_idle_source, muted=bool(muted))
        LOGGER.info("[OBS] Am thanh video nen: %s", "tat" if muted else "bat")

    async def clear_idle_video(self, target_char: str = "char1") -> None:
        async with self._media_config_lock:
            if not self.mock_mode:
                await self._refresh_scene_items_cache()
            target_idle_source = (
                IDLE_SOURCE_NAME
                if self.mock_mode
                else self._resolve_real_source_name(IDLE_SOURCE_NAME, IDLE_SOURCE_NAME)
            )
            if self.mock_mode:
                return
            await self._request(
                "set_input_settings",
                name=target_idle_source,
                settings={
                    "local_file": "",
                    "file": "",
                    "is_local_file": True,
                },
                overlay=True,
            )
            await self._verify_input_file(target_idle_source, "")
            LOGGER.info("[OBS] Da xoa Video Cho khoi %s", target_idle_source)

    async def sync_all_idle_videos(self) -> dict[str, list[str]]:
        """Đồng bộ một video nền duy nhất vào Idle_Source."""
        result: dict[str, list[str]] = {"synced": [], "skipped": [], "errors": []}
        path = resolve_existing_media_path(get_idle_video_path("main"))
        if not path.is_file():
            result["skipped"].append("main")
            return result
        try:
            await self.set_idle_video(path, "main")
            result["synced"].append("main")
        except Exception as exc:
            result["errors"].append(f"main: {exc}")
        LOGGER.info(
            "[OBS] Dong bo video nen: %s thanh cong, %s chua chon video, %s loi",
            len(result["synced"]),
            len(result["skipped"]),
            len(result["errors"]),
        )
        return result

    async def stop_action(self, target_char: str = "char1") -> None:
        stop_sound_file()
        LOGGER.info("[OBS] Ket thuc action, quay ve video nen")
        await self._set_action_visible(False, target_char="main")

    async def update_queue_text(self, current_job: GiftJob | None, queue_items: list[GiftJob]) -> None:
        lines: list[str] = []
        if current_job:
            count_str = f" (x{current_job.repeat_count})" if current_job.repeat_count > 1 else ""
            lines.append(f"🎬 ĐANG PHÁT: {current_job.gift_name.title()}{count_str} từ {current_job.sender}")
        else:
            lines.append("🎬 ĐANG PHÁT: (Chờ quà...)")

        if queue_items:
            lines.append(f"⏳ HÀNG CHỜ ({len(queue_items)}):")
            for idx, job in enumerate(queue_items[:5], 1):
                c_str = f" (x{job.repeat_count})" if job.repeat_count > 1 else ""
                lines.append(f"  {idx}. {job.sender}: {job.gift_name.title()}{c_str}")
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


_DURATION_CACHE: dict[tuple[str, int, int], float] = {}


def get_video_duration(video_path: Path) -> float:
    """Lay duration bang ffprobe; neu file khong ton tai thi fallback 0.5s de khong nghien hang cho."""
    if not video_path.is_file():
        return 0.5

    if video_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        return 3.0

    cache_key = None
    try:
        resolved = video_path.resolve()
        stat = resolved.stat()
        cache_key = (str(resolved), stat.st_size, stat.st_mtime_ns)
        if cache_key in _DURATION_CACHE:
            return _DURATION_CACHE[cache_key]
    except OSError:
        pass

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
        # ffprobe is launched for every action.  A windowed PyInstaller app
        # would otherwise briefly create a visible console on Windows.
        run_options: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "check": True,
            "timeout": 2.0,
        }
        if os.name == "nt":
            run_options["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, **run_options)
        duration = max(float(result.stdout.strip()), 0.1)
        if cache_key is not None:
            _DURATION_CACHE[cache_key] = duration
        return duration
    except (FileNotFoundError, ValueError, subprocess.SubprocessError, OSError):
        return ACTION_DEFAULT_DURATION


class TikTokObsApp:
    def __init__(
        self,
        mock_mode: bool = False,
        enable_tiktok: bool = False,
        enable_obs: bool = True,
        overlay: LocalOverlayServer | None = None,
    ) -> None:
        self.mock_mode = mock_mode
        self.enable_tiktok = enable_tiktok
        self.enable_obs = enable_obs
        self.queue = PriorityGiftQueue()
        self.gift_history: deque[dict[str, Any]] = deque(maxlen=100)
        self.obs = ObsController(mock_mode=mock_mode)
        self.overlay = overlay
        self._stop_event = asyncio.Event()
        self._current_interrupt: asyncio.Event | None = None
        self._last_job_was_skipped = False
        self._action_sequence_counters: dict[str, int] = {}
        self._trigger_last_fired: dict[str, float] = {}
        self.is_tiktok_connected: bool = False
        self.current_job: GiftJob | None = None
        self.current_job_start_time: float = 0.0
        self.current_job_duration: float = 0.0
        self.client = TikTokLiveClient(unique_id=TIKTOK_USERNAME)
        self.client.add_listener(ConnectEvent, self.on_connect)
        self.client.add_listener(DisconnectEvent, self.on_disconnect)
        self.client.add_listener(GiftEvent, self.on_gift)
        self.client.add_listener(CommentEvent, self.on_comment)
        self.client.add_listener(FollowEvent, self.on_follow)
        self.client.add_listener(ShareEvent, self.on_share)
        self.client.add_listener(LikeEvent, self.on_like)
        self.client.add_listener(JoinEvent, self.on_join)
        self.client.add_listener(SubNotifyEvent, self.on_subscribe)

    async def on_connect(self, _: ConnectEvent) -> None:
        self.is_tiktok_connected = True
        LOGGER.info("Da ket noi TikTok Live: @%s", TIKTOK_USERNAME)

    async def on_disconnect(self, _: DisconnectEvent) -> None:
        self.is_tiktok_connected = False
        LOGGER.warning("TikTok Live da ngat ket noi; se thu ket noi lai")

    @staticmethod
    def _event_sender(event: Any) -> str:
        user_obj = getattr(event, "user", None)
        return str(
            getattr(user_obj, "nickname", None)
            or getattr(user_obj, "unique_id", None)
            or "Người xem"
        )

    async def trigger_tiktok_event(
        self,
        event_type: str,
        value: str = "",
        sender: str = "Người xem",
        count: int = 1,
        diamonds: int = 0,
    ) -> int:
        """Match one TikTok event against saved rules and enqueue every match."""
        now = self.loop_time()
        matched = 0
        rule_matched = False
        for trigger_key, mapping in list(GIFT_MAPPING.items()):
            if not mapping_enabled(mapping) or not trigger_matches(trigger_key, event_type, value, count):
                continue
            rule_matched = True
            cooldown = mapping_cooldown(mapping)
            last_fired = self._trigger_last_fired.get(trigger_key, 0.0)
            if cooldown and now - last_fired < cooldown:
                continue
            self._trigger_last_fired[trigger_key] = now
            display_name = value if event_type == "gift" else trigger_event_label(event_type, value or parse_trigger_key(trigger_key)[1])
            await self.enqueue_gift(
                trigger_key,
                sender=sender,
                repeat_count=count,
                diamonds=diamonds,
                display_name=display_name,
                event_type=event_type,
                event_value=value,
            )
            matched += 1
        if rule_matched and not matched:
            LOGGER.info("Su kien TikTok dang trong cooldown: %s (%s)", event_type, value or "*")
        elif not matched:
            LOGGER.info("Bo qua su kien TikTok chua map: %s (%s)", event_type, value or "*")
        return matched

    @staticmethod
    def loop_time() -> float:
        return asyncio.get_running_loop().time()

    async def on_comment(self, event: CommentEvent) -> None:
        await self.trigger_tiktok_event("comment", str(getattr(event, "content", "")), self._event_sender(event))

    async def on_follow(self, event: FollowEvent) -> None:
        await self.trigger_tiktok_event("follow", sender=self._event_sender(event))

    async def on_share(self, event: ShareEvent) -> None:
        await self.trigger_tiktok_event("share", sender=self._event_sender(event))

    async def on_like(self, event: LikeEvent) -> None:
        await self.trigger_tiktok_event(
            "like",
            sender=self._event_sender(event),
            count=max(1, int(getattr(event, "count", 1) or 1)),
        )

    async def on_join(self, event: JoinEvent) -> None:
        await self.trigger_tiktok_event("join", sender=self._event_sender(event))

    async def on_subscribe(self, event: SubNotifyEvent) -> None:
        await self.trigger_tiktok_event("subscribe", sender=self._event_sender(event))

    async def on_gift(self, event: GiftEvent) -> None:
        if not should_enqueue_gift_event(event):
            return

        gift_name = str(getattr(event.gift, "name", "")).strip().lower()
        sender = self._event_sender(event)
        repeat_count = int(getattr(event, "repeat_count", 1) or 1)
        per_diamond = int(getattr(event.gift, "diamond_count", 0) or 0)
        diamond_count = per_diamond * repeat_count
        await self.trigger_tiktok_event(
            "gift",
            gift_name,
            sender=sender,
            count=repeat_count,
            diamonds=diamond_count,
        )

    async def enqueue_gift(
        self,
        gift_name: str,
        sender: str = "Người xem",
        repeat_count: int = 1,
        diamonds: int = 0,
        video_index: int | None = None,
        display_name: str = "",
        event_type: str = "gift",
        event_value: str = "",
    ) -> None:
        """Them gift vao cuoi queue FIFO; khong ngat video dang phat."""
        import time as _time_mod
        gift_key = gift_name.strip().lower()
        mapping = GIFT_MAPPING.get(gift_key)
        if mapping is None and gift_name in ACTION_PRESETS:
            action_target = gift_name
            priority = 1
            sound_filename = ""
        elif mapping is not None:
            action_target = mapping[0]
            priority = int(mapping[1])
            sound_filename = mapping[2] if len(mapping) > 2 else ""
        else:
            LOGGER.info("Bo qua qua tang chua map: %s", gift_name or "(khong ten)")
            return

        target_char = "main"

        video_files, resolved_sound_fn, action_name = resolve_gift_action_media(action_target, sound_filename)
        media_candidates: list[tuple[str, Path]] = []
        for candidate in video_files:
            if not candidate:
                continue
            candidate_path = Path(candidate)
            video_path = candidate_path if candidate_path.is_absolute() else (VIDEO_DIRECTORY / candidate)
            media_candidates.append((candidate, resolve_existing_media_path(video_path)))

        existing_candidates = [(name, path) for name, path in media_candidates if path.is_file()]
        if video_index is not None and 0 <= video_index < len(existing_candidates):
            filename, resolved_path = existing_candidates[video_index]
        elif existing_candidates:
            seq_idx = self._action_sequence_counters.get(gift_key, 0) % len(existing_candidates)
            filename, resolved_path = existing_candidates[seq_idx]
            self._action_sequence_counters[gift_key] = seq_idx + 1
        elif self.mock_mode and media_candidates:
            v_idx = video_index if (video_index is not None and 0 <= video_index < len(media_candidates)) else 0
            filename, resolved_path = media_candidates[v_idx]
        else:
            missing_files = ", ".join(str(path) for _, path in media_candidates) or "(chưa cấu hình)"
            LOGGER.error("Không thể phát quà '%s': không tìm thấy file media: %s", gift_name, missing_files)
            return

        resolved_sound_path: Path | None = None
        if resolved_sound_fn:
            sp = Path(resolved_sound_fn)
            sound_path = sp if sp.is_absolute() else (VIDEO_DIRECTORY / resolved_sound_fn)
            resolved_sound_path = resolve_existing_sound_path(sound_path)
            if not resolved_sound_path.is_file():
                LOGGER.warning("⚠️ CHÚ Ý: File âm thanh cho quà '%s' chưa tồn tại: %s", gift_name, sound_path)

        timestamp = _time_mod.strftime("%H:%M:%S")
        event_label = display_name or gift_name
        job_id = f"{event_type}_{_time_mod.time_ns()}"
        job = GiftJob(
            gift_name=event_label,
            file_path=resolved_path,
            priority=priority,
            sound_path=resolved_sound_path,
            target_char=target_char,
            sender=sender,
            repeat_count=repeat_count,
            diamonds=diamonds,
            timestamp=timestamp,
            event_type=event_type,
            event_value=event_value,
        )
        await self.queue.put(job)
        self.gift_history.appendleft({
            "id": job_id,
            "gift": event_label,
            "event_type": event_type,
            "event_value": event_value,
            "file": resolved_path.name,
            "priority": priority,
            "sound": resolved_sound_path.name if resolved_sound_path else "",
            "sender": sender,
            "count": repeat_count,
            "diamonds": diamonds,
            "timestamp": timestamp,
            "status": "queued",
        })
        LOGGER.info("⚡ [TRIGGER:%s] %s · %s x%d -> Action [%s]", event_type.upper(), sender, event_label, repeat_count, action_name)
        await self.update_queue_display()

    async def enqueue_trigger(self, trigger_key: str, sender: str = "Người xem") -> bool:
        key = str(trigger_key).strip().lower()
        mapping = GIFT_MAPPING.get(key)
        if mapping is None or not mapping_enabled(mapping):
            return False
        event_type, condition = parse_trigger_key(key)
        display_name = condition if event_type == "gift" else trigger_event_label(event_type, condition)
        count = int(condition or "1") if event_type == "like" else 1
        await self.enqueue_gift(
            key,
            sender=sender,
            repeat_count=count,
            display_name=display_name,
            event_type=event_type,
            event_value=condition,
        )
        return True

    async def enqueue_action_preset(self, preset_id: str, target_char: str = "main") -> bool:
        preset = ACTION_PRESETS.get(preset_id)
        if preset is None:
            LOGGER.error("Khong tim thay Hanh Dong: %s", preset_id)
            return False
        candidates: list[Path] = []
        for filename in preset.videos:
            path = Path(filename)
            if not path.is_absolute():
                path = VIDEO_DIRECTORY / filename
            resolved = resolve_existing_media_path(path)
            if resolved.is_file() or self.mock_mode:
                candidates.append(resolved)
        if not candidates:
            LOGGER.error("Hanh Dong '%s' chua co video hop le", preset.name)
            return False
        sound_path: Path | None = None
        if preset.sound_filename:
            raw_sound = Path(preset.sound_filename)
            if not raw_sound.is_absolute():
                raw_sound = VIDEO_DIRECTORY / preset.sound_filename
            resolved_sound = resolve_existing_sound_path(raw_sound)
            if resolved_sound.is_file():
                sound_path = resolved_sound
        await self.queue.put(
            GiftJob(
                gift_name=preset.name,
                file_path=random.choice(candidates),
                priority=1,
                sound_path=sound_path,
                target_char="main",
            )
        )
        await self.update_queue_display()
        return True

    async def update_queue_display(self) -> None:
        # The Browser Overlay is the complete playback path when OBS output is
        # disabled.  Queue text is an OBS-only feature, and calling it here
        # would otherwise make _request() connect to OBS implicitly.
        if not self.enable_obs:
            return
        queue_items = self.queue.get_items()
        await self.obs.update_queue_text(self.current_job, queue_items)

    def skip_current(self) -> None:
        """Ngat ngay video dang phat de chuyen sang mon tiep theo trong queue."""
        if self._current_interrupt is not None:
            LOGGER.info("Nguoi dung yeu cau Bo Qua (Skip) video hien tai")
            self._current_interrupt.set()

    async def clear_all_playback(self) -> int:
        """Clear pending jobs and wait until the current action returns to idle."""
        cleared = await self.queue.clear_async()
        had_current = self.current_job is not None
        self.skip_current()
        if had_current:
            try:
                await asyncio.wait_for(self._wait_until_idle(), timeout=2.0)
            except asyncio.TimeoutError:
                LOGGER.warning("Action hien tai chua dung xong sau khi xoa hang doi")
        return cleared + int(had_current)

    async def _wait_until_idle(self) -> None:
        while self.current_job is not None:
            await asyncio.sleep(0.01)

    async def _play_job(self, job: GiftJob) -> None:
        interrupt = asyncio.Event()
        obs_playing = False
        self._last_job_was_skipped = False
        self._current_interrupt = interrupt
        self.current_job = job
        self.current_job_start_time = asyncio.get_event_loop().time()
        self.current_job_duration = ACTION_DEFAULT_DURATION
        # Start probing in parallel so playback and Skip react immediately.
        # ffprobe can be slow on first launch in a packaged Windows app.
        duration_task = asyncio.create_task(asyncio.to_thread(get_video_duration, job.file_path))
        interrupt_task = asyncio.create_task(interrupt.wait())

        await self.update_queue_display()

        try:
            if self.overlay:
                next_jobs = self.queue.get_items()
                next_path = next_jobs[0].file_path if next_jobs else None
                count_str = f" {job.repeat_count}x" if job.repeat_count > 1 else " 1x"
                diamond_str = f" (💎{job.diamonds})" if job.diamonds > 0 else ""
                label_text = f"🎁 {job.sender} đã tặng{count_str} {job.gift_name.title()}{diamond_str}"
                if next_path:
                    self.overlay.show_action(job.file_path, sound_path=job.sound_path, label=label_text, preload_path=next_path)
                else:
                    self.overlay.show_action(job.file_path, sound_path=job.sound_path, label=label_text)

            if self.enable_obs:
                try:
                    await self.obs.play_action(job.file_path, sound_path=job.sound_path, target_char=job.target_char)
                    obs_playing = True
                except Exception as exc:
                    if not self.overlay:
                        raise
                    LOGGER.warning("OBS khong phat duoc action; tiep tuc bang Browser Overlay: %s", exc)

            metadata_done, _ = await asyncio.wait(
                {duration_task, interrupt_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if interrupt_task in metadata_done:
                self._last_job_was_skipped = True
                LOGGER.info("Video %s da bi bo qua theo yeu cau nguoi dung", job.gift_name)
                return

            self.current_job_duration = duration_task.result()
            elapsed = max(0.0, asyncio.get_running_loop().time() - self.current_job_start_time)
            remaining_duration = max(0.1, self.current_job_duration - elapsed)
            playback_task = asyncio.create_task(
                self.obs.wait_for_action_end(job.target_char, remaining_duration)
                if obs_playing
                else asyncio.sleep(remaining_duration)
            )
            done, pending = await asyncio.wait(
                {playback_task, interrupt_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in pending:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if interrupt_task in done:
                self._last_job_was_skipped = True
                LOGGER.info("Video %s da bi bo qua theo yeu cau nguoi dung", job.gift_name)
        finally:
            for task in (duration_task, interrupt_task):
                if not task.done():
                    task.cancel()
            stop_sound_file()
            if self.overlay:
                next_jobs = self.queue.get_items()
                next_path = next_jobs[0].file_path if next_jobs else None
                if next_path:
                    self.overlay.show_idle(preload_path=next_path)
                else:
                    self.overlay.show_idle()
            if obs_playing:
                with contextlib.suppress(Exception):
                    await self.obs.stop_action(target_char=job.target_char)
            self._current_interrupt = None
            self.current_job = None
            self.current_job_start_time = 0.0
            self.current_job_duration = 0.0
            with contextlib.suppress(Exception):
                await self.update_queue_display()

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
            if len(self.queue) and not self._last_job_was_skipped and not self._stop_event.is_set():
                LOGGER.info("Cho %.1f giay o video nen truoc action tiep theo", QUEUE_ACTION_COOLDOWN)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=QUEUE_ACTION_COOLDOWN)
                except asyncio.TimeoutError:
                    pass

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
        if self.enable_obs:
            try:
                await self.obs.connect()
                await self.obs.sync_all_idle_videos()
                await self.update_queue_display()
            except Exception as exc:
                LOGGER.error("Auto-setup OBS khi khoi dong: %s", exc)
        else:
            LOGGER.info("Che do TikTok Studio truc tiep: chi phat Browser Overlay, OBS dang tat")

        worker_task = asyncio.create_task(self.worker())
        LOGGER.info("Tien trinh xu ly Hang Cho (Worker Task) da san sang hoat dong!")

        try:
            await self.tiktok_loop()
        finally:
            self._stop_event.set()
            self.skip_current()
            if self.enable_tiktok and not self.mock_mode:
                with contextlib.suppress(Exception):
                    await self.client.disconnect()
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
            cleared = self.queue.clear()
            if cleared:
                LOGGER.info("Da xoa %s mon con lai trong hang cho khi dong app", cleared)
            if self.enable_obs:
                with contextlib.suppress(Exception):
                    await self.obs.update_queue_text(None, [])
                with contextlib.suppress(Exception):
                    await self.obs.reset_obs_display_state()
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
