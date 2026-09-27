#!/usr/bin/env python3
"""check_secrets.py - zero-dependency secret / identity leak scanner for a repo.

Designed for a privacy gate before publishing: run it on the whole tree and
require zero findings.

Usage:
    python scripts/check_secrets.py .
    python scripts/check_secrets.py . --exclude check_secrets.py --exclude .git
    python scripts/check_secrets.py . --max-bytes 2000000 --json

What it looks for:
  1. Credential-shaped strings: cloud access keys, private key headers, bearer
     tokens, api_key / password / secret assignments with a literal value.
  2. High-entropy tokens (long random-looking strings) - catches keys that do
     not match any known prefix.
  3. Identity / topology leaks: e-mail addresses, private IPv4 ranges, MAC
     addresses, Windows user-profile paths, internal hostnames.
  4. Documentation placeholders that were never replaced: <...>, TODO, XXX,
     your-... in a value position are reported as INFO, not as failures.

Allowed by default (so an example-rich repo passes without noise):
  * the documentation example ranges 192.168.1.x, 10.0.0.x, 100.64.x
    (the "…x" placeholder form is treated as documentation, not a real address)
  * placeholder MACs AA:BB:CC:DD:EE:xx
  * noreply / example.com e-mail addresses
  * stock OpenWrt UCI section names such as dhcp.lan / interface.lan, which
    look like internal hostnames but exist in every vanilla OpenWrt install

Exit codes: 0 = clean, 1 = findings, 2 = usage error.

The scanner skips binary files by extension and by a NUL-byte probe.
"""

import argparse
import json
import os
import re
import sys

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache"}
SKIP_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".pyc", ".woff", ".woff2", ".ttf", ".mp4",
}

# Sensitive literals are assembled from fragments so this file never matches its
# own patterns (a scanner that trips on itself is useless).
_F = lambda *parts: "".join(parts)

PATTERNS = [
    ("cloud-access-key",
     re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private-key-block",
     re.compile(_F(r"-----BEGIN [A-Z ]*", r"PRIVATE KEY-----"))),
    ("openssh-private-key",
     re.compile(_F(r"-----BEGIN OPENSSH ", r"PRIVATE KEY-----"))),
    ("github-token",
     re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack-token",
     re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key",
     re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("jwt",
     re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("credential-assignment",
     re.compile(r"(?i)\b(?:api[_-]?key|apikey|secret|passwd|password|passphrase|"
                r"access[_-]?token|auth[_-]?token|client[_-]?secret|private[_-]?key)\b"
                r"\s*[:=]\s*[\"']?(?!\s*$|\$|<|%|\{\{|your[-_]|example|xxx|redacted|placeholder|"
                r"none|null|true|false|os\.environ|getenv)[\"']?([^\s\"'#]{8,})")),
    ("bearer-literal",
     re.compile(r"(?i)\bAuthorization\b[^\n]{0,20}Bearer\s+(?!\$\{|\$|<|\{\{|%)([A-Za-z0-9._\-]{20,})")),
    ("windows-user-path",
     re.compile(r"[A-Za-z]:\\\\?Users\\\\?(?!<user>|\$|\{|%|<USERNAME>)[A-Za-z0-9._\-]+")),
    ("private-ip",
     re.compile(r"\b(?:10\.(?!0\.0\.(?:\d|x|/))|172\.(?:1[6-9]|2\d|3[01])\.|"
                r"192\.168\.(?!1\.(?:\d|x|/))|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.)"
                r"\d{1,3}\.\d{1,3}\b")),
    ("mac-address",
     re.compile(r"\b(?!AA:BB:CC:DD:EE:)(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")),
    ("internal-hostname",
     re.compile(r"(?i)\b[a-z0-9][a-z0-9\-]{2,}\.(?:internal|local|lan|corp|intra|home)\b")),
]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
EMAIL_ALLOW = re.compile(r"(?i)(noreply|no-reply|example\.(com|org|net)|users\.noreply\.github\.com)$")

# Long random-looking strings. Tuned to avoid prose and ordinary identifiers:
# besides the length + Shannon-entropy test, a candidate must also be vowel-poor.
# Random tokens are near-uniform over [A-Za-z0-9], so the a/e/i/o/u share stays
# around 0.05-0.17; identifiers, paths and prose ("ChatGPT/Claude/Netflix") sit
# at 0.28+ and are rejected. Measured on a calibration set of both kinds.
ENTROPY_RE = re.compile(r"\b[A-Za-z0-9+/=_\-]{32,}\b")
VOWEL_RATIO_MAX = 0.25
# A token carrying an RFC-4122 GUID is an identifier (device path, efivars name,
# registry key), not a secret - no credential is shaped like that.
GUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
INFO_RE = re.compile(r"<[A-Z_]{2,}>|TODO|FIXME|XXX|your-[a-z\-]+")

# Stock OpenWrt UCI section identifiers. These match the ".lan" hostname shape
# but are generic config names present in every OpenWrt installation, not
# local topology.
UCI_LAN_ALLOW = re.compile(
    r"^(?:dhcp|interface|firewall|wireless|network|system|wan|lan|loopback)\.lan$")


def shannon(s):
    from math import log2
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * log2(c / n) for c in counts.values())


def entropy_hits(line):
    out = []
    for tok in ENTROPY_RE.findall(line):
        if re.fullmatch(r"[a-f0-9]{32,40}", tok):  # git sha / md5-ish, common in docs
            continue
        if GUID_RE.search(tok):  # identifier carrying a GUID, not a credential
            continue
        vowels = sum(ch in "aeiouAEIOU" for ch in tok) / len(tok)
        if vowels > VOWEL_RATIO_MAX:  # word-like / identifier-like, not a token
            continue
        if shannon(tok) >= 4.2:
            out.append(tok)
    return out


def iter_files(root, excludes):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in excludes:
                continue
            path = os.path.join(dirpath, name)
            if os.path.splitext(name)[1].lower() in SKIP_EXT:
                continue
            yield path


def scan_file(path, max_bytes):
    findings, infos = [], []
    try:
        if os.path.getsize(path) > max_bytes:
            return findings, infos, "skipped (too large)"
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        return findings, infos, "unreadable: %s" % exc
    if b"\x00" in raw[:4096]:
        return findings, infos, "skipped (binary)"
    text = raw.decode("utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rx in PATTERNS:
            for m in rx.finditer(line):
                hit = m.group(0) or ""
                if name == "internal-hostname" and UCI_LAN_ALLOW.match(hit):
                    continue
                findings.append((lineno, name, hit[:60]))
        for m in EMAIL_RE.finditer(line):
            if not EMAIL_ALLOW.search(m.group(0)):
                findings.append((lineno, "email-address", m.group(0)[:60]))
        for tok in entropy_hits(line):
            findings.append((lineno, "high-entropy-token", tok[:60]))
        if INFO_RE.search(line):
            infos.append((lineno, "placeholder-or-todo", INFO_RE.search(line).group(0)))
    return findings, infos, "ok"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Scan a directory tree for secrets, private IPs, MACs and identity leaks.")
    ap.add_argument("root", nargs="?", default=".", help="Directory to scan (default: .)")
    ap.add_argument("--exclude", action="append", default=[], help="File name to skip (repeatable).")
    ap.add_argument("--max-bytes", type=int, default=2_000_000, help="Skip files larger than this.")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    ap.add_argument("--show-info", action="store_true", help="Also print INFO (placeholder/TODO) lines.")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.root):
        print("not a directory: %s" % args.root, file=sys.stderr)
        return 2

    results, total = [], 0
    for path in iter_files(args.root, set(args.exclude)):
        findings, infos, status = scan_file(path, args.max_bytes)
        rel = os.path.relpath(path, args.root)
        if findings:
            total += len(findings)
        results.append({"file": rel, "status": status, "findings": findings, "info": infos})

    if args.json:
        print(json.dumps({"total_findings": total, "files": results}, indent=1))
    else:
        for r in results:
            if r["status"] not in ("ok",):
                print("  [%s] %s" % (r["status"], r["file"]))
            for lineno, name, sample in r["findings"]:
                print("%s:%d: [%s] %s" % (r["file"], lineno, name, sample.replace("\n", " ")))
            if args.show_info:
                for lineno, name, sample in r["info"]:
                    print("%s:%d: INFO [%s] %s" % (r["file"], lineno, name, sample))
        print("\nscanned %d file(s); findings: %d" % (len(results), total))
        print("RESULT: %s" % ("CLEAN" if total == 0 else "FINDINGS PRESENT"))
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
