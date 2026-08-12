"""Credential loading fails closed, and credentials refuse to be printed."""

import json
import logging

import pytest
from patchapi_github_tools.config import (
    ENV_APP_ID,
    ENV_INSTALLATION_ID,
    ENV_PRIVATE_KEY_PATH,
    ENV_PRIVATE_KEY_SECRET,
)
from patchapi_github_tools.credentials import (
    AppCredentials,
    Secret,
    credentials_are_configured,
    load_app_credentials,
)
from patchapi_github_tools.errors import CredentialsUnavailableError
from patchapi_github_tools.wiring import build_github_client

# Shaped like key material so the redaction assertions are meaningful; not a
# key, and deliberately not scanner-shaped.
SENSITIVE = "BEGIN-PRIVATE-KEY EXAMPLE-NOT-A-KEY"


def test_secret_never_renders_itself(caplog):
    secret = Secret(SENSITIVE)
    assert repr(secret) == "<redacted>"
    assert str(secret) == "<redacted>"
    assert f"{secret}" == "<redacted>"
    assert f"{secret!r}" == "<redacted>"
    assert f"{secret:>40}" == "<redacted>"
    assert SENSITIVE not in json.dumps({"key": str(secret)})
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("test").info("credential=%s", secret)
    assert SENSITIVE not in caplog.text
    assert secret.reveal() == SENSITIVE


def test_credentials_repr_omits_the_key(app_env, private_key_pem):
    credentials = load_app_credentials(app_env)
    rendered = repr(credentials)
    assert "123456" in rendered
    assert "PRIVATE KEY" not in rendered
    assert private_key_pem.strip() not in rendered


def test_loads_the_key_from_a_file(app_env, private_key_pem):
    credentials = load_app_credentials(app_env)
    assert credentials.app_id == "123456"
    assert credentials.installation_id == "78901234"
    assert credentials.private_key_pem.reveal() == private_key_pem


def test_loads_the_key_from_secret_manager(app_env, private_key_pem):
    class RecordingResolver:
        def __init__(self):
            self.requested = None

        def resolve(self, resource_name: str) -> str:
            self.requested = resource_name
            return private_key_pem

    env = {**app_env}
    del env[ENV_PRIVATE_KEY_PATH]
    env[ENV_PRIVATE_KEY_SECRET] = "projects/patch-505223/secrets/github-app-key/versions/latest"
    resolver = RecordingResolver()

    credentials = load_app_credentials(env, secret_resolver=resolver)
    assert resolver.requested.endswith("/versions/latest")
    assert credentials.private_key_pem.reveal() == private_key_pem


@pytest.mark.parametrize("missing", [ENV_APP_ID, ENV_INSTALLATION_ID, ENV_PRIVATE_KEY_PATH])
def test_a_missing_variable_is_named_in_the_failure(app_env, missing):
    env = {key: value for key, value in app_env.items() if key != missing}
    with pytest.raises(CredentialsUnavailableError) as failure:
        load_app_credentials(env)
    assert missing in str(failure.value)


def test_two_key_sources_is_an_error_not_a_preference(app_env):
    env = {**app_env, ENV_PRIVATE_KEY_SECRET: "projects/p/secrets/s/versions/1"}
    with pytest.raises(CredentialsUnavailableError, match="exactly one"):
        load_app_credentials(env)


def test_a_non_numeric_app_id_is_rejected(app_env):
    with pytest.raises(CredentialsUnavailableError, match=ENV_APP_ID):
        load_app_credentials({**app_env, ENV_APP_ID: "PatchAPI Demo"})


def test_a_missing_key_file_is_rejected(app_env, tmp_path):
    env = {**app_env, ENV_PRIVATE_KEY_PATH: str(tmp_path / "absent.pem")}
    with pytest.raises(CredentialsUnavailableError, match="not a readable file"):
        load_app_credentials(env)


def test_a_malformed_key_is_rejected_at_load_time(app_env, tmp_path):
    bad = tmp_path / "bad.pem"
    bad.write_text("not a key", encoding="utf-8")
    with pytest.raises(CredentialsUnavailableError, match="unencrypted PEM"):
        load_app_credentials({**app_env, ENV_PRIVATE_KEY_PATH: str(bad)})


def test_configured_predicate_matches_the_loader(app_env):
    assert credentials_are_configured(app_env) is True
    assert credentials_are_configured({}) is False


def test_unconfigured_environment_yields_no_client():
    assert build_github_client({}) is None


def test_misconfigured_environment_raises_rather_than_returning_none(app_env):
    # "Not configured" and "configured wrongly" must not look the same.
    with pytest.raises(CredentialsUnavailableError):
        build_github_client({**app_env, ENV_APP_ID: "not-a-number"})


def test_app_credentials_reject_a_non_rsa_pem(private_key_pem):
    with pytest.raises(CredentialsUnavailableError):
        AppCredentials(app_id="1", installation_id="2", private_key_pem=Secret("garbage"))
