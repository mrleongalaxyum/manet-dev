# MANET Change History

## 2026-04-17 (session 2)

### Radio driver mapping (confirmed on all 4 nodes — identical layout)

| Interface | Driver       | Band/Tech         | Role in bat0 |
|-----------|--------------|-------------------|--------------|
| wlan0     | mt7915e (PCIe) | 2.4 GHz          | mesh slave   |
| wlan1     | mt7915e (PCIe) | 5 GHz            | mesh slave   |
| wlan2     | morse_usb (USB)| 900 MHz S1G/HaLow| mesh slave   |
| wlan3     | brcmfmac (SDIO)| 2.4 GHz (AP only)| NOT in bat0  |

All 3 mesh radios (wlan0/wlan1/wlan2) are active in bat0 on every provisioned node.
wlan3 (brcmfmac) is the onboard RPi WiFi chip — used for AP mode only, never enslaved to bat0.

### Full mesh status (2026-04-17 evening — all ethernet disconnected except 7946)

All 4 nodes provisioned from rpi5-install tarball (including 78f7 — no longer a reference node).
All confirmed in mesh with 9 neighbours each (3 per radio) and 3 originators:
- **mesh-78f3** (192.168.1.198 / mesh 10.30.2.226): bat0_if=wlan0+wlan1+wlan2, 9 neighbours
- **mesh-78f7** (192.168.1.53 / mesh 10.30.2.6): bat0_if=wlan0+wlan1+wlan2, 9 neighbours
- **mesh-f86f** (192.168.1.51 / mesh 10.30.2.182): bat0_if=wlan0+wlan1+wlan2, 9 neighbours
- **mesh-7946** (192.168.1.50 / mesh 10.30.2.160): bat0_if=wlan0+wlan1+wlan2, 9 neighbours, gateway (has ethernet)

Internet routing: nodes without ethernet route via `default via 10.30.2.160 dev br0` (7946 mesh gateway).
Dynamic gateway works: whichever node has ethernet becomes `batctl gw_mode server`, others auto-detect and route through it.

### Bugs fixed this session

- **SAE MESH-SAE-AUTH-BLOCKED causing bat0 to be empty at boot**: wpa_supplicant blocks a peer for 300s after 4 SAE failures. On fresh boot, batman-enslave finds no mesh peers → wlan0/wlan1 never added to bat0. Fix: added `sae-watchdog.service` which monitors journald for MESH-SAE-AUTH-BLOCKED events and restarts wpa_supplicant + batman-enslave when bat0 is missing interfaces.
- **`systemctl restart systemd-networkd` in networkd-dispatcher scripts**: On newly provisioned nodes, the no-carrier/off/degraded dispatcher scripts used `systemctl restart systemd-networkd` instead of `networkctl reload && networkctl reconfigure end0`. Full networkd restart evicts wlan0/wlan1 from bat0 on every ethernet unplug. Fixed by syncing correct scripts from mesh-78f3.
- **Stale br0 IPs accumulating across reboots**: Each reboot where a node gets a different chunk left the old IPs on br0 (never cleaned up). Other nodes pinging those IPs got local replies, breaking `gateway-route-manager` reachability checks and preventing default route installation. Fix: added `cleanup_stale_br0_ips()` to `mesh-ip-manager.sh` which removes all mesh-subnet IPs from br0 that don't belong to the current persistent chunk on startup.

### New files added to rpi5-install

- `usr/local/bin/sae-watchdog.sh` — SAE block recovery watchdog
- `etc/systemd/system/sae-watchdog.service` — systemd unit
- `etc/systemd/system/multi-user.target.wants/sae-watchdog.service` — enable symlink
- `etc/networkd-dispatcher/carrier.d/50-ethernet-detect` — synced from mesh-78f3



## 2026-04-17

### Script sync
- Pulled scripts from mesh-78f3 (192.168.1.198) and mesh-78f7 (192.168.1.53) and compared against local rpi5-install tarball
- Updated scripts in rpi5-install from reference node mesh-78f7: `gateway-route-manager.sh`, `radio-setup.sh`, `ethernet-autodetect.sh`, `mesh-ip-manager.sh`
- Created per-node live snapshots: `rpi5/rpi5-live/78f3/`, `rpi5/rpi5-live/78f7/`

### Bugs found
- **ethernet-autodetect.sh** (mesh-78f3): contained spurious line `systemctl restart systemd-networkd 2>/dev/null || true` (l.102) — not present on reference node mesh-78f7, removed from rpi5-install
- **mesh-ip-manager.sh**: differed between mesh-78f3 and mesh-78f7 — updated to mesh-78f7 version
- **tarball prefix bug**: tarball was built from parent directory (`tar -czf rpi5-install.tar.gz rpi5-install/`), causing extraction to `/rpi5-install/` instead of `/` on the node. Fixed by building from inside the directory (`cd rpi5-install && tar -czf ../rpi5-install.tar.gz .`)
