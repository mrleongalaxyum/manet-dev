# Morse Micro HaLow TX Power / BCF Handover

Date: 2026-04-20

This file is a handover for continuing the Morse Micro GW16167 / MM8108 BCF investigation.

## Operational note (2026-04-22)

- Live MANET nodes now expose compact radio rate summaries in Alfred gossip for `wlan0`, `wlan1` and `wlan2`.
- This is separate from the TX-power unlock work, but useful while validating radio behaviour after driver/BCF experiments because `perf.local` can now show current link modulation without extra per-node polling.
- Current live protobuf runtime on the nodes is still `python3-protobuf 4.21.12`; any regenerated `NodeInfo_pb2.py` used for operational deploys must stay compatible with that runtime.
The goal is lab-only experimental TX power work for EMC precompliance in a Faraday cage with dummy loads/attenuators.

## Hardware And Node

- Card/module: GW16167, reported as MM8108 / MF15457 class.
- Primary test node: `radio@192.168.1.51`, password `raspberry`, hostname `mesh-f86f`.
- Additional mesh nodes reached through `mesh-f86f`:
  - `radio@10.30.2.28`, hostname `mesh-78f7`.
  - `radio@10.30.2.182`, hostname `mesh-78f3`.
  - `radio@10.30.2.138`, hostname `mesh-7946`.
- Kernel: `6.6.78-manet+`.
- Driver version in dmesg: `v1.16.4-gdec5bc215b88`.
- Firmware loaded: `morse/mm8108b2-rl.bin`, size `456924`, dmesg CRC `0xe4799c8d`.
- Default BCF loaded: `morse/bcf_boardtype_0807.bin`, size `2081`.
- Current default BCF SHA256:
  `60d66d5df39066c9b1bb08577b1de3d65b140a14d22ec1d70732dfd6c9622db5`.
- Current original `morse.ko` SHA256:
  `24aa230816f70884e4f4af2576bf8b3030beb9a864b1ddb1371e39bc718714b1`.
- Original module backup on node:
  `/root/morse-module-backups/morse.ko.20260420-075822`.

The nodes currently have the EU26-request package installed, but the effective reported TX power is
clamped at `24.00 dBm`.

## Current Result

Nodes `.51`, `10.30.2.28`, `10.30.2.182`, and `10.30.2.138` have been successfully brought to the
highest currently observed effective setting:

```bash
/usr/sbin/iw dev wlan2 info
# txpower 24.00 dBm
```

The working recipe requires three pieces:

1. EU BCF power TLVs raised with valid BCF CRCs.
2. `dot11ah.ko` EU Linux regulatory rules patched above the stock 16 dBm limit.
3. `morse.ko` patched to force `morse_mac_set_txpower()` requests above the stock path.

Observed ceilings:

- EU22 BCF + `dot11ah` 22 + `morse` force2200 -> `txpower 22.00 dBm`.
- EU25 BCF + `dot11ah` 25 + `morse` force2500 -> `txpower 24.00 dBm`.
- EU26 BCF + `dot11ah` 26 + `morse` force2600 -> `txpower 24.00 dBm`.

So 25/26 dBm requests load successfully, but this driver/firmware stack reports a remaining
effective clamp at `24.00 dBm`. The nodes are intentionally left on the EU26-request artifacts
because that produced the highest observed reported value.

An all-regdomain 24 dBm BCF was later generated from the stock
`bcf_boardtype_0807.bin` with:

```bash
./morse-bcf-patch.py rpi5/rpi5-install/usr/lib/firmware/morse/bcf_boardtype_0807.bin \
  build/morse-bcf/bcf_boardtype_0807-all24.bin \
  --country ALL --power-dbm 24
```

This sets every TX power TLV in `.regdom_AU`, `.regdom_CA`, `.regdom_EU`,
`.regdom_GB`, `.regdom_JP`, and `.regdom_US` to `96` qdBm = `24.00 dBm`,
with regenerated per-regdomain CRCs. Alias copies were also created for the
BCF names in this image that are byte-identical to `bcf_boardtype_0807.bin`.

The first piece removes the firmware/BCF validation barrier.
The second piece makes `iw phy` advertise EU mapped channels at 22 dBm instead of 16 dBm.
The third piece avoids the remaining host/firmware set-power clamp path.

This is for the lab-only conducted/Faraday cage setup described in the project notes.

## Earlier Driver-Only Conclusion

Changing the host Linux driver alone was not enough to raise real HaLow TX power above 15 dBm.
The firmware/BCF regulatory data also enforces a cap.

Evidence:

- With original driver:
  - `iw dev wlan2 set txpower fixed 500` -> `txpower 5.00 dBm`
  - `1000` -> `10.00 dBm`
  - `1500` -> `15.00 dBm`
  - `1600` -> still `15.00 dBm`
  - `2200` -> still `15.00 dBm`
- A binary-patched driver forced the argument in `morse_mac_set_txpower()` to `2200` mBm.
  Even then, `iw dev wlan2 info` stayed capped at `15.00 dBm`.

So the useful path was BCF/regdomain generation plus host-side regulatory and set-power patches.

## Generated / Added Tools

Added local tools in repo root:

- `morse-bcf-patch.py`
  - Patches Morse ELF BCF `.regdom_XX` TX power TLVs.
  - Regenerates `.board_config` and `.regdom_XX` CRC fields.
- `morse-dot11ah-eu-power-patch.py`
  - Patches current `dot11ah.ko` EU `max_eirp` values.
  - Current image-specific offsets:
    - `.data` file offset: `0x8380`
    - `eu_reg_rules` symbol value: `0x4ff8`
    - rule size: `120`
    - `max_eirp` offset per rule: `0x10`
    - six EU rules patched.
- `morse-force-txpower-patch.py`
  - Patches current `morse.ko` at file offset `0x5b70`.
  - Replaces the clamp sequence in `morse_mac_set_txpower()` with `mov w20,#<power_mbm>; nop; nop`.

Generated artifacts:

```text
build/morse-bcf/bcf_boardtype_0807-eu16.bin
build/morse-bcf/bcf_boardtype_0807-eu22.bin
build/morse-bcf/bcf_boardtype_0807-eu25.bin
build/morse-bcf/bcf_boardtype_0807-eu26.bin
build/morse-bcf/bcf_boardtype_0807-all24.bin
build/morse-bcf/bcf_aw_hm677-all24.bin
build/morse-bcf/bcf_boardtype_0804-all24.bin
build/morse-bcf/bcf_boardtype_0a02-all24.bin
build/morse-bcf/bcf_mf15457-all24.bin
build/morse-bcf/dot11ah-eu22.ko
build/morse-bcf/dot11ah-eu25.ko
build/morse-bcf/dot11ah-eu26.ko
build/morse-bcf/morse-force2200-from-script.ko
build/morse-bcf/morse-force2500.ko
build/morse-bcf/morse-force2600.ko
```

Important artifact SHA256 values:

```text
c80d005e7476616a451f81b6c088e27a46e7d8417026f23bca4865a3989e9fd0  bcf_boardtype_0807-eu16.bin
370e2b9ed0b736f3c2e13148fcb9705427e6b60732f45f35503aa8855784d11f  bcf_boardtype_0807-eu22.bin
9d262b81d40ef3e60a05437a0ee02a5bdcfa893b1f5de76a111836efd70e1061  bcf_boardtype_0807-eu25.bin
973ea58204b5d7fd2fcb208699cf7b91a5eca5e48947eddef318db200bdb0b49  bcf_boardtype_0807-eu26.bin
21c144ee4d7fc81d865f80be12c4ea2e140e5b78dcf6b01f780038f4f57bc608  bcf_boardtype_0807-all24.bin
21c144ee4d7fc81d865f80be12c4ea2e140e5b78dcf6b01f780038f4f57bc608  bcf_aw_hm677-all24.bin
21c144ee4d7fc81d865f80be12c4ea2e140e5b78dcf6b01f780038f4f57bc608  bcf_boardtype_0804-all24.bin
21c144ee4d7fc81d865f80be12c4ea2e140e5b78dcf6b01f780038f4f57bc608  bcf_boardtype_0a02-all24.bin
21c144ee4d7fc81d865f80be12c4ea2e140e5b78dcf6b01f780038f4f57bc608  bcf_mf15457-all24.bin
19b1c99d90f31c5f9cf6c55550a666004d0b17d81e542f3df62afc2945977e7f  dot11ah-eu22.ko
b728b340fe6fdbf483a7029c6e911c860e574977e6f028553896a1fb564bd4c0  dot11ah-eu25.ko
00e516a34121b08c10d1ca3d576c64f4acc511891a21d26c378a418ff84c232b  dot11ah-eu26.ko
55743c932687f0022fed3573842357d4df69a4f264fa4f835386926bba146058  morse-force2200-from-script.ko
b1ab851f04d8c8f6faf176336a1f5c0e4fbe3807d2b7a70e2d7f234122d02f38  morse-force2500.ko
6557749d2802dcb893f5b7ebfede1b0f76b0a525d8b3755c6c71ad1b96038eed  morse-force2600.ko
```

## Repos / Local Sources

The following repos/folders exist locally under `/home/leon/Desktop/manet-dev`:

- `morse_driver/`
  - Public Linux driver clone.
  - Tag checked: `1.16.4`.
  - Commit seen: `7f95fe3`.
- `morse-firmware/`
  - Public BCF and firmware binaries.
- `mm-iot-esp32/`
  - Contains MBIN BCF C arrays and `convert-bin-to-mbin.py`.
- `mm-iot-cmsis/`
  - Contains MBIN headers and embedded BCF C arrays.
- `very-srs-manet/`
  - Clone of `github/very-srs/manet`, used for image/provisioning context.

Temporary parser outputs:

- `/tmp/bcf_regdom_records.json`
- `/tmp/bcf_regdom_unique.json`
- `/tmp/bcf_full_records.json`
- Parser scripts:
  - `/tmp/parse_bcf_corpus.py`
  - `/tmp/bcf_analyze_full.py`

## Driver Power Locations

Relevant public Linux driver files:

- `morse_driver/mac.c`
  - `morse_mac_get_max_txpower()`
  - `morse_mac_set_txpower()`
  - Module parameter `tx_max_power_mbm`, default `2200`.
- `morse_driver/command.c`
  - `morse_cmd_set_txpower()`
  - Sends `MORSE_CMD_ID_SET_TXPOWER`.
- `morse_driver/morse_commands.h`
  - TX power command uses `power_qdbm`.

The node lacks the exact kernel build tree:

- No `/lib/modules/6.6.78-manet+/build`.
- No `/proc/config.gz`.
- No `/boot/config-6.6.78-manet+`.
- No `Module.symvers`.

The module uses modversions, so rebuilding cleanly needs the exact kernel build artifacts.

## Host-Side Driver Hack History

Binary patch applied to a copy of `morse.ko`:

- Function: `morse_mac_set_txpower`.
- Original code at `.text` around address `0x5b30`.
- File offset patched: `0x5b70`.
- Replaced:
  - `ldr w20, [x19,#0x3c0]`
  - `cmp w20,w21`
  - `csel w20,w20,w21,le`
- With:
  - `mov w20,#0x898` (`2200` mBm)
  - `nop`
  - `nop`
- Patched bytes:
  `14 13 81 52 1f 20 03 d5 1f 20 03 d5`
- Patched module SHA256:
  `55743c932687f0022fed3573842357d4df69a4f264fa4f835386926bba146058`.
- 2500 mBm patch bytes:
  `94 38 81 52 1f 20 03 d5 1f 20 03 d5`
- 2600 mBm patch bytes:
  `14 45 81 52 1f 20 03 d5 1f 20 03 d5`

Initial result with the stock 15 dBm BCF:

- Module loaded.
- Real interface still reported `15.00 dBm`.
- Conclusion at that time: firmware/BCF cap remained.

Later result with the EU22 BCF plus patched `dot11ah.ko`:

- The same force patch did work.
- `iw dev wlan2 info` reported `txpower 22.00 dBm`.

Later result with EU25/EU26 packages:

- `morse.ko` force2500 and force2600 both loaded.
- Valid EU25/EU26 BCFs loaded with dmesg CRCs:
  - EU25 full-file BCF CRC seen on node: `0xc4ea589c`.
  - EU26 full-file BCF CRC seen on node: `0x720e0822`.
- `iw dev wlan2 info` reported `txpower 24.00 dBm` on all three reachable nodes.

Current deployed EU26-request backup timestamps:

- `mesh-f86f` / `192.168.1.51`: latest EU26 backup timestamp `20260420-202037`.
- `mesh-78f7` / `10.30.2.28`: latest EU26 backup timestamp `20260420-202516`.
- `mesh-78f3` / `10.30.2.182`: latest EU26 backup timestamp `20260420-202516`.
- `mesh-7946` / `10.30.2.138`: latest EU26 backup timestamp `20260420-214919`.

Backups are under:

```text
/root/morse-bcf-backups/bcf_boardtype_0807.bin.<timestamp>
/root/morse-module-backups/dot11ah.ko.<timestamp>
/root/morse-module-backups/morse.ko.<timestamp>
```

## BCF Format Findings

`bcf_boardtype_0807.bin`, `bcf_mf15457.bin`, `bcf_aw_hm677.bin`, `bcf_boardtype_0804.bin`, and `bcf_boardtype_0a02.bin` in the current local image are byte-identical for this module group.

Default file type:

```text
ELF 32-bit LSB RISC-V
```

Important sections in `bcf_boardtype_0807.bin`:

```text
.board_config off 0x2ed size 0xc0
.regdom_AU    off 0x3ad size 0x44
.regdom_CA    off 0x3f1 size 0x7c
.regdom_EU    off 0x46d size 0x88
.regdom_GB    off 0x4f5 size 0xa6
.regdom_JP    off 0x59b size 0xf2
.regdom_US    off 0x68d size 0x7c
```

BCF `.board_config` begins with:

```text
ef be ad de ...
```

This is little-endian `0xdeadbeef`.

## EU Regdomain Details

Original `.regdom_EU` begins:

```text
49 a3 b4 f0 7c 00 00 00 45 55 00 2e ...
```

Interpretation:

- First u32: `0xf0b4a349`, internal check/signature word.
- Second u32: `0x0000007c`, apparent payload length.
- Marker: `EU\0.`
- Then TLV-like records.

Observed TLVs:

- `0xc9 len4`: center frequency in kHz, little-endian.
- `0xca len1`: bandwidth in MHz.
- `0xcc len2`: TX power in quarter-dBm.
- `0xcd len1`: op_class.
- `0x67`, `0x68`: unknown regulatory/policy metadata.

EU records in the default MF15457 BCF:

```text
863.500 MHz BW 1 MHz power 60 qdBm = 15.00 dBm op_class 181
864.500 MHz BW 1 MHz power 60 qdBm = 15.00 dBm op_class 181
865.500 MHz BW 1 MHz power 60 qdBm = 15.00 dBm op_class 181
866.500 MHz BW 1 MHz power 60 qdBm = 15.00 dBm op_class 181
867.500 MHz BW 1 MHz power 60 qdBm = 15.00 dBm op_class 181
866.000 MHz BW 2 MHz power 60 qdBm = 15.00 dBm op_class 186
864.000 MHz BW 2 MHz power 60 qdBm = 15.00 dBm op_class 186
```

The seven EU power field file offsets are:

```text
0x0490
0x04a0
0x04b0
0x04c0
0x04d0
0x04e0
0x04f0
```

Each is `3c 00` = `60` qdBm = `15 dBm`.

## Direct BCF Edit Failed Before CRC Formula Was Known

Changing EU power fields from:

```text
3c 00
```

to:

```text
40 00
```

for `16 dBm` produced a BCF that loaded by the Linux driver but failed firmware init:

```text
FW manifest pointer not set (ret:-5)
morse_firmware_init failed: -5
probe failed with error -5
```

The bad BCF had SHA256:

```text
79d31c8e...
```

Dmesg BCF CRC during that failed boot was:

```text
0x14d35a1c
```

Conclusion: first word of `.regdom_EU` must be regenerated/validated.

This is now solved.

## BCF CRC Formula

The BCF checks are standard zlib/IEEE CRC32, but with a regdomain seed derived from the board CRC.

For `.board_config`:

```python
board_len = u32le(board_config, 12)
board_crc = zlib.crc32(board_config[8:8 + board_len + 8]) & 0xffffffff
put_u32le(board_config, 4, board_crc)
```

For `.regdom_XX`:

```python
REGDOMAIN_SALT = b"# Morse Micro regulatory domain #"
reg_len = u32le(regdom, 4)
seed = zlib.crc32(REGDOMAIN_SALT, board_crc) & 0xffffffff
reg_crc = zlib.crc32(regdom[4:4 + reg_len + 8], seed) & 0xffffffff
put_u32le(regdom, 0, reg_crc)
```

For the default `bcf_boardtype_0807.bin`:

```text
board_crc = 0x4ef7a950
regdomain seed = 0xed5c25d0
stock EU CRC = 0xf0b4a349
EU16 CRC = 0xa9af3332
EU22 CRC = 0x029c0582
```

The full-file dmesg CRC after loading EU22 BCF on node 51:

```text
0xc40c4019
```

## BCF Corpus Analysis

Parsed BCF-like candidates from:

- `rpi5/`
- `morse-firmware/`
- `mm-iot-esp32/`
- `mm-iot-cmsis/`
- `very-srs-manet/`
- `/tmp/morse-bcf-1.15.3`
- `/tmp/very-srs-install` when present

Latest parser run:

```text
files/records 38 320
countries Counter({'US': 76, 'AU': 69, 'CA': 65, 'JP': 40, 'EU': 26, 'GB': 18, 'IN': 8, 'KR': 6, 'NZ': 6, 'SG': 6})
same payload diff-check groups 14
same payload+board diff-check groups 0
same payload+board+meta diff-check groups 0
```

Critical inference:

The check word is not only a function of the regdomain payload.
The same regdomain payload can have different check words for different board configs.
However, for the same `(payload + board_config)` pair, the check word was consistent in the corpus.

Therefore the generator likely computes the check from at least:

- `.board_config`
- selected `.regdom_XX` payload

Possibly also metadata, but current corpus did not prove metadata is needed once board_config is included.

## Existing High-Power Blocks

No existing EU block in the corpus was above 15 dBm.

EU candidates found:

```text
MF15457 MBIN EU check 0x7065c432 max 15.0 dBm board f0e20e46
MF15457 ELF  EU check 0xf0b4a349 max 15.0 dBm board a56443f5
```

Existing high-power blocks are mostly AU/CA/US:

- MF15457 AU:
  - ELF check `0x07ac62ea`, max about `21.5 dBm`.
  - MBIN check `0x8ca965b2`, max about `21.75 dBm`.
- MF15457 CA/US:
  - max about `21.5 dBm`.
- Other modules have higher values, up to about `28 dBm`, but not for EU and not necessarily compatible with this board.

Practical implication:

- Transplanting an entire valid AU/US regdomain might boot, but it changes frequencies/channel plan.
- Editing EU frequencies/powers requires regenerating the check.

## MBIN Notes

`mm-iot-esp32/framework/tools/buildsystem/convert-bin-to-mbin.py` can pack BCF sections into MBIN TLVs, but it does not regenerate the inner regdomain check word.

MBIN TLV types from `mbin.h`:

```text
FIELD_TYPE_MAGIC          0x8000
FIELD_TYPE_BCF_BOARD_CONFIG 0x8100
FIELD_TYPE_BCF_REGDOM       0x8101
FIELD_TYPE_BCF_BOARD_DESC   0x8102
FIELD_TYPE_BCF_BUILD_VER    0x8103
FIELD_TYPE_BCF_CHIPS        0x8104
```

Magic:

```text
MMBC = 0x43424d4d
```

For `FIELD_TYPE_BCF_REGDOM`, payload starts with:

```c
struct mbin_regdom_hdr {
    uint8_t country_code[2];
    uint16_t reserved;
};
```

Then the same inner regdomain blob follows.

## Firmware Validation Lead Used To Find CRC Formula

The firmware binary is an ELF:

```text
rpi5/rpi5-install/usr/lib/firmware/morse/mm8108b2-rl.bin:
ELF 32-bit LSB executable, UCB RISC-V, RVC, soft-float ABI, statically linked, not stripped
```

Useful strings in `.host_rodmem`:

```text
0x2203a0 BCF regdom invalid
0x2203b4 BCF board_config parse failed
0x2203d4 BCF regdom parse failed
0x2203f0 # Morse Micro regulatory domain #
0x220414 bcf_regdom_validate
0x220428 bcf_validate
```

Initial RISC-V disassembly around validation code:

- Likely `bcf_validate` starts near `0x203880`.
- It validates `.board_config` magic `0xdeadbeef`.
- It appears to zero the first 4 bytes before computing/comparing the board_config check.
- It calls into a hash/check function around the `jal 0xc1eee` / `jal 0xc1d92` sites.
- It validates the regdomain separately near the references to `bcf_regdom_validate`.

Useful xrefs found:

```text
0x203a84 -> string 0x2203a0 "BCF regdom invalid"
0x203bb4 -> string 0x2203b4 "BCF board_config parse failed"
0x203bc2 -> string 0x2203d4 "BCF regdom parse failed"
0x203a78 -> string 0x220414 "bcf_regdom_validate"
0x203924 -> string 0x220428 "bcf_validate"
0x2039fc -> string 0x2203f0 "# Morse Micro regulatory domain #"
```

This lead is now resolved:

- `bcf_validate` checks board magic `0xdeadbeef`.
- Board check is CRC32 over `board_config[8:]` with length `board_len + 8`.
- Regdomain check is CRC32 over `regdom[4:]` with length `reg_len + 8`, seeded by CRC32 of `# Morse Micro regulatory domain #` using `board_crc` as seed.

## Common Hash Attempts

Tried common direct hashes/checks on regdomain payload variants:

- CRC32
- inverted CRC32
- Adler32
- CRC16/XMODEM variants
- FNV-like and other simple hashes in earlier tests
- payload-only ranges:
  - `inner[4:]`
  - `inner[8:]`
  - `inner[12:]`
  - check-zeroed inner blob
- board + payload variants:
  - `board_config + inner[4:]`
  - `board_config + inner[8:]`
  - `board_config + inner[12:]`

The final match was zlib CRC32 with the board-derived regdomain seed above.

## Useful Commands

Check node state:

```bash
sshpass -p raspberry ssh -o StrictHostKeyChecking=no radio@192.168.1.51 \
  "iw dev wlan2 info; systemctl is-active wpa_supplicant-s1g-wlan2.service"
```

Dmesg filter:

```bash
sudo dmesg -wH | grep -iE 'morse|bcf|firmware|txpower|tx power|max tx|set_txpower|mBm|qdbm'
```

Show loaded BCF:

```bash
dmesg | grep -iE 'Loaded BCF|Loaded firmware|morse'
```

Run current corpus parser:

```bash
python3 /tmp/bcf_analyze_full.py
```

## Reproduction Commands

Generate 22 dBm EU BCF:

```bash
./morse-bcf-patch.py \
  --country EU \
  --power-dbm 22 \
  rpi5/rpi5-install/usr/lib/firmware/morse/bcf_boardtype_0807.bin \
  build/morse-bcf/bcf_boardtype_0807-eu22.bin
```

Patch `dot11ah.ko` EU regulatory max to 22 dBm:

```bash
./morse-dot11ah-eu-power-patch.py \
  --power-dbm 22 \
  rpi5/rpi5-install/lib/modules/6.6.78-manet+/extra/morse/dot11ah.ko \
  build/morse-bcf/dot11ah-eu22.ko
```

Patch `morse.ko` to force 2200 mBm:

```bash
./morse-force-txpower-patch.py \
  --power-mbm 2200 \
  rpi5/rpi5-install/lib/modules/6.6.78-manet+/extra/morse/morse.ko \
  build/morse-bcf/morse-force2200-from-script.ko
```

Install on node 51, then reload:

```bash
sshpass -p raspberry scp build/morse-bcf/bcf_boardtype_0807-eu22.bin radio@192.168.1.51:/tmp/
sshpass -p raspberry scp build/morse-bcf/dot11ah-eu22.ko radio@192.168.1.51:/tmp/
sshpass -p raspberry scp build/morse-bcf/morse-force2200-from-script.ko radio@192.168.1.51:/tmp/

sshpass -p raspberry ssh radio@192.168.1.51 'echo raspberry | sudo -S bash -c "
set -e
k=$(uname -r)
install -m 0644 /tmp/bcf_boardtype_0807-eu22.bin /lib/firmware/morse/bcf_boardtype_0807.bin
install -m 0644 /tmp/bcf_boardtype_0807-eu22.bin /usr/lib/firmware/morse/bcf_boardtype_0807.bin
install -m 0644 /tmp/dot11ah-eu22.ko /lib/modules/$k/extra/morse/dot11ah.ko
install -m 0644 /tmp/morse-force2200-from-script.ko /lib/modules/$k/extra/morse/morse.ko
depmod $k
systemctl stop wpa_supplicant-s1g-wlan2.service || true
ip link set wlan2 down || true
modprobe -r morse || true
modprobe -r dot11ah || true
modprobe dot11ah
modprobe morse
systemctl restart wpa_supplicant-s1g-wlan2.service
sleep 2
/usr/sbin/iw dev wlan2 info
"'
```

## Node 51 Backups Created

BCF backups:

```text
/root/morse-bcf-backups/bcf_boardtype_0807.bin.20260420-081604
/root/morse-bcf-backups/bcf_boardtype_0807.bin.20260420-081642
```

Module backups:

```text
/root/morse-module-backups/dot11ah.ko.20260420-081818
/root/morse-module-backups/morse.ko.20260420-081948
```

## Remaining Work Plan

1. ~~Decide whether to bake these experimental artifacts into `rpi5/rpi5-install` image~~ — **DONE (2026-04-28).** All three patched files replaced in image. Five BCF aliases updated to `all24` content. Released as v0.22-halow-24dbm. Build artifacts kept in `build/morse-bcf/`.
2. Verify conducted output with measurement gear. `iw` confirms software state, not calibrated RF output.
3. Consider rebuilding `morse.ko` properly from source once the exact kernel build tree is available, instead of keeping the binary force patch.

## Final Working Model

BCF generation is solved for ELF BCF files:

- Update EU `0xcc` power qdBm fields.
- Recompute board CRC.
- Recompute regdomain CRC using the board-derived salt seed.

To make Linux actually request and report 22 dBm on the current image, BCF generation alone is not enough.
Patch `dot11ah.ko` and `morse.ko` as described above.

## 2026-04-20 Official-Power MT7916 Setting

After testing the blunt MT7915/MT7916 `force30` module, the AW7916-NPD radios
were moved back to a more official/conservative lab setting:

- `wlan0` / 2.4 GHz: `23.00 dBm`
- `wlan1` / 5 GHz: `24.00 dBm`
- `wlan2` / HaLow: `24.00 dBm`

The MT7915/MT7916 module ceiling is now generated as 24 dBm:

```bash
./mt7915-force-target-power-patch.py \
  rpi5/rpi5-install/usr/lib/modules/6.6.78-manet+/kernel/drivers/net/wireless/mediatek/mt76/mt7915/mt7915e.ko.xz \
  build/mt76-power/mt7915e-force24-official.ko.xz \
  --target-dbm 24 \
  --xz
```

Artifact:

```text
build/mt76-power/mt7915e-force24-official.ko.xz
sha256: 206140e9e2e78ab8da9fa9e1fcf149a6eba165a29d98b29f176ab179c5b54549
```

Runtime commands used after module reload:

```bash
sudo /usr/sbin/iw dev wlan0 set txpower fixed 2300
sudo /usr/sbin/iw dev wlan1 set txpower fixed 2400
```

Persistence:

- Added `/etc/systemd/system/manet-txpower.service`.
- Enabled it in `multi-user.target.wants`.
- Deployed and enabled it on all four live nodes.
- The service reapplies:
  - `wlan0 = 2300 mBm`
  - `wlan1 = 2400 mBm`
  - `wlan2 = 2400 mBm`

Deployment verified on all four active nodes:

| Node | Address used | wlan0 | wlan1 | wlan2 |
| --- | --- | ---: | ---: | ---: |
| mesh-f86f | `192.168.1.51` | 23 dBm | 24 dBm | 24 dBm |
| mesh-78f7 | `10.30.2.28` via mesh-f86f jump | 23 dBm | 24 dBm | 24 dBm |
| mesh-78f3 | `10.30.2.182` via mesh-f86f jump | 23 dBm | 24 dBm | 24 dBm |
| mesh-7946 | `10.30.2.138` via mesh-f86f jump | 23 dBm | 24 dBm | 24 dBm |

Backups before replacing the `force30` module:

```text
mesh-f86f: /root/mt76-module-backups/mt7915e.ko.xz.20260420-223456.pre-official24
mesh-78f7: /root/mt76-module-backups/mt7915e.ko.xz.20260420-223803.pre-official24
mesh-78f3: /root/mt76-module-backups/mt7915e.ko.xz.20260420-223714.pre-official24
mesh-7946: /root/mt76-module-backups/mt7915e.ko.xz.20260420-223714.pre-official24
```
