# Measurements Dashboard — Handover

## Kontekst projekta

Akademski zadatak: eksperimentalna analiza IEEE 802.11ah (HaLow) MANET mreže za kritične komunikacije.
Mjerenja se provode na 4-nodnoj RPi5 MANET mreži s batman-adv L2 mesh protokolom.
Dashboard `perf.local` služi kao **control plane** za pokretanje mjernih sesija i upravljanje interfaceima — **ne** kao live monitoring.

### Trenutni status implementacije
- `perf-dashboard.py` postoji i radi kao Python `http.server` na portu 8081.
- `perf-dashboard.service`, `perf-http.service` i `/etc/sudoers.d/perf` postoje u RPi5 install treeju.
- `mesh-status.py` je proširen control endpointima za interface toggle, tx power, HaLow channel, iperf server/client i ping.
- Ispravan systemd unit za admin panel je `mesh-status.service`; `manet-status.service` ne postoji i ne smije se koristiti u push/deploy skriptama.
- Basic auth je isključen za admin UI; `/admin` ne smije otvarati browser login prozor. Runtime control endpointi na `mesh-status.py` nisu admin-form endpointi: dostupni su server-to-server pozivima iz `perf-dashboard.py` za localhost/mesh subnet IP-eve.
- `perf-dashboard.py` CSS ima mobile breakpoint za uske ekrane: header/nav se lome, kartice i forme idu u jednu kolonu, global action buttons u 2 kolone, a tablice dobivaju horizontalni scroll samo unutar tablice.
- Measurement i radio config akcije daju foreground overlay feedback: start/running/failed/completed za mjerenja te applying/failed/applied za HaLow i Wi-Fi channel promjene.
- Measurement progress prikazuje lagane status brojke bez dodatnog radio opterećenja: completed/total, elapsed, current pair/test, current elapsed i zadnji završeni rezultat. Saved sessions prikazuje simple avg/min/max sažetak za TCP/UDP Mbps, RTT, jitter i loss kad su metrike dostupne.
- Saved sessions imaju `DELETE` akciju s browser confirmation dialogom prije brisanja cijele sesije.
- `perf.local` proxy u `mesh-status.py` mora prosljeđivati i `DELETE`, inače brisanje sesije kroz port 80 vrati HTML/501 pa frontend prijavi da odgovor nije validan JSON.
- Aktivni dashboard tab se sprema u `localStorage` (`perfDashboardTab`) i URL hash (`#sessions`, `#measure`, itd.) da refresh stranice ostane na istom tabu. Dashboard HTML se šalje s `Cache-Control: no-store` zbog mobilnog browser cachea.
- Dugi iperf/ping control pozivi moraju imati timeout dulji od trajanja testa. Kratki HTTP timeout uzrokuje lažne `timed out` failove i može ostaviti iperf server zauzet za sljedeći test.
- Hop matrix tablica i hop-count računanje su uklonjeni iz perf dashboarda; hop/multihop vizualizacija ostaje u glavnom `mesh-status.py` topology prikazu.
- HaLow runtime info se prvo pokušava čitati kroz Morse driver tooling (`morse_cli` channel info, JSON ili parsable text), jer `iw` može prijaviti krivi standardni Wi-Fi kanal. `wpa_supplicant_s1g` config ostaje samo fallback/debug.
- Radio link summaries za `wlan0`, `wlan1` i `wlan2` sada se skupljaju lokalno na svakom nodu iz `iw dev <iface> station dump`, pa se kroz Alfred type `68` propagiraju do `perf.local`. Nema dodatnog dashboard-side streamanja po nodovima.
- Format prikaza je kompaktan i mobile-safe: `MCSx Nn [GI] [BW]`, npr. `MCS9 N1 SGI 20M`.
- Trenutni protobuf field names su ostali povijesni (`*_tx_mcs`, `*_rx_mcs`), ali sadržaj tih polja više nije samo goli MCS broj nego kratki rate summary string.

### Otvoreno / sljedeći koraci
- Provjeriti točnu `morse_cli` runtime sintaksu na fizičkom nodu. Implementacija trenutno pokušava više varijanti, uključujući `morse_cli -i wlan2 channel -j`, `--json` i text output.
- Ako produkcijski Morse alat koristi drugačiji morsectrl transport call, zamijeniti listu pokušaja u `get_halow_driver_info()`.
- Nakon deploya potvrditi da `/api/topology` i `/api/data` vraćaju `halow_source: "morse"` za `wlan2`; `halow_source: "config"` znači da driver alat nije vratio parsable runtime podatke.

### Implementirano (2026-04-24)
- Alfred koordinirani radio-state workflow (type 71/72) je implementiran i verificiran na svim 4 nodovima.
- `halow-mcs-summary.py` je zajednički extractor za `wlan0/wlan1/wlan2`; node-manager ga zove lokalno prije Alfred publisha.
- `NodeInfo_pb2.py` u install treeju je ručno zadržan kompatibilan s runtimeom na nodovima (`protobuf 4.21.12`). Ako se opet generira novijim `protoc`-om i ostavi `runtime_version` import, encoder/decoder će pasti na živim nodovima.
- `uptime_seconds` i `cpu_load_average` sada se ispravno šalju u Alfred payload (čitaju se iz `/proc/uptime` i `/proc/loadavg` u sva tri node-managera).
- TQ za lokalni (self) node je `None` — batman nema self-TQ; badge se ne prikazuje za THIS NODE.
- Header local time tece u realnom vremenu (setInterval, ne zamrznuti server timestamp).
- CPU load prikazuje se na 2 decimale.
- `perf.local` header accent strip usklađen s `manet.local` dark yellow gradientom.
- Sve izmjene mergane na `master`, release `v0.9-runtime-dashboard-fixes` na GitHubu, tarball na Ventumu i Colorado SFTP.

---

## Mesh arhitektura

### Nodovi
| Hostname    | LAN IP        | Mesh IP (br0) |
|-------------|---------------|----------------|
| mesh-78f3   | 192.168.1.198 | 10.30.2.182    |
| mesh-78f7   | 192.168.1.53  | 10.30.2.28     |
| mesh-f86f   | 192.168.1.51  | 10.30.2.72     |
| mesh-7946   | 192.168.1.50  | 10.30.2.138    |

SSH: `radio@<ip>`, password: `raspberry`

### Radio interfacei (identično na svim nodovima)
| Interface | Driver      | Band           | Uloga u meshu |
|-----------|-------------|----------------|----------------|
| wlan0     | mt7915e     | 2.4 GHz        | batman-adv (bat0) |
| wlan1     | mt7915e     | 5 GHz          | batman-adv (bat0) |
| wlan2     | morse_usb   | HaLow  | batman-adv (bat0) |
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

**Kritični zahtjev za propagaciju:**
- Globalni up/down radio state ne smije se raditi kao direktni HTTP fan-out po nodovima. To može presjeći mesh usred promjene i ostaviti dio nodova u starom stanju.
- Novi state mora ići kroz Alfred kao staged radio-state paket: `version`, `activate_at`, željeno stanje po interfaceu (`wlan0`, `wlan1`, `wlan2`) i inicijator.
- Svaki nod nakon primitka paketa lokalno validira da može primijeniti state, spremi pending state i objavi ACK kroz Alfred.
- Dashboard smije pokrenuti coordinated apply tek kad svi očekivani/reachable nodovi objave ACK za istu verziju.
- Ako ACK timeout istekne, apply se ne radi; UI mora prikazati koji nodovi nisu potvrdili.
- Per-node toggle može ostati dijagnostička/dev opcija, ali produkcijski "all up/down" mora koristiti Alfred koordinaciju.

**Implementirani Alfred radio-state tok:**
- Alfred type `71`: radio-state package (`kind=radio_state`) i cancel package (`kind=radio_cancel`)
- Alfred type `72`: radio ACK payload (`kind=radio_ack`, `version`, `hostname`, `ok`, `error`)
- Local staged file: `/var/run/mesh_pending_radio_state.json`
- Local ACK file: `/var/run/mesh_radio_ack_version`
- Applied marker: `/var/run/mesh_applied_radio_version`
- Persistent desired radio state: `/var/lib/mesh_radio_state.json`
- Agent: `/usr/local/bin/mesh-radio-state.py sync`
- Node-manager varijante (`node-manager.sh`, `node-manager-static.sh`, `node-manager-acs.sh`) pozivaju radio-state sync u glavnoj petlji.
- `batman-if-setup.sh`, `sae-watchdog.sh`, `channel-election.sh` i node-manager channel restart logika moraju poštovati `/var/lib/mesh_radio_state.json`, da watchdog/channel election ne vrate namjerno ugašen radio.
- Verificirano nakon deploya: `wlan0=down` i `wlan1=down` kroz Alfred workflow daju 4/4 ACK, nakon activationa na sva 4 noda ostaje samo `wlan2: active`; `wpa_supplicant@wlan0` i `wpa_supplicant@wlan1` su `inactive`, a `wpa_supplicant-s1g-wlan2` je `active`.
- UI nakon ACK/scheduled poruke sada čeka `activate_at`, poll-a `/api/topology` i daje finalnu foreground obavijest: executed ako svi ciljani nodovi potvrde željeni active/down state, ili error s popisom nodova gdje stanje nije potvrđeno.
- UI za sve `down` radio naredbe sada traži browser confirmation prije Alfred stagea. `up` naredbe ostaju bez confirmationa.

**Po nodu zasebno:**
- Isti toggleovi ali samo za odabrani nod

**Safety guard (obavezno):**
- Zabrani gašenje interfacea ako bi to ostavilo nod bez ijednog aktivnog batman-adv interfacea
- Zabrani gašenje interfacea ako je to jedina veza između dva dijela mesha (particija detection)
- Logika: provjeri `batctl o` prije togglea — ako bi nod ostao isoliran, odbij s porukom

**Implementacija applyja na nodu:**
- Ugasiti wlan interface znači zaustaviti njegov `wpa_supplicant` systemd service. Samo `batctl if del` + `ip link down` nije dovoljno, jer service ili watchdog mogu interface vratiti gore.
- Upaliti wlan interface znači dignuti link, startati odgovarajući `wpa_supplicant` service i osigurati da je interface ponovno u `bat0`.
- Standardni Wi-Fi koristi `wpa_supplicant@wlan0.service` / `wpa_supplicant@wlan1.service`.
- HaLow koristi Morse/S1G supplicant service (`wpa_supplicant-s1g-wlan2.service` ili aktualni template naziv u install treeju). Provjeriti točan unit name na nodu prije finalnog koda.

```bash
# Ugasiti interface:
sudo batctl if del wlan0
sudo systemctl stop wpa_supplicant@wlan0.service
sudo ip link set wlan0 down

# Upaliti interface:
sudo ip link set wlan0 up
sudo systemctl start wpa_supplicant@wlan0.service
sudo batctl if add wlan0
```

Za HaLow apply treba koristiti S1G/Morse service, npr.:
```bash
sudo batctl if del wlan2
sudo systemctl stop wpa_supplicant-s1g-wlan2.service
sudo ip link set wlan2 down

sudo ip link set wlan2 up
sudo systemctl start wpa_supplicant-s1g-wlan2.service
sudo batctl if add wlan2
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
- Gase se wlan0 i wlan1, mesh radi samo na HaLow
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
POST /api/interface/toggle      # Legacy/dev direct toggle; global production toggle mora ići kroz Alfred staged radio-state
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
POST /api/control/interface     # Dev/per-node direct toggle; global production apply mora koristiti Alfred ACK workflow
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
   radio ALL=(ALL) NOPASSWD: /usr/sbin/batctl, /sbin/ip link set wlan*, /bin/systemctl start wpa_supplicant@wlan*.service, /bin/systemctl stop wpa_supplicant@wlan*.service, /bin/systemctl start wpa_supplicant-s1g-wlan*.service, /bin/systemctl stop wpa_supplicant-s1g-wlan*.service
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

---

## 2026-04-19 UI refresh / FER identity

- `manet.local` i `perf.local` su prebačeni na FER vizualni smjer: Paper grey / Deep space black / Power Yellow / Deep Blue, uz FER logo u headeru.
- Dodan je dark mode toggle na oba GUI-ja. Izbor se pamti u `localStorage` (`manetUiTheme`), a prvi load prati system preference.
- `perf.local` ima čvrsti sticky tab bar, kompaktniji header nakon scrolla i diskretniji FER accent strip ispod tabova.
- Button styling je usklađen s temom: primary/action gumbi koriste FER žutu, sekundarni deep-blue/outline, destruktivne akcije ostaju crvene ali bez pastelnog alert izgleda.
- Status pillovi poput `INET OK` su smireni na neutralnu površinu s diskretnim status rubom da ne iskaču iz teme.
- Auto-refresh ostaje periodički i ne prekida aktivno editiranje input/select polja.
