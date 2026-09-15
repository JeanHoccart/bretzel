"""Playwright probe — Dialog V3 port, BLOCKING gate.

Drives ``bench_dialog.py`` (uvicorn :8946) in a real Chromium :

1. Closed at rest : panel display:none (pre-stamp + bz-show).
2. ``dlg.open()`` trigger → panel + backdrop visible.
3. Scroll lock engaged while open, released on close.
4. Focus trap : focus lands INSIDE the panel, Tab cycles inside.
5. Escape closes (dismissible default).
6. Backdrop click closes.
7. Close via ``dlg.close()`` button.
8. Persistent dialog : escape + backdrop DON'T close, button does.
9. Zero JS console errors. Screenshot of the open state.

Run :  py tests/probes/probe_dialog.py
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from tests.probes._serve import free_port
from playwright.sync_api import sync_playwright

from tests.probes._overlay import overlay_state, wait_overlay

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
    raise RuntimeError("dialog bench never came up on :8946")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_dialog.py"), str(PORT)],
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
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")


            def panel_display() -> str:
                """L'état du dialog — via ``data-open``, pas via ``display``.

                Un modal garde ``display: flex`` fermé (il part en
                ``visibility: hidden ; opacity: 0``), donc ce contrôle
                était vrai au repos et faux à l'ouverture. Cf.
                ``_overlay.overlay_state``.
                """
                return overlay_state(page, '[role="dialog"]')

            def body_overflow() -> str:
                return page.evaluate("getComputedStyle(document.body).overflow")

            print("\nDialog — lifecycle de base")
            check("panel hidden at rest", panel_display() == "closed")
            check("body scroll free at rest", body_overflow() != "hidden")

            page.click("#trigger")
            page.wait_for_selector('[role="dialog"]', state="visible")
            check("open() → panel visible", panel_display() != "none")
            check("scroll locked while open", body_overflow() == "hidden")
            # Le focus initial arrive à la DEUXIÈME frame — avant, les
            # boutons du panneau sont encore en ``visibility: hidden`` et
            # ``focus()`` y est un no-op (mesuré : caché à +1 ms, visible à
            # +16 ms). On l'attend donc au lieu de l'échantillonner : le
            # contrat est « le focus atterrit », pas « il atterrit dans le
            # même tick ».
            focus_inside = "() => document.querySelector('[role=\"dialog\"]')"                            ".contains(document.activeElement)"
            with contextlib.suppress(PlaywrightTimeout):
                page.wait_for_function(focus_inside, timeout=2000)
            check("focus trapped inside the panel", page.evaluate(focus_inside),
                  page.evaluate(
                      "() => { const a = document.activeElement;"
                      "  const d = document.querySelector('[role=\"dialog\"]');"
                      "  return 'actif=' + (a ? a.tagName + '/' +"
                      "    (a.getAttribute('aria-label') || (a.textContent||'').trim().slice(0,12)) : 'aucun')"
                      "    + ' visibilité1erFocusable=' + (() => { const f = d.querySelector("
                      "      'a[href],button:not([disabled]),input:not([disabled])');"
                      "      return f ? getComputedStyle(f).visibility : 'aucun'; })(); }"))
            for _ in range(6):
                page.keyboard.press("Tab")
            check(
                "Tab x6 stays inside the panel",
                page.evaluate(
                    "document.querySelector('[role=\"dialog\"]')"
                    ".contains(document.activeElement)"
                ),
            )
            page.screenshot(path=str(HERE / "dialog_screenshot.png"))

            print("\nDialog — fermetures")
            page.keyboard.press("Escape")
            page.wait_for_selector('[role="dialog"]', state="hidden")
            check("Escape closes", panel_display() == "closed")
            check("scroll released after close", body_overflow() != "hidden")

            page.click("#trigger")
            page.wait_for_selector('[role="dialog"]', state="visible")
            # Backdrop is the first child of the dialog root — click a
            # corner far from the centered panel.
            page.mouse.click(5, 5)
            page.wait_for_selector('[role="dialog"]', state="hidden")
            check("backdrop click closes", panel_display() == "closed")

            page.click("#trigger")
            page.wait_for_selector('[role="dialog"]', state="visible")
            page.get_by_role("button", name="Cancel").click()
            page.wait_for_selector('[role="dialog"]', state="hidden")
            check("close() button closes", panel_display() == "closed")

            print("\nDialog persistent")
            page.click("#trigger-persistent")
            check("persistent s'ouvre",
                  wait_overlay(page, '[role="dialog"]', "open", index=1) == "open")
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
            check("persistent ignores Escape",
                  overlay_state(page, '[role="dialog"]', 1) == "open")
            page.mouse.click(5, 5)
            page.wait_for_timeout(150)
            check("persistent ignores backdrop click",
                  overlay_state(page, '[role="dialog"]', 1) == "open")
            page.click("#stubborn-close")
            check("persistent closes via close()",
                  wait_overlay(page, '[role="dialog"]', "closed", index=1) == "closed")

            check("no JS console errors", not console_errors, "; ".join(console_errors[:5]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"DIALOG PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("DIALOG PROBE PASSED — le Dialog V3 est fonctionnel en browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
