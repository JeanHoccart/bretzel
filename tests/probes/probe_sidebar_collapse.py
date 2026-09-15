"""Probe — le repli de la sidebar : ce qui déborde, et ce qui fond.

Sorti de ``bench_sidebar_collapse.py`` le 2026-08-26. Il y vivait en
``--probe``, une **troisième forme** que ``pytest -m probes`` ne collecte
pas : ce dernier ramasse ``probe_*.py``. Conséquence, mesurée en le
sortant : il **plantait** sur un ``TimeoutError`` avant d'atteindre le
moindre verdict, et personne ne pouvait le savoir.

Pourquoi il plantait, et ce que ça dit du sélecteur
----------------------------------------------------
Il cliquait ``button[aria-label*="idebar"]``. Ce motif matche **deux**
contrôles, et ``query_selector`` rend le premier du DOM :

- l'**arête** (``rail_edge``, ``aria-label="Collapse or expand the
  sidebar"``) — ``hidden md:block``, donc **0×0** sous 768 px, et le banc
  ouvrait une fenêtre de 700 ;
- le **bouton de titre** (``aria-label="Toggle sidebar"``) — 40×40,
  visible tant que la barre est dépliée.

Un sélecteur « qui contient » attrape donc le mauvais des deux, et le
clic attend 30 s un élément invisible. Ce probe nomme désormais son
contrôle en toutes lettres, et ouvre une fenêtre assez large pour que
l'arête existe : le mode rail est une affordance BUREAU, la gater sous
``md:`` est une décision du composant, pas un accident.

Ce qu'il mesure
---------------
1. **statique**, sur les huit cas du banc : aucune icône hors de la
   bande, et le bouton de repli tient dans sa boîte ;
2. **le clic**, parce que le repli est une transition et qu'un état
   statique ne dit rien d'elle : la largeur change, et rien ne dépasse
   après ;
3. **le fondu des DEUX libellés** — celui du titre et celui d'une
   entrée —, échantillonné DANS la page. Un ``getComputedStyle`` après
   coup ne voit que l'état final, identique qu'il ait fondu ou sauté
   (cf. la memory ``steady_state_instruments_miss_races``). Mesuré le
   2026-08-18 avant correction : le titre sautait à ``display:none`` en
   60 ms, opacité encore à 1.00 ; l'entrée a suivi le 2026-09-01 ;
4. **ce que le fondu de l'entrée aurait pu coûter**. Son ``hidden``
   était défendu par un argument juste — ``display:none`` rend sa place
   sans discuter, donc l'icône se centre toute seule dans le carré. Le
   fondu doit rendre cette place AUSSI complètement (``w-0`` +
   ``flex-none``), et c'est la seule chose qui n'allait pas de soi :
   mesuré, le centre de l'icône est à 0 px du centre de la bande.

Run :  py tests/probes/probe_sidebar_collapse.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from tempfile import mkdtemp

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
PORT = 8952
BASE = f"http://127.0.0.1:{PORT}"

#: Les DEUX contrôles de repli, nommés séparément — c'est tout l'objet du
#: bug de sélecteur décrit plus haut.
#:
#: ``EDGE`` est l'arête : elle existe avec OU SANS titre, dépliée comme
#: repliée. C'est l'affordance universelle que le finding [29] a
#: restaurée, donc celle qu'on CLIQUE.
#: ``TITLE_TOGGLE`` est le chevron du titre : il n'existe que si la barre
#: a un ``ui.sidebar_title``, et disparaît une fois repliée. On le MESURE
#: quand il est là, on ne s'en sert pas pour piloter.
EDGE = '#probe-side button[aria-label="Collapse or expand the sidebar"]'
TITLE_TOGGLE = '#probe-side button[aria-label="Toggle sidebar"]'

#: Les huit pages du banc — ``(route, mode, ouvert)``. Miroir de ses
#: ``CASES`` ; ``test_every_bench_page_still_renders`` garde par ailleurs
#: que ces routes rendent.
CASES = (
    ("rail-titled", "rail", True),
    ("rail-untitled", "rail", True),
    ("none-untitled", "none", True),
    ("offcanvas-open", "offcanvas", True),
    ("overlay-open", "overlay", True),
    ("rail-closed", "rail", False),
    ("offcanvas-closed", "offcanvas", False),
    ("overlay-closed", "overlay", False),
)

_MEASURE = """(sel) => {
    const side = document.getElementById('probe-side');
    if (!side) return {error: 'sidebar introuvable'};
    const box = side.getBoundingClientRect();
    const out = {
      w: Math.round(box.width), h: Math.round(box.height),
      overflowX: getComputedStyle(side).overflowX,
    };
    const clipped = [];
    for (const ic of side.querySelectorAll('iconify-icon')) {
      const b = ic.getBoundingClientRect();
      if (b.width === 0 && b.height === 0) continue;
      if (b.left < box.left - 1 || b.right > box.right + 1 ||
          b.top < box.top - 1 || b.bottom > box.bottom + 1) {
        clipped.push({
          icon: ic.getAttribute('icon'),
          dx: Math.round(Math.max(box.left - b.left, b.right - box.right)),
          dy: Math.round(Math.max(box.top - b.top, b.bottom - box.bottom)),
        });
      }
    }
    out.clipped = clipped;
    const toggle = document.querySelector(sel);
    if (toggle) {
      const tb = toggle.getBoundingClientRect();
      const glyph = toggle.querySelector('iconify-icon');
      const gb = glyph ? glyph.getBoundingClientRect() : null;
      out.toggle = {
        w: Math.round(tb.width), h: Math.round(tb.height),
        glyphW: gb ? Math.round(gb.width) : null,
        overflows: gb
          ? (gb.width > tb.width + 1 || gb.height > tb.height + 1)
          : null,
      };
    }
    return out;
}"""

#: Le libellé du TITRE et celui d'une ENTRÉE, nommés séparément.
#: ``[class*="truncate"]`` les matchait tous les deux et rendait le
#: premier du document — donc le titre, par accident de position. Depuis
#: que l'entrée fond elle aussi (2026-09-01), s'en remettre à l'ordre du
#: DOM ferait dire au probe qu'il mesure l'un pendant qu'il mesure
#: l'autre. Même règle que pour les deux boutons de repli, plus haut.
TITLE_TEXT = '#probe-side .text-2xl.truncate'
ITEM_LABEL = '#probe-side [aria-label="Home"] span.truncate'

_ARM_FRAMES = """(sel) => {
  const side = document.getElementById('probe-side');
  const label = document.querySelector(sel);
  window.__bzFrames = [];
  const t0 = performance.now();
  (function tick() {
    const cs = label ? getComputedStyle(label) : null;
    window.__bzFrames.push({
      t: Math.round(performance.now() - t0),
      w: Math.round(side.getBoundingClientRect().width),
      opacity: cs ? cs.opacity : null,
    });
    if (performance.now() - t0 < 700) requestAnimationFrame(tick);
  })();
}"""

_ITEM_GEOM = """(sel) => {
    const side = document.getElementById('probe-side');
    const label = document.querySelector(sel);
    if (!side || !label) return {error: 'entree ou libelle introuvable'};
    const row = label.closest('[aria-label="Home"]');
    const icon = row.querySelector('iconify-icon');
    const sb = side.getBoundingClientRect();
    const rb = row.getBoundingClientRect();
    const ib = icon.getBoundingClientRect();
    return {
      sideW: Math.round(sb.width),
      labelW: Math.round(label.getBoundingClientRect().width),
      // Écart entre le centre de l'icône et celui de la bande.
      dx: Math.round((ib.left + ib.width / 2) - (sb.left + sb.width / 2)),
      rowOverflow: Math.round(
        Math.max(sb.left - rb.left, rb.right - sb.right)),
    };
}"""

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/rail-titled", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"bench_sidebar_collapse n'a jamais demarre sur :{PORT}")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_sidebar_collapse.py")],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    tmp = Path(mkdtemp())
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            # ⚠️ 1000 px, pas 700 : sous ``md:`` (768) l'arête de repli
            # n'existe pas, et le probe mesurait alors un contrôle absent.
            pg = browser.new_page(viewport={"width": 1000, "height": 2400})

            print("A. Les huit cas, au repos")
            for route, mode, _opened in CASES:
                pg.goto(f"{BASE}/{route}")
                pg.wait_for_timeout(400)
                m = pg.evaluate(_MEASURE, TITLE_TOGGLE)
                pg.screenshot(path=str(tmp / f"{route}.png"))
                if m.get("error"):
                    check(f"{route} : la barre existe", False, m["error"])
                    continue
                # ``overlay`` est ``fixed inset-0`` et ``offcanvas`` replié
                # fait 0 px : leur boîte propre n'est PAS la référence, et
                # y comparer donne des faux positifs.
                if m["w"] > 0 and mode != "overlay":
                    check(f"{route} : aucune icone hors de la bande "
                          f"({m['w']}px)",
                          not m["clipped"], str(m["clipped"]))
                tg = m.get("toggle") or {}
                if tg.get("w"):
                    check(f"{route} : le glyphe tient dans son bouton",
                          not tg.get("overflows"),
                          f"glyphe {tg['glyphW']}px dans {tg['w']}x{tg['h']}")
                    if m["w"] > 0:
                        check(f"{route} : le bouton tient dans la bande",
                              tg["w"] <= m["w"],
                              f"bouton {tg['w']}px, bande {m['w']}px")

            print("\nB. Le CLIC — le repli est une transition")
            for route in ("rail-titled", "rail-untitled"):
                pg.goto(f"{BASE}/{route}")
                pg.wait_for_timeout(400)
                before = pg.evaluate(_MEASURE, EDGE)
                btn = pg.query_selector(EDGE)
                if btn is None:
                    check(f"{route} : l'arete de repli existe", False, EDGE)
                    continue
                btn.click()
                pg.wait_for_timeout(600)
                after = pg.evaluate(_MEASURE, EDGE)
                pg.screenshot(path=str(tmp / f"{route}-clicked.png"))
                check(f"{route} : le clic replie la barre",
                      before["w"] != after["w"],
                      f"{before['w']}px -> {after['w']}px")
                check(f"{route} : rien ne deborde apres le repli",
                      not after["clipped"],
                      f"{len(after['clipped'])} icone(s) — {after['clipped']}")

            print("\nC. Le libelle FOND-il, ou saute-t-il ?")
            for what, sel in (("titre", TITLE_TEXT),
                              ("libelle d'entree", ITEM_LABEL)):
                pg.goto(f"{BASE}/rail-titled")
                pg.wait_for_timeout(500)
                if pg.query_selector(sel) is None:
                    check(f"le {what} est identifie", False, sel)
                    continue
                pg.evaluate(_ARM_FRAMES, sel)
                btn = pg.query_selector(EDGE)
                if btn is None:
                    check("rail-titled : l'arete de repli existe", False, EDGE)
                    continue
                btn.click()
                pg.wait_for_timeout(900)
                frames = pg.evaluate("() => window.__bzFrames")
                mid = [
                    f for f in frames
                    if f["opacity"] is not None
                    and 0.05 < float(f["opacity"]) < 0.95
                ]
                check(f"le {what} FOND (opacite intermediaire echantillonnee)",
                      len(mid) >= 3,
                      f"{len(mid)} image(s) intermediaire(s) sur "
                      f"{len(frames)} — un ``display:none`` tue la "
                      f"transition, cf. le slot ``title_text`` du theme")

            print("\nD. Le fondu ne coute PAS le centrage de l'icone")
            # Le libellé d'entrée a porté ``hidden`` jusqu'au 2026-09-01
            # *parce que* ``display:none`` rend sa place sans discuter.
            # ``w-0`` + ``flex-none`` la rendent tout autant — mais c'est
            # exactement ce qu'il faut prouver, sinon le fondu se paie
            # d'une icône décalée dans la bande de 64 px.
            pg.goto(f"{BASE}/rail-titled")
            pg.wait_for_timeout(400)
            btn = pg.query_selector(EDGE)
            if btn is None:
                check("rail-titled : l'arete de repli existe", False, EDGE)
            else:
                btn.click()
                pg.wait_for_timeout(800)
                geom = pg.evaluate(_ITEM_GEOM, ITEM_LABEL)
                if geom.get("error"):
                    check("l'entree repliee est mesurable", False, geom["error"])
                else:
                    check("le libelle ne prend plus AUCUNE place",
                          geom["labelW"] == 0,
                          f"largeur {geom['labelW']}px")
                    check("l'icone reste centree dans la bande",
                          abs(geom["dx"]) <= 1,
                          f"centre icone a {geom['dx']}px du centre de "
                          f"la bande ({geom['sideW']}px)")
                    check("la ligne ne deborde pas de la bande",
                          geom["rowOverflow"] <= 0,
                          f"{geom['rowOverflow']}px hors de la bande")

            pg.screenshot(path=str(tmp / "sidebar_collapse.png"), full_page=True)
            print(f"\ncaptures -> {tmp}")
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    print()
    if FAILURES:
        print(f"PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("Tout vert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
