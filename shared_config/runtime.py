import os
import pathlib
import tempfile

# Every generated file gets its mode stated explicitly, because the two writing
# styles in this project disagree by default: mkstemp() creates its file 0600
# and os.replace() carries that onto the destination, while Path.write_text()
# leaves an existing file's mode untouched. Without an explicit chmod a file's
# permissions end up decided by whichever writer ran last instead of by who has
# to read it, which silently breaks readers running as other users.
SHARED_MODE = 0o644  # nginx, the micro-server's appuser, or the host user reads it
SECRET_MODE = 0o600  # only the deploying user may read it


def set_descriptor_mode(fileno: int, mode: int) -> None:
    """State a mode on an open descriptor, where descriptors carry one.

    Unix answers with :func:`os.fchmod`. Windows keeps its permissions in access
    control lists rather than in a mode, and a bind mount there presents a file to a
    container with permissions its file sharing decides, so the file is left as
    :func:`tempfile.mkstemp` made it.

    One place, because both writers that state a mode go through it: the generated
    files, and the password a database client reads for the length of one query.
    """
    if hasattr(os, "fchmod"):
        os.fchmod(fileno, mode)


def atomic_write_text(path: pathlib.Path, text: str, mode: int = SECRET_MODE) -> None:
    """Write text to path atomically with an explicit permission mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    tmp_path = pathlib.Path(tmp_name)
    try:
        # The descriptor is handed to the file object first, so it is closed however
        # this ends. A mode stated on it before anything is written means the file
        # never exists carrying the wrong one, and names no path for anything to be
        # swapped at.
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            set_descriptor_mode(tmp.fileno(), mode)
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, path)
    finally:
        # Nothing to remove once the replace has happened, and the descriptor is
        # closed by the time this runs either way --- which is what lets Windows
        # remove a file at all.
        tmp_path.unlink(missing_ok=True)


def load_env(path: pathlib.Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def set_env_value(path: pathlib.Path, key: str, value: str) -> None:
    """Update a single key in an env file, leaving every other line untouched.

    Comments, ordering and unrelated keys are preserved, and the file is
    swapped into place atomically so a reader never sees a partial write. The
    key is appended when it is not already present.
    """
    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    replaced = False
    for index, line in enumerate(lines):
        if line.startswith("#") or "=" not in line:
            continue
        if line.split("=", 1)[0] == key:
            lines[index] = f"{key}={value}"
            replaced = True

    if not replaced:
        lines.append(f"{key}={value}")

    # .env holds the MySQL root password and researcher credentials.
    atomic_write_text(path, "\n".join(lines) + "\n", SECRET_MODE)


def strip_ipv6_brackets(host: str) -> str:
    value = str(host).strip()
    if value.startswith("[") and value.endswith("]"):
        return value[1:-1]
    return value


def host_for_url(host: str) -> str:
    value = strip_ipv6_brackets(host)
    if ":" in value and not value.startswith("["):
        return f"[{value}]"
    return value


def build_public_base_url(protocol: str, host: str, port: int) -> str:
    formatted_host = host_for_url(host)
    is_default_port = (protocol == "http" and port == 80) or (protocol == "https" and port == 443)
    base_url = f"{protocol}://{formatted_host}"
    if not is_default_port:
        base_url += f":{port}"
    return base_url


def normalize_public_env(env: dict[str, str]) -> dict[str, str]:
    normalized = dict(env)
    public_host = strip_ipv6_brackets(str(normalized.get("PUBLIC_HOST", "")).strip())
    protocol = str(normalized.get("PROTOCOL", "")).strip().lower()
    public_port = str(normalized.get("PUBLIC_PORT", "")).strip()
    cert_path = str(normalized.get("SSL_CERTIFICATE_PATH", "")).strip()
    cert_key_path = str(normalized.get("SSL_CERTIFICATE_KEY_PATH", "")).strip()

    if public_host in {"example.test", "CHANGE_ME"}:
        public_host = ""

    if protocol not in {"http", "https"}:
        protocol = "http"

    if protocol == "https" and (not cert_path or not cert_key_path):
        protocol = "http"
        public_port = "80"
        normalized.pop("SSL_CERTIFICATE_PATH", None)
        normalized.pop("SSL_CERTIFICATE_KEY_PATH", None)

    if not public_port:
        public_port = "443" if protocol == "https" else "80"

    if protocol == "http" and public_port == "443":
        public_port = "80"
    if protocol == "https" and public_port == "80":
        public_port = "443"

    if not public_host:
        raise ValueError("PUBLIC_HOST is required")

    normalized["PUBLIC_HOST"] = public_host
    normalized["PROTOCOL"] = protocol
    normalized["PUBLIC_PORT"] = public_port
    return normalized


def get_runtime_settings(env: dict[str, str]) -> dict[str, str | int]:
    protocol = env.get("PROTOCOL", "http")
    public_host = strip_ipv6_brackets(env.get("PUBLIC_HOST", "localhost"))
    public_port = int(env.get("PUBLIC_PORT", "443" if protocol == "https" else "80"))
    micro_database_host = str(env.get("MICRO_DATABASE_HOST", "mysql")).strip() or "mysql"
    android_database_host = (
        str(env.get("ANDROID_DATABASE_HOST", public_host)).strip() or public_host
    )
    external_server_host = build_public_base_url(protocol, public_host, public_port)

    return {
        "protocol": protocol,
        "public_host": public_host,
        "public_port": public_port,
        "micro_database_host": micro_database_host,
        "android_database_host": android_database_host,
        "external_server_host": external_server_host,
    }
