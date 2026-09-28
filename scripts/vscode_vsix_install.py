#!/usr/bin/env python3
"""vscode_vsix_install.py - install VS Code extensions offline (VSIX).

Use when the marketplace is unreachable through the proxy, or when you must pin
an older version because the newest one demands a newer VS Code engine.

It does four things: list all versions -> pick the newest compatible one ->
download bypassing the proxy and gunzip -> install and verify.

Usage:
    python vscode_vsix_install.py <publisher.extension> [more ...]
    python vscode_vsix_install.py ms-vscode-remote.remote-ssh
    python vscode_vsix_install.py ms-vscode-remote.remote-ssh --code "<VS Code install>/bin/code"
    python vscode_vsix_install.py <ext> --list-versions    # only show versions + engine

Hard-won details (do not "simplify" these away):
  * extensionquery flags must be 439 (0x1B7). Using 951 sets
    IncludeLatestVersionOnly and returns a single version, which makes the
    script wrongly conclude "no compatible version".
  * The downloaded vspackage is gzip-wrapped (magic 1f 8b); gunzip it to PK(zip).
  * code --install-extension needs a Windows absolute path; an MSYS-style
    relative path fails.
  * Extensions declare an engine range (e.g. ^1.133.0). Newer than your local
    VS Code => not installable, fall back to a historical version.
"""

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

GALLERY = "https://marketplace.visualstudio.com/_apis/public/gallery"
QUERY_URL = GALLERY + "/extensionquery"
FLAGS_ALL_VERSIONS = 439  # 0x1B7 - never use 951 (it adds IncludeLatestVersionOnly)
# Lookup order: PATH first, then the standard per-machine / per-user install
# roots. The roots are read from the environment (%ProgramFiles%, %LOCALAPPDATA%)
# so no machine-specific drive letter is baked into this file. If VS Code lives
# somewhere else, append your own path - e.g. "<drive>:/<dir>/bin/code".
CODE_CANDIDATES = ["code", "code.cmd"]


def installed_code_candidates():
    """Absolute paths of the `code` CLI under the standard install roots."""
    out = []
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        out.append(os.path.join(program_files, "Microsoft VS Code", "bin", "code"))
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        out.append(os.path.join(local_appdata, "Programs", "Microsoft VS Code", "bin", "code"))
    return out


def opener_no_proxy():
    """Explicitly bypass environment proxies (they are often persisted and may
    not be able to reach the marketplace)."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url, data=None):
    req = urllib.request.Request(url)
    if data is not None:
        req.add_header("Accept", "application/json;api-version=7.2-preview.1")
        req.add_header("Content-Type", "application/json")
        return opener_no_proxy().open(req, json.dumps(data).encode(), timeout=60).read()
    return opener_no_proxy().open(req, timeout=120).read()


def find_code(explicit=None):
    if explicit:
        return explicit
    for cand in CODE_CANDIDATES + installed_code_candidates():
        found = shutil.which(cand)
        if found:
            return found
        if os.path.isabs(cand) and os.path.exists(cand):
            return cand
    return None


def code_version(code):
    out = subprocess.run([code, "--version"], capture_output=True, text=True, shell=True)
    return (out.stdout or "").splitlines()[0].strip() if out.stdout else ""


def ver_tuple(s):
    parts = []
    for chunk in str(s).split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts + [0] * (4 - len(parts)))


def engine_ok(engine, target):
    if not engine or not engine.startswith(("^", ">=", "~")):
        return True  # no engine constraint
    return ver_tuple(target) >= ver_tuple(engine.lstrip("^=~"))


def list_versions(ext_id):
    body = {
        "filters": [{"criteria": [{"filterType": 7, "value": ext_id}], "pageSize": 1}],
        "flags": FLAGS_ALL_VERSIONS,
    }
    raw = fetch(QUERY_URL, body)
    exts = json.loads(raw.decode())["results"][0]["extensions"]
    if not exts:
        raise SystemExit("extension not found: %s" % ext_id)
    e = exts[0]
    rows = []
    for v in e["versions"]:
        eng = ""
        for p in v.get("properties", []):
            if p["key"] == "Microsoft.VisualStudio.Code.Engine":
                eng = p["value"]
        rows.append((v["version"], eng))
    return e.get("displayName", ext_id), rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install VS Code extensions offline (VSIX).")
    ap.add_argument("extensions", nargs="+", help="Extension IDs, e.g. ms-python.python")
    ap.add_argument("--code", help="Path to the code CLI (auto-detected when omitted).")
    ap.add_argument("--list-versions", action="store_true", help="Only list versions and engine requirements.")
    a = ap.parse_args(argv)

    code = find_code(a.code)
    if not code:
        raise SystemExit("Cannot find the code CLI; pass --code=<path>.")
    target = code_version(code)
    print("Local VS Code engine version: %s   (code: %s)" % (target, code))

    tmpdir = tempfile.mkdtemp(prefix="vsix_")
    failed = []

    for ext_id in a.extensions:
        print("\n=== %s ===" % ext_id)
        try:
            name, rows = list_versions(ext_id)
        except Exception as exc:  # noqa: BLE001 - network/API failure per extension
            print("  query failed: %s" % exc)
            failed.append(ext_id)
            continue
        print("%s: %d versions" % (name, len(rows)))

        picked = None
        for ver, eng in rows:  # API returns newest first
            ok = engine_ok(eng, target)
            if a.list_versions:
                print("  %-22s engine %-12s %s" % (ver, eng or "-", "OK" if ok else "TOO NEW"))
            if ok and picked is None:
                picked = (ver, eng)
        if a.list_versions:
            continue
        if not picked:
            print("  x no version compatible with %s" % target)
            failed.append(ext_id)
            continue

        ver, eng = picked
        print("  -> picking %s (engine %s)" % (ver, eng or "-"))
        pub, name_only = ext_id.split(".", 1)
        url = "%s/publishers/%s/vsextensions/%s/%s/vspackage" % (GALLERY, pub, name_only, ver)
        raw = fetch(url)

        if raw[:2] == b"\x1f\x8b":  # gzip wrapper
            raw = gzip.decompress(raw)
        if raw[:2] != b"PK":
            print("  x downloaded payload is not a zip (magic %r); wrong API/version?" % raw[:2])
            failed.append(ext_id)
            continue

        vsix = os.path.join(tmpdir, "%s-%s.vsix" % (name_only, ver))
        with open(vsix, "wb") as fh:
            fh.write(raw)

        win_path = os.path.abspath(vsix).replace("/", "\\")
        cmdline = '"%s" --install-extension "%s" --force' % (code, win_path)
        r = subprocess.run(cmdline, capture_output=True, text=True, shell=True)
        tail = (r.stdout or "").strip().splitlines()
        print("  " + (tail[-1] if tail else (r.stderr or "").strip()[:200]))
        if r.returncode != 0:
            failed.append(ext_id)

    lst = subprocess.run([code, "--list-extensions"], capture_output=True, text=True, shell=True)
    installed = {x.strip().lower() for x in (lst.stdout or "").splitlines() if x.strip()}
    print("\n=== verify ===")
    for ext_id in a.extensions:
        print("  %-42s %s" % (ext_id, "installed" if ext_id.lower() in installed else "MISSING"))
    print("temp dir: %s" % tmpdir)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
