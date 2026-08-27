"""Where the study database runs, as one answer everything else follows.

Two placements, and the researcher chooses between them:

``bundled``
    A MySQL container this deployment brings up and administers. Nothing has to
    exist beforehand and nothing outside this machine is involved.

``external``
    A database the researcher names and owns --- their institution's server, a
    managed instance, a host on their own network. This deployment connects to it
    and never starts a database of its own.

The answer is not a field of its own. ``database.host`` already carries it: a host
that names this deployment's own database is ``bundled`` and any other host is
``external``, which is the same question :func:`shared_config.database.is_internal`
already answers for every other reader. A second field would be a second answer,
and the two could disagree about which database a study is using.

What follows from the choice is the whole of it. On ``external`` the bundled MySQL
service does not exist: no container, no published port, and none of the six
services that wait on its health check. On ``bundled`` it is brought up and the
published port is whatever the dataflow decides.

One combination is refused. A study running the direct dataflow puts every
participant's phone on the database itself, from whatever network the participant
happens to be on, which means the host has to be reachable from the internet for
the length of the study. That is a thing a researcher can decide to do with a
database they administer, and it is not a thing an institution does with theirs ---
so external is offered with HTTP/S ingest, where only the micro-server connects,
and refused with direct, where every phone would have to.

Switching placement is a redeploy rather than a live change, for the same reason
the dataflow is: it decides which containers exist. What it does not do is carry
the data across --- the history stays on the server that holds it, and moving it is
an export from one and a merge-import into the other.
"""

from shared_config import dataflow

#: A MySQL container this deployment runs.
BUNDLED = "bundled"
#: A database the researcher names and owns.
EXTERNAL = "external"

CHOICES = (BUNDLED, EXTERNAL)

#: What a study declares when it names no host of its own.
DEFAULT_HOST = "db.internal"


def declared(source: dict) -> str:
    """Where this study's database runs, read from the host it declares."""
    from shared_config import database

    return BUNDLED if database.is_internal(database.declared_host(source.get("database") or {})) else EXTERNAL


def declared_for_host(host: str) -> str:
    """The placement a host implies, for a host that is not in a study model yet."""
    from shared_config import database

    return BUNDLED if database.is_internal(host) else EXTERNAL


def unsupported_reason(placement: str, android_dataflow: str) -> str | None:
    """Why this placement cannot be run beside this dataflow, or None when it can.

    A sentence rather than a boolean, because the caller's job is to tell a
    researcher what the combination costs rather than to report that a form is
    invalid.
    """
    if placement not in CHOICES:
        return f"{placement!r} is not a placement. Choose {BUNDLED!r} or {EXTERNAL!r}."
    if placement == BUNDLED:
        return None
    if android_dataflow == dataflow.DIRECT:
        return (
            "An external database cannot be used while Android phones connect to it "
            "directly: every participant's phone would have to reach that host on its "
            "database port from whatever network it is on, for the length of the "
            "study. Send Android data through the server instead, and only the "
            "micro-server connects to the database."
        )
    return None


def runs_bundled_mysql(placement: str) -> bool:
    """Whether this deployment brings up a database of its own."""
    return placement != EXTERNAL


def switch_note(current: str, chosen: str) -> str | None:
    """What changing placement on a deployed study costs, or None when nothing changes.

    Returned for a switch that is allowed, and says the part the software does not
    do: the rows already collected stay on the server holding them. The dashboard's
    backup page exports from one server and merge-imports into another, which is how
    they travel if the researcher wants them to.
    """
    if current == chosen:
        return None
    if chosen == EXTERNAL:
        return (
            "The deployment will stop running its own database and connect to the one "
            "you named. Data already collected stays in the bundled database and does "
            "not move: export it from the backup page first if the study needs it, then "
            "merge-import it into the new server."
        )
    return (
        "The deployment will bring up its own database again. Data already collected "
        "stays on the external server and does not move: export it from the backup "
        "page first if the study needs it, then merge-import it once this is running."
    )


def validate(source: dict) -> list[str]:
    """Every reason this study's placement cannot be honoured, as sentences.

    Empty means the study is coherent. Collected rather than raised on the first
    problem, so a researcher fixing a study model sees all of it at once.
    """
    reason = unsupported_reason(declared(source), dataflow.declared(source, "android"))
    return [] if reason is None else [f"database: {reason}"]
