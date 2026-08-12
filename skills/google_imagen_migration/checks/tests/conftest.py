"""Put the check modules on the path.

The skill is a self-contained package rather than a uv workspace member: it must
stay runnable as a plain script inside the sandbox image, where PatchAPI's
Python workspace is not installed.
"""

import sys
from pathlib import Path

CHECKS_DIR = Path(__file__).resolve().parent.parent
if str(CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(CHECKS_DIR))
