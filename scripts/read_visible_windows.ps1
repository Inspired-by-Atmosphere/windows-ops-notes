<#
.SYNOPSIS
    List visible top-level windows with their owning process.

.DESCRIPTION
    Enumerates windows that are actually visible and have a title, and prints
    PID / process name / window title / parent process. This is the fastest way
    to answer "which program is popping this window?" - a window storm shows up
    as several console-class processes created seconds apart.

.NOTES
    Read-only. Does not touch any window. Works on Windows PowerShell 5.1 and
    PowerShell 7+.

.PARAMETER Filter
    Regex applied to the process name (default: every process with a window).

.PARAMETER ConsoleOnly
    Only show console hosts (conhost.exe, WindowsTerminal.exe, OpenConsole.exe)
    and their parents - use this for popup-storm triage.

.EXAMPLE
    powershell -NoProfile -File read_visible_windows.ps1
.EXAMPLE
    powershell -NoProfile -File read_visible_windows.ps1 -ConsoleOnly
#>
[CmdletBinding()]
param(
    [string]$Filter = '',
    [switch]$ConsoleOnly
)

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WinEnum {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
}
"@

$procCache = @{}
$rows = New-Object System.Collections.Generic.List[object]

$callback = {
    param($hWnd, $lParam)
    if (-not [WinEnum]::IsWindowVisible($hWnd)) { return $true }
    $len = [WinEnum]::GetWindowTextLength($hWnd)
    if ($len -le 0) { return $true }
    $sb = New-Object System.Text.StringBuilder ($len + 2)
    [void][WinEnum]::GetWindowText($hWnd, $sb, $sb.Capacity)
    $title = $sb.ToString()
    $windowPid = 0
    [void][WinEnum]::GetWindowThreadProcessId($hWnd, [ref]$windowPid)
    if ($windowPid -le 0) { return $true }
    $proc = Get-Process -Id $windowPid -ErrorAction SilentlyContinue
    if (-not $proc) { return $true }
    $rows.Add([pscustomobject]@{
        PID     = $windowPid
        Name    = $proc.ProcessName
        Title   = $title
        Started = $proc.StartTime
    })
    return $true
}

[void][WinEnum]::EnumWindows($callback, [IntPtr]::Zero)

$console = @('conhost', 'WindowsTerminal', 'OpenConsole', 'cmd', 'powershell', 'pwsh')
$result = $rows | Sort-Object Started
if ($ConsoleOnly) {
    $result = $result | Where-Object { $console -contains $_.Name }
}
if ($Filter) {
    $result = $result | Where-Object { $_.Name -match $Filter }
}

$result | Format-Table -AutoSize PID, Name, Started, Title | Out-String -Width 240
"total visible windows: {0}" -f @($result).Count
