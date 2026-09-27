#!/usr/bin/env python3
"""catch_popup.py - catch the process that is popping up console windows.

Samples the process table every 5 seconds for N seconds (default 30) and prints
every *newly appeared* console-class process together with its parent chain and
command line. A window that keeps coming back shows up as repeated new entries;
a window that just stays open appears once.

Usage:
    python catch_popup.py [seconds] [--match "conhost|cmd|python|node|wt"]

Requires: Windows + PowerShell (Get-CimInstance).
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
    except Exception as exc:  # noqa: BLE001 - a bad sample must not kill the watch
        print("PowerShell parse error: %s" % exc, file=sys.stderr)
    return out


def parent_chain(pid, table):
    chain, seen = [], set()
    while pid and pid not in seen:
        seen.add(pid)
        row = table.get(pid)
        if not row:
            break
        chain.append("%s(%d)" % (row.get("Name"), pid))
        pid = int(row.get("ParentProcessId") or 0)
    return " <- ".join(chain)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Watch for newly spawned console processes.")
    ap.add_argument("seconds", nargs="?", type=int, default=30, help="Total watch time (default 30).")
    ap.add_argument("--match", default=DEFAULT_MATCH, help="Process name regex for PowerShell.")
    ap.add_argument("--interval", type=int, default=5, help="Sampling interval in seconds.")
    args = ap.parse_args(argv)

    before = snapshot(args.match)
    print("[%s] baseline process count: %d" % (time.strftime("%H:%M:%S"), len(before)), flush=True)
    rounds = max(1, args.seconds // args.interval)
    for _ in range(rounds):
        time.sleep(args.interval)
        after = snapshot(args.match)
        for pid in sorted(set(after) - set(before)):
            row = after[pid]
            print(
                "[%s] NEW %s(%d) parents=%s"
                % (time.strftime("%H:%M:%S"), row.get("Name"), pid,
                   parent_chain(int(row.get("ParentProcessId") or 0), after)),
                flush=True,
            )
            print("    CMD: %s" % (row.get("CommandLine") or "")[:200], flush=True)
        before = after
    print("[%s] watch finished" % time.strftime("%H:%M:%S"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
