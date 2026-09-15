"""Playwright probe — client-event handlers push to a ClientState list.

Drives ``bench_clientevent.py`` (uvicorn :8961). The bug : ``log.push()``
mutated the array in place, V3 signals compare by identity, so nothing
re-rendered ("no events yet" forever). Asserts a client ``on_click``
push updates the bound log with zero network round-trips.

Run :  py tests/probes/probe_clientevent.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from tests.probes._serve import free_port

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("clientevent bench never came up on :8961")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_clientevent.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    posts: list[str] = []
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            console_errors: list[str] = []
            page.on("console", lambda m: console_errors.append(m.text)
                    if m.type == "error" else None)
            page.on("request", lambda r: posts.append(r.url)
                    if "/action/" in r.url else None)
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            log = lambda: page.inner_text("#log")  # noqa: E731

            print("\nClient events push to the bound log")
            check("starts empty", "no events yet" in log(), log())

            page.click("#btn-click")
            page.wait_for_timeout(120)
            check("after 1 click, log shows 'click'",
                  "click" in log() and "no events yet" not in log(), log())

            page.click("#btn-click")
            page.wait_for_timeout(120)
            check("after 2 clicks, log has two entries",
                  log().count("click") == 2, log())

            # A different event type appends, doesn't replace.
            page.hover("#btn-enter")
            page.wait_for_timeout(120)
            check("mouseenter appends 'enter'",
                  "enter" in log() and log().count("click") == 2, log())

            # Clear resets the list.
            page.click("#btn-clear")
            page.wait_for_timeout(120)
            check("Clear empties the log", "no events yet" in log(), log())

            check("ZERO network round-trips (pure client)", not posts,
                  f"{len(posts)} action POST(s)")
            check("no JS console errors", not console_errors,
                  "; ".join(console_errors[:6]))
            page.screenshot(path=str(HERE / "clientevent_screenshot.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"CLIENTEVENT PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("CLIENTEVENT PROBE PASSED — client handlers push to the bound log, no network.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
