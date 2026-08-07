import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tiktok_obs_controller as core


class TestTriggerRuleHelpers(unittest.TestCase):
    def test_trigger_keys_are_backward_compatible_with_gifts(self) -> None:
        self.assertEqual(core.make_trigger_key("gift", "Rose"), "rose")
        self.assertEqual(core.parse_trigger_key("rose"), ("gift", "rose"))
        self.assertEqual(core.make_trigger_key("follow"), "@follow:*")
        self.assertEqual(core.parse_trigger_key("@follow:*"), ("follow", ""))

    def test_comment_and_like_conditions_match(self) -> None:
        self.assertTrue(core.trigger_matches("@comment:xin chào", "comment", "Bạn ơi XIN CHÀO nhé"))
        self.assertFalse(core.trigger_matches("@comment:xin chào", "comment", "tạm biệt"))
        self.assertTrue(core.trigger_matches("@like:10", "like", count=10))
        self.assertFalse(core.trigger_matches("@like:10", "like", count=9))

    def test_trigger_rule_metadata_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "gift_config.json"
            mapping = {"@comment:hello": ("action_hello", 2, "", "main", 8.5, False)}
            with patch.object(core, "CONFIG_FILE", config):
                core.save_gift_mapping(mapping)
                loaded = core.load_gift_mapping()
            self.assertEqual(loaded["@comment:hello"][0], "action_hello")
            self.assertEqual(core.mapping_cooldown(loaded["@comment:hello"]), 8.5)
            self.assertFalse(core.mapping_enabled(loaded["@comment:hello"]))


class TestTikTokEventRouting(unittest.IsolatedAsyncioTestCase):
    async def test_comment_rule_enqueues_action_and_respects_cooldown(self) -> None:
        preset = core.ActionPreset("action_hello", "Hello", ["hello.mp4"], "")
        mapping = {"@comment:hello": ("action_hello", 2, "", "main", 30, True)}
        with patch.object(core, "ACTION_PRESETS", {preset.id: preset}), patch.object(core, "GIFT_MAPPING", mapping):
            app = core.TikTokObsApp(mock_mode=True, enable_tiktok=False, enable_obs=False)
            first = await app.trigger_tiktok_event("comment", "say HELLO now", sender="Alice")
            second = await app.trigger_tiktok_event("comment", "hello again", sender="Alice")
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        queued = app.queue.get_items()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].event_type, "comment")
        self.assertEqual(queued[0].sender, "Alice")

    async def test_disabled_rule_is_ignored(self) -> None:
        preset = core.ActionPreset("action_follow", "Follow", ["follow.mp4"], "")
        mapping = {"@follow:*": ("action_follow", 1, "", "main", 0, False)}
        with patch.object(core, "ACTION_PRESETS", {preset.id: preset}), patch.object(core, "GIFT_MAPPING", mapping):
            app = core.TikTokObsApp(mock_mode=True, enable_tiktok=False, enable_obs=False)
            matched = await app.trigger_tiktok_event("follow", sender="Bob")
        self.assertEqual(matched, 0)
        self.assertEqual(app.queue.get_items(), [])


if __name__ == "__main__":
    unittest.main()
