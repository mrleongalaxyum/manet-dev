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

## 2026-04-22 quick state

- `perf.local` now gets radio link summaries through Alfred gossip instead of direct cross-mesh polling.
- `manet.local` and `perf.local` were partially re-skinned to align with the FER brandbook:
  - shared FER token set for light/dark themes
  - `Roobert, Arial, sans-serif`
  - inline monochrome FER SVG mark embedded in both GUIs, no external image fetch
  - self/info states use FER deep blue, gateway/warn emphasis uses FER yellow
  - `manet.local` keeps a restrained FER-style yellow/blue glow in the topology area
- `manet.local` now exposes a `PERF.LOCAL` handoff button tied to the provisioned `admin_password`.
  - validation endpoint on `manet.local`: `POST /api/perf-auth`
  - persistent `perf.local` cookie: `manet_perf_auth`
  - direct unauthenticated visits to `perf.local` now show a small password page before proxying to the dashboard
- The `MANAGE` button on `manet.local` now redirects directly to `perf.local` with no intermediate prompt; auth happens only on the `perf.local` page.
- The `perf.local` password card was re-centered for mobile/small viewport rendering.
- `manet.local` mobile interaction was reworked:
  - one-finger touch no longer pans the topology canvas
  - whole-page scrolling is restored
  - topology keeps tap-to-select and two-finger pinch zoom
  - non-simulation redraws are now `requestAnimationFrame`-queued to reduce mobile stutter
  - layout uses a less rigid split-panel structure with fewer nested scroll containers
- HaLow GUI TX-power selection is now bandwidth-aware using a live-tested cap table:
  - `1 MHz -> 24 dBm`
  - `2 MHz -> 24 dBm`
  - `4 MHz -> 22 dBm`
  The dropdown clamps down when narrowing allowed power and re-exposes higher valid values when switching back.
- Current protobuf status payload includes compact per-interface TX/RX summaries for all mesh radios:
  - `wifi_24_tx_mcs`, `wifi_24_rx_mcs`
  - `wifi_5_tx_mcs`, `wifi_5_rx_mcs`
  - `halow_tx_mcs`, `halow_rx_mcs`
  - `halow_mcs_peer`
- Despite the field names, the carried values are now compact rate summaries, not just raw MCS numbers. Example: `MCS9 N1 SGI 20M`.
- Important compatibility note: do not blindly regenerate `NodeInfo_pb2.py` with a newer local `protoc` and deploy it. The node image currently has `python3-protobuf 4.21.12`; generated files that import `google.protobuf.runtime_version` will break both `encoder.py` and `decoder.py` on the nodes.

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

## Tarball distribution

Tarball releases are published as GitHub Release artifacts:
- **Latest:** https://github.com/mrleongalaxyum/manet-dev/releases/latest
- **Current:** https://github.com/mrleongalaxyum/manet-dev/releases/tag/v0.4-admin-panel-mdns

Also mirrored on Colorado SFTP: `/rpi5/rpi5-install.tar.gz`

**Local server (backup):** 192.168.1.131, user: leon, password: hobbyking. Files served from `~/Desktop/MANET/manet/` via Docker nginx. Upload: `curl -u clanker:really-strong-password-321 -T <file> https://manet.ventum.hr/upload/rpi5/<file>`

---

## LAN Devices

| WAN Port | Local IP       | Hostname  | SSH Port | Mesh IPs        | Notes          |
|----------|----------------|-----------|----------|-----------------|----------------|
| 3254     | 192.168.1.198  | mesh-78f3 | 22       | 10.30.2.28      | has ethernet   |
| 3255     | 192.168.1.51   | mesh-f86f | 22       | 10.30.2.204     | has ethernet   |
| 3256     | 192.168.1.53   | mesh-78f7 | 22       | 10.30.2.116     | has ethernet   |
| 3257     | 192.168.1.50   | mesh-7946 | 22       | 10.30.2.50      | has ethernet   |

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
ssh -J radio@192.168.1.53 radio@10.30.2.204   # reach mesh-f86f via mesh-78f7
ssh -J radio@192.168.1.53 radio@10.30.2.50    # reach mesh-7946 via mesh-78f7
ssh -J radio@192.168.1.53 radio@10.30.2.28    # reach mesh-78f3 via mesh-78f7
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
- **THIS NODE badge:** Local node highlighted with FER deep-blue "THIS NODE" badge in the node list.
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
2. Download tarball from GitHub releases: `curl -L https://github.com/mrleongalaxyum/manet-dev/releases/latest/download/rpi5-install.tar.gz | tar -xzf - -C /`
3. Edit `/etc/mesh.conf` with node-specific settings (especially `regulatory_domain`, `halow_regulatory_domain`)
4. Run `/usr/local/bin/radio-setup.sh` (or reboot if firstrun service is enabled)

For change history and bug log see [history.md](history.md).

### 2026-04-22 - FER logo asset

- Kanonski lokalni logo file je `/usr/local/share/manet/fer-logo.svg`.
- Taj file mora biti sinkan sa službenim FER SVG assetom s `https://www.fer.unizg.hr/_pub/themes_static/fer_2025/default/img/FERlogo.svg`.
- `mesh-status.py` i `perf-dashboard.py` serviraju isti lokalni asset preko `/assets/fer-logo.svg`; ne treba vraćati inline/generirani logo osim ako korisnik to izričito ne traži.

### 2026-04-22 - PERF navigation

- `perf-dashboard.py` header ima `OVERVIEW` gumb koji redirecta na `http://manet.local/`.
- Ako se header dalje mijenja, zadržati `OVERVIEW` i theme toggle u desnom actions bloku.

### 2026-04-22 - THIS NODE badge

- `mesh-status.py` koristi `.self-node-badge` za lokalni node u listi i detail headeru.
- Ne vraćati zvjezdicu uz `THIS NODE`; badge treba ostati suzdržan i u FER color schemi.

### 2026-04-22 - Touch behavior

- `mesh-status.py` topo canvas na touch uređajima više ne obrađuje single-finger tap selection.
- Jedan prst je rezerviran za page scroll; canvas touch interakcija ostaje samo za two-finger pinch zoom.

### 2026-04-22 - PERF logout flow

- `perf-dashboard.py` rendera `LOGOUT` gumb na dnu stranice.
- `mesh-status.py` obrađuje `/auth/perf-logout`, briše `manet_perf_auth` cookie i redirecta na `/auth/perf-login`.

### 2026-04-22 - FER logo theming

- Header lockup na `mesh-status.py` i `perf-dashboard.py` koristi veći FER logo nego prije.
- U light temi logo ostaje crn, a u dark temi se prikazuje bijelo.
- `render_perf_auth_page()` koristi veliki logo i `prefers-color-scheme` dark/light stilove.

### 2026-04-22 - PERF login sizing

- `render_perf_auth_page()` input i submit button koriste puni raspoloživi prostor bez overflowa.
- Ako se login layout dalje dira, zadržati `box-sizing: border-box` na form controls.

### 2026-04-22 - Theme handoff

- `mesh-status.py` i `perf-dashboard.py` čitaju `?theme=light|dark` i spremaju ga u isti `manetUiTheme` key za svoj origin.
- `MANAGE` i `OVERVIEW` redirecti prenose trenutni theme da login i drugi dashboard ostanu vizualno usklađeni.

### 2026-04-22 - Login CTA and logo block

- `render_perf_auth_page()` nema više accent pozadinu u `.top` bloku.
- Login CTA koristi FER žutu, ne plavu.
- Dashboard lockup prikazuje samo FER mark crop službenog SVG asseta.

### 2026-04-22 - Inline node detail

- `mesh-status.py` uklanja gornji `peer-drawer` i detalje rendera inline unutar selektiranog node reda.

### 2026-04-22 - Canvas click behavior

- Canvas click na `mesh-status.py` samo selektira node i skrola listu do njegovog inline detaila.
- Uklonjen je stari dupli canvas click handler koji je radio dodatni selection flow.

### 2026-04-22 - Header rows

- `mesh-status.py` koristi troredni header: brand row, meta row, action row.
- `perf-dashboard.py` lockup više ne cropa FER logo; širina je vraćena tako da stane puni logo.

### 2026-04-22 - Compact node toggles

- `mesh-status.py` opet prikazuje topo canvas iznad node liste.
- Selektirani node detail se otvara i zatvara ponovnim klikom na isti compact row.

### 2026-04-22 - Canvas tooltip

- `mesh-status.py` više ne koristi `#tooltip` floating info box nad canvasom.
- Ostaju samo hover cursor/highlight i click selection prema listi.

### 2026-04-22 - FER local variants

- Runtime asseti su `/usr/local/share/manet/fer-logo-black.svg` i `/usr/local/share/manet/fer-logo-white.svg`.
- `mesh-status.py` i `perf-dashboard.py` theme switching direktno mijenja `src` između crne i bijele sign-only varijante.

### 2026-04-23 - Full logo on login

- `render_perf_auth_page()` opet koristi puni `/assets/fer-logo.svg`.
- Dashboard lockup na `mesh-status.py` i `perf-dashboard.py` skalira se na oko 25% širine ekrana kroz `clamp()`.

### 2026-04-23 - Yellow CTA pass

- `mesh-status.py` koristi puni FER yellow stil za `MANAGE`, a `perf-dashboard.py` isti tretman za `OVERVIEW`.
- `render_perf_auth_page()` prikazuje `Login` labelu i ima autofill-triggered submit fallbacke za browser password managers.
- Header FER logo na oba dashboarda dodatno je povećan (`30vw` desktop, jači mobile clamp) radi boljeg vizualnog balansa.

### 2026-04-23 - Header polish follow-up

- `updateHealthHeader()` više ne stavlja dodatnu `●` u `ALL OK` label jer je status dot već zaseban element.
- FER lockup na `manet.local` i `perf.local` dignut je na `38vw` desktop clamp, uz veći mobile clamp.
- `perf-dashboard.py` compact header čuva veći FER logo umjesto starog `88px` shrinka.

### 2026-04-23 - Remembered perf login

- `render_perf_auth_page()` koristi skriveni `username=admin` field s `autocomplete="username"` uz `current-password` kako bi browser password managers pravilnije zapamtili login.
- `PERF_AUTH_COOKIE_MAX_AGE` postavljen je na 180 dana za dulje zadržavanje `manet_perf_auth` cookieja.

### 2026-04-23 - MANAGE redirect

- `goPerfDashboard()` sada otvara `http://perf.local/?theme=...` umjesto izravnog `/auth/perf-login` URL-a.
- Time `MANAGE` koristi postojeći auth cookie i ne baca korisnika nepotrebno na login page.

### 2026-04-23 - Header logo/title spacing

- `mesh-status.py` i `perf-dashboard.py` imaju manji razmak između FER lockupa i `MANET//...` naslova.
- Na oba GUI-ja smanjen je i `padding-right` unutar `.fer-lockup` bloka kako bi naslov sjedio bliže logotipu.

### 2026-04-23 - Narrower FER lockup box

- Dodatni follow-up sužava `.fer-lockup` clamp na oba dashboarda jer je ranije preširok logo box ostavljao vidljiv prazan prostor.
- Lockup sada ostaje velik, ali više ne gura `MANET//STAT` i `MANET//PERF` predaleko udesno.

### 2026-04-23 - mDNS aliases for services

- Live nodovi imaju `avahi-daemon` s `allow-interfaces=br0` i `enable-reflector=no`, pa mDNS ostaje lokalni na EUD AP segmentu.
- Dodan je `mesh-mdns-update.sh` + systemd timer koji iz `/var/run/mesh_node_registry` odlučuje jesu li `mumble` i `mediamtx` aktivni, a zatim objavljuje njihove stabilne service VIP adrese kroz `/etc/avahi/hosts`.
- `mesh-ip-manager.sh` više ne piše ručno samo `manet.local` i `perf.local`, nego poziva isti helper kako bi svi lokalni aliases ostali konzistentni.

### 2026-04-23 - Mumble registry repair

- Live dijagnostika je pokazala da `mumble-election.sh` uredno starta iz `node-manager` petlje, ali pada s `ERROR: 'sqlite3' command not found`.
- `radio-setup.sh` je proširen da instalira `sqlite3` za buduće reprovisioning-e.
- `node-manager.sh`, `node-manager-static.sh` i `node-manager-acs.sh` sada publishe Mumble service flag na isti način kao MediaMTX, ali samo kad lokalni node stvarno drži Mumble VIP (`HostMin + 2`).

### 2026-04-23 - Dedicated mDNS publisher

- `avahi/hosts` se pokazao nedovoljnim za pouzdano `.local` hostname resolution na mobitelu.
- Dodan je `mesh-mdns-publisher.py` + `mesh-mdns-publisher.service` koji preko `python3-zeroconf` eksplicitno objavljuje `mumble.local` i `mtx.local` samo na `br0`.
- `mesh-mdns-update.sh` ostaje zadužen samo za `manet.local` i `perf.local`.

### 2026-04-22 - MANET palette cleanup

- `mesh-status.py` dashboard pass uklanja plave tematske akcente s glavnog `manet.local` UI-ja.
- Preferirati neutralne tonove i FER žutu za badgeve, service chipove, `THIS NODE` i topo naglaske.

### 2026-04-22 - PERF tabs

- `perf-dashboard.py` koristi underline-only tabs za aktivni state.
- Ako se tabovi opet mijenjaju, zadržati žuti FER underline umjesto punog plavog aktivnog taba.
