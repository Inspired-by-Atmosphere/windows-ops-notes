#!/usr/bin/env python3
"""find_file_lock.py - find which Windows process holds a file open.

Uses the Restart Manager API (rstrtmgr.dll) to get an exact answer instead of
guessing from process names.

Usage:
    python find_file_lock.py "<windows path>"
    python find_file_lock.py "<windows path>" --json

Output: one line per holding process: PID | app name | application type.

Why Restart Manager: enumerate-handle tools (handle.exe etc.) need admin or a
driver; RmGetList answers the same question for the current user with no extra
dependency.

Pitfalls (learned the hard way):
  * RmGetList signature: arg2 = pnProcInfoNeeded (out), arg3 = pnProcInfo
    (in = buffer capacity, out = count). Call it once with a NULL buffer to get
    the needed count, then again with that capacity. Swapping the two gives an
    empty result or a bogus 0. Return code 234 (ERROR_MORE_DATA) is a normal
    signal, not a failure.
  * strAppName is a WCHAR[]; print it through an explicit utf-8 encode/decode
    or a non-ASCII app name can raise a surrogate encoding error.

Safety: after you get a PID, check whether the process has a visible window
(MainWindowHandle != 0) before killing anything. A headless helper may hold a
stale handle to a file the user is no longer viewing (safe to stop); a process
with a visible window is probably the viewer itself - ask the user to close it.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import sys

if sys.platform != "win32":
    raise SystemExit("This tool only runs on Windows (Restart Manager API).")


class RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", wt.DWORD),
        ("strAppName", wt.WCHAR * 256),
        ("strServiceShortName", wt.WCHAR * 64),
        ("ApplicationType", wt.DWORD),
        ("AppStatus", wt.DWORD),
        ("TSSessionId", wt.DWORD),
        ("bRestartable", wt.BOOL),
    ]


ERROR_MORE_DATA = 234


def find_locks(path):
    """Return [(pid, app_name, application_type), ...] for the given path."""
    rm = ctypes.WinDLL("rstrtmgr.dll")
    key = (wt.WCHAR * 32)()
    handle = wt.DWORD()
    rc = rm.RmStartSession(ctypes.byref(handle), 0, ctypes.byref(key))
    if rc != 0:
        raise RuntimeError("RmStartSession failed rc=%d" % rc)
    try:
        files = (ctypes.c_wchar_p * 1)(path)
        rm.RmRegisterResources(
            handle, 1, ctypes.cast(files, ctypes.POINTER(ctypes.c_void_p)), 0, None, 0
        )
        # First call: NULL buffer, only asks how many entries are needed.
        needed = wt.DWORD(0)
        count = wt.DWORD(0)
        reason = wt.DWORD(0)
        rm.RmGetList(handle, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reason))
        n = needed.value
        if n <= 0:
            return []
        # Second call: pass the needed count as the buffer capacity.
        buf = (RM_PROCESS_INFO * n)()
        count = wt.DWORD(n)
        rm.RmGetList(
            handle,
            ctypes.byref(needed),
            ctypes.byref(count),
            ctypes.cast(buf, ctypes.POINTER(RM_PROCESS_INFO)),
            ctypes.byref(reason),
        )
        out = []
        for i in range(count.value):
            p = buf[i]
            name = p.strAppName.encode("utf-8", "replace").decode("utf-8")
            out.append((int(p.Process), name, int(p.ApplicationType)))
        return out
    finally:
        rm.RmEndSession(handle)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Find Windows processes holding a file open (Restart Manager API).",
        epilog="Example: python find_file_lock.py \"<drive>:\\path\\to\\report.pdf\"",
    )
    ap.add_argument("path", help="Windows path to the locked file (native form, backslashes).")
    ap.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = ap.parse_args(argv)

    locks = find_locks(args.path)
    if args.json:
        print(json.dumps([{"pid": p, "app": n, "type": t} for p, n, t in locks]))
        return 0 if locks else 1
    if not locks:
        print("No process holds a handle on this file (or the lock is already released).")
        return 1
    for pid, name, typ in locks:
        print("PID=%d | %s | applicationType=%d" % (pid, name, typ))
    print("\nNext step: check for a visible window before stopping anything:")
    print("  Get-Process -Id <pid> | Select-Object Id,ProcessName,MainWindowHandle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
