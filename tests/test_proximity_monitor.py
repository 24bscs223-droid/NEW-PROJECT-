"""
Unit tests for the Bluetooth Proximity Screen Control laptop daemon.

These tests validate the core logic (RSSI threshold evaluation, state
machine, config loading, etc.) without requiring real Bluetooth hardware
or a real screen.  All hardware calls are mocked.
"""

import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Make the laptop package importable without installing it
# ---------------------------------------------------------------------------
_LAPTOP_DIR = os.path.join(os.path.dirname(__file__), "..", "laptop")
sys.path.insert(0, os.path.abspath(_LAPTOP_DIR))


# ---------------------------------------------------------------------------
# Stub bleak so tests run without the real library installed
# ---------------------------------------------------------------------------

def _make_bleak_stub():
    """Return a minimal bleak stub that satisfies the imports in bluetooth_scanner."""
    bleak = types.ModuleType("bleak")
    bleak_backends = types.ModuleType("bleak.backends")
    bleak_backends_device = types.ModuleType("bleak.backends.device")
    bleak_backends_scanner = types.ModuleType("bleak.backends.scanner")

    class _BLEDevice:
        def __init__(self, address, name):
            self.address = address
            self.name    = name

    class _AdvertisementData:
        def __init__(self, local_name, rssi):
            self.local_name = local_name
            self.rssi       = rssi

    class _BleakScanner:
        """Minimal async context manager stub."""
        def __init__(self, detection_callback=None, **_kw):
            self._cb = detection_callback

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

    bleak_backends_device.BLEDevice = _BLEDevice
    bleak_backends_scanner.AdvertisementData = _AdvertisementData
    bleak.BleakScanner = _BleakScanner
    bleak.backends = bleak_backends
    bleak_backends.device = bleak_backends_device
    bleak_backends.scanner = bleak_backends_scanner

    sys.modules.setdefault("bleak", bleak)
    sys.modules.setdefault("bleak.backends", bleak_backends)
    sys.modules.setdefault("bleak.backends.device", bleak_backends_device)
    sys.modules.setdefault("bleak.backends.scanner", bleak_backends_scanner)


_make_bleak_stub()

import config as cfg_module                 # noqa: E402  (after path setup)
import screen_control                        # noqa: E402
from bluetooth_scanner import ScanResult    # noqa: E402


# ===========================================================================
# Config tests
# ===========================================================================

class TestConfig(unittest.TestCase):

    def test_defaults_are_complete(self):
        """All expected keys are present in DEFAULTS."""
        required = {
            "device_name", "device_address",
            "rssi_lock_threshold", "rssi_hysteresis",
            "scan_interval_seconds", "miss_count_before_lock",
            "ble_scan_duration_seconds", "enable_screen_control",
            "log_level",
        }
        self.assertTrue(required.issubset(cfg_module.DEFAULTS.keys()))

    def test_load_returns_defaults_when_no_file(self):
        """load() returns defaults if config.json is absent."""
        with patch.object(cfg_module, "_CONFIG_FILE", "/nonexistent/config.json"):
            cfg = cfg_module.load()
        self.assertEqual(cfg["device_name"], cfg_module.DEFAULTS["device_name"])
        self.assertEqual(cfg["rssi_lock_threshold"],
                         cfg_module.DEFAULTS["rssi_lock_threshold"])

    def test_load_overrides_from_file(self):
        """load() correctly overrides defaults with values from config.json."""
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False) as tmp:
            json.dump({"device_name": "MyPhone", "rssi_lock_threshold": -80}, tmp)
            tmp_path = tmp.name

        try:
            with patch.object(cfg_module, "_CONFIG_FILE", tmp_path):
                cfg = cfg_module.load()
            self.assertEqual(cfg["device_name"], "MyPhone")
            self.assertEqual(cfg["rssi_lock_threshold"], -80)
            # Non-overridden keys keep defaults
            self.assertEqual(cfg["rssi_hysteresis"],
                             cfg_module.DEFAULTS["rssi_hysteresis"])
        finally:
            os.unlink(tmp_path)

    def test_save_and_reload(self):
        """save() writes a valid JSON file that load() can read back."""
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        os.unlink(tmp_path)   # let save() create the file fresh

        cfg_in = dict(cfg_module.DEFAULTS)
        cfg_in["device_name"] = "TestDevice"
        cfg_in["rssi_lock_threshold"] = -75

        with patch.object(cfg_module, "_CONFIG_FILE", tmp_path):
            cfg_module.save(cfg_in)
            cfg_out = cfg_module.load()

        os.unlink(tmp_path)

        self.assertEqual(cfg_out["device_name"], "TestDevice")
        self.assertEqual(cfg_out["rssi_lock_threshold"], -75)


# ===========================================================================
# ScanResult tests
# ===========================================================================

class TestScanResult(unittest.TestCase):

    def test_found_true(self):
        sr = ScanResult(found=True, rssi=-65, address="AA:BB:CC:DD:EE:FF",
                        name="ProximityLock")
        self.assertTrue(sr.found)
        self.assertEqual(sr.rssi, -65)
        self.assertEqual(sr.name, "ProximityLock")

    def test_found_false(self):
        sr = ScanResult(found=False)
        self.assertFalse(sr.found)
        self.assertIsNone(sr.rssi)
        self.assertEqual(sr.address, "")

    def test_repr_contains_key_info(self):
        sr = ScanResult(found=True, rssi=-70, address="AA:BB:CC:DD:EE:FF",
                        name="MyPhone")
        rep = repr(sr)
        self.assertIn("found=True", rep)
        self.assertIn("-70", rep)


# ===========================================================================
# State machine / locking logic tests
# ===========================================================================

class TestProximityStateMachine(unittest.TestCase):
    """
    Tests for the NEAR/FAR state machine logic in proximity_monitor.run().

    We import the module and exercise its decision logic in isolation
    by patching scan_once, lock_screen, unlock_screen, and time.sleep.
    """

    def _run_n_cycles(self, scan_results, cfg_overrides=None):
        """
        Drive the proximity_monitor loop for len(scan_results) cycles.
        Returns lists of 'lock' and 'unlock' call counts.
        """
        import proximity_monitor as pm

        cfg = dict(cfg_module.DEFAULTS)
        cfg.update({
            "device_name":          "ProximityLock",
            "device_address":       "",
            "rssi_lock_threshold":  -70,
            "rssi_hysteresis":      8,
            "scan_interval_seconds": 3,
            "miss_count_before_lock": 3,
            "ble_scan_duration_seconds": 2.0,
            "enable_screen_control": True,
            "log_level":            "WARNING",
        })
        if cfg_overrides:
            cfg.update(cfg_overrides)

        scan_iter = iter(scan_results)
        lock_calls   = []
        unlock_calls = []

        def fake_scan(*_a, **_kw):
            return next(scan_iter)

        def fake_lock():
            lock_calls.append(1)
            return True

        def fake_unlock():
            unlock_calls.append(1)
            return True

        with patch.object(cfg_module, "load", return_value=cfg), \
             patch("proximity_monitor.scan_once", side_effect=fake_scan), \
             patch("proximity_monitor.screen_control.lock_screen", side_effect=fake_lock), \
             patch("proximity_monitor.screen_control.unlock_screen", side_effect=fake_unlock), \
             patch("time.sleep"):
            # run() is infinite; wrap in StopIteration to exit after N scans
            try:
                pm.run(dry_run=False)
            except StopIteration:
                pass

        return lock_calls, unlock_calls

    # ── Lock tests ──────────────────────────────────────────────────────────

    def test_lock_when_rssi_below_threshold(self):
        """Screen locks when RSSI drops below the threshold."""
        results = [
            ScanResult(found=True, rssi=-80),   # below -70 → lock
        ]
        locks, unlocks = self._run_n_cycles(results)
        self.assertEqual(len(locks), 1)
        self.assertEqual(len(unlocks), 0)

    def test_lock_after_consecutive_misses(self):
        """Screen locks after miss_count_before_lock consecutive missed scans."""
        results = [
            ScanResult(found=False),  # miss 1
            ScanResult(found=False),  # miss 2
            ScanResult(found=False),  # miss 3 → lock (miss_count_before_lock=3)
        ]
        locks, unlocks = self._run_n_cycles(results)
        self.assertEqual(len(locks), 1)

    def test_no_lock_for_single_miss(self):
        """A single missed scan does NOT lock (miss_count_before_lock=3)."""
        results = [
            ScanResult(found=False),          # miss 1
            ScanResult(found=False),          # miss 2
            ScanResult(found=True, rssi=-60), # found again before miss 3 → no lock
        ]
        locks, unlocks = self._run_n_cycles(results)
        self.assertEqual(len(locks), 0)

    def test_no_lock_when_rssi_above_threshold(self):
        """Screen stays on while RSSI is above the lock threshold."""
        results = [
            ScanResult(found=True, rssi=-60),
            ScanResult(found=True, rssi=-55),
            ScanResult(found=True, rssi=-50),
        ]
        locks, unlocks = self._run_n_cycles(results)
        self.assertEqual(len(locks), 0)

    # ── Unlock tests ────────────────────────────────────────────────────────

    def test_unlock_when_phone_returns(self):
        """Screen wakes when phone comes back with RSSI above unlock threshold."""
        # lock_threshold=-70, hysteresis=8 → unlock_threshold=-62
        results = [
            ScanResult(found=True, rssi=-80),   # → lock
            ScanResult(found=True, rssi=-60),   # above -62 → unlock
        ]
        locks, unlocks = self._run_n_cycles(results)
        self.assertEqual(len(locks), 1)
        self.assertEqual(len(unlocks), 1)

    def test_no_unlock_if_rssi_still_weak(self):
        """Screen stays locked if phone is found but RSSI is still too weak."""
        # unlock threshold = -70 + 8 = -62
        results = [
            ScanResult(found=True, rssi=-80),   # → lock
            ScanResult(found=True, rssi=-65),   # -65 < -62 → still locked
        ]
        locks, unlocks = self._run_n_cycles(results)
        self.assertEqual(len(locks), 1)
        self.assertEqual(len(unlocks), 0)

    # ── Dry-run ─────────────────────────────────────────────────────────────

    def test_dry_run_does_not_call_screen_control(self):
        """dry_run=True skips actual screen lock/unlock calls."""
        import proximity_monitor as pm

        cfg = dict(cfg_module.DEFAULTS)
        cfg.update({
            "rssi_lock_threshold": -70,
            "rssi_hysteresis": 8,
            "miss_count_before_lock": 3,
            "ble_scan_duration_seconds": 2.0,
            "scan_interval_seconds": 3,
            "enable_screen_control": True,
            "log_level": "WARNING",
        })

        scan_results = iter([ScanResult(found=True, rssi=-80)])

        with patch.object(cfg_module, "load", return_value=cfg), \
             patch("proximity_monitor.scan_once",
                   side_effect=lambda *a, **kw: next(scan_results)), \
             patch("proximity_monitor.screen_control.lock_screen") as mock_lock, \
             patch("proximity_monitor.screen_control.unlock_screen") as mock_unlock, \
             patch("time.sleep"):
            try:
                pm.run(dry_run=True)
            except StopIteration:
                pass

        mock_lock.assert_not_called()
        mock_unlock.assert_not_called()


# ===========================================================================
# Screen control tests (platform helpers are mocked)
# ===========================================================================

class TestScreenControl(unittest.TestCase):

    @patch("screen_control._SYSTEM", "Linux")
    @patch("screen_control._run", return_value=True)
    def test_linux_lock(self, mock_run):
        result = screen_control.lock_screen()
        self.assertTrue(result)
        mock_run.assert_called()

    @patch("screen_control._SYSTEM", "Linux")
    @patch("screen_control._run", return_value=True)
    def test_linux_wake(self, mock_run):
        result = screen_control.unlock_screen()
        self.assertTrue(result)

    @patch("screen_control._SYSTEM", "Windows")
    def test_windows_lock(self):
        mock_windll = MagicMock()
        mock_windll.user32.LockWorkStation.return_value = 1
        with patch.dict("sys.modules", {"ctypes": MagicMock(windll=mock_windll)}):
            import ctypes
            ctypes.windll = mock_windll
            with patch("screen_control._windows_lock", return_value=True) as m:
                result = screen_control.lock_screen()
                m.assert_called_once()

    @patch("screen_control._SYSTEM", "Darwin")
    @patch("screen_control._run", return_value=True)
    def test_macos_lock(self, mock_run):
        result = screen_control.lock_screen()
        self.assertTrue(result)

    @patch("screen_control._SYSTEM", "FreeBSD")
    def test_unsupported_platform_returns_false(self):
        result = screen_control.lock_screen()
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
