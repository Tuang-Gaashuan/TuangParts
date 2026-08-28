# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warehouse.settings import DEFAULT_SETTINGS, chat_completions_url


class DefaultAiSettingsTests(unittest.TestCase):
    def test_default_ai_has_no_embedded_credential(self):
        ai = DEFAULT_SETTINGS["ai"]
        self.assertEqual(ai["base_url"], "https://api.deepseek.com")
        self.assertEqual(ai["api_key"], "")
        self.assertEqual(ai["model"], "deepseek-chat")

    def test_default_base_url_resolves_to_openai_compatible_endpoint(self):
        self.assertEqual(
            chat_completions_url("https://api.deepseek.com"),
            "https://api.deepseek.com/v1/chat/completions",
        )


if __name__ == "__main__":
    unittest.main()
