import pathlib


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
    is_default_port = (protocol == "http" and port == 80) or (
        protocol == "https" and port == 443
    )
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
