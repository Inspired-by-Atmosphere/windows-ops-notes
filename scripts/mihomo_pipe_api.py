#!/usr/bin/env python3
"""mihomo_pipe_api.py - talk to the mihomo (Clash Meta) control API on Windows.

On Windows the mihomo control API is exposed over a named pipe
(\\.\pipe\verge-mihomo) speaking plain HTTP. curl cannot open a named pipe, so
this script implements the pipe client with ctypes and no third-party deps.

Usage:
    python mihomo_pipe_api.py version|configs|proxies
    python mihomo_pipe_api.py select "<group>" "<node>"
    python mihomo_pipe_api.py mode [rule|global|direct]
    python mihomo_pipe_api.py delay "<node>" [--timeout 5000]
    python mihomo_pipe_api.py --pipe "\\.\pipe\my-mihomo" version

Environment:
    MIHOMO_PIPE    override the pipe name (default \\.\pipe\verge-mihomo)
    MIHOMO_SECRET  bearer token, only needed if the pipe enforces one

Notes:
  * Access over the named pipe is normally NOT authenticated, but sending a
    Bearer header is harmless and keeps the script working if that changes.
  * The GUI's HTTP controller port is often disabled (enable_external_controller:
    false), so probing 9090/9097 returns nothing - use the pipe.
  * Responses may be chunked; parse_body() de-chunks before json.loads.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import urllib.parse

DEFAULT_PIPE = os.environ.get("MIHOMO_PIPE", r"\\.\pipe\verge-mihomo")
SECRET = os.environ.get("MIHOMO_SECRET", "")

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
BUFSIZE = 65536


def pipe_request(pipe, method, path, body=None):
    """Return (raw_http_response_text, error)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wt.HANDLE
    h = k32.CreateFileW(pipe, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
    if h in (ctypes.c_void_p(-1).value, None, 0):
        return None, "CreateFileW failed, last_error=%d" % ctypes.get_last_error()

    headers = [
        "%s %s HTTP/1.1" % (method, path),
        "Host: localhost",
    ]
    if SECRET:
        headers.append("Authorization: Bearer %s" % SECRET)
    headers.append("Connection: close")
    if body:
        headers.append("Content-Length: %d" % len(body))
        headers.append("Content-Type: application/json")
    req = ("\r\n".join(headers) + "\r\n\r\n" + (body or "")).encode("utf-8")

    written = wt.DWORD()
    if not k32.WriteFile(h, req, len(req), ctypes.byref(written), None):
        err = ctypes.get_last_error()
        k32.CloseHandle(h)
        return None, "WriteFile failed, last_error=%d" % err

    data = b""
    buf = ctypes.create_string_buffer(BUFSIZE)
    read = wt.DWORD()
    while True:
        k32.ReadFile(h, buf, BUFSIZE, ctypes.byref(read), None)
        n = read.value
        if n == 0:
            break
        data += buf.raw[:n]
        if n < BUFSIZE:
            break
    k32.CloseHandle(h)
    return data.decode("utf-8", errors="replace"), None


def parse_body(raw):
    """Split an HTTP response, de-chunk it, return (status, parsed_json_or_text)."""
    parts = raw.split("\r\n\r\n", 1)
    head = parts[0]
    body = parts[1] if len(parts) > 1 else ""
    try:
        status = int(head.split(" ")[1])
    except (IndexError, ValueError):
        return 0, raw
    if "transfer-encoding: chunked" in head.lower():
        out, pos = [], 0
        while True:
            e = body.find("\r\n", pos)
            if e == -1:
                break
            size = int(body[pos:e], 16)
            if size == 0:
                break
            out.append(body[e + 2:e + 2 + size])
            pos = e + 2 + size + 2
        body = "".join(out)
    try:
        return status, json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        return status, body


def api(pipe, method, path, body=None):
    raw, err = pipe_request(pipe, method, path, json.dumps(body) if body else None)
    if err:
        sys.exit("ERROR: %s (is the proxy client running?)" % err)
    status, data = parse_body(raw)
    if status >= 400:
        sys.exit("API error %s: %s" % (status, raw[:300]))
    return data


def quote(s):
    return urllib.parse.quote(s, safe="")


def main(argv=None):
    ap = argparse.ArgumentParser(description="mihomo control API over a Windows named pipe.")
    ap.add_argument("--pipe", default=DEFAULT_PIPE, help="Named pipe path.")
    ap.add_argument("command", choices=["version", "configs", "proxies", "select", "mode", "delay"])
    ap.add_argument("args", nargs="*", help="select: <group> <node>; mode: <rule|global|direct>; delay: <node>")
    ap.add_argument("--timeout", type=int, default=5000, help="Delay test timeout in ms.")
    ap.add_argument("--url", default="http://www.gstatic.com/generate_204",
                    help="URL used for the delay test.")
    a = ap.parse_args(argv)
    pipe = a.pipe

    if a.command == "version":
        print(api(pipe, "GET", "/version"))
    elif a.command == "configs":
        print(api(pipe, "GET", "/configs"))
    elif a.command == "proxies":
        d = api(pipe, "GET", "/proxies")
        for name, g in d.get("proxies", {}).items():
            print("%s (%s): %s" % (name, g.get("type"), g.get("now", "-")))
    elif a.command == "select":
        if len(a.args) != 2:
            sys.exit("usage: select <group> <node>")
        api(pipe, "PUT", "/proxies/%s" % quote(a.args[0]), {"name": a.args[1]})
        print("Switched %s -> %s" % (a.args[0], a.args[1]))
    elif a.command == "mode":
        if a.args:
            api(pipe, "PATCH", "/configs", {"mode": a.args[0]})
            print("Mode set to: %s" % a.args[0])
        else:
            print(api(pipe, "GET", "/configs").get("mode"))
    elif a.command == "delay":
        if not a.args:
            sys.exit("usage: delay <node>")
        node = a.args[0]
        r = api(pipe, "GET", "/proxies/%s/delay?timeout=%d&url=%s"
                % (quote(node), a.timeout, quote(a.url)))
        print("%s: %sms" % (node, r.get("delay")) if r.get("delay") else "%s: timeout" % node)
    return 0


if __name__ == "__main__":
    sys.exit(main())
