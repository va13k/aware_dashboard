import ipaddress
import json
import re
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


def is_private_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return isinstance(address, ipaddress.IPv4Address) and address.is_private


def is_preferred_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return (
        isinstance(address, ipaddress.IPv4Address)
        and is_usable_address(value)
        and not address.is_loopback
        and not address.is_link_local
    )


def score_candidate(address: str, adapter_name: str = "") -> tuple[int, int, str]:
    name = adapter_name.strip().lower()
    private_bonus = 2 if is_private_ipv4(address) else 0
    ipv4_bonus = 1 if is_preferred_ipv4(address) else 0

    penalty_keywords = (
        "docker",
        "wsl",
        "hyper-v",
        "vethernet",
        "virtual",
        "vmware",
        "vbox",
        "loopback",
        "tailscale",
        "zerotier",
        "vpn",
        "tunnel",
        "bluetooth",
    )
    penalty = -2 if any(keyword in name for keyword in penalty_keywords) else 0
    return (private_bonus + ipv4_bonus + penalty, ipv4_bonus, address)


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


def detect_via_windows_netipconfiguration() -> str | None:
    if shutil.which("powershell") is None:
        return None

    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-NetIPConfiguration | "
            "Where-Object { $_.NetAdapter.Status -eq 'Up' -and $_.IPv4Address } | "
            "ForEach-Object { "
            "  [PSCustomObject]@{ "
            "    InterfaceAlias = $_.InterfaceAlias; "
            "    IPv4DefaultGateway = @($_.IPv4DefaultGateway | Select-Object -ExpandProperty NextHop); "
            "    IPv4Address = @($_.IPv4Address | Select-Object -ExpandProperty IPAddress) "
            "  } "
            "} | ConvertTo-Json -Compress"
        ),
    ]

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    if result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    if isinstance(payload, dict):
        payload = [payload]

    preferred: list[tuple[tuple[int, int, str], str]] = []
    fallback: list[tuple[tuple[int, int, str], str]] = []
    for item in payload:
        interface_alias = str(item.get("InterfaceAlias", "")).strip()
        has_gateway = bool(item.get("IPv4DefaultGateway"))
        for address in item.get("IPv4Address", []) or []:
            if not is_preferred_ipv4(address):
                continue
            scored = (score_candidate(address, interface_alias), address)
            if has_gateway:
                preferred.append(scored)
            else:
                fallback.append(scored)

    if preferred:
        return max(preferred, key=lambda item: item[0])[1]
    if fallback:
        return max(fallback, key=lambda item: item[0])[1]
    return None


def detect_via_windows_ipconfig() -> str | None:
    if shutil.which("ipconfig") is None:
        return None

    try:
        result = subprocess.run(
            ["ipconfig"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    output = f"{result.stdout}\n{result.stderr}"
    adapter_name = ""
    has_gateway = False
    candidates: list[tuple[tuple[int, int, str], bool, str]] = []

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            adapter_name = ""
            has_gateway = False
            continue

        if line.endswith(":") and "adapter" in line.lower():
            adapter_name = line.strip(" :")
            has_gateway = False
            continue

        if "Default Gateway" in line and ":" in line:
            gateway_value = line.split(":", 1)[1].strip()
            has_gateway = bool(gateway_value)
            continue

        match = re.search(r"IPv4 Address[^\:]*:\s*([0-9.]+)", line)
        if not match:
            continue

        address = match.group(1).strip()
        if not is_preferred_ipv4(address):
            continue

        candidates.append((score_candidate(address, adapter_name), has_gateway, address))

    gateway_matches = [item for item in candidates if item[1]]
    if gateway_matches:
        return max(gateway_matches, key=lambda item: item[0])[2]
    if candidates:
        return max(candidates, key=lambda item: item[0])[2]
    return None


def main() -> None:
    detected = (
        detect_via_windows_netipconfiguration()
        or detect_via_windows_ipconfig()
        or detect_via_udp()
        or detect_via_commands()
        or detect_via_hostname()
        or "localhost"
    )
    print(detected)


if __name__ == "__main__":
    main()
