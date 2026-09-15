"""Playwright probe — Slider factory refactor preserves behaviour.

Drives ``bench_slider.py`` (uvicorn :8965). Confirms the shared
``$bz.slider.scope`` factory behaves like the old inline scope :
keyboard nudge + step snap + clamp, range two-handle, ClientBinding
sync. Reads ``aria-valuenow`` on each handle (role=slider).

Run :  py tests/probes/probe_slider.py
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
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
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
    raise RuntimeError("slider bench never came up on :8965")


def handles(page, sid):
    return page.query_selector_all(f"#{sid} [role=slider]")


def valuenow(handle):
    return handle.get_attribute("aria-valuenow")


def main():
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_slider.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 700, "height": 700})
            errs = []
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            print("\nFactory wiring")
            bd = page.eval_on_selector("#sl-single", "el => el.getAttribute('bz-data')")
            check("bz-data spreads $bz.slider.scope", "$bz.slider.scope" in bd)
            check("bz-data lean (not inlined)", len(bd) < 360, f"len={len(bd)}")
            check("$bz.slider.scope exists", page.evaluate("() => !!(window.$bz && $bz.slider && $bz.slider.scope)"))

            print("\nSingle — keyboard nudge + clamp + step")
            h = handles(page, "sl-single")
            check("one handle", len(h) == 1, str(len(h)))
            h[0].focus()
            check("starts at 50", valuenow(h[0]) == "50", valuenow(h[0]))
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(60)
            check("ArrowRight → 60 (step 10)", valuenow(h[0]) == "60", valuenow(h[0]))
            for _ in range(10):
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(20)
            check("clamps at max 100", valuenow(h[0]) == "100", valuenow(h[0]))
            page.keyboard.press("Home")
            page.wait_for_timeout(60)
            check("Home → min 0", valuenow(h[0]) == "0", valuenow(h[0]))

            print("\nRange — two handles, start ≤ end")
            r = handles(page, "sl-range")
            check("two handles", len(r) == 2, str(len(r)))
            check("start=20 end=80", valuenow(r[0]) == "20" and valuenow(r[1]) == "80",
                  f"{valuenow(r[0])},{valuenow(r[1])}")
            r[0].focus()
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(60)
            check("start handle ArrowRight → 25 (step 5)", valuenow(r[0]) == "25", valuenow(r[0]))

            print("\nClientBinding sync")
            bh = handles(page, "sl-bound")
            check("bound starts at 40", valuenow(bh[0]) == "40", valuenow(bh[0]))
            bh[0].focus()
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(80)
            check("bound handle → 50", valuenow(bh[0]) == "50", valuenow(bh[0]))
            check("bound readout reflects store (50)",
                  "50" in page.inner_text("#bound-readout"),
                  page.inner_text("#bound-readout"))

            check("no JS console errors", not errs, "; ".join(errs[:5]))
            page.screenshot(path=str(HERE / "slider_factory_screenshot.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"SLIDER PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("SLIDER PROBE PASSED — factory behaves identically (single/range/bound).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
