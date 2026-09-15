"""Playwright probe — ce que coûte UN CLIC, bout en bout, dans Chromium.

Pilote ``bench_clic.py`` (uvicorn :8998) et décompose le trajet
« clic → DOM à jour » en trois segments, mesurés DANS la page :

    clic ──[réseau + serveur]──> réponse ──[runtime : morph + rescan]──> DOM

L'instrument est armé dans la page et relu après (memory
``steady_state_instruments_miss_races`` : sur quelques millisecondes,
sonder depuis Playwright efface le phénomène). Trois horloges :

- ``performance.now()`` capturé sur le clic, en capture ;
- l'entrée ``PerformanceResourceTiming`` du POST d'action, qui donne le
  temps serveur (``responseStart - requestStart``) et le transfert ;
- un ``MutationObserver`` sur la zone, qui date le moment où le DOM a
  bougé.

Ce que la mesure a établi le 2026-09-05
---------------------------------------

Le serveur est LINÉAIRE (~0,05 ms par composant re-rendu) et notre
``scan()`` aussi (~2,3 µs par nœud, ×2,0 par doublement). Le coût qui
s'emballe est **idiomorph**, qui morphe la région échangée : ×3,6 à
×4,0 par doublement, donc quadratique sur une longue liste de frères.
Vérifié que ce ne sont PAS les ``id=`` de Bretzel (une zone de 800
n'en porte qu'un, celui de la zone) : c'est le comportement de la
bibliothèque sur des fratries longues.

Conséquence pratique : sous ~200 composants dans une zone, un clic
coûte 13 à 30 ms et rien ne se sent. Au-delà, le client devient le
goulot et ça décroche vite (1 600 composants : 820 ms, dont 734 de
client).

⚠️ **Le mode compte.** En ``dev`` la page embarque
``@tailwindcss/browser``, qui observe le DOM et recompile sa feuille à
chaque mutation : il ajoute 20 à 40 % sur les grosses zones. Ce bench
lit ``$BZ_BENCH_MODE`` (défaut ``dev``) ; en ``prod`` la falaise est la
même, en moins creusée. Les chiffres ci-dessus sont en ``dev``.

Ce qu'il GARDE (seuils larges à dessein : la machine dérive d'un
facteur 2 à 3 — memory ``inprocess_ab_or_no_measurement``) :

1. un clic sur une petite zone (50 composants) reste sous 60 ms ;
2. **notre ``scan()`` reste linéaire** — c'est la moitié du coût client
   qui nous appartient, et la seule qu'on puisse régresser ;
3. le runtime ne domine pas le serveur sous 200 composants — le jour
   où il le ferait, la frontière a bougé ;
4. zéro erreur console.

Run :  py tests/probes/probe_clic.py
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
TAILLES = (1, 10, 50, 100, 200, 400, 800, 1600)
REPETITIONS = 7

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("clic bench never came up on :8998")


#: Arme les trois horloges. Rendu une fois par mesure, dans la page.
ARMER = """
(taille) => {
  window.__clic = null;
  const box = document.getElementById('box-' + taille);
  const btn = document.getElementById('btn-' + taille);
  const t0 = {v: 0};
  btn.addEventListener('click', () => { t0.v = performance.now(); },
                       {capture: true, once: true});
  const obs = new MutationObserver(() => {
    obs.disconnect();
    // Dater la mutation SANS attendre une frame : un rAF ajoute jusqu'à
    // 16 ms de son cru, ce qui a fait lire « 15,8 ms de runtime » sur
    // une zone d'UN composant. La frame est mesurée à part.
    const mut = performance.now();
    requestAnimationFrame(() => {
      const peint = performance.now();
      const post = performance.getEntriesByType('resource')
        .filter(e => e.name.includes('/_bretzel/action/'))
        .pop();
      window.__clic = {
        total: mut - t0.v,
        jusqua_peinture: peint - t0.v,
        serveur: post ? post.responseStart - post.requestStart : null,
        transfert: post ? post.responseEnd - post.responseStart : null,
        avant_envoi: post ? post.startTime - t0.v : null,
        octets: post ? (post.transferSize || post.encodedBodySize || 0) : 0,
        runtime: post ? mut - post.responseEnd : null,
        frame: peint - mut,
      };
    });
  });
  obs.observe(box, {childList: true, subtree: true, characterData: true});
}
"""


#: Sépare ce qui est À NOUS (``scan``) de ce qui est à idiomorph, sur des
#: clones détachés : les deux voient exactement le même sous-arbre.
ISOLER = """
() => {
  const out = [];
  for (const t of [200, 400, 800, 1600]) {
    const box = document.getElementById('box-' + t);
    if (!box) continue;
    const noeuds = box.querySelectorAll('*').length;

    const c1 = box.cloneNode(true);
    document.body.appendChild(c1);
    let a = performance.now();
    window.$bz._scan(c1);
    const scan = performance.now() - a;
    c1.remove();

    const c2 = box.cloneNode(true), c3 = box.cloneNode(true);
    const prem = c3.querySelector('span');
    if (prem) prem.textContent = 'changé';
    document.body.appendChild(c2);
    a = performance.now();
    window.Idiomorph.morph(c2, c3);
    const morph = performance.now() - a;
    c2.remove();

    out.push({t, noeuds, scan: +scan.toFixed(2), morph: +morph.toFixed(2)});
  }
  return out;
}
"""


def mesure_une(page, taille: int) -> dict:
    page.evaluate("() => performance.clearResourceTimings()")
    page.evaluate(ARMER, taille)
    page.click(f"#btn-{taille}")
    page.wait_for_function("() => window.__clic !== null", timeout=15000)
    return page.evaluate("() => window.__clic")


def mediane(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[len(xs) // 2]


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_clic.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda m: console_errors.append(m.text) if m.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            resultats: dict[int, dict] = {}
            print("\n  clic → DOM à jour, médiane de "
                  f"{REPETITIONS} clics (ms)\n")
            print(f"  {'zone':>6} {'total':>7} {'avant':>7} {'serveur':>8} "
                  f"{'transf':>7} {'runtime':>8} {'frame':>6} {'peint':>7} "
                  f"{'octets':>7}")
            for taille in TAILLES:
                mesure_une(page, taille)  # une à blanc : chemins chauds
                echs = [mesure_une(page, taille) for _ in range(REPETITIONS)]
                r = {
                    k: mediane([e[k] for e in echs if e[k] is not None])
                    for k in ("total", "jusqua_peinture", "serveur",
                              "transfert", "avant_envoi", "runtime", "frame")
                }
                r["octets"] = mediane([e["octets"] for e in echs])
                resultats[taille] = r
                print(f"  {taille:>6} {r['total']:7.1f} {r['avant_envoi']:7.1f} "
                      f"{r['serveur']:8.1f} {r['transfert']:7.1f} "
                      f"{r['runtime']:8.1f} {r['frame']:6.1f} "
                      f"{r['jusqua_peinture']:7.1f} {r['octets']:7.0f}")

            print()
            # ── Isoler ce qui est à NOUS de ce qui est à idiomorph ────
            isole = page.evaluate(ISOLER)
            print("  qui coûte, dans le client (ms) :")
            print()
            print(f"  {'zone':>6} {'nœuds':>7} {'scan() (à nous)':>17} "
                  f"{'idiomorph':>11}")
            for x in isole:
                print(f"  {x['t']:>6} {x['noeuds']:>7} {x['scan']:>17.1f} "
                      f"{x['morph']:>11.1f}")
            fac_scan = [
                isole[i]["scan"] / max(isole[i - 1]["scan"], 0.01)
                for i in range(1, len(isole))
            ]
            fac_morph = [
                isole[i]["morph"] / max(isole[i - 1]["morph"], 0.01)
                for i in range(1, len(isole))
            ]
            print()
            print(
                "  par doublement — scan x"
                f"{sum(fac_scan) / len(fac_scan):.1f}, idiomorph x"
                f"{sum(fac_morph) / len(fac_morph):.1f}"
            )
            print()

            moyenne, grande = resultats[50], resultats[200]
            check(
                "un clic sur une zone de 50 composants reste sous 60 ms",
                moyenne["total"] < 60,
                f"{moyenne['total']:.1f} ms",
            )
            moy_scan = sum(fac_scan) / len(fac_scan)
            moy_morph = sum(fac_morph) / len(fac_morph)
            check(
                "notre scan() reste LINÉAIRE — et nettement sous le morph",
                moy_scan < 2.8 and moy_scan < moy_morph * 0.8,
                f"scan x{moy_scan:.1f} par doublement contre "
                f"x{moy_morph:.1f} pour idiomorph. Un scan qui rejoint le "
                "morph est une régression À NOUS : le morph vient de la "
                "bibliothèque, le scan est notre code. Le CONTRASTE est "
                "gardé en plus du seuil absolu parce qu'une machine "
                "chargée gonfle les deux ensemble.",
            )
            check(
                "sous 200 composants le client ne domine pas le serveur",
                grande["runtime"] <= grande["serveur"] * 1.6,
                f"runtime {grande['runtime']:.1f} ms vs serveur "
                f"{grande['serveur']:.1f} ms — la frontière a bougé",
            )
            check("zéro erreur console", not console_errors, str(console_errors[:3]))

            page.screenshot(path=str(HERE / "clic_screenshot.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S)")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
