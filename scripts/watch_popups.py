#!/usr/bin/env python3
"""watch_popups.py - same probe as catch_popup.py, tuned for boot-time storms.

Run it on the target machine right after login (60-90s). Every newly appeared
console-class process is printed with its parent chain and command line, so you
can see *who* is re-spawning the windows instead of guessing which startup
entry is guilty.

Usage:
    python watch_popups.py [--seconds 60] [--interval 5]

Tip: if your shell exports PYTHONPATH/VIRTUAL_ENV for another app, clear it
first (`env -u PYTHONPATH python watch_popups.py`) so the sampler itself does
not look like a suspect.
"""

import argparse
import json
import subprocess
import sys
import time

DEFAULT_MATCH = "conhost|cmd|python|node|wt|WindowsTerminal|OpenConsole"


def snapshot(match):
    cmd = (
        "Get-CimInstance Win32_Process | Where-Object {$_.Name -match '%s'} | "
        "Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine | "
        "ConvertTo-Json -Compress" % match
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True, text=True, timeout=60, errors="replace",
    )
    out = {}
    try:
        data = json.loads(r.stdout or "[]")
        if isinstance(data, dict):
            data = [data]
        for d in data:
            out[int(d["ProcessId"])] = d
    except Exception as exc:  # noqa: BLE001
        print("PowerShell parse error: %s" % exc, file=sys.stderr)
    return out


def chain(pid, table):
    seen, acc = set(), []
    while pid and pid not in seen:
        seen.add(pid)
        row = table.get(pid)
        if not row:
            break
        acc.append("%s(%d)" % (row.get("Name"), pid))
        pid = int(row.get("ParentProcessId") or 0)
    return " <- ".join(acc)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detect console-window storms at boot.")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--interval", type=int, default=5)
    ap.add_argument("--match", default=DEFAULT_MATCH)
    args = ap.parse_args(argv)

    before = snapshot(args.match)
    print("[%s] baseline process count %d" % (time.strftime("%H:%M:%S"), len(before)), flush=True)
    for _ in range(max(1, args.seconds // args.interval)):
        time.sleep(args.interval)
        after = snapshot(args.match)
        for pid in sorted(set(after) - set(before)):
            row = after[pid]
            print(
                "[%s] NEW %s(%d) parents=%s"
                % (time.strftime("%H:%M:%S"), row.get("Name"), pid,
                   chain(int(row.get("ParentProcessId") or 0), after)),
                flush=True,
            )
            print("    CMD: %s" % (row.get("CommandLine") or "")[:200], flush=True)
        before = after
    print("[%s] watch finished" % time.strftime("%H:%M:%S"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
