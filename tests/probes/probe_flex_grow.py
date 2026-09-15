"""Playwright probe — une barre de filtres reste une BARRE.

Drives ``bench_flex_grow.py`` (port 8984) dans un vrai Chromium.

Le defaut, mesure le 2026-08-25
-------------------------------
La racine de ``ui.form_field`` porte ``w-full`` — la convention de tous
les controles, ecrite et voulue : un champ remplit sa colonne. Mais sur
une ligne de repli, un item dont la base vaut 100 % ne peut **jamais**
partager sa ligne. Deux champs dans 860 px :

    sans base   860 px chacun, empiles,     barre de 148 px
    avec base   422 px chacun, cote a cote, barre de  66 px

Trois apps portaient la rustine a l'appel (``BAR_FIELD = "basis-64
grow"``), recopiee sur chaque champ. ``grow=`` la deplace sur le PARENT.

Pourquoi un probe et pas une assertion de HTML
-----------------------------------------------
Le HTML des deux barres est identique a une classe pres, et cette classe
ne dit rien de ce qui se passe : c'est le moteur de rendu qui decide si
deux items partagent une ligne. Aucune lecture de classes ne montre les
860 px.

Run :  py tests/probes/probe_flex_grow.py
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

#: Un demi-pixel de tolerance : le sous-pixel du moteur de rendu, pas un
#: decalage. Les ecarts mesures ici se comptent en centaines de pixels.
SLACK = 0.5

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
    raise RuntimeError(f"flex-grow bench never came up on {BASE}")


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
            f"{BASE} repond DEJA — un autre serveur tient le port 8984. "
            f"Arrete-le : mesurer celui d'un voisin donnerait un rouge qui "
            f"n'accuse pas le bon coupable."
        )


READ = """(id) => {
  const zone = document.querySelector('#' + id);
  const bar = zone.querySelector(':scope > div');
  // Les champs sont les enfants DIRECTS de la barre.
  const fields = [...bar.children];
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return {x: +r.x.toFixed(2), y: +r.y.toFixed(2),
            w: +r.width.toFixed(2), h: +r.height.toFixed(2)};
  };
  return {
    // La largeur de la ZONE, pour que les assertions se mesurent contre
    // elle et non contre un nombre recopie. Un seuil litteral (`> 380`,
    // taille pour un temoin de 420 px) devient faux des que le banc
    // change de largeur — et il a du changer quand l'echelle du framework
    // a maigri, le 2026-09-13.
    zoneWidth: +zone.getBoundingClientRect().width.toFixed(2),
    barHeight: +bar.getBoundingClientRect().height.toFixed(2),
    barClass: bar.getAttribute('class') || '',
    fields: fields.map(box),
    // Ce qu'un enfant porte LUI-MEME : la promesse est que le parent
    // distribue seul, donc aucun champ ne doit avoir de base a lui.
    fieldClasses: fields.map(f => f.getAttribute('class') || ''),
  };
}"""


def rows_of(fields: list[dict]) -> int:
    """Combien de LIGNES occupent ces boites — le seul verdict qui compte.

    Compte les ordonnees distinctes plutot que de comparer deux a deux :
    une barre a trois champs dont deux partagent une ligne n'est ni une
    pile ni une barre, et il faut pouvoir le dire.
    """
    return len({round(f["y"]) for f in fields})


def main() -> int:
    refuse_a_squatted_port()
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_flex_grow.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 1400})
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready", state="attached")
            page.wait_for_timeout(400)

            temoin = page.evaluate(READ, "temoin")
            repare = page.evaluate(READ, "repare")
            egal = page.evaluate(READ, "egal")
            base = page.evaluate(READ, "base")
            etroit = page.evaluate(READ, "etroit")

            print("\n(0) le temoin reproduit bien le defaut")
            # Si le temoin ne s'empile pas, tout le reste ne prouve rien :
            # on aurait mesure deux barres correctes.
            check(
                "sans grow=, les deux champs sont EMPILES",
                rows_of(temoin["fields"]) == 2,
                f"lignes : {rows_of(temoin['fields'])}, "
                f"boites : {temoin['fields']}",
            )
            print(f"      temoin : {[f['w'] for f in temoin['fields']]} px, "
                  f"barre {temoin['barHeight']} px")

            print("\n(1) avec grow=, la barre est une BARRE")
            check(
                "les deux champs partagent une ligne",
                rows_of(repare["fields"]) == 1,
                f"lignes : {rows_of(repare['fields'])}, "
                f"boites : {repare['fields']}",
            )
            print(f"      repare : {[f['w'] for f in repare['fields']]} px, "
                  f"barre {repare['barHeight']} px")
            check(
                "et elle est deux fois moins haute",
                repare["barHeight"] < temoin["barHeight"] * 0.75,
                f"{repare['barHeight']} px contre {temoin['barHeight']} px",
            )
            check(
                "chaque champ est plus etroit que la barre entiere",
                all(f["w"] < 500 for f in repare["fields"]),
                f"largeurs : {[f['w'] for f in repare['fields']]}",
            )

            print("\n(2) le parent distribue SEUL")
            check(
                "la classe est sur la barre",
                "*:basis-64" in repare["barClass"],
                f"classe de la barre : {repare['barClass']!r}",
            )
            check(
                "aucun champ ne porte de base a lui",
                not any("basis-" in c for c in repare["fieldClasses"]),
                f"classes des champs : {repare['fieldClasses']}",
            )

            print("\n(3) grow=True donne des parts EGALES, et ce n'est PAS une base")
            widths = [f["w"] for f in egal["fields"]]
            spread = max(widths) - min(widths)
            print(f"      equal : {widths} px, {rows_of(egal['fields'])} ligne(s)")
            print(f"      16rem : {[f['w'] for f in base['fields']]} px, "
                  f"{rows_of(base['fields'])} ligne(s)")
            check(
                "trois boutons de largeurs intrinseques differentes "
                "rendent trois largeurs EGALES",
                spread <= SLACK,
                f"ecart de {spread:.2f} px entre {widths}",
            )
            check(
                "…et ils tiennent sur UNE ligne, la ou une base de 16rem "
                "en demanderait deux",
                rows_of(egal["fields"]) == 1 and rows_of(base["fields"]) == 2,
                f"equal sur {rows_of(egal['fields'])} ligne(s), 16rem sur "
                f"{rows_of(base['fields'])} — si les deux sont egales, rien "
                f"ne distingue l'entree ``equal`` d'une base",
            )

            print("\n(4) trop etroit, la barre se replie — c'est voulu")
            check(
                "dans 300 px, les deux champs reviennent sur deux lignes",
                rows_of(etroit["fields"]) == 2,
                f"lignes : {rows_of(etroit['fields'])}, "
                f"boites : {etroit['fields']}",
            )
            check(
                "et chacun prend toute la largeur disponible",
                all(f["w"] >= etroit["zoneWidth"] * 0.95
                    for f in etroit["fields"]),
                f"largeurs : {[f['w'] for f in etroit['fields']]} "
                f"pour une zone de {etroit['zoneWidth']} px",
            )

            page.screenshot(
                path=str(HERE / "flex_grow_screenshot.png"), full_page=True,
            )
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print(f"\nScreenshot -> {HERE / 'flex_grow_screenshot.png'}")
    if FAILURES:
        print(f"\n{len(FAILURES)} ECHEC(S) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nTout vert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
