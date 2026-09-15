"""Playwright probe — responsive ``{breakpoint: value}`` props. BLOCKING gate.

Drives ``bench_responsive_props.py`` (uvicorn :8996) and reads
``getComputedStyle`` at three widths, because serializing ``md:flex-row``
proves only that Python built a string : it says nothing about Tailwind
compiling the variant or the browser flipping at 768px.

Checked at 375 / 800 / 1400 px :

1. ``direction={"base": "col", "md": "row"}`` → column below md, row from
   md up ;
2. ``gap={"base": "sm", "md": "xl"}`` → 8px below md, 32px from md up ;
3. a SCALAR ``direction=``/``gap=`` never moves (the dict path must not
   leak into the plain path) ;
4. ``grid(cols=…)`` flips its template column count the same way ;
5. ``vstack`` inherits the responsive gap at its own breakpoint (lg).

Run :  py tests/probes/probe_responsive_props.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from bretzel.theme import DEFAULT_SPACING_PX

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
    raise RuntimeError("responsive-props bench never came up on :8996")


def style(page, selector: str, prop: str) -> str:
    return page.evaluate(
        "([sel, prop]) => getComputedStyle(document.querySelector(sel))[prop]",
        [selector, prop],
    )


def px(crans: int) -> str:
    """La valeur CSS d'un nombre de crans, telle que le navigateur la rend.

    ``gap-2`` vaut deux crans : 8 px sur l'échelle de Tailwind, 6 px sur
    celle de Bretzel. Lire le jeton plutôt que recopier le résultat est ce
    qui empêche ces attentes de repérimer au prochain réglage de densité.
    """
    return f"{crans * DEFAULT_SPACING_PX}px"


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_responsive_props.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # ⚠️ Les écarts se DÉRIVENT du pas d'espacement du thème, ils ne
    # s'écrivent pas. Ils étaient en dur — 8, 16, 32 px, c'est-à-dire
    # l'échelle de Tailwind — et le jour où Bretzel a choisi la sienne
    # (3 px le cran, 2026-09-13) ces quatre nombres sont devenus faux
    # d'un coup. Le SUJET de ce probe est qu'un écart CHANGE avec le
    # palier de fenêtre, pas sa valeur absolue.
    #
    # width → (flex-direction, flex gap, grid template count, vstack gap)
    EXPECTED = {
        375: ("column", px(2), 1, "0px"),
        800: ("row", px(8), 3, "0px"),
        1400: ("row", px(8), 3, px(8)),
    }
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            errors: list[str] = []
            for width, (direction, gap, cols, vgap) in EXPECTED.items():
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.on(
                    "console",
                    lambda m: errors.append(m.text) if m.type == "error" else None,
                )
                page.goto(BASE + "/")
                page.wait_for_selector("html.bz-ready")
                # Tailwind compiles in the browser in dev mode — give the
                # JIT a beat to emit the sheet before reading computed style.
                page.wait_for_timeout(600)

                print(f"\nViewport {width}px")

                got = style(page, "#flex-responsive", "flexDirection")
                check(f"{width}px flex direction", got == direction, f"{got!r} != {direction!r}")

                got = style(page, "#flex-responsive", "columnGap")
                check(f"{width}px flex gap", got == gap, f"{got!r} != {gap!r}")

                # Scalar control : identical at every width.
                got = style(page, "#flex-scalar", "flexDirection")
                check(f"{width}px scalar direction pinned", got == "row", f"{got!r} != 'row'")
                got = style(page, "#flex-scalar", "columnGap")
                check(f"{width}px scalar gap pinned", got == px(4),
                      f"{got!r} != {px(4)!r}")

                got = style(page, "#grid-responsive", "gridTemplateColumns")
                n = len(got.split())
                check(f"{width}px grid column count", n == cols, f"{n} tracks ({got}) != {cols}")

                got = style(page, "#vstack-responsive", "rowGap")
                check(f"{width}px vstack gap", got == vgap, f"{got!r} != {vgap!r}")

                if width == 375:
                    page.screenshot(path=str(HERE / "responsive_props_mobile_screenshot.png"))
                elif width == 1400:
                    page.screenshot(path=str(HERE / "responsive_props_desktop_screenshot.png"))
                page.close()

            print("\nConsole")
            check("zero JS console errors", not errors, "; ".join(errors[:3]))
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
