"""Provision the first owner outside the public HTTP API."""

import argparse
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError

from .config import database_url_from_env
from .domain import ConfigurationError
from .profile import DuplicateEmailError, InvalidProfileError
from .profile_repository import SqlProfileRepository


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision the first API owner")
    parser.add_argument("email")
    args = parser.parse_args(argv)
    try:
        repository = SqlProfileRepository(database_url_from_env())
        try:
            profile = repository.provision_owner(args.email)
        finally:
            repository.close()
    except (ConfigurationError, DuplicateEmailError, InvalidProfileError) as error:
        print(error)
        return 1
    except SQLAlchemyError:
        print("Profile database is unavailable")
        return 1
    print(f"Provisioned owner {profile.email} (id {profile.id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
