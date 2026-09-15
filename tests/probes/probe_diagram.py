"""Playwright probe — le diagramme, une fois le CSS applique.

Drives ``bench_diagram.py`` (port 8999) dans un vrai Chromium.

Ce qu'aucune assertion de HTML ne peut dire
--------------------------------------------
Le moteur de placement est pur et il est deja gate au calcul
(``tests/unit/components/data/test_diagram_layout.py`` echantillonne les
Beziers pour affirmer qu'aucune arete ne traverse un noeud). Ce qui
reste au navigateur, c'est tout ce qui depend du CSS :

1. **Les boites sont-elles la ou le moteur les a mises ?** Les positions
   partent en ``style=`` inline ; une classe du theme qui poserait un
   ``margin`` ou un ``box-sizing`` different decalerait tout le dessin
   sans changer un octet de HTML.
2. **Le calque d'aretes avale-t-il les clics ?** Il RECOUVRE les noeuds.
   ``pointer-events-none`` est la seule chose qui l'en empeche, et son
   absence ne se voit qu'a l'essai : le HTML est identique, les noeuds
   sont bien la, et plus rien ne repond.
3. **Une double barre de defilement ?** La racine defile ; si un enfant
   defile aussi, l'utilisateur en voit deux.
4. **L'ordre de tabulation suit-il les couches ?** C'est la promesse du
   partage HTML/SVG — un ``<rect>`` ne se tabule pas.
5. **Le piege de la colonne** : la racine clippe, donc sa hauteur
   minimale automatique vaut zero. Dans une colonne flex remplie elle
   s'ecrase et coupe le dessin, sans barre et sans erreur
   (``traps.md`` § « Une colonne qui defile ECRASE ses items »).

Run :  py tests/probes/probe_diagram.py
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

#: Un demi-pixel : le sous-pixel du moteur de rendu. Les ecarts qu'on
#: cherche ici se comptent en dizaines.
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
    raise RuntimeError(f"diagram bench never came up on {BASE}")


def refuse_a_squatted_port() -> None:
    """Ne pas mesurer le serveur de quelqu'un d'autre."""
    try:
        with urllib.request.urlopen(BASE + "/", timeout=1):
            occupied = True
    except urllib.error.HTTPError:
        occupied = True
    except OSError:
        occupied = False
    if occupied:
        raise RuntimeError(
            f"{BASE} repond DEJA — un autre serveur tient le port 8999. "
            f"Arrete-le : mesurer celui d'un voisin donnerait un rouge qui "
            f"n'accuse pas le bon coupable."
        )


#: ⚠️ On ancre sur `.bz-diagram`, un MARQUEUR, jamais sur une classe
#: visuelle. La premiere version cherchait `[class*="overflow-auto"]` :
#: le jour ou la racine est passee a `overflow-x-auto`, le selecteur
#: n'a plus rien trouve et le probe est mort d'un TypeError. C'est la
#: meme mort que les deux selecteurs de `tests/audit/checklist.py`
#: emportes par la migration des rayons.
#:
#: Ce que le navigateur sait et que le serveur ignore : la boite REELLE
#: de chaque noeud, relative au canevas, plus ce que le style inline
#: promettait. L'ecart entre les deux est le verdict.
READ = """(id) => {
  const zone = document.querySelector('#' + id);
  const root = zone.querySelector('.bz-diagram');
  const canvas = root.firstElementChild;
  const svg = canvas.querySelector('svg');
  const nodes = [...canvas.querySelectorAll('[data-bz-node]')];
  const canvasBox = canvas.getBoundingClientRect();
  const promised = (el) => {
    const s = el.getAttribute('style') || '';
    const get = (k) => {
      const m = s.match(new RegExp(k + ':([-0-9.]+)px'));
      return m ? parseFloat(m[1]) : null;
    };
    return {left: get('left'), top: get('top'),
            width: get('width'), height: get('height')};
  };
  return {
    rootScrolls: root.scrollWidth > root.clientWidth + 1
              || root.scrollHeight > root.clientHeight + 1,
    rootClientH: root.clientHeight,
    rootScrollH: root.scrollHeight,
    // Un enfant qui defile AUSSI = deux barres pour l'utilisateur.
    innerScrollers: [...root.querySelectorAll('*')].filter(el => {
      const st = getComputedStyle(el);
      const scrolly = ['auto', 'scroll'].includes(st.overflowY)
                   || ['auto', 'scroll'].includes(st.overflowX);
      return scrolly && (el.scrollHeight > el.clientHeight + 1
                      || el.scrollWidth > el.clientWidth + 1);
    }).length,
    svgPointerEvents: getComputedStyle(svg).pointerEvents,
    edgeCount: svg.querySelectorAll('path[marker-end]').length,
    nodes: nodes.map(el => {
      const r = el.getBoundingClientRect();
      return {
        key: el.getAttribute('data-bz-node'),
        actual: {left: +(r.x - canvasBox.x).toFixed(2),
                 top: +(r.y - canvasBox.y).toFixed(2),
                 width: +r.width.toFixed(2), height: +r.height.toFixed(2)},
        promised: promised(el),
        tabindex: el.getAttribute('tabindex'),
      };
    }),
  };
}"""


def worst_drift(nodes: list[dict]) -> tuple[str, float]:
    """Le plus grand ecart entre la boite promise et la boite rendue."""
    worst, key = 0.0, ""
    for node in nodes:
        for axis in ("left", "top", "width", "height"):
            promised = node["promised"][axis]
            if promised is None:
                continue
            gap = abs(node["actual"][axis] - promised)
            if gap > worst:
                worst, key = gap, f"{node['key']}.{axis}"
    return key, worst


def main() -> int:
    refuse_a_squatted_port()
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_diagram.py"), str(PORT)],
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

            place = page.evaluate(READ, "place")
            etroit = page.evaluate(READ, "etroit")
            colonne = page.evaluate(READ, "colonne")

            print("\n1. Le dessin est la ou le moteur l'a place")
            check("quatre noeuds rendus", len(place["nodes"]) == 4,
                  f"{len(place['nodes'])}")
            key, drift = worst_drift(place["nodes"])
            check("aucune boite ne derive de son style inline",
                  drift <= SLACK, f"{key} derive de {drift} px")
            check("une arete par paire, fleche comprise",
                  place["edgeCount"] == 5, f"{place['edgeCount']} tracees")

            print("\n2. Le calque d'aretes n'avale pas les clics")
            check("pointer-events:none sur le <svg>",
                  place["svgPointerEvents"] == "none",
                  place["svgPointerEvents"])
            # La preuve par le geste : un noeud du graphe cliquable est
            # RECOUVERT par le calque. S'il repond, le calque est
            # transparent aux clics pour de vrai.
            before = page.evaluate("document.querySelectorAll('[data-bz-node]').length")
            page.click('#clic [data-bz-node="d"]')
            page.wait_for_timeout(600)
            check("un clic atteint le noeud sous le calque",
                  page.evaluate("document.querySelectorAll('[data-bz-node]').length") == before,
                  "la page a change de forme apres le clic")

            print("\n3. Designer un noeud eclaire ce qui le touche")
            # Le geste que le framework rend GRATUIT : zero requete, zero
            # ligne de JS ecrite par l'app. L'adjacence est cuite dans le
            # DOM au rendu, `bz-class` fait le reste.
            def opacities() -> dict[str, str]:
                return dict(page.eval_on_selector_all(
                    "#place [data-bz-node]",
                    "e=>e.map(x=>[x.dataset.bzNode,"
                    " getComputedStyle(x).opacity])"))

            rest = opacities()
            check("au repos, tout est en avant",
                  set(rest.values()) == {"1"}, str(rest))
            page.click('#place [data-bz-node="b"]')
            page.wait_for_timeout(300)
            lit = opacities()
            # `c` est le seul que rien ne relie a `b` dans le losange.
            check("le non-relie s'estompe",
                  float(lit["c"]) < 0.5, f"c={lit['c']}")
            check("le designe et ses voisins restent en avant",
                  all(lit[k] == "1" for k in ("a", "b", "d")), str(lit))
            faded = page.eval_on_selector_all(
                "#place svg path[marker-end]",
                "e=>e.filter(p=>+getComputedStyle(p).opacity < 0.5).length")
            check("les aretes qui sortent du voisinage s'estompent aussi",
                  faded > 0, "aucune arete estompee")
            page.click('#place [data-bz-node="b"]')
            page.wait_for_timeout(300)
            check("recliquer eteint — la seule sortie sans survol",
                  set(opacities().values()) == {"1"}, str(opacities()))

            # Les deux autres sorties. Sans elles on reste eclaire tant
            # qu'on n'a pas RETROUVE le noeud designe — ce qui suppose
            # de savoir lequel c'etait.
            page.click('#place [data-bz-node="b"]')
            page.wait_for_timeout(250)
            page.mouse.click(5, 5)  # hors du composant
            page.wait_for_timeout(350)
            check("cliquer hors du diagramme rallume tout",
                  set(opacities().values()) == {"1"}, str(opacities()))

            page.click('#place [data-bz-node="b"]')
            page.wait_for_timeout(250)
            root = page.query_selector('#place div.bz-diagram')
            box = root.bounding_box()
            # Le coin bas-droit du dessin : dans le composant, sur aucun
            # noeud (les couches se lisent vers la droite, la derniere
            # est en haut).
            page.mouse.click(box["x"] + box["width"] - 6,
                             box["y"] + box["height"] - 6)
            page.wait_for_timeout(350)
            check("cliquer dans le vide du dessin rallume tout",
                  set(opacities().values()) == {"1"}, str(opacities()))

            cursors = page.eval_on_selector_all(
                "#place [data-bz-node]",
                "e=>[...new Set(e.map(x=>getComputedStyle(x).cursor))]")
            check("un noeud s'annonce cliquable au curseur",
                  cursors == ["pointer"], str(cursors))
            # Le `render=` maison doit centrer son contenu : deux
            # `justify-*` sur le meme element se departagent par l'ordre
            # de la FEUILLE, pas de l'attribut, et le contenu restait
            # colle en haut.
            centred = page.evaluate("""() => {
              const n = document.querySelector('#place [data-bz-node]');
              const body = n.firstElementChild;
              const nb = n.getBoundingClientRect();
              const bb = body.getBoundingClientRect();
              const top = bb.top - nb.top;
              const bottom = nb.bottom - bb.bottom;
              return Math.abs(top - bottom) <= 1.5;
            }""")
            check("le corps d'un noeud est centre dans sa boite", centred)

            print("\n4. Une seule barre de defilement")
            check("le graphe etroit DEFILE au lieu de retrecir",
                  etroit["rootScrolls"] is True)
            check("aucun enfant ne defile en plus de la racine",
                  etroit["innerScrollers"] == 0,
                  f"{etroit['innerScrollers']} defileur(s) interne(s)")

            print("\n5. L'ordre de tabulation suit les couches")
            order = [n["key"] for n in place["nodes"]]
            check("l'ordre du DOM est celui des couches",
                  order == ["a", "b", "c", "d"], str(order))
            clic_nodes = page.evaluate(READ, "clic")["nodes"]
            check("un noeud cliquable est tabulable",
                  all(n["tabindex"] == "0" for n in clic_nodes),
                  str([n["tabindex"] for n in clic_nodes]))

            print("\n6. Le piege de la colonne (traps.md)")
            # La racine clippe, donc sa hauteur minimale auto vaut zero :
            # dans une colonne bornee elle s'ecrase. Ce qu'on exige ici
            # n'est pas qu'elle ne s'ecrase pas — c'est qu'elle laisse
            # une barre plutot que de COUPER en silence.
            crushed = colonne["rootClientH"] < 40
            check("le graphe ne s'ecrase pas a zero dans une colonne bornee",
                  not crushed, f"hauteur visible {colonne['rootClientH']} px")
            check("s'il est coupe, il defile",
                  colonne["rootScrollH"] <= colonne["rootClientH"] + 1
                  or colonne["rootScrolls"],
                  "contenu coupe SANS barre de defilement")

            page.screenshot(path=str(HERE / "_shots" / "diagram.png"),
                            full_page=True)
            print(f"\n  capture : {HERE / '_shots' / 'diagram.png'}")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print("==> SOME CHECKS FAILED")
        for line in FAILURES:
            print(f"  - {line}")
        return 1
    print("==> ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
