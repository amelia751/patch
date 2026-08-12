"""Fixture test suite: green on the baseline, red on an invented model id."""

from __future__ import annotations

import unittest

from image_service import client
from image_service.provider import SUPPORTED_MODEL_IDS


class RenderTest(unittest.TestCase):
    def test_configured_model_is_supported(self):
        self.assertIn(client.MODEL_ID, SUPPORTED_MODEL_IDS)

    def test_render_returns_descriptor_for_configured_model(self):
        descriptor = client.render("a small red boat")
        self.assertEqual(descriptor["model"], client.MODEL_ID)
        self.assertEqual(descriptor["prompt"], "a small red boat")


if __name__ == "__main__":
    unittest.main()
