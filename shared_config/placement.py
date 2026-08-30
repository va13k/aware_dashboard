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

One combination is warned about rather than refused. A study running the direct
dataflow puts every participant's phone on the database itself, from whatever
network the participant is on, so an external host has to be reachable from the
internet for the length of the study. An institution does not open its database
that way; a researcher running their own server legitimately might. Refusing it
would decide for them, so it is offered with the exposure stated plainly.

Encryption follows the placement in the same way. On ``bundled`` it is settled and
not asked about: this deployment administers both ends. On ``external`` it is a
property of somebody else's server, so it is asked for, checked before the study
deploys, and refusable --- an institutional MySQL built without TLS would otherwise
be a database this software simply cannot be pointed at.

Switching placement is a redeploy rather than a live change, for the same reason
the dataflow is: it decides which containers exist. What it decides on its own is
only where the next row is written. Two things a researcher may want to follow the
study are asked for instead of assumed, and both are no unless answered: carrying
the rows already collected, which the deploy writes out as a script to run rather
than doing behind a browser, and keeping the scheduled backup job, which is
otherwise removed along with the database it was written for.
"""

from shared_config import dataflow

#: A MySQL container this deployment runs.
BUNDLED = "bundled"
#: A database the researcher names and owns.
EXTERNAL = "external"

CHOICES = (BUNDLED, EXTERNAL)

#: What a study declares when it names no host of its own.
DEFAULT_HOST = "db.internal"

#: The port that host answers on. MySQL's own, because this deployment runs the
#: server and publishes it unchanged --- so it belongs to the placement the same way
#: the host does, and a study moving back onto it takes both rather than keeping the
#: port of a server it no longer names.
DEFAULT_PORT = 3306


def declared(source: dict) -> str:
    """Where this study's database runs, read from the host it declares."""
    from shared_config import database

    return BUNDLED if database.is_internal(database.declared_host(source.get("database") or {})) else EXTERNAL


def declared_for_host(host: str) -> str:
    """The placement a host implies, for a host that is not in a study model yet."""
    from shared_config import database

    return BUNDLED if database.is_internal(host) else EXTERNAL


#: Who opens the study database, from where, and what that demands of the
#: connection. Every setting that used to be decided by the dataflow alone is
#: decided here instead, because the dataflow only names half of it: the same
#: webservice study is a connection inside one machine on a bundled database and a
#: connection across a real network on one the researcher names.
def connection(placement_choice: str, android_dataflow: str) -> dict:
    """What the combination of dataflow and placement makes true of the database.

    ``opener``
        Who opens MySQL. Participants' phones on the direct path; this deployment's
        micro-server on the webservice one. It decides which account carries the
        credential and therefore where a password has to be asked for.

    ``crosses_network``
        Whether the connection leaves the machine running the deployment. True for
        every combination except a server talking to a database beside it, and it is
        the whole reason TLS matters: a hop across a bridge on one host and a hop
        across the internet are the same statement in the config and not the same
        risk.

    ``bundled_bind``
        The address the bundled database is published on, or ``None`` when this
        deployment runs no database of its own. Publishing to ``0.0.0.0`` is not a
        preference: a phone opening MySQL itself has to reach it from whatever
        network the participant is on.
    """
    direct = android_dataflow == dataflow.DIRECT
    external = placement_choice == EXTERNAL
    return {
        "opener": "participants" if direct else "server",
        "crosses_network": direct or external,
        "bundled_bind": None if external else ("0.0.0.0" if direct else "127.0.0.1"),
        "publishes_port": (not external) and direct,
    }


def requires_tls(placement_choice: str) -> bool:
    """Whether encryption is settled by the placement rather than asked about.

    A database this deployment runs is one it administers at both ends: it generates
    the certificate, the deploy publishes the authority it signed with, and every
    account it creates requires an encrypted session. Nothing has to be arranged, so
    there is nothing to ask and no answer worth accepting except yes.

    A database the researcher names is a server this deployment does not administer,
    and TLS there is something its owner either offers or does not. That is the one
    placement where the question is real, and :func:`shared_config.database.tls_required`
    is where the study's answer to it is read.
    """
    return placement_choice != EXTERNAL


def unencrypted_warning(placement_choice: str, android_dataflow: str) -> str | None:
    """What running this combination without TLS exposes, or None when it cannot be run so.

    Returned as the sentence an interface shows in red, because the two unsafe cases
    are unsafe for different reasons and a single generic caution would understate
    both.
    """
    if requires_tls(placement_choice):
        return None
    if connection(placement_choice, android_dataflow)["opener"] == "participants":
        return (
            "Without TLS every participant's phone sends its sensor data, and the "
            "database password it holds, in clear text across whatever network the "
            "participant is on. Anyone on that network can read both."
        )
    return (
        "Without TLS this deployment sends the whole study's data to the database "
        "in clear text across the network between them, with the account password "
        "in the open alongside it."
    )


def unsupported_reason(placement: str, android_dataflow: str) -> str | None:
    """Why this placement cannot be run beside this dataflow, or None when it can.

    A sentence rather than a boolean, because the caller's job is to tell a
    researcher what the combination costs rather than to report that a form is
    invalid.
    """
    if placement not in CHOICES:
        return f"{placement!r} is not a placement. Choose {BUNDLED!r} or {EXTERNAL!r}."
    return None


def exposure_caution(placement_choice: str, android_dataflow: str) -> str | None:
    """What this combination requires of the network, or None when it requires nothing.

    The direct path is the one that costs something a researcher has to arrange with
    somebody else: every participant's phone opens the database, so the host has to
    accept connections from anywhere for the length of the study. On a database they
    run themselves that is theirs to decide; on their institution's it is a request
    that will usually be refused, and better read here than after enrolment.
    """
    if android_dataflow != dataflow.DIRECT:
        return None
    if placement_choice == EXTERNAL:
        return (
            "Every participant's phone opens this database directly, so the host you "
            "named has to accept connections from any network, for the length of the "
            "study. An institution will rarely open a database that way --- if this is "
            "not a server you run yourself, send the data through the server instead."
        )
    return (
        "Every participant's phone opens this database directly, so its port is "
        "published on this machine's public address for the length of the study."
    )


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
