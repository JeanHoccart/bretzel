"""Playwright probe — Combobox V3 port, BLOCKING gate.

Drives ``bench_combobox.py`` (uvicorn :8952) :

Single :
1. Panel hidden at rest.
2. Focus input → panel opens, floats below, options stacked vertically.
3. Type "sp" → only "Spain" matches (client filter via bz-show).
4. Click "Spain" → hidden value = "Spain", input reflects it, panel closes.
5. Keyboard : reopen, ArrowDown+Enter picks a row.

Multiple :
6. Starts with Italy pill.
7. Type "fr", pick "France" → second pill (bz-for keyed), hidden = both.

8. Zero JS console errors. Screenshot.

Run :  py tests/probes/probe_combobox.py
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
    raise RuntimeError("combobox bench never came up on :8952")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_combobox.py"), str(PORT)],
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
            s_panel = single.get_by_role("listbox")
            s_input = single.locator("input:not([type=hidden])").first
            s_hidden = single.locator("input[type=hidden][name=country]")

            print("\nCombobox single")
            check("panel hidden at rest", s_panel.is_hidden())
            s_input.click()
            page.wait_for_selector("#single [role=listbox]", state="visible")
            check("focus opens the panel", s_panel.is_visible())
            ib = s_input.bounding_box()
            pb = s_panel.bounding_box()
            check(
                "panel floats below the input",
                pb["y"] >= ib["y"] + ib["height"] - 6,
                f"input.bottom={ib['y']+ib['height']}, panel.y={pb['y']}",
            )
            # options stacked vertically (the Select bz-class bug guard)
            opt_w = single.get_by_role("option").first.bounding_box()["width"]
            check(
                "options span the panel width (stacked, not cramped)",
                opt_w > 150,
                f"first option width={opt_w}",
            )

            print("\nCombobox single — client filter")
            s_input.fill("sp")
            page.wait_for_function(
                "[...document.querySelectorAll('#single [role=option]')]"
                ".filter(o => o.offsetParent !== null).length === 1"
            )
            visible_opts = single.get_by_role("option").evaluate_all(
                "els => els.filter(e => e.offsetParent !== null).map(e => e.textContent.trim())"
            )
            check("typing 'sp' filters to Spain only", visible_opts == ["Spain"],
                  f"visible: {visible_opts}")
            single.get_by_role("option", name="Spain").click()
            page.wait_for_selector("#single [role=listbox]", state="hidden")
            check("picking Spain closes the panel", s_panel.is_hidden())
            check("hidden value = Spain", s_hidden.input_value() == "Spain")

            print("\nCombobox single — keyboard")
            s_input.click()
            page.wait_for_selector("#single [role=listbox]", state="visible")
            s_input.press("ArrowDown")
            s_input.press("Enter")
            page.wait_for_selector("#single [role=listbox]", state="hidden")
            check("ArrowDown+Enter picked a row", s_hidden.input_value() != "")

            print("\nCombobox multiple — filter + pills")
            multi = page.locator("#multi")
            m_input = multi.locator("input:not([type=hidden])").first
            m_hidden = multi.locator("input[type=hidden][name=countries]")
            check("multi starts with Italy", "Italy" in m_hidden.input_value())
            m_input.click()
            page.wait_for_selector("#multi [role=listbox]", state="visible")
            m_input.fill("fr")
            page.wait_for_function(
                "[...document.querySelectorAll('#multi [role=option]')]"
                ".filter(o => o.offsetParent !== null).length === 1"
            )
            multi.get_by_role("option", name="France").click()
            page.wait_for_function(
                "document.querySelector('#multi input[type=hidden][name=countries]')"
                ".value.includes('France')"
            )
            check(
                "picking France adds it (hidden carries both)",
                "Italy" in m_hidden.input_value() and "France" in m_hidden.input_value(),
                f"hidden={m_hidden.input_value()}",
            )

            check("no JS console errors", not console_errors, "; ".join(console_errors[:6]))
            page.screenshot(path=str(HERE / "combobox_screenshot.png"), full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"COMBOBOX PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("COMBOBOX PROBE PASSED — le Combobox V3 est fonctionnel en browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
