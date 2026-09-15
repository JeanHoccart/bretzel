"""Playwright probe — Calendar + DatePicker V3, BLOCKING gate.

Drives ``bench_calendar.py`` (uvicorn :8953) :

Calendar (custom element grid) :
1. <bz-calendar> renders a day grid (>=28 day cells).
2. June 2026 shown in the header.
3. Clicking a day selects it (the hidden input value updates).
4. Next-month arrow advances the header to July 2026.

DatePicker :
5. Popover hidden at rest, input shows the ISO value.
6. Click input → calendar popover opens, floats.
7. Pick a day → popover closes, input + hidden value update.

8. Zero JS console errors. Screenshot.

Run :  py tests/probes/probe_calendar.py
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
    raise RuntimeError("calendar bench never came up on :8953")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_calendar.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 900})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")
            # The custom element renders async — wait for day cells.
            page.wait_for_function(
                "document.querySelectorAll('#cal [data-bz-cal-day], #cal button')"
                ".length > 10"
            )

            print("\nCalendar (custom element)")
            cal = page.locator("#cal")
            # Day cells : the custom element renders buttons with day numbers.
            day_cells = cal.locator("button").evaluate_all(
                "els => els.filter(e => /^\\d{1,2}$/.test(e.textContent.trim())).length"
            )
            check("renders a day grid (>=28 day cells)", day_cells >= 28,
                  f"day cells={day_cells}")
            header_txt = cal.inner_text()
            check("June 2026 in header", "June" in header_txt and "2026" in header_txt,
                  f"header has: {[w for w in header_txt.split() if w][:6]}")

            # The standalone calendar exposes its value via the
            # <bz-calendar value="..."> observed attribute.
            cal.get_by_role("button", name="20", exact=True).first.click()
            page.wait_for_function(
                "document.querySelector('#cal').getAttribute('value') === '2026-06-20'"
            )
            check("clicking day 20 updates the value", True)

            cal.get_by_role("button", name="Next month").click()
            page.wait_for_function(
                "/July/.test(document.querySelector('#cal').textContent)"
            )
            check("next-month advances to July 2026", "July" in cal.inner_text())

            print("\nDatePicker popover")
            picker = page.locator("#picker")
            p_input = picker.locator("input:not([type=hidden])").first
            p_hidden = picker.locator("input[type=hidden][name=d]")
            check("input shows the ISO value", "2026-06-15" in p_input.input_value())
            check(
                "calendar popover hidden at rest",
                picker.locator("bz-calendar").evaluate(
                    "el => el.offsetParent === null"
                ),
            )
            # The chevron trigger button (last button) opens the popover.
            picker.get_by_role("button").last.click()
            page.wait_for_function(
                "document.querySelector('#picker bz-calendar').offsetParent !== null"
            )
            check("clicking the trigger opens the calendar", True)
            picker.get_by_role("button", name="22", exact=True).first.click()
            page.wait_for_function(
                "document.querySelector('#picker input[type=hidden]').value"
                ".includes('2026-06-22')"
            )
            check("picking day 22 updates the hidden value",
                  "2026-06-22" in p_hidden.input_value(),
                  f"value={p_hidden.input_value()}")

            check("no JS console errors", not console_errors, "; ".join(console_errors[:6]))
            page.screenshot(path=str(HERE / "calendar_screenshot.png"), full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"CALENDAR PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("CALENDAR PROBE PASSED — Calendar + DatePicker V3 fonctionnels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
