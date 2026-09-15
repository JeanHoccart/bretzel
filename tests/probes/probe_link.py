"""Playwright probe — Link hit-area is the text, not the whole row.

Drives ``bench_link.py`` (uvicorn :8960). The bug : a Link as a direct
child of a vstack stretches to full column width (flex ``align-items:
stretch``), so the entire row is clickable. Asserts each ``<a>`` is only
as wide as its text, and that a point far to the right of the text (but
on the same row) does NOT resolve to the link.

Run :  py tests/probes/probe_link.py
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
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
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
    raise RuntimeError("link bench never came up on :8960")


def measure(page, lid: str):
    return page.evaluate(
        """(lid) => {
            const a = document.getElementById(lid);
            const r = document.createRange();
            r.selectNodeContents(a);
            const text = r.getBoundingClientRect();
            const box = a.getBoundingClientRect();
            // A point on the link's row, far to the right of the text.
            const x = box.right + 80;
            const y = box.top + box.height / 2;
            const hit = document.elementFromPoint(x, y);
            return {
                boxLeft: box.left, boxRight: box.right, boxWidth: box.width,
                textWidth: text.width,
                rightHitIsLink: !!(hit && (hit === a || a.contains(hit))),
                x, y,
            };
        }""",
        lid,
    )


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_link.py"), str(PORT)],
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
                lambda m: console_errors.append(m.text) if m.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            print("\nLink hit-area = text width, not the row")
            for lid in ("lnk-1", "lnk-2", "lnk-3"):
                m = measure(page, lid)
                # The <a> box should hug its text (a little slack for
                # padding / focus-ring rounding), NOT span the column.
                check(f"{lid}: box width ≈ text width",
                      m["boxWidth"] <= m["textWidth"] + 12,
                      f"box {m['boxWidth']:.0f} vs text {m['textWidth']:.0f}")
                # A click 80px right of the text must NOT hit the link.
                check(f"{lid}: far-right point is NOT the link",
                      m["rightHitIsLink"] is False,
                      f"elementFromPoint at x={m['x']:.0f} resolved to the link")

            # ── Disabled : hover OFF, cursor not-allowed ──────────────
            print("\nDisabled link — hover neutralised, cursor not-allowed")

            def deco_on_hover(lid: str) -> str:
                page.hover(f"#{lid}")
                page.wait_for_timeout(80)
                return page.eval_on_selector(
                    f"#{lid}",
                    "el => getComputedStyle(el).textDecorationLine",
                )

            def cursor_of(lid: str) -> str:
                return page.eval_on_selector(
                    f"#{lid}", "el => getComputedStyle(el).cursor"
                )

            # Enabled control : hover DOES underline (so we know the
            # variant's hover effect is live and the probe is meaningful).
            check("enabled link underlines on hover",
                  "underline" in deco_on_hover("lnk-enabled"),
                  deco_on_hover("lnk-enabled"))
            # Disabled hover variant : no underline on hover.
            check("disabled link does NOT underline on hover",
                  "underline" not in deco_on_hover("lnk-disabled"),
                  deco_on_hover("lnk-disabled"))
            # Disabled keeps the not-allowed cursor (the whole point).
            check("disabled link cursor is not-allowed",
                  cursor_of("lnk-disabled") == "not-allowed",
                  cursor_of("lnk-disabled"))
            check("disabled text-variant cursor is not-allowed",
                  cursor_of("lnk-disabled-text") == "not-allowed",
                  cursor_of("lnk-disabled-text"))

            page.mouse.move(5, 5)
            page.screenshot(path=str(HERE / "link_screenshot.png"))
            check("no JS console errors", not console_errors,
                  "; ".join(console_errors[:6]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"LINK PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("LINK PROBE PASSED — hit-area hugs the text, row is not clickable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
