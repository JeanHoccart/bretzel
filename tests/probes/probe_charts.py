"""Playwright probe — charts V3 tooltips + legend, BLOCKING gate.

Drives ``bench_charts.py`` (uvicorn :8956) :

Bar :
1. Hovering a bar shows the floating tooltip (.bz-chart-tooltip) with
   the bar's data label, opacity 1.
2. Leaving hides it.

Line (multi-series) :
3. The legend has 2 toggle buttons ; both series paths visible at rest.
4. Clicking a legend button hides that series' path (bz-show).
5. The "can't hide the last series" guard : after hiding one, clicking
   the remaining one does NOT hide it.

Pie :
6. Hovering a wedge shows the tooltip.

Scatter :
7. Un point au repos est translucide (deux points superposés doivent se
   voir) et le survol le rend PLEIN. Cette paire est arrivée le
   2026-09-01 avec le scatter du banc : le slot ``dot`` annonçait un
   « hover-pop effect » que personne ne survolait, et qui n'existait
   pas — la translucidité est sur le ``fill``, or les deux classes
   visaient ``opacity``, déjà à 1 au repos.

8. Zero JS console errors. Screenshot with the bar tooltip up.

Run :  py tests/probes/probe_charts.py
"""

from __future__ import annotations

import re
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

FAILURES: list[str] = []


def _alpha(css_color: str) -> float:
    """L'alpha d'une couleur calculée, quelle que soit sa notation.

    Chromium résout ``fill-(--bz-solid)/70`` en ``oklab(… / 0.7)`` et la
    forme pleine en ``rgb(…)`` : les deux chaînes ne se comparent pas,
    et c'est l'alpha — pas la teinte — que ce probe juge.
    """
    m = re.search(r"/\s*([0-9.]+)\s*\)", css_color)
    if m:
        return float(m.group(1))
    m = re.search(r"rgba\([^)]*,\s*([0-9.]+)\s*\)", css_color)
    return float(m.group(1)) if m else 1.0


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("charts bench never came up on :8956")


def tooltip_opacity(page) -> float:
    return page.evaluate(
        "() => { const t = document.querySelector('.bz-chart-tooltip'); "
        "return t ? parseFloat(getComputedStyle(t).opacity) : -1; }"
    )


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_charts.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1000, "height": 1100})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            # ── Bar tooltip ───────────────────────────────────────────
            print("\nBar — hover tooltip")
            bar = page.locator("#bar-wrap rect[data-bz-display]").first
            check("bars carry data-bz-display", bar.count() >= 1 or bar.is_visible())
            bar.hover(force=True)
            page.wait_for_function(
                "() => { const t = document.querySelector('.bz-chart-tooltip'); "
                "return t && parseFloat(getComputedStyle(t).opacity) > 0.5; }"
            )
            check("hovering a bar shows the tooltip", tooltip_opacity(page) > 0.5)
            tip_text = page.evaluate(
                "document.querySelector('.bz-chart-tooltip').textContent"
            )
            check("tooltip carries a data label", len(tip_text.strip()) > 0,
                  f"text={tip_text!r}")
            page.screenshot(path=str(HERE / "charts_screenshot.png"))
            # move away
            page.mouse.move(5, 5)
            page.wait_for_function(
                "() => { const t = document.querySelector('.bz-chart-tooltip'); "
                "return !t || parseFloat(getComputedStyle(t).opacity) < 0.5; }"
            )
            check("leaving hides the tooltip", tooltip_opacity(page) < 0.5)

            # ── Line legend toggle ────────────────────────────────────
            print("\nLine — legend toggle + last-series guard")
            legend_btns = page.locator("#line-wrap [aria-pressed]")
            n_legend = legend_btns.count()
            check("legend has 2 toggle buttons", n_legend == 2, f"found {n_legend}")

            # ⚠️ ``path[bz-show]``, et pas ``[data-series-index]``.
            #
            # Cette fonction cherchait un attribut qui n'existe NULLE PART
            # dans ``bretzel/`` — des deux côtés de son sélecteur — et
            # elle était **définie sans jamais être appelée**. Deux
            # défauts qui se cachaient l'un l'autre : morte, elle ne
            # pouvait pas rendre 0 et faire rougir qui que ce soit.
            #
            # Le vrai marqueur d'une série est sa directive ``bz-show``,
            # et le clic de légende pose ``display: none`` dessus. Mesuré
            # le 2026-08-26.
            def visible_series() -> int:
                return page.evaluate(
                    "() => [...document.querySelectorAll('#line-wrap path[bz-show]')]"
                    ".filter(e => getComputedStyle(e).display !== 'none').length"
                )

            # Le clic bascule l'attribut du bouton — ET FAIT DISPARAÎTRE
            # la série. Seule la première moitié était vérifiée : le
            # commentaire disait « its series hides » au-dessus d'un check
            # qui ne regardait que ``aria-pressed``. Un bouton qui bascule
            # sans rien cacher aurait passé.
            before_visible = visible_series()
            check("les deux series sont tracees au depart",
                  before_visible == 2, f"{before_visible} chemin(s) visible(s)")
            before_pressed = legend_btns.first.get_attribute("aria-pressed")
            legend_btns.first.click()
            page.wait_for_timeout(150)
            after_pressed = legend_btns.first.get_attribute("aria-pressed")
            check("clicking a legend toggles its aria-pressed",
                  after_pressed != before_pressed,
                  f"{before_pressed} -> {after_pressed}")
            after_visible = visible_series()
            check("...et CACHE vraiment la serie",
                  after_visible == before_visible - 1,
                  f"{before_visible} -> {after_visible} chemin(s) visible(s)")

            # Garde : la dernière série encore allumée ne peut pas être
            # cachée. Là encore on mesure les DEUX : le bouton refuse de
            # basculer, et le tracé reste à l'écran.
            second = legend_btns.nth(1)
            sec_before = second.get_attribute("aria-pressed")
            second.click()
            page.wait_for_timeout(150)
            sec_after = second.get_attribute("aria-pressed")
            check("can't hide the last visible series (guard holds)",
                  sec_after == sec_before,
                  f"second went {sec_before} -> {sec_after}")
            check("...et la derniere serie est toujours tracee",
                  visible_series() == 1,
                  f"{visible_series()} chemin(s) visible(s) apres la garde")

            # ── Pie tooltip ───────────────────────────────────────────
            print("\nPie — hover tooltip")
            wedge = page.locator("#pie-wrap path[data-bz-display]").first
            wedge.hover(force=True)
            page.wait_for_function(
                "() => { const t = document.querySelector('.bz-chart-tooltip'); "
                "return t && parseFloat(getComputedStyle(t).opacity) > 0.5; }"
            )
            check("hovering a pie wedge shows the tooltip", tooltip_opacity(page) > 0.5)

            # ── Scatter : le survol rend le point PLEIN ───────────────
            print("\nScatter — le survol rend le point plein")
            dot = page.locator("#scatter-wrap circle").first
            rest = dot.evaluate("e => getComputedStyle(e).fill")
            dot.hover(force=True)
            page.wait_for_timeout(400)
            hovered = dot.evaluate("e => getComputedStyle(e).fill")
            # Le point est translucide au repos POUR une raison : deux
            # points superposés doivent se voir. Ce qu'on vérifie ici est
            # que le survol lève cette translucidité — et l'alpha est la
            # seule lecture qui le dise, la chaîne changeant d'espace
            # colorimétrique au passage (``oklab(… / 0.7)`` → ``rgb(…)``).
            check("un point au repos est translucide",
                  _alpha(rest) < 0.95, f"fill au repos : {rest}")
            check("le survol le rend plein",
                  _alpha(hovered) > 0.99, f"fill au survol : {hovered}")

            check("no JS console errors", not console_errors, "; ".join(console_errors[:6]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"CHARTS PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("CHARTS PROBE PASSED — tooltips + legend charts V3 fonctionnels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
