"""Playwright probe — Notification V3 port, BLOCKING gate.

Drives ``bench_notification.py`` (uvicorn :8955) :

1. No toast at rest.
2. Click "Fire success" → a server action runs ui.notification(...),
   the <bz-patch> -> bz:notify -> toaster path materialises a toast in
   the top-right stack with the title + message.
3. Auto-dismiss : a 4s toast disappears on its own.
4. Click "Fire error" (persistent, bottom-right) → toast in the
   bottom-right stack ; its × dismiss button removes it.
5. Zero JS console errors. Screenshot with a toast visible.

Run :  py tests/probes/probe_notification.py
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
    raise RuntimeError("notification bench never came up on :8955")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_notification.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1000, "height": 700})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            def toast_count() -> int:
                return page.locator('[role="status"]').count()

            print("\nNotification")
            check("no toast at rest", toast_count() == 0)

            # 1. server action → toast appears
            page.click("#btn-success")
            page.wait_for_selector('[role="status"]', state="visible", timeout=8000)
            toast = page.locator('[role="status"]').first
            check("server ui.notification() materialises a toast", toast.is_visible())
            check(
                "toast carries the title + message",
                "Done" in toast.inner_text() and "Saved successfully" in toast.inner_text(),
                f"toast text: {toast.inner_text()!r}",
            )
            page.screenshot(path=str(HERE / "notification_screenshot.png"))

            # 2. auto-dismiss after 4s (default duration)
            page.wait_for_selector('[role="status"]', state="detached", timeout=8000)
            check("4s toast auto-dismisses", toast_count() == 0)

            # 3. persistent error toast + manual dismiss
            page.click("#btn-error")
            page.wait_for_selector('[role="status"]', state="visible", timeout=8000)
            err_toast = page.locator('[role="status"]').first
            check("error toast appears (bottom-right)", err_toast.is_visible())
            # stays past 4s (persistent)
            page.wait_for_timeout(1200)
            check("persistent toast still there after 1.2s", toast_count() == 1)
            err_toast.get_by_role("button", name="Dismiss notification").click()
            page.wait_for_selector('[role="status"]', state="detached", timeout=4000)
            check("× dismiss removes the persistent toast", toast_count() == 0)

            check("no JS console errors", not console_errors, "; ".join(console_errors[:6]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"NOTIFICATION PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("NOTIFICATION PROBE PASSED — le Notification V3 est fonctionnel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
