import json
import os

import pytest

from src.domain import ConfigurationError
from src.runtime_secrets import load_ingestion_runtime_secrets


class FakeSecretsClient:
    def __init__(self, secret_string: str) -> None:
        self.secret_string = secret_string
        self.requested_arn: str | None = None

    def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
        self.requested_arn = SecretId
        return {"SecretString": self.secret_string}


def test_runtime_secrets_populate_required_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeSecretsClient(
        json.dumps(
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "test-model",
                "DATABASE_URL": "postgresql+psycopg://localhost/test",
            }
        )
    )
    monkeypatch.setenv("INGESTION_RUNTIME_SECRET_ARN", "arn:aws:secretsmanager:test")
    for key in ("OPENAI_API_KEY", "OPENAI_MODEL", "DATABASE_URL"):
        monkeypatch.setenv(key, "")
    monkeypatch.setattr("src.runtime_secrets.boto3.client", lambda _: client)

    load_ingestion_runtime_secrets()

    assert client.requested_arn == "arn:aws:secretsmanager:test"
    assert os.environ["OPENAI_MODEL"] == "test-model"


@pytest.mark.parametrize("secret_string", ['{"OPENAI_API_KEY":"key"}', "not-json"])
def test_runtime_secrets_reject_malformed_secret(
    monkeypatch: pytest.MonkeyPatch, secret_string: str
) -> None:
    client = FakeSecretsClient(secret_string)
    monkeypatch.setenv("INGESTION_RUNTIME_SECRET_ARN", "arn:aws:secretsmanager:test")
    monkeypatch.setattr("src.runtime_secrets.boto3.client", lambda _: client)

    with pytest.raises(ConfigurationError, match="Invalid ingestion runtime secret"):
        load_ingestion_runtime_secrets()
