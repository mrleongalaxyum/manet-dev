# MANET Change History

## 2026-04-29

### Feature: GPS location + NTP via u-blox 7 USB dongle

All 4 nodes have a u-blox 7 USB GPS receiver (`VID 1546:01a7`) connected.

**New files:**
- `usr/local/bin/gps-reader.py` — daemon that queries gpsd via JSON protocol on `127.0.0.1:2947`, extracts the first TPV message, and writes `/run/gps_status.json` every 5 s. Fields: `has_fix` (bool), `latitude`, `longitude`, `altitude` (float, WGS84), `hdop`, `timestamp`. Writes `has_fix=false` safely when gpsd is unreachable or GPS has no fix — nodes without a dongle are unaffected.
- `etc/systemd/system/gps-reader.service` — `After=gpsd.service`, `Restart=always`.

**Modified files:**
- `encoder.py` — `--latitude`, `--longitude`, `--altitude` args populate `NodeInfo.location` (proto field 40, already defined). Only sets location if lat/lon are non-zero (i.e., `has_fix=true`).
- `node-manager-static.sh` — reads `/run/gps_status.json` before each Alfred publish, appends `--latitude/--longitude/--altitude` to encoder args if `has_fix=true`.
- `node-manager-acs.sh` — same, in both lobby and data-channel publish blocks.
- `radio-setup.sh` — installs `gpsd gpsd-clients`; writes `/etc/default/gpsd` (`USBAUTO=true`, `GPSD_OPTIONS="-n"`); appends `refclock SHM 0` to `/etc/chrony/chrony.conf` and `allow 10.30.2.0/24` (idempotent checks); enables `gps-reader.service`; restarts chrony.

**NTP design:** chrony was already installed and serving NTP to the mesh (`allow fd01:ed20:ecb4::/64`, `local stratum 10`). With GPS fix, the SHM 0 refclock gives chrony a stratum-0 source → node advertises at stratum ~2. Other nodes' chrony prefers the lower stratum automatically. No mesh election logic change needed — `is_ntp_server` flag remains tied to ethernet gateway; GPS silently improves time quality mesh-wide. Nodes without GPS or without fix continue at stratum 10.

**Pending:** new tarball release needed to deploy to nodes.

### Fix: Syncthing state directory missing after reprovisioning

After SD-card reprovisioning, `syncthing@radio.service` failed on all nodes with:

```
Failed to acquire lock: open /home/radio/.local/state/syncthing/syncthing.lock: no such file or directory
```

**Root cause:** `radio-setup.sh` generated `/home/radio/.config/syncthing`, but did not create Syncthing's state directory before the systemd service started.

**Fix:** `radio-setup.sh` now creates the state directory during first-run setup:

```bash
install -d -o radio -g radio -m 700 /home/radio/.local/state/syncthing
```

The fixed image is released as `v0.24-syncthing-state` with `rpi5-install.tar.gz` packed as root-owned entries and root-relative archive contents.

### Fix: GitHub release asset naming broke first-boot provisioning

Three of four nodes ended up at default hostname `raspberrypi` with no `br0`/`bat0`/`wlan2` and `mesh-provision.service` failed. Root cause: the v0.25 release asset was uploaded as `rpi5-install-v0.25-txpower-verify.tar.gz`, but `provision-mesh.sh` (from upstream `very-srs/MANET` SD-card image template) greps `releases/latest` strictly for `rpi5-install\.tar\.gz`:

```bash
RPI5_URL=$(curl -s https://api.github.com/repos/mrleongalaxyum/manet-dev/releases/latest \
    | grep -o '"browser_download_url": *"[^"]*rpi5-install\.tar\.gz"' \
    | grep -o 'https://[^"]*')
```

The versioned suffix didn't match, `RPI5_URL` was empty, the script exited 1, nothing else ran. Three nodes that picked v0.25 as "latest" never got their tarball, never ran `radio-setup.sh`, never built `br0`/`bat0`. Journal on each broken node:

```
ERROR: Could not resolve rpi5-install.tar.gz from latest release
mesh-provision.service: Failed with result 'exit-code'.
```

**Fix:** v0.25 asset re-uploaded as bare `rpi5-install.tar.gz`. After re-upload, broken nodes recovered with `systemctl restart mesh-provision.service`.

**Lesson:** the asset name is load-bearing for first-boot provisioning. Always upload as `rpi5-install.tar.gz`, never with a versioned suffix.

### Revert: bogus `Before=` claim about radio-setup-run-once

A previous note claimed `radio-setup-run-once.service` was given `Before=batman-enslave.service node-manager.service mesh-status.service perf-dashboard.service` to fix an ordering race. That framing is wrong — `radio-setup.sh` is what **creates** those `.service` files (heredoc writes at lines 1239/1280/1455 of `radio-setup.sh` overwriting the baseline copies shipped in the tarball). The `Before=` directive in the upstream `firstrun.sh.template` doesn't reflect a real dependency between radio-setup and pre-existing services; it's at most a workaround for the fact that runtime services don't carry `After=radio-setup-run-once.service` themselves. Removing the claim from this changelog and proposing upstream cleanup separately.

---

## 2026-04-28

### Refactor: mDNS stack zamijenjen dnsmasq statičkim entryjima

`mumble.local` i `mtx.local` su ranije rješavani putem `mesh-mdns-publisher.py` (python3-zeroconf), što je bilo nepouzdano na Androidu i zahtijevalo Python runtime servis. `manet.local` i `perf.local` su bili duplicirani u dnsmasq i avahi/hosts putem `mesh-mdns-update.sh`.

Sva 4 `.local` imena sada žive isključivo u `/etc/dnsmasq.d/mesh-eud.conf`, koji generira `mesh-ip-manager.sh` pri svakoj IP alokaciji:

```
address=/manet.local/<node-ip>      per-node
address=/perf.local/<node-ip>       per-node
address=/mumble.local/<HostMin+2>   VIP, derived from ipv4_network in mesh.conf
address=/mtx.local/<HostMin+1>      VIP, derived from ipv4_network in mesh.conf
```

Service VIP-ovi se računaju iz `ipv4_network` istom `HostMin+N` formulom kao i election skripte — nema hardkodiranih IP adresa.

Uklonjeno: `mesh-mdns-publisher.py`, `mesh-mdns-update.sh`, njihovi systemd unitovi i `wants/` symlinkovi. `mdns-isolate.service` (ebtables blok mDNS prometa na bat0) ostaje.

Deployano na sva 4 noda. Verifikovano grep-om na `/etc/dnsmasq.d/mesh-eud.conf`.

---

### Fix: tarball build procedura — root ownership + Linux obavezno

Tarball izgrađen na Windowsu imao je `radio:radio` ownership na svim fajlovima umjesto `root:root`. Također, Git Bash na Windowsu ne može kreirati symlinke čak i s `core.symlinks=true`, pa `tar` na Windows-u producira tarball s pokvarenim symlinkovama u `multi-user.target.wants/`.

**Ispravna komanda (na Linux nodu):**
```bash
cd rpi5/rpi5-install
sudo tar --owner=root --group=root -czf ../rpi5-install.tar.gz .
```

**Windows workflow:** `git archive` → gzip → scp na node → strip-components extract → `sudo tar --owner=root --group=root` rebuild → scp nazad.

Dokumentovano u `handover.md` s verifikacijskim komandama.

---

### Istraga: mesh-f86f periodični reboot — uzrok nije definitivan

Node mesh-f86f (`10.30.2.182`) se periodično resetuje. Istraga nije pronašla definitivan uzrok jer nema perzistentnog journala ni pstore crash dumpa.

**Prikupljeni dokazi:**
- EXT4 journal recovery pri bootu → prethodni shutdown je bio unclean (hard reset, ne clean reboot)
- `systemd[1]: Watchdog running with a hardware timeout of 1min` → hardware watchdog aktivan
- `throttled=0x0` → firmware nije detektovao podnapon
- Nema OOM, nema kernel panic dumpa u pstore, temperatura OK (48.8°C)
- `man-db.timer: Not using persistent file timestamp Mon 2026-04-27 19:15:38 BST as it is in the future` → potvrđuje prethodni boot s ispravnim NTP vremenom, dakle reboot se desio između 19:15 i 22:56 BST

**Najvjerojatniji uzrok:** kernel hang → watchdog (1 min) resetuje sistem. `morse_usb` HaLow adapter traži `MxPwr=500mA` (maksimum USB 2.0 porta) — USB timeout može blokirati kernel I/O threadove, što sprečava systemd da feedi watchdog.

**Poduzeto:** Aktiviran perzistentni journal (`mkdir -p /var/log/journal`). Nakon sljedećeg reboota, pokrenuti:
```bash
sudo journalctl -b -1 --no-pager | tail -80
```

---

### Deploy: HaLow 24 dBm unlock na svim nodovima — baken u image, v0.22 release

**Uzrok:** Stock BCF (`bcf_boardtype_0807.bin`) ograničava EU TX power na 15 dBm na firmware razini. `iw dev wlan2 set txpower fixed 2400` se tiho clippa. GUI "Apply 24 dBm" nije imao efekta.

**Tri-dijelni unlock (sve tri komponente su obavezne):**
1. `bcf_boardtype_0807-all24.bin` — sve regdomain TX power TLV-ove podiže na 96 qdBm (24 dBm) s regeneriranim CRC-ovima. BCF CRC formula: board CRC = `zlib.crc32(board_config[8:8+board_len+8])`; regdomain CRC = `zlib.crc32(regdom[4:4+reg_len+8], seed)` gdje je `seed = zlib.crc32(b"# Morse Micro regulatory domain #", board_crc)`.
2. `dot11ah-eu26.ko` — patchuje EU `max_eirp` u Linux regulatory tablici s 16 dBm na 26 dBm (`.data` offset `0x8380`, 6 EU pravila, `0x10` stride). Bez ovog patcha kernel clippa na 16 dBm bez obzira na BCF.
3. `morse-force2600.ko` — patchuje `morse_mac_set_txpower()` na file offsetu `0x5b70`: `mov w20,#0xa45; nop; nop` (2600 mBm). Zaobilazi preostali host/firmware clamp.

EU25 i EU26 paket oba rezultiraju 24.00 dBm (hardverski ceiling). EU26 ostavljen kao "viši traženi" za reporting.

**Instalirano na svim nodovima i verifikovano:**
```
mesh-7946, mesh-78f3, mesh-78f7, mesh-f86f  →  txpower 24.00 dBm
```

**Baken u image:** svi patched fajlovi zamijenjeni u `rpi5/rpi5-install/`, build artifakti u `build/morse-bcf/`. Commit `4373775`. Releaseano kao [v0.22-halow-24dbm](https://github.com/mrleongalaxyum/manet-dev/releases/tag/v0.22-halow-24dbm).

**Tarball fix:** Windows NTFS gubi `lib -> usr/lib` symlink. Ispravna procedura: `git archive HEAD:rpi5/rpi5-install | tar -x -C /tmp/extract` (symlink iz gita), zatim `sudo tar --owner=root --group=root -czf rpi5-install.tar.gz -C /tmp/extract .`.

---

## 2026-04-27

### Fix: perf.local login forma submitala na prvom unesenom slovu

`render_perf_auth_page()` u `mesh-status.py` imao je `input`, `change`, `blur` i tri `setTimeout` listenera koji su pozivali `trySubmit()`. Uvjet `document.activeElement === password` je bio `true` dok korisnik tipka, pa se forma submitala čim se upišu prvo slovo.

Ispravak: uklonjeni svi listeneri osim `animationstart`. `animationstart` se okida isključivo kada browser autofilluje polje (CSS `@keyframes autofill-detect` trik) — ne pri ručnom unosu. Manuelni submit ostaje na Enter ili kliku na Login dugme.

Deployano na sva 4 noda.

---

### Fix: mesh-mdns-publisher.service nikad nije bio aktivan — Windows git symlink bug

`mumble.local` i `mtx.local` nisu radili jer `mesh-mdns-publisher.service` nije bio enable-an ni na jednom nodu.

**Uzrok:** `core.symlinks=false` u git konfiguraciji na Windows razvojnoj mašini. Git je symlink fajlove u `multi-user.target.wants/` i `timers.target.wants/` pohranio kao regularne tekstualne fajlove (`100644` mode) umjesto pravih symlinkovaka (`120000` mode). Tarball izgrađen s tog checkoutsa nosio je tekstualne fajlove na nodove. systemd ignorira sve što nije pravi symlink u `*.target.wants/` direktorijumima — servis je ostajao `disabled` bez ikakve greške.

Pogođeni fajlovi u repou:
- `etc/systemd/system/multi-user.target.wants/mesh-mdns-publisher.service` (100644 → 120000)
- `etc/systemd/system/timers.target.wants/mesh-mdns-update.timer` (100644 → 120000)

**Popravak u repou:** `git update-index --cacheinfo 120000,...` za oba fajla + `git config core.symlinks true`. Na živim nodovima symlink je kreiran ručno (`ln -sf`) i servis startovan.

**Provjera:** Nakon starta publishera na sva 4 noda, journald potvrđuje:
```
[MESH-MDNS-PUB] registered mumble
[MESH-MDNS-PUB] registered mtx
```

**Napomena za buduće tarball gradnje:** Ako se repo klonira na Windowsu, provjeriti `git config core.symlinks` — mora biti `true`, inače symlinkovi u install treeju postaju tekstualni fajlovi i servisi se ne enable-aju pri provisioning-u.

---

### Fix: election skripta — svaki node pobjeđivao vlastite izbore (VIP incumbency bug)

Sva 4 noda su istovremeno držali VIP adrese `10.30.2.2` (MediaMTX) i `10.30.2.3` (Mumble) na `br0`. Oba servisa su radila na svim nodovima paralelno.

**Uzrok:** `mumble-election.sh` i `mediamtx-election.sh` su određivali incumbency (koji node je trenutni vođa) tako što su provjeravali je li lokalni node ima VIP na `br0`:
```bash
# Stari, pokvareni kod:
if ip addr show dev br0 | grep -q "inet $MEDIAMTX_IPV4_VIP/"; then
    CURRENT_LEADER_MAC="$MY_MAC"  # Svaki node s VIP-om proglašava sebe vođom
fi
```
Kada je VIP slučajno ostao na više nodova (npr. zbog sqlite3 greške koja je sprečavala election u ranijem period), svaki node bi vidio vlastiti VIP, dodijelio sebi +10 TQ incumbency bias i pobijedio vlastite izbore. Ni ARP-based pristup nije pomogao jer node ne vidi vlastitu MAC adresu u `ip neigh show` tablici za vlastiti VIP.

**Popravak:** Incumbency se sada čita iz Alfred-propagiranog node registra (`/var/run/mesh_node_registry`). `node-manager.sh` već ispravno postavlja `IS_MUMBLE_SERVER='true'` / `IS_MEDIAMTX_SERVER='true'` samo kad node drži I aktivni servis I VIP — svi nodovi čitaju iste Alfred-sync podatke, pa je ground truth konzistentan mreži.
```bash
# Novi, ispravni kod:
CURRENT_LEADER_MAC=""
if [ -f "$REGISTRY_STATE_FILE" ]; then
    INCUMBENT_NODE_ID=$(grep "IS_MEDIAMTX_SERVER='true'" "$REGISTRY_STATE_FILE" \
        | head -1 | sed "s/NODE_\([^_]*\)_.*/\1/")
    if [ -n "$INCUMBENT_NODE_ID" ]; then
        INCUMBENT_MAC=$(grep "^NODE_${INCUMBENT_NODE_ID}_MAC_ADDRESS=" "$REGISTRY_STATE_FILE" \
            | cut -d"'" -f2)
        [ -n "$INCUMBENT_MAC" ] && CURRENT_LEADER_MAC="$INCUMBENT_MAC"
    fi
fi
```

Deployano na sva 4 noda. Stale VIP-ovi manualno uklonjeni sa losing nodova. Pobjednički node: mesh-78f7 (`10.30.2.204`) drži `10.30.2.2` i `10.30.2.3`.

---

## 2026-04-22

### FER brand alignment for `manet.local` and `perf.local`

- Verified GUI alignment against the official FER brandbook PDF from `fer.unizg.hr`.
- Standardized both dashboards on FER typography and color tokens:
  - font stack `Roobert, Arial, sans-serif`
  - neutral base `#EBEAE8` / `#02000D`
  - accents `#ECB000` and `#00003F`
- Replaced the previous internet-fetched FER image usage with inline SVG lockups embedded directly in:
  - `mesh-status.py`
  - `perf-dashboard.py`
- Simplified the lockup to a monochrome FER mark so it follows the brandbook rule of black/white logo on brand surfaces and works fully offline on nodes.
- Removed remaining non-FER UI drift from badges and state chips:
  - self/info states now use FER deep blue
  - gateway/warn emphasis now uses FER yellow
  - red remains reserved for actual fault/error states
- Reduced decorative striping and grid styling in both GUIs and replaced it with cleaner FER-style accent bands and surface treatment.
- Kept the glow effect on `manet.local`, but reworked it into a controlled yellow/blue FER halo in the topology panel instead of the previous generic dashboard decoration.

### `manet.local` → `perf.local` authenticated handoff

- Added a `PERF.LOCAL` button to `manet.local`.
- Clicking it now validates the provisioned `admin_password` from `/etc/mesh.conf` before sending the user into `perf.local`.
- The browser receives a derived auth token instead of the raw password.
- `perf.local` now converts that token into a persistent cookie (`manet_perf_auth`) and strips the token from the URL on redirect.
- Added a direct-access fallback password page on `perf.local` so opening it without a cookie still works cleanly.
- Updated the button UX so `manet.local` now redirects straight to `perf.local` without an extra prompt; authentication stays entirely on the `perf.local` login page.
- Centered the `perf.local` password card more reliably on mobile and small viewports using viewport-safe height and padded grid centering.

### `manet.local` mobile scroll, stutter, and layout pass

- Removed one-finger canvas panning on `manet.local`; single-finger touch now scrolls the whole page normally.
- Kept topology interaction as:
  - tap to select a node
  - two-finger pinch to zoom
- Replaced repeated immediate canvas redraws outside the physics loop with `requestAnimationFrame`-queued redraw scheduling to reduce visible scroll and hover stutter.
- Switched the page away from a fixed full-height split layout toward a document-scroll-friendly panel layout with:
  - padded grid structure on desktop
  - stacked mobile layout
  - rounded topology and side panels
  - less nested internal scrolling
- Smoothed transitions on node cards and cleaned the topology background so motion feels lighter and more modern on mobile, especially in landscape orientation.

### HaLow TX power GUI clamping by bandwidth

- Fixed HaLow TX power option handling in both GUI/backend paths so bandwidth changes clamp to valid live-tested maxima instead of leaving impossible combinations selected.
- Empirically validated on a live node:
  - `1 MHz -> 24 dBm`
  - `2 MHz -> 24 dBm`
  - `4 MHz -> 22 dBm`
- Added those caps to the code as an explicit table and updated the GUI dropdown logic so:
  - switching `1 MHz -> 4 MHz` drops the selected TX power to `22 dBm`
  - switching `4 MHz -> 1 MHz` offers the `24 dBm` maximum again
- Updated and deployed:
  - `rpi5/rpi5-install/usr/local/bin/perf-dashboard.py`
  - `rpi5/rpi5-install/usr/local/bin/mesh-status.py`

### perf.local: Alfred-carried radio rate summary for HaLow and Wi-Fi

- Added compact per-interface link-rate summaries to the Alfred status payload so `perf.local` can show current radio modulation without polling every node directly.
- Source of truth is `iw dev <iface> station dump` on each node, sampled locally inside node-manager publish loop, then propagated through existing protobuf gossip.
- All three mesh radios are covered:
  - `wlan0` -> Wi-Fi 2.4 GHz
  - `wlan1` -> Wi-Fi 5 GHz
  - `wlan2` -> HaLow
- Display format is intentionally compact for mobile UI: `MCSx Nn [GI] [BW]`, for example `MCS9 N1 SGI 20M`.
- `perf.local` topology and interface cards now read those summaries from Alfred-backed topology data rather than from direct live fetches.

### Bug fixed: protobuf generator/runtime mismatch on live nodes

- Newly generated `NodeInfo_pb2.py` from a modern local `protoc` imported `google.protobuf.runtime_version`.
- Live nodes ship `protobuf 4.21.12`, which does not expose that symbol.
- Result was a hard failure in both `encoder.py` and `decoder.py`, followed by repeated:
  - `REGISTRY: Warning: decoder.py failed with exit code 1`
- Fix: keep the updated descriptor payload, but remove the newer runtime gate from checked-in `NodeInfo_pb2.py` so it stays compatible with the node image runtime.
- After redeploy, registry building recovered and Alfred once again carried valid peer state for all 4 nodes.

## 2026-04-17 (session 4)

### Bug fixed: HaLow (wlan2) S1G "Invalid S1G configuration" on EU deployment

**Root cause (primary):** `radio-setup.sh` generated `op_class=67, channel=6` for EU HaLow config. `op_class=67` is Singapore (SG), not EU. EU S1G uses `global_op_class=66`, channels 1/3/5/7/9, freq_start=863000 kHz. Confirmed by reading MorseMicro/hostap source (`morse-hostap/src/utils/morse.c`): `eu6` struct has `global_op_class=66`; `sg19` struct has `global_op_class=67`.

Correct EU channel 5 → 863000 + 5×500 = 865500 kHz (865.5 MHz) ✓

**Root cause (secondary):** `country=EU` without quotes in wpa_supplicant_s1g config. `wpa_config_parse_string` (in MorseMicro wpa_supplicant) treats unquoted string values as hex — `U` is not valid hex so `EU` silently fails. Must be `country="EU"` with double quotes.

**Root cause (tertiary — REGDOM churn):** wpa_supplicant on wlan0/wlan1 had `country=EU` in config → periodically tried to set EU regdomain → kernel reverted to WORLD (00) via wireless-regdb → CTRL-EVENT-REGDOM-CHANGE loop every ~1s, disrupting batman-adv OGM propagation. Note: wireless-regdb (Debian) always overrides `cfg80211 ieee80211_regdom=EU` in modprobe — kernel stays at WORLD globally. The morse phy manages its own EU S1G regulatory domain independently.

**Fixes applied to radio-setup.sh:**

1. EU S1G wpa_supplicant config: `op_class=67 channel=6` → `op_class=66 channel=5`
2. EU S1G wpa_supplicant config: `country=$HALOW_REGULATORY_DOMAIN` → `country="$HALOW_REGULATORY_DOMAIN"` (added quotes)
3. wlan0/wlan1 wpa_supplicant config generation: removed `country=` line entirely to prevent REGDOM churn
4. CFG80211_REGDOM variable: set to `EU` when `HALOW_REGULATORY_DOMAIN=EU`, used in modprobe cfg80211.conf (cfg80211 itself stays at WORLD due to wireless-regdb override, but at least not causing conflict)

**Fixes applied live to all 4 nodes (without reprovision):**
- `/etc/wpa_supplicant/wpa_supplicant-wlan2-s1g.conf`: `op_class=66`, `channel=5`, `country="EU"` (with quotes, both global and in network{} block)
- `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf`, `wpa_supplicant-wlan1.conf`, `wpa_supplicant-wlan0-lobby.conf`, `wpa_supplicant-wlan1-lobby.conf`: `country=EU` line removed

**Result:** All 4 nodes — wlan0/wlan1/wlan2 each show 3 mesh stations. Batman-adv routing table populated (verified via bridge FDB and `ip neigh show dev bat0`). Nodes reachable at 10.30.2.x over mesh. Note: `batctl n`/`batctl o` commands show empty due to batctl 2025.3 vs batman-adv kernel module 2023.3 version mismatch — this is a display-only issue, routing works correctly.

### Regulatory domain and TX power analysis

- **WORLD (00)** is the effective regdomain for wlan0/wlan1 (mt7915e) — wireless-regdb forces this regardless of modprobe settings. WORLD allows 30 dBm on all bands.
- **Hardware TX power caps** (mt7915e EEPROM): wlan0 2.4 GHz = 17 dBm, wlan1 5 GHz = 29 dBm. These are hardware limits, not regulatory.
- **HR regdomain would be worse**: HR limits 5 GHz to ~23 dBm vs WORLD's 30 dBm (29 dBm actual). Staying on WORLD maximises range.
- **HaLow (wlan2/morse)** always uses EU regardless of cfg80211 global domain — morse phy is self-managed and registers EU S1G channels via `regulatory_hint()`.
- **Conclusion:** No regulatory changes needed. WORLD is already optimal for WiFi range. HaLow stays EU for correct S1G frequencies.

### batman-if-setup.sh: HaLow enslaved first as batman-adv primary

Changed interface enslavement order in `batman-if-setup.sh`: HaLow (wlan2) is now added to bat0 **before** standard 802.11 interfaces (wlan0/wlan1). Rationale: HaLow is the longest-range link — when standard 802.11 peers go out of range, batman-adv needs at least one active interface to continue generating and processing OGMs. If HaLow is the last one added and standard interfaces timeout first, OGM propagation stops.

Also: standard interface detection changed from polling for netdev existence to polling for `type mesh point` (iw dev check), ensuring wpa_supplicant has fully initialized the mesh interface before batman-adv enslaves it.

### Node status (end of session 4)

| Hostname   | LAN IP        | Mesh IPs               | wlan0 | wlan1 | wlan2 | bat0 |
|------------|---------------|------------------------|-------|-------|-------|------|
| mesh-7946  | 192.168.1.50  | 10.30.2.72/73          | 3 sta | 3 sta | 3 sta | ✓   |
| mesh-f86f  | 192.168.1.51  | 10.30.2.160/161        | 3 sta | 3 sta | 3 sta | ✓   |
| mesh-78f7  | 192.168.1.53  | 10.30.2.182/183        | 3 sta | 3 sta | 3 sta | ✓   |
| mesh-78f3  | 192.168.1.54* | unknown (offline)      | —     | —     | —     | —   |

*mesh-78f3 was unreachable at end of session (possibly rebooting or different IP).

---

## 2026-04-17 (session 3)

### Bug fixed: HaLow (wlan2) not forming mesh when country code is HR

**Root cause:** `cfg80211.conf` had `ieee80211_regdom=HR`. Standard cfg80211 country databases include no S1G (sub-1GHz) channel definitions for country-specific codes like HR. When `wpa_supplicant_s1g` tried to resolve `op_class=67, channel=6` (EU868 HaLow) against the cfg80211 channel database, it got 0 MHz → "Unsupported mesh mode frequency: 0 MHz" → wlan2 never entered mesh.

The morse driver correctly uses EU internally (morse.conf `country=EU`), and morse registers EU S1G channel info with cfg80211 via `regulatory_hint()`. But wpa_supplicant_s1g validates against the active cfg80211 regulatory domain (HR), not morse's internal state.

**Fix:** In `radio-setup.sh`, when `HALOW_REGULATORY_DOMAIN=EU` (all EU member states), write `ieee80211_regdom=EU` to `cfg80211.conf` instead of the node's ISO country code. EU is a valid cfg80211 domain for 2.4/5 GHz as well, so the mt7915e radios are unaffected. Non-EU deployments (US/AU/JP/KR) continue to write their country code as before.

Changed line in `radio-setup.sh` (MORSE/HALOW MODULE OPTIONS section):
```bash
# before
echo "options cfg80211 ieee80211_regdom=$REGULATORY_DOMAIN" > /etc/modprobe.d/cfg80211.conf
# after
if [[ "$HALOW_REGULATORY_DOMAIN" == "EU" ]]; then CFG80211_REGDOM="EU"
else CFG80211_REGDOM="$REGULATORY_DOMAIN"; fi
echo "options cfg80211 ieee80211_regdom=$CFG80211_REGDOM" > /etc/modprobe.d/cfg80211.conf
```

Pushed to `hr-country-code` branch on GitHub. Applied live to all 4 nodes (updated cfg80211.conf, rebooted).

---

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

## 2026-04-18

### UPS HAT (E) battery monitoring — branch `ups-battery-monitor`

Waveshare UPS HAT (E) je montiran na svim 4 nodeovima. Implementiran battery monitoring koji čita MCU i publicira podatke kroz mesh.

#### Ispravan chip i register map

Inicijalna pretpostavka bila je da RPi direktno čita INA219 na `0x40`. To je **pogrešno** — INA219 je interno spojen na IP2368 MCU i nije direktno dostupan. Svi podaci čitaju se s IP2368 MCU na `0x2D`:

| Register | Sadržaj | Format |
|----------|---------|--------|
| `0x02`   | Status byte: bit6=fast_charging, bit7=charging, bit5=discharging | uint8 |
| `0x10`   | VBUS voltage(mV), current(mA), power(mW) | 3×uint16 LE |
| `0x20`   | Battery voltage(mV), current(mA signed), percent, capacity(mAh), runtime, time-to-full | 6×uint16 LE |
| `0x30`   | Cell voltages V1-V4 (mV) | 4×uint16 LE |

Shutdown trigger: bilo koja ćelija < 3150 mV dok se ne puni (prema Waveshare sample kodu).

#### I2C enable na RPi5

RPi5 koristi `i2c_designware` driver (ne `i2c-bcm2835`). Za `/dev/i2c-1`:
1. `dtparam=i2c_arm=on` u `/boot/firmware/config.txt` (Bookworm) ili `/boot/config.txt` (stariji)
2. `i2c-dev` u `/etc/modules`
3. **Reboot obavezan** — `modprobe i2c-dev` ne stvara `/dev/i2c-1` bez device tree overlay-a

Ispravna provjera u radio-setup.sh: `grep -q '^dtparam=i2c_arm=on$'` (exact match), sa fallbackom na `/boot/config.txt`.

#### Novi fajlovi

- `usr/local/bin/battery-reader.py` — čita IP2368 MCU svakih 30s, piše `/run/battery_status.json`
- `etc/systemd/system/battery-reader.service` — systemd unit, starts after multi-user.target

#### JSON schema

```json
{
  "percentage": 85,
  "voltage_v": 15.208,
  "current_ma": 1178,
  "power_w": 26.796,
  "charging": true,
  "status": "fast_charging",
  "cell_mv": [3813, 3796, 3797, 3802],
  "timestamp": 1713394823
}
```

#### Integracija u mesh

- `node-manager-static.sh` i `node-manager-acs.sh`: čitaju `/run/battery_status.json` i prosljeđuju `--battery-percentage` encoderu
- `encoder.py` / `decoder.py`: već imaju `battery_percentage` u protobuf shemi (field 31), nije trebalo mijenjati
- `mesh-status.py`: local panel pokazuje voltage/current/power/status; peer kartice pokazuju `⚡85%`

#### Hardverski problemi

- **mesh-78f3**: HAT nije bio dobro sjedeći na GPIO headerima — I2C bus potpuno prazan (`i2cdetect` ne vidi ni `0x2D`). Riješeno lemljenjem kontakata.
- **mesh-78f7**: Baterija se ispraznila, node se nije bootao. Nakon punjenja normalno se bootao.

#### Live stanje nodova (2026-04-18)

| Node | Baterija | Napon | Status |
|------|----------|-------|--------|
| mesh-f86f | 100% | 16.745V | full |
| mesh-7946 | ~37% | 14.543V | fast_charging |
| mesh-78f7 | 69% | 15.357V | fast_charging |
| mesh-78f3 | 58% | 15.208V | fast_charging |

### Branch ups-battery-monitor mergean u master i obrisan

---

## Sljedeće — branch `admin-panel-mdns`

Cilj: korisnik s mobitela može otvoriti admin panel bez znanja IP adrese, samo kroz `manet.local` hostname.

### Kontekst

- `mesh-status.py` sluša na portu **80** (konfigurirano u radio-setup.sh kao `ExecStart=... mesh-status.py 80`)
- `avahi-daemon` se **uklanja** pri prvom provisioning-u (`apt remove -y network-manager avahi*`) — namjerno, zbog potencijalnih konflikata s mesh routingom
- AP interface nije uvijek `wlan3` — ovisi o nodu, čita se iz `/var/lib/ap_interface` (runtime) i `/var/lib/no_mesh_if`
- mDNS broadcast treba ići samo na AP interface, ne na mesh interfaces (wlan0/1/2, bat0, br0)

### Implementacija — manet.local mDNS (branch `admin-panel-mdns`)

**Problem:** avahi je bio namjerno uklonjen pri provisioning-u (`apt remove avahi*`). AP interface nije uvijek `wlan3` — ovisi o nodu, čita se iz `/var/lib/ap_interface`. wlan3 je enslaved u `br0` pa nema vlastitu IPv4 adresu — avahi treba slušati na `br0`.

**Rješenje:**
- avahi-daemon reinstaliran, konfiguriran da **deny** bat0/wlan0/wlan1/wlan2 (ne allow — zbog br0)
- `host-name=manet` → svaki node broadcasta kao `manet.local`
- `/etc/avahi/services/manet-http.service` advertisa `_http._tcp` port 80
- `radio-setup.sh`: uklonjen avahi iz `apt remove`, dodana instalacija + konfiguracija
- Konfig fajlovi u tarbalu: `usr/local/share/manet/avahi-daemon.conf` i `manet-http.service`

**Testirano:** mobitel spojen na AP od mesh-78f3 uspješno otvara `http://manet.local`.

### Admin panel GUI poboljšanja (branch `admin-panel-mdns`)

- **Drag-to-resize panel**: na mobilnom uređaju između topology mape i info panela dodan je drag handle (pill ikona). Povlačenjem prema gore info panel se proširuje do cijelog ekrana. CSS media query na 768px prebacuje layout u column mode s `--topo-h` CSS varijablom.
- **Pinch-to-zoom na mapi**: implementiran vlastiti pinch zoom i pan na canvas elementu. Zoom se vrši oko točke između prstiju (ispravna matematika: `view.x = cx - (cx - view.x) * (newScale / view.scale)`). Jedan prst = pan ili drag noda, dva prsta = zoom. Uklonjeno `maximum-scale=1` iz viewport meta taga.
- **Fix: EUD AP interface false warnings**: GUI je prijavljivao wlan3 (EUD AP) kao "not in bat0" i "wpa_supplicant not running". Ispravak: učitava `/var/lib/no_mesh_if` pri health checku i isključuje te interface-e iz mesh/wpa_supplicant validacije. AP interface se klasificira kao `ap` role i provjerava samo hostapd/SSID status. wpa_supplicant nije potreban za AP mode (to vodi hostapd).

---

## 2026-04-18–19 (session 5) — branch `admin-panel-mdns`

### Fix: manet.local nije radio (avahi hostname conflict + no IPv4 on wlan3)

**Problem 1:** Svi nodovi dijele isti `br0` L2 broadcast domain (bat0 je bridge member od br0). Avahi konfig koristio `deny-interfaces=bat0,wlan0,wlan1,wlan2` što ostavlja `br0` aktivan — svi nodovi vide jedni druge-ove mDNS pakete pa avahi preimenova `manet` → `manet-2`, `manet-3`, `manet-4`.

**Pokušaj 1:** Promijenjen na `allow-interfaces=wlan3` — ali `wlan3` je bridge slave i nema vlastitu IPv4 adresu pa avahi može objaviti samo IPv6 link-local, ne IPv4. EUD browser dobiva fe80:: i ne može otvoriti HTTP.

**Konačno rješenje:** Dodan `address=/manet.local/<gateway_ip>` u dnsmasq config (`mesh-ip-manager.sh`). dnsmasq je već DNS server za EUD klijente (dhcp-option=6) i ima IPv4 gateway adresu noda. Svaki node odgovara na `manet.local` DNS upite s vlastitim IP-om — bez avahi, bez konflikata.

**Izmjena u `mesh-ip-manager.sh`:** Dodano u dnsmasq template (`/etc/dnsmasq.d/mesh-eud.conf`):
```
address=/manet.local/$br0_secondary
```

**`radio-setup.sh` avahi fix:** Avahi config promijenjen s `deny-interfaces` na `allow-interfaces=<ap_if>` (čita iz `/var/lib/no_mesh_if`). Nije kritično jer dnsmasq rješava DNS, ali avahi više ne uzrokuje konflikt.

**Deployjano live na sve 4 nodove** (mesh-eud.conf i avahi-daemon.conf ažurirani, dnsmasq restartan).

### Admin panel: peer detail drawer refaktoriran

**Staro ponašanje:** "THIS NODE" sekcija uvijek vidljiva na vrhu, drawer se otvara/zatvara klikom. Neighbor klik otvara drawer ispod headera.

**Novo ponašanje:**
- Drawer je uvijek otvoren — defaultno prikazuje lokalni node s "★ THIS NODE" u naslovu
- Klik na neighbor (canvas ili lista) → drawer prikazuje neighbor podatke, fetchano kroz `/api/peer/<ip>`
- Klik na centralni node (canvas) ili THIS NODE u listi → vraća na lokalni prikaz
- Klik na bilo koji node → side-panel skrola na vrh automatski

**Canvas highlight za selektirani node:**
- Selektirani node dobiva bijeli border, pojačan glow (radijus 4.5× umjesto 3×, opacity 0.7 umjesto 0.3), i blagi fill
- Lokalni (centralni) node je uvijek highlightan dok nije selektiran neighbor (jer je defaultno prikazan)
- `isSelected = (SELECTED_PEER_ID === null && n.is_me) || (SELECTED_PEER_ID === n.id)`

### 2026-04-22 - FER logo asset correction

- Lokalni `rpi5/rpi5-install/usr/local/share/manet/fer-logo.svg` placeholder zamijenjen je službenim FER SVG assetom preuzetim s `https://www.fer.unizg.hr/_pub/themes_static/fer_2025/default/img/FERlogo.svg`.
- `manet.local`, `perf.local` i `perf.local` auth stranica i dalje serviraju logo lokalno preko `/assets/fer-logo.svg`, ali sada koriste točan FER-ov originalni asset umjesto ručno generirane zamjene.

### 2026-04-22 - PERF to OVERVIEW shortcut

- `perf.local` header sada ima `OVERVIEW` gumb koji vodi na `http://manet.local/`.
- Stil gumba prati isti FER button system kao `MANAGE` na `manet.local`.

### 2026-04-22 - THIS NODE badge refinement

- U `manet.local` je uklonjena zvjezdica uz `THIS NODE`.
- Lokalni node sada koristi umjeren, profesionalan glow badge u FER paleti umjesto stare tekstualne oznake sa zvjezdicom.

### 2026-04-22 - Canvas single-touch disabled

- `manet.local` topo canvas više ne reagira na single-touch tap.
- Na touch uređajima jedan prst sada uvijek ostaje za scroll cijelog dashboarda; canvas zadržava samo two-finger pinch zoom.

### 2026-04-22 - PERF logout

- `perf.local` sada ima `LOGOUT` opciju na dnu stranice.
- Logout briše `manet_perf_auth` cookie kroz `/auth/perf-logout` i vraća korisnika na `perf.local` login ekran.

### 2026-04-22 - FER logo theme variants

- `manet.local` i `perf.local` headeri sada koriste veći službeni FER logo.
- Light tema prikazuje crni logo, a dark tema bijelu varijantu kroz theme-aware prikaz.
- `perf.local` login ekran koristi veliki službeni FER logo i dark/light prilagodbu preko `prefers-color-scheme`.

### 2026-04-22 - PERF login form overflow fix

- `perf.local` login input i submit button sada koriste `box-sizing: border-box` i `width: 100%`.
- Time password polje više ne strši van login boxa na užim ekranima.

### 2026-04-22 - Theme sync and login cleanup

- `manet.local` i `perf.local` sada prenose isti `theme` pri redirectu između dashboarda i login ekrana.
- `perf.local` login više nema žuti accent iza loga, a CTA koristi FER žutu umjesto plave.
- Dashboard header lockup koristi samo FER mark crop iz službenog SVG-a, bez punog wordmarka.

### 2026-04-22 - MANET node list order

- `MESH NODES` lista je premještena iznad topologije u desnom panelu.
- Selektirani node sada otvara detail inline unutar vlastitog entryja umjesto starog drawer panela.

### 2026-04-22 - Canvas select cleanup

- Klik na node na `manet.local` canvasu više ne koristi dodatni canvas-select flow.
- Canvas selection sada samo otvara inline detail u listi i glatko odskrola do odgovarajuceg node entryja.

### 2026-04-22 - Header layout refinement

- `manet.local` header je prebačen na tri reda, s prvim redom za FER logo i `MANET//STAT`.
- `perf.local` FER lockup je proširen tako da stane cijeli službeni logo bez cropa.

### 2026-04-22 - MANET compact node list

- `manet.local` je vraćen na raspored s canvasom iznad liste nodova.
- Lista nodova je zbijena i koristi `click to expand / click to collapse` inline detalje.

### 2026-04-22 - Canvas tooltip removed

- `manet.local` canvas više ne rendera floating mini info window nad nodeovima.
- Canvas interakcija je svedena na hover highlight i click-to-scroll/select ponašanje.

### 2026-04-22 - FER sign-only variants

- Dashboardi i login sada koriste lokalne sign-only FER SVG varijante iz `fer-logo-svg/`.
- Light koristi crni znak, a dark bijeli znak bez CSS invert workarounda.

### 2026-04-23 - Login logo rollback and larger dashboard logos

- `perf.local` login vraćen je na puni prethodni FER logo (`fer-logo.svg`).
- Dashboard logo lockup na `manet.local` i `perf.local` povećan je na približno `25vw` uz `clamp()` ograničenja.

### 2026-04-22 - MANET dashboard de-blue pass

- `manet.local` dashboard više ne koristi plave dekorativne akcente.
- Header, topo panel, badgevi, role chipovi i local-node highlight prebačeni su na neutralne tonove i FER žutu.

### 2026-04-23 - Yellow dashboard CTAs and login autofill

- `MANAGE` na `manet.local` i `OVERVIEW` na `perf.local` koriste puni FER yellow CTA stil umjesto muted/transparent varijante.
- `perf.local` login CTA sada se zove `Login`.
- Login forma pokušava automatski submitati kad browser autofilla management password.
- FER dashboard logo na `manet.local` i `perf.local` dodatno je povećan za čitljiviji header.

### 2026-04-23 - Overview status dot and larger FER logo

- `ALL OK` status na `manet.local` overview headeru više ne duplicira status točku.
- FER logo na `manet.local` i `perf.local` dodatno je povećan na jači desktop/mobile clamp.
- `perf.local` compact header više ne spušta FER logo na premalu `88px` širinu.

### 2026-04-23 - Browser login memory

- `perf.local` login forma sada izlaže browser-friendly `username` + `current-password` par kako bi Chrome/Google password manager lakše ponudio spremanje lozinke.
- `manet_perf_auth` cookie produžen je na 180 dana da se login dulje pamti u browseru.

### 2026-04-23 - MANAGE redirect fix

- `MANAGE` na `manet.local` više ne vodi direktno na `/auth/perf-login`.
- Redirect sada ide na `perf.local/`, tako da postojeći `manet_perf_auth` cookie preskače login kad je korisnik već prijavljen.

### 2026-04-23 - Header title spacing

- FER logo i `MANET//STAT` / `MANET//PERF` tekst približeni su u headeru na oba dashboarda.
- Smanjeni su `gap` i desni padding logo lockupa na desktop i mobile breakpointima.

### 2026-04-23 - Narrower logo box

- FER header lockup na `manet.local` i `perf.local` dodatno je sužen da ne rezervira prazan prostor desno od znaka.
- Logo box sada koristi uži clamp i `flex: 0 0 auto` kako bi naslov bio stvarno bliže logotipu.

### 2026-04-23 - Local mDNS service aliases

- Potvrđeno je da je `avahi-daemon` reflector na nodovima isključen (`enable-reflector=no`) i ograničen na AP-facing `br0`.
- Dodan je `mesh-mdns-update.sh` koji generira `/etc/avahi/hosts` iz lokalnog `br0` IP-a i `/var/run/mesh_node_registry`.
- `mumble.local` i `mtx.local` objavljuju se kroz stabilne service VIP adrese kad registry potvrdi da je servis aktivan, dok `manet.local` i `perf.local` ostaju lokalni na svakom AP nodeu.

### 2026-04-23 - Mumble leader publish fix

- Otkriveno je da `mumble-election.sh` pada na live nodovima zbog nedostajućeg `sqlite3` paketa.
- `radio-setup.sh` sada instalira `sqlite3` kako bi Mumble election mogao odabrati leadera i podignuti VIP.
- Sva tri `node-manager` toka sada publishe `--is-mumble-server` kad je lokalni node stvarni Mumble VIP holder.

### 2026-04-23 - Real mDNS responder for service aliases

- Pokazalo se da `/etc/avahi/hosts` nije dovoljan da mobiteli pouzdano resolveaju `mumble.local` i `mtx.local`.
- Dodan je `mesh-mdns-publisher.py` koji preko `python3-zeroconf` aktivno objavljuje `mumble.local` i `mtx.local` na `br0`.
- `mesh-mdns-update.sh` je vraćen na lokalne `manet.local` i `perf.local` Avahi host alias-e, dok service alias-e sada vodi zasebni responder.

### 2026-04-22 - PERF tab styling rollback

- `perf.local` tabovi vraćeni su na stariji underline stil.
- Aktivni tab više nema plavi/yellow fill blok, nego čisti žuti underline u FER paleti.

**Uklonjene komponente:** `local-toggle`, `local-panel`, `LOCAL_COLLAPSED`, `local-chevron`, `renderLocalPanel` → `peer-drawer-body`

### Systemd unit nazivi (post-reprovisioning)

Nakon reprovisioning-a s trenutnim tarbalijom:
- `batman-enslave.service` (ne `batman-if-setup.service`)
- `node-manager.service` (ne `node-manager-static.service`)

### Node status (kraj session 5 — 2026-04-19)

Svi 4 nodovi imaju ethernet u lab setupu. Mesh IP-ovi:

| Hostname   | LAN IP         | Mesh IP (br0 secondary) |
|------------|----------------|-------------------------|
| mesh-7946  | 192.168.1.50   | 10.30.2.51              |
| mesh-f86f  | 192.168.1.51   | 10.30.2.205             |
| mesh-78f7  | 192.168.1.53   | 10.30.2.117             |
| mesh-78f3  | 192.168.1.198  | 10.30.2.29              |

### 2026-04-29 - GPS/NTP local follow-up

- Root workspace review found new GPS files under `manet-dev/rpi5/rpi5-install`: `gps-reader.py`, `gps-reader.service`, GPS args in `encoder.py`, GPS reads in all `node-manager*.sh`, and GPS/chrony setup in `radio-setup.sh`.
- Completed the missing protobuf receive path locally: `decoder.py` now emits `GPS_LATITUDE`, `GPS_LONGITUDE`, and `GPS_ALTITUDE` from existing `NodeInfo.location`; `mesh-registry-builder.sh` now writes those fields into `/var/run/mesh_node_registry`.
- Hardened `radio-setup.sh` chrony setup: GPS SHM refclock and `allow 10.30.2.0/24` are now applied to active `chrony.conf` and to `chrony-default.conf`, `chrony-server.conf`, and `chrony-test.conf` templates when present, so `ethernet-autodetect.sh` does not wipe GPS NTP on later config swaps.
- `radio-setup.sh` now restarts `gps-reader.service` after enabling it so `/run/gps_status.json` is populated immediately after provisioning.
- Follow-up for Claude: validate the full end-to-end GPS payload on nodes after reprovision (`gpsd` -> `/run/gps_status.json` -> Alfred protobuf -> registry -> dashboard), and decide whether GPS `refclock SHM 0` should initially be `noselect` during field validation.
