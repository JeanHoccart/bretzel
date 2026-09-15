"""Probe — l'état vide d'un graphique tient sa boîte, et se voit.

Pilote `bench_chart_empty.py` (:8981). Ce qu'un `TestClient` ne peut PAS
voir, et qui est donc mesuré ici :

- la boîte vide **occupe la hauteur du tracé**. Le SVG d'avant portait
  un `height` en attribut ; la boîte HTML repose sur un `min-height`
  inline, et une classe Tailwind mal compilée l'aplatirait à zéro sans
  qu'aucun test de rendu ne le dise ;
- l'**icône est peinte** — `iconify-icon` est un custom element, donc un
  élément présent dans le HTML peut très bien ne rien dessiner ;
- rien ne **déborde en largeur** : la boîte est posée dans le wrapper du
  chart, qui portait jusqu'ici un SVG à largeur fixe ;
- l'**échappatoire** rend le bouton de l'auteur, et RIEN d'autre — pas
  d'état vide automatique en plus.

Run :  py tests/probes/probe_chart_empty.py
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
CHARTS = ("bar_chart", "line_chart", "pie_chart", "scatter_chart")

#: L'icône que chaque graphique pose sur son état vide automatique. Sa
#: présence dans la boîte de l'échappatoire signerait un auto qui
#: s'ajoute au lieu de céder la place.
DEFAUTS = {
    "bar_chart": "bar-chart-3", "line_chart": "line-chart",
    "pie_chart": "pie-chart", "scatter_chart": "scatter-chart",
}
FAILURES: list[str] = []

#: Le plancher de hauteur. Les tailles de tracé du catalogue vont de
#: ~180 px (`sm`) à ~360 px ; 120 px est en dessous de toutes, donc il
#: n'épingle aucun palier — il dit seulement « la boîte n'est pas
#: aplatie ». Un seuil calé sur la valeur exacte se casserait au premier
#: changement de thème, pour rien.
_PLANCHER = 120


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("le bench chart_empty n'est jamais monté sur :8981")


#: La géométrie d'une boîte vide + ce qu'elle contient réellement.
_MESURE = """(id) => {
  const hote = document.getElementById(id);
  if (!hote) return {erreur: 'introuvable: ' + id};
  const boite = hote.querySelector('[role="img"]');
  if (!boite) return {erreur: 'aucune boîte role=img dans ' + id};
  const r = boite.getBoundingClientRect();
  const icone = boite.querySelector('iconify-icon');
  const ir = icone ? icone.getBoundingClientRect() : null;
  return {
    h: Math.round(r.height),
    w: Math.round(r.width),
    parent_w: Math.round(hote.getBoundingClientRect().width),
    aria: boite.getAttribute('aria-label'),
    icone_peinte: !!(ir && ir.width > 0 && ir.height > 0),
    icones: [...boite.querySelectorAll('iconify-icon')]
      .map(e => e.getAttribute('icon') || ''),
    bouton: !!boite.querySelector('button'),
    texte: boite.innerText.trim().slice(0, 60),
  };
}"""


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_chart_empty.py"), str(PORT)],
        cwd=str(HERE.parents[1]),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as p:
            navigateur = p.chromium.launch()
            page = navigateur.new_page(viewport={"width": 1280, "height": 900})
            erreurs: list[str] = []
            page.on("pageerror", lambda e: erreurs.append(str(e)))
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready", state="attached")
            page.wait_for_timeout(400)

            print("\n1. La boîte vide tient la hauteur du tracé")
            for nom in CHARTS:
                m = page.evaluate(_MESURE, f"{nom}_auto")
                if "erreur" in m:
                    check(f"{nom} — la boîte existe", False, m["erreur"])
                    continue
                check(f"{nom} — la boîte n'est pas aplatie",
                      m["h"] >= _PLANCHER, f"hauteur={m['h']}px")
                check(f"{nom} — rien ne déborde en largeur",
                      m["w"] <= m["parent_w"] + 1,
                      f"boîte={m['w']} > parent={m['parent_w']}")

            print("\n2. L'icône est PEINTE, pas seulement présente")
            for nom in CHARTS:
                m = page.evaluate(_MESURE, f"{nom}_auto")
                check(f"{nom} — icône dessinée", bool(m.get("icone_peinte")),
                      f"{m.get('texte')!r}")

            print("\n3. Le graphique garde son identité au lecteur d'écran")
            attendu = {
                "bar_chart": "Bar chart", "line_chart": "Line chart",
                "pie_chart": "Pie chart", "scatter_chart": "Scatter plot",
            }
            for nom in CHARTS:
                m = page.evaluate(_MESURE, f"{nom}_auto")
                aria = m.get("aria") or ""
                check(f"{nom} — aria-label le nomme",
                      aria.startswith(attendu[nom]), f"{aria!r}")

            print("\n4. La description arrive")
            for nom in CHARTS:
                m = page.evaluate(_MESURE, f"{nom}_desc")
                check(f"{nom} — la description est rendue",
                      "Choisis une autre" in (m.get("texte") or ""),
                      f"{m.get('texte')!r}")

            print("\n5. L'échappatoire remplace, elle n'ajoute pas")
            for nom in CHARTS:
                m = page.evaluate(_MESURE, f"{nom}_escape")
                check(f"{nom} — le bouton de l'auteur est là",
                      bool(m.get("bouton")), f"{m.get('texte')!r}")
                # ⚠️ Vérifier l'ABSENCE de l'icône par défaut, pas
                # l'absence de toute icône. La première version de ce
                # probe exigeait `not icone_peinte` et rendait quatre
                # rouges — sur un code correct : le bouton de
                # l'échappatoire porte `icon_left="plus"`, donc il
                # PEINT une icône, légitimement. Le probe confondait
                # « pas d'état vide automatique » et « pas d'icône ».
                icones = m.get("icones") or []
                check(f"{nom} — l'état vide auto ne s'ajoute PAS",
                      "Rien à montrer" not in (m.get("texte") or "")
                      and not any(i.endswith(DEFAUTS[nom]) for i in icones),
                      f"texte={m.get('texte')!r} icônes={icones}")

            print("\n6. Hygiène")
            hauteur = page.evaluate(
                "() => { const d = document.scrollingElement;"
                " return {w: d.scrollWidth, cw: d.clientWidth}; }")
            check("pas de défilement horizontal du document",
                  hauteur["w"] <= hauteur["cw"] + 1, str(hauteur))
            check("aucune erreur JS", not erreurs, "; ".join(erreurs[:2]))

            page.screenshot(path=str(HERE / "chart_empty.png"), full_page=True)
            navigateur.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    if FAILURES:
        print(f"\nCHART EMPTY PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nCHART EMPTY PROBE PASSED — l'état vide tient sa boîte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
