"""Namespace anchor for the `packages.*` trees.

Declared pkgutil-style so an installed workspace member (for example
`packages.schemas`) can contribute to the same namespace as the in-tree source
checkout without shadowing it.
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
