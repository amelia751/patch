"""Failure types for the identity provider.

Callers upstream (the control plane's auth routes) catch `ValueError` and turn
the message into an HTTP 400 body that reaches the browser. Every message
raised from this package is therefore written for a person reading a sign-in
form, never for a log reader: no provider error codes, no request IDs.
"""


class AuthConfigurationError(RuntimeError):
    """Identity Platform is not configured well enough to attempt a call.

    Distinct from a credential the user got wrong: this is an operator problem,
    and answering a sign-in attempt with it would leak deployment detail.
    """


class AuthUnavailableError(RuntimeError):
    """The provider could not be reached, so the outcome is genuinely unknown.

    Never collapsed into "incorrect password". A network failure that presents
    as a rejected credential trains users to retype a password that was right.
    """
