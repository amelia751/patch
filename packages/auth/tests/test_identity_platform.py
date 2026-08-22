"""Offline tests for the Identity Platform client.

Every provider call is stubbed at the transport boundary. These assert the two
things a swap from Cognito can silently get wrong: that provider error tokens
still reach the browser as the sentences the sign-in form expects, and that the
methods whose semantics changed (one bearer token, `oobCode` in place of a
typed code) still honour the contract their callers were written against.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from packages.auth.config import IdentityPlatformConfig, load_config
from packages.auth.errors import AuthConfigurationError, AuthUnavailableError
from packages.auth.identity_platform import IdentityPlatformService, _translate

CONFIG = IdentityPlatformConfig(api_key="test-key", project="test-project")


class _Recorder:
    """Stands in for `_post`, capturing calls and replaying queued responses."""

    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, url: str, payload: dict[str, Any], **kwargs: Any) -> Any:
        self.calls.append((url, payload))
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _service(*responses: Any) -> tuple[IdentityPlatformService, _Recorder]:
    service = IdentityPlatformService(CONFIG)
    recorder = _Recorder(*responses)
    service._post = recorder  # type: ignore[method-assign]
    return service, recorder


# -- error translation -----------------------------------------------------


@pytest.mark.parametrize(
    ("provider_message", "expected"),
    [
        ("EMAIL_EXISTS", "An account with this email already exists"),
        ("INVALID_LOGIN_CREDENTIALS", "Incorrect email or password"),
        ("EMAIL_NOT_FOUND", "No account found with this email"),
        ("EXPIRED_OOB_CODE", "That verification link has expired. Please request a new one."),
        ("TOO_MANY_ATTEMPTS_TRY_LATER", "Too many attempts. Please try again later."),
    ],
)
def test_provider_errors_become_readable_sentences(provider_message: str, expected: str) -> None:
    assert _translate(provider_message) == expected


def test_weak_password_keeps_the_providers_detail() -> None:
    message = _translate("WEAK_PASSWORD : Password should be at least 6 characters")
    assert (
        message == "Password does not meet requirements: Password should be at least 6 characters"
    )


def test_unmapped_error_does_not_leak_the_provider_token() -> None:
    """An unrecognised code must not reach the browser verbatim."""
    message = _translate("SOME_INTERNAL_BACKEND_DETAIL")
    assert "SOME_INTERNAL_BACKEND_DETAIL" not in message
    assert message == "Authentication failed. Please try again."


# -- token semantics -------------------------------------------------------


async def test_sign_in_reports_one_bearer_as_both_tokens() -> None:
    """Callers that stored Cognito's access token keep working unchanged."""
    service, _ = _service({"idToken": "id-abc", "refreshToken": "refresh-abc", "expiresIn": "3600"})

    tokens = await service.sign_in("someone@example.com", "pw")

    assert tokens.access_token == "id-abc"
    assert tokens.id_token == tokens.access_token
    assert tokens.expires_in == 3600
    assert tokens.token_type == "Bearer"


async def test_refresh_returns_the_rotated_refresh_token() -> None:
    """Echoing the submitted token back would hand the caller a dead credential."""
    service, _ = _service(
        {"id_token": "id-2", "refresh_token": "refresh-rotated", "expires_in": "3600"}
    )

    tokens = await service.refresh_tokens("refresh-original")

    assert tokens.refresh_token == "refresh-rotated"
    assert tokens.access_token == "id-2"


async def test_refresh_falls_back_when_no_rotation_is_offered() -> None:
    service, _ = _service({"id_token": "id-2", "expires_in": "3600"})

    tokens = await service.refresh_tokens("refresh-original")

    assert tokens.refresh_token == "refresh-original"


# -- account lookup --------------------------------------------------------


async def test_get_user_maps_local_id_onto_sub() -> None:
    service, _ = _service(
        {
            "users": [
                {
                    "localId": "local-123",
                    "email": "someone@example.com",
                    "emailVerified": True,
                    "displayName": "Someone",
                }
            ]
        }
    )

    user = await service.get_user("id-abc")

    assert user.sub == "local-123"
    assert user.email_verified is True
    assert user.name == "Someone"


async def test_absent_email_verified_reads_as_unverified() -> None:
    """The API omits the field rather than sending false."""
    service, _ = _service({"users": [{"localId": "local-123", "email": "a@b.com"}]})

    user = await service.get_user("id-abc")

    assert user.email_verified is False


async def test_empty_lookup_is_rejected() -> None:
    service, _ = _service({"users": []})

    with pytest.raises(ValueError, match="Invalid or expired token"):
        await service.get_user("id-abc")


# -- oobCode handling ------------------------------------------------------


async def test_verification_binds_to_the_code_not_the_caller_supplied_email() -> None:
    """Trusting the address would let one account's link verify another."""
    service, recorder = _service({"email": "someone@example.com"})

    await service.confirm_sign_up("attacker@example.com", "oob-code-xyz")

    _, payload = recorder.calls[0]
    assert payload == {"oobCode": "oob-code-xyz"}
    assert "attacker@example.com" not in str(payload)


async def test_verify_email_attribute_ignores_the_access_token() -> None:
    service, recorder = _service({})

    await service.verify_email_attribute("id-abc", "oob-code-xyz")

    _, payload = recorder.calls[0]
    assert payload == {"oobCode": "oob-code-xyz"}


async def test_reset_sends_only_the_code_and_new_password() -> None:
    service, recorder = _service({})

    await service.confirm_forgot_password("a@b.com", "oob-code", "N3w-Passw0rd!")

    _, payload = recorder.calls[0]
    assert payload == {"oobCode": "oob-code", "newPassword": "N3w-Passw0rd!"}


async def test_inspect_reset_code_does_not_set_a_password() -> None:
    service, recorder = _service({"email": "a@b.com", "requestType": "PASSWORD_RESET"})

    email = await service.inspect_reset_code("oob-code")

    assert email == "a@b.com"
    _, payload = recorder.calls[0]
    assert payload == {"oobCode": "oob-code"}


# -- enumeration resistance ------------------------------------------------


async def test_forgot_password_hides_whether_the_account_exists() -> None:
    """Otherwise the reset form becomes an oracle for registered addresses."""
    service, _ = _service(ValueError("No account found with this email"))

    result = await service.forgot_password("unknown@example.com")

    assert result == {"delivery": {"AttributeName": "email"}}


async def test_forgot_password_still_surfaces_other_failures() -> None:
    service, _ = _service(ValueError("Too many attempts. Please try again later."))

    with pytest.raises(ValueError, match="Too many attempts"):
        await service.forgot_password("someone@example.com")


def test_continue_url_keeps_mode_after_google_strips_the_code() -> None:
    config = IdentityPlatformConfig(
        api_key="k", project="p", action_url="https://app.example/auth/action"
    )
    assert config.continue_url("resetPassword").endswith("?mode=resetPassword")
    assert config.continue_url("verifyEmail").endswith("?mode=verifyEmail")


async def test_forgot_password_continue_url_names_reset() -> None:
    service, recorder = _service({})

    await service.forgot_password("a@b.com")

    assert recorder.calls[0][1]["requestType"] == "PASSWORD_RESET"
    assert recorder.calls[0][1]["continueUrl"].endswith("?mode=resetPassword")


# -- compatibility shims ---------------------------------------------------


async def test_admin_confirm_is_a_truthful_no_op() -> None:
    """Identity Platform has no confirmation gate to satisfy."""
    service, recorder = _service()

    assert await service.admin_confirm_sign_up("someone@example.com") is True
    assert recorder.calls == []


async def test_resend_by_address_alone_fails_loudly() -> None:
    """Reporting a sent mail that was never sent would be worse than failing."""
    service, _ = _service()

    with pytest.raises(ValueError, match="sign in again"):
        await service.resend_confirmation_code("someone@example.com")


async def test_sign_out_never_raises() -> None:
    service, _ = _service(ValueError("Invalid or expired token"))

    assert await service.sign_out("expired-token") is False


async def test_sign_up_reports_unconfirmed_so_the_prompt_shows() -> None:
    service, _ = _service({"localId": "local-123", "idToken": "id", "refreshToken": "r"})

    result = await service.sign_up("a@b.com", "pw", "Someone")

    assert result["user_sub"] == "local-123"
    assert result["id_token"] == "id"
    assert result["confirmed"] is False


# -- configuration ---------------------------------------------------------


def test_unconfigured_service_is_reported_not_guessed() -> None:
    service = IdentityPlatformService(IdentityPlatformConfig())
    assert service.is_configured() is False


async def test_unconfigured_sign_in_raises_an_operator_error() -> None:
    """Distinct from a rejected credential, which is a user error."""
    service = IdentityPlatformService(IdentityPlatformConfig())

    with pytest.raises(AuthConfigurationError):
        await service.sign_in("a@b.com", "pw")


def test_api_key_resolves_from_the_environment_first(tmp_path: Path) -> None:
    (tmp_path / ".secrets").mkdir()
    (tmp_path / ".secrets/identity_platform_api_key.txt").write_text("from-file")

    config = load_config(
        {"PATCHAPI_IDENTITY_API_KEY": "from-env", "GCP_PROJECT": "p"}, base_dir=tmp_path
    )

    assert config.api_key == "from-env"


def test_api_key_falls_back_to_the_key_file(tmp_path: Path) -> None:
    (tmp_path / ".secrets").mkdir()
    # Trailing newline is what a shell redirect leaves behind.
    (tmp_path / ".secrets/identity_platform_api_key.txt").write_text("from-file\n")

    config = load_config({"GCP_PROJECT": "p"}, base_dir=tmp_path)

    assert config.api_key == "from-file"


def test_api_key_falls_back_to_the_web_config(tmp_path: Path) -> None:
    (tmp_path / ".secrets").mkdir()
    (tmp_path / ".secrets/identity-platform.json").write_text(
        '{"apiKey": "from-json", "authDomain": "p.firebaseapp.com", "projectId": "p"}'
    )

    config = load_config({}, base_dir=tmp_path)

    assert config.api_key == "from-json"
    assert config.project == "p"
    assert config.auth_domain == "p.firebaseapp.com"


def test_google_oauth_reads_the_console_web_download(tmp_path: Path) -> None:
    (tmp_path / ".secrets").mkdir()
    (tmp_path / ".secrets/google-oauth.json").write_text(
        '{"web":{"client_id":"id.apps.googleusercontent.com","client_secret":"s"}}'
    )

    config = load_config({"GCP_PROJECT": "p"}, base_dir=tmp_path)

    assert config.google_client_id == "id.apps.googleusercontent.com"
    assert config.google_client_secret == "s"
    assert config.google_oauth_configured() is True


def test_malformed_web_config_reports_unconfigured_rather_than_raising(tmp_path: Path) -> None:
    """A half-written file should not take down every sign-in with a traceback."""
    (tmp_path / ".secrets").mkdir()
    (tmp_path / ".secrets/identity-platform.json").write_text("{not valid json")

    config = load_config({}, base_dir=tmp_path)

    assert config.is_configured() is False


def test_auth_domain_is_derived_when_the_config_omits_it(tmp_path: Path) -> None:
    config = load_config({"GCP_PROJECT": "patch-505223"}, base_dir=tmp_path)

    assert config.auth_domain == "patch-505223.firebaseapp.com"


def test_urls_carry_the_key_and_project() -> None:
    assert CONFIG.url("signUp").endswith("accounts:signUp?key=test-key")
    assert CONFIG.admin_url("accounts").endswith("/projects/test-project/accounts")


async def test_transport_failure_is_not_mistaken_for_a_bad_password() -> None:
    """A network error that presents as a rejected credential trains users to
    retype a password that was already correct."""
    service = IdentityPlatformService(CONFIG)

    async def _explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AuthUnavailableError("could not reach Identity Platform")

    service._post = _explode  # type: ignore[method-assign]

    with pytest.raises(AuthUnavailableError):
        await service.sign_in("a@b.com", "pw")
