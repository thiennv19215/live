import logging
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tiktok_obs_controller as core
import tiktok_obs_gui as gui
import tiktok_obs_gui_mapping as mapping
import tiktok_obs_gui_settings as settings
import tiktok_obs_gui_widgets as widgets


class TestGuiRefactor(unittest.TestCase):
    def test_moved_modules_keep_runtime_dependencies(self) -> None:
        self.assertIs(mapping.logging, logging)
        self.assertIs(settings.logging, logging)
        self.assertIs(settings.time, time)

    def test_gui_facade_preserves_previous_exports(self) -> None:
        names = (
            "CARD_HOVER",
            "CHAR_DISPLAY_MAP",
            "CHAR_SHORT_TAGS",
            "CHAR_VALUE_MAP",
            "TEXT_DARK",
            "ToolTip",
            "get_char_display_name",
            "get_char_value_from_display",
        )
        for name in names:
            self.assertIs(getattr(gui, name), getattr(widgets, name))

    def test_mapping_update_no_longer_fails_while_logging(self) -> None:
        owner = SimpleNamespace(deck_buttons={})
        with (
            patch.dict(core.GIFT_MAPPING, {}, clear=True),
            patch.object(core, "save_gift_mapping") as save_mapping,
        ):
            mapping.GiftMappingMixin.update_card_mapping(owner, "rose", "rose.mp4", 1)
            self.assertEqual(core.GIFT_MAPPING["rose"], ("rose.mp4", 1, "", "main"))
            save_mapping.assert_called_once()

    def test_remove_character_confirmation_can_use_monotonic_clock(self) -> None:
        original_count = core.CHARACTER_COUNT
        owner = SimpleNamespace(
            _remove_character_armed_until=0.0,
            remove_character_button=None,
        )
        try:
            core.set_character_count(2)
            settings.ObsSettingsMixin.remove_last_character(owner)
            self.assertGreater(owner._remove_character_armed_until, time.monotonic())
        finally:
            core.set_character_count(original_count)


if __name__ == "__main__":
    unittest.main()
