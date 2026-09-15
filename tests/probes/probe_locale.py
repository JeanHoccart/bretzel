"""Playwright probe — un calendrier parle la langue de l'app.

Drives ``bench_locale.py`` DEUX FOIS (``BENCH_LANG=en`` puis ``fr``) sur
le port 8978, dans un vrai Chromium.

Pourquoi ce probe et pas une assertion de HTML
-----------------------------------------------
Parce que le serveur n'emet plus AUCUN nom de mois : il ne peut pas les
produire (le module ``locale`` de Python est un etat global au processus,
et Babel serait une dependance). C'est ``Intl`` qui les fabrique dans la
page, depuis ``<html lang>``. Une assertion sur le HTML rendu verrait
donc un trou et ne pourrait rien en conclure — c'est exactement le mode
de panne que ce probe existe pour couvrir.

Quatre mesures, dans l'ordre ou elles comptent :

1. ``<html lang>`` porte bien ce que l'app a declare ;
2. l'en-tete du calendrier AUTO nomme le mois dans cette langue, et pas
   dans l'autre — mesure croisee, sinon « aout » passerait pour de
   l'anglais si rien ne changeait ;
3. les sept jours sont nommes, non vides, et DIFFERENTS d'une langue a
   l'autre ;
4. le calendrier a liste EXPLICITE ignore la langue — l'echappatoire
   tier 2 gagne toujours.

Run :  py tests/probes/probe_locale.py
"""

from __future__ import annotations

import os
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

#: Les memes que dans le bench — repetes ici expres : un probe qui
#: importe son bench ne prouve plus qu'ils s'accordent.
MADE_UP_MONTH = "M08"
MADE_UP_WEEKDAY = "J0"

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout: float = 60.0) -> None:
    """Attendre le bench — et DISTINGUER « pas encore la » de « casse ».

    ``HTTPError`` derive d'``OSError`` : un ``except OSError`` avale donc
    un 500 et attend soixante secondes une app deja demarree, pour finir
    sur « n'est jamais venu ». C'est exactement ce qui vient de se passer
    ici (un ``ui.box`` inexistant dans le bench), et c'est la neuvieme
    fois qu'une sonde de ce depot ment sur ce qu'elle mesure.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"le bench repond {exc.code} — il est demarre et CASSE, "
                f"pas absent. Lance-le seul pour voir la trace : "
                f"BENCH_LANG=fr py tests/probes/bench_locale.py"
            ) from exc
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("locale bench never came up on :8978")


MEASURE = """() => {
  const read = (id) => {
    const root = document.querySelector('#' + id);
    const header = root.querySelector('[data-bz-cal-header]');
    const days = [...root.querySelectorAll('[data-bz-cal-weekdays] > div')]
      .map(d => d.textContent.trim());
    return {
      header: header ? header.textContent.replace(/\\s+/g, ' ').trim() : '',
      days: days,
    };
  };
  return {
    lang: document.documentElement.getAttribute('lang'),
    auto: read('auto'),
    explicit: read('explicit'),
    dismiss: (document.querySelector('#alert button[aria-label]') || {})
      .getAttribute ? document.querySelector('#alert button[aria-label]')
        .getAttribute('aria-label') : null,
  };
}"""


def refuse_a_squatted_port() -> None:
    """Refuser de mesurer le serveur de QUELQU'UN D'AUTRE.

    ``uvicorn`` n'arrete pas le processus quand le bind echoue : il
    journalise l'erreur et rend la main, donc le probe croit avoir
    demarre son banc alors qu'il interroge celui d'a cote. Mesure du
    2026-08-25 : le banc de l'utilisateur tournait en ``en``, mes deux
    lancements l'ont interroge, et le probe a rougi sur la langue —
    en accusant le code, pas la collision.

    C'est le piege n°7 du chantier CRM (« une collision de port a fait
    rougir un probe qui allait bien »), et la seule facon de ne plus s'y
    faire prendre est de regarder AVANT.
    """
    try:
        with urllib.request.urlopen(BASE + "/", timeout=1):
            occupied = True
    except urllib.error.HTTPError:
        occupied = True
    except OSError:
        occupied = False
    if occupied:
        raise RuntimeError(
            f"{BASE} repond DEJA — un autre serveur tient le port 8978. "
            f"Ce probe demarre le sien : mesurer celui d'un voisin donnerait "
            f"un rouge qui n'accuse pas le bon coupable. Arrete-le et relance."
        )


def run_one(pw, lang: str) -> dict:
    refuse_a_squatted_port()
    env = dict(os.environ, BENCH_LANG=lang)
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_locale.py"), str(PORT)],
        cwd=HERE.parent.parent, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        page.goto(BASE + "/")
        page.wait_for_selector("html.bz-ready", state="attached")
        page.wait_for_timeout(600)
        out = page.evaluate(MEASURE)
        page.screenshot(path=str(HERE / f"locale_{lang}_screenshot.png"))
        browser.close()
        return out
    finally:
        server.terminate()
        server.wait(timeout=10)
        # Laisser le port se liberer avant la seconde app.
        time.sleep(1.0)


def main() -> int:
    with sync_playwright() as pw:
        en = run_one(pw, "en")
        fr = run_one(pw, "fr")

    print(f"\nen : lang={en['lang']!r} header={en['auto']['header']!r}")
    print(f"     jours={en['auto']['days']}")
    print(f"fr : lang={fr['lang']!r} header={fr['auto']['header']!r}")
    print(f"     jours={fr['auto']['days']}")
    print(f"explicite (fr) : header={fr['explicit']['header']!r} "
          f"jours={fr['explicit']['days']}")

    print("\n(1) la langue declaree arrive dans le document")
    check("en", en["lang"] == "en", f"lang = {en['lang']!r}")
    check("fr", fr["lang"] == "fr", f"lang = {fr['lang']!r}")

    print("\n(2) le mois est nomme dans la langue de l'app")
    check("l'anglais dit August", "August" in en["auto"]["header"],
          f"en-tete = {en['auto']['header']!r}")
    check("le francais ne dit PAS August", "August" not in fr["auto"]["header"],
          f"en-tete = {fr['auto']['header']!r}")
    check("le francais nomme quand meme le mois",
          any(c.isalpha() for c in fr["auto"]["header"]),
          f"en-tete = {fr['auto']['header']!r}")

    print("\n(3) les sept jours sont nommes, et differents d'une langue a l'autre")
    for tag, got in (("en", en), ("fr", fr)):
        days = got["auto"]["days"]
        check(f"{tag} : sept colonnes", len(days) == 7, f"{len(days)} colonne(s)")
        check(f"{tag} : aucune vide", all(d for d in days), f"{days}")
    check("les deux langues ne donnent pas les memes jours",
          en["auto"]["days"] != fr["auto"]["days"],
          f"identiques : {en['auto']['days']}")

    print("\n(4) une liste explicite gagne sur la langue")
    check("le mois vient de la liste", MADE_UP_MONTH in fr["explicit"]["header"],
          f"en-tete = {fr['explicit']['header']!r}")
    check("les jours viennent de la liste",
          MADE_UP_WEEKDAY in fr["explicit"]["days"],
          f"jours = {fr['explicit']['days']}")

    print("\n(5) les mots du framework suivent texts=")
    check("en : le defaut anglais", en["dismiss"] == "Dismiss alert",
          f"aria-label = {en['dismiss']!r}")
    check("fr : la surcharge", fr["dismiss"] == "Fermer l'alerte",
          f"aria-label = {fr['dismiss']!r}")

    print(f"\nScreenshots -> {HERE / 'locale_fr_screenshot.png'}")
    if FAILURES:
        print(f"\n{len(FAILURES)} ECHEC(S) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nTout vert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
