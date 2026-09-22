# -*- coding: utf-8 -*-
"""Test the self-update swap script for real.

The first implementation used a .bat with `timeout` and `start` inside a
DETACHED_PROCESS, which silently failed: the app closed and never came back.
That bug was only findable by running it, so this test runs it — with a stand-in
process to wait for and stand-in "executables" — and asserts that the file was
actually replaced and the replacement actually launched.

Run:  "C:\\gv\\Scripts\\python.exe" desktop\\test_updater_swap.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import updater  # noqa: E402

_ok = True


def check(label, cond, detail=""):
    global _ok
    print(f"  {'PASS' if cond else 'FAIL'}  {label}"
          f"{(' — ' + str(detail)) if detail and not cond else ''}")
    _ok = _ok and bool(cond)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="gf_swaptest_")
    dst = os.path.join(tmp, "app.cmd")            # stands in for the running .exe
    src = os.path.join(tmp, "_update_app.cmd")    # stands in for the download
    marker = os.path.join(tmp, "relaunched.txt")
    log = os.path.join(tmp, "swap.log")

    with open(dst, "w", encoding="ascii") as fh:
        fh.write("@echo off\r\nrem OLD VERSION\r\n")
    with open(src, "w", encoding="ascii") as fh:
        fh.write(f'@echo off\r\nrem NEW VERSION\r\necho relaunched> "{marker}"\r\n')

    print("1. script generation")
    script = updater.build_swap_script(12345, src, dst, log)
    check("waits on the right pid", "Wait-Process -Id 12345" in script)
    # cmd's `timeout /t` is what breaks without a console; Wait-Process's
    # -Timeout parameter is fine and must not trip this check.
    check("no cmd `timeout /t` (breaks without a console)",
          "timeout /t" not in script.lower())
    check("no cmd `start` (needs a console)", " start " not in f" {script.lower()} ")
    check("retries the move", "-lt 40" in script)
    check("logs what happened", "Out-File" in script)

    print("2. path quoting")
    weird = updater.build_swap_script(1, r"C:\a b\it's.exe", r"C:\c d\x.exe", "L")
    check("space-containing paths quoted", "'C:\\a b\\it''s.exe'" in weird, weird[:0] or "quoting")
    check("apostrophe doubled", "it''s" in weird)

    print("3. the real thing: wait for a process, replace a file, relaunch it")
    # A stand-in for the app being updated: a process that exits shortly.
    victim = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", "Start-Sleep -Seconds 3"],
        creationflags=0x08000000,
    )
    print(f"     stand-in process pid={victim.pid}, exits in ~3 s")

    script = updater.build_swap_script(victim.pid, src, dst, log)
    subprocess.Popen(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        creationflags=0x08000000,
    )

    # It must NOT act before the process has gone.
    time.sleep(1.5)
    early = open(dst, encoding="ascii").read()
    check("waits — file untouched while the process lives", "OLD VERSION" in early,
          early.strip())

    deadline = time.time() + 40
    while time.time() < deadline:
        if os.path.exists(marker) and "NEW VERSION" in open(dst, encoding="ascii").read():
            break
        time.sleep(0.5)

    victim.wait(timeout=30)
    after = open(dst, encoding="ascii").read() if os.path.exists(dst) else ""
    check("file was replaced", "NEW VERSION" in after, after.strip())
    check("download was consumed (moved, not copied)", not os.path.exists(src))
    check("replacement was launched", os.path.exists(marker),
          "marker never appeared — relaunch failed")

    if os.path.exists(log):
        print("     swap log:")
        for line in open(log, encoding="utf-8-sig").read().splitlines():
            print(f"       {line}")
        text = open(log, encoding="utf-8-sig").read()
        check("log records the replace", "replaced the exe" in text)
        check("log records the relaunch", "relaunched" in text)
        check("no failure recorded", "MOVE FAILED" not in text and "relaunch failed" not in text)
    else:
        check("swap log written", False, "no log file — the script probably never ran")

    print()
    print("ALL PASS" if _ok else "FAILURES ABOVE")
    print(f"(test files in {tmp})")
    return 0 if _ok else 1


if __name__ == "__main__":
    sys.exit(main())
