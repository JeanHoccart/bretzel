"""Playwright probe — Drawer V3 port, BLOCKING gate.

Drives ``bench_drawer.py`` (uvicorn :8947) in a real Chromium :

1. All four drawers hidden at rest.
2. Each side opens via ``drw.open()`` and the panel is GEOMETRICALLY
   anchored to its edge (left x≈0, right x+w≈viewport, top y≈0,
   bottom y+h≈viewport) — catches CSS side-table regressions that
   string assertions can't.
3. Scroll lock + focus trap while open.
4. Escape / backdrop click / ``drw.close()`` button all close.
5. Zero JS console errors. Screenshot of the left drawer open.

Run :  py tests/probes/probe_drawer.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from tests.probes._serve import free_port

from tests.probes._overlay import overlay_state, wait_overlay

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"
SIDES = ("left", "right", "top", "bottom")

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
    raise RuntimeError("drawer bench never came up on :8947")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_drawer.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            def panel(idx: int):
                return page.locator('[role="dialog"]').nth(idx)

            def settled_box(idx: int, predicate, tries: int = 25):
                """La boîte du panneau une fois le GLISSEMENT terminé.

                Le tiroir entre en translation : mesurée juste après le
                passage à « ouvert », sa boîte est encore hors écran
                (relevé : ``x=1280`` pour un tiroir droit large de 384 sur
                un viewport de 1280). Le contrat est « il FINIT ancré »,
                pas « il l'est au premier tick » — on laisse la transition
                se poser, en s'arrêtant dès que c'est vrai.
                """
                box = panel(idx).bounding_box()
                for _ in range(tries):
                    if box and predicate(box):
                        return box
                    page.wait_for_timeout(40)
                    box = panel(idx).bounding_box()
                return box

            print("\nDrawers — au repos")
            check(
                "4 panels hidden at rest",
                all(overlay_state(page, '[role="dialog"]', k) == "closed"
                    for k in range(4)),
                str([overlay_state(page, '[role="dialog"]', k) for k in range(4)]),
            )

            print("\nDrawers — ancrage par côté")
            for idx, side in enumerate(SIDES):
                page.click(f"#trigger-{side}")
                # Un modal ne se ferme pas en ``display`` : il garde
                # ``display: flex`` et part en ``visibility: hidden``. Le
                # test sur ``display`` était donc vrai AU REPOS (on
                # n'attendait rien) et jamais vrai à la fermeture (30 s de
                # timeout, puis une stacktrace). Cf. ``_overlay``.
                check(f"{side} ouvert",
                      wait_overlay(page, '[role="dialog"]', "open",
                                   index=idx) == "open")
                if side == "left":
                    def at_edge(b): return b["x"] <= 1
                elif side == "right":
                    def at_edge(b): return abs((b["x"] + b["width"]) - 1280) <= 1
                elif side == "top":
                    def at_edge(b): return b["y"] <= 1
                else:
                    def at_edge(b): return abs((b["y"] + b["height"]) - 720) <= 1
                box = settled_box(idx, at_edge)
                anchored = bool(box) and at_edge(box)
                check(f"{side} panel anchored to its edge", anchored, f"box: {box}")
                if side == "left":
                    check(
                        "scroll locked while open",
                        page.evaluate("getComputedStyle(document.body).overflow")
                        == "hidden",
                    )
                    # Le focus initial arrive quand le panneau devient
                    # focusable, pas dans le tick de l'ouverture : on
                    # l'attend (cf. ``helpers.focusTrap``).
                    inside = "el => el.contains(document.activeElement)"
                    for _ in range(25):
                        if panel(idx).evaluate(inside):
                            break
                        page.wait_for_timeout(40)
                    check("focus trapped inside the panel",
                          panel(idx).evaluate(inside))
                    page.screenshot(path=str(HERE / "drawer_screenshot.png"))
                # Close each via its own mechanism, rotating coverage.
                if side == "left":
                    page.keyboard.press("Escape")
                elif side == "right":
                    page.mouse.click(15, 700)  # backdrop, far from the panel
                else:
                    page.get_by_role("button", name=f"Close {side}").click()
                check(f"{side} closed (escape/backdrop/button rotation)",
                      wait_overlay(page, '[role="dialog"]', "closed",
                                   index=idx) == "closed")

            check(
                "scroll released after close",
                page.evaluate("getComputedStyle(document.body).overflow") != "hidden",
            )
            check("no JS console errors", not console_errors, "; ".join(console_errors[:5]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"DRAWER PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("DRAWER PROBE PASSED — le Drawer V3 est fonctionnel en browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
