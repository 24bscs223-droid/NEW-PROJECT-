"""
Configuration for the Bluetooth Proximity Screen Control daemon.

Edit the values below (or supply them via config.json in the same directory)
to match your environment.
"""

import json
import os

# ---------------------------------------------------------------------------
# Default configuration values
# ---------------------------------------------------------------------------

DEFAULTS = {
    # BLE local name advertised by the Android companion app.
    # Change this to match the name set in the Android app.
    "device_name": "ProximityLock",

    # Optional: Bluetooth MAC address of the phone (Linux only).
    # Set to "" to match by name only.
    "device_address": "",

    # RSSI threshold in dBm.
    # When the phone's RSSI drops BELOW this value, the screen is locked.
    # Typical values:
    #   -60 dBm  ≈ 2–3 m
    #   -70 dBm  ≈ 5 m   (default)
    #   -80 dBm  ≈ 8–10 m
    "rssi_lock_threshold": -70,

    # Hysteresis margin (dBm). The screen is unlocked only when RSSI rises
    # above (rssi_lock_threshold + rssi_hysteresis), preventing rapid
    # lock/unlock oscillation near the boundary.
    "rssi_hysteresis": 8,

    # Seconds between each BLE scan cycle.
    "scan_interval_seconds": 3,

    # Consecutive missed scans before the screen is locked.
    # Avoids locking due to a single missed advertisement packet.
    "miss_count_before_lock": 3,

    # How long (seconds) each BLE scan runs before results are evaluated.
    "ble_scan_duration_seconds": 2.0,

    # Whether to actually lock/unlock the screen (set False for dry-run).
    "enable_screen_control": True,

    # Log level: DEBUG, INFO, WARNING, ERROR
    "log_level": "INFO",
}

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")


def load() -> dict:
    """Return the merged configuration (file overrides defaults)."""
    cfg = dict(DEFAULTS)
    if os.path.isfile(_CONFIG_FILE):
        with open(_CONFIG_FILE, "r", encoding="utf-8") as fh:
            overrides = json.load(fh)
        cfg.update(overrides)
    return cfg


def save(cfg: dict) -> None:
    """Persist *cfg* to config.json (excludes keys not in DEFAULTS)."""
    data = {k: cfg[k] for k in DEFAULTS if k in cfg}
    with open(_CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
