#!/usr/bin/env python3
"""
Waveshare UPS HAT (E) battery reader — IP2368 via I2C bus 1, address 0x2D.

Writes /run/battery_status.json atomically every READ_INTERVAL seconds.
On low battery, logs a warning. On critical battery, triggers a graceful shutdown.

JSON output:
  {
    "percentage":   85,          # SOC 0-100
    "voltage_mv":   16200,       # pack voltage in mV
    "current_ma":   -450,        # negative = discharging, positive = charging
    "power_mw":     7290,        # abs(voltage * current)
    "charging":     false,       # true when current > CHARGE_THRESHOLD_MA
    "status":       "discharging", # "charging" | "discharging" | "full" | "unknown"
    "timestamp":    1713394823
  }

Register map (IP2368, word reads, little-endian):
  0x00  Config      (default 0x000a)
  0x01  Control     (write 0x0055 to shutdown)
  0x02  Bus voltage — raw * 1.25 mV/LSB  (after byte-swap)
  0x03  Power       — raw mW (after byte-swap)
  0x04  Current     — raw * 1 mA/LSB, signed (after byte-swap)
  0x06  SOC         — high byte = whole %, low byte = 1/256 %
"""

import json
import logging
import os
import struct
import subprocess
import sys
import time

# ── Configuration ──────────────────────────────────────────────────────────────
I2C_BUS             = 1
I2C_ADDR            = 0x2D
READ_INTERVAL       = 30        # seconds between reads
OUTPUT_FILE         = "/run/battery_status.json"
LOW_BATTERY_PCT     = 15        # log warning below this
CRITICAL_BATTERY_PCT = 5        # shutdown below this
CHARGE_THRESHOLD_MA = 50        # mA — above this = charging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s battery-reader %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("battery-reader")


def open_bus():
    try:
        import smbus2
        return smbus2.SMBus(I2C_BUS)
    except ImportError:
        pass
    try:
        import smbus
        return smbus.SMBus(I2C_BUS)
    except ImportError:
        log.error("Neither smbus2 nor smbus is installed — run: apt-get install python3-smbus")
        sys.exit(1)


def read_word(bus, reg):
    """Read a 16-bit word and swap bytes (IP2368 is big-endian over SMBus)."""
    raw = bus.read_word_data(I2C_ADDR, reg)
    return ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)


def read_signed_word(bus, reg):
    val = read_word(bus, reg)
    if val >= 0x8000:
        val -= 0x10000
    return val


def read_battery(bus):
    voltage_raw = read_word(bus, 0x02)
    voltage_mv  = int(voltage_raw * 1.25)

    current_ma  = read_signed_word(bus, 0x04)

    # Power register (0x03) — use it if plausible, else derive
    try:
        power_raw = read_word(bus, 0x03)
        power_mw  = power_raw if power_raw > 0 else abs(voltage_mv * current_ma) // 1000
    except Exception:
        power_mw  = abs(voltage_mv * current_ma) // 1000

    # SOC register (0x06) — high byte = whole %, low byte = fractional
    soc_raw    = read_word(bus, 0x06)
    percentage = min(100, max(0, (soc_raw >> 8) & 0xFF))

    charging   = current_ma > CHARGE_THRESHOLD_MA
    if percentage >= 99 and charging:
        status = "full"
    elif charging:
        status = "charging"
    else:
        status = "discharging"

    return {
        "percentage": percentage,
        "voltage_mv": voltage_mv,
        "current_ma": current_ma,
        "power_mw":   power_mw,
        "charging":   charging,
        "status":     status,
        "timestamp":  int(time.time()),
    }


def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def trigger_shutdown(pct):
    log.critical("Battery critical (%d%%) — initiating graceful shutdown", pct)
    try:
        subprocess.run(["systemctl", "poweroff"], check=False)
    except Exception as e:
        log.error("Failed to trigger shutdown: %s", e)


def main():
    log.info("Starting — I2C bus %d addr 0x%02X, output %s", I2C_BUS, I2C_ADDR, OUTPUT_FILE)
    bus = open_bus()
    shutdown_triggered = False
    consecutive_errors = 0

    while True:
        try:
            data = read_battery(bus)
            consecutive_errors = 0
            write_atomic(OUTPUT_FILE, data)

            pct = data["percentage"]
            log.info(
                "%d%% | %dmV | %dmA | %dmW | %s",
                pct, data["voltage_mv"], data["current_ma"], data["power_mw"], data["status"],
            )

            if not shutdown_triggered:
                if pct <= CRITICAL_BATTERY_PCT and not data["charging"]:
                    shutdown_triggered = True
                    trigger_shutdown(pct)
                elif pct <= LOW_BATTERY_PCT and not data["charging"]:
                    log.warning("Low battery: %d%%", pct)

        except OSError as e:
            consecutive_errors += 1
            log.error("I2C read error (%d consecutive): %s", consecutive_errors, e)
            if consecutive_errors == 1:
                # Write unknown status so web UI shows something
                write_atomic(OUTPUT_FILE, {
                    "percentage": None,
                    "voltage_mv": None,
                    "current_ma": None,
                    "power_mw":   None,
                    "charging":   None,
                    "status":     "unknown",
                    "timestamp":  int(time.time()),
                })

        time.sleep(READ_INTERVAL)


if __name__ == "__main__":
    main()
