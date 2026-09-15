"""Playwright probe — ``ui.pending()`` : le témoin d'action en vol (:8986).

Ce que ce probe mesure, et pourquoi il le mesure DANS la page
-------------------------------------------------------------
Le seuil de 200 ms est la raison d'être de ``ui.pending()`` : sous ce
délai, un spinner produit un flash qui fait paraître l'interface plus
lente que si rien ne s'affichait. Le vérifier, c'est prouver une
ABSENCE pendant quelques dizaines de millisecondes — exactement le
genre de phénomène qu'un ``getComputedStyle`` appelé après coup rate,
et qu'un sondage depuis Playwright efface (cf. la memory « un bug
intermittent ne se mesure pas avec getComputedStyle »).

Donc on arme un échantillonneur ``requestAnimationFrame`` DANS la page
avant le clic, et on relit la frise après. Les quatre verdicts :

1. au repos, rien n'est visible ;
2. action rapide (10 ms) → le spinner n'apparaît **à aucune frame** ;
3. action lente (700 ms) → il apparaît, et **pas avant ~200 ms** ;
4. ``after=0`` → la désactivation, elle, est immédiate.

Plus l'adressage à distance : un squelette ailleurs dans le DOM suit la
même action, et tout revient au repos après la réponse.

Run :  py tests/probes/probe_pending.py
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

SLOW_SPIN = '[data-probe="slow"] span[role="status"]'
FAST_SPIN = '[data-probe="fast"] span[role="status"]'
REMOTE = '[data-probe="remote"]'
IMMEDIATE = '[data-probe="immediate"]'

# L'échantillonneur : une frise par frame, armée avant le clic. On
# enregistre le display calculé (le spinner et le squelette basculent en
# bz-show → display:none) et l'état ``disabled`` du bouton after=0.
ARM = """({sels, btn}) => {
  window.__frise = { t0: performance.now(), rows: [], stop: false };
  const f = window.__frise;
  function tick() {
    if (f.stop) return;
    const row = { t: performance.now() - f.t0 };
    for (const [name, sel] of Object.entries(sels)) {
      const el = document.querySelector(sel);
      row[name] = el ? getComputedStyle(el).display !== "none" : null;
    }
    const b = document.querySelector(btn);
    row.disabled = b ? b.disabled : null;
    f.rows.push(row);
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}"""

READ = """() => { window.__frise.stop = true; return window.__frise.rows; }"""

#: L'état à l'instant t, hors frise — pour les deux constats de repos.
SNAPSHOT = """(s) => Object.fromEntries(Object.entries(s).map(([k, sel]) => {
  const el = document.querySelector(sel);
  return [k, el ? getComputedStyle(el).display !== 'none' : null];
}))"""


def first_true(rows, key):
    """Instant (ms depuis l'armement) de la première frame où ``key`` est vrai."""
    for r in rows:
        if r.get(key):
            return r["t"]
    return None


def check(cond, msg):
    print(f"   [{'ok ' if cond else 'RED'}] {msg}")
    if not cond:
        FAILURES.append(msg)


def main():
    srv = subprocess.Popen(
        [sys.executable, str(HERE / "bench_pending.py"), str(PORT)],
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
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 900})
            page.goto(BASE + "/")
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )
            page.wait_for_timeout(200)

            sels = {"slow": SLOW_SPIN, "fast": FAST_SPIN, "remote": REMOTE}
            vis = page.evaluate(SNAPSHOT, sels)
            print("\n  1. au repos")
            check(vis["slow"] is False, f"spinner slow caché au repos (vu {vis['slow']})")
            check(vis["fast"] is False, f"spinner fast caché au repos (vu {vis['fast']})")
            check(vis["remote"] is False,
                  f"squelette distant caché au repos (vu {vis['remote']})")

            print("\n  2. action rapide (10 ms) — aucune apparition attendue")
            page.evaluate(ARM, {"sels": sels, "btn": IMMEDIATE})
            page.click('[data-probe="fast"]')
            page.wait_for_timeout(700)
            rows = page.evaluate(READ)
            t_fast = first_true(rows, "fast")
            print(f"   {len(rows)} frames échantillonnées")
            check(t_fast is None,
                  f"spinner fast jamais apparu (première apparition : {t_fast})")

            print("\n  3. action lente (700 ms) — apparition, mais pas avant 200 ms")
            page.evaluate(ARM, {"sels": sels, "btn": IMMEDIATE})
            page.click('[data-probe="slow"]')
            page.wait_for_timeout(400)
            page.screenshot(path=str(HERE / "pending_inflight.png"), full_page=True)
            page.wait_for_timeout(900)
            rows = page.evaluate(READ)
            t_slow = first_true(rows, "slow")
            t_remote = first_true(rows, "remote")
            print(f"   {len(rows)} frames ; spinner à {t_slow} ms, "
                  f"squelette distant à {t_remote} ms")
            check(t_slow is not None, "spinner slow apparu")
            # Seuil à 150 ms et non 200 : l'armement précède le clic de
            # quelques frames, et le rAF échantillonne à ~16 ms près.
            check(t_slow is not None and t_slow >= 150,
                  f"spinner slow pas avant le seuil (apparu à {t_slow} ms)")
            check(t_remote is not None,
                  "squelette distant suivi par adressage handler")

            print("\n  4. retour au repos après la réponse")
            vis = page.evaluate(SNAPSHOT, sels)
            check(vis["slow"] is False, f"spinner slow re-caché (vu {vis['slow']})")
            check(vis["remote"] is False,
                  f"squelette distant re-caché (vu {vis['remote']})")

            print("\n  5. after=0 — désactivation immédiate")
            page.evaluate(ARM, {"sels": sels, "btn": IMMEDIATE})
            page.click(IMMEDIATE)
            page.wait_for_timeout(900)
            rows = page.evaluate(READ)
            t_dis = first_true(rows, "disabled")
            print(f"   désactivé à {t_dis} ms")
            check(t_dis is not None and t_dis < 150,
                  f"bouton after=0 désactivé sans seuil (à {t_dis} ms)")
            check(page.evaluate("(s) => !document.querySelector(s).disabled",
                                IMMEDIATE),
                  "bouton after=0 réactivé après la réponse")

            print("\n  screenshot → pending_inflight.png")
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)

    print()
    if FAILURES:
        print(f"PENDING PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("PENDING PROBE PASSED — seuil respecté, adressage distant OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
