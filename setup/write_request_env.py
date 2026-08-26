import json
import pathlib
import re
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
from shared_config import dataflow  # noqa: E402

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


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: write_request_env.py <output-path>")

    output_path = pathlib.Path(sys.argv[1])
    payload = json.load(sys.stdin)
    env_fallback = parse_env_text(str(payload.get("env", "")))

    mysql_root_password = (
        str(
            payload.get(
                "mysql_root_password",
                env_fallback.get("MYSQL_ROOT_PASSWORD", "CHANGE_ME"),
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
        f"MYSQL_ROOT_PASSWORD={mysql_root_password}",
        f"PUBLIC_HOST={public_host}",
        f"PUBLIC_PORT={public_port}",
        f"PROTOCOL={protocol}",
        f"ANDROID_DATAFLOW={android_dataflow}",
        f"MYSQL_BACKUP_HOST_DIR={backup_host_dir}",
        f"MYSQL_BACKUP_INTERVAL_SECONDS={backup_interval_seconds}",
        f"MYSQL_BACKUP_RETENTION_DAYS={backup_retention_days}",
        f"MYSQL_MAX_USER_CONNECTIONS_PER_ACCOUNT={mysql_max_user_connections}",
    ]

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
