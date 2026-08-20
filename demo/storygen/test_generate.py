"""The gate the sandbox loop grades: red before the patch, green after it.

sys.path is extended so the suite runs both from inside this directory and by
file path from the repository root; the tree is standalone by design and is not
an importable package.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate


class TestModelIsServed(unittest.TestCase):
    def test_model_is_not_a_retired_identifier(self) -> None:
        self.assertNotIn(
            generate.MODEL,
            generate.RETIRED_MODELS,
            f"{generate.MODEL} was shut down on 2026-06-01; migrate to gemini-3.5-flash",
        )

    def test_main_succeeds_on_a_served_model(self) -> None:
        self.assertEqual(generate.main(), 0)


if __name__ == "__main__":
    unittest.main()
