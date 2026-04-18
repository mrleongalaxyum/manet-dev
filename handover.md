# MANET Project Handover

## System Overview

**4-node RPi5 MANET** (Mobile Ad-hoc NETwork) using batman-adv layer-2 mesh routing over 3 radios per node:

| Interface | Driver     | Band          | Role           |
|-----------|------------|---------------|----------------|
| wlan0     | mt7915e    | 2.4 GHz       | batman-adv mesh slave |
| wlan1     | mt7915e    | 5 GHz         | batman-adv mesh slave |
| wlan2     | morse_usb  | 900 MHz HaLow | batman-adv mesh slave |
| wlan3     | brcmfmac   | 2.4 GHz       | AP only (EUDs), NOT in bat0 |

batman-adv aggregates all 3 radios into `bat0`. `bat0` is bridged into `br0`. Each node gets a `/24` chunk of `10.30.2.0/24` via `node-manager.sh` (alfred-based gossip). All 4 nodes currently have ethernet (`end0`) — in normal field deployment only one node has ethernet and becomes the mesh gateway (`batctl gw_mode server`); others route `default via bat0`.

**Current active branch:** `admin-panel-mdns`

---

## Colorado SFTP Server

- **Host:** www.colorado-governor.com
- **Port:** 11238
- **User:** clanker
- **Protocol:** SFTP
- **Private key** (save to file, chmod 600):

```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACCnNETHB0/u45sU67/gxRlgRk10+sJOZp+3W2YDYlBmUgAAAKCoL4EoqC+B
KAAAAAtzc2gtZWQyNTUxOQAAACCnNETHB0/u45sU67/gxRlgRk10+sJOZp+3W2YDYlBmUg
AAAEAUxp+UL8DvbQaBtsGRgs9309eWPPpdYzubfZYqzZ0ZWqc0RMcHT+7jmxTrv+DFGWBG
TXT6wk5mn7dbZgNiUGZSAAAAFmNsYW5rZXJAY29sb3JhZG8tbWFuZXQBAgMEBQYH
-----END OPENSSH PRIVATE KEY-----
```

- **Public key:** `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKc0RMcHT+7jmxTrv+DFGWBGTXT6wk5mn7dbZgNiUGZS clanker@colorado-manet`

**Connect:**
```bash
sftp -i .ssh/colorado-manet-key -P 11238 clanker@www.colorado-governor.com
```

---

## Ventum Upload Server

- **URL:** https://manet.ventum.hr/upload/
- **User:** clanker
- **Password:** really-strong-password-321

**Upload example:**
```bash
curl -u clanker:really-strong-password-321 -T <file> https://manet.ventum.hr/upload/rpi5/<file>
```

**Local server:** 192.168.1.131, user: leon, password: hobbyking. Files are served from `~/Desktop/MANET/manet/` inside a Docker nginx container. The `/upload/` endpoint maps to that same directory.

---

## LAN Devices

| WAN Port | Local IP       | Hostname  | SSH Port | Mesh IPs        | Notes          |
|----------|----------------|-----------|----------|-----------------|----------------|
| 3254     | 192.168.1.198  | mesh-78f3 | 22       | 10.30.2.x       | has ethernet   |
| 3255     | 192.168.1.51   | mesh-f86f | 22       | 10.30.2.160/161 | has ethernet   |
| 3256     | 192.168.1.53   | mesh-78f7 | 22       | 10.30.2.182/183 | has ethernet   |
| 3257     | 192.168.1.50   | mesh-7946 | 22       | 10.30.2.72/73   | has ethernet   |

- **User:** radio
- **Password:** raspberry

**All 4 nodes currently have ethernet** (dev/lab setup). In field deployment, only one node has ethernet and acts as gateway. To SSH into any node:

```bash
ssh radio@192.168.1.50   # mesh-7946
ssh radio@192.168.1.51   # mesh-f86f
ssh radio@192.168.1.53   # mesh-78f7
ssh radio@192.168.1.198  # mesh-78f3
```

If a node is mesh-only (no ethernet), jump via a node that has ethernet:
```bash
ssh -J radio@192.168.1.50 radio@10.30.2.182   # reach mesh-78f7 via mesh
ssh -J radio@192.168.1.50 radio@10.30.2.160   # reach mesh-f86f via mesh
```

---

## Repository and Scripts

- **GitHub:** https://github.com/mrleongalaxyum/manet-dev (private)
- **Active branch:** `admin-panel-mdns`
- `rpi5/rpi5-install/` — install package (all 4 nodes provisioned from this)
- `rpi5/rpi5-live/78f3/` and `rpi5/rpi5-live/78f7/` — live script snapshots from nodes (taken 2026-04-17, before full reprovision — for reference only)
- `rpi5/rpi5-install.tar.gz` — built tarball, uploaded to Ventum (`/manet/rpi5/rpi5-install.tar.gz`) and available on Colorado SFTP (`/rpi5/rpi5-install.tar.gz`)

### Key scripts (all under `rpi5/rpi5-install/usr/local/bin/`)

| Script | Purpose |
|--------|---------|
| `radio-setup.sh` | Provisioning: detects radios, writes all wpa_supplicant configs, creates systemd units, sets hostname, enables I2C. Re-runnable. |
| `batman-if-setup.sh` | Enslaves wlan0/wlan1/wlan2 to bat0 at boot (HaLow first, then standard). |
| `node-manager-static.sh` | Static channel mode: publishes node status via alfred, runs service elections. |
| `node-manager-acs.sh` | ACS channel mode: same as static but with channel scanning/selection. |
| `gateway-route-manager.sh` | Installs/removes default route via bat0 based on gateway announcements. |
| `mesh-ip-manager.sh` | IP chunk allocation library (used by node-manager). |
| `ethernet-autodetect.sh` | Detects ethernet plug/unplug and promotes/demotes node as mesh gateway. |
| `sae-watchdog.sh` | Monitors for SAE auth blocks and restarts wpa_supplicant if bat0 loses interfaces. |
| `battery-reader.py` | Reads Waveshare UPS HAT (E) IP2368 MCU at I2C `0x2D` every 30s. Writes `/run/battery_status.json`. Triggers poweroff if any cell < 3150 mV while discharging. |
| `mesh-status.py` | Web admin panel on **port 80**. Shows topology canvas, local battery fuel gauge + peer battery % from alfred registry. Peer proxy fetch via `/api/peer/<ip>`. |

### Systemd unit names (post-reprovisioning)

After reprovisioning with the current tarball, unit names are:
- `batman-enslave.service` (NOT `batman-if-setup.service`)
- `node-manager.service` (NOT `node-manager-static.service`)

Check with: `systemctl status batman-enslave node-manager`

### Config files on nodes (generated by radio-setup.sh, not in repo)

- `/etc/mesh.conf` — node config (mesh_ssid, mesh_key, regulatory_domain, halow_regulatory_domain, eud mode, etc.)
- `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` — 2.4 GHz mesh, no `country=` line
- `/etc/wpa_supplicant/wpa_supplicant-wlan1.conf` — 5 GHz mesh, no `country=` line
- `/etc/wpa_supplicant/wpa_supplicant-wlan2-s1g.conf` — HaLow S1G, `country="EU"` (quoted), `op_class=66`, `channel=5` (865.5 MHz)
- `/etc/modprobe.d/morse.conf` — morse driver options including `country=EU`
- `/etc/modprobe.d/cfg80211.conf` — `options cfg80211 ieee80211_regdom=EU`

### AP interface

AP interface (non-mesh, for EUD hotspot) varies per node — stored at runtime in `/var/lib/ap_interface`. Non-mesh interfaces listed in `/var/lib/no_mesh_if`. Do **not** assume `wlan3` — always read from these files.

### mDNS — manet.local

EUD clients connected to the node's AP can open `http://manet.local` to reach the admin panel (port 80).

**Implementation:** dnsmasq (already the EUD DNS server via DHCP option 6) answers `manet.local` queries with the node's own IP. This is set in `/etc/dnsmasq.d/mesh-eud.conf` as `address=/manet.local/<gateway_ip>`, written by `mesh-ip-manager.sh` when the node gets its IP chunk.

- No avahi dependency for name resolution — dnsmasq handles it directly
- avahi-daemon is still installed and restricted to the AP interface (`allow-interfaces=<ap_if>` from `/var/lib/no_mesh_if`) to avoid hostname conflicts over the shared mesh L2 domain
- Source files in tarball: `usr/local/share/manet/avahi-daemon.conf` and `manet-http.service`

**Why not avahi alone:** All nodes share `br0` L2 (bat0 is bridged into br0). Avahi on br0 causes hostname conflicts (`manet-2`, `manet-3`...). Avahi on `wlan3` alone has no IPv4 (bridge slave). dnsmasq is the correct layer.

### Admin panel (mesh-status.py) — features

- **Port:** 80 (passed via argv in systemd unit — the `PORT` constant in the script defaults to 8080 but is overridden)
- **Peer proxy fetch:** `/api/peer/<ip>` endpoint fetches `/api/local` from a peer node on port 80 and returns JSON. Used by the UI to show remote node details.
- **Drawer — always visible:** Top of side panel always shows a node detail drawer. Default: local node ("★ THIS NODE"). Click neighbor on canvas or in list → shows that neighbor (fetched via proxy). Click central node → returns to local. Clicking any node auto-scrolls side panel to top.
- **Canvas highlight:** Selected node gets white border + large bright glow. Local node is highlighted by default (while no neighbor is selected).
- **THIS NODE badge:** Local node highlighted with purple "THIS NODE" badge in the node list.
- **Drag handle**: visible pill between topology canvas and info panel on mobile (≤768px). Drag up to expand info panel to full screen.
- **Pinch-to-zoom**: canvas supports pinch zoom (0.3×–5×) and pan.
- **EUD AP health**: `/var/lib/no_mesh_if` is read at runtime to exclude AP interfaces from bat0/wpa_supplicant checks.

### Known live deviations from repo (as of 2026-04-18)

- **wpa_supplicant@wlan0 and wpa_supplicant@wlan1 are stopped** on all nodes — temporary dev state for HaLow-only testing. Not a persistent config change. Re-enable with `systemctl start wpa_supplicant@wlan0 wpa_supplicant@wlan1`.
- **All 4 nodes have ethernet** in current lab setup — in the field only one node has ethernet. `ethernet-autodetect.service` should only run on the node with actual ethernet; starting it on a node without cable causes routing issues.
- **mesh-78f3 HAT had cold solder joints** on GPIO header — I2C bus was completely empty. Resolved by resoldering. Verify with `sudo i2cdetect -y 1` (should show `2d`).

### Battery monitoring (UPS HAT E)

All nodes have Waveshare UPS HAT (E) with IP2368 MCU at I2C `0x2D`. INA219 at `0x40` is **not** directly accessible — all data comes from the MCU.

**I2C enable requirements (RPi5):**
1. `dtparam=i2c_arm=on` in `/boot/firmware/config.txt` — use exact-match sed, fallback to `/boot/config.txt` for pre-Bookworm
2. `i2c-dev` in `/etc/modules`
3. **Reboot required** — modprobe alone doesn't create `/dev/i2c-1` on RPi5

**Verify:** `sudo i2cdetect -y 1` should show `2d`. Then check `cat /run/battery_status.json`.

**Shutdown trigger:** any cell voltage < 3150 mV while discharging → `systemctl poweroff`.

**Battery data in mesh:** `node-manager-*.sh` reads `/run/battery_status.json` and passes `--battery-percentage` to `encoder.py` → alfred gossip type 68 → visible in `mesh-status.py` peer cards.

**IMPORTANT — tarball packaging:** The tarball must be built from inside the `rpi5-install/` directory so it extracts directly to `/` on the node:
```bash
cd rpi5/rpi5-install && tar -czf ../rpi5-install.tar.gz .
```
Building from the parent directory creates a prefix folder and scripts end up at `/rpi5-install/` instead of `/`.

### Provisioning a new node

1. Flash SD with base Raspberry Pi OS image
2. Download tarball from Ventum: `curl -u clanker:really-strong-password-321 https://manet.ventum.hr/upload/rpi5/rpi5-install.tar.gz | tar -xzf - -C /`
3. Edit `/etc/mesh.conf` with node-specific settings (especially `regulatory_domain`, `halow_regulatory_domain`)
4. Run `/usr/local/bin/radio-setup.sh` (or reboot if firstrun service is enabled)

For change history and bug log see [history.md](history.md).
