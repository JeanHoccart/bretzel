"""Playwright probe — overlays never exceed a phone viewport. BLOCKING gate.

Drives ``bench_mobile_overflow.py`` (uvicorn :8995) in a real Chromium and,
for every ``width=`` step of Drawer (x4 sides) and Dialog, asserts :

1. the panel is no wider than the viewport ;
2. the panel is no taller than the viewport ;
3. the panel is fully on screen (no edge past a viewport border) ;
4. the document grows no horizontal scrollbar while it is open.

This is the *containment* invariant : whatever the dev asks for, a component
never breaks out of the screen. It is a framework guarantee, not an app-code
responsibility.

Two viewports, because the two axes fail for DIFFERENT reasons and a single
portrait pass gives a false green :

- **portrait 375x667** — the width axis. Left/right panels are flex items, so
  ``flex-shrink`` hides a hard ``w-96`` behind a clean-looking pass. Add one
  unbreakable token (the ``*-wide`` triggers) and ``min-width: auto`` blocks
  the shrink : the panel overflows, and *silently*, since a ``fixed`` subtree
  grows no document scrollbar.
- **landscape 667x375** — the height axis. Shrink does not apply on the cross
  axis at all, so ``lg``/``xl`` top/bottom drawers (384/512px) simply run off
  screen. A ``bottom`` one puts its header — and its close button — above the
  top edge, leaving no way to close it.

Run :  py tests/probes/probe_mobile_overflow.py
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
WIDTHS = ("sm", "md", "lg", "xl", "full")
SIDES = ("left", "right", "top", "bottom")
# Sub-pixel slack : layout rounding can hand back 375.0000001.
SLACK = 1.0

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
    raise RuntimeError("mobile-overflow bench never came up on :8995")


def sweep(browser, vw: int, vh: int, triggers: list[tuple[str, str]], label: str) -> None:
    """Open each trigger at ``vw x vh`` and assert the panel stays on screen."""
    print(f"\n{label} — viewport {vw}x{vh}")
    page = browser.new_page(viewport={"width": vw, "height": vh})
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(BASE + "/")
    page.wait_for_selector("html.bz-ready")

    for trigger_id, name in triggers:
        page.click(f"#{trigger_id}")
        panel = page.locator('[role="dialog"]:visible')
        panel.wait_for(state="visible", timeout=3000)
        # Let the slide/scale transition settle before measuring. 600ms,
        # not the 300ms transition : Playwright first scrolls the trigger
        # into view (the bench stacks ~46 of them), and that scroll eats
        # into the budget — at 400ms the panel was still mid-translate.
        page.wait_for_timeout(600)

        box = panel.bounding_box()
        if box is None:
            check(f"{name} measurable", False, "no bounding box")
            continue

        check(
            f"{name} fits viewport",
            box["width"] <= vw + SLACK and box["height"] <= vh + SLACK,
            f"panel {box['width']:.0f}x{box['height']:.0f} > viewport {vw}x{vh}",
        )
        rect = panel.evaluate(
            "el => {const r = el.getBoundingClientRect();"
            " return {top: r.top, left: r.left, right: r.right, bottom: r.bottom};}"
        )
        offscreen = [
            f"{edge}={rect[edge]:.0f}"
            for edge, bad in (
                ("top", rect["top"] < -SLACK),
                ("left", rect["left"] < -SLACK),
                ("right", rect["right"] > vw + SLACK),
                ("bottom", rect["bottom"] > vh + SLACK),
            )
            if bad
        ]
        check(
            f"{name} fully on screen",
            not offscreen,
            "edges off screen: " + ", ".join(offscreen),
        )
        over = page.evaluate(
            "() => document.documentElement.scrollWidth"
            " - document.documentElement.clientWidth"
        )
        check(
            f"{name} no horizontal scrollbar",
            over <= SLACK,
            f"document overflows by {over}px",
        )

        page.keyboard.press("Escape")
        page.wait_for_timeout(400)

    check(f"{label}: zero JS console errors", not errors, "; ".join(errors[:3]))
    page.close()


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_mobile_overflow.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    all_overlays = (
        [(f"drawer-{s}-{w}", f"drawer {s}/{w}") for s in SIDES for w in WIDTHS]
        + [(f"dialog-{w}", f"dialog {w}") for w in WIDTHS]
        + [("drawer-wide", "drawer md + wide content"), ("dialog-wide", "dialog md + wide content")]
    )
    # Landscape only needs the panels whose height is the free axis, plus
    # the wide-content pair (cheap, and it exercises both axes at once).
    landscape = [
        (f"drawer-{s}-{w}", f"drawer {s}/{w}") for s in ("top", "bottom") for w in WIDTHS
    ] + [("drawer-wide", "drawer md + wide content")]

    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            sweep(browser, 375, 667, all_overlays, "Portrait")
            sweep(browser, 667, 375, landscape, "Landscape")

            # Worst offender of each axis, kept as the eyeball artefact.
            # ``HERE / *.png`` is the repo convention (and what .gitignore
            # covers) — no subdirectory.
            for vw, vh, trigger, shot in (
                (667, 375, "drawer-bottom-xl", "mobile_overflow_landscape_screenshot.png"),
                (375, 667, "drawer-wide", "mobile_overflow_wide_screenshot.png"),
            ):
                page = browser.new_page(viewport={"width": vw, "height": vh})
                page.goto(BASE + "/")
                page.wait_for_selector("html.bz-ready")
                page.click(f"#{trigger}")
                page.wait_for_timeout(900)
                page.screenshot(path=str(HERE / shot))
                page.close()
                print(f"\nScreenshot → {HERE / shot}")

            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S)")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
