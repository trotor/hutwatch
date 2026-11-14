"""Pre-flight check for macOS Bluetooth privacy (TCC) crashes.

On macOS, CoreBluetooth access is attributed to the app *responsible* for the
process — usually the terminal app. If that app's Info.plist lacks
``NSBluetoothAlwaysUsageDescription``, TCC kills HutWatch with SIGABRT the
moment the BLE scanner starts ("zsh: abort"). That cannot be caught in Python,
so we detect the situation up front and explain it before it happens.

Everything here fails open: on any error or uncertainty, nothing is reported.
Only stdlib is used, and nothing runs on non-macOS platforms.
"""

from __future__ import annotations

import ctypes
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Optional

_USAGE_KEY = "NSBluetoothAlwaysUsageDescription"


def _proc_path(pid: int) -> Optional[str]:
    out = subprocess.run(
        ["ps", "-o", "comm=", "-p", str(pid)],
        capture_output=True, text=True, timeout=2,
    ).stdout.strip()
    return out or None


def _parent_pid(pid: int) -> Optional[int]:
    out = subprocess.run(
        ["ps", "-o", "ppid=", "-p", str(pid)],
        capture_output=True, text=True, timeout=2,
    ).stdout.strip()
    return int(out) if out else None


def _app_bundle(exe_path: str) -> Optional[Path]:
    """Return the outermost .app bundle containing exe_path, if any."""
    marker = ".app/"
    idx = exe_path.find(marker)
    if idx < 0:
        return None
    return Path(exe_path[: idx + len(".app")])


def _responsible_app() -> Optional[Path]:
    """Find the .app bundle TCC attributes this process's Bluetooth access to."""
    me = os.getpid()

    # Primary: ask the kernel which process is responsible for us (what TCC uses).
    # Its answer is authoritative — if we are our own responsible process (ssh,
    # launchd), there is no host app to blame, even if the interpreter itself
    # happens to live in a Python.app bundle.
    try:
        fn = ctypes.CDLL(None).responsibility_get_pid_responsible_for_pid
    except Exception:
        fn = None
    if fn is not None:
        try:
            fn.restype = ctypes.c_int
            fn.argtypes = [ctypes.c_int]
            rpid = fn(me)
            if rpid <= 0 or rpid == me:
                return None
            path = _proc_path(rpid)
            return _app_bundle(path) if path else None
        except Exception:
            return None

    # Fallback (API unavailable): nearest ancestor inside an .app bundle.
    try:
        pid: Optional[int] = _parent_pid(me)
        for _ in range(20):
            if not pid or pid <= 1:
                break
            path = _proc_path(pid)
            if path:
                bundle = _app_bundle(path)
                if bundle:
                    return bundle
            pid = _parent_pid(pid)
    except Exception:
        pass
    return None


def find_bluetooth_blocker() -> Optional[str]:
    """Return the name of the app that will make macOS abort BLE access, or None.

    Only reports a positively identified, non-Apple app bundle whose
    Info.plist has no Bluetooth usage description.
    """
    if sys.platform != "darwin":
        return None
    try:
        bundle = _responsible_app()
        if bundle is None:
            return None
        with open(bundle / "Contents" / "Info.plist", "rb") as f:
            info = plistlib.load(f)
        if _USAGE_KEY in info:
            return None
        # Apple's own apps (Terminal.app) are not held to the plist requirement.
        if str(info.get("CFBundleIdentifier", "")).startswith("com.apple."):
            return None
        return str(info.get("CFBundleName") or bundle.stem)
    except Exception:
        return None
