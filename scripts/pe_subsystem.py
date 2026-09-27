#!/usr/bin/env python
"""Read PE headers to classify an exe's subsystem.

Purpose: on Windows, "pythonw.exe" from a uv-created venv is a fake Console
shim (subsystem=3) that re-execs back to console python.exe and still pops a
Windows Terminal despite pythonw + CREATE_NO_WINDOW. The real GUI pythonw
(subsystem=2) lives in the uv base dir. This probe tells you which one a
given exe is WITHOUT running it.

Subsystem: 2 = GUI (no console / no popup), 3 = Console (pops a window).

Usage:
    python pe_subsystem.py C:\\path\\to\\pythonw.exe [more.exe ...]

Reference: notes/windows-shell/console-silent-launch.md (pitfall: uv venv pythonw shim).
"""
import struct
import sys

SUBSYSTEM_NAMES = {
    1: "Native",
    2: "GUI (no console, no popup)",
    3: "Console (pops a window)",
    5: "OS2",
    7: "POSIX",
    9: "Windows CE",
    10: "EFI",
}


def subsystem(path: str):
    with open(path, "rb") as f:
        data = f.read()
    idx = data.find(b"PE\x00\x00")
    if idx < 0:
        return None, "not a PE executable"
    # Optional header starts after PE sig (4) + COFF header (20)
    opt_off = idx + 4 + 20
    magic = struct.unpack("<H", data[opt_off : opt_off + 2])[0]  # 0x20b = PE32+
    # Subsystem field is at offset 68 within the optional header.
    subsys = struct.unpack("<H", data[opt_off + 68 : opt_off + 70])[0]
    return subsys, SUBSYSTEM_NAMES.get(subsys, "unknown")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    for path in argv[1:]:
        subsys, name = subsystem(path)
        if subsys is None:
            print(f"{path}: {name}")
        else:
            print(f"{path}: subsystem={subsys} -> {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
