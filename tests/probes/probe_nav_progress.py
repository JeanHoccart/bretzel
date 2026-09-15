"""Playwright probe — la barre de progression de navigation (:8987).

Meme instrument que ``probe_pending.py``, et pour la meme raison : on
prouve une ABSENCE pendant quelques dizaines de millisecondes, ce qu'un
``getComputedStyle`` appele apres coup rate et qu'un sondage depuis
Playwright efface. La frise est armee DANS la page avant le clic.

Quatre verdicts :

1. au repos la barre est cachee, et elle l'est des le HTML servi (le
   ``style="display:none"`` pre-pose) — sinon elle clignote a chaque
   chargement de page ;
2. lien BOOSTE vers une page a 700 ms → la barre vient, pas avant le
   seuil de 200 ms ;
3. item de SIDEBAR (pas boost : ``hx-get`` + ``hx-push-url``) → la
   barre vient aussi. C'est le versant que tester le boost seul
   raterait ;
4. navigation RAPIDE → la barre n'apparait a aucune frame.

Run :  py tests/probes/probe_nav_progress.py
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
FAILURES: list[str] = []

BAR = "#bz-nav-progress"

ARM = """(sel) => {
  window.__frise = { t0: performance.now(), rows: [], stop: false };
  const f = window.__frise;
  function tick() {
    if (f.stop) return;
    const el = document.querySelector(sel);
    f.rows.push({
      t: performance.now() - f.t0,
      shown: el ? getComputedStyle(el).display !== "none" : null,
    });
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}"""

READ = """() => { window.__frise.stop = true; return window.__frise.rows; }"""

SHOWN = """(sel) => {
  const el = document.querySelector(sel);
  return el ? getComputedStyle(el).display !== "none" : null;
}"""


def first_shown(rows):
    for r in rows:
        if r["shown"]:
            return r["t"]
    return None


def check(cond, msg):
    print(f"   [{'ok ' if cond else 'RED'}] {msg}")
    if not cond:
        FAILURES.append(msg)


def navigate(page, selector, settle_ms):
    """Arme la frise, clique, laisse retomber, rend la frise."""
    page.evaluate(ARM, BAR)
    page.click(selector)
    page.wait_for_timeout(settle_ms)
    return page.evaluate(READ)


def main():
    srv = subprocess.Popen(
        [sys.executable, str(HERE / "bench_nav_progress.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                urllib.request.urlopen(BASE + "/", timeout=1)
                break
            except OSError:
                time.sleep(0.3)

        # Le HTML SERVI, avant tout JavaScript : la garde anti-clignotement
        # doit etre dans les octets, pas posee par le runtime au boot.
        served = urllib.request.urlopen(BASE + "/", timeout=5).read().decode("utf-8")
        print("\n  0. dans le HTML servi")
        check('id="bz-nav-progress"' in served, "la barre est dans le shell")
        check('style="display:none"' in served.split('id="bz-nav-progress"')[1][:400],
              "elle est pre-cachee cote serveur (pas de clignotement au load)")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1100, "height": 800})
            page.goto(BASE + "/")
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )
            page.wait_for_timeout(200)

            print("\n  1. au repos")
            check(page.evaluate(SHOWN, BAR) is False, "barre cachee au repos")

            print("\n  2. lien BOOSTE vers la page lente (700 ms)")
            rows = navigate(page, '[data-probe="lien-lent"]', 1400)
            t = first_shown(rows)
            print(f"   {len(rows)} frames ; barre a {t} ms")
            check(t is not None, "la barre est venue sur un lien booste")
            # 150 et non 200 : l'armement precede le clic de quelques
            # frames, et le rAF echantillonne a ~16 ms pres.
            check(t is not None and t >= 150,
                  f"pas avant le seuil (vue a {t} ms)")
            check(page.evaluate(SHOWN, BAR) is False,
                  "re-cachee une fois la page arrivee")

            print("\n  3. item de SIDEBAR (hx-get + hx-push-url, pas boost)")
            page.goto(BASE + "/")
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )
            page.wait_for_timeout(200)
            rows = navigate(page, 'a[href="/lente"]', 1400)
            t = first_shown(rows)
            print(f"   {len(rows)} frames ; barre a {t} ms")
            check(t is not None,
                  "la barre est venue sur une nav de sidebar")
            check(t is not None and t >= 150,
                  f"pas avant le seuil (vue a {t} ms)")

            print("\n  4. navigation RAPIDE — aucune apparition attendue")
            page.goto(BASE + "/")
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )
            page.wait_for_timeout(200)
            rows = navigate(page, '[data-probe="lien-rapide"]', 900)
            t = first_shown(rows)
            print(f"   {len(rows)} frames ; premiere apparition : {t}")
            check(t is None, f"barre jamais apparue (vue a {t})")

            print("\n  5. capture pendant la navigation lente")
            page.goto(BASE + "/")
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )
            page.wait_for_timeout(200)
            page.click('[data-probe="lien-lent"]')
            page.wait_for_timeout(400)
            page.screenshot(path=str(HERE / "nav_progress_inflight.png"))
            print("   screenshot -> nav_progress_inflight.png")
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)

    print()
    if FAILURES:
        print(f"NAV PROGRESS PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("NAV PROGRESS PROBE PASSED — les deux formes de nav, seuil respecte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
