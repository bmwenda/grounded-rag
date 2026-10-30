"""Load ingestion Lambda credentials from a referenced Secrets Manager secret."""

import json
import os

import boto3  # type: ignore[import-untyped]

from .domain import ConfigurationError

SECRET_ALIASES = {
    "LLM_API_KEY": "OPENAI_API_KEY",
    "LLM_MODEL": "OPENAI_MODEL",
    "EMBEDDING_MODEL": "OPENAI_EMBEDDING_MODEL",
}
REQUIRED_SECRET_KEYS = ("LLM_API_KEY", "LLM_MODEL", "DATABASE_URL")
OPTIONAL_SECRET_KEYS = (
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
        for name, legacy in SECRET_ALIASES.items():
            if not values.get(name) and values.get(legacy):
                values[name] = values[legacy]
        if any(
            not isinstance(values.get(key), str) or not values[key]
            for key in REQUIRED_SECRET_KEYS
        ):
            raise ValueError("missing runtime secret setting")
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError("Invalid ingestion runtime secret") from exc

    for key in (*REQUIRED_SECRET_KEYS, *OPTIONAL_SECRET_KEYS, *SECRET_ALIASES.values()):
        if key in values:
            if not isinstance(values[key], str):
                raise ConfigurationError("Invalid ingestion runtime secret")
            os.environ[key] = values[key]
