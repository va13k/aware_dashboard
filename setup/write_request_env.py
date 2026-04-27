import json
import pathlib
import sys


def parse_env_text(env_text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in str(env_text).splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


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

    if not public_host:
        raise SystemExit("PUBLIC_HOST is required")

    lines = [
        f"MYSQL_ROOT_PASSWORD={mysql_root_password}",
        f"PUBLIC_HOST={public_host}",
        f"PUBLIC_PORT={public_port}",
        f"PROTOCOL={protocol}",
    ]

    if researcher_username:
        lines.append(f"RESEARCHER_USERNAME={researcher_username}")
    if researcher_password:
        lines.append(f"RESEARCHER_PASSWORD={researcher_password}")

    if protocol == "https":
        if ssl_cert:
            lines.append(f"SSL_CERTIFICATE_PATH={ssl_cert}")
        if ssl_key:
            lines.append(f"SSL_CERTIFICATE_KEY_PATH={ssl_key}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
