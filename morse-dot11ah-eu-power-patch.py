#!/usr/bin/env python3
"""Patch EU max_eirp in the Morse dot11ah.ko regulatory table.

This is a narrow binary patcher for the v1.16.4 dot11ah.ko shipped in this
project's 6.6.78-manet+ image. It updates the six EU reg_rules max_eirp fields
from the default 1600 mBm to the requested value.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DATA_SECTION_FILE_OFFSET = 0x8380
EU_REG_RULES_VALUE = 0x4FF8
REG_RULE_SIZE = 120
MAX_EIRP_OFFSET_IN_RULE = 0x10
EU_RULE_COUNT = 6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Patch EU max_eirp in dot11ah.ko.")
    parser.add_argument("input", type=Path, help="Input dot11ah.ko")
    parser.add_argument("output", type=Path, help="Output dot11ah.ko")
    parser.add_argument("--power-dbm", type=float, required=True, help="New max EIRP in dBm")
    parser.add_argument(
        "--expected-old-mbm",
        type=int,
        default=1600,
        help="Expected current value in mBm, default: 1600",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    power_mbm = round(args.power_dbm * 100)

    shutil.copyfile(args.input, args.output)
    data = bytearray(args.output.read_bytes())

    eu_file_offset = DATA_SECTION_FILE_OFFSET + EU_REG_RULES_VALUE
    for idx in range(EU_RULE_COUNT):
        field_off = eu_file_offset + idx * REG_RULE_SIZE + MAX_EIRP_OFFSET_IN_RULE
        old_mbm = int.from_bytes(data[field_off : field_off + 4], "little")
        if old_mbm != args.expected_old_mbm:
            raise SystemExit(
                f"Unexpected max_eirp at 0x{field_off:x}: {old_mbm} mBm "
                f"(expected {args.expected_old_mbm})"
            )
        data[field_off : field_off + 4] = power_mbm.to_bytes(4, "little")
        print(f"EU rule {idx}: file 0x{field_off:x}: {old_mbm} -> {power_mbm} mBm")

    args.output.write_bytes(data)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
