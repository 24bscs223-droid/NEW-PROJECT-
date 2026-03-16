"""
Cross-platform screen lock / unlock helpers.

Supported platforms
-------------------
* Linux   – uses loginctl / xdg-screensaver / xset DPMS
* Windows – uses ctypes (LockWorkStation) and SendMessage for display power
* macOS   – uses pmset and caffeinate
"""

import logging
import platform
import subprocess
import sys

logger = logging.getLogger(__name__)

_SYSTEM = platform.system()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lock_screen() -> bool:
    """Lock / blank the screen.  Returns True on success."""
    logger.info("Locking screen …")
    try:
        if _SYSTEM == "Linux":
            return _linux_lock()
        elif _SYSTEM == "Windows":
            return _windows_lock()
        elif _SYSTEM == "Darwin":
            return _macos_lock()
        else:
            logger.warning("Unsupported platform: %s", _SYSTEM)
            return False
    except Exception as exc:
        logger.error("lock_screen failed: %s", exc)
        return False


def unlock_screen() -> bool:
    """Wake / un-blank the screen.
    Note: On most desktop systems the screen *wakes* automatically when
    the user interacts; this call turns the display power back on so the
    lock-screen prompt is immediately visible.
    Returns True on success.
    """
    logger.info("Waking screen …")
    try:
        if _SYSTEM == "Linux":
            return _linux_wake()
        elif _SYSTEM == "Windows":
            return _windows_wake()
        elif _SYSTEM == "Darwin":
            return _macos_wake()
        else:
            logger.warning("Unsupported platform: %s", _SYSTEM)
            return False
    except Exception as exc:
        logger.error("unlock_screen failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Linux helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> bool:
    """Run *cmd*, return True if exit-code is 0."""
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        logger.debug("Command %s failed (rc=%d): %s",
                     cmd, result.returncode, result.stderr.decode(errors="replace"))
    return result.returncode == 0


def _linux_lock() -> bool:
    # Try loginctl first (systemd), then xdg-screensaver, then xset DPMS.
    for cmd in (
        ["loginctl", "lock-session"],
        ["xdg-screensaver", "lock"],
        ["xset", "dpms", "force", "off"],
    ):
        if _run(cmd):
            return True
    logger.warning("All Linux lock commands failed.")
    return False


def _linux_wake() -> bool:
    for cmd in (
        ["loginctl", "unlock-session"],
        ["xdg-screensaver", "reset"],
        ["xset", "dpms", "force", "on"],
    ):
        if _run(cmd):
            return True
    logger.warning("All Linux wake commands failed.")
    return False


# ---------------------------------------------------------------------------
# Windows helpers
# ---------------------------------------------------------------------------

def _windows_lock() -> bool:
    import ctypes
    ret = ctypes.windll.user32.LockWorkStation()
    return bool(ret)


def _windows_wake() -> bool:
    # Send WM_SYSCOMMAND / SC_MONITORPOWER -1 (on) to the desktop window.
    import ctypes
    SC_MONITORPOWER = 0xF170
    HWND_BROADCAST = 0xFFFF
    WM_SYSCOMMAND = 0x0112
    ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, -1)
    return True


# ---------------------------------------------------------------------------
# macOS helpers
# ---------------------------------------------------------------------------

def _macos_lock() -> bool:
    # macOS 10.13+: use pmset or screensaver shortcut.
    for cmd in (
        ["pmset", "displaysleepnow"],
        ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession",
         "-suspend"],
    ):
        if _run(cmd):
            return True
    return False


def _macos_wake() -> bool:
    # Wake the display by momentarily inhibiting sleep via caffeinate.
    return _run(["caffeinate", "-u", "-t", "1"])
