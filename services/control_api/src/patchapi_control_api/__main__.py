"""Console entry point: serve the control plane with uvicorn.

Reads `PORT` because that is what Cloud Run injects, and `HOST` so a local run
can bind the loopback interface instead of every interface.
"""

import os

import uvicorn

# Containers bind every interface; the platform, not the process, decides who
# may reach the port. Set HOST to bind the loopback interface locally.
_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = 8080


def main() -> None:
    """Run the ASGI server until interrupted."""
    uvicorn.run(
        "patchapi_control_api.asgi:app",
        host=os.environ.get("HOST", _DEFAULT_HOST),
        port=int(os.environ.get("PORT", _DEFAULT_PORT)),
        # The control plane never reloads from a watched directory: reload
        # imports whatever is on disk, which is the opposite of the guarantee
        # that this service does not execute code it did not ship with.
        reload=False,
    )


if __name__ == "__main__":
    main()
