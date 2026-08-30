import base64
import json
import pathlib
import re
import urllib.parse
import sys

#: Where the project root can be, in the order tried. A checkout keeps this file
#: in the project's setup directory; the wizard container keeps it in a flat
#: /wizard directory and mounts the project at /project.
PROJECT_CANDIDATES = (
    pathlib.Path(__file__).resolve().parent.parent,
    pathlib.Path("/project"),
)


def project_root(candidates=PROJECT_CANDIDATES) -> pathlib.Path:
    """The candidate that holds shared_config, which is the project root.

    Both layouts serve the same wizard, so the root is found by the package it
    has to contain rather than by this file's position in it.
    """
    for candidate in candidates:
        if (candidate / "shared_config").is_dir():
            return candidate
    return candidates[0]


# The dataflow vocabulary and its rules live with the study model rather than
# being restated here, so the wizard cannot accept a choice the generation
# refuses.
sys.path.insert(0, str(project_root()))
from shared_config import database, dataflow, placement  # noqa: E402
from shared_config.certificates import read_certificate  # noqa: E402

# Characters that survive .env, the wizard's JSON responses and MySQL quoting
# unambiguously, and that a participant can retype from a printed sheet. Kept
# in step with PASSWORD_PATTERN in script.js.
PASSWORD_PATTERN = re.compile(r"^[A-Za-z0-9._~@#%^*+=:-]+$")


def parse_env_text(env_text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in str(env_text).splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def positive_int(value: object, fallback: str) -> str:
    try:
        numeric = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return str(numeric if numeric > 0 else int(fallback))


def clean_participant_password(value: object) -> str:
    """Validate the participant password, or return "" to let deploy generate one.

    Only reached for a value the researcher typed: an empty field means "keep
    whatever .env already holds", which deploy_config resolves.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if not PASSWORD_PATTERN.match(text):
        raise SystemExit(
            "Participant password may only contain letters, digits or . _ ~ @ # % ^ * + = : -"
        )
    return text


def clean_path(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if any(ch.isspace() for ch in text):
        raise SystemExit("Backup folder cannot contain spaces")
    return text



def clean_dataflow(value: object, fallback: str) -> str:
    """The Android dataflow, refused here rather than downstream when unknown.

    A value nothing recognises would otherwise reach the study model and be
    silently replaced by a default, which is the study quietly collecting the
    wrong way. Refusing at the boundary keeps the answer the researcher gave.
    """
    chosen = str(value or fallback or dataflow.DIRECT).strip().lower()
    if chosen not in dataflow.CHOICES:
        raise SystemExit(
            f"ANDROID_DATAFLOW must be one of {', '.join(dataflow.CHOICES)}, "
            f"not {chosen!r}"
        )
    reason = dataflow.unsupported_reason("android", chosen)
    if reason is not None:
        raise SystemExit(reason)
    return chosen


def parse_connection_string(value: object) -> dict[str, str]:
    """The parts of a connection string, or {} when this is not one.

    Providers give a database as a single line to copy --- scheme, credentials,
    host, port, database, options --- and that line is what a researcher has in
    hand. Reading it here means the wizard can be pasted into rather than filled
    in, and that pasting it in the wrong field is answered by using it rather than
    by an error.
    """
    text = str(value or "").strip()
    if "://" not in text:
        return {}

    parsed = urllib.parse.urlsplit(text)
    if not parsed.hostname:
        return {}

    found = {"host": parsed.hostname}
    if parsed.port:
        found["port"] = str(parsed.port)
    if parsed.username:
        found["admin_user"] = urllib.parse.unquote(parsed.username)
    if parsed.password:
        found["admin_password"] = urllib.parse.unquote(parsed.password)
    return found


#: Who makes the database ready. `auto` is setup, with the account the study
#: named; `manual` is somebody running the file it hands out, after which setup
#: only checks what it finds. The difference is which account has to be powerful:
#: creating a schema needs more than writing to one.
DB_INIT_CHOICES = ("auto", "manual")


def clean_db_init(value: object, fallback: str) -> str:
    chosen = str(value or fallback or "auto").strip().lower()
    if chosen not in DB_INIT_CHOICES:
        raise SystemExit(
            f"DB_INIT must be one of {', '.join(DB_INIT_CHOICES)}, not {chosen!r}"
        )
    return chosen


def clean_flag(value: object, fallback: object = "") -> str:
    """A yes-or-no answer as `.env` carries one, defaulting to no.

    Both answers this reads are about a database somebody else runs, and the wizard
    only shows them once the study says it names one. Anything it does not recognise
    falls to what the deployment already settled and then to no, because these decide
    what is copied to and dumped from a server this deployment does not administer.
    """
    for candidate in (value, fallback):
        text = str(candidate if candidate is not None else "").strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return "1"
        if text in {"0", "false", "no", "off"}:
            return "0"
    return "0"


def clean_admin_user(value: object, fallback: str) -> str:
    """The account that creates the schema, as MySQL will accept it.

    Defaulted to root because that is MySQL's own administrator and the bundled
    database's. A managed service names it something else --- `avnadmin`,
    `doadmin`, whatever was chosen when the instance was created --- and a study
    pointed at one authenticates as nobody until it is told which.
    """
    name = str(value or "").strip()
    if not name:
        return fallback or "root"
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,32}", name):
        raise SystemExit(
            "The administrator account may hold only letters, digits and . _ @ - "
            f"characters: {name!r}"
        )
    return name


def clean_placement(value: object, dataflow_choice: str, host: object) -> tuple[str, str]:
    """Where the database runs, refused here when the combination cannot be honoured.

    The pairing is the part worth refusing at the boundary. An external database with
    phones connecting to it directly would need that host reachable from every
    participant's network for the length of the study, and a researcher who chose it
    by accident finds out when the coverage grid stays empty.
    """
    chosen = str(value or placement.BUNDLED).strip().lower()
    if chosen not in placement.CHOICES:
        raise SystemExit(
            f"DB_PLACEMENT must be one of {', '.join(placement.CHOICES)}, not {chosen!r}"
        )

    named = str(host or "").strip()
    if chosen == placement.EXTERNAL and not named:
        raise SystemExit("DB_HOST is required when the database is external")
    if chosen == placement.BUNDLED:
        named = placement.DEFAULT_HOST
    elif placement.declared_for_host(named) == placement.BUNDLED:
        raise SystemExit(
            f"DB_HOST {named!r} names this deployment's own database, which is the "
            f"bundled placement. Give the address of the database you own, or choose "
            f"{placement.BUNDLED!r}."
        )

    reason = placement.unsupported_reason(chosen, dataflow_choice)
    if reason is not None:
        raise SystemExit(reason)
    return chosen, named


def clean_tls(
    placement_choice: str, require: object, ca_certificate: object
) -> tuple[bool, str]:
    """What this run asks of the connection, refused here when it cannot be honoured.

    Only a database the researcher names carries an answer. A bundled one is
    administered at both ends by this deployment, which generates the certificate and
    publishes the authority it signed with, so an answer arriving for it is a form
    field that was never asked rather than a decision to apply.

    A certificate that cannot be read is refused at the boundary rather than stored.
    Devices build their trust store from what a study publishes and treat an
    unreadable authority as a database they cannot reach, so a half-copied paste
    would stop every upload --- and finding that out here costs a corrected paste
    instead of a study that enrols and collects nothing.
    """
    if placement_choice != placement.EXTERNAL:
        return True, ""

    text = str(require if require is not None else "1").strip().lower()
    encrypted = text not in {"0", "false", "no", "off"}
    if not encrypted:
        return False, ""

    supplied = str(ca_certificate or "").strip()
    if not supplied:
        return True, ""
    cleaned = read_certificate(supplied)
    if not cleaned:
        raise SystemExit(
            "The database certificate authority is not a certificate this deployment "
            "can read. Paste the whole file, from -----BEGIN CERTIFICATE----- to "
            "-----END CERTIFICATE-----, or leave it empty to connect encrypted "
            "without verifying the server."
        )
    return True, cleaned


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: write_request_env.py <output-path>")

    output_path = pathlib.Path(sys.argv[1])
    payload = json.load(sys.stdin)
    env_fallback = parse_env_text(str(payload.get("env", "")))

    # A connection string pasted into the host field is used rather than refused:
    # it is what the provider hands out, and it carries the port, the account and
    # the password with it. Read first, so everything below sees the parts.
    pasted = parse_connection_string(payload.get("db_host"))
    if pasted:
        payload = dict(payload)
        payload["db_host"] = pasted["host"]
        if pasted.get("port"):
            payload["db_port"] = pasted["port"]
        if pasted.get("admin_user"):
            payload["db_admin_user"] = pasted["admin_user"]
        # The typed password wins: somebody who filled the field meant it, and a
        # string copied from a console may be older than the password they set.
        if pasted.get("admin_password") and not str(
            payload.get("mysql_root_password") or ""
        ).strip():
            payload["mysql_root_password"] = pasted["admin_password"]

    # The account that administers the database this study names, whichever server
    # that is. Kept apart from the bundled container's own root password: that one is
    # baked into its data directory at first start and cannot be retyped, so a field
    # serving both overwrote the value the bundled server still needed the moment a
    # researcher named somebody else's.
    db_admin_password = (
        str(
            payload.get(
                "mysql_root_password",
                env_fallback.get(
                    database.ADMIN_PASSWORD_ENV,
                    env_fallback.get("MYSQL_ROOT_PASSWORD", "CHANGE_ME"),
                ),
            )
        ).strip()
        or "CHANGE_ME"
    )
    public_host = str(payload.get("public_host", env_fallback.get("PUBLIC_HOST", ""))).strip()
    public_port = (
        str(payload.get("public_port", env_fallback.get("PUBLIC_PORT", "80"))).strip()
        or "80"
    )
    protocol = (
        str(payload.get("protocol", env_fallback.get("PROTOCOL", "http"))).strip().lower()
        or "http"
    )
    android_dataflow = clean_dataflow(
        payload.get("android_dataflow"),
        env_fallback.get("ANDROID_DATAFLOW", ""),
    )
    db_placement, db_host = clean_placement(
        payload.get("db_placement", env_fallback.get("DB_PLACEMENT", "")),
        android_dataflow,
        payload.get("db_host", env_fallback.get("DB_HOST", "")),
    )
    # Settled by the placement where the placement owns it. A study moving back onto
    # the bundled database takes that database's port along with its host; keeping the
    # one still in the form points every service, and the micro-server's config, at a
    # port on this deployment that nothing listens on.
    db_port = (
        placement.DEFAULT_PORT
        if db_placement == placement.BUNDLED
        else positive_int(
            payload.get("db_port"),
            env_fallback.get("DB_PORT", str(placement.DEFAULT_PORT)),
        )
    )
    # Named by the study, then by what the host says about its provider, and only
    # then by MySQL's own default. A managed database is not root, and a
    # researcher deploying for the first time has no reason to know that.
    db_admin_user = clean_admin_user(
        payload.get("db_admin_user"),
        database.admin_user(db_host, env_fallback.get("DB_ADMIN_USER", "")),
    )
    db_init = clean_db_init(payload.get("db_init"), env_fallback.get("DB_INIT", "auto"))
    # What travels with the study, each asked rather than assumed. A move changes
    # which database is written to next; the rows already written and the job that
    # copies them are two separate decisions about somebody else's server, and both
    # are no until the researcher says otherwise.
    db_keep_backups = clean_flag(
        payload.get("db_keep_backups"), env_fallback.get("DB_KEEP_BACKUPS", "")
    )
    # Asked for one run rather than remembered: a copy is done once, and a deployment
    # that kept the answer would offer to repeat it on every redeploy.
    db_carry_data = clean_flag(payload.get("db_carry_data"))
    db_require_tls, db_ca_certificate = clean_tls(
        db_placement,
        payload.get("db_require_tls", env_fallback.get("DB_REQUIRE_TLS", "")) or None,
        payload.get("db_ca_certificate"),
    )
    ssl_cert = str(
        payload.get(
            "ssl_certificate_path",
            env_fallback.get("SSL_CERTIFICATE_PATH", ""),
        )
    ).strip()
    ssl_key = str(
        payload.get(
            "ssl_certificate_key_path",
            env_fallback.get("SSL_CERTIFICATE_KEY_PATH", ""),
        )
    ).strip()

    researcher_username = str(payload.get("researcher_username", "")).strip()
    researcher_password = str(payload.get("researcher_password", "")).strip()
    participant_db_password = clean_participant_password(
        payload.get(
            "participant_db_password",
            env_fallback.get("PARTICIPANT_DB_PASSWORD", ""),
        )
    )
    backup_host_dir = clean_path(
        payload.get(
            "mysql_backup_host_dir",
            env_fallback.get("MYSQL_BACKUP_HOST_DIR", "./backups/mysql"),
        ),
        "./backups/mysql",
    )
    backup_interval_seconds = positive_int(
        payload.get(
            "mysql_backup_interval_seconds",
            env_fallback.get("MYSQL_BACKUP_INTERVAL_SECONDS", "86400"),
        ),
        "86400",
    )
    backup_retention_days = positive_int(
        payload.get(
            "mysql_backup_retention_days",
            env_fallback.get("MYSQL_BACKUP_RETENTION_DAYS", "30"),
        ),
        "30",
    )
    mysql_max_user_connections = positive_int(
        payload.get(
            "mysql_max_user_connections_per_account",
            env_fallback.get("MYSQL_MAX_USER_CONNECTIONS_PER_ACCOUNT", "100"),
        ),
        "100",
    )

    if not public_host:
        raise SystemExit("PUBLIC_HOST is required")

    lines = [
        f"{database.ADMIN_PASSWORD_ENV}={db_admin_password}",
        f"PUBLIC_HOST={public_host}",
        f"PUBLIC_PORT={public_port}",
        f"PROTOCOL={protocol}",
        f"ANDROID_DATAFLOW={android_dataflow}",
        f"DB_PLACEMENT={db_placement}",
        f"DB_HOST={db_host}",
        f"DB_ADMIN_USER={db_admin_user}",
        f"DB_INIT={db_init}",
        f"DB_KEEP_BACKUPS={db_keep_backups}",
        f"DB_CARRY_DATA={db_carry_data}",
        f"DB_PORT={db_port}",
        f"DB_REQUIRE_TLS={'1' if db_require_tls else '0'}",
        f"MYSQL_BACKUP_HOST_DIR={backup_host_dir}",
        f"MYSQL_BACKUP_INTERVAL_SECONDS={backup_interval_seconds}",
        f"MYSQL_BACKUP_RETENTION_DAYS={backup_retention_days}",
        f"MYSQL_MAX_USER_CONNECTIONS_PER_ACCOUNT={mysql_max_user_connections}",
    ]

    # Encoded because every line here is one setting and a PEM is several. Left out
    # entirely when there is none, so an empty field clears nothing a previous run
    # settled -- the study model is where an authority is cleared, and it is cleared
    # there by saving an empty one.
    if db_ca_certificate:
        lines.append(
            "DB_CA_CERTIFICATE_B64="
            + base64.b64encode(db_ca_certificate.encode("utf-8")).decode("ascii")
        )

    if researcher_username:
        lines.append(f"RESEARCHER_USERNAME={researcher_username}")
    if researcher_password:
        lines.append(f"RESEARCHER_PASSWORD={researcher_password}")
    # Left out when blank so the existing .env value survives; deploy_config
    # generates one only when neither source has a password.
    if participant_db_password:
        lines.append(f"PARTICIPANT_DB_PASSWORD={participant_db_password}")

    if protocol == "https":
        if ssl_cert:
            lines.append(f"SSL_CERTIFICATE_PATH={ssl_cert}")
        if ssl_key:
            lines.append(f"SSL_CERTIFICATE_KEY_PATH={ssl_key}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
