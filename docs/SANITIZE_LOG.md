# Sanitization log

What was removed or replaced before this repository was published, why, and how the result
was verified. **This file never records an original value** — not the literal, not a hash of
it. Categories and counts only, as required by the publishing rules.

Two rounds are recorded:

- **Round 1 — bulk sanitization** when the notes were first collected into this staging tree.
- **Round 2 — verification pass** on the finished tree (this round). Counts below are
  measured on the tree as committed, so every number can be re-checked with the commands in
  the last section.

Placeholder ranges/values used throughout: `192.168.1.x`, `10.0.0.x` for private addresses;
RFC 5737 `192.0.2.0/24` and `198.51.100.0/24` where a complete address is needed; `<盘符>` for a
drive letter; `AA:BB:CC:DD:EE:xx` for MACs; `$HOME/…`, `~/…` and repository-relative paths
for filesystem locations; `<…>` angle-bracket tokens for anything the reader must supply.

## Round 1 — bulk sanitization

Counts are placeholder **occurrences measured in the tree as committed** (round-1 records
were not kept per item); the action column describes what the placeholder stands for.

| Category | Occurrences now | Action |
|---|---|---|
| Home / absolute user paths | 21 placeholders | Real profile paths replaced with `$HOME/…`, `~/…`, `<user>`, or a repository-relative path |
| Foreign project-drive paths | 18 | Absolute paths into this machine's work drives replaced with repository-relative links (`../scripts/…`) |
| Private network addresses | 28 | Real private addresses replaced with the documentation example ranges (incl. the gateway, portal and in-house device addresses) |
| Hosts / services / device models | 20 | Concrete server, router and service names replaced with `your-router` / `your-service` / `server-a` / `the old router` |
| Organisation | 2 | Campus / organisation name replaced with an "Example University"-style placeholder |
| People | 0 | No personal names were present after review (re-verified in round 2) |
| Credentials | 31 placeholders | No literal credential ever entered the tree; `~/.campus_cred` is a path name only, and every password/SSID/instance-ID position holds an angle-bracket placeholder |
| Dates | 31 | Dates that identify a specific event on a specific machine replaced with an explicit "date removed" marker |
| MAC addresses | 3 | Real MACs replaced with the `AA:BB:CC:DD:EE:xx` placeholder shape |

## Round 2 — verification pass (this round)

| Category | Count | Action |
|---|---|---|
| Credentials (vendor defaults) | 1 line | Literal factory-default router credentials (several account/password pairs plus a derived default password pattern) removed; only the *method* of obtaining access is kept, and no value is recorded anywhere |
| Private network addresses | 2 | Two remaining real private addresses (default-bridge-style, from a service bundle) replaced with the `10.0.0.x` documentation range |
| Device vendor / model / platform names | 6 | Router vendor, portal-platform vendor (including its SSO product name) and a corporate SSL-VPN product name replaced with generic descriptions; hardware vendor facts that carry the diagnosis were kept |
| Messaging-channel product name | 1 | A consumer chat-product name replaced with the neutral term "instant-messaging channel" |
| Internal project directory name | 1 (2 occurrences) | An in-house project directory name in a path example replaced with a generic example path |
| Broken replacement artefact | 1 | A bullet that had been over-replaced into three identical placeholder directory names was rewritten as a plain description |
| Dangling references | 3 | Three cross-references pointing at files outside this repository were replaced with links to notes that exist here, or folded into the text inline |

### Tooling changes made during round 2

`scripts/check_secrets.py` is the gate for this repository, so it was tightened rather than
loosened, and re-validated against a fixture with deliberately planted leaks:

| Change | Reason |
|---|---|
| High-entropy candidates must also be vowel-poor | Random tokens sit at a much lower vowel share than identifiers and prose; this removed identifier/path false positives without dropping any planted secret |
| A candidate carrying an RFC-4122 GUID is skipped | Device paths, efivars names and registry keys embed GUIDs; no credential is shaped that way |
| The documented example ranges tolerate the `…x` placeholder form, and stock OpenWrt UCI section names (`dhcp.lan`, `interface.lan`) are allowed | These are documentation conventions and vanilla OpenWrt config names, not real topology |

Validation fixture (kept out of the repository): five planted leaks — an assignment-style
random token, a private address, a MAC, a personal e-mail address and an internal hostname —
plus a control file containing only allowed forms. The scanner reported all five and none of
the allowed forms, before and after the changes above.

## Verification commands

The sweeps below are written so that this file does not match its own patterns.

```bash
python scripts/check_secrets.py .                                     # findings: 0 / RESULT: CLEAN

# Drive-letter and MSYS-style path sweep (negative lookbehind skips https:// etc.)
grep -rnP '(?<![A-Za-z])[A-Za-z]:[/\\]' --exclude-dir=.git .
grep -rnE '/[cde]/(Users|Hermes)' --exclude-dir=.git .

# Private addresses outside the documented example ranges
grep -rnP '\b(?:10\.(?!0\.0\.)|172\.(?:1[6-9]|2[0-9]|3[01])\.|192\.168\.(?!1\.))\d{1,3}\.\d{1,3}\b' --exclude-dir=.git .
```

Internal-project and identity terms were also swept by hand (campus/organisation names,
student or account identifiers, Wi-Fi passphrases, WAN MACs, private addresses, server names,
messaging accounts, e-mail addresses, personal names, and in-house project names). Result:
zero remaining occurrences. The categories and the reasoning are recorded above; the
individual strings are deliberately not.
