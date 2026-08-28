"""One declared database, resolved into the address each reader can actually use.

The study model declares the database once, in ``database.host``. Four things then
need to reach it: whatever writes (the phones, or the micro-server), the dashboard's
API reading with its analytics account, the backup job reaching it with
administrative one, and the Configurator when it creates the schema. They were
configured in different files, so changing one left the others pointing at the old
server --- and a dashboard still reporting on a database nobody writes to any more
looks exactly like a study that stopped collecting.

Who writes is resolved here too. Each dataflow puts a different holder on the ingest
path --- a participant's phone on the direct one, the micro-server on the webservice
one --- so each has its own account with its own credential and its own grants, and
the accounts are named below.

Resolution is not copying the address around. Who is asking changes the answer:

*A phone* needs an address reachable from wherever the participant happens to be,
so an internally-named database resolves to the deployment's public host. That is
:func:`~shared_config.serializers.resolve_database_host`, which the generated study
configs already use.

*A service inside the deployment* reaches the bundled database over the compose
network, where its name is ``mysql``. Handing it the public host would send it out
to the internet and back for a container beside it --- or fail outright, since the
published port may be bound to loopback on the webservice dataflow.

So one declaration, two resolutions, and the distinction is which side of the
deployment boundary the reader sits on.

What is asked of that connection is declared once here too, in ``database.tls``,
and resolved the same way: the placement decides whether it is a question at all.
See :func:`tls_required`.
"""

from shared_config import dataflow

#: Names that mean "the database this deployment runs", rather than a host that
#: exists on a network. Kept in step with resolve_database_host in serializers.
INTERNAL_HOSTS = frozenset({"", "db.internal", "mysql", "localhost", "127.0.0.1", "0.0.0.0"})

#: What the bundled database is called on the compose network.
COMPOSE_HOST = "mysql"

#: Where a study says what it wants of the connection to its database: whether that
#: connection has to be encrypted, and the authority the server's certificate is
#: checked against. Beside ``host`` rather than inside a platform's block, because
#: both platforms and every service open the same server --- two answers could
#: disagree about one connection.
TLS_KEY = "tls"

#: The account the dashboard reads with. Read-only on the study tables, with write
#: granted on its own cache tables only (see db/dashboard-tables.sql).
ANALYTICS_USER = "aware_analytics"

#: The account a participant's phone opens the database with on the direct dataflow.
#: Granted inserts on the platform schema and nothing more: a phone delivers rows and
#: reads nothing back.
ANDROID_PARTICIPANT_USER = "aware_android_participant"

#: The account the Android micro-server writes with. Every write on the webservice
#: dataflow is the server's, so ingest authenticates as the server: inserts on the
#: platform schema, the enrolment registry it reads to decide whether a device may
#: write, the refusal counters it keeps, and the device-metadata row it fills in.
ANDROID_SERVER_USER = "aware_android_server"

#: Which account each Android dataflow puts on the ingest path: the study-model keys
#: holding its name and password, and the ``.env`` variable the deployment keeps that
#: password in.
#:
#: One table because several readers need the same answer --- the generated
#: micro-server configuration, the deploy that settles the credential, and the
#: Configurator's password field as it is revealed, stored and applied to MySQL. A
#: field that changed one account's password while the study wrote with the other
#: would report success and collect nothing.
ANDROID_INGEST_ACCOUNTS = {
    dataflow.DIRECT: {
        "name_key": "username",
        "password_key": "password",
        "env_key": "PARTICIPANT_DB_PASSWORD",
        "default_name": ANDROID_PARTICIPANT_USER,
    },
    dataflow.WEBSERVICE: {
        "name_key": "server_username",
        "password_key": "server_password",
        "env_key": "ANDROID_SERVER_DB_PASSWORD",
        "default_name": ANDROID_SERVER_USER,
    },
}


def android_ingest_account(choice: str) -> dict:
    """Where the account this dataflow's Android writes authenticate as is kept.

    Anything other than a declared dataflow reads as the direct path, which is the
    answer :func:`shared_config.dataflow.declared` gives such a study too.
    """
    return ANDROID_INGEST_ACCOUNTS.get(choice, ANDROID_INGEST_ACCOUNTS[dataflow.DIRECT])


def android_credentials(database: dict, choice: str) -> tuple[str, str]:
    """The name and password of the account that writes the Android schema.

    The name falls back to the one the bootstrap SQL creates, so a study model
    carrying no account still names an account that exists.
    """
    account = android_ingest_account(choice)
    entry = (database or {}).get("android") or {}
    return (
        str(entry.get(account["name_key"]) or account["default_name"]).strip(),
        str(entry.get(account["password_key"]) or ""),
    )


def android_server_credentials(database: dict) -> tuple[str, str]:
    """The name and password the Android micro-server authenticates with.

    Read without consulting the dataflow: the instance is configured whichever one
    the study runs, and the server is this credential's only holder, so on the direct
    path it is the same account with no traffic to write.
    """
    return android_credentials(database, dataflow.WEBSERVICE)


def declared_host(database: dict) -> str:
    """The host the study model declares, or the internal name when it declares none."""
    return str((database or {}).get("host") or "db.internal").strip()


def is_internal(host: str) -> bool:
    """Whether this names the deployment's own database rather than a real host."""
    return str(host or "").strip().lower() in INTERNAL_HOSTS


def service_host(database: dict) -> str:
    """The address a service inside the deployment should use.

    ``mysql`` while the database is the bundled one, because that is its name on the
    compose network and the published port may not be reachable at all. A declared
    external host is used as given: there is no internal route to it, and the point
    of declaring it was to send everything there.
    """
    host = declared_host(database)
    return COMPOSE_HOST if is_internal(host) else host


def tls_declaration(database: dict) -> dict:
    """What this study declares about the connection, or {} when it declares nothing."""
    block = (database or {}).get(TLS_KEY)
    return block if isinstance(block, dict) else {}


def tls_required(database: dict) -> bool:
    """Whether the connection to this study's database has to be encrypted.

    Not a preference on the bundled placement. Both ends belong to this deployment,
    the server generates its own certificate on first start and the deploy publishes
    the authority it signed with, so there is nothing for a researcher to arrange and
    nothing to gain by leaving it off --- the setting would only ever be a way to
    make a working study less safe.

    A database the researcher names is a server this deployment does not administer,
    and not every one of them can offer TLS: a MySQL built without it, a MariaDB
    older than 11.4 that generated no certificate, an institutional host whose
    administrator will not enable it. Refusing those outright refuses the study, so
    there the answer is declared rather than assumed.

    A study that declares nothing is encrypted. Silence has meant TLS ever since
    every account was created requiring it, and a study running that way today would
    otherwise be turned unencrypted by the arrival of this setting.
    """
    if is_internal(declared_host(database)):
        return True
    declared = tls_declaration(database).get("require")
    return True if declared is None else bool(declared)


def tls_authority(database: dict) -> str:
    """The authority the database's certificate is checked against, or "" for none.

    Read from the connection block, falling back to where a study written before it
    kept the same PEM so nothing a researcher pasted is lost. Empty leaves the
    connection encrypted and unverified: the traffic cannot be read, and a server on
    the same network could still answer in this database's place.

    Nothing to verify without encryption, so a study that turned TLS off reports
    none whatever it holds.
    """
    if not tls_required(database):
        return ""
    declared = tls_declaration(database).get("ca_certificate")
    if declared is None:
        declared = ((database or {}).get("android") or {}).get("ca_certificate")
    return str(declared or "").strip()


def declare_tls(
    database: dict, require: bool | None = None, ca_certificate: str | None = None
) -> dict:
    """Record what a study wants of its connection, in the one place it is read from.

    Each part is written only when an answer was given, so a caller settling one of
    them leaves the other as the study declared it.
    """
    block = database.setdefault(TLS_KEY, {})
    if require is not None:
        block["require"] = bool(require)
    if ca_certificate is not None:
        block["ca_certificate"] = str(ca_certificate or "").strip()
    return block


def platform_port(database: dict, platform: str) -> int:
    """The port for a platform, defaulting to MySQL's rather than guessing."""
    entry = (database or {}).get(platform) or {}
    try:
        return int(entry.get("port") or 3306)
    except (TypeError, ValueError):
        return 3306


def platform_schema(database: dict, platform: str) -> str:
    """The schema name a platform's data lives in."""
    entry = (database or {}).get(platform) or {}
    return str(entry.get("name") or f"aware_{platform}").strip()


def analytics_url(
    database: dict, platform: str, password: str, driver: str = "mysql+aiomysql"
) -> str:
    """The URL the dashboard's API and its refresher read a platform's data with.

    Built rather than written down, so the two services that need it cannot drift
    apart from each other or from the declaration. The password is passed in rather
    than read from the model: it belongs to the deployment's own account, not to the
    study, and it is the one part of this that is a secret.
    """
    host = service_host(database)
    port = platform_port(database, platform)
    schema = platform_schema(database, platform)
    return f"{driver}://{ANALYTICS_USER}:{password}@{host}:{port}/{schema}"


def resolved_env(database: dict, analytics_password: str) -> dict[str, str]:
    """Everything a deployment's services need, derived from the one declaration.

    Written into ``.env`` so the compose file reads variables instead of repeating
    an address it cannot keep in step. Names are explicit about which side of the
    boundary they serve: these are the internal ones.
    """
    return {
        "DB_SERVICE_HOST": service_host(database),
        # The dashboard's API opens the same server as everything else, so it takes
        # the same answer. Passed as an environment variable because the API reads
        # `.env` and not the study model: a service that encrypted while the server
        # does not offer it would fail every query rather than read the study.
        "DB_REQUIRE_TLS": "1" if tls_required(database) else "0",
        "ANDROID_DATABASE_URL": analytics_url(database, "android", analytics_password),
        "IOS_DATABASE_URL": analytics_url(database, "ios", analytics_password),
    }
