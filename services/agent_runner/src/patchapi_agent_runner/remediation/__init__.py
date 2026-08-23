"""The remediation lane: one change, one repository, one pull request.

Separate from the change-intelligence handler in `serve.py` because they are
different shapes of work rather than two features of one service. Change
intelligence reads a notice and writes a sentence, in seconds, on a request.
Remediation clones a tree, runs a model against it several times, builds it,
tests it, has a second model grade the result, and opens a pull request — for
minutes, with no request to answer.

They share this image because they share the fleet, the sandbox, and the
database. They do not share an entry point.
"""

from __future__ import annotations

__all__: list[str] = []
