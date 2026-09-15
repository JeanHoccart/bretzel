"""Playwright probe — une grille qui compte ses colonnes sur SA place.

Drives ``bench_grid_min_col.py`` (port 8985) dans un vrai Chromium.

Le defaut mesure le 2026-08-25
-------------------------------
Rapporte par l'utilisateur sur l'ecran Parametres du CRM : le
``ui.toggle_group`` « Densite » sortait de sa colonne et se posait sur le
``ui.select`` voisin.

La cause n'etait pas le composant — un segmente a une largeur
INTRINSEQUE, comme chez tous les systemes de design. C'est la grille : un
prefixe ``xl:`` lit la largeur de la FENETRE, pas celle que la grille a
vraiment. Sous une coque a barre laterale, les deux divergent de la
largeur de la barre.

    conteneur de 1024 px (la largeur de contenu reelle du CRM)

    cols={"base":1,"md":2,"xl":4}   4 colonnes, cellules de 244 px,
                                    le cluster (256) dehors de 11,9 px
    min_col="16rem"                 3 colonnes de 331 px, rien dehors

Pourquoi un probe et pas une assertion de HTML
-----------------------------------------------
Les deux grilles rendent un HTML identique a une classe pres, et cette
classe ne dit rien de ce qui se passe : c'est le moteur de rendu qui
compte les colonnes. Aucune lecture de classes ne montre les 244 px.

Run :  py tests/probes/probe_grid_min_col.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from tests.probes._serve import free_port

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"

#: Un demi-pixel de tolerance : le sous-pixel du moteur de rendu.
SLACK = 0.5

#: Les largeurs de FENETRE. Le conteneur, lui, reste a 1024 px — c'est
#: tout l'interet : un regime qui lit le viewport bougera, l'autre non.
VIEWPORTS = (1600, 1440, 1280, 1100, 900, 700)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"le bench repond {exc.code} — demarre et CASSE, pas absent."
            ) from exc
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"grid-min-col bench never came up on {BASE}")


def refuse_a_squatted_port() -> None:
    """Ne pas mesurer le serveur de quelqu'un d'autre (piege n°7)."""
    try:
        with urllib.request.urlopen(BASE + "/", timeout=1):
            occupied = True
    except urllib.error.HTTPError:
        occupied = True
    except OSError:
        occupied = False
    if occupied:
        raise RuntimeError(
            f"{BASE} repond DEJA — un autre serveur tient le port 8985. "
            f"Arrete-le : mesurer celui d'un voisin donnerait un rouge qui "
            f"n'accuse pas le bon coupable."
        )


READ = """(id) => {
  const zone = document.querySelector('#' + id);
  const grid = zone.firstElementChild;
  const cells = [...grid.children];
  // Le nombre de COLONNES se lit sur la piste, pas en divisant le nombre
  // d'enfants par celui des lignes : la derniere ligne est souvent
  // incomplete, et la division rend alors un compte faux.
  const pistes = getComputedStyle(grid).gridTemplateColumns.split(' ').length;
  let pire = -1e9;
  for (const g of grid.querySelectorAll('[role=group]')) {
    // La CELLULE est l'ancetre dont le parent est la grille. Prendre
    // ``parentElement.parentElement`` a l'aveugle attrapait un ancetre
    // plus haut, donc une boite plus large : le temoin mesurait -508 px
    // et declarait qu'il ne debordait pas.
    let cell = g;
    while (cell.parentElement && cell.parentElement !== grid) {
      cell = cell.parentElement;
    }
    pire = Math.max(pire,
      g.getBoundingClientRect().right - cell.getBoundingClientRect().right);
  }
  return {
    colonnes: pistes,
    cellule: +cells[0].getBoundingClientRect().width.toFixed(1),
    conteneur: +zone.getBoundingClientRect().width.toFixed(1),
    debord: +pire.toFixed(1),
  };
}"""


def main() -> int:
    refuse_a_squatted_port()
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_grid_min_col.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1200})
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready", state="attached")
            page.wait_for_timeout(600)

            print("\n(0) le temoin reproduit bien le defaut")
            paliers = page.evaluate(READ, "paliers")
            print(f"      paliers : {paliers['colonnes']} colonnes, "
                  f"cellules de {paliers['cellule']} px dans "
                  f"{paliers['conteneur']} px")
            check(
                "avec des paliers de fenetre, le cluster DEBORDE sa cellule",
                paliers["debord"] > SLACK,
                f"debord de {paliers['debord']} px — si le temoin ne "
                f"deborde pas, le reste du probe ne prouve rien.",
            )

            print("\n(1) avec min_col=, plus rien ne deborde")
            intr = page.evaluate(READ, "intrinseque")
            print(f"      min_col : {intr['colonnes']} colonnes, "
                  f"cellules de {intr['cellule']} px")
            check(
                "aucun cluster hors de sa cellule",
                intr["debord"] <= SLACK,
                f"debord de {intr['debord']} px",
            )
            check(
                "et la cellule fait au moins les 16rem demandes",
                intr["cellule"] >= 256 - SLACK,
                f"cellule de {intr['cellule']} px pour un minimum de 256",
            )
            check(
                "la grille a moins de colonnes que les paliers n'en voulaient",
                intr["colonnes"] < paliers["colonnes"],
                f"{intr['colonnes']} contre {paliers['colonnes']}",
            )

            print("\n(2) le viewport ne decide plus de rien")
            # Le conteneur est fige a 1024 px : un regime qui lit la
            # fenetre bougera, l'autre non. C'est la moitie du defaut
            # qu'on ne voit pas en regardant un seul ecran.
            vus_paliers, vus_intr = {}, {}
            for width in VIEWPORTS:
                page.set_viewport_size({"width": width, "height": 1200})
                page.wait_for_timeout(300)
                vus_paliers[width] = page.evaluate(READ, "paliers")["colonnes"]
                vus_intr[width] = page.evaluate(READ, "intrinseque")["colonnes"]
            print(f"      paliers : {vus_paliers}")
            print(f"      min_col : {vus_intr}")
            check(
                "min_col rend le MEME nombre de colonnes a toutes les "
                "largeurs de fenetre",
                len(set(vus_intr.values())) == 1,
                f"colonnes vues : {vus_intr}",
            )
            check(
                "…la ou les paliers en changent, conteneur inchange",
                len(set(vus_paliers.values())) > 1,
                f"colonnes vues : {vus_paliers} — si elles ne bougent pas "
                f"non plus, le banc ne montre pas le decalage.",
            )

            print("\n(3) trop etroit, une seule colonne — le versant licite")
            page.set_viewport_size({"width": 1600, "height": 1200})
            page.wait_for_timeout(300)
            etroit = page.evaluate(READ, "etroit")
            check(
                "dans 300 px, min_col ne force pas deux colonnes",
                etroit["colonnes"] == 1,
                f"{etroit['colonnes']} colonnes dans "
                f"{etroit['conteneur']} px",
            )

            page.screenshot(
                path=str(HERE / "grid_min_col_screenshot.png"), full_page=True,
            )
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print(f"\nScreenshot -> {HERE / 'grid_min_col_screenshot.png'}")
    if FAILURES:
        print(f"\n{len(FAILURES)} ECHEC(S) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nTout vert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
