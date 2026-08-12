"""PatchAPI control plane.

`create_app` is the only supported entry point; importing it does not build an
application, so a caller chooses its own dependency wiring.
"""

from patchapi_control_api.app import create_app

__all__ = ["create_app"]
