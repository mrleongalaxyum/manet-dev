#!/usr/bin/env python3
"""Patch morse.ko to force morse_mac_set_txpower() requests to a fixed mBm.

This is a narrow binary patcher for the v1.16.4 aarch64 morse.ko shipped in
this project's 6.6.78-manet+ image. It replaces the clamp sequence in
morse_mac_set_txpower() with:

    mov w20, #<power_mbm>
    nop
    nop
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PATCH_OFFSET = 0x5B70
ORIGINAL_BYTES = bytes.fromhex("74c243b99f02156b94d2951a")
NOP = bytes.fromhex("1f2003d5")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Patch morse.ko to force TX power requests.")
    parser.add_argument("input", type=Path, help="Input morse.ko")
    parser.add_argument("output", type=Path, help="Output morse.ko")
    parser.add_argument("--power-mbm", type=int, required=True, help="Forced power in mBm, e.g. 2200")
    parser.add_argument("--allow-already-patched", action="store_true")
    return parser.parse_args()


def mov_w20_imm(power_mbm: int) -> bytes:
    if power_mbm < 0 or power_mbm > 0xFFFF:
        raise SystemExit("power-mbm must fit in a 16-bit MOVZ immediate")
    insn = 0x52800000 | (power_mbm << 5) | 20
    return insn.to_bytes(4, "little")


def main() -> int:
    args = parse_args()
    shutil.copyfile(args.input, args.output)
    data = bytearray(args.output.read_bytes())
    current = bytes(data[PATCH_OFFSET : PATCH_OFFSET + len(ORIGINAL_BYTES)])
    patch = mov_w20_imm(args.power_mbm) + NOP + NOP

    if current != ORIGINAL_BYTES:
        if args.allow_already_patched and current[4:] == NOP + NOP:
            print(f"Existing patch at 0x{PATCH_OFFSET:x}: {current.hex()} -> {patch.hex()}")
        else:
            raise SystemExit(
                f"Unexpected bytes at 0x{PATCH_OFFSET:x}: {current.hex()} "
                f"(expected {ORIGINAL_BYTES.hex()})"
            )

    data[PATCH_OFFSET : PATCH_OFFSET + len(patch)] = patch
    args.output.write_bytes(data)
    print(f"Wrote {args.output}")
    print(f"Patch @ 0x{PATCH_OFFSET:x}: {current.hex()} -> {patch.hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
