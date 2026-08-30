"""Keep the MySQL account ingest authenticates as in sync with the study configuration.

The account is named by the caller, because which one holds the study's ingest
credential follows from its dataflow: the participant account a phone opens the
database with on the direct path, and the micro-server's own on the webservice path,
where the server performs every write. This module adjusts that account so a saved
configuration is always usable by whatever the study writes with. It only touches an
already-provisioned account; creating databases and accounts remains the
responsibility of the deployment setup step.
"""
from __future__ import annotations

import logging

import pymysql

logger = logging.getLogger(__name__)

# Both holders connect through the '<user>'@'%' account created during deployment: a
# phone from wherever the participant is, the micro-server from the compose network.
ACCOUNT_HOST_PATTERN = "%"


class ParticipantDbError(RuntimeError):
    """Raised when the account's credentials cannot be applied."""


def apply_account_credentials(
    *,
    host: str,
    port: int,
    admin_user: str,
    admin_password: str,
    username: str,
    password: str,
    require_ssl: bool,
) -> None:
    """Set the named account's password and TLS requirement.

    ``password`` is the empty string for a passwordless account. Raises
    ``ParticipantDbError`` if the account cannot be reached or updated; the
    caller relies on that to leave the served config and database untouched.
    """
    if not username:
        raise ParticipantDbError("The database account to change is not configured.")
    if not admin_password:
        raise ParticipantDbError(
            f"No password for {admin_user or 'the database administrator'}; cannot "
            "update the database account."
        )

    try:
        connection = pymysql.connect(
            host=host,
            port=int(port),
            user=admin_user or "root",
            password=admin_password,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=10,
        )
    except Exception as exc:
        logger.error("Could not connect to MySQL as root: %s", exc)
        raise ParticipantDbError(
            "Could not reach the database to update the account."
        ) from exc

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM mysql.user WHERE user = %s AND host = %s",
                (username, ACCOUNT_HOST_PATTERN),
            )
            if cursor.fetchone() is None:
                raise ParticipantDbError(
                    f"Account '{username}'@'{ACCOUNT_HOST_PATTERN}' does not "
                    "exist. Run the deployment setup before changing its credentials."
                )

            # Change the password and TLS requirement in a single statement so
            # the account is never left in a half-updated state between them.
            require_clause = "SSL" if require_ssl else "NONE"
            cursor.execute(
                f"ALTER USER %s@%s IDENTIFIED BY %s REQUIRE {require_clause}",
                (username, ACCOUNT_HOST_PATTERN, password),
            )
        logger.info(
            "Updated account '%s'@'%s' (passwordless=%s, require_ssl=%s)",
            username,
            ACCOUNT_HOST_PATTERN,
            not password,
            require_ssl,
        )
    except ParticipantDbError:
        raise
    except Exception as exc:
        logger.error("Failed to update the database account: %s", exc)
        raise ParticipantDbError(
            "The database rejected the account update."
        ) from exc
    finally:
        connection.close()
