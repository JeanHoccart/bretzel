"""Playwright probe — server value adopted by bound inputs on refresh.

Drives ``bench_value_resync.py`` (uvicorn :8970). Two things :

A. ``htmx.config.historyCacheSize === 0`` — htmx read the ``<meta
   name=htmx-config>`` the shell emits, so big pages no longer blow the
   localStorage quota (``htmx:historyCacheError``).

B. After a SEPARATE button mutates every server var and refreshes the
   panel, each bound input REFLECTS the new server value (was stale :
   ``absorb`` skipped the existing signal). Read via the component's own
   scope proxy (the canonical signal) + the user-visible DOM where it's
   observable (number_input ``<input>.value``, select trigger label).

Run :  py tests/probes/probe_value_resync.py
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
    raise RuntimeError("value-resync bench never came up on :8970")


def scope_value(page, cid):
    """The component's canonical value signal, via its scope proxy."""
    return page.eval_on_selector(
        f"#{cid}", "el => window.$bz._scopeFor(el).proxy.value"
    )


def main():
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_value_resync.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 900})
            errs = []
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            # ── A. htmx history cache disabled (Fix A) ────────────────
            print("\nA. htmx history cache")
            hcs = page.evaluate("window.htmx && window.htmx.config.historyCacheSize")
            check("htmx.config.historyCacheSize === 0 (meta read)", hcs == 0, repr(hcs))
            meta = page.evaluate(
                "document.querySelector('meta[name=htmx-config]') && "
                "document.querySelector('meta[name=htmx-config]').content"
            )
            check("meta htmx-config present", meta == '{"historyCacheSize":0}', repr(meta))

            # ── B. initial values ─────────────────────────────────────
            print("\nB. initial (server) values")
            ni0 = page.eval_on_selector("#ni input", "el => el.value")
            check("number_input shows 7", ni0 == "7", ni0)
            check("slider value signal = 30", scope_value(page, "sl") == 30, scope_value(page, "sl"))
            check("select value signal = Apple", scope_value(page, "se") == "Apple", scope_value(page, "se"))
            check("select trigger shows Apple", "Apple" in page.inner_text("#se"), page.inner_text("#se"))
            check("combobox value signal = alpha", scope_value(page, "cb") == "alpha", scope_value(page, "cb"))

            # ── B. mutate server-side + refresh ───────────────────────
            print("\nB. after 'Set server values + refresh'")
            page.eval_on_selector("#set-btn", "el => el.click()")
            page.wait_for_function(
                "document.getElementById('bump') && "
                "document.getElementById('bump').textContent.indexOf('= 1') !== -1"
            )
            page.wait_for_timeout(150)  # let the resync + bz-attr effects settle

            ni1 = page.eval_on_selector("#ni input", "el => el.value")
            check("number_input ADOPTED 42 (input.value)", ni1 == "42", ni1)
            check("number_input value signal = 42", scope_value(page, "ni") == 42, scope_value(page, "ni"))

            check("slider ADOPTED 80", scope_value(page, "sl") == 80, scope_value(page, "sl"))

            check("select ADOPTED Cherry (signal)", scope_value(page, "se") == "Cherry", scope_value(page, "se"))
            check("select trigger shows Cherry", "Cherry" in page.inner_text("#se"), page.inner_text("#se"))

            check("combobox ADOPTED gamma", scope_value(page, "cb") == "gamma", scope_value(page, "cb"))

            check("no console errors", not errs, "; ".join(errs[:4]))

            page.screenshot(path=str(HERE / "value_resync_screenshot.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"VALUE-RESYNC PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("VALUE-RESYNC PROBE PASSED — server values adopted on refresh, htmx cache off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
