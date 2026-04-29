# MANET Project Handover

## System Overview

**4-node RPi5 MANET** (Mobile Ad-hoc NETwork) using batman-adv layer-2 mesh routing over 3 radios per node:

| Interface | Driver     | Band          | Role           |
|-----------|------------|---------------|----------------|
| wlan0     | mt7915e    | 2.4 GHz       | batman-adv mesh slave |
| wlan1     | mt7915e    | 5 GHz         | batman-adv mesh slave |
| wlan2     | morse_usb  | HaLow | batman-adv mesh slave |
| wlan3     | brcmfmac   | 2.4 GHz       | AP only (EUDs), NOT in bat0 |

batman-adv aggregates all 3 radios into `bat0`. `bat0` is bridged into `br0`. Each node gets a `/24` chunk of `10.30.2.0/24` via `node-manager.sh` (alfred-based gossip). All 4 nodes currently have ethernet (`end0`) — in normal field deployment only one node has ethernet and becomes the mesh gateway (`batctl gw_mode server`); others route `default via bat0`.

**Current active branch:** `master`

## 2026-04-29 quick state

- **GPS (u-blox 7 USB) implemented.** All 4 nodes have a u-blox 7 dongle (`1546:01a7`) connected. `gps-reader.py` daemon reads location from gpsd every 5 s, writes `/run/gps_status.json`. `encoder.py` now accepts `--latitude/--longitude/--altitude` and populates `NodeInfo.location`. Both `node-manager-static.sh` and `node-manager-acs.sh` read the JSON and pass coordinates to the encoder. `radio-setup.sh` installs gpsd, patches chrony SHM 0 refclock + `allow 10.30.2.0/24`. chrony already installed; GPS nodes become stratum ~2 NTP source automatically — no election logic change needed. Next release needed to deploy.
- **Syncthing first-boot fix baked into image.** `radio-setup.sh` now creates `/home/radio/.local/state/syncthing` as `radio:radio` before running `syncthing -generate`, preventing first-boot `syncthing.lock: no such file or directory` failures after reprovisioning.
- **New tarball release:** v0.25-txpower-verify (mesh-status.py + perf-dashboard.py now read back `iw dev <iface> info` after each TX power apply and surface the actual reported value). Built from `git archive HEAD:rpi5/rpi5-install`, extracted under Linux/WSL to preserve symlinks, then packed with `tar --owner=root --group=root` so the archive extracts directly into `/`.
- **Release asset naming is load-bearing.** Upstream `provision-mesh.sh` (in the SD-card image, sourced from `very-srs/MANET`) greps `releases/latest` for `"browser_download_url": "...rpi5-install\.tar\.gz"` — versioned filenames like `rpi5-install-v0.25-...tar.gz` do **not** match and break first-boot provisioning silently. Always upload the asset as bare `rpi5-install.tar.gz`.

---

## 2026-04-28 quick state

- **mDNS stack removed.** `mumble.local`, `mtx.local`, `manet.local`, `perf.local` now resolved exclusively via dnsmasq `address=/` entries in `/etc/dnsmasq.d/mesh-eud.conf`. No avahi/zeroconf dependencies remain for name resolution.
- **Service VIP formula:** `HostMin+1` = MediaMTX VIP (`mtx.local`), `HostMin+2` = Mumble VIP (`mumble.local`). VIPs are deterministic from `ipv4_network` in `/etc/mesh.conf` — same formula in election scripts and dnsmasq config.
- **Election incumbency bug fixed.** Both `mediamtx-election.sh` and `mumble-election.sh` now read incumbent from Alfred registry (`IS_MEDIAMTX_SERVER='true'` / `IS_MUMBLE_SERVER='true'`) instead of checking local VIP presence. Deployed to all 4 nodes. Confirmed winner: mesh-78f7.
- **mesh-f86f periodic reboot — investigation ongoing.** No crash dump, no OOM, no pstore. Likely cause: kernel hang → 1-min hardware watchdog reset. Possible culprit: `morse_usb` USB HaLow adapter requesting 500 mA causing USB timeout. Persistent journal activated (`/var/log/journal/`). After next reboot, run `sudo journalctl -b -1 --no-pager | tail -80`.
- **HaLow 24 dBm unlock deployed on all 4 nodes and baked into image.** Three-piece package: `bcf_boardtype_0807-all24.bin` (all regdomain TLVs to 24 dBm), `dot11ah-eu26.ko` (EU kernel regulatory max_eirp raised to 26 dBm), `morse-force2600.ko` (bypasses remaining set-power clamp). Build artifacts in `build/morse-bcf/`. Released as v0.22-halow-24dbm.
- **Tarball must be built via `git archive` + WSL** — `git archive HEAD:rpi5/rpi5-install | tar -x` preserves the `lib -> usr/lib` symlink that Windows NTFS drops; then `sudo tar --owner=root --group=root` for root ownership. See tarball packaging section above.

---

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
- `rpi5/rpi5-install/usr/local/bin/NodeInfo_pb2.py` now carries an explicit guard comment: `# protoc: DO NOT REGENERATE — requires protobuf 4.21.x compatibility on live nodes.`

---

## Tarball distribution

`*.tar.gz` fajlovi **nisu u git repozitorijumu** — ignoriraju se putem `.gitignore`. Tarball se drži lokalno i objavljuje isključivo kao GitHub Release artifact.

Tarball releases are published as GitHub Release artifacts:
- **Latest:** https://github.com/mrleongalaxyum/manet-dev/releases/latest
- **Current:** https://github.com/mrleongalaxyum/manet-dev/releases/tag/v0.25-txpower-verify

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
- **Active branch:** `master`
- `rpi5/rpi5-install/` — install package (all 4 nodes provisioned from this)
- `rpi5/rpi5-live/78f3/` and `rpi5/rpi5-live/78f7/` — live script snapshots from nodes (taken 2026-04-17, before full reprovision — for reference only)
- `rpi5/rpi5-install.tar.gz` — **nije u repozitorijumu** (gitignored); drži se lokalno i objavljuje se kao GitHub Release artifact

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
| `gps-reader.py` | Reads GPS fix from gpsd every 5 s. Writes `/run/gps_status.json` (`has_fix`, `latitude`, `longitude`, `altitude`, `hdop`). Writes `has_fix=false` safely when gpsd is absent or device not plugged in. |
| `mesh-status.py` | Web admin panel on **port 80**. Shows topology canvas, local battery fuel gauge + peer battery % from alfred registry. Peer proxy fetch via `/api/peer/<ip>`. |

### Systemd unit names (post-reprovisioning)

After reprovisioning with the current tarball, unit names are:
- `batman-enslave.service` (NOT `batman-if-setup.service`)
- `node-manager.service` (NOT `node-manager-static.service`)
- `mesh-status.service` (NOT `manet-status.service`)

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

### .local name resolution

EUD clients get all `.local` names resolved via dnsmasq (EUD DNS server via DHCP option 6). **No mDNS/zeroconf/avahi involved** — all four names are static `address=/` entries in `/etc/dnsmasq.d/mesh-eud.conf`, written by `mesh-ip-manager.sh` at IP allocation time:

| Name | Resolves to | Notes |
|------|-------------|-------|
| `manet.local` | node's own br0 IP | per-node, changes if IP chunk changes |
| `perf.local` | node's own br0 IP | per-node |
| `mumble.local` | HostMin+2 of ipv4_network | stable VIP — same on every node |
| `mtx.local` | HostMin+1 of ipv4_network | stable VIP — same on every node |

VIP formula: `ipv4_network` read from `/etc/mesh.conf`, then `ipcalc` → `HostMin` → `+1`/`+2`. Same formula as `mumble-election.sh` and `mediamtx-election.sh`.

**What was removed (2026-04-28):** `mesh-mdns-publisher.py` (python3-zeroconf), `mesh-mdns-update.sh`, their systemd units and `wants/` symlinks. `mdns-isolate.service` (ebtables mDNS block on bat0) is retained.

**Why dnsmasq over mDNS:** mDNS was unreliable on Android. python3-zeroconf required a Python runtime service. Duplicate entries existed in avahi+dnsmasq causing update races. dnsmasq static entries are instant, zero-dependency, and identical on all nodes.

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

**IMPORTANT — tarball packaging:** The tarball must be built on a **Linux machine** (e.g. one of the RPi5 nodes) from inside the `rpi5-install/` directory with explicit root ownership:
```bash
cd rpi5/rpi5-install
sudo tar --owner=root --group=root -czf ../rpi5-install.tar.gz .
```
Two requirements must both be met:
- **`sudo`** — ensures all entries in the tarball are owned by `root:root`. Without it, files are owned by the build user (e.g. `radio:radio`) and after provisioning `/usr/local/bin/` scripts end up non-root owned.
- **Built on Linux** — Windows (Git Bash/pscp) cannot create real symlinks on NTFS. Building on Windows produces a tarball where `etc/systemd/system/multi-user.target.wants/*.service` and `lib → usr/lib` are broken (regular files instead of symlinks), causing systemd to silently skip service enablement on provisioning.

Typical workflow when building from a Windows dev machine:
```bash
# 1. Pack git archive locally (no extraction — avoids Windows symlink problem)
git archive HEAD -- rpi5/rpi5-install/ | gzip > /tmp/rpi5-build-src.tar.gz

# 2. Transfer to a node and rebuild there
scp /tmp/rpi5-build-src.tar.gz radio@<node-ip>:/tmp/
ssh radio@<node-ip> '
  mkdir -p /tmp/rpi5-build && cd /tmp/rpi5-build
  tar --strip-components=2 -xzf /tmp/rpi5-build-src.tar.gz
  sudo tar --owner=root --group=root -czf /tmp/rpi5-install.tar.gz .
  rm -rf /tmp/rpi5-build /tmp/rpi5-build-src.tar.gz
'
scp radio@<node-ip>:/tmp/rpi5-install.tar.gz rpi5/rpi5-install.tar.gz
```

Verify before releasing:
```bash
# Paths must start with ./usr/, ./etc/ — NOT rpi5/rpi5-install/usr/
tar -tzf rpi5-install.tar.gz | head -5

# Ownership must be root/root
tar -tvzf rpi5-install.tar.gz | head -5

# Symlinks must be real symlinks (lrwxrwxrwx)
tar -tvzf rpi5-install.tar.gz | grep "^l"
```

Building from the parent directory creates a path prefix and scripts end up at `/rpi5-install/` instead of `/`.

**IMPORTANT — Windows git symlinks:** The repo must be cloned with `core.symlinks=true` (set in `.git/config`). Without it, git on Windows stores symlinks as plain text files. Symlinks in `etc/systemd/system/multi-user.target.wants/` and `timers.target.wants/` must be real symlinks (mode `120000`) — if they end up as text files in the tarball, systemd silently ignores them and the services are never enabled after provisioning. Verify with:
```bash
git ls-files -s rpi5/rpi5-install/etc/systemd/system/multi-user.target.wants/
```
All entries must show mode `120000`, not `100644`.

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

### 2026-04-27 - Election incumbent detection fix

- **Bug:** `mumble-election.sh` i `mediamtx-election.sh` su određivali incumbency provjeri lokalnog VIP-a na `br0`. Svaki node s VIP-om (`ip addr show dev br0 | grep -q "inet $VIP/"`) bi proglasio sebe vođom → primio +10 TQ bias → pobijedio vlastite izbore. Kad VIP ostane na više nodova (npr. zbog election failure), sva 4 noda su paralelno pokretala Mumble/MediaMTX servis.
- **Popravak:** Oba election skripte sada čitaju `IS_MUMBLE_SERVER='true'` / `IS_MEDIAMTX_SERVER='true'` iz Alfred-propagiranog node registra (`/var/run/mesh_node_registry`) kao autoritativan izvor incumbency. `node-manager.sh` te flagove postavlja samo kad lokalni node drži i aktivni servis i VIP → svi nodovi čitaju konzistentne Alfred-sync podatke.
- Deployano na sva 4 noda. Pobjednički node: mesh-78f7 (`10.30.2.204`) drži oba VIP-a (`10.30.2.2`, `10.30.2.3`).

### 2026-04-27 - Login forma auto-submit fix

- `render_perf_auth_page()` u `mesh-status.py` je submitao formu na prvom unesenom slovu jer je `input` listener pozivao `trySubmit()` dok je password field bio fokusiran.
- Ispravak: uklonjeni `input`, `change`, `blur` listeneri i `setTimeout` fallbacki — ostao je samo `animationstart` koji se okida isključivo pri browser autofill-u, ne pri ručnom unosu.

### 2026-04-27 - mesh-mdns-publisher.service Windows symlink fix

- `core.symlinks=false` na Windows git konfiguraciji pohranio je symlinke u `multi-user.target.wants/` i `timers.target.wants/` kao regularne tekstualne fajlove (mode `100644`). systemd ignorira non-symlink fajlove u `*.target.wants/` → servis nikad nije bio enable-an.
- Fix: `git update-index --cacheinfo 120000,...` za pogođene fajlove + `git config core.symlinks true` u repo konfiguraciji. Tarball se mora graditi s `core.symlinks=true`.

### 2026-04-22 - MANET palette cleanup

- `mesh-status.py` dashboard pass uklanja plave tematske akcente s glavnog `manet.local` UI-ja.
- Preferirati neutralne tonove i FER žutu za badgeve, service chipove, `THIS NODE` i topo naglaske.

### 2026-04-22 - PERF tabs

- `perf-dashboard.py` koristi underline-only tabs za aktivni state.
- Ako se tabovi opet mijenjaju, zadržati žuti FER underline umjesto punog plavog aktivnog taba.

### 2026-04-24 - Uptime, CPU i live clock fix

- Sva tri `node-manager*.sh` nisu prosljeđivala `--uptime-seconds` ni `--cpu-load-average` encoderu — Alfred payload je uvijek imao 0. Dodano čitanje iz `/proc/uptime` i `/proc/loadavg` u ENCODER_ARGS bloku sva tri managera.
- `perf-dashboard.py`: dodana `fmt_uptime()` i poziva se pri buildu node_info umjesto golog int stringa.
- `mesh-status.py`: `tq` za lokalni (self) node je postavljen na `None` umjesto `255` (batman ne računa TQ prema sebi); TQ badge u node listi se za THIS NODE uopće ne prikazuje.
- `mesh-status.py`: header local time (`hdr-time`) sada tece svake sekunde kroz `setInterval(tickLocalTime, 1000)` umjesto da stoji na zamrznutom server timestampu.
- Live patch deploy na sve 4 nodova kroz mesh-f86f (192.168.1.51) kao jump host.

### 2026-04-29 - GPS/NTP implementation handoff

- Local GPS implementation lives in `manet-dev/rpi5/rpi5-install`, not in `.manet-dev-head-install` or `MANET-upstream`.
- Existing protobuf already has `NodeInfo.location` with `latitude`, `longitude`, and `altitude`; do not add a new protobuf field for basic location.
- `gps-reader.py` queries local `gpsd` JSON on `127.0.0.1:2947` and writes `/run/gps_status.json` with `has_fix`, `latitude`, `longitude`, `altitude`, `hdop`, and `timestamp`.
- `node-manager.sh`, `node-manager-static.sh`, and `node-manager-acs.sh` read `/run/gps_status.json` and pass `--latitude`, `--longitude`, `--altitude` into `encoder.py` only when `has_fix` is true.
- Local follow-up completed: `decoder.py` now emits `GPS_LATITUDE`, `GPS_LONGITUDE`, `GPS_ALTITUDE`; `mesh-registry-builder.sh` now persists those fields into `/var/run/mesh_node_registry`, which matches what `mesh-status.py` already expects.
- `radio-setup.sh` installs `gpsd gpsd-clients`, writes `/etc/default/gpsd` with `USBAUTO=true` and `GPSD_OPTIONS="-n"`, enables/restarts `gps-reader.service`, and applies chrony GPS config to active and template chrony configs if present.
- Important risk for Claude to verify: `ethernet-autodetect.sh` copies `/etc/chrony/chrony-test.conf`, `chrony-server.conf`, or `chrony-default.conf` over `chrony.conf`; therefore every chrony template must keep the GPS `refclock SHM 0` and mesh `allow 10.30.2.0/24` additions.
- Test plan after reprovision: confirm u-blox appears as `/dev/ttyACM0`, `gpsd` sees TPV messages, `/run/gps_status.json` flips `has_fix=true`, `alfred -r 68` decodes to GPS fields, `/var/run/mesh_node_registry` contains `NODE_*_GPS_*`, dashboard shows GPS, and `chronyc sources -n` shows GPS plus network/mesh fallback.
### 2026-04-29 - Provisioning release state

- Current latest release on `mrleongalaxyum/manet-dev`: `v0.27-provisioning-lf`.
- Asset: `rpi5-install.tar.gz`.
- SHA256: `b4e224c720f671f02af9af0ea5daa6018149d74531cbd23d4d38cca791d44bd4`.
- Source commits pushed to `master`: `fcc0c7c` (`.gitattributes` LF enforcement) and `098b12b` (`radio-setup-run-once` post-reboot completion fix).
- Correct packaging command shape: build from Linux/WSL staging rooted at `rpi5/rpi5-install`, then run `tar --owner=root --group=root --numeric-owner -czvf rpi5-install.tar.gz .`. Do not package from the Windows working tree, because CRLF and symlink materialization can break provisioning.
- Concrete build command, run while `pwd` is the staged `rpi5-install` root: `sudo tar --owner=root --group=root --numeric-owner -czvf ~/manet-new/MANET/install_packages/rpi5-install.tar.gz .`
- Provisioning bug fixed: first run previously disabled `radio-setup-run-once.service` and then rebooted, so the expected post-reboot pass never ran. The script now keeps the unit enabled until the post-reboot pass completes, then creates `/var/lib/radio-setup.done` and disables the unit.
- Live check after patch: `mesh-78f7`, `mesh-7946`, and `mesh-f86f` finished with `radio-setup-run-once.service inactive/disabled` and `/var/lib/radio-setup.done`. `mesh-78f3` still needs final SSH verification; it replied to ping but timed out during SSH banner exchange.
