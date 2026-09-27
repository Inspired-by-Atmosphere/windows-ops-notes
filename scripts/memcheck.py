#!/usr/bin/env python3
"""memcheck.py - full memory picture of a Windows box in one pass.

Sections: physical memory overview / commit charge / memory type breakdown /
top-25 processes / per-application rollup / pagefile reality / GPU memory /
pressure verdict.

Usage:
    python memcheck.py > mem.txt 2>&1      # long output: write to a file first
    python memcheck.py --quiet             # sections 1 and 7 only

Dependencies: powershell.exe, nvidia-smi (the GPU section is skipped if absent).
Note: some counters need an elevated shell; without it they print nothing.

Reading guide:
  * Commit charge near the commit limit is what usually freezes a machine, not
    "free" RAM. Watch the commit percentage, not the free-bytes number.
  * A process holding many GB of private commit with ~0% GPU utilisation is a
    model/daemon that is resident but idle (keep-alive style), not a leak.
  * Pagefile peak vs current tells you whether the pagefile can be shrunk.
"""

import argparse
import subprocess
import sys


def ps(cmd, timeout=180):
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", cmd],
        capture_output=True, text=True, errors="replace", timeout=timeout,
    )
    return (r.stdout or "").strip()


def nv(args, timeout=60):
    try:
        r = subprocess.run(["nvidia-smi"] + args, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
        return (r.stdout or "").strip()
    except FileNotFoundError:
        return ""


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Windows memory inventory.")
    ap.add_argument("--quiet", action="store_true", help="Only overview + pressure verdict.")
    args = ap.parse_args(argv)

    section("1. Physical memory overview")
    print(ps("""
$os = Get-CimInstance Win32_OperatingSystem
$total = $os.TotalVisibleMemorySize * 1KB
$free  = $os.FreePhysicalMemory * 1KB
$used  = $total - $free
$commit = $os.TotalVirtualMemorySize * 1KB
$commitUsed = $os.TotalVirtualMemorySize * 1KB - $os.FreeVirtualMemory * 1KB
'Physical total : {0} GB' -f [math]::Round($total/1GB,1)
'Used           : {0} GB ({1}%)' -f [math]::Round($used/1GB,1), [math]::Round($used/$total*100)
'Available      : {0} GB' -f [math]::Round($free/1GB,1)
'Commit limit   : {0} GB' -f [math]::Round($commit/1GB,1)
'Commit used    : {0} GB ({1}%)' -f [math]::Round($commitUsed/1GB,1), [math]::Round($commitUsed/$commit*100)
"""))

    if not args.quiet:
        section("2. Memory type breakdown (cache/standby/pool; standby is reclaimable)")
        out = ps("""
$c = Get-Counter '\\Memory\\*' -ErrorAction SilentlyContinue
$want = 'Available MBytes','Committed Bytes','Commit Limit','Cache Bytes','Pool Nonpaged Bytes','Pool Paged Bytes','Modified Page List Bytes','Standby Cache Normal Priority Bytes','Standby Cache Core Bytes','Free & Zero Page List Bytes'
foreach ($s in $c.CounterSamples) {
  $name = $s.Path -replace '.*\\\\Memory\\\\',''
  if ($want -contains $name) {
    $v = $s.CookedValue
    if ($name -match 'MBytes') { '{0,-40} {1,10:N1} MB' -f $name, $v }
    else { '{0,-40} {1,10:N1} GB' -f $name, ($v/1GB) }
  }
}
""")
        print(out or "(counter read failed - retry from an elevated shell)")

        section("3. Top 25 processes by working set")
        print(ps("""
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 25 |
  ForEach-Object {
    $ws = $_.WorkingSet64/1MB; $priv = $_.PrivateMemorySize64/1MB
    $totalMB = (Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize
    $pct = if ($ws -gt 0) { [math]::Round($_.WorkingSet64 / ($totalMB * 1KB) * 100, 1) } else { 0 }
    '{0,-30} {1,7}  WS={2,8:N0}MB ({3,5}%)  Priv={4,8:N0}MB  CPU={5,6:N0}s' -f $_.ProcessName, $_.Id, $ws, $pct, $priv, $_.CPU
  }
""") or "(none)")

        section("4. Rollup by application (top 20)")
        print(ps("""
Get-Process | Group-Object ProcessName | ForEach-Object {
  [PSCustomObject]@{
    Name = $_.Name; Count = $_.Count
    WS_MB = [math]::Round(($_.Group | Measure-Object WorkingSet64 -Sum).Sum/1MB, 0)
    Priv_MB = [math]::Round(($_.Group | Measure-Object PrivateMemorySize64 -Sum).Sum/1MB, 0)
  }
} | Sort-Object WS_MB -Descending | Select-Object -First 20 |
  ForEach-Object { '{0,-32} x{1,-3} WS={2,8:N0}MB  Priv={3,8:N0}MB' -f $_.Name, $_.Count, $_.WS_MB, $_.Priv_MB }
""") or "(none)")

        section("5. Pagefile (peak vs current - decides whether it can be shrunk)")
        print(ps("""
Get-CimInstance Win32_PageFileUsage | Select-Object Name, @{n='Alloc_MB';e={$_.AllocatedBaseSize}}, @{n='Peak_MB';e={$_.PeakUsage}}, @{n='Cur_MB';e={$_.CurrentUsage}} | Format-Table -AutoSize | Out-String
"""))

        section("6. GPU memory + processes (used_memory shows N/A on WDDM - normal)")
        print(nv(["--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
                  "--format=csv,noheader"]) or "(nvidia-smi not available)")
        print("--- compute apps ---")
        print(nv(["--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"])
              or "(no GPU compute process)")
        print("To attribute a PID: walk its parent chain (Get-CimInstance Win32_Process) "
              "and check listening ports (netstat -ano).")

    section("7. Pressure verdict")
    print(ps("""
$p = Get-Process
$os = Get-CimInstance Win32_OperatingSystem
$used = ($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) * 1KB
$total = $os.TotalVisibleMemorySize * 1KB
'Process count : {0}' -f $p.Count
if ($used/$total -gt 0.9) { 'WARNING: memory usage >90%' } elseif ($used/$total -gt 0.75) { 'CAUTION: memory usage 75-90%' } else { 'OK: memory usage normal' }
"""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
