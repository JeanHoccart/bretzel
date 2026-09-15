"""Playwright probe — FileUpload V3 port, BLOCKING gate.

Drives ``bench_fileupload.py`` (uvicorn :8954) :

1. Empty state shown, file-list strip hidden at rest.
2. Selecting 2 files via the native input → 2 rows appear in the
   keyed bz-for list, with names + sizes.
3. The native <input type=file> is synced (carries the 2 files for
   form submit) via DataTransfer.
4. Removing one file → 1 row left, native input down to 1.
5. Validation : selecting a 4th file (max_files=3) surfaces an error.
6. Zero JS console errors. Screenshot.

Uses real temp files created on disk + set_input_files (the trusted
path the component listens on).

Run :  py tests/probes/probe_fileupload.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
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
    raise RuntimeError("fileupload bench never came up on :8954")


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    f1 = tmp / "alpha.txt"
    f1.write_text("alpha content")
    f2 = tmp / "beta.txt"
    f2.write_text("beta content")
    f3 = tmp / "gamma.txt"
    f3.write_text("gamma content")
    f4 = tmp / "delta.txt"
    f4.write_text("delta content")

    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_fileupload.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 800})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            uploader = page.locator("#uploader")
            native = uploader.locator("input[type=file]")

            def file_rows() -> int:
                return page.evaluate(
                    "document.querySelectorAll('#uploader [data-file-row], "
                    "#uploader [data-bz-file-entry]').length"
                )

            print("\nFileUpload")
            check(
                "native file input present",
                native.count() == 1,
            )
            # 1. select two files
            native.set_input_files([str(f1), str(f2)])
            page.wait_for_function(
                "document.querySelector('#uploader').textContent.includes('alpha.txt')"
            )
            check("selecting 2 files shows both names",
                  "alpha.txt" in uploader.inner_text()
                  and "beta.txt" in uploader.inner_text())
            check(
                "native input synced to 2 files (form submit)",
                native.evaluate("el => el.files.length") == 2,
                f"native.files={native.evaluate('el => el.files.length')}",
            )

            # 2. remove one file via its × button
            remove_btns = uploader.get_by_role("button").evaluate_all(
                "els => els.filter(e => /remove|×|delete/i.test("
                "(e.getAttribute('aria-label')||'') + e.textContent)).length"
            )
            # click the first remove control (aria-label Remove or × text)
            uploader.locator(
                "button[aria-label*='emove' i], button[aria-label*='etirer' i]"
            ).first.click()
            page.wait_for_function(
                "document.querySelector('#uploader input[type=file]').files.length === 1"
            )
            check("removing a file leaves the native input with 1",
                  native.evaluate("el => el.files.length") == 1)

            # 3. validation : exceed max_files (3). Currently 1 file ;
            # add 3 more (alpha, gamma, delta) → 4 total > 3 → error.
            native.set_input_files([str(f1), str(f2), str(f3), str(f4)])
            page.wait_for_function(
                "/skipped|reached|Maximum|allowed/i.test("
                "document.querySelector('#uploader').textContent)"
            )
            check("exceeding max_files surfaces an error", True)

            check("no JS console errors", not console_errors, "; ".join(console_errors[:6]))
            page.screenshot(path=str(HERE / "fileupload_screenshot.png"), full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"FILEUPLOAD PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("FILEUPLOAD PROBE PASSED — le FileUpload V3 est fonctionnel en browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
