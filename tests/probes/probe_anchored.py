"""Playwright probe — anchored overlays V3 (Popover/Dropdown/Tooltip).

BLOCKING gate. Drives ``bench_anchored.py`` (uvicorn :8949) :

Popover :
1. Panel hidden at rest.
2. Trigger click opens it ; panel floats BELOW the trigger (geometry).
3. Click outside closes it.
4. Re-open, Escape closes it.

Dropdown :
5. Menu opens on trigger click.
6. Clicking an item closes the menu (bz-dropdown-pick).

Tooltip :
7. Hidden at rest, appears on hover, teleported under <body>,
   positioned near the trigger.
8. Disappears on mouse-leave.

9. Zero JS console errors. Screenshot of the open popover.

Run :  py tests/probes/probe_anchored.py
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
    raise RuntimeError("anchored bench never came up on :8949")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_anchored.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            # ── Popover ────────────────────────────────────────────────
            print("\nPopover")
            pop_panel = page.locator('[role="dialog"]').first
            check("popover hidden at rest", pop_panel.is_hidden())
            page.click("#pop-trigger")
            page.wait_for_selector('[role="dialog"]', state="visible")
            check("trigger opens popover", pop_panel.is_visible())
            trig_box = page.locator("#pop-trigger").bounding_box()
            panel_box = pop_panel.bounding_box()
            check(
                "panel floats below the trigger",
                panel_box["y"] >= trig_box["y"] + trig_box["height"] - 2,
                f"trigger.bottom={trig_box['y']+trig_box['height']}, panel.y={panel_box['y']}",
            )
            page.screenshot(path=str(HERE / "anchored_screenshot.png"))
            page.mouse.click(1000, 800)  # far outside
            page.wait_for_selector('[role="dialog"]', state="hidden")
            check("click outside closes popover", pop_panel.is_hidden())
            page.click("#pop-trigger")
            page.wait_for_selector('[role="dialog"]', state="visible")
            page.keyboard.press("Escape")
            page.wait_for_selector('[role="dialog"]', state="hidden")
            check("Escape closes popover", pop_panel.is_hidden())

            # ── Dropdown ───────────────────────────────────────────────
            print("\nDropdown")
            menu = page.locator('[role="menu"]').first
            check("menu hidden at rest", menu.is_hidden())
            page.click("#dd-trigger")
            page.wait_for_selector('[role="menu"]', state="visible")
            check("trigger opens menu", menu.is_visible())
            page.click("#dd-edit")
            page.wait_for_selector('[role="menu"]', state="hidden")
            check("picking an item closes the menu", menu.is_hidden())

            # ── Tooltip ────────────────────────────────────────────────
            print("\nTooltip")
            tip = page.locator('[role="tooltip"]').first
            check("tooltip hidden at rest", tip.is_hidden())
            check(
                "tooltip teleported under <body>",
                tip.evaluate("el => el.parentElement === document.body"),
            )
            page.hover("#tip-trigger")
            page.wait_for_selector('[role="tooltip"]', state="visible")
            check("tooltip appears on hover", tip.is_visible())
            tip_box = tip.bounding_box()
            trig_box = page.locator("#tip-trigger").bounding_box()
            check(
                "tooltip positioned near the trigger",
                abs(tip_box["y"] - (trig_box["y"] + trig_box["height"])) < 40,
                f"trigger.bottom={trig_box['y']+trig_box['height']}, tip.y={tip_box['y']}",
            )
            page.mouse.move(1200, 50)  # leave the trigger
            page.wait_for_selector('[role="tooltip"]', state="hidden")
            check("tooltip disappears on mouse-leave", tip.is_hidden())

            check("no JS console errors", not console_errors, "; ".join(console_errors[:5]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"ANCHORED PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("ANCHORED PROBE PASSED — Popover/Dropdown/Tooltip V3 fonctionnels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
