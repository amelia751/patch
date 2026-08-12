"""Run the GitHub tool service locally: `patchapi-github-tools`."""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "patchapi_github_tools.asgi:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8081")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
