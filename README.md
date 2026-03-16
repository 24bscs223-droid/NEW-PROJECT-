# ProximityLock – Bluetooth Screen Auto-Lock

Automatically **lock your laptop screen** when you walk away (≈ 5 m) and
**wake it** the moment you return — no button presses needed.

The system has two parts:

| Part | Platform | What it does |
|------|----------|--------------|
| **Android app** (`android/`) | Phone | Broadcasts a BLE beacon continuously |
| **Python daemon** (`laptop/`) | Laptop (Linux / Windows / macOS) | Scans for the beacon; locks / wakes the screen based on signal strength (RSSI) |

---

## How it works

```
Phone (BLE advertiser)          Laptop (BLE scanner + screen control)
──────────────────────          ──────────────────────────────────────
 ┌─────────────────┐             every 3 s:
 │  ProximityLock  │─── BLE ──►  measure RSSI of "ProximityLock"
 │  beacon (BLE)   │             │
 └─────────────────┘             ├─ RSSI ≥ -62 dBm  →  screen ON  (you are ≤ 5 m away)
                                 └─ RSSI  < -70 dBm  →  screen OFF (you walked away)
```

RSSI ≈ -70 dBm corresponds roughly to **5 metres** in a typical indoor
environment.  Both thresholds are fully configurable.

---

## Quick Start

### 1 – Phone: Install the Android app

1. Open the `android/` folder in **Android Studio**.
2. Connect your phone and click **Run ▶**.
3. Grant the Bluetooth / Location permissions the app requests.
4. Tap **Start Beacon** — you should see *"🟢 Advertising BLE beacon…"*.
5. Leave the app running in the background (it survives reboots via a
   `BOOT_COMPLETED` receiver).

### 2 – Laptop: Run the Python daemon

#### Install dependencies
```bash
cd laptop
pip install -r requirements.txt
```

#### (First time) Run the setup wizard
```bash
python proximity_monitor.py --setup
```
The wizard asks for:
- The **BLE device name** displayed in the Android app (default: `ProximityLock`).
- Optionally, the **Bluetooth MAC address** of your phone for stricter matching.
- The **RSSI lock threshold** (default: `-70 dBm` ≈ 5 m).

Settings are saved to `laptop/config.json`.

#### Start the daemon
```bash
python proximity_monitor.py
```

To test without actually locking the screen:
```bash
python proximity_monitor.py --dry-run
```

#### Example output
```
09:15:02 [INFO] proximity_monitor – === Bluetooth Proximity Screen Control ===
09:15:02 [INFO] proximity_monitor – Target device name : ProximityLock
09:15:02 [INFO] proximity_monitor – Lock RSSI threshold: -70 dBm  (~5 m)
09:15:02 [INFO] proximity_monitor – Wake RSSI threshold: -62 dBm  (hysteresis +8)
09:15:07 [INFO] proximity_monitor – Phone out of range (rssi=-78, misses=3) → locking screen
09:15:19 [INFO] proximity_monitor – Phone back in range (rssi=-61 dBm) → waking screen
```

---

## Configuration reference (`laptop/config.json`)

| Key | Default | Description |
|-----|---------|-------------|
| `device_name` | `"ProximityLock"` | BLE local name to look for (case-insensitive substring) |
| `device_address` | `""` | Bluetooth MAC/UUID of the phone (optional, empty = name only) |
| `rssi_lock_threshold` | `-70` | RSSI below this value → lock screen (dBm) |
| `rssi_hysteresis` | `8` | Screen unlocks only when RSSI > threshold + hysteresis |
| `scan_interval_seconds` | `3` | Seconds between BLE scan cycles |
| `miss_count_before_lock` | `3` | Consecutive missed scans before locking |
| `ble_scan_duration_seconds` | `2.0` | Duration of each BLE scan |
| `enable_screen_control` | `true` | Set `false` for dry-run mode |
| `log_level` | `"INFO"` | Verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

Copy `config.json.example` → `config.json` and edit as needed.

---

## Project structure

```
.
├── android/                      # Android companion app (BLE beacon)
│   ├── app/
│   │   ├── build.gradle
│   │   └── src/main/
│   │       ├── AndroidManifest.xml
│   │       ├── java/com/proximitylock/
│   │       │   ├── MainActivity.java        # UI: start/stop beacon
│   │       │   ├── BluetoothBeaconService.java  # Foreground BLE advertiser
│   │       │   └── BootReceiver.java        # Auto-start on reboot
│   │       └── res/
│   │           ├── layout/activity_main.xml
│   │           └── values/{strings,colors,themes}.xml
│   ├── build.gradle
│   └── settings.gradle
│
├── laptop/                       # Python proximity daemon
│   ├── proximity_monitor.py      # Main entry point / daemon loop
│   ├── bluetooth_scanner.py      # BLE RSSI scanner (bleak)
│   ├── screen_control.py         # Cross-platform screen lock/wake
│   ├── config.py                 # Configuration loader/saver
│   ├── config.json.example       # Sample configuration
│   └── requirements.txt
│
└── tests/
    └── test_proximity_monitor.py # Unit tests (19 tests, no hardware needed)
```

---

## Supported platforms

| Platform | Lock command | Wake command |
|----------|--------------|--------------|
| **Linux** | `loginctl lock-session` → `xdg-screensaver lock` → `xset dpms force off` | `loginctl unlock-session` → `xdg-screensaver reset` → `xset dpms force on` |
| **Windows** | `LockWorkStation()` (Win32 API) | `SendMessage(SC_MONITORPOWER, -1)` |
| **macOS** | `pmset displaysleepnow` | `caffeinate -u -t 1` |

---

## Running the tests

```bash
pip install pytest bleak
python -m pytest tests/ -v
```

All 19 tests run without Bluetooth hardware using mock stubs.