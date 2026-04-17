# MANET Change History

## 2026-04-17

### Izmjene skripti
- Povučene skripte s nodova mesh-78f3 (192.168.1.198) i mesh-78f7 (192.168.1.53) te uspoređene s lokalnim rpi5-install tarballom
- Ažurirane skripte u rpi5-install (s referentnog nodea 78f7): `gateway-route-manager.sh`, `radio-setup.sh`, `ethernet-autodetect.sh`, `mesh-ip-manager.sh`
- Kreiran live snapshot skripti po nodovima: `rpi5/rpi5-live/78f3/`, `rpi5/rpi5-live/78f7/`

### Bugovi
- **ethernet-autodetect.sh** (78f3): sadržavala buggy liniju `systemctl restart systemd-networkd 2>/dev/null || true` (l.102) — nije prisutna na referentnom 78f7, uklonjena iz rpi5-install
- **mesh-ip-manager.sh**: razlikovala se između 78f3 i 78f7 — ažurirana na 78f7 referentnu verziju
