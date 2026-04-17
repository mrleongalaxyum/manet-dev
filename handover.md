# MANET Project Handover

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

---

## LAN Uređaji (lokalne IP adrese za spajanje)

| Port (WAN) | Lokalna IP     | Hostname  | SSH port |
|------------|----------------|-----------|----------|
| 3254       | 192.168.1.198  | mesh-78f3 | 22       |
| 3255       | 192.168.1.51   | mesh-f86f | 22       |
| 3256       | 192.168.1.53   | mesh-78f7 | 22       |
| 3257       | 192.168.1.50   | mesh-7946 | 22       |

- **User:** radio
- **Password:** raspberry

Spajanje na uređaje se vrši putem lokalnih IP adresa (port 22).

---

## Stanje skripti (rpi5-install)

Skripte u `rpi5/rpi5-install/usr/local/bin/` su referentni izvor. Povučene su s uređaja mesh-78f3 (192.168.1.198) dana 2026-04-17.

**Referentni node: mesh-78f7 (192.168.1.53)** — na njemu sve radi ispravno.

**Datoteke ažurirane s uređaja (povučene s 78f7 kao referentnog):**
- `gateway-route-manager.sh`
- `radio-setup.sh`
- `ethernet-autodetect.sh` — uklonjena linija `systemctl restart systemd-networkd` (bug na 78f3, ne postoji na 78f7)
- `mesh-ip-manager.sh` — novija verzija s 78f7

**Razlike između nodova (2026-04-17):**
- `ethernet-autodetect.sh`: 78f3 ima buggy liniju `systemctl restart systemd-networkd` (l.102), 78f7 nema
- `mesh-ip-manager.sh`: 78f3 i 78f7 se razlikuju — 78f7 je referentna

**Datoteke prisutne lokalno ali ne na uređaju (dio install paketa, ne tools):**
- `batman-if-setup.sh.bak`, `chronyc`, `morse_cli`, `NodeInfo.proto`, `README.md`, `version.txt`
- `etc/systemd/network/`, `etc/udev/`, `etc/manet_version.txt`
