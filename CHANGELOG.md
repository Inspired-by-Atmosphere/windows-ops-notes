# Changelog

All notable changes to this repository are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [0.1.0] - 2026-09-28

First public snapshot: 28 field notes plus 11 standalone scripts, collected from real
Windows / OpenWrt / campus-network troubleshooting sessions.

### Added

- **Notes, network**: campus edge router replacement and captive-portal recovery, campus
  network profile template, multi-WAN proxy routing, speed diagnostics, OpenWrt on
  IPQ6018, ubus RPC cheat sheet, portal autologin watchdog, proxy client control API.
- **Notes, Windows**: software deployment without admin rights; autostart inventory and
  popup sourcing (plus a crash-loop case and a full playbook); USB install media, Linux
  install and offline ext4 shrink; file-lock hunting; window recovery; hardware
  enumeration, GPU/eGPU provenance, event IDs and bugchecks, modern-standby hang; console
  silent launch, default-terminal diagnostics, Chinese-locale quirks.
- **Scripts**: `check_secrets.py` (privacy gate), `memcheck.py`, `catch_popup.py`,
  `watch_popups.py`, `read_visible_windows.ps1`, `find_file_lock.py`, `pe_subsystem.py`,
  `mihomo_pipe_api.py`, `vscode_vsix_install.py`, `wan_mab_watchdog.sh`, and four
  `gpu-power-mode/*.bat` templates.
- **Docs**: bilingual README, sanitization log, MIT license.

### Privacy review

- All notes passed a three-stage pre-publication review (credentials, identity/topology,
  internal-project terms). What was replaced and why is recorded in
  [docs/SANITIZE_LOG.md](docs/SANITIZE_LOG.md) — that log never contains the original values.
- `scripts/check_secrets.py` was tightened during that review: a vowel-ratio test and a GUID
  exception remove identifier false positives without weakening detection of real tokens
  (verified against a planted-leak fixture).
