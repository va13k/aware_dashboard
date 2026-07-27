"""Keep the participant MySQL account in sync with the study configuration.

The study configuration served to devices embeds the participant account's
password, or marks the account as passwordless. This module adjusts the actual
MySQL account so a saved configuration is always usable by devices. It only
touches an already-provisioned participant account; creating databases and
accounts remains the responsibility of the deployment setup step.
"""
from __future__ import annotations

import logging

import pymysql

logger = logging.getLogger(__name__)

# Devices connect through the '<user>'@'%' account created during deployment.
PARTICIPANT_HOST_PATTERN = "%"


class ParticipantDbError(RuntimeError):
    """Raised when the participant account credentials cannot be applied."""


def apply_participant_credentials(
    *,
    host: str,
    port: int,
    root_password: str,
    username: str,
    password: str,
    require_ssl: bool,
) -> None:
    """Set the participant account's password and TLS requirement.

    ``password`` is the empty string for a passwordless account. Raises
    ``ParticipantDbError`` if the account cannot be reached or updated; the
    caller relies on that to leave the served config and database untouched.
    """
    if not username:
        raise ParticipantDbError("Participant database username is not configured.")
    if not root_password:
        raise ParticipantDbError(
            "MySQL root password is unavailable; cannot update the participant account."
        )

    try:
        connection = pymysql.connect(
            host=host,
            port=int(port),
            user="root",
            password=root_password,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=10,
        )
    except Exception as exc:
        logger.error("Could not connect to MySQL as root: %s", exc)
        raise ParticipantDbError(
            "Could not reach the database to update the participant account."
        ) from exc

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM mysql.user WHERE user = %s AND host = %s",
                (username, PARTICIPANT_HOST_PATTERN),
            )
            if cursor.fetchone() is None:
                raise ParticipantDbError(
                    f"Participant account '{username}'@'{PARTICIPANT_HOST_PATTERN}' does not "
                    "exist. Run the deployment setup before changing its credentials."
                )

            # Change the password and TLS requirement in a single statement so
            # the account is never left in a half-updated state between them.
            require_clause = "SSL" if require_ssl else "NONE"
            cursor.execute(
                f"ALTER USER %s@%s IDENTIFIED BY %s REQUIRE {require_clause}",
                (username, PARTICIPANT_HOST_PATTERN, password),
            )
        logger.info(
            "Updated participant account '%s'@'%s' (passwordless=%s, require_ssl=%s)",
            username,
            PARTICIPANT_HOST_PATTERN,
            not password,
            require_ssl,
        )
    except ParticipantDbError:
        raise
    except Exception as exc:
        logger.error("Failed to update participant account: %s", exc)
        raise ParticipantDbError(
            "The database rejected the participant account update."
        ) from exc
    finally:
        connection.close()
