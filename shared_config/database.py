"""One declared database, resolved into the address each reader can actually use.

The study model declares the database once, in ``database.host``. Four things then
need to reach it: whatever writes (the phones, or the micro-server), the dashboard's
API reading with its analytics account, the backup job reaching it with
administrative one, and the Configurator when it creates the schema. They were
configured in different files, so changing one left the others pointing at the old
server --- and a dashboard still reporting on a database nobody writes to any more
looks exactly like a study that stopped collecting.

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
"""

#: Names that mean "the database this deployment runs", rather than a host that
#: exists on a network. Kept in step with resolve_database_host in serializers.
INTERNAL_HOSTS = frozenset({"", "db.internal", "mysql", "localhost", "127.0.0.1", "0.0.0.0"})

#: What the bundled database is called on the compose network.
COMPOSE_HOST = "mysql"

#: The account the dashboard reads with. Read-only on the study tables, with write
#: granted on its own cache tables only (see db/dashboard-tables.sql).
ANALYTICS_USER = "aware_analytics"


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
        "ANDROID_DATABASE_URL": analytics_url(database, "android", analytics_password),
        "IOS_DATABASE_URL": analytics_url(database, "ios", analytics_password),
    }
