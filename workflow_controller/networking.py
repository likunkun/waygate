from __future__ import annotations

import os
import socket


WILDCARD_HOSTS = {'', '0.0.0.0', '::', '[::]'}


def detect_primary_ip_address() -> str:
    """Return the primary outbound IPv4 address for browser-facing URLs."""
    for target in ('8.8.8.8', '1.1.1.1'):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((target, 80))
                candidate = str(sock.getsockname()[0]).strip()
        except OSError:
            continue
        if _is_routable_display_candidate(candidate):
            return candidate

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM):
            candidate = str(info[4][0]).strip()
            if _is_routable_display_candidate(candidate):
                return candidate
    except OSError:
        pass

    return '127.0.0.1'


def browser_display_host(bind_host: str | None, *, display_host: str | None = None) -> str:
    explicit_display_host = (display_host or os.environ.get('WAYGATE_DISPLAY_HOST') or '').strip()
    if explicit_display_host:
        return _strip_ipv6_brackets(explicit_display_host)

    normalized_bind_host = _strip_ipv6_brackets((bind_host or '').strip())
    if normalized_bind_host in WILDCARD_HOSTS:
        return detect_primary_ip_address()
    return normalized_bind_host


def url_host(host: str) -> str:
    normalized = _strip_ipv6_brackets(host.strip())
    if ':' in normalized and not normalized.startswith('['):
        return f'[{normalized}]'
    return normalized


def _strip_ipv6_brackets(host: str) -> str:
    if host.startswith('[') and host.endswith(']'):
        return host[1:-1]
    return host


def _is_routable_display_candidate(host: str) -> bool:
    if not host or host in WILDCARD_HOSTS:
        return False
    if host.startswith('127.'):
        return False
    if host == 'localhost':
        return False
    return True
