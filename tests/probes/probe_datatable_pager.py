"""Probe — le pager n'émet plus de bouton mort, et toutes les pages restent atteignables.

Le composant rendait ``max(5, max_visible)`` slots quel que soit le
nombre de pages : une table de deux pages partait avec **sept** boutons,
cinq d'entre eux masqués par ``bz-show`` et liés à chaque scan du
runtime. Ils sont maintenant coupés au rendu.

C'est une coupe, donc le mode d'échec à craindre n'est pas le surplus :
c'est d'en retirer un de trop et de rendre une page **inatteignable**.
Un test SSR ne peut pas trancher — il compte des balises, or ce qu'il
faut savoir c'est ce que l'œil VOIT et ce que le clic ATTEINT. D'où ce
probe, sur le bench à neuf tables (2, 5, 6, 7 et 9 pages).

Trois mesures, une par façon de se tromper :

1. **aucun bouton de page invisible ne survit** — le surplus d'avant ;
2. **le compte visible vaut le compte attendu** — ni trop, ni trop peu ;
3. **la dernière page s'atteint au clic** et affiche ses lignes — la
   preuve qu'aucun slot utile n'est parti avec le ménage.

Plus la navigation partielle (``hx-boost``) : le pager est reconstruit
par le morph, et « aucune suite ne NAVIGUE » est le point aveugle
documenté du dépôt.

**Et la barre d'outils préservée sur un TRI** — l'autre changement du
2026-08-28. Les tables de ce bench n'exportent pas, donc rien dans leur
barre ne sérialise le tri : elle part désormais en coquille
``hx-preserve`` sur un clic d'en-tête. Le mode d'échec est
catastrophique et muet — un id de coquille qui diverge fait DISPARAÎTRE
recherche, filtres et export — donc il se mesure dans un vrai DOM, pas
dans une chaîne HTML.

Run :  py tests/probes/probe_datatable_pager.py
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
        "probe_datatable_pager est un script : lance-le "
        "(`py tests/probes/probe_datatable_pager.py`), ne l'importe pas."
    )

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PORT = free_port()
URL = f"http://127.0.0.1:{PORT}/"
srv = subprocess.Popen(
    [sys.executable, str(HERE / "bench_datatable_pager.py"), str(PORT)],
    cwd=str(HERE.parent.parent),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)


def wait() -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(URL, timeout=1)
            return
        except OSError:
            time.sleep(0.3)


FAILURES: list[str] = []

#: ``per_page`` de chacune des neuf tables du bench, dans l'ordre du DOM,
#: et le nombre de pages que 34 lignes y donnent. La fenêtre plafonne à
#: ``max(5, max_visible)`` = 7, donc au-delà l'ellipse prend le relais.
EXPECTED = [
    ("Seven",  5, 7),
    ("Five",   8, 5),
    ("Extra1", 5, 7),
    ("Extra2", 5, 7),
    ("Extra3", 4, 9),
    ("Extra4", 4, 9),
    ("Extra5", 4, 9),
    ("Extra6", 6, 6),
    ("Extra7", 20, 2),
]


def slots(pg) -> list[dict]:
    """Un enregistrement par pager : ses boutons de page, vus du DOM.

    On lit ``offsetParent`` plutôt que ``:visible`` : un bouton masqué
    par ``bz-show`` porte ``display:none``, et c'est exactement ce qu'on
    veut compter séparément du texte affiché.
    """
    return pg.evaluate(
        """() => [...document.querySelectorAll('nav[aria-label="Pagination"]')]
            .map(nav => {
                const items = [...nav.querySelectorAll('button')]
                    .filter(b => !(b.getAttribute('aria-label') || '')
                        .match(/^(Previous|Next) page$/));
                return {
                    total: items.length,
                    hidden: items.filter(b => b.offsetParent === null).length,
                    labels: items.map(b => b.textContent.trim()),
                };
            })"""
    )


def check(page_label: str, pg) -> None:
    got = slots(pg)
    if len(got) != len(EXPECTED):
        FAILURES.append(
            f"{page_label} : {len(got)} pagers pour {len(EXPECTED)} tables"
        )
        return
    for (name, per_page, pages), seen in zip(EXPECTED, got):
        want = min(7, pages)
        if seen["hidden"]:
            FAILURES.append(
                f"{page_label}/{name} : {seen['hidden']} bouton(s) de page "
                f"INVISIBLES sur {seen['total']} — le surplus est de retour, "
                f"il repart sur le fil et le runtime le lie à chaque scan"
            )
        if seen["total"] != want:
            FAILURES.append(
                f"{page_label}/{name} ({pages} pages) : {seen['total']} "
                f"boutons de page pour {want} attendus — "
                + ("des pages sont devenues INATTEIGNABLES"
                   if seen["total"] < want else "du surplus est émis")
            )
        if seen["labels"] and seen["labels"][0] != "1":
            FAILURES.append(
                f"{page_label}/{name} : le premier slot dit "
                f"{seen['labels'][0]!r} au lieu de « 1 »"
            )


with sync_playwright() as p:
    wait()
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL, wait_until="networkidle")

    check("chargement dur", page)

    # ── La dernière page s'atteint-elle vraiment ? ────────────────────
    #
    # La table à DEUX pages est celle que la coupe touche le plus fort
    # (7 slots → 2). Si un slot utile était parti, « 2 » n'existerait
    # plus et le tableau resterait sur sa première page.
    last_nav = page.locator('nav[aria-label="Pagination"]').last
    two = last_nav.locator('button', has_text="2").first
    if two.count() == 0:
        FAILURES.append(
            "la table à 2 pages n'a plus de bouton « 2 » : la coupe a "
            "retiré un slot UTILE, la deuxième page est inatteignable"
        )
    else:
        before = page.locator("table").last.locator("tbody tr").count()
        two.click()
        page.wait_for_timeout(600)
        rows = page.locator("table").last.locator("tbody tr").count()
        if rows == 0:
            FAILURES.append(
                "cliquer « 2 » sur la table à 2 pages ne montre AUCUNE "
                "ligne — la page existe dans le pager mais pas dans la table"
            )
        current = last_nav.locator('button[aria-current="page"]').first
        label = current.text_content().strip() if current.count() else "(aucun)"
        if label != "2":
            FAILURES.append(
                f"après le clic sur « 2 », la page courante est {label!r} : "
                f"le pager ne suit pas"
            )
        print(f"table à 2 pages : {before} lignes → {rows} après le clic")

    # ── Le tri PRÉSERVE la barre, sans la faire disparaître ──────────
    #
    # On pose d'abord un filtre, pour que la barre porte un état VISIBLE
    # qui devrait survivre. Une barre qui s'évapore et une barre qui
    # revient neuve se ressemblent beaucoup quand elle est vide.
    first = page.locator(".bz-datatable").first
    toolbar_before = first.locator('[id$="_toolbar"]')
    filter_trigger = toolbar_before.locator("button", has_text="Status").first
    if filter_trigger.count() == 0:
        FAILURES.append("pas de filtre « Status » dans la première barre")
    else:
        filter_trigger.click()
        page.wait_for_timeout(400)
        page.locator('[role="option"]', has_text="open").first.click()
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
        label_before = filter_trigger.text_content().strip()

        header = first.locator("thead button").first
        header.click()
        page.wait_for_timeout(800)

        if toolbar_before.count() == 0:
            FAILURES.append(
                "la barre d'outils a DISPARU après un tri — la coquille "
                "`hx-preserve` porte un id qui ne correspond pas à la barre "
                "vivante, donc le morph l'a remplacée par une div vide"
            )
        else:
            label_after = toolbar_before.locator(
                "button", has_text="Status"
            ).first.text_content().strip()
            if label_after != label_before:
                FAILURES.append(
                    f"le filtre a changé pendant un tri : {label_before!r} "
                    f"-> {label_after!r} — la barre préservée n'est pas la "
                    f"même, ou le tri a réinitialisé l'état"
                )
            print(f"tri avec barre préservée : filtre {label_after!r} intact")
        if first.locator("tbody tr").count() == 0:
            FAILURES.append("le tri ne rend plus aucune ligne")

    # ── Après une navigation PARTIELLE ────────────────────────────────
    page.click("#vers-deux")
    page.wait_for_timeout(900)
    check("après hx-boost", page)

    for label, seen in zip([e[0] for e in EXPECTED], slots(page)):
        print(f"  {label:8} {seen['total']} slots  {seen['labels']}")

    if errors:
        FAILURES.append(f"{len(errors)} erreur(s) JS : {errors[:3]}")

    browser.close()

srv.terminate()

print()
if FAILURES:
    print(f"❌ {len(FAILURES)} échec(s)")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("✅ pager : aucun slot mort, aucune page perdue, avant et après un hx-boost")
