"""Playwright probe — Combobox change inside its own @refreshable (:8973).

Mirror of probe_select_events. Expected AFTER the fix :
1. Picking "banana" logs EXACTLY ONE ``change(value='banana')``.
2. No phantom ``change(value='')``.
3. The input keeps "banana" after the refresh (value not lost).
4. Zero JS console errors.

Run :  py tests/probes/probe_combobox_events.py
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
    raise RuntimeError("combobox-events bench never came up on :8973")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_combobox_events.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 700, "height": 700})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda m: console_errors.append(m.text) if m.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            cb = page.locator("#cb")
            inp = cb.locator("input:not([type=hidden])").first

            print("\nCombobox change inside its own @refreshable")
            inp.click()
            page.wait_for_selector("#cb [role=listbox]", state="visible")
            cb.get_by_role("option", name="banana").click()
            page.wait_for_timeout(700)

            log_lines = page.locator("#evlog .evt").all_inner_texts()
            print(f"  log = {log_lines!r}")
            change_events = [ln for ln in log_lines if "change(" in ln]
            check(
                "exactly one change event logged",
                len(change_events) == 1,
                f"got {len(change_events)}: {change_events}",
            )
            check(
                "the change carries value='banana'",
                any("value='banana'" in ln for ln in change_events),
                f"events={change_events}",
            )
            check(
                "no phantom change(value='')",
                not any("value=''" in ln for ln in log_lines),
                f"log={log_lines}",
            )
            check(
                "input still shows banana after refresh",
                "banana" in (inp.input_value() or ""),
                f"input={inp.input_value()!r}",
            )
            check("no JS console errors", not console_errors,
                  "; ".join(console_errors[:6]))
            page.screenshot(path=str(HERE / "combobox_events_screenshot.png"),
                            full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"COMBOBOX-EVENTS PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("COMBOBOX-EVENTS PROBE PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
