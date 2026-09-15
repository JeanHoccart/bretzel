"""Sonde — l'adresse se corrige, et sans polluer l'historique.

La moitié serveur (composer l'adresse juste) se vérifie sur une chaîne.
La moitié qui compte, non : ``replaceState`` ne se mesure que dans une
vraie pile d'historique. Un ``pushState`` posé par erreur donnerait
exactement le même DOM et exactement la même barre d'adresse — et
casserait le bouton retour, sans que rien ne le dise.

Quatre mesures :

1. **l'adresse se corrige** — on trie, on va ailleurs, on revient sur
   l'URL NUE, et la barre d'adresse dit le tri ;
2. **la profondeur d'historique n'a pas bougé** — c'est un REPLACE. Si
   c'était un push, revenir en arrière une fois retomberait sur la même
   page au lieu de la précédente ;
3. **un retour ramène bien où l'on était**, ce qui est la conséquence
   observable du point 2 ;
4. **une adresse déjà juste n'est pas réécrite**.

Run :  py tests/probes/probe_url_memory.py
"""

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from tests.probes._serve import free_port

if __name__ != "__main__":
    raise RuntimeError(
        "probe_url_memory est un script : lance-le "
        "(`py tests/probes/probe_url_memory.py`), ne l'importe pas."
    )

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"
srv = subprocess.Popen(
    [sys.executable, str(HERE / "bench_url_memory.py"), str(PORT)],
    cwd=str(HERE.parent.parent),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)


def wait() -> None:
    """Attendre que le bench réponde — 30 s, pas 18.

    En mode dev la première requête compile la feuille Tailwind, ce qui
    dépasse largement le budget des sondes qui servent une page déjà
    chaude.
    """
    last = None
    for _ in range(150):
        try:
            urllib.request.urlopen(BASE + "/table", timeout=2)
            return
        except OSError as exc:
            last = exc
            time.sleep(0.2)
    raise RuntimeError(f"le bench n'a pas démarré sur :8973 — {last}")


FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    if not ok:
        FAILURES.append(f"{label} : {got!r} au lieu de {want!r}")
    print(f"  [{'PASS' if ok else 'FAIL'}] {label} — {got!r}")


def address(pg) -> str:
    return pg.evaluate("() => location.pathname + location.search")


def depth(pg) -> int:
    return pg.evaluate("() => history.length")


with sync_playwright() as p:
    wait()
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(BASE + "/table", wait_until="networkidle")
    check("au depart, adresse nue", address(page), "/table")

    # Trier : l'action pousse (c'est le mecanisme deja gate ailleurs).
    page.click("thead button")
    page.wait_for_timeout(600)
    check("apres le tri, l'adresse suit", address(page), "/table?tri=nom")

    # ── 1 + 2. Naviguer, revenir sur l'URL NUE ───────────────────────
    page.click("#vers-ailleurs")
    page.wait_for_timeout(700)
    check("on est ailleurs", address(page), "/ailleurs")

    before = depth(page)
    page.click("#vers-table")
    page.wait_for_timeout(900)

    check("de retour, l'adresse dit le TRI memorise",
          address(page), "/table?tri=nom")
    # Le point qui distingue replace de push : la navigation elle-meme
    # ajoute UNE entree ; la correction ne doit pas en ajouter une
    # seconde.
    check("la correction n'a PAS empile d'entree", depth(page), before + 1)

    # ── 3. Le retour ramene ou l'on etait ────────────────────────────
    page.go_back()
    page.wait_for_timeout(900)
    check("un seul retour ramene AILLEURS", address(page), "/ailleurs")

    # ── 4. Une adresse deja juste n'est pas reecrite ─────────────────
    page.goto(BASE + "/table?tri=nom", wait_until="networkidle")
    settled = depth(page)
    page.wait_for_timeout(500)
    check("adresse deja juste : rien ne bouge", address(page), "/table?tri=nom")
    check("...et aucune entree de plus", depth(page), settled)

    if errors:
        FAILURES.append(f"{len(errors)} erreur(s) JS : {errors[:3]}")
    else:
        print("  [PASS] aucune erreur JS")

    browser.close()

srv.terminate()

print()
if FAILURES:
    print(f"❌ {len(FAILURES)} échec(s)")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("✅ l'adresse se corrige, et l'historique reste utilisable")
