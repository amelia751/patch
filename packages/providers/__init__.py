"""Provider adapters: untrusted external evidence in, typed contracts out.

Nothing is imported eagerly here. A bare `pytest` at the repo root collects
every tree using the workspace-root environment, which does not install
workspace members, so an eager import of Pydantic or google-auth would abort
collection for all of them.
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
