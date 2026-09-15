"""Playwright probe — une barre ``sticky`` licite atterrit bien en bas.

Drives ``bench_bottom_bar_placement.py`` (uvicorn :8973) dans un vrai
Chromium et mesure les DEUX compositions que la garde du modele « document
gele » laisse passer :

- **A, dans le pane** — la composition d'``examples/crm`` : dernier enfant
  de la region qui defile ;
- **B, frere du pane** — enfant direct du ``ui.viewport(direction="col")``.

Pourquoi mesurer ce qui MARCHE
-------------------------------
La passe (``base/_wiring.check_sticky_bar_placement``, appelee par le
pipeline quand l'arbre est bati) refuse cinq compositions, et ses refus
sont tenus par une gate. Ce qu'aucune gate ne
peut dire, c'est si elle refuse **trop** : une garde qui rougirait aussi
sur B condamnerait la forme la plus courte de la coque mobile, et rien ne
le signalerait — le dev contournerait, c'est tout. C'est le versant licite
de la preuve, et c'est celui qui a trouve les deux seuls bugs de gate du
remboursement de dette du 2026-08-19.

Trois mesures par page, chacune correspondant a un mode d'echec mesure le
2026-08-24 avant que la garde existe :

1. la barre touche le bas de l'ecran (hors du cadre : elle se rendait a
   **y = 0**) ;
2. elle y RESTE apres defilement de la region (c'est ce que ``sticky``
   promet) ;
3. la region voisine garde sa largeur (dans un cadre en RANGEE, le
   ``ui.pane`` tombait a **0 px** et son contenu disparaissait).

Run :  py tests/probes/probe_bottom_bar_placement.py
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
#: Arrondi sous-pixel de la mise en page.
SLACK = 1.0

PAGES = (
    ("/dans-le-pane", "A dans le pane"),
    ("/frere-du-pane", "B frere du pane"),
)

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
            with urllib.request.urlopen(BASE + "/dans-le-pane", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("bottom-bar-placement bench never came up on :8973")


def box(page, selector: str) -> dict:
    return page.evaluate(
        "sel => {const r = document.querySelector(sel).getBoundingClientRect();"
        " return {x: r.x, y: r.y, w: r.width, h: r.height, bottom: r.bottom};}",
        selector,
    )


def measure(browser, path: str, label: str) -> None:
    print(f"\n{label} — {path}")
    page = browser.new_page(viewport={"width": VW, "height": VH})
    page.goto(BASE + path)
    # ``state="attached"`` et pas le defaut ``visible`` : un
    # ``ui.viewport`` est ``fixed``, donc le document n'a plus AUCUN
    # contenu dans le flux et Playwright juge ``<html>`` invisible. C'est
    # la signature du modele gele, pas une page qui n'a pas boote.
    page.wait_for_selector("html.bz-ready", state="attached")
    page.wait_for_timeout(400)

    bar = box(page, "#bar")
    check(
        f"{label}: la barre touche le bas de l'ecran",
        abs(bar["bottom"] - VH) <= SLACK,
        f"bottom={bar['bottom']:.0f}, attendu {VH}",
    )
    check(
        f"{label}: la barre prend la largeur de l'ecran",
        abs(bar["w"] - VW) <= SLACK,
        f"largeur={bar['w']:.0f}, attendu {VW}",
    )

    region = box(page, "#region")
    check(
        f"{label}: la region voisine garde sa largeur",
        region["w"] >= VW - SLACK,
        f"largeur={region['w']:.0f} — une barre pleine largeur en RANGEE "
        f"l'ecrase a 0",
    )

    page.evaluate("() => {document.querySelector('#region').scrollTop = 99999;}")
    page.wait_for_timeout(300)
    after = box(page, "#bar")
    check(
        f"{label}: elle y RESTE apres defilement",
        abs(after["bottom"] - VH) <= SLACK,
        f"bottom={after['bottom']:.0f} apres scroll, attendu {VH}",
    )

    page.screenshot(path=str(HERE / f"bottom_bar_{path.strip('/')}_screenshot.png"))
    page.close()


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_bottom_bar_placement.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for path, label in PAGES:
                measure(browser, path, label)
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
