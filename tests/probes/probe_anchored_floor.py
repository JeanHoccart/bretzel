"""Probe : le plancher de largeur d'un panneau ancré (`bench_anchored_floor`).

Trois panneaux, trois verdicts. Les deux étroits doivent atteindre le
plancher (192 px) et rester lisibles ; le témoin large doit rendre
**exactement** la largeur de sa gâchette, comme avant le correctif.

    py tests/probes/probe_anchored_floor.py
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from tests.probes._serve import free_port

if __name__ != "__main__":
    raise RuntimeError(
        "probe_anchored_floor est un script : lance-le "
        "(`py tests/probes/probe_anchored_floor.py`), ne l'importe pas."
    )

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).parent
PORT = free_port()
URL = f"http://127.0.0.1:{PORT}/"

#: Le plancher posé dans ``06_helpers.js`` (``MIN_MATCHED_WIDTH``). Écrit
#: ici en clair : un probe qui relirait la constante depuis la source
#: qu'il teste serait vert quel que soit son contenu.
FLOOR = 192

#: L'arête de repli que la sidebar rend elle-même (cf.
#: ``probe_sidebar_collapse``) — c'est elle qui bascule ``data-open``.
EDGE = '#probe-side button[aria-label="Collapse or expand the sidebar"]'

VISIBLE = """(sel) => {
  const trig = document.querySelector(sel + ' [role=combobox]');
  if (!trig) return {found: false, w: 0, h: 0};
  const r = trig.getBoundingClientRect();
  return {found: true, w: r.width, h: r.height};
}"""

MEASURE = """(sel) => {
  const root = document.querySelector(sel);
  const trig = root.querySelector('[role=combobox]');
  const panel = root.querySelector('[role=listbox]');
  const opt = panel.querySelector('[role=option]');
  const t = trig.getBoundingClientRect();
  const p = panel.getBoundingClientRect();
  const o = opt.getBoundingClientRect();
  return {
    tw: t.width, th: t.height,
    pw: p.width, pleft: p.left, pright: p.right,
    minw: panel.style.minWidth, maxw: panel.style.maxWidth,
    oh: o.height,
    vw: window.innerWidth,
  };
}"""

srv = subprocess.Popen(
    [sys.executable, str(HERE / "bench_anchored_floor.py"), str(PORT)],
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


fail: list[str] = []
try:
    wait()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={"width": 1200, "height": 800})
        pg.goto(URL)
        pg.wait_for_selector("html.bz-ready")

        # ── La GÂCHETTE au repli ─────────────────────────────────
        # Deux mesures, pas une : « #hidden-select est invisible » ne
        # dit rien tout seul (une sidebar vide le dirait aussi). C'est
        # la PAIRE avec #rail-select, monté à l'identique sans la
        # classe, qui prouve que c'est bien le repli qui le cache.
        hid = pg.evaluate(VISIBLE, "#hidden-select")
        shown = pg.evaluate(VISIBLE, "#rail-select")
        ok_hidden = hid["w"] == 0 and hid["h"] == 0
        ok_pair = shown["w"] > 0 and shown["h"] > 0
        print("repli — gâchette cachée   %.0fx%.0f | témoin sans la classe "
              "%.0fx%.0f" % (hid["w"], hid["h"], shown["w"], shown["h"]))
        print("  [%s] la section marquée disparaît au repli"
              % ("PASS" if ok_hidden else "FAIL"))
        print("  [%s] celle qui ne l'est pas reste là"
              % ("PASS" if ok_pair else "FAIL"))
        if not (ok_hidden and ok_pair):
            fail.append("repli")

        # Le TÉMOIN passe en premier : sa hauteur d'option est la
        # référence des deux autres. Un seuil en dur (« 1,5 × la
        # gâchette ») tombait à 48,0 <= 48,0 sur l'état cassé — pile sur
        # le seuil, donc un check qui n'affirme rien.
        ref_option_h = 0.0
        for sel, label, narrow in (
            ("#wide-select", "témoin w-96", False),
            ("#rail-select", "sidebar repliée en rail", True),
            ("#box-select", "boîte w-16", True),
        ):
            pg.click(f"{sel} [role=combobox]")
            pg.wait_for_timeout(200)
            m = pg.evaluate(MEASURE, sel)
            print(
                f"{label:24s} gâchette={m['tw']:6.1f} panneau={m['pw']:6.1f}"
                f" (min={m['minw'] or '—'} max={m['maxw'] or '—'})"
                f" option_h={m['oh']:5.1f} left={m['pleft']:6.1f}"
            )

            if narrow:
                ok_w = m["pw"] >= FLOOR - 1
                print("  [%s] panneau >= %d px (plancher)"
                      % ("PASS" if ok_w else "FAIL", FLOOR))
            else:
                # Le témoin : le plancher ne doit RIEN changer au-dessus
                # de lui — même largeur que la gâchette, au pixel.
                ok_w = abs(m["pw"] - m["tw"]) <= 0.5
                print("  [%s] panneau == gâchette (%.1f px)"
                      % ("PASS" if ok_w else "FAIL", m["tw"]))

            # Une option tient sur une ligne. C'est la LISIBILITÉ, et
            # c'est ce que la largeur seule ne dit pas : un panneau
            # étroit enroule « Tous les portefeuilles » et l'option
            # double de hauteur. La référence est le témoin — même
            # composant, même taille, seule la largeur diffère — donc le
            # seuil n'est pas un chiffre choisi mais une comparaison.
            if not narrow:
                ref_option_h = m["oh"]
            budget = ref_option_h * 1.25
            ok_h = m["oh"] <= budget
            print("  [%s] option sur une ligne (%.1f <= %.1f, témoin=%.1f)"
                  % ("PASS" if ok_h else "FAIL", m["oh"], budget,
                     ref_option_h))

            # Élargir un panneau ne doit pas le pousser hors écran.
            ok_v = m["pleft"] >= 0 and m["pright"] <= m["vw"]
            print("  [%s] panneau dans le viewport"
                  % ("PASS" if ok_v else "FAIL"))

            if not (ok_w and ok_h and ok_v):
                fail.append(label)
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(120)

        # Capture avec les deux panneaux étroits ouverts n'a pas de sens
        # (un seul s'ouvre à la fois) : on rouvre celui du rail, le cas
        # réel, pour que l'image montre le bug tel que l'utilisateur l'a vu.
        pg.click("#rail-select [role=combobox]")
        pg.wait_for_timeout(200)
        pg.screenshot(path=str(HERE / "anchored_floor_screenshot.png"))
        # ── Et il revient au déploiement ─────────────────────────
        # Sans ça, « caché » serait indistinguable de « jamais rendu » —
        # exactement le vert à tort que ce dossier a déjà payé.
        pg.keyboard.press("Escape")
        pg.click(EDGE)
        pg.wait_for_timeout(600)
        back = pg.evaluate(VISIBLE, "#hidden-select")
        ok_back = back["w"] > 0 and back["h"] > 0
        print("déployé — gâchette de retour %.0fx%.0f"
              % (back["w"], back["h"]))
        print("  [%s] la section revient quand la sidebar se déploie"
              % ("PASS" if ok_back else "FAIL"))
        if not ok_back:
            fail.append("déploiement")

        browser.close()
finally:
    srv.terminate()
    srv.wait(timeout=10)

print("PROBE", "FAILED" if fail else "PASSED")
sys.exit(1 if fail else 0)
