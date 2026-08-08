"""Pure TikTok event-rule parsing and matching helpers.

This module intentionally has no dependency on the runtime, OBS, TikTokLive,
or configuration files so rule behavior can evolve and be tested in isolation.
"""

from __future__ import annotations

from typing import Any


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


def trigger_action_label(
    event_type: str,
    sender: str,
    event_label: str,
    count: int = 1,
    diamonds: int = 0,
    event_value: str = "",
) -> str:
    """Build audience-facing copy for the currently playing TikTok event."""
    event_name = str(event_type or "gift").strip().lower()
    viewer = str(sender or "Người xem").strip()
    label = str(event_label or TRIGGER_EVENT_LABELS.get(event_name, "Sự kiện TikTok")).strip()
    if event_name == "gift":
        count_text = f" {max(1, int(count or 1))}x"
        diamond_text = f" (💎{int(diamonds)})" if int(diamonds or 0) > 0 else ""
        return f"🎁 {viewer} đã tặng{count_text} {label.title()}{diamond_text}"
    if event_name == "like":
        return f"❤️ {viewer} đã thả {max(1, int(count or 1))} lượt thích"
    if event_name == "comment":
        content = str(event_value or label).strip()
        return f"💬 {viewer} đã bình luận: {content}"
    copy = {
        "follow": ("➕", "đã theo dõi kênh"),
        "share": ("↗️", "đã chia sẻ LIVE"),
        "join": ("👋", "đã vào phòng LIVE"),
        "subscribe": ("⭐", "đã đăng ký LIVE"),
    }
    icon, action = copy.get(event_name, ("⚡", f"đã kích hoạt {label}"))
    return f"{icon} {viewer} {action}"


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
