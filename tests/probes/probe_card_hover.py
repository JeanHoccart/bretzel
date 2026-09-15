"""Playwright probe — hoverable Card actually lifts on hover.

Drives ``bench_card_hover.py`` (uvicorn :8962). Reads the computed
``top`` at rest vs on hover. Two regressions guarded :

1. ``aria-enabled:`` gating meant the lift never compiled (mai 2026).
2. The lift MUST stay a position offset (``relative top-0
   hover:-top-0.5``) and never go back to ``translate`` : a transform
   makes the card the containing block of its descendants' ``fixed``
   overlay panels — a Select inside a hoverable card then opened 477px
   below its trigger. Cf. traps.md § « Hover lift en translate »
   (2026-07-15). Hence ``is_lifted`` reads ``top``, and
   ``no_transform`` asserts the transform stays absent.

Run :  py tests/probes/probe_card_hover.py
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
    raise RuntimeError("card-hover bench never came up on :8962")


def lift_of(page, cid):
    # The lift is a position offset : read ``top``. ``translate`` /
    # ``transform`` are read too — they must stay 'none' (a transform
    # would create a containing block for fixed overlay panels).
    return page.eval_on_selector(
        f"#{cid}",
        "el => { const s = getComputedStyle(el); "
        "return s.top + ' | ' + s.translate + ' | ' + s.transform; }",
    )


def main():
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_card_hover.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1100, "height": 600})
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            # "lifted" = the CSS ``top`` property is negative
            # (``hover:-top-0.5`` → "-2px"). At rest it is "0px" ; on a
            # non-positioned (static) card it is "auto".
            def is_lifted(combined: str) -> bool:
                top = combined.split(" | ")[0].strip()
                return top.startswith("-")

            # A transform of ANY kind on the card re-introduces the
            # containing-block bug — assert it never comes back.
            def has_transform(combined: str) -> bool:
                _, translate, transform = (p.strip() for p in combined.split(" | "))
                return translate not in ("none", "") or transform not in ("none", "")

            def hover_state(cid):
                page.mouse.move(5, 5)
                page.wait_for_timeout(60)
                rest = lift_of(page, cid)
                page.hover(f"#{cid}")
                page.wait_for_timeout(250)  # transition
                hov = lift_of(page, cid)
                return rest, hov

            print("\nHoverable card lifts on hover")
            rest, hov = hover_state("hover-card")
            check("at rest, no lift", not is_lifted(rest), rest)
            check("on hover, a negative top is applied", is_lifted(hov),
                  f"rest={rest} hover={hov}")
            check("the lift is NOT a transform (containing-block bug)",
                  not has_transform(hov), f"hover={hov}")

            print("\nLocked (aria-disabled) card does NOT lift")
            _, h2 = hover_state("locked-card")
            check("locked card stays put on hover", not is_lifted(h2),
                  f"hover top={h2}")

            print("\nStatic card never lifts")
            _, h3 = hover_state("static-card")
            check("static card stays put on hover", not is_lifted(h3), h3)

            page.screenshot(path=str(HERE / "card_hover_screenshot.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"CARD-HOVER PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("CARD-HOVER PROBE PASSED — hoverable lifts, locked/static don't.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
