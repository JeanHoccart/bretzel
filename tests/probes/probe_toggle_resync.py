"""Playwright probe — ToggleGroup value adopted on @refreshable swap.

Drives bench_toggle_resync.py (:8973). Clicks a server button that
mutates the bound value + refreshes the panel ; the selected toggle must
follow to the NEW server value (it currently sticks to the old one
because the group's ``picked`` scope signal has no ``_serverSync``).

Run :  py tests/probes/probe_toggle_resync.py
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
    # Le détail n'est montré qu'en ROUGE : ici il est rédigé comme un
    # diagnostic d'échec (« stuck on old value »), donc l'afficher sur un
    # PASS faisait lire « PASS — resync bug » à chaque ligne verte.
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
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
    raise RuntimeError("toggle bench never came up on :8973")


def selected(page, gid):
    """La valeur du bouton à ``data-selected="true"`` — ``None`` si aucun.

    ⚠️ Elle se lit sur ``value=``, pas sur ``data-toggle-id`` : ce
    dernier appartenait à l'indicateur glissant, **retiré**, et
    ``test_toggle_group.py`` affirme depuis son absence. Le probe le
    lisait encore : chaque groupe rendait donc ``None``, et les cinq
    assertions accusaient un « resync bug » qu'elles ne mesuraient pas.
    """
    return page.evaluate(
        """(gid) => {
          const g = document.querySelector('#' + gid);
          if (!g) return '(groupe introuvable : ' + gid + ')';
          const b = g.querySelector('button[data-selected="true"]');
          return b ? b.getAttribute('value') : null;
        }""",
        gid,
    )


def main():
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_toggle_resync.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 700, "height": 700})
            errs = []
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")
            page.wait_for_timeout(80)

            print("\nInitial SSR selection")
            check("single starts 'active'", selected(page, "tg-single") == "active",
                  str(selected(page, "tg-single")))
            check("multi starts 'active'", selected(page, "tg-multi") == "active",
                  str(selected(page, "tg-multi")))

            print("\nServer changes single -> done + refresh")
            page.click("#btn-single")
            page.wait_for_timeout(250)
            sel = selected(page, "tg-single")
            print(f"  single selected after server change : {sel}")
            check("single ADOPTS server 'done'", sel == "done",
                  f"got {sel} — stuck on old value (resync bug)")

            print("\nServer changes multi -> done + refresh")
            page.click("#btn-multi")
            page.wait_for_timeout(250)
            selm = selected(page, "tg-multi")
            print(f"  multi (list field) selected after server change : {selm}")
            check("multi (list field) ADOPTS server 'done'", selm == "done",
                  f"got {selm} — stuck on old value (resync bug)")
            # The wrapped-scalar group rides Srv.single (changed by btn-single).
            selw = selected(page, "tg-wrap")
            print(f"  multi (wrapped scalar) selected : {selw}")
            check("multi (wrapped [scalar]) ADOPTS server 'done'", selw == "done",
                  f"got {selw} — stuck on old value (resync bug)")

            check("no JS console errors", not errs, "; ".join(errs[:5]))
            page.screenshot(path=str(HERE / "toggle_resync_screenshot.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"TOGGLE RESYNC PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("TOGGLE RESYNC PROBE PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
