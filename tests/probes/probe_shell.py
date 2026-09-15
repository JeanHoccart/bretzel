"""Playwright probe — V3 runtime on the REAL Bretzel shell, END TO END.

Serves ``tests.e2e.apps.counter_app:app`` (uvicorn, port 8944) and checks
the full pipeline → shell → runtime.js → emission V3 :

Boot :
1. Page served, ``<bz-envelope>`` tag present in the document.
2. ``html.bz-ready`` set → 00_index.js bootstrap completed.
3. ``window.$bz.version`` matches the protocol.
4. Envelope hydration : ``$bz.state.MemoryCounter.default.count`` === 0.
5. ``#bz-sink`` mounted, Alpine NOT loaded (V3 has none).

Interactivity (the V3 emission chantier) :
6. Client row (ClientState memory) : « + » mutates the signal via
   ``bz-on:click``, the ``bz-text`` display follows — ZERO POST.
7. Server row (module variable) : « + » fires ``hx-post`` with the
   HMAC sig header, the refreshable swaps back via OOB morph.
8. Zero JS console errors throughout.

⚠️ **L'hôte a changé le 2026-09-10.** Ce probe servait
``examples/counter``, supprimé ce jour-là : son contenu — le tableau
des sept portées — est déjà enseigné par la doc vivante
(``state_server.py``, ``state_client.py``), et un tableau comparatif
n'est pas une mécanique mise en scène.

Il pointe maintenant la fixture POSSÉDÉE par les tests, qui porte la
même forme à sept lignes. C'est le même argument que
``tests/e2e/conftest.py`` écrit depuis le 2026-08-16 : une démo est
de la documentation, elle doit rester libre de changer pour des
raisons de démo, et un test du framework qui casse quand une démo
s'améliore ne dit rien du framework.

Run :  py tests/probes/probe_shell.py
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
REPO = HERE.parent.parent
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
    raise RuntimeError("counter app never came up on :8944")


def main() -> int:
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "tests.e2e.apps.counter_app:app",
            "--host", "127.0.0.1", "--port", str(PORT),
        ],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )

            page.goto(BASE + "/")
            print("\nShell réel + runtime V3 — boot")
            page.wait_for_selector("html.bz-ready", timeout=15000)
            check("html.bz-ready set (bootstrap completed)", True)
            check(
                "bz-envelope tag in document",
                page.evaluate("!!document.querySelector('bz-envelope')"),
            )
            check(
                "$bz.version is v1.0",
                page.evaluate("window.$bz && window.$bz.version") == "v1.0",
                f"got: {page.evaluate('window.$bz && window.$bz.version')}",
            )
            check(
                "envelope hydrated $bz.state (MemoryCounter.count=0)",
                page.evaluate("window.$bz.state.MemoryCounter.default.count") == 0,
                f"got: {page.evaluate('window.$bz.state.MemoryCounter.default.count')}",
            )
            check(
                "signal store writable ($bz.state round-trip)",
                page.evaluate(
                    "($bz.state.MemoryCounter.default.count = 7,"
                    " $bz.state.MemoryCounter.default.count)"
                ) == 7,
            )
            # Reset the probe's own pollution before the interactivity
            # scenario asserts on fresh values.
            page.evaluate("$bz.state.MemoryCounter.default.count = 0")
            check("#bz-sink mounted", page.evaluate("!!document.getElementById('bz-sink')"))
            check(
                "Alpine absent (V3 has none)",
                page.evaluate("typeof window.Alpine === 'undefined'"),
            )
            check(
                "persistence adapter live (localStorage $bz:LocalCounter)",
                page.evaluate(
                    "($bz.state.LocalCounter.default.count = 3,"
                    " JSON.parse(localStorage.getItem('$bz:LocalCounter.default')).count)"
                ) == 3,
            )

            # ── Interactivity : client row (zero round-trip) ────────────
            print("\nRow client (ClientState memory) — bz-on + bz-text")
            action_posts: list[str] = []
            page.on(
                "request",
                lambda req: action_posts.append(req.url)
                if "/_bretzel/action/" in req.url
                else None,
            )
            mem_display = page.locator(
                '[bz-text="$bz.state.MemoryCounter.default.count"]'
            )
            check("bz-text display rendered", mem_display.count() == 1)
            check("initial value 0", page.evaluate(
                "document.querySelector("
                "'[bz-text=\"$bz.state.MemoryCounter.default.count\"]').textContent"
            ) == "0")
            mem_row = mem_display.locator(
                "xpath=ancestor::div[contains(@class,'flex-col')][1]"
            )
            mem_row.get_by_role("button", name="+").click()
            mem_row.get_by_role("button", name="+").click()
            page.wait_for_function(
                "document.querySelector("
                "'[bz-text=\"$bz.state.MemoryCounter.default.count\"]')"
                ".textContent === '2'"
            )
            check("two clicks → display 2 (signal → bz-text)", True)
            check(
                "ZERO POST serveur sur la row client",
                len(action_posts) == 0,
                f"posts: {action_posts}",
            )

            # ── Interactivity : server row (hx-post + OOB morph) ────────
            print("\nRow serveur (module variable) — hx-post + refreshable")
            mod_label = page.get_by_text("Module variable", exact=True)
            mod_row = mod_label.locator(
                "xpath=ancestor::div[contains(@class,'flex-col')][1]"
            )
            display_before = mod_row.locator("span.text-3xl").inner_text()
            check("server display starts at 0", display_before == "0")
            mod_row.get_by_role("button", name="+").click()
            page.wait_for_function(
                "[...document.querySelectorAll('span')].some("
                "s => s.classList.contains('text-3xl') && s.textContent === '1')"
            )
            check("click + → POST action → OOB morph → display 1", True)
            check(
                "exactly one action POST fired",
                len(action_posts) == 1,
                f"posts: {action_posts}",
            )
            mod_row.get_by_role("button", name="+").click()
            page.wait_for_function(
                "[...document.querySelectorAll('span')].some("
                "s => s.classList.contains('text-3xl') && s.textContent === '2')"
            )
            check("second click → display 2 (rebind after morph OK)", True)

            check("no JS console errors", not console_errors, "; ".join(console_errors[:5]))

            page.screenshot(path=str(HERE / "shell_screenshot.png"), full_page=False)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"SHELL PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("SHELL PROBE PASSED — le runtime V3 boote sur le vrai shell.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
