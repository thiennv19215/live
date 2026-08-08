"""Reusable media-catalog value objects and parsing helpers."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass
class ActionPreset:
    id: str
    name: str
    videos: list[str]
    sound_filename: str = ""


def parse_media_references(value: str | list[str] | Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    item = str(value).strip()
    return [item] if item else []


def select_random_media_reference(value: str | list[str] | Any) -> str:
    references = parse_media_references(value)
    return random.choice(references) if references else ""
