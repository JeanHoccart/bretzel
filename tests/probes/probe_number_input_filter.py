"""Playwright probe — number_input filter + clean on_change (:8994).

Verifies the two bugs the user hit are fixed :

1. Typing letters into the number field : they never appear (the
   ``beforeinput`` keystroke filter rejects any char outside ``[0-9.-]``)
   — the field stays numeric.
2. ``on_change`` (pushing ``$event.target.value``) logs the COMMITTED
   value, not the raw typed text, and fires ONCE per commit (no native +
   synthetic double-fire — observers ride the private ``bzchange``).

Run :  py tests/probes/probe_number_input_filter.py
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


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def main():
    srv = subprocess.Popen(
        [sys.executable, str(HERE / "bench_number_input_filter.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                urllib.request.urlopen(BASE + "/", timeout=1)
                break
            except OSError:
                time.sleep(0.3)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 800, "height": 600})
            errs = []
            page.on("console",
                    lambda m: errs.append(m.text) if m.type == "error" else None)
            page.goto(BASE + "/")
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )

            inp = page.locator("#ni input")

            # ── Case 1 : type digits interleaved with letters ────────
            inp.click()
            page.keyboard.press("Control+A")
            page.type("#ni input", "4102aaaa")
            typed = inp.input_value()
            check("letters never appear in the field (beforeinput filter)",
                  typed == "4102", f"field shows {typed!r}")

            # blur (Tab) → commit → fires on_change once with the clean
            # value. NB: a body click does NOT reliably blur in headless
            # Chromium — Tab moves focus off the input deterministically.
            page.keyboard.press("Tab")
            page.wait_for_timeout(150)
            log = page.locator("#log").inner_text()
            count = page.locator("#count").inner_text()
            check("on_change logs the committed value, not the raw text",
                  log == "4102", f"log = {log!r}")
            check("on_change fires exactly once per commit (no double-fire)",
                  count == "1", f"count = {count}")

            # ── Case 2 : a second clean edit appends one entry ───────
            inp.click()
            page.keyboard.press("Control+A")
            page.type("#ni input", "37")
            page.keyboard.press("Tab")
            page.wait_for_timeout(150)
            log2 = page.locator("#log").inner_text()
            count2 = page.locator("#count").inner_text()
            check("second commit appends the clean value",
                  log2 == "4102 | 37", f"log = {log2!r}")
            check("still one fire per commit", count2 == "2", f"count = {count2}")

            # ── Case 3 : the decimal point passes the filter ─────────
            inp.click()
            page.keyboard.press("Control+A")
            page.type("#ni input", "3.5x")  # the 'x' must be rejected
            typed3 = inp.input_value()
            check("decimal point allowed, trailing letter rejected",
                  typed3 == "3.5", f"field shows {typed3!r}")
            page.keyboard.press("Tab")
            page.wait_for_timeout(150)
            log3 = page.locator("#log").inner_text()
            check("decimal commit appends clean value",
                  log3 == "4102 | 37 | 3.5", f"log = {log3!r}")

            check("no JS console errors", not errs, "; ".join(errs[:5]))
            page.screenshot(path=str(HERE / "number_input_filter.png"))
            print("  screenshot → number_input_filter.png")
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)

    print()
    if FAILURES:
        print(f"NUMBER_INPUT FILTER PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("NUMBER_INPUT FILTER PROBE PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
