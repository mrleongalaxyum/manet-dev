# Measurements Dashboard — Handover

## Kontekst projekta

Akademski zadatak: eksperimentalna analiza IEEE 802.11ah (HaLow) MANET mreže za kritične komunikacije.
Mjerenja se provode na 4-nodnoj RPi5 MANET mreži s batman-adv L2 mesh protokolom.
Dashboard `perf.local` služi kao **control plane** za pokretanje mjernih sesija i upravljanje interfaceima — **ne** kao live monitoring.

### Trenutni status implementacije
- `perf-dashboard.py` postoji i radi kao Python `http.server` na portu 8081.
- `perf-dashboard.service`, `perf-http.service` i `/etc/sudoers.d/perf` postoje u RPi5 install treeju.
- `mesh-status.py` je proširen control endpointima za interface toggle, tx power, HaLow channel, iperf server/client i ping.
- Basic auth je isključen za admin UI; `/admin` ne smije otvarati browser login prozor. Runtime control endpointi na `mesh-status.py` nisu admin-form endpointi: dostupni su server-to-server pozivima iz `perf-dashboard.py` za localhost/mesh subnet IP-eve.
- `perf-dashboard.py` CSS ima mobile breakpoint za uske ekrane: header/nav se lome, kartice i forme idu u jednu kolonu, global action buttons u 2 kolone, a tablice dobivaju horizontalni scroll samo unutar tablice.
- Measurement i radio config akcije daju foreground overlay feedback: start/running/failed/completed za mjerenja te applying/failed/applied za HaLow i Wi-Fi channel promjene.
- Measurement progress prikazuje lagane status brojke bez dodatnog radio opterećenja: completed/total, elapsed, current pair/test, current elapsed i zadnji završeni rezultat. Saved sessions prikazuje simple avg/min/max sažetak za TCP/UDP Mbps, RTT, jitter i loss kad su metrike dostupne.
- Saved sessions imaju `DELETE` akciju s browser confirmation dialogom prije brisanja cijele sesije.
- Dugi iperf/ping control pozivi moraju imati timeout dulji od trajanja testa. Kratki HTTP timeout uzrokuje lažne `timed out` failove i može ostaviti iperf server zauzet za sljedeći test.
- Hop matrix tablica i hop-count računanje su uklonjeni iz perf dashboarda; hop/multihop vizualizacija ostaje u glavnom `mesh-status.py` topology prikazu.
- HaLow runtime info se prvo pokušava čitati kroz Morse driver tooling (`morse_cli` channel info, JSON ili parsable text), jer `iw` može prijaviti krivi standardni Wi-Fi kanal. `wpa_supplicant_s1g` config ostaje samo fallback/debug.

### Otvoreno / sljedeći koraci
- Provjeriti točnu `morse_cli` runtime sintaksu na fizičkom nodu. Implementacija trenutno pokušava više varijanti, uključujući `morse_cli -i wlan2 channel -j`, `--json` i text output.
- Ako produkcijski Morse alat koristi drugačiji morsectrl transport call, zamijeniti listu pokušaja u `get_halow_driver_info()`.
- Nakon deploya potvrditi da `/api/topology` i `/api/data` vraćaju `halow_source: "morse"` za `wlan2`; `halow_source: "config"` znači da driver alat nije vratio parsable runtime podatke.

---

## Mesh arhitektura

### Nodovi
| Hostname    | LAN IP        | Mesh IP (br0) |
|-------------|---------------|----------------|
| mesh-78f3   | 192.168.1.198 | 10.30.2.226    |
| mesh-78f7   | 192.168.1.53  | 10.30.2.6      |
| mesh-f86f   | 192.168.1.51  | 10.30.2.182    |
| mesh-7946   | 192.168.1.50  | 10.30.2.160    |

SSH: `radio@<ip>`, password: `raspberry`

### Radio interfacei (identično na svim nodovima)
| Interface | Driver      | Band           | Uloga u meshu |
|-----------|-------------|----------------|----------------|
| wlan0     | mt7915e     | 2.4 GHz        | batman-adv (bat0) |
| wlan1     | mt7915e     | 5 GHz          | batman-adv (bat0) |
| wlan2     | morse_usb   | 900 MHz HaLow  | batman-adv (bat0) |
| wlan3     | brcmfmac    | 2.4 GHz AP     | EUD AP (br0, ne u bat0) |

### Mrežni stack
```
bat0 (BATMAN_V) ← wlan0 + wlan1 + wlan2
br0 (bridge)    ← bat0 + end0 + wlan3 (ako EUD wireless mode)
```

### Ključni servisi na nodovima
- `node-manager.service` — Alfred gossip publisher, servisne elections
- `batman-enslave.service` — enslava radije u bat0
- `ethernet-autodetect.service` — gateway promotion/demotion (NAT, default route)
- `sae-watchdog.service` — restart wpa_supplicant ako bat0 izgubi interfacee
- `battery-reader.service` — INA219 (I2C 0x40), piše `/run/battery_status.json`

---

## perf.local Dashboard — Specifikacija

### Hosting
- Pokreće se na **svim nodovima** (uvijek upaljen, port 8081)
- Laptop pristupa kroz wlan3 AP bilo kojeg noda — nema ovisnosti o ethernet/gateway statusu
- mDNS: `perf.local` → port 8081 (ne miješati s postojećim mesh-status.py na portu 80)
- Tech stack: **Python 3 + http.server + inline HTML/JS** (bez npm/node, isti pattern kao mesh-status.py)
- Upload na GitHub/Ventum dostupan samo kada gateway ima internet

### Avahi mDNS config
- Nova datoteka: `/etc/avahi/services/perf-http.service` (port 8081, ime "MANET Perf Dashboard")
- Postojeći: `/etc/avahi/services/manet-http.service` (port 80, mesh-status.py) — ne dirati

### Kritični fajlovi za referencu
| Fajl | Svrha |
|------|-------|
| `rpi5/rpi5-install/usr/local/bin/mesh-status.py` | Postojeći admin panel — patterns za http.server, IP restriction, `/api/peer/<ip>` proxy |
| `rpi5/rpi5-install/usr/local/bin/ethernet-autodetect.sh` | Gateway detection — trigger za pokretanje/zaustavljanje perf dashboarda |
| `rpi5/rpi5-install/etc/avahi/services/manet-http.service` | mDNS template |
| `rpi5/rpi5-install/etc/mesh.conf` | Node config (REGULATORY_DOMAIN, HALOW_REGULATORY_DOMAIN, AUTO_CHANNEL, itd.) |
| `rpi5/rpi5-install/usr/local/bin/channel-election.sh` | Kanal election logika — razumjeti prije implementacije channel override |
| `rpi5/rpi5-install/usr/local/bin/batman-if-setup.sh` | Interface enslave/release logika |

---

## Funkcionalnosti dashboarda

### 1. Interface Control
**Globalno (svi nodovi odjednom):**
- Toggle 2.4 GHz (wlan0) ON/OFF na svim nodovima
- Toggle 5 GHz (wlan1) ON/OFF na svim nodovima
- Toggle HaLow (wlan2) ON/OFF na svim nodovima

**Po nodu zasebno:**
- Isti toggleovi ali samo za odabrani nod

**Safety guard (obavezno):**
- Zabrani gašenje interfacea ako bi to ostavilo nod bez ijednog aktivnog batman-adv interfacea
- Zabrani gašenje interfacea ako je to jedina veza između dva dijela mesha (particija detection)
- Logika: provjeri `batctl o` prije togglea — ako bi nod ostao isoliran, odbij s porukom

**Implementacija togglea na nodu:**
```bash
# Ugasiti interface (makni iz bat0, down):
sudo batctl if del wlan0
sudo ip link set wlan0 down

# Upaliti interface (dodaj nazad u bat0):
sudo ip link set wlan0 up
sudo batctl if add wlan0
```

### 2. HaLow Channel & Bandwidth Selection
- Prikaz trenutnog kanala i bandwidtha mora dolaziti iz Morse drivera (`morse_cli`/morsectrl channel info), jer `iw dev wlan2 info` može prijaviti krivi standardni Wi-Fi kanal/frekvenciju.
- `wpa_supplicant-wlan2-s1g.conf` opisuje željenu konfiguraciju, ali nije pouzdan runtime izvor istine nakon driver/channel promjena.
- Dropdown odabir kanala (EU S1G kanali: 863.5–868 MHz, 1 MHz / 2 MHz / 4 MHz širina)
- Propagacija na sve nodove kroz mesh (POST na svaki nod)
- **Napomena:** Trenutno channel election radi kroz Alfred consensus (`channel-election.sh`) — novi dashboard treba bypass mechanism koji piše direktno u wpa_supplicant config i restarta

### 3. Mjerne sesije (iperf3)

**Session metadata (obavezno za svako mjerenje):**
- `session_label` — slobodan unos (npr. "outdoor-50m", "indoor-1hop")
- `timestamp` — automatski (ISO8601)
- `topology_snapshot` — koji interfacei aktivni, HaLow kanal/BW, 2.4 GHz kanal
- GPS koordinate (opcionalno, za budući GPS modul)

**iperf3 test tipovi:**
| Test | Parametri | Mjeri |
|------|-----------|-------|
| TCP throughput | `-t 30` | propusnost |
| UDP throughput | `-u -b 100M -t 30` | propusnost, gubitak |
| UDP jitter | `-u -b 10M -t 30 --get-server-output` | jitter, gubitak |
| Packet loss | `-u -b <max> -t 30` | loss% pri opterećenju |
| Reverse | `-R -t 30` | asimetrija |
| Parallel streams | `-P 4 -t 30` | realni promet |

**Source/Destination odabir:**
- Dropdown: odaberi source nod i destination nod
- Dashboard zna mesh IP svakog noda
- Pokreće `iperf3 -s` na destination, `iperf3 -c <dst_ip>` na source
- Hop count se trenutno ne prikazuje i ne sprema u perf dashboardu. Ako kasnije zatreba, računati ga odvojeno i pažljivo jer `batctl o` koristi interface MAC-ove, ne nužno primary node MAC.

**Rezultati:**
- JSON output iperf3 (`--json` flag) sprema se u `/var/log/manet-measurements/<session_label>/<timestamp>_<src>_<dst>.json`
- CSV summary s ključnim metrikama za lakšu kasniju obradu

### 4. Upload rezultata
- Gumb "Upload to GitHub" — git commit + push novog JSON/CSV
- Gumb "Upload to Ventum" — spakira `/var/log/manet-measurements` u `tar.gz` i šalje na Ventum HTTP upload preko `curl -u`
- **Ne uploadati automatski** — samo na eksplicitni zahtjev

### 5. Pregled prošlih mjerenja
- Lista sesija (session_label, timestamp, broj testova)
- Pregled raw JSON i CSV po sesiji
- **Bez grafova** — obrada podataka kasnije kroz AI

---

## Format rezultata

### JSON (po testu)
```json
{
  "session_label": "outdoor-50m",
  "timestamp": "2026-04-19T10:30:00Z",
  "test_type": "tcp_throughput",
  "source_node": "mesh-78f3",
  "destination_node": "mesh-7946",
  "active_interfaces": ["wlan0", "wlan1", "wlan2"],
  "halow_channel": 5,
  "halow_bw": "1MHz",
  "ch_2g": "6",
  "gps_source": null,
  "gps_destination": null,
  "iperf3_result": { ... }
}
```

### CSV summary (po sesiji)
```
timestamp,session_label,test_type,src_node,dst_node,active_interfaces,halow_channel,halow_bw,tcp_mbps,udp_mbps,jitter_ms,loss_pct,rtt_avg_ms,rtt_min_ms,rtt_max_ms
```

---

## Topologija testiranja

### Scenariji za akademski rad

**1. Single-hop (direktni susjedi)**
- Source i destination su fizički blizu, direktna RF veza
- Mjeri maksimalnu propusnost po radiju

**2. Multi-hop (2+ skoka)**
- Source i destination s jednim ili više posrednih nodova
- Mjeri degradaciju propusnosti i latency po hopu

**3. Radio isolation test**
- Gasi se jedan radio (npr. wlan1 5GHz), mjeri se utjecaj na propusnost/latency
- Relevantno za "hibridna arhitektura" analizu

**4. HaLow-only mode**
- Gase se wlan0 i wlan1, mesh radi samo na HaLow 900 MHz
- Mjeri HaLow standalone performanse (domet vs propusnost)

**5. Channel width comparison**
- Isti test na HaLow 1 MHz / 2 MHz / 4 MHz
- Mjeri propusnost vs range tradeoff

**6. TAK/CoT traffic**
- Generira se CoT XML promet na portu 8087/8088 uz paralelni iperf3
- Mjeri QoS degradaciju pod opterećenjem

---

## Implementacijski plan

### Fajlovi za kreirati
```
rpi5/rpi5-install/usr/local/bin/perf-dashboard.py     # Glavni dashboard server (port 8081)
rpi5/rpi5-install/etc/systemd/system/perf-dashboard.service
rpi5/rpi5-install/etc/avahi/services/perf-http.service  # perf.local mDNS
```

### Modifikacije postojećih fajlova
```
rpi5/rpi5-install/usr/local/bin/ethernet-autodetect.sh  # Start/stop perf-dashboard.service na gateway promjeni
```

### API endpointi na perf-dashboard.py
```
GET  /                          # Dashboard HTML
GET  /api/topology              # Trenutna topologija (nodovi, interfacei, gateway/internet)
POST /api/interface/toggle      # Toggle wlan interface na nodu(ovima)
POST /api/halow/channel         # Postavi HaLow kanal/BW na sve nodove
POST /api/wifi/channel          # Postavi 2.4/5 GHz kanal na sve nodove
POST /api/txpower               # Postavi TX power po nodu/interfaceu
POST /api/measure/start         # Pokretanje iperf3 sesije
GET  /api/measure/status        # Status tekućeg mjerenja
GET  /api/sessions              # Lista prošlih sesija
GET  /api/sessions/<id>         # Dohvati rezultate sesije
DELETE /api/sessions/<id>       # Obriši saved session uz UI confirmation
POST /api/upload/github         # Git push rezultata
POST /api/upload/ventum         # curl -u upload tar.gz bundlea na Ventum
```

### Control API na svakom nodu (dodati u mesh-status.py)
Control API je mesh-local/server-to-server: dozvoljen je samo za localhost ili IP iz mesh subneta (`ipv4_network`), bez admin Basic autha. Admin UI je također bez Basic autha da se na mobitelu ne pojavljuje login dialog.

```
POST /api/control/interface     # { "iface": "wlan0", "state": "up"|"down" }
POST /api/control/halow_channel # { "channel": 42, "bw": "2MHz" }
POST /api/control/wifi_channel  # { "interface": "wlan0", "channel": 6 }
POST /api/control/txpower       # { "iface": "wlan0", "dbm": 15 }
POST /api/iperf/server/start    # Pokreni iperf3 -s
POST /api/iperf/server/stop
POST /api/iperf/client/run      # { "server_ip": "...", "test_type": "...", ...params }
POST /api/ping/run              # { "target": "...", "count": 100, "interval": 0.2 }
```

---

## Rad bez interneta

Dashboard mora raditi i kada nodovi **nemaju internet konekciju** (field deployment):

- `perf.local` dostupan kroz mesh (bat0 → br0 → laptop na wlan3 AP ili end0)
- Sva mjerenja se spremaju lokalno na gateway nodu (`/var/log/manet-measurements/`)
- Upload na GitHub/Ventum je **odgođen** — gumb postane aktivan tek kada internet dostupan (`/run/mesh-gateway.state` postoji)
- Dashboard detektira internet: `curl -s --max-time 2 -o /dev/null https://github.com && echo ok`
- Ako nema interneta: gumbi "Upload" su disabled s tooltipom "No internet"
- iperf3 testovi rade isključivo unutar mesha (mesh IP adrese) — ne trebaju internet

## Napomene za implementaciju

1. **sudo bez passworda za specifične komande** — dodati u `/etc/sudoers.d/perf`:
   ```
   radio ALL=(ALL) NOPASSWD: /usr/sbin/batctl, /sbin/ip link set wlan*
   ```

2. **iperf3 server management** — koristiti `iperf3 -s -D --one-off` (daemon, jedan klijent pa exit) da ne blokira

3. **Partition detection** prije interface togglea:
   - `batctl o` daje TQ per originator
   - Ako gašenje wlan0 ostavlja nod s TQ=0 prema nekom originatoru koji se jedino vidi kroz taj interface — zabrani toggle

4. **HaLow channel override** zaobilazi `channel-election.sh` — potrebno postaviti flag `/var/run/halow-channel-override` da election skripta ne overridea manualnu selekciju. Runtime prikaz kanala/BW mora se čitati kroz Morse driver (`morse_cli`/morsectrl channel JSON), ne iz `iw`.

5. **GPS integracija (future)** — `/run/gps_location.json` format: `{"lat": 45.123, "lon": 15.456, "accuracy": 3.0}` — dashboard će ga uključiti u snapshot ako postoji

---

## Ventum / GitHub pristup

- GitHub: `mrleongalaxyum/manet-dev` (public) — measurements u `measurements/` folderu
- Ventum measurements upload: `curl -u <user>:<password> -T <file> https://manet.ventum.hr/upload/rpi5/measurements/<file>`
- Runtime config overridei u `/etc/mesh.conf`: `ventum_upload_url`, `ventum_auth` ili `ventum_user` + `ventum_password`
