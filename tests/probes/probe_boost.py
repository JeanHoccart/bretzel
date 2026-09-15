"""Playwright probe — automatic hx-boost + bridge URL-clean (:8976).

Clicks a plain internal content link and asserts :
  - the outlet content swapped (Page A → Page B),
  - the sidebar DOM node PERSISTED (a JS property survives → no full
    reload, the shell stayed mounted),
  - the URL was pushed to /b with NO client-state query params, even
    after toggling ColorScheme (the bridge POST-only fix).

Run :  py tests/probes/probe_boost.py
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
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
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
    raise RuntimeError("boost bench never came up on :8976")


def main():
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_boost.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 700})
            errs = []
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            page.goto(BASE + "/")
            # The outlet starts display:none until the runtime reveals it,
            # so wait on the ready CLASS (not visibility) + the reveal.
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )
            page.wait_for_timeout(300)

            check("starts on Page A", "Page A" in page.inner_text("h1"))

            # Mark the sidebar DOM node with a JS property — survives only
            # if the sidebar isn't re-rendered (partial nav keeps it).
            page.evaluate(
                "document.querySelector('a[href=\"/b\"]').__probeKept = true"
            )
            # Toggle the theme → ColorScheme.default.mode lands in the store.
            page.click("button:has(iconify-icon[icon='lucide:moon'])")
            page.wait_for_timeout(100)

            # Click the PLAIN content link (no hx-* of its own) — only the
            # document hx-boost should turn it into an outlet swap.
            page.click("a[href='/b'] >> text=Go to B")
            page.wait_for_timeout(500)

            print("\nAfter boosted nav to /b")
            check("outlet swapped to Page B", "Page B" in page.inner_text("h1"),
                  page.inner_text("h1"))
            kept = page.evaluate(
                "document.querySelector('a[href=\"/b\"]') && "
                "document.querySelector('a[href=\"/b\"]').__probeKept === true"
            )
            check("sidebar PERSISTED (no full reload)", kept is True, str(kept))
            url = page.url
            print(f"  URL = {url}")
            check("URL pushed to /b", url.endswith("/b"), url)
            check("URL CLEAN — no client-state leak", "?" not in url
                  and "ColorScheme" not in url, url)

            check("no JS console errors", not errs, "; ".join(errs[:5]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"BOOST PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("BOOST PROBE PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
