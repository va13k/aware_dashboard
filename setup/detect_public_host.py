import ipaddress
import socket
import shutil
import subprocess


def is_usable_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        address.is_loopback
        or address.is_unspecified
        or address.is_link_local
        or address.is_multicast
    )


def detect_via_udp() -> str | None:
    candidates = [
        (socket.AF_INET, ("192.0.2.1", 80)),
        (socket.AF_INET6, ("2001:db8::1", 80, 0, 0)),
    ]
    for family, target in candidates:
        try:
            sock = socket.socket(family, socket.SOCK_DGRAM)
            try:
                sock.connect(target)
                host = sock.getsockname()[0]
            finally:
                sock.close()
        except OSError:
            continue
        if is_usable_address(host):
            return host
    return None


def detect_via_hostname() -> str | None:
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, proto=socket.IPPROTO_TCP)
    except OSError:
        return None

    ipv4_candidates: list[str] = []
    ipv6_candidates: list[str] = []
    for family, _socktype, _proto, _canonname, sockaddr in infos:
        host = sockaddr[0]
        if not is_usable_address(host):
            continue
        if family == socket.AF_INET:
            ipv4_candidates.append(host)
        elif family == socket.AF_INET6:
            ipv6_candidates.append(host)

    if ipv4_candidates:
        return ipv4_candidates[0]
    if ipv6_candidates:
        return ipv6_candidates[0]
    return None


def detect_via_commands() -> str | None:
    command_sets = [
        ("plain", ["ipconfig", "getifaddr", "en0"]),
        ("plain", ["ipconfig", "getifaddr", "en1"]),
        ("plain", ["hostname", "-I"]),
        ("ip-route", ["ip", "route", "get", "1.1.1.1"]),
    ]

    for mode, command in command_sets:
        if shutil.which(command[0]) is None:
            continue
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            continue
        output = f"{result.stdout}\n{result.stderr}"
        tokens = output.replace("\n", " ").split()
        if mode == "ip-route":
            for index, token in enumerate(tokens[:-1]):
                if token == "src":
                    candidate = tokens[index + 1]
                    if is_usable_address(candidate):
                        return candidate
            continue

        for token in tokens:
            if is_usable_address(token):
                return token
    return None


def main() -> None:
    detected = (
        detect_via_udp()
        or detect_via_commands()
        or detect_via_hostname()
        or "localhost"
    )
    print(detected)


if __name__ == "__main__":
    main()
