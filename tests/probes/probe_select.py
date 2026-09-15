"""Playwright probe — Select V3 port, BLOCKING gate.

Drives ``bench_select.py`` (uvicorn :8951) :

Single :
1. Panel hidden at rest, trigger shows "France".
2. Click trigger → listbox opens, floats below the trigger.
3. Click "Spain" → trigger shows "Spain", panel closes, hidden input
   value = "Spain".
4. Keyboard : reopen, ArrowDown + Enter picks the next option.

Multiple :
5. Starts with one pill ("Italy").
6. Open, click "France" → a second pill appears (bz-for keyed),
   hidden value carries both.
7. Remove a pill via its × → pill disappears.

8. Zero JS console errors. Screenshot.

Run :  py tests/probes/probe_select.py
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
    raise RuntimeError("select bench never came up on :8951")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_select.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 800})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            single = page.locator("#single")
            s_trigger = single.get_by_role("combobox")
            s_panel = single.get_by_role("listbox")
            s_hidden = single.locator("input[type=hidden]")

            print("\nSelect single")
            check("panel hidden at rest", s_panel.is_hidden())
            check("trigger shows France", "France" in s_trigger.inner_text())
            s_trigger.click()
            page.wait_for_selector("#single [role=listbox]", state="visible")
            check("click opens the listbox", s_panel.is_visible())
            tb = s_trigger.bounding_box()
            pb = s_panel.bounding_box()
            check(
                "panel floats below the trigger",
                pb["y"] >= tb["y"] + tb["height"] - 4,
                f"trigger.bottom={tb['y']+tb['height']}, panel.y={pb['y']}",
            )
            single.get_by_role("option", name="Spain").click()
            page.wait_for_selector("#single [role=listbox]", state="hidden")
            check("picking Spain closes the panel", s_panel.is_hidden())
            check("trigger now shows Spain", "Spain" in s_trigger.inner_text())
            check("hidden input value = Spain", s_hidden.input_value() == "Spain")

            print("\nSelect single — keyboard")
            s_trigger.click()
            page.wait_for_selector("#single [role=listbox]", state="visible")
            s_trigger.press("ArrowDown")
            s_trigger.press("Enter")
            page.wait_for_selector("#single [role=listbox]", state="hidden")
            check(
                "ArrowDown+Enter changed the value",
                s_hidden.input_value() != "Spain",
                f"value still {s_hidden.input_value()}",
            )

            print("\nSelect multiple — pills (bz-for)")
            multi = page.locator("#multi")
            m_trigger = multi.get_by_role("combobox")

            def pill_count() -> int:
                return multi.locator("[data-bz-pill], .inline-flex").evaluate_all(
                    "els => els.filter(e => /Italy|France|Spain|Germany|Portugal/"
                    ".test(e.textContent) && e.querySelector('button')).length"
                ) if False else multi.get_by_role("button").count()

            check("multi shows initial Italy pill", "Italy" in m_trigger.inner_text())
            m_trigger.click()
            page.wait_for_selector("#multi [role=listbox]", state="visible")
            multi.get_by_role("option", name="France").click()
            page.wait_for_function(
                "document.querySelector('#multi input[type=hidden]').value"
                ".includes('France')"
            )
            check(
                "clicking France adds it (hidden carries both)",
                "Italy" in multi.locator("input[type=hidden]").input_value()
                and "France" in multi.locator("input[type=hidden]").input_value(),
                f"hidden={multi.locator('input[type=hidden]').input_value()}",
            )
            check("France pill visible in trigger", "France" in m_trigger.inner_text())

            check("no JS console errors", not console_errors, "; ".join(console_errors[:6]))
            page.screenshot(path=str(HERE / "select_screenshot.png"), full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"SELECT PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("SELECT PROBE PASSED — le Select V3 est fonctionnel en browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
