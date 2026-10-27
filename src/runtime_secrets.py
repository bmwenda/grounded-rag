"""Load ingestion Lambda credentials from a referenced Secrets Manager secret."""

import json
import os

import boto3  # type: ignore[import-untyped]

from .domain import ConfigurationError

REQUIRED_SECRET_KEYS = ("OPENAI_API_KEY", "OPENAI_MODEL", "DATABASE_URL")


def load_ingestion_runtime_secrets() -> None:
    """Populate required settings from a secret when its ARN is configured."""
    secret_arn = os.getenv("INGESTION_RUNTIME_SECRET_ARN")
    if not secret_arn:
        return

    response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
    try:
        values = json.loads(response["SecretString"])
        if not isinstance(values, dict) or any(
            not isinstance(values.get(key), str) or not values[key]
            for key in REQUIRED_SECRET_KEYS
        ):
            raise ValueError("missing runtime secret setting")
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError("Invalid ingestion runtime secret") from exc

    for key in REQUIRED_SECRET_KEYS:
        os.environ[key] = values[key]
