"""ASGI entry point: `uvicorn patchapi_github_tools.asgi:app`."""

from fastapi import FastAPI

from patchapi_github_tools.app import create_app
from patchapi_github_tools.wiring import build_github_client

app: FastAPI = create_app(github=build_github_client())
