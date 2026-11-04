"""Open each live bot's MT5 terminal if it is not already running (Windows).

    python scripts/start_terminals.py                  cent and btc
    python scripts/start_terminals.py cent btc eurjpy

Run at logon by the trading-bot-terminals task (install_windows_tasks.bat), so
a reboot brings the terminals back before the bots' preflight looks for them.

Each terminal is started the way its install expects:
  - a PORTABLE install (its own Config\\accounts.dat inside the install folder,
    e.g. C:\\MT5-Gold) gets /portable, so it keeps its own saved account;
  - a standard install (C:\\Program Files\\...) is started plainly -- /portable
    there would point it at an empty profile with no saved login.

A terminal whose terminal64.exe is already running is left alone.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CONFIGS = {
    "cent": "config/config-cent.toml",
    "btc": "config/config-btc.toml",
    "eurjpy": "config/config-eurjpy.toml",
}


def is_portable_install(exe: Path) -> bool:
    if (exe.parent / "Config" / "accounts.dat").exists():
        return True
    return "program files" not in str(exe).lower()


def running_exe_paths() -> set[str] | None:
    """Lower-cased full paths of running processes; None if unavailable."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32")
        arr = (wintypes.DWORD * 4096)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)):
            return None
        out = set()
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        for pid in arr[: needed.value // ctypes.sizeof(wintypes.DWORD)]:
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                continue
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    out.add(buf.value.lower())
            finally:
                kernel32.CloseHandle(h)
        return out
    except Exception:  # noqa: BLE001
        return None


def main(argv: list[str]) -> int:
    from trading_bot.config import load_config

    tags = argv or ["cent", "btc"]
    running = running_exe_paths()
    rc = 0
    for tag in tags:
        cfg = load_config(ROOT / CONFIGS[tag])
        path = cfg.live.terminal_path
        if not path:
            print(f"{tag}: no [live] terminal_path set -- skipped")
            continue
        exe = Path(path)
        if not exe.exists():
            print(f"{tag}: {exe} not found")
            rc = 1
            continue
        if running is not None and str(exe).lower() in running:
            print(f"{tag}: already running  {exe}")
            continue
        args = [str(exe)] + (["/portable"] if is_portable_install(exe) else [])
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED | NEW_GROUP
        subprocess.Popen(args, cwd=str(exe.parent), creationflags=flags, close_fds=True)
        print(f"{tag}: started  {' '.join(args)}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
