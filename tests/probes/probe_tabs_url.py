"""Sonde — un onglet a une adresse, et les flèches du navigateur marchent.

Aucun test SSR ne peut trancher ça. La moitié serveur (semer l'onglet
depuis ``?onglet=``) se vérifie sur une chaîne, mais l'autre moitié vit
entièrement dans le navigateur : ``history.pushState`` au clic, et le
``popstate`` qui rebascule le signal au retour. Il faut une vraie pile
d'historique.

Cinq mesures, une par façon de se tromper :

1. **le clic pousse** — l'adresse suit ce qu'on regarde ;
2. **le retour revient** — l'URL ET l'onglet, ensemble. C'est le pire
   mode d'échec : pousser sans restaurer laisse une adresse qui MENT sur
   ce qui est à l'écran, ce qui est pire que pas d'adresse du tout ;
3. **l'avant refait le chemin** ;
4. **un chargement dur sur l'adresse ouvre le bon onglet** — la moitié
   serveur, mesurée là où elle compte : à l'écran, au premier paint ;
5. **un ``ui.tabs`` SANS ``url=`` ne pousse rien** — la contre-épreuve.
   Sans elle, « pousser toujours » passerait les quatre premières, et
   l'opt-in ne protégerait plus rien.

Plus : le panneau ne fait aucun aller-retour (c'est la raison d'être de
``bz-show``, et l'adresser ne doit pas la coûter) et zéro erreur JS.

Run :  py tests/probes/probe_tabs_url.py
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
        "probe_tabs_url est un script : lance-le "
        "(`py tests/probes/probe_tabs_url.py`), ne l'importe pas."
    )

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"
srv = subprocess.Popen(
    [sys.executable, str(HERE / "bench_tabs_url.py"), str(PORT)],
    cwd=str(HERE.parent.parent),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)


def wait() -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/contacts/5", timeout=1)
            return
        except OSError:
            time.sleep(0.3)


FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{label} : {got!r} au lieu de {want!r}")
    print(f"  [{'PASS' if got == want else 'FAIL'}] {label} — {got!r}")


def visible_panel(pg) -> str:
    """QUEL panneau est réellement visible, vu du navigateur.

    ``offsetParent`` et pas une classe : ``bz-show`` bascule un
    ``display``, et lire l'attribut dirait ce que le serveur a écrit, pas
    ce que l'utilisateur voit.
    """
    return pg.evaluate(
        """() => {
            for (const id of ['p-identity', 'p-activity', 'p-documents']) {
                const el = document.getElementById(id);
                if (el && el.offsetParent !== null) return id;
            }
            return '(aucun)';
        }"""
    )


def param(pg) -> str:
    return pg.evaluate("() => new URL(location.href).searchParams.get('onglet')")


with sync_playwright() as p:
    wait()
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url))

    page.goto(BASE + "/contacts/5", wait_until="networkidle")
    check("au chargement, panneau identite", visible_panel(page), "p-identity")
    check("aucun parametre au depart", param(page), None)

    # ── 1. le clic pousse ────────────────────────────────────────────
    before = len(requests)
    page.click("#adresse >> text=Activites")
    page.wait_for_timeout(400)
    check("apres le clic, panneau activites", visible_panel(page), "p-activity")
    check("l'adresse a suivi", param(page), "activity")

    # Le panneau bascule SANS requête — c'est la raison d'être de
    # ``bz-show``, et lui donner une adresse ne doit pas la coûter.
    fresh = [u for u in requests[before:] if "/contacts/" in u]
    check("aucun aller-retour pour changer d'onglet", fresh, [])

    # ── 2. le RETOUR ─────────────────────────────────────────────────
    page.go_back()
    page.wait_for_timeout(600)
    check("apres retour, l'adresse est revenue", param(page), None)
    check("apres retour, l'ONGLET est revenu", visible_panel(page), "p-identity")

    # ── 3. l'avant ───────────────────────────────────────────────────
    page.go_forward()
    page.wait_for_timeout(600)
    check("apres avant, l'adresse", param(page), "activity")
    check("apres avant, l'onglet", visible_panel(page), "p-activity")

    # ── 4. un chargement DUR sur l'adresse ───────────────────────────
    page.goto(BASE + "/contacts/5?onglet=documents", wait_until="networkidle")
    check("chargement dur : le bon onglet", visible_panel(page), "p-documents")
    selected = page.evaluate(
        """() => {
            const b = document.querySelector('#adresse [role=tab][data-selected="true"]');
            return b ? b.textContent.trim() : '(aucun)';
        }"""
    )
    check("chargement dur : l'onglet est SOULIGNE", selected, "Documents")

    # ── 5. la contre-epreuve : un tabs SANS url= ─────────────────────
    page.goto(BASE + "/contacts/5", wait_until="networkidle")
    page.click("#muet >> text=Deux")
    page.wait_for_timeout(400)
    muted = page.evaluate(
        """() => document.getElementById('p-deux').offsetParent !== null"""
    )
    check("le tabs muet bascule bien", muted, True)
    check("...mais ne pousse RIEN", param(page), None)
    check("...et n'empile pas d'entree", page.evaluate("() => location.search"), "")

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
print("✅ un onglet a une adresse : clic, retour, avant, lien direct — et "
      "l'opt-in tient")
