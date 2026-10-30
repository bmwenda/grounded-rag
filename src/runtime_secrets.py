"""Load ingestion Lambda credentials from a referenced Secrets Manager secret."""

import json
import os

import boto3  # type: ignore[import-untyped]

from .domain import ConfigurationError

REQUIRED_SECRET_KEYS = ("LLM_MODEL", "DATABASE_URL")
OPTIONAL_SECRET_KEYS = (
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_API_KEY",
    "EMBEDDING_MODEL",
)


def load_ingestion_runtime_secrets() -> None:
    """Populate required settings from a secret when its ARN is configured."""
    secret_arn = os.getenv("INGESTION_RUNTIME_SECRET_ARN")
    if not secret_arn:
        return

    response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
    try:
        values = json.loads(response["SecretString"])
        if not isinstance(values, dict):
            raise TypeError("invalid secret object")
        provider = values.get("LLM_PROVIDER", "openai")
        if provider not in {"openai", "anthropic", "ollama"}:
            raise ValueError("invalid model provider")
        required = list(REQUIRED_SECRET_KEYS)
        if provider != "ollama":
            required.append("LLM_API_KEY")
        if provider != "openai":
            required.append("EMBEDDING_API_KEY")
        if any(
            not isinstance(values.get(key), str) or not values[key]
            for key in required
        ):
            raise ValueError("missing runtime secret setting")
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError("Invalid ingestion runtime secret") from exc

    for key in (*REQUIRED_SECRET_KEYS, *OPTIONAL_SECRET_KEYS):
        if key in values:
            if not isinstance(values[key], str):
                raise ConfigurationError("Invalid ingestion runtime secret")
            os.environ[key] = values[key]
