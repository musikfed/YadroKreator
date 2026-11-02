"""Restrict private image downloads to the explicitly trusted LAN.

This is a *network trust policy*, NOT user authentication. Anyone able to
access the trusted subnet can potentially export embedded Wi-Fi credentials.
The dashboard intentionally has no password yet. Do not open it to the WAN.
"""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit

# Huananzhi: web service listens on 192.168.0.100:62404. Only its local /24
# plus the local machine are permitted by default. Configure additional
# subnets deliberately via PEGINELAB_EXPORT_TRUSTED_NETWORKS.
DEFAULT_NETWORKS = ("127.0.0.0/8", "::1/128", "192.168.0.0/24")


def permitted_networks() -> tuple:
    supplied = os.environ.get("PEGINELAB_EXPORT_TRUSTED_NETWORKS", "")
    sources = [item.strip() for item in supplied.split(",")] if supplied else DEFAULT_NETWORKS
    networks = []
    for source in sources:
        if not source:
            continue
        try:
            network = ipaddress.ip_network(source, strict=True)
        except ValueError:
            # Fail closed instead of silently opening access.
            return ()
        if network.prefixlen == 0:
            return ()
        networks.append(network)
    return tuple(networks)


def allow_private_export(req) -> bool:
    """Check the actual TCP peer, not untrusted proxy forwarding headers."""
    try:
        address = ipaddress.ip_address(req.remote_addr or "")
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
    except ValueError:
        return False

    # Never trust forwarded-client IPs. The service is directly bound to LAN.
    # Reverse proxies need an independently authenticated export integration.
    for name in ("Forwarded", "X-Forwarded-For", "X-Real-IP"):
        if req.headers.get(name):
            return False

    if not any(address in network for network in permitted_networks()
               if address.version == network.version):
        return False

    # Normal browsers send Origin on same-origin POST. A mismatched Origin
    # is an obvious cross-site request; the application also requires its
    # X-PegineLab-Action header to reject browser form CSRF.
    origin = req.headers.get("Origin", "")
    if origin:
        parsed = urlsplit(origin)
        if (parsed.scheme not in ("http", "https") or
            parsed.netloc != req.host or
            parsed.scheme != req.scheme):
            return False
    return True
