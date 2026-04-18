# MANET Change History

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

### Plan

Reinstalirati avahi-daemon ali s restriktivnom konfiguracijom:
- `allow-interfaces=<AP_IFACE>` — samo AP interface
- `deny-interfaces=bat0,br0,wlan0,wlan1,wlan2` — eksplicitno zabraniti mesh
- Custom `.service` file koji broadcasta `manet` na portu 80
- radio-setup.sh: ukloniti avahi iz `apt remove`, dodati avahi konfiguraciju i service file
