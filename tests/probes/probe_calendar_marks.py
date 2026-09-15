"""Playwright probe — un jour marque se VOIT, et ne bouscule rien.

Drives ``bench_calendar_marks.py`` (port 8980) dans un vrai Chromium.

Pourquoi un probe et pas une assertion de HTML
-----------------------------------------------
Le HTML rendu ne contient AUCUNE case : la grille est batie par le custom
element au ``connectedCallback``. Tout ce que le serveur emet, c'est un
attribut ``marks`` et un gabarit de nom accessible. Le contrat Python est
tenu par ``tests/unit/.../test_calendar_marks.py`` ; ce qui suit ne peut
se mesurer qu'ici.

Six choses, et chacune ferme un mode de panne different :

1. **les bons jours, et eux seuls** — une pastille de trop est aussi
   fausse qu'une manquante ;
2. **le debord ne compte pas** — la grille montre six jours de part et
   d'autre du mois ; pastiller un 30 juillet vu depuis aout ferait lire
   une charge qui n'est pas celle du mois qu'on regarde ;
3. **le numero du jour ne bouge PAS** — la pastille est en position
   absolue exprès. Posee dans le flux, elle transformerait la case en
   colonne et decalerait le chiffre de TOUTES les cases, marquees ou
   non. Mesure contre un calendrier temoin sans marques ;
4. **elle reste visible sur le jour selectionne** — dont le fond EST la
   couleur d'accent. C'est le probe « color distinctness » de la
   discipline #3 : deux couleurs identiques rendent un HTML parfait et
   une pastille invisible ;
5. **elle survit au changement de mois** — la grille est REBATIE en JS a
   chaque clic, donc une marque branchee au seul premier rendu
   disparaitrait au premier geste ;
6. **le nom accessible porte le compte, dans la langue de l'app** — le
   gabarit part resolu du serveur ; s'il sort en anglais, il n'a pas
   voyage.

Run :  py tests/probes/probe_calendar_marks.py
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

SIZES = ("xs", "sm", "md", "lg", "xl")

#: Repetes ici et non importes du bench : un probe qui importe son banc
#: ne prouve plus qu'ils s'accordent.
MARKED_IN_MONTH = ["2026-08-03", "2026-08-14"]
OUTSIDE_MONTH = "2026-07-30"
NEXT_MONTH_MARK = "2026-09-09"

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
    raise RuntimeError(f"calendar-marks bench never came up on {BASE}")


def refuse_a_squatted_port() -> None:
    try:
        with urllib.request.urlopen(BASE + "/", timeout=1):
            occupied = True
    except urllib.error.HTTPError:
        occupied = True
    except OSError:
        occupied = False
    if occupied:
        raise RuntimeError(
            f"{BASE} repond DEJA — un autre serveur tient le port 8980. "
            f"Arrete-le : mesurer celui d'un voisin donnerait un rouge qui "
            f"n'accuse pas le bon coupable."
        )


READ = """(id) => {
  const root = document.querySelector('#' + id + ' bz-calendar');
  const cells = [...root.querySelectorAll('[data-day-cell]')];
  const dotOf = (c) => c.querySelector('span:nth-child(2)');
  const marked = cells.filter(c => dotOf(c));
  const numberTop = (c) => {
    const n = c.querySelector('span:first-child').getBoundingClientRect();
    return +(n.top - c.getBoundingClientRect().top).toFixed(2);
  };
  const paint = (el) => getComputedStyle(el).backgroundColor;
  const selected = cells.find(c => c.dataset.selected === 'true');
  const selectedDot = selected ? dotOf(selected) : null;
  return {
    markedDates: marked.map(c => c.dataset.date),
    // Le decalage du CHIFFRE dans sa case, marquee ou non : c'est la
    // seule facon de voir si la pastille pousse quelque chose.
    numberTops: Object.fromEntries(
      cells.slice(0, 14).map(c => [c.dataset.date, numberTop(c)])),
    labels: Object.fromEntries(
      marked.map(c => [c.dataset.date, c.getAttribute('aria-label')])),
    dotSizes: marked.map(c => {
      const r = dotOf(c).getBoundingClientRect();
      return +Math.min(r.width, r.height).toFixed(2);
    }),
    selectedDate: selected ? selected.dataset.date : null,
    selectedBg: selected ? paint(selected) : null,
    selectedDotBg: selectedDot ? paint(selectedDot) : null,
  };
}"""


def rgb(value: str) -> tuple[int, int, int]:
    nums = [int(float(n)) for n in value.replace(",", " ")
            .strip("rgbaRGBA() ").split()[:3]]
    return tuple(nums)  # type: ignore[return-value]


def distance(a: str, b: str) -> int:
    """Ecart de couleur, somme des canaux. Grossier et suffisant : on ne
    demande pas « joli », on demande « distinguable »."""
    return sum(abs(x - y) for x, y in zip(rgb(a), rgb(b), strict=True))


def main() -> int:
    refuse_a_squatted_port()
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_calendar_marks.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 2400})
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready", state="attached")
            page.wait_for_timeout(800)

            print("\n(1) les bons jours, et eux seuls")
            for size in SIZES:
                got = page.evaluate(READ, f"m-{size}")
                check(
                    f"{size} : deux jours marques",
                    sorted(got["markedDates"]) == MARKED_IN_MONTH,
                    f"marques : {sorted(got['markedDates'])}",
                )
                check(
                    f"{size} : la pastille a une taille",
                    all(d > 0 for d in got["dotSizes"]),
                    f"tailles : {got['dotSizes']}",
                )

            print("\n(2) un jour hors du mois affiche n'est jamais marque")
            got = page.evaluate(READ, "m-md")
            check(
                "le 30 juillet, visible dans le debord, n'a pas de pastille",
                OUTSIDE_MONTH not in got["markedDates"],
                f"marques : {got['markedDates']}",
            )

            print("\n(3) le numero du jour ne bouge pas")
            witness = page.evaluate(READ, "temoin")
            tops = {**got["numberTops"]}
            shared = set(tops) & set(witness["numberTops"])
            drift = max(
                (abs(tops[d] - witness["numberTops"][d]) for d in shared),
                default=None,
            )
            check(
                "meme position qu'un calendrier sans marques",
                drift is not None and drift <= 0.5,
                f"decalage max de {drift} px sur {len(shared)} cases",
            )

            print("\n(4) la pastille reste visible sur le jour selectionne")
            check(
                "le jour selectionne est bien marque",
                got["selectedDotBg"] is not None,
                f"selectionne = {got['selectedDate']}, pastille = "
                f"{got['selectedDotBg']}",
            )
            if got["selectedDotBg"]:
                gap = distance(got["selectedBg"], got["selectedDotBg"])
                check(
                    "elle se distingue du fond d'accent",
                    gap >= 60,
                    f"fond {got['selectedBg']} contre pastille "
                    f"{got['selectedDotBg']} — ecart {gap}",
                )

            print("\n(5) elle survit au changement de mois")
            # ``>`` obligatoire : sans lui, ``button:last-of-type``
            # attrape aussi le declencheur de chaque dropdown (seul
            # bouton de son parent, donc last-of-type), et Playwright
            # clique le PREMIER trouve — le selecteur de mois. Le probe
            # rougissait alors sur le rendu alors que le clic n'avait
            # jamais change de mois.
            page.click("#m-md bz-calendar [data-bz-cal-header] > button:last-of-type")
            page.wait_for_timeout(500)
            after = page.evaluate(READ, "m-md")
            check(
                "septembre montre SA marque",
                after["markedDates"] == [NEXT_MONTH_MARK],
                f"marques apres le clic : {after['markedDates']}",
            )

            print("\n(6) le nom accessible porte le compte, dans la langue")
            label = got["labels"].get("2026-08-03")
            check(
                "le compte y est",
                label is not None and "1" in label,
                f"aria-label = {label!r}",
            )
            check(
                "et la surcharge de texts= a voyage",
                label is not None and "activites" in label,
                f"aria-label = {label!r} — attendu la forme francaise",
            )

            print("\n(7) la prop traverse ui.date_picker")
            page.click("#picker button[aria-label]")
            page.wait_for_timeout(500)
            picker = page.evaluate(READ, "picker")
            check(
                "le panneau du picker montre les memes marques",
                sorted(picker["markedDates"]) == MARKED_IN_MONTH,
                f"marques : {sorted(picker['markedDates'])}",
            )

            page.screenshot(
                path=str(HERE / "calendar_marks_screenshot.png"), full_page=True,
            )
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print(f"\nScreenshot -> {HERE / 'calendar_marks_screenshot.png'}")
    if FAILURES:
        print(f"\n{len(FAILURES)} ECHEC(S) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nTout vert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
