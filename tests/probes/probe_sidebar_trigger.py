"""Playwright probe — le declencheur RAMENE la barre a l'ecran.

Drives ``bench_sidebar_trigger.py`` (uvicorn :8976) dans un vrai Chromium,
en 375x667, sur la composition du finding [17] : cadre gele + barre en
``overlay`` fermee + ``ui.sidebar_trigger`` dans la barre du haut.

Pourquoi ce probe et pas une assertion de HTML
-----------------------------------------------
Parce que le defaut d'origine ETAIT invisible au HTML : la page rendait
200, l'``<aside>`` etait dans le document avec tous ses liens, et rien ne
disait qu'il etait a **x = -256**. Trois mesures, dans l'ordre ou elles
comptent :

1. **au chargement**, la barre est hors ecran ET aucun de ses liens n'est
   atteignable — c'est l'etat de depart, celui qui avait rendu six des
   onze routes du CRM injoignables ;
2. **le declencheur, lui, est a l'ecran** — sinon il ne sert a rien ;
3. **apres le clic**, la barre est revenue, entierement dans l'ecran, et
   ses liens sont cliquables.

Run :  py tests/probes/probe_sidebar_trigger.py
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
VW, VH = 375, 667
SLACK = 1.0

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
    raise RuntimeError("sidebar-trigger bench never came up on :8976")


def measure(page) -> dict:
    return page.evaluate(
        """() => {
            const aside = document.querySelector('aside');
            const r = aside.getBoundingClientRect();
            const links = [...aside.querySelectorAll('a')].filter(a => {
                const b = a.getBoundingClientRect();
                return b.width > 0 && b.left >= 0 && b.right <= window.innerWidth;
            }).length;
            const t = document.querySelector('#trigger').getBoundingClientRect();
            return {asideX: r.x, asideRight: r.right, asideW: r.width,
                    linksOnScreen: links,
                    triggerX: t.x, triggerY: t.y, triggerW: t.width};
        }"""
    )


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_sidebar_trigger.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": VW, "height": VH})
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready", state="attached")
            page.wait_for_timeout(500)

            before = measure(page)
            print(f"\nAu chargement — aside.x = {before['asideX']:.0f}")
            check(
                "la barre part hors ecran",
                before["asideRight"] <= SLACK,
                f"aside.right = {before['asideRight']:.0f}, attendu <= 0",
            )
            check(
                "aucun de ses liens n'est atteignable",
                before["linksOnScreen"] == 0,
                f"{before['linksOnScreen']} lien(s) a l'ecran alors que la "
                f"barre est censee etre fermee",
            )
            check(
                "le declencheur, lui, est a l'ecran",
                0 <= before["triggerX"] <= VW - before["triggerW"] + SLACK
                and before["triggerW"] > 0,
                f"x = {before['triggerX']:.0f}, largeur = "
                f"{before['triggerW']:.0f}",
            )

            page.click("#trigger")
            page.wait_for_timeout(600)
            after = measure(page)
            print(f"\nApres le clic — aside.x = {after['asideX']:.0f}")
            check(
                "la barre est revenue",
                after["asideX"] >= -SLACK,
                f"aside.x = {after['asideX']:.0f}, attendu >= 0",
            )
            check(
                "entierement dans l'ecran",
                after["asideRight"] <= VW + SLACK,
                f"aside.right = {after['asideRight']:.0f} > {VW}",
            )
            check(
                "ses liens sont atteignables",
                after["linksOnScreen"] >= len(("Accueil", "Clients", "Ventes")),
                f"{after['linksOnScreen']} lien(s) a l'ecran, attendu >= 3",
            )

            page.screenshot(path=str(HERE / "sidebar_trigger_screenshot.png"))
            print(f"\nScreenshot → {HERE / 'sidebar_trigger_screenshot.png'}")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S)")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
