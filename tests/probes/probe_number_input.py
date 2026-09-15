"""Playwright probe — NumberInput factory refactor preserves behaviour.

Drives ``bench_number_input.py`` (uvicorn :8963). Confirms the shared
``$bz.numberInput.scope`` factory behaves identically to the old inline
scope : nudge via the steppers, clamp to min/max, step precision (no
float drift), and ClientBinding sync.

Run :  py tests/probes/probe_number_input.py
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
    raise RuntimeError("number-input bench never came up on :8963")


def val(page, nid):
    return page.eval_on_selector(f"#{nid} input", "el => el.value")


def click_btn(page, nid, label):
    page.eval_on_selector(
        f"#{nid} button[aria-label='{label}']", "el => el.click()"
    )
    page.wait_for_timeout(60)


def main():
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_number_input.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 700})
            errs = []
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            # factory present, scope NOT inlined
            print("\nFactory wiring")
            bd = page.eval_on_selector("#ni-basic", "el => el.getAttribute('bz-data')")
            check("bz-data spreads $bz.numberInput.scope", "$bz.numberInput.scope" in bd)
            check("bz-data is short (not inlined)", len(bd) < 400, f"len={len(bd)}")
            has_factory = page.evaluate("() => !!(window.$bz && $bz.numberInput && $bz.numberInput.scope)")
            check("$bz.numberInput.scope exists in runtime", has_factory)

            print("\nSteppers (nudge + clamp)")
            check("starts at 5", val(page, "ni-basic") == "5")
            click_btn(page, "ni-basic", "Increment")
            check("increment → 6", val(page, "ni-basic") == "6", val(page, "ni-basic"))
            for _ in range(10):
                click_btn(page, "ni-basic", "Increment")
            check("clamps at max 10", val(page, "ni-basic") == "10", val(page, "ni-basic"))
            for _ in range(20):
                click_btn(page, "ni-basic", "Decrement")
            check("clamps at min 0", val(page, "ni-basic") == "0", val(page, "ni-basic"))

            print("\nType + blur (commit + clamp)")
            page.click("#ni-basic input")
            page.keyboard.press("Control+a")
            page.keyboard.type("100")
            page.keyboard.press("Tab")  # blur via real focus change
            page.wait_for_timeout(120)
            check("typed 100 clamps to 10 on blur", val(page, "ni-basic") == "10", val(page, "ni-basic"))

            print("\nStep precision (no float drift)")
            for _ in range(3):
                click_btn(page, "ni-prec", "Increment")
            check("0 + 0.1×3 == 0.3 (not 0.30000000000000004)",
                  val(page, "ni-prec") == "0.3", val(page, "ni-prec"))

            print("\nClientBinding sync")
            check("bound starts at 3", val(page, "ni-bound") == "3")
            click_btn(page, "ni-bound", "Increment")
            check("bound input → 4", val(page, "ni-bound") == "4", val(page, "ni-bound"))
            # the bound readout text mirrors the store
            check("bound readout reflects store (4)",
                  "4" in page.inner_text("#bound-readout"),
                  page.inner_text("#bound-readout"))

            check("no JS console errors", not errs, "; ".join(errs[:5]))
            page.screenshot(path=str(HERE / "number_input_screenshot.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"NUMBER-INPUT PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("NUMBER-INPUT PROBE PASSED — factory behaves identically, HTML lean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
