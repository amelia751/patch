"""Fixture build step: emits dist/manifest.json inside the workspace.

Writing a real artifact is the point — it proves the build wrote into the
disposable workspace and not into the checkout the source was copied from.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Imported after the path is prepared above, which is why it is not at the top.
from image_service import client


def main() -> int:
    dist = Path(__file__).resolve().parent / "dist"
    dist.mkdir(exist_ok=True)
    manifest = {"artifact": "image-service", "model_id": client.MODEL_ID}
    (dist / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"built dist/manifest.json for model {client.MODEL_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
