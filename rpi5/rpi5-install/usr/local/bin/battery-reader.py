#!/usr/bin/env python3
"""
Waveshare UPS HAT (E) battery reader.

Hardware: INA219 current/voltage monitor at I2C bus 1, address 0x40.
MCU for power control at 0x2D (not used for reading).

Writes /run/battery_status.json atomically every READ_INTERVAL seconds.
Triggers graceful poweroff at CRITICAL_BATTERY_PCT% while discharging.

JSON schema:
  {
    "percentage":  85,        # estimated SOC 0-100 from voltage curve
    "voltage_v":   4.921,     # load (bus) voltage in V
    "current_ma":  -312.4,    # negative=discharging, positive=charging
    "power_w":     1.536,     # power in W
    "charging":    false,
    "status":      "discharging",   # charging | discharging | full | unknown
    "timestamp":   1713394823
  }

INA219 register map (16-bit big-endian):
  0x00  Config
  0x01  Shunt voltage  (10 µV/LSB, signed)
  0x02  Bus voltage    (4 mV/LSB, bits 15:3)
  0x03  Power          (2 mW/LSB)
  0x04  Current        (0.1 mA/LSB, signed) — requires calibration write first
  0x05  Calibration

Calibration for 32 V / 2 A range:
  Cal = 4096, current_lsb = 0.1 mA, power_lsb = 2 mW
"""

import json
import logging
import os
import subprocess
import sys
import time

I2C_BUS              = 1
I2C_ADDR             = 0x40
READ_INTERVAL        = 30        # seconds
OUTPUT_FILE          = "/run/battery_status.json"
LOW_BATTERY_PCT      = 15
CRITICAL_BATTERY_PCT = 5
CHARGE_THRESHOLD_MA  = 50        # mA above this = charging

# INA219 registers
_REG_CONFIG      = 0x00
_REG_SHUNT_V     = 0x01
_REG_BUS_V       = 0x02
_REG_POWER       = 0x03
_REG_CURRENT     = 0x04
_REG_CALIBRATION = 0x05

# Calibration values for 32 V / 2 A
_CAL_VALUE    = 4096
_CURRENT_LSB  = 0.1   # mA per LSB
_POWER_LSB    = 0.002 # W per LSB

# Config: 32 V range, gain /8 (320 mV), 12-bit 32-sample averaging, continuous
_CONFIG_VALUE = 0x399F

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s battery-reader %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("battery-reader")


def open_bus():
    for mod in ("smbus2", "smbus"):
        try:
            m = __import__(mod)
            return m.SMBus(I2C_BUS)
        except ImportError:
            continue
    log.error("Neither smbus2 nor smbus installed — run: apt-get install python3-smbus")
    sys.exit(1)


def read_reg(bus, reg):
    """Read 16-bit big-endian register."""
    data = bus.read_i2c_block_data(I2C_ADDR, reg, 2)
    return (data[0] << 8) | data[1]


def write_reg(bus, reg, value):
    bus.write_i2c_block_data(I2C_ADDR, reg, [(value >> 8) & 0xFF, value & 0xFF])


def calibrate(bus):
    write_reg(bus, _REG_CALIBRATION, _CAL_VALUE)
    write_reg(bus, _REG_CONFIG, _CONFIG_VALUE)


def voltage_to_pct(v):
    """
    Estimate SOC% from bus voltage for a 4S Li-ion pack (4 × 21700).
    4S full = 16.8 V, 4S empty = 12.0 V (3.0 V/cell cutoff).
    Linear approximation — good enough for a field indicator.
    """
    FULL_V  = 16.8
    EMPTY_V = 12.0
    if v >= FULL_V:
        return 100
    if v <= EMPTY_V:
        return 0
    return int((v - EMPTY_V) / (FULL_V - EMPTY_V) * 100)


def read_battery(bus):
    write_reg(bus, _REG_CALIBRATION, _CAL_VALUE)

    raw_bus = read_reg(bus, _REG_BUS_V)
    voltage_v = ((raw_bus >> 3) * 0.004)

    raw_cur = read_reg(bus, _REG_CURRENT)
    if raw_cur > 32767:
        raw_cur -= 65536
    current_ma = raw_cur * _CURRENT_LSB

    raw_pwr = read_reg(bus, _REG_POWER)
    power_w = raw_pwr * _POWER_LSB

    percentage = voltage_to_pct(voltage_v)
    charging   = current_ma > CHARGE_THRESHOLD_MA

    if percentage >= 99 and charging:
        status = "full"
    elif charging:
        status = "charging"
    else:
        status = "discharging"

    return {
        "percentage": percentage,
        "voltage_v":  round(voltage_v, 3),
        "current_ma": round(current_ma, 1),
        "power_w":    round(power_w, 3),
        "charging":   charging,
        "status":     status,
        "timestamp":  int(time.time()),
    }


def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def main():
    log.info("Starting — I2C bus %d addr 0x%02X", I2C_BUS, I2C_ADDR)
    bus = open_bus()
    calibrate(bus)

    shutdown_triggered = False
    consecutive_errors = 0

    while True:
        try:
            data = read_battery(bus)
            consecutive_errors = 0
            write_atomic(OUTPUT_FILE, data)

            pct = data["percentage"]
            log.info("%d%% | %.3fV | %.1fmA | %.3fW | %s",
                     pct, data["voltage_v"], data["current_ma"], data["power_w"], data["status"])

            if not shutdown_triggered:
                if pct <= CRITICAL_BATTERY_PCT and not data["charging"]:
                    log.critical("Battery critical (%d%%) — initiating graceful shutdown", pct)
                    shutdown_triggered = True
                    subprocess.run(["systemctl", "poweroff"], check=False)
                elif pct <= LOW_BATTERY_PCT and not data["charging"]:
                    log.warning("Low battery: %d%%", pct)

        except OSError as e:
            consecutive_errors += 1
            log.error("I2C read error (%d consecutive): %s", consecutive_errors, e)
            if consecutive_errors == 1:
                write_atomic(OUTPUT_FILE, {
                    "percentage": None, "voltage_v": None, "current_ma": None,
                    "power_w": None, "charging": None, "status": "unknown",
                    "timestamp": int(time.time()),
                })
            if consecutive_errors >= 5:
                log.error("Too many errors, recalibrating...")
                try:
                    calibrate(bus)
                except Exception:
                    pass
                consecutive_errors = 0

        time.sleep(READ_INTERVAL)


if __name__ == "__main__":
    main()
