"""Playwright probe — batch-1 V3 ports, BLOCKING gate.

Drives ``bench_batch1.py`` (uvicorn :8948) in a real Chromium :

1. Alert : visible at rest, X dismisses it client-side (zero POST).
2. Checkbox : external ``chk.set(True)`` button checks the input.
3. Switch : external ``sw.toggle()`` flips it.
4. Input : ``inp.set("hello V3")`` fills, ``inp.clear()`` empties.
5. Progress : binding mutation moves the fill width and the percent
   text (bz-attr:style + bz-text reactivity).
6. Zero JS console errors, zero action POST (everything client-side).

Run :  py tests/probes/probe_batch1.py
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
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
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
    raise RuntimeError("batch1 bench never came up on :8948")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_batch1.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            action_posts: list[str] = []
            page.on(
                "request",
                lambda req: action_posts.append(req.url)
                if "/_bretzel/action/" in req.url
                else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            print("\nAlert — dismiss client-side")
            alert = page.locator("#bench-alert")
            check("alert visible at rest", alert.is_visible())
            alert.get_by_role("button").click()
            page.wait_for_selector("#bench-alert", state="hidden")
            check("X dismisses the alert", alert.is_hidden())

            print("\nCheckbox / Switch — imperative commands")
            chk = page.locator('input[type="checkbox"]').first
            check("checkbox unchecked at rest", not chk.is_checked())
            page.click("#btn-check")
            page.wait_for_function(
                "document.querySelector('input[type=checkbox]').checked === true"
            )
            check("chk.set(True) checks it", chk.is_checked())

            sw = page.locator('input[type="checkbox"]').nth(1)
            initial = sw.is_checked()
            page.click("#btn-toggle")
            page.wait_for_function(
                f"document.querySelectorAll('input[type=checkbox]')[1]"
                f".checked === {str(not initial).lower()}"
            )
            check("sw.toggle() flips it", sw.is_checked() != initial)

            print("\nInput — set / clear")
            inp = page.locator("#bench-input input, input#bench-input").first
            page.click("#btn-fill")
            page.wait_for_function(
                "[...document.querySelectorAll('input')].some("
                "i => i.value === 'hello V3')"
            )
            check("inp.set('hello V3') fills", True)
            page.click("#btn-clear")
            page.wait_for_function(
                "[...document.querySelectorAll('input')].every("
                "i => i.value !== 'hello V3')"
            )
            check("inp.clear() empties", True)

            print("\nProgress — binding reactivity")
            check(
                "fill width starts at 30%",
                page.evaluate(
                    "!![...document.querySelectorAll('[bz-attr\\\\:style]')]"
                    ".find(e => (e.getAttribute('style')||'').includes('30%'))"
                ),
            )
            page.click("#btn-pct")
            page.wait_for_function(
                "[...document.querySelectorAll('[bz-attr\\\\:style]')]"
                ".some(e => (e.getAttribute('style')||'').includes('80%'))"
            )
            check("binding.set(80) moves the fill width", True)
            check(
                "percent text follows via bz-text",
                page.evaluate(
                    "[...document.querySelectorAll('[bz-text]')]"
                    ".some(e => e.textContent.includes('80'))"
                ),
            )

            check("zero action POST (all client-side)", len(action_posts) == 0,
                  f"posts: {action_posts}")
            check("no JS console errors", not console_errors, "; ".join(console_errors[:5]))
            page.screenshot(path=str(HERE / "batch1_screenshot.png"), full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"BATCH1 PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("BATCH1 PROBE PASSED — les composants batch 1 sont fonctionnels en browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
