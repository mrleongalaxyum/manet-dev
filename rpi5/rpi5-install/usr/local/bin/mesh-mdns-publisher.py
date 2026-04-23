#!/usr/bin/env python3
import ipaddress
import os
import re
import socket
import subprocess
import sys
import time

from zeroconf import IPVersion, ServiceInfo, Zeroconf

REGISTRY_FILE = "/var/run/mesh_node_registry"
MESH_CONF_FILE = "/etc/mesh.conf"
CONTROL_IFACE = "br0"
STALE_NODE_THRESHOLD = 600
POLL_INTERVAL = 10


def log(msg: str) -> None:
    print(f"[MESH-MDNS-PUB] {msg}", flush=True)


def local_br0_ip() -> str:
    out = subprocess.run(
        ["ip", "-4", "-o", "addr", "show", "dev", CONTROL_IFACE, "scope", "global"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            return parts[3].split("/")[0]
    return ""


def host_min_ip() -> str:
    try:
        with open(MESH_CONF_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("ipv4_network="):
                    cidr = line.split("=", 1)[1].strip()
                    network = ipaddress.ip_network(cidr, strict=False)
                    return str(next(network.hosts()))
    except Exception:
        return ""
    return ""


def service_vip(offset: int) -> str:
    first = host_min_ip()
    if not first:
        return ""
    octets = first.split(".")
    octets[-1] = str(int(octets[-1]) + offset)
    return ".".join(octets)


def service_active(flag_suffix: str) -> bool:
    if not os.path.exists(REGISTRY_FILE):
        return False
    now = int(time.time())
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = f.read().splitlines()
    except Exception:
        return False

    nodes = {}
    for line in data:
        m = re.match(r"^NODE_([0-9A-Fa-f]+)_(.+)='(.*)'$", line)
        if not m:
            continue
        node_id, key, value = m.groups()
        nodes.setdefault(node_id, {})[key] = value

    for node in nodes.values():
        if node.get(flag_suffix) != "true":
            continue
        if node.get("NODE_STATE", "ACTIVE") != "ACTIVE":
            continue
        ts = int(node.get("LAST_SEEN_TIMESTAMP", "0") or "0")
        if now - ts > STALE_NODE_THRESHOLD:
            continue
        if node.get("IPV4_ADDRESS"):
            return True
    return False


def make_info(instance: str, service_type: str, hostname: str, addr: str, port: int) -> ServiceInfo:
    return ServiceInfo(
        service_type,
        f"{instance}.{service_type}",
        addresses=[socket.inet_aton(addr)],
        port=port,
        properties={},
        server=f"{hostname}.",
    )


def main() -> int:
    local_ip = local_br0_ip()
    if not local_ip:
        log("No br0 IPv4 address found")
        return 1

    zc = Zeroconf(interfaces=[local_ip], ip_version=IPVersion.V4Only)
    registered = {}

    def sync_service(name: str, should_exist: bool, info_factory):
        nonlocal registered
        if should_exist and name not in registered:
            info = info_factory()
            zc.register_service(info)
            registered[name] = info
            log(f"registered {name}")
        elif should_exist and name in registered:
            new_info = info_factory()
            old_info = registered[name]
            if old_info.addresses != new_info.addresses or old_info.port != new_info.port or old_info.server != new_info.server:
                zc.unregister_service(old_info)
                zc.register_service(new_info)
                registered[name] = new_info
                log(f"updated {name}")
        elif not should_exist and name in registered:
            zc.unregister_service(registered[name])
            del registered[name]
            log(f"unregistered {name}")

    try:
        while True:
            mumble_ip = service_vip(2)
            mtx_ip = service_vip(1)
            sync_service(
                "mumble",
                bool(mumble_ip) and service_active("IS_MUMBLE_SERVER"),
                lambda: make_info("Mumble", "_mumble._tcp.local.", "mumble.local", mumble_ip, 64738),
            )
            sync_service(
                "mtx",
                bool(mtx_ip) and service_active("IS_MEDIAMTX_SERVER"),
                lambda: make_info("MediaMTX", "_rtsp._tcp.local.", "mtx.local", mtx_ip, 8554),
            )
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        for info in list(registered.values()):
            try:
                zc.unregister_service(info)
            except Exception:
                pass
        zc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
