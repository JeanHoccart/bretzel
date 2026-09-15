"""Playwright probe — une transition d'``opacity`` DÉCLARÉE anime-t-elle ?

Sert ``examples.playground.main:app`` (uvicorn, port 8956).

Le fait mesuré
---------------
Un panneau qui s'ouvre doit fondre pour de vrai. Ce banc ARME une frise
``requestAnimationFrame`` sur l'élément AVANT le geste, joue le geste,
et relit les images.

Il est né d'un constat : sept éléments déclaraient ``transition-opacity``
alors que la lecture statique ne leur trouvait qu'UNE valeur d'opacité
atteignable — `alert` et les six panneaux flottants. Confirmé ici le
2026-09-04, opacité constante à 1 sur les sept. Depuis, treize panneaux
ancrés fondent et `alert` a perdu la classe au lieu de la gagner (il est
DANS le flux, un fondu sans effondrement de hauteur laisserait un trou).
Le banc sert maintenant à ce que ça le reste.

Pourquoi une frise et pas un ``getComputedStyle``
--------------------------------------------------
Un lecteur d'état lit l'APRÈS, pas la course : une opacité relue après
coup vaut 1 que la transition ait joué ou non. Il faut échantillonner
pendant. (Même leçon que la memory
``steady_state_instruments_miss_races``.)

⚠️ **Et pas depuis le panneau navigateur de Claude** : un onglet qui
n'est pas composé ne cadence pas ``requestAnimationFrame``, donc la
frise revient VIDE et se lit comme « rien ne bouge ». Mesuré le
2026-09-04 — trois tentatives à zéro image avant de comprendre que
l'instrument, pas le composant, était en cause. Playwright, lui, compose.

Le verdict par élément
-----------------------
- ``ANIMÉE``     : deux valeurs d'opacité au moins pendant l'ouverture ;
- ``INSTANTANÉE``: l'élément apparaît, mais à opacité constante ;
- ``INDÉTERMINÉ``: le geste n'a rien ouvert — le banc ne conclut PAS.
  C'est le piège qui a fait échouer la mesure du 2026-09-01 : un
  sélecteur qui visait un panneau que le geste n'ouvrait pas, lu comme
  un résultat.

Run :  py tests/probes/probe_dead_transition.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
REPO = HERE.parent.parent
PORT = 8956
BASE = f"http://127.0.0.1:{PORT}"

#: ``(nom, chemin, sélecteur du panneau, comment l'ouvrir)``. Le geste
#: est décrit en JS pour rester dans la page : le clic doit partir APRÈS
#: l'armement de la frise, dans le même tour.
CASES: list[tuple[str, str, str, str]] = [
    (
        "dropdown", "/dropdown", '[role="menu"]',
        "[...document.querySelectorAll('button')]"
        ".find(b => b.textContent.trim() === 'Actions')",
    ),
    (
        "popover", "/popover", '[role="dialog"]',
        "[...document.querySelectorAll('button')]"
        ".find(b => /Popover|Ouvrir|Open/i.test(b.textContent))",
    ),
    (
        "tooltip", "/tooltip", '[role="tooltip"]',
        "[...document.querySelectorAll('button')]"
        ".find(b => /Survole|Hover|Tooltip/i.test(b.textContent))",
    ),
    (
        "select", "/select", '[role="listbox"]',
        "document.querySelector('[role=\"combobox\"]')",
    ),
    (
        "combobox", "/combobox", '[role="listbox"]',
        # Le declencheur du combobox est un DIV role=combobox (pas un
        # input) : son clic ne fait que focus l'input interne, c'est ce
        # focus qui ouvre le panneau.
        "document.querySelector('[role=\"combobox\"] input')"
        " || document.querySelector('[role=\"combobox\"]')",
    ),
    (
        "sidebar_footer", "/", '[role="menu"]',
        "document.querySelector('aside button.group\\\\/acct')"
        " || [...document.querySelectorAll('aside button')].pop()",
    ),
    # ── Les panneaux ancrés rejoints le 2026-09-04 ────────────────────
    # Ils ne DÉCLARAIENT rien (donc ils échappaient au constat d'origine)
    # et ils apparaissaient d'un coup pendant que leurs voisins
    # fondaient. Le critère qui les a trouvés : ``bz-ref="bzpanel"``,
    # une SURFACE qui s'ouvre — pas « piloté par ``display`` », qui
    # ramasse aussi du contenu conditionnel.
    (
        "date_picker", "/date_picker", '[bz-ref="bzpanel"]',
        "document.querySelector('[bz-ref=\"bztrigger\"]')"
        " || [...document.querySelectorAll('input')][0]",
    ),
    (
        "time_picker", "/time_picker", '[bz-ref="bzpanel"]',
        "document.querySelector('[bz-ref=\"bztrigger\"]')"
        " || [...document.querySelectorAll('input')][0]",
    ),
    (
        "color_picker", "/color_picker", '[bz-ref="bzpanel"]',
        "document.querySelector('[bz-ref=\"bztrigger\"]')"
        " || [...document.querySelectorAll('button')][0]",
    ),
]

#: ``alert`` n'est pas un panneau : il est DANS le flux et sa fermeture
#: passe par le ``bz-show`` du dismiss. On mesure donc la disparition,
#: pas l'apparition.
ALERT_CASE = ("alert", "/alert")

#: **Les témoins.** ``dialog`` et ``drawer`` fondent pour de vrai : ils
#: restent MONTÉS et ``data-open`` pilote ``opacity-0`` + ``invisible``.
#: Sans eux, un banc cassé rendrait « INSTANTANÉE » partout et se lirait
#: comme une découverte. Un témoin qui ne dit pas ``ANIMÉE`` est un
#: échec de l'INSTRUMENT, et il invalide tous les verdicts au-dessus.
CONTROLS: list[tuple[str, str, str, str]] = [
    (
        "dialog", "/dialog", '[role="dialog"]',
        "[...document.querySelectorAll('button')]"
        ".find(b => /Dialog|Ouvrir|Open/i.test(b.textContent))",
    ),
    (
        # Le FOND, pas le panneau. Le panneau du drawer transitionne
        # ``translate``, jamais ``opacity`` — le viser rendait
        # « INSTANTANÉE » sur un composant parfaitement sain, et ce faux
        # rouge de témoin est exactement ce qu'un témoin doit produire
        # quand on se trompe de cible plutôt que de le laisser passer.
        "drawer (fond)", "/drawer", '[class*="bg-black/50"]',
        "[...document.querySelectorAll('button')]"
        ".find(b => /Drawer|Ouvrir|Open/i.test(b.textContent))",
    ),
]

FAILURES: list[str] = []
VERDICTS: dict[str, str] = {}


def wait_server(timeout: float = 40.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"playground never came up on :{PORT}")


#: Le script d'armement. Il prend le sélecteur du panneau et l'expression
#: du déclencheur, arme la frise sur TOUS les candidats, joue le geste,
#: et rend les images du seul qui s'est affiché.
ARM = """
([selector, triggerExpr, gesture]) => new Promise((resolve) => {
  const panels = [...document.querySelectorAll(selector)];
  const trigger = eval(triggerExpr);
  if (!trigger) { resolve({error: 'declencheur introuvable'}); return; }
  trigger.scrollIntoView({block: 'center'});

  const frames = [];
  const t0 = performance.now();
  let running = true;
  (function tick() {
    if (!running) return;
    const t = performance.now() - t0;
    panels.forEach((p, i) => {
      const cs = getComputedStyle(p);
      if (cs.display !== 'none' && cs.visibility !== 'hidden') {
        frames.push({t: Math.round(t), i, o: cs.opacity});
      }
    });
    requestAnimationFrame(tick);
  })();

  // Le geste part au tour SUIVANT : la frise doit tourner avant lui,
  // sinon la premiere image est deja l'etat ouvert.
  requestAnimationFrame(() => {
    if (gesture === 'hover') {
      const r = trigger.getBoundingClientRect();
      for (const type of ['pointerover', 'pointerenter', 'mouseover', 'mouseenter', 'mousemove']) {
        trigger.dispatchEvent(new MouseEvent(type, {
          bubbles: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
        }));
      }
      trigger.focus();
    } else {
      trigger.click();
    }
  });

  setTimeout(() => {
    running = false;
    resolve({frames, nPanels: panels.length, ticks: frames.length});
  }, 700);
})
"""


def verdict_of(result: dict) -> tuple[str, str]:
    """``(verdict, détail)`` — INDÉTERMINÉ si rien ne s'est ouvert."""
    if result.get("error"):
        return "INDÉTERMINÉ", result["error"]
    frames = result.get("frames") or []
    if not frames:
        return "INDÉTERMINÉ", "aucun panneau ne s'est affiché après le geste"
    values = sorted({f["o"] for f in frames})
    span = f"{frames[0]['t']}→{frames[-1]['t']} ms, {len(frames)} images"
    if len(values) > 1:
        return "ANIMÉE", f"opacités {values} ({span})"
    return "INSTANTANÉE", f"opacité constante {values[0]} ({span})"


def run_panels(page, cases, *, expect: str | None = None) -> None:
    for name, path, selector, trigger in cases:
        page.goto(BASE + path)
        page.wait_for_function(
            "document.documentElement.classList.contains('bz-ready')",
            timeout=20000,
        )
        gesture = "hover" if name == "tooltip" else "click"
        result = page.evaluate(ARM, [selector, trigger, gesture])
        verdict, detail = verdict_of(result)
        VERDICTS[name] = verdict
        print(f"  {verdict:13s} {name:16s} — {detail}")
        if verdict == "INDÉTERMINÉ":
            FAILURES.append(f"{name}: {detail}")
        elif expect and verdict != expect:
            FAILURES.append(
                f"TÉMOIN {name} : attendu {expect}, obtenu {verdict}. "
                f"C'est l'INSTRUMENT qui est en cause, pas le composant — "
                f"les verdicts qui suivent ne valent rien."
            )


ALERT_ARM = """
() => new Promise((resolve) => {
  // ``alert`` est le cas OPPOSE des six panneaux : le remede ne s'y
  // applique pas (il est DANS le flux, cf. son theme), donc on verifie
  // qu'il ne PROMET plus rien -- et qu'il se ferme toujours.
  const root = [...document.querySelectorAll('[bz-show="open"]')]
    .find(e => e.querySelector('button'));
  if (!root) { resolve({error: 'aucune alerte fermable sur la page'}); return; }
  const cs0 = getComputedStyle(root);
  // La PAIRE, pas la seule propriete : ``transition-property`` vaut
  // ``all`` par defaut, donc le lire seul ferait passer un
  // ``transition-all duration-200``, qui lui animerait bien l'opacite.
  // C'est la duree qui dit si quelque chose est promis.
  const declared = cs0.transitionProperty + ' / ' + cs0.transitionDuration;
  const x = root.querySelector('button');

  const frames = [];
  const t0 = performance.now();
  let running = true;
  (function tick() {
    if (!running) return;
    frames.push({t: Math.round(performance.now() - t0),
                 d: getComputedStyle(root).display});
    requestAnimationFrame(tick);
  })();
  requestAnimationFrame(() => x.click());
  setTimeout(() => {
    running = false;
    resolve({declared, gone: frames.findIndex(f => f.d === 'none')});
  }, 700);
})
"""


def run_alert(page) -> None:
    name, path = ALERT_CASE
    page.goto(BASE + path)
    page.wait_for_function(
            "document.documentElement.classList.contains('bz-ready')",
            timeout=20000,
        )
    result = page.evaluate(ALERT_ARM)
    if result.get("error"):
        VERDICTS[name] = "INDÉTERMINÉ"
        FAILURES.append(f"{name}: {result['error']}")
        print(f"  {'INDÉTERMINÉ':13s} {name:16s} — {result['error']}")
        return
    gone = result["gone"]
    declared = result["declared"]
    if gone < 0:
        VERDICTS[name] = "INDÉTERMINÉ"
        FAILURES.append(f"{name}: l'alerte n'a jamais disparu")
        print(f"  {'INDÉTERMINÉ':13s} {name:16s} — n'a jamais disparu")
        return
    # Le remède des panneaux ne s'applique pas à un élément DU FLUX :
    # ce qu'on garde ici, c'est qu'il ne PROMET plus un fondu.
    prop, _, duration = declared.partition(" / ")
    promises = (
        ("opacity" in prop or prop.strip() == "all")
        and duration.strip() not in ("", "0s")
    )
    VERDICTS[name] = "PROMET ENCORE" if promises else "NE PROMET RIEN"
    print(
        f"  {VERDICTS[name]:13s} {name:16s} — transition-property: "
        f"{declared!r}, display:none à l'image {gone}"
    )
    if promises:
        FAILURES.append(
            f"{name}: déclare encore une transition d'opacity "
            f"({declared!r}) alors que sa fermeture est un display:none. "
            f"Une alerte est DANS le flux — le remède des panneaux ne "
            f"s'y applique pas, cf. son thème."
        )


def main() -> int:
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "examples.playground.main:app",
            "--host", "127.0.0.1", "--port", str(PORT),
        ],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            print("\nTémoins — l'instrument DOIT les voir fondre\n")
            run_panels(page, CONTROLS, expect="ANIMÉE")
            print("\nLes panneaux, et l'alerte qui ne promet rien\n")
            run_panels(page, CASES)
            run_alert(page)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    dead = [n for n, v in VERDICTS.items() if v in ("INSTANTANÉE", "PROMET ENCORE")]
    live = [n for n, v in VERDICTS.items() if v == "ANIMÉE"]
    print(f"ANIMÉE : {live or '—'}")
    print(f"INSTANTANÉE (la classe ne sert à rien) : {dead or '—'}")
    if FAILURES:
        print(f"\n{len(FAILURES)} INDÉTERMINÉ — le banc ne conclut pas dessus :")
        for line in FAILURES:
            print("  -", line)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
