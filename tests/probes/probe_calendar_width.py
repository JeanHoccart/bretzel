"""Playwright probe — la fleche « mois suivant » ne se derobe pas.

Drives ``bench_calendar_width.py`` (port 8979) dans un vrai Chromium,
en francais PUIS en anglais.

Le defaut mesure le 2026-08-25
-------------------------------
Le slot ``root`` du calendrier valait ``w-fit``, donc sa largeur etait
``max(en-tete, grille)`` — et le libelle du mois est du texte de largeur
variable. Mesure a ``md``, en francais :

    aout       largeur 278,0   fleche a x = 249,0
    septembre  largeur 292,8   fleche a x = 263,8

**La cible se deplacait de 14,8 px entre deux clics sur elle-meme.** On
clique « mois suivant », le mois change, la fleche part ailleurs, et il
faut re-viser. La hauteur, elle, ne bougeait pas : la grille complete
toujours ses 6 semaines.

Deux causes, et la seconde ne se voyait pas depuis la premiere :
1. ``w-fit`` laissait l'en-tete dimensionner la racine ;
2. les fleches sont des ``ui.icon_button`` a qui le calendrier passait
   ``size=`` — donc 40 px au palier ``md``, alors que son PROPRE theme
   declare ``nav_button: w-8`` (32 px). Le jeton etait honore par le
   rendu JS et ignore par le rendu Python, et ces 2 x 8 px de trop
   faisaient deborder l'en-tete de la largeur figee.

Pourquoi un probe et pas une assertion de HTML
-----------------------------------------------
Le HTML etait IDENTIQUE d'un mois a l'autre — seules les classes
Tailwind decidaient, et il faut un moteur de rendu pour savoir ce
qu'elles produisent. Aucune lecture de classes n'aurait montre les
14,8 px.

Run :  py tests/probes/probe_calendar_width.py
"""

from __future__ import annotations

import os
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

SIZES = ("xs", "sm", "md", "lg", "xl")
MONTHS = (5, 8, 9, 12)

#: Un demi-pixel de tolerance : le sous-pixel du moteur de rendu, pas un
#: deplacement. Le defaut d'origine valait 14,8 px, donc le seuil ne
#: risque pas de le laisser passer.
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
    raise RuntimeError(f"calendar-width bench never came up on {BASE}")


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
            f"{BASE} repond DEJA — un autre serveur tient le port 8979. "
            f"Arrete-le : mesurer celui d'un voisin donnerait un rouge qui "
            f"n'accuse pas le bon coupable."
        )


MEASURE = """(ids) => {
  const out = {};
  for (const id of ids) {
    const root = document.querySelector('#' + id + ' bz-calendar');
    if (!root) { out[id] = null; continue; }
    const hdr = root.querySelector('[data-bz-cal-header]');
    const buttons = [...hdr.querySelectorAll('button')];
    const next = buttons[buttons.length - 1];
    const label = hdr.querySelector('span');
    // Le declencheur du MOIS : son chevron est le premier a etre ecrase
    // quand l'en-tete manque de place, et c'est le symptome qu'aucune
    // mesure de largeur ne montre. Vu a ``xs`` en francais avant la
    // reparation : chevron a 0 px et « septembre2026 » colles.
    const trigger = hdr.children[1].querySelector('button');
    const chevron = trigger.querySelector('iconify-icon');
    const lr = label.getBoundingClientRect();
    const cr = chevron.getBoundingClientRect();
    const r = root.getBoundingClientRect();
    out[id] = {
      width: +r.width.toFixed(2),
      // Position de la fleche RELATIVE a son calendrier : les bancs
      // sont poses cote a cote, donc une coordonnee absolue melangerait
      // la mise en page de la page avec ce qu'on mesure.
      nextX: +(next.getBoundingClientRect().x - r.x).toFixed(2),
      nextW: +next.getBoundingClientRect().width.toFixed(2),
      label: label ? label.textContent.trim() : '',
      overflow: +(hdr.scrollWidth - hdr.clientWidth).toFixed(2),
      chevronW: +cr.width.toFixed(2),
      labelToChevron: +(cr.x - lr.right).toFixed(2),
      truncated: label.scrollWidth > label.clientWidth + 0.5,
    };
  }
  return out;
}"""


def run_one(pw, lang: str) -> dict:
    refuse_a_squatted_port()
    env = dict(os.environ, BENCH_LANG=lang)
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_calendar_width.py"), str(PORT)],
        cwd=HERE.parent.parent, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 2400})
        page.goto(BASE + "/")
        page.wait_for_selector("html.bz-ready", state="attached")
        page.wait_for_timeout(800)
        ids = [f"c-{s}-{m}" for s in SIZES for m in MONTHS] + [f"y-{s}" for s in SIZES]
        out = page.evaluate(MEASURE, ids)
        page.screenshot(
            path=str(HERE / f"calendar_width_{lang}_screenshot.png"), full_page=True,
        )
        browser.close()
        return out
    finally:
        server.terminate()
        server.wait(timeout=10)
        time.sleep(1.0)


def judge(lang: str, measured: dict) -> None:
    print(f"\n=== {lang}")
    for size in SIZES:
        cells = [measured[f"c-{size}-{m}"] for m in MONTHS]
        assert all(cells), f"un calendrier manque au palier {size}"
        labels = " / ".join(c["label"] for c in cells)
        widths = {c["width"] for c in cells}
        xs = [c["nextX"] for c in cells]
        spread = max(xs) - min(xs)
        print(f"  {size:<3} {labels:<34} largeur={sorted(widths)} "
              f"ecart_fleche={spread:.2f} px")

        check(
            f"{lang}/{size} : la largeur ne depend pas du mois",
            len(widths) == 1,
            f"largeurs mesurees : {sorted(widths)}",
        )
        check(
            f"{lang}/{size} : la fleche ne bouge pas",
            spread <= SLACK,
            f"ecart de {spread:.2f} px entre {labels}",
        )
        check(
            f"{lang}/{size} : l'en-tete ne deborde pas",
            all(c["overflow"] <= SLACK for c in cells),
            f"debordements : {[c['overflow'] for c in cells]}",
        )
        check(
            f"{lang}/{size} : la fleche garde sa taille",
            len({c["nextW"] for c in cells}) == 1,
            f"largeurs de fleche : {sorted({c['nextW'] for c in cells})}",
        )
        # Les deux symptomes qu'une mesure de LARGEUR ne montre pas : ce
        # qui cede quand l'en-tete manque de place, ce n'est pas la
        # largeur du calendrier (elle est figee) mais ce qu'il y a
        # dedans — le chevron du mois d'abord, le libelle ensuite.
        check(
            f"{lang}/{size} : le chevron du mois garde sa place",
            all(c["chevronW"] > 0 and c["labelToChevron"] > 0 for c in cells),
            f"chevrons : {[c['chevronW'] for c in cells]}, "
            f"ecarts au libelle : {[c['labelToChevron'] for c in cells]}",
        )
        check(
            f"{lang}/{size} : le nom du mois n'est pas tronque",
            not any(c["truncated"] for c in cells),
            f"tronques : {[c['label'] for c in cells if c['truncated']]}",
        )

    # Le mode ``month`` a une grille d'annee, pas de jours : la largeur
    # figee par palier doit lui aller aussi, sans debordement.
    for size in SIZES:
        year = measured[f"y-{size}"]
        assert year, f"mode=month manquant au palier {size}"
        check(
            f"{lang}/{size} : mode=month ne deborde pas",
            year["overflow"] <= SLACK,
            f"debordement de {year['overflow']} px",
        )


def main() -> int:
    with sync_playwright() as pw:
        for lang in ("fr", "en"):
            judge(lang, run_one(pw, lang))

    print(f"\nScreenshots -> {HERE / 'calendar_width_fr_screenshot.png'}")
    if FAILURES:
        print(f"\n{len(FAILURES)} ECHEC(S) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nTout vert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
