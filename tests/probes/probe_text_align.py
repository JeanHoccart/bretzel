"""Playwright probe — Text ``align=`` actually moves the glyphs.

Drives ``bench_text_align.py`` (uvicorn :8958). Measures the REAL
position of the rendered text (a DOM ``Range`` over the span's text
node, not just the class string) inside the playground's centred flex
wrapper, and asserts :

- ``align='left'``  → glyphs hug the row's left edge
- ``align='right'`` → glyphs hug the row's right edge
- ``align='center'``→ glyphs centred in the row
- left vs right differ by most of the row width (the bug was "no
  visual change" — every align looked identical / centred)

Run :  py tests/probes/probe_text_align.py
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
    raise RuntimeError("text-align bench never came up on :8958")


def glyph_box(page, align: str):
    """Range rect of the span's text + the wrapping row's rect."""
    return page.evaluate(
        """(align) => {
            const span = document.getElementById('t-' + align);
            const row = document.getElementById('row-' + align);
            const range = document.createRange();
            range.selectNodeContents(span);
            const t = range.getBoundingClientRect();
            const c = row.getBoundingClientRect();
            return {
                textLeft: t.left, textRight: t.right,
                contLeft: c.left, contRight: c.right, contWidth: c.width,
            };
        }""",
        align,
    )


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_text_align.py"), str(PORT)],
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

            left = glyph_box(page, "left")
            center = glyph_box(page, "center")
            right = glyph_box(page, "right")

            print("\nGlyph position vs row")
            # Left-aligned text hugs the row's left edge.
            check("align=left → text at the row's left edge",
                  abs(left["textLeft"] - left["contLeft"]) <= 8,
                  f"textLeft {left['textLeft']:.0f}, contLeft {left['contLeft']:.0f}")
            # Right-aligned text hugs the row's right edge.
            check("align=right → text at the row's right edge",
                  abs(right["textRight"] - right["contRight"]) <= 8,
                  f"textRight {right['textRight']:.0f}, contRight {right['contRight']:.0f}")
            # Centre-aligned text sits mid-row.
            c_mid = (center["textLeft"] + center["textRight"]) / 2
            row_mid = (center["contLeft"] + center["contRight"]) / 2
            check("align=center → text centred in the row",
                  abs(c_mid - row_mid) <= 8,
                  f"text mid {c_mid:.0f}, row mid {row_mid:.0f}")

            # The bug was "no visual change" : left and right must now
            # differ by most of the row width.
            spread = right["textLeft"] - left["textLeft"]
            check("left vs right differ by most of the row width",
                  spread > left["contWidth"] * 0.5,
                  f"spread {spread:.0f}px of {left['contWidth']:.0f}px row")

            page.screenshot(path=str(HERE / "text_align_screenshot.png"))
            check("no JS console errors", not console_errors,
                  "; ".join(console_errors[:6]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"TEXT-ALIGN PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("TEXT-ALIGN PROBE PASSED — align= moves the glyphs (left/center/right).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
