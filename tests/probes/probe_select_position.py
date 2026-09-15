"""Playwright probe — Select panel positioning, BLOCKING gate.

Drives ``bench_select_position.py`` (uvicorn :8957). Targets the two
bugs the user reported on the V3 Select :

1. The open panel is roughly trigger-width and left-aligned to the
   trigger — NOT stretched to the viewport's right edge.
2. The panel does not drift left ; its left edge tracks the trigger's
   left edge (within a few px) both at rest AND after a page scroll.

Run :  py tests/probes/probe_select_position.py
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
    raise RuntimeError("select-position bench never came up on :8957")


def rects(page, root_id: str):
    """Return (trigger_rect, panel_rect, viewport_width) for a Select."""
    return page.evaluate(
        """(rootId) => {
            const root = document.getElementById(rootId);
            const trigger = root.querySelector('[role=combobox]');
            const panel = root.querySelector('[role=listbox]');
            const t = trigger.getBoundingClientRect();
            const p = panel.getBoundingClientRect();
            return {
                trigger: {left: t.left, right: t.right, width: t.width,
                          top: t.top, bottom: t.bottom},
                panel: {left: p.left, right: p.right, width: p.width,
                        top: p.top},
                vw: window.innerWidth,
            };
        }""",
        root_id,
    )


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_select_position.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1000, "height": 760})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            # ── Open the size select ──────────────────────────────────
            print("\nAt rest — panel alignment + width")
            trigger = page.locator("#size-select [role=combobox]")
            trigger.click()
            page.wait_for_selector("#size-select [role=listbox]", state="visible")
            page.wait_for_timeout(120)  # let floating() settle

            m = rects(page, "size-select")
            tw = m["trigger"]["width"]
            pw_ = m["panel"]["width"]

            # 1. Panel RIGHT edge pins to the trigger's right edge
            #    (bottom-end : starts at the right, grows leftward).
            dr = abs(m["panel"]["right"] - m["trigger"]["right"])
            check("panel right-aligns with the trigger (≤ 4px)", dr <= 4,
                  f"|panel.right {m['panel']['right']:.0f} - trigger.right "
                  f"{m['trigger']['right']:.0f}| = {dr:.0f}px")

            # 2. Panel is AT LEAST the trigger width (matchWidth floor),
            #    and not stretched to the viewport edge.
            check("panel is at least the trigger width (matchWidth floor)",
                  pw_ >= tw - 1,
                  f"panel {pw_:.0f} vs trigger {tw:.0f}")
            check("panel is NOT stretched toward the viewport's right edge",
                  m["panel"]["right"] < m["vw"] - 100,
                  f"panel.right {m['panel']['right']:.0f}, vw {m['vw']}")

            # 3. Panel sits just below the trigger.
            check("panel opens below the trigger",
                  m["panel"]["top"] >= m["trigger"]["bottom"] - 1,
                  f"panel.top {m['panel']['top']:.0f}, "
                  f"trigger.bottom {m['trigger']['bottom']:.0f}")

            page.screenshot(path=str(HERE / "select_position_screenshot.png"))

            # ── Scroll, panel must keep tracking ──────────────────────
            print("\nAfter scroll — panel still tracks the trigger")
            page.mouse.wheel(0, 160)
            page.wait_for_timeout(150)
            m2 = rects(page, "size-select")
            dr2 = abs(m2["panel"]["right"] - m2["trigger"]["right"])
            check("after scroll, panel right still tracks trigger (≤ 4px)",
                  dr2 <= 4,
                  f"|panel.right {m2['panel']['right']:.0f} - trigger.right "
                  f"{m2['trigger']['right']:.0f}| = {dr2:.0f}px")
            check("after scroll, panel width unchanged (no stretch)",
                  abs(m2["panel"]["width"] - pw_) <= 6,
                  f"panel {m2['panel']['width']:.0f} vs initial {pw_:.0f}")
            check("after scroll, panel follows the trigger vertically",
                  abs(m2["panel"]["top"] - m2["trigger"]["bottom"]) <= 14,
                  f"panel.top {m2['panel']['top']:.0f}, "
                  f"trigger.bottom {m2['trigger']['bottom']:.0f}")

            check("no JS console errors", not console_errors,
                  "; ".join(console_errors[:6]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"SELECT-POSITION PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("SELECT-POSITION PROBE PASSED — panel aligned, trigger-width, scroll-tracked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
