"""
Bluetooth Low Energy scanner utilities.

Uses the *bleak* library to perform BLE scans and return the RSSI of a
target device identified by its advertised local name and/or MAC address.
"""

import asyncio
import logging
from typing import Optional

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

logger = logging.getLogger(__name__)


class ScanResult:
    """Holds the outcome of a single BLE scan cycle."""

    def __init__(self, found: bool, rssi: Optional[int] = None,
                 address: str = "", name: str = ""):
        self.found = found          # Was the target device seen?
        self.rssi = rssi            # RSSI in dBm (None if not found)
        self.address = address      # BLE MAC / UUID of the device
        self.name = name            # Advertised local name

    def __repr__(self) -> str:
        return (f"ScanResult(found={self.found}, rssi={self.rssi}, "
                f"address={self.address!r}, name={self.name!r})")


async def _async_scan(
    device_name: str,
    device_address: str,
    scan_duration: float,
) -> ScanResult:
    """Perform one BLE scan cycle and return a :class:`ScanResult`."""

    best_rssi: Optional[int] = None
    best_device: Optional[BLEDevice] = None
    best_adv: Optional[AdvertisementData] = None

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        nonlocal best_rssi, best_device, best_adv

        name_match = (
            device_name
            and adv.local_name
            and device_name.lower() in adv.local_name.lower()
        )
        addr_match = (
            device_address
            and device.address.lower() == device_address.lower()
        )

        if name_match or addr_match:
            rssi = adv.rssi
            if rssi is not None and (best_rssi is None or rssi > best_rssi):
                best_rssi = rssi
                best_device = device
                best_adv = adv
                logger.debug("Seen target: name=%r addr=%s rssi=%d dBm",
                             adv.local_name, device.address, rssi)

    async with BleakScanner(detection_callback=callback):
        await asyncio.sleep(scan_duration)

    if best_device is not None:
        return ScanResult(
            found=True,
            rssi=best_rssi,
            address=best_device.address,
            name=best_adv.local_name or best_device.name or "",
        )
    return ScanResult(found=False)


def scan_once(
    device_name: str,
    device_address: str = "",
    scan_duration: float = 2.0,
) -> ScanResult:
    """Synchronous wrapper around :func:`_async_scan`.

    Parameters
    ----------
    device_name:
        The BLE local name advertised by the Android companion app
        (e.g. ``"ProximityLock"``).  Case-insensitive substring match.
    device_address:
        Optional Bluetooth MAC / UUID for more precise matching.
        Pass an empty string to match by name only.
    scan_duration:
        How many seconds to listen before returning results.
    """
    return asyncio.run(_async_scan(device_name, device_address, scan_duration))
