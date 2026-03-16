#!/usr/bin/env python3
"""
Bluetooth Proximity Screen Control – laptop daemon
===================================================

Monitors a paired Android phone over Bluetooth Low Energy.
When the phone moves further than ~5 m (configurable RSSI threshold) the
laptop screen is locked.  When the phone comes back within range the screen
wakes automatically.

Usage
-----
    python proximity_monitor.py            # uses config.json / defaults
    python proximity_monitor.py --dry-run  # log only, no screen changes
    python proximity_monitor.py --setup    # interactive first-time setup

Requirements
------------
    pip install bleak
    (see requirements.txt)
"""

import argparse
import json
import logging
import os
import sys
import time

# ---------------------------------------------------------------------------
# Project-local imports (same directory)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import config as cfg_module
import screen_control
from bluetooth_scanner import scan_once

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("proximity_monitor")


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

class _State:
    NEAR = "NEAR"       # phone is close – screen on
    FAR  = "FAR"        # phone is far   – screen locked


# ---------------------------------------------------------------------------
# Core daemon loop
# ---------------------------------------------------------------------------

def run(dry_run: bool = False) -> None:
    """Start the proximity monitoring loop (runs indefinitely)."""
    cfg = cfg_module.load()

    device_name    = cfg["device_name"]
    device_address = cfg["device_address"]
    lock_threshold = cfg["rssi_lock_threshold"]
    hysteresis     = cfg["rssi_hysteresis"]
    scan_interval  = cfg["scan_interval_seconds"]
    miss_limit     = cfg["miss_count_before_lock"]
    scan_duration  = cfg["ble_scan_duration_seconds"]
    screen_enabled = cfg["enable_screen_control"] and not dry_run

    log_level = getattr(logging, cfg.get("log_level", "INFO").upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)

    unlock_threshold = lock_threshold + hysteresis

    logger.info("=== Bluetooth Proximity Screen Control ===")
    logger.info("Target device name : %s", device_name or "(any)")
    logger.info("Target device addr : %s", device_address or "(any)")
    logger.info("Lock RSSI threshold: %d dBm  (~5 m)", lock_threshold)
    logger.info("Wake RSSI threshold: %d dBm  (hysteresis +%d)", unlock_threshold, hysteresis)
    logger.info("Screen control     : %s", "ENABLED" if screen_enabled else "DISABLED (dry-run)")
    logger.info("Scan every         : %.1f s", scan_interval)
    logger.info("Miss count limit   : %d consecutive misses", miss_limit)
    logger.info("Press Ctrl-C to stop.\n")

    state = _State.NEAR   # Assume screen is on at startup
    miss_count = 0        # Consecutive scans without finding the phone

    while True:
        result = scan_once(device_name, device_address, scan_duration)

        if not result.found:
            miss_count += 1
            logger.debug("Phone not found (miss %d/%d)", miss_count, miss_limit)
        else:
            miss_count = 0
            logger.debug("Phone RSSI = %d dBm  (state=%s)", result.rssi, state)

        # ---------- decide whether to change state ----------
        if state == _State.NEAR:
            # Lock if phone is absent long enough OR RSSI is below threshold
            should_lock = (
                miss_count >= miss_limit
                or (result.found and result.rssi is not None
                    and result.rssi < lock_threshold)
            )
            if should_lock:
                logger.info(
                    "Phone out of range (rssi=%s, misses=%d) → locking screen",
                    result.rssi, miss_count,
                )
                if screen_enabled:
                    screen_control.lock_screen()
                state = _State.FAR

        elif state == _State.FAR:
            # Unlock only when the phone reappears with good RSSI
            phone_near = (
                result.found
                and result.rssi is not None
                and result.rssi >= unlock_threshold
            )
            if phone_near:
                logger.info(
                    "Phone back in range (rssi=%d dBm) → waking screen",
                    result.rssi,
                )
                if screen_enabled:
                    screen_control.unlock_screen()
                state = _State.NEAR
                miss_count = 0

        # Sleep before the next cycle (subtract scan time already spent)
        sleep_time = max(0.0, scan_interval - scan_duration)
        time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Interactive setup wizard
# ---------------------------------------------------------------------------

def setup_wizard() -> None:
    """Guide the user through creating / updating config.json."""
    print("\n=== Bluetooth Proximity Screen Control – Setup ===\n")
    print("This wizard will help you configure the daemon.\n")

    cfg = cfg_module.load()

    def _prompt(key: str, description: str, cast=str) -> None:
        current = cfg[key]
        raw = input(f"  {description} [{current}]: ").strip()
        if raw:
            try:
                cfg[key] = cast(raw)
            except ValueError:
                print(f"  Invalid value, keeping: {current}")

    _prompt("device_name",
            "BLE local name advertised by the Android app (e.g. ProximityLock)")
    _prompt("device_address",
            "Bluetooth MAC/UUID of your phone (leave blank to match by name only)")
    _prompt("rssi_lock_threshold",
            "RSSI lock threshold in dBm (-70 ≈ 5 m)", int)
    _prompt("rssi_hysteresis",
            "Hysteresis margin in dBm to avoid rapid lock/unlock", int)
    _prompt("scan_interval_seconds",
            "Seconds between scans", float)
    _prompt("miss_count_before_lock",
            "Consecutive missed scans before locking", int)

    cfg_module.save(cfg)
    print(f"\nConfiguration saved to {os.path.join(_HERE, 'config.json')}")
    print("Run 'python proximity_monitor.py' to start the daemon.\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lock/unlock the laptop screen based on phone proximity via BLE."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without actually changing the screen state.",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run the interactive setup wizard.",
    )
    args = parser.parse_args()

    if args.setup:
        setup_wizard()
        return

    try:
        run(dry_run=args.dry_run)
    except KeyboardInterrupt:
        logger.info("Stopped by user.")


if __name__ == "__main__":
    main()
