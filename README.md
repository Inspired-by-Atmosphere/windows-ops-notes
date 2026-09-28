# windows-ops-notes

Field notes and zero-dependency scripts from real Windows / OpenWrt / campus-network troubleshooting.

## What this is

Problem write-ups, each self-contained and in the same shape: **symptom / trigger →
root cause → commands → how to verify → pitfalls**. No blog filler and no dead
ends — every note finishes with the check that proves the fix actually worked, and
the section that lists the traps that cost the most time.

```text
notes/windows-filesystem/file-lock-hunting.md
  When to Use · 触发场景 · 常见持有者（实测） · 排查步骤
  · Restart Manager API 坑位 · 验证 · 相关
```

The notes themselves are written in Chinese (each one opens with an English
`When to Use` section); the scripts and their `--help` are English.

## Why

Most of what you find online for these problems is either a one-line Stack Overflow answer
that does not match your actual symptom, or a vendor page that assumes the GUI still looks
the way it did three versions ago. These notes are the other thing: the evidence-gathering
order, the command that actually produced the answer, and the pitfall that cost the time.

They are organised the way a diagnosis runs, not the way a manual is written:

> **symptom / when it applies → root cause → commands and steps → how to verify → pitfalls**

Every note is self-contained and dated to the environment it was written on. Anything that
was environment-specific has been replaced with a placeholder (see
[docs/SANITIZE_LOG.md](docs/SANITIZE_LOG.md)); placeholders are examples, not values you
should copy blindly.

## Repository layout

```
windows-ops-notes/
├── README.md                  # this file (English)
├── README.zh-CN.md            # 中文版
├── notes/
│   ├── network/               # campus network, OpenWrt, proxy, speed diagnostics
│   ├── windows-apps/          # installing software without admin rights
│   ├── windows-autostart/     # startup entries, popup hunting, crash loops
│   ├── windows-boot/          # USB install media, Linux install, dual-boot resizing
│   ├── windows-filesystem/    # file locks, "in use by another process"
│   ├── windows-gui/           # window enumeration / recovery, proxy client
│   ├── windows-hardware/      # hardware enumeration, GPU/eGPU, blue screens
│   └── windows-shell/         # console windows, silent launch, locale quirks
├── scripts/                   # the tools the notes call, usable on their own
└── docs/SANITIZE_LOG.md       # what was removed before publishing
```

## Quickstart

1. Read the note that matches your symptom, e.g. `notes/windows-hardware/hardware-diagnostics.md`.
2. Run the probe the note names, from `scripts/`, with no arguments first (`--help` where
   the tool has it) — the tools are stdlib-only.
3. Replace the `<PLACEHOLDER>` values (`<GPU_INDEX>`, `<GPU_INSTANCE_ID>`, `<口令>`, …) with
   your own before you run anything that writes state.

```bash
python scripts/check_secrets.py .        # privacy gate, run it before publishing anything
python scripts/memcheck.py > mem.txt     # full memory picture of the box
python scripts/pe_subsystem.py <exe>     # 2 = GUI (no console), 3 = console (pops a window)
```

## Notes index

### Network

| Note | When to use it | One-line idea |
|---|---|---|
| [campus-edge-router.md](notes/network/campus-edge-router.md) | Replacing the dorm/office edge router behind a captive portal, MAC clone, LAN subnet migration | Get a durable root channel (SSH key) before you touch the production link |
| [campus-network-profile-template.md](notes/network/campus-network-profile-template.md) | Blank template for documenting any campus/office network | Pin down four blocks: official facts / topology / measured bandwidth / limits |
| [multi-wan-proxy-routing.md](notes/network/multi-wan-proxy-routing.md) | Wired + wireless + TUN proxy all present, "some sites work, some don't" | The proxy only carries its own traffic — fix the direct path, not the proxy config |
| [network-speed-diagnostics.md](notes/network/network-speed-diagnostics.md) | "The network is slow", before proposing any fix | Test four layers separately: plan tier / device link / peering / proxy route |
| [openwrt-ipq6018-ecosystem.md](notes/network/openwrt-ipq6018-ecosystem.md) | OpenWrt on memory-tight IPQ6018 hardware, missing kernel modules | The missing `tun` kmod is the hard blocker; three alternatives, ranked by cost |
| [openwrt-ubus-rpc.md](notes/network/openwrt-ubus-rpc.md) | Router reachable over ubus but SSH is broken, or you need scripted config changes | ubus RPC is the fallback channel: read files, set config, restart services |
| [portal-autologin-service.md](notes/network/portal-autologin-service.md) | Building a captive-portal keepalive/login watchdog | Probe real page content, never a captive-detection URL — those are whitelisted |
| [proxy-client-control-api.md](notes/network/proxy-client-control-api.md) | Scripting Clash Verge Rev / mihomo on Windows | The control API lives on a named pipe; `curl` cannot open one — use ctypes |

### Windows: applications, autostart, boot

| Note | When to use it | One-line idea |
|---|---|---|
| [software-deploy-no-admin.md](notes/windows-apps/software-deploy-no-admin.md) | Installing software on a machine where you have no admin rights | Portable-path install, then compress the steps into a one-click bundle |
| [autostart-inventory-and-popup-source.md](notes/windows-autostart/autostart-inventory-and-popup-source.md) | Something pops up at login and you cannot find its startup entry | There are five autostart places plus one hidden session-restore path |
| [case-crashloop-and-dock-popup.md](notes/windows-autostart/case-crashloop-and-dock-popup.md) | A window appears over and over, or a window appears once | Process count + creation time separates a crash loop from a session restore |
| [startup-popup-playbook.md](notes/windows-autostart/startup-popup-playbook.md) | You want the full ordered procedure, not a single trick | Window match → five startup points → process tree → backup → fix and roll back |
| [linux-install-notes.md](notes/windows-boot/linux-install-notes.md) | Installing a Ubuntu-family distro on an x86_64 box | Decide boot mode before partitioning; run a health check right after install |
| [offline-ext4-shrink.md](notes/windows-boot/offline-ext4-shrink.md) | Making room for a second OS on a disk that already runs Linux | Back up first; sizes, `e2fsck`, and re-verify — all three or it is not done |
| [usb-install-media.md](notes/windows-boot/usb-install-media.md) | Building bootable USB media (Ventoy, ISO, hybrid ISO) | Confirm the USB identity, verify the ISO twice, let Ventoy copy it |
| [ventoy-gui-automation.md](notes/windows-boot/ventoy-gui-automation.md) | Automating the Ventoy2Disk GUI, or clicks that "do nothing" | Foreground lock and full-screen overlay break physical clicks; bring to front first |

### Windows: filesystem, GUI, hardware, shell

| Note | When to use it | One-line idea |
|---|---|---|
| [file-lock-hunting.md](notes/windows-filesystem/file-lock-hunting.md) | "The file is in use by another process" and you need the exact holder | Restart Manager gives the holder name; only kill it once no window is visible |
| [proxy-client-windows-notes.md](notes/windows-gui/proxy-client-windows-notes.md) | Daily operation and triage of a Clash Verge Rev setup | GUI and core are separate processes; fake-ip poisons "is this an internal address" tests |
| [window-recovery-and-automation.md](notes/windows-gui/window-recovery-and-automation.md) | A desktop app's window "disappeared" (Tauri/Electron) | Work the recovery ladder; a GUI restart is not a service restart |
| [hardware-diagnostics.md](notes/windows-hardware/hardware-diagnostics.md) | Enumerating hardware, tracing a GPU/eGPU, blue screens, standby hangs | Build the evidence chain first: event log, WER, process parent chain |
| [hardware-enumeration.md](notes/windows-hardware/hardware-enumeration.md) | "Is this card original? Is it actually connected?" | WMI/PnP instance ID + install history + parent device chain answer both |
| [event-ids-and-bugchecks.md](notes/windows-hardware/event-ids-and-bugchecks.md) | You have a System log or a stop code and need the semantics | One table mapping graphics/power/driver event IDs and bugcheck codes |
| [case-egpu-provenance.md](notes/windows-hardware/case-egpu-provenance.md) | Proving whether a GPU came with the machine or was added externally | SUBSYS vendor ID differing from the OEM ID is the proof |
| [case-modern-standby-hang.md](notes/windows-hardware/case-modern-standby-hang.md) | Laptop freezes after a standby/idle transition | A 30-second service timeout storm plus Kernel-Power 41 = whole-box freeze |
| [cn-env-encoding-quirks.md](notes/windows-shell/cn-env-encoding-quirks.md) | Chinese-locale Windows: patches that fail, "binary file" matches, installs that hang | Five classes: CRLF / encoding / paths / proxy interception / mirrors |
| [console-silent-launch.md](notes/windows-shell/console-silent-launch.md) | A console window pops up (or flashes repeatedly) at login | Any console-subsystem process pops a window; call the module via pythonw instead |
| [default-terminal-diagnostics.md](notes/windows-shell/default-terminal-diagnostics.md) | Windows 11 with Windows Terminal as the default host | conhost vs WindowsTerminal decides whether SW_HIDE has any effect |
| [silent-launch-case-service.md](notes/windows-shell/silent-launch-case-service.md) | A uv/pip-installed service keeps flashing windows | Two triggers racing to restart it, plus a wrapper that re-execs — fix both |

## Scripts

All Python scripts are standard library only; they print to stdout and exit non-zero on
failure, which makes them usable as gates.

| Script | Purpose |
|---|---|
| [check_secrets.py](scripts/check_secrets.py) | Zero-dependency repo scanner: credentials, high-entropy tokens, private IPs, MACs, e-mails, profile paths, internal hostnames |
| [memcheck.py](scripts/memcheck.py) | Whole-box memory picture: commit charge, memory types, per-app rollup, pagefile, GPU memory |
| [catch_popup.py](scripts/catch_popup.py) | Sample the process table and print every newly appeared console-class process with its parent chain |
| [watch_popups.py](scripts/watch_popups.py) | Same probe tuned for boot-time storms (run it right after login) |
| [read_visible_windows.ps1](scripts/read_visible_windows.ps1) | List visible top-level windows with their owning process |
| [find_file_lock.py](scripts/find_file_lock.py) | Which process holds a file open, via the Restart Manager API |
| [pe_subsystem.py](scripts/pe_subsystem.py) | Read PE headers without running the file: subsystem 2 = GUI, 3 = console |
| [mihomo_pipe_api.py](scripts/mihomo_pipe_api.py) | Talk to the mihomo (Clash Meta) control API over its Windows named pipe |
| [vscode_vsix_install.py](scripts/vscode_vsix_install.py) | Install VS Code extensions offline from VSIX, picking a compatible version |
| [wan_mab_watchdog.sh](scripts/wan_mab_watchdog.sh) | OpenWrt/busybox-ash keepalive: probe real content, bounce WAN to re-trigger MAC auth |
| [gpu-power-mode/](scripts/gpu-power-mode/) | Four `.bat` templates: disable eGPU, enable eGPU, clock-cap "eco" mode, restore defaults |

## Configuration

Nothing needs a config file. Environment variables, with their defaults:

| Variable | Used by | Default | Meaning |
|---|---|---|---|
| `MIHOMO_PIPE` | mihomo_pipe_api.py | `\\.\pipe\verge-mihomo` | Named pipe of the control API |
| `MIHOMO_SECRET` | mihomo_pipe_api.py | empty | Bearer secret, if the control API has one |
| `LOCALAPPDATA` | vscode_vsix_install.py | (Windows) | Where it probes for the VS Code CLI |
| `PORTAL_MARK` | wan_mab_watchdog.sh | `10.0.0.254` | String in the response body that means "not authenticated" |
| `PROBE_URLS` | wan_mab_watchdog.sh | `http://www.baidu.com http://www.163.com` | Real pages used as authentication probes |
| `WAN_IF` | wan_mab_watchdog.sh | `wan` | UCI/interface name of the WAN link to bounce |
| `LOG`, `STATE` | wan_mab_watchdog.sh | `/etc/wan_mab.log`, `/etc/wan_mab.state` | Log and state file (put them in `/etc/sysupgrade.conf` to survive firmware upgrade) |
| `FAIL_NEED`, `COOLDOWN` | wan_mab_watchdog.sh | `2`, `900` | Consecutive failures before acting; seconds between actions |
| `DOWN_SECONDS`, `SETTLE` | wan_mab_watchdog.sh | `25`, `25` | Physical link down time; settle time before re-probing |
| `BACKOFF_STEP`, `BACKOFF_MAX` | wan_mab_watchdog.sh | `1800`, `7200` | Backoff growth and cap after failed bounces |

## Requirements

- **Windows notes and scripts**: Windows 10 / 11, Windows PowerShell 5.1+, Python 3.x
  (standard library only), `nvidia-smi` for the GPU sections (skipped when absent).
- **Router notes and the watchdog**: OpenWrt / ImmortalWrt, `ubus` + `dropbear`,
  busybox `ash` (no `curl`, no `sftp-server` assumed).
- **Boot/dual-boot notes**: a Linux live session for the ext4 work; Ventoy for the USB media.
- No third-party Python packages. See [requirements.txt](requirements.txt).

## Limitations

- **Environment-specific by construction.** Every note describes one real machine, one
  router model, one portal vendor. The reasoning transfers; the exact output does not.
- **Placeholders must be replaced.** `AA:BB:CC:DD:EE:02`, `192.168.1.x`, `10.0.0.x`,
  `<GPU_INSTANCE_ID>`, `<口令>` are examples. Device instance IDs and GPU indexes change
  when you move a card to another port or reinstall its driver.
- **Dated behaviour.** Portal menus, LuCI page layouts and router firmware were verified on
  the versions named in each note; vendors move things around.
- **Some procedures change system state** — crash-dump settings, power settings, UCI config,
  firewall, disabling devices. Read the rollback section first and take a backup.
- **No warranty.** Notes are a record of what worked once; verify before trusting them on a
  machine that matters.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Inspired-by-Atmosphere.
