"""The ASGI target for `uvicorn patchapi_control_api.asgi:app`.

Kept apart from `app.py` so importing the package — or the factory — never
constructs an application as a side effect.

This instance is deliberately unwired: a deployment supplies its ports through
`create_app`, and until it does, the service reports itself as not ready rather
than pretending it can reach Postgres or Pub/Sub.
"""

from fastapi import FastAPI

from patchapi_control_api.app import create_app

app: FastAPI = create_app()
