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
