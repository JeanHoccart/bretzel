"""Playwright probe — bool toggles bound to a server var stay OFF.

Drives ``bench_switch_server.py`` (uvicorn :8959). Three cases, each
toggled ON then OFF, asserting the control actually STAYS off after the
server refresh (the bug : it snapped back on because an unchecked
checkbox transmits nothing) :

1. server-bound Switch (autoname)   — POST on uncheck carries ``…=false``
2. server-bound Checkbox (autoname) — same, shared helper
3. client-bound Switch              — non-regression : toggles freely,
   no hx-vals injected (the bridge ships the store).

Run :  py tests/probes/probe_switch_server.py
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
    raise RuntimeError("switch-server bench never came up on :8959")


def checked(page, cid: str) -> bool:
    return page.eval_on_selector(f"#{cid}", "el => el.checked")


def click(page, cid: str) -> None:
    page.eval_on_selector(f"#{cid}", "el => el.click()")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_switch_server.py"), str(PORT)],
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
            page.on(
                "request",
                lambda r: posts.append(r.post_data or "<empty>")
                if "/action/" in r.url and r.method == "POST" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            # ── 1. server-bound Switch ────────────────────────────────
            print("\n1. server-bound Switch (autoname)")
            check("starts unchecked", checked(page, "server-switch") is False)
            click(page, "server-switch")
            page.wait_for_timeout(400)
            check("checked after ON", checked(page, "server-switch") is True,
                  page.inner_text("#readout-switch"))
            posts.clear()
            click(page, "server-switch")
            page.wait_for_timeout(600)
            print(f"    POST on uncheck: {(posts[0] if posts else '<none>')!r}")
            check("STAYS unchecked after OFF",
                  checked(page, "server-switch") is False,
                  page.inner_text("#readout-switch"))
            check("server reads enabled = False",
                  "False" in page.inner_text("#readout-switch"),
                  page.inner_text("#readout-switch"))

            # ── 2. server-bound Checkbox ──────────────────────────────
            print("\n2. server-bound Checkbox (autoname)")
            click(page, "server-checkbox")
            page.wait_for_timeout(400)
            check("checked after ON", checked(page, "server-checkbox") is True,
                  page.inner_text("#readout-checkbox"))
            posts.clear()
            click(page, "server-checkbox")
            page.wait_for_timeout(600)
            print(f"    POST on uncheck: {(posts[0] if posts else '<none>')!r}")
            check("STAYS unchecked after OFF",
                  checked(page, "server-checkbox") is False,
                  page.inner_text("#readout-checkbox"))
            check("server reads accepted = False",
                  "False" in page.inner_text("#readout-checkbox"),
                  page.inner_text("#readout-checkbox"))

            # ── 3. client-bound Switch (non-regression) ───────────────
            print("\n3. client-bound Switch (non-regression)")
            has_vals = page.eval_on_selector(
                "#client-switch", "el => el.hasAttribute('hx-vals')"
            )
            check("client switch has NO hx-vals injected", has_vals is False)
            click(page, "client-switch")
            page.wait_for_timeout(150)
            check("checked after ON", checked(page, "client-switch") is True)
            click(page, "client-switch")
            page.wait_for_timeout(200)
            check("STAYS unchecked after OFF (no snap-back)",
                  checked(page, "client-switch") is False)

            page.screenshot(path=str(HERE / "switch_server_screenshot.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"SWITCH-SERVER PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("SWITCH-SERVER PROBE PASSED — server toggles stay OFF, client unaffected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
