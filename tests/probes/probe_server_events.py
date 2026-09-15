"""Playwright probe — Switch + RadioGroup server-event bugs (:8972).

Reproduces (then, after the fix, guards) :
 1. a LOCAL switch resets to false after its on_change refreshes the panel.
 2. a bound RadioGroup's on_change reaches the handler with an EMPTY value.

Reads ground truth from the bench's /calls endpoint (what the handlers
actually received) + the live DOM (switch .checked) + intercepted POST
bodies.

Run :  py tests/probes/probe_server_events.py
"""

from __future__ import annotations

import json
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


def wait_server(timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("server-events bench never came up on :8972")


def get_calls():
    with urllib.request.urlopen(BASE + "/calls", timeout=2) as r:
        return json.loads(r.read().decode())


def main():
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_server_events.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 600, "height": 800})
            errs = []
            posts = []
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            page.on("request", lambda r: posts.append((r.url, r.post_data))
                    if r.method == "POST" else None)
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")
            page.wait_for_timeout(80)

            # ── 1. Local switch keeps its checked state across refresh ──
            print("\nLocal switch — survives its own on_change refresh")
            started = page.evaluate("() => document.querySelector('#sw-local').checked")
            check("switch starts unchecked", started is False)
            # Click the switch's label (the checkbox is sr-only) to toggle.
            page.evaluate("() => document.querySelector('#sw-local').click()")
            page.wait_for_timeout(300)
            checked_after = page.evaluate("() => document.querySelector('#sw-local').checked")
            print(f"  switch .checked after change+refresh : {checked_after}")
            check("switch STAYS checked after refresh", checked_after is True,
                  "snapped back to false (the bug)" if checked_after is False else "")

            # ── 2. Bound radio group on_change carries the picked value ──
            print("\nBound radio group — on_change carries the picked value")
            page.click("#rg-bound label:has-text('B')")
            page.wait_for_timeout(250)
            calls = get_calls()
            radio_calls = [c for c in calls if c.get("which") == "radio_change"]
            print(f"  radio_change calls : {radio_calls}")
            check("radio_change fired", len(radio_calls) >= 1, str(calls))
            if radio_calls:
                form = radio_calls[-1].get("form", {})
                picked = next((v for v in form.values() if v), "")
                print(f"  handler received form={form} → picked={picked!r}")
                check("picked value is 'b' (NOT empty)", picked == "b",
                      f"got {picked!r} — empty-value bug")

            # ── 3. Whole simple family persists across its own refresh ──
            print("\nSimple family (checkbox / input / textarea) survives refresh")
            # Checkbox : toggle on → on_change refreshes panel.
            cb_before = page.evaluate("() => document.querySelector('#cb-local').checked")
            page.evaluate("() => document.querySelector('#cb-local').click()")
            page.wait_for_timeout(250)
            cb_after = page.evaluate("() => document.querySelector('#cb-local').checked")
            check("checkbox stays checked after refresh", cb_after is True,
                  f"before={cb_before} after={cb_after}")

            # Input : type + blur (fires change → refresh) → value kept.
            page.fill("#in-local", "hello")
            page.evaluate("() => document.querySelector('#in-local').blur()")
            page.wait_for_timeout(250)
            in_after = page.evaluate("() => document.querySelector('#in-local').value")
            check("input keeps typed text after refresh", in_after == "hello",
                  f"got {in_after!r}")

            # Textarea : type + blur → value kept.
            page.fill("#ta-local", "multi\nline")
            page.evaluate("() => document.querySelector('#ta-local').blur()")
            page.wait_for_timeout(250)
            ta_after = page.evaluate("() => document.querySelector('#ta-local').value")
            check("textarea keeps typed text after refresh", ta_after == "multi\nline",
                  f"got {ta_after!r}")

            # POST bodies (diagnostic).
            print("\n  POST bodies seen :")
            for url, body in posts[-4:]:
                print(f"    {url.split('/')[-1] or url} :: {body}")

            check("no JS console errors", not errs, "; ".join(errs[:5]))
            page.screenshot(path=str(HERE / "server_events_screenshot.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"SERVER-EVENTS PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("SERVER-EVENTS PROBE PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
