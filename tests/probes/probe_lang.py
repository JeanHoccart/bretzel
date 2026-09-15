"""Playwright probe — la langue resolue par requete (:8988).

Trois maillons, et seul un navigateur peut les mesurer ensemble :

1. **l'en-tete decide a la premiere visite** — un contexte Playwright en
   ``locale="fr-FR"`` envoie un vrai ``Accept-Language`` ;
2. **le calendrier suit sans traduction** — ses noms de mois sont
   derives par ``Intl`` DANS le navigateur, a partir du ``<html lang>``
   que le shell pose. C'est la moitie de la chaine qu'aucun test
   serveur ne peut voir : le HTML servi ne contient AUCUN nom de mois ;
3. **``Language.set`` pose le cookie et fait recharger** (``HX-Refresh``),
   et le cookie gagne ensuite sur l'en-tete — c'est ce maillon qui rend
   un selecteur de langue possible, et c'est celui qui casserait en
   silence si on inversait l'ordre de la chaine.

Run :  py tests/probes/probe_lang.py
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

#: Les deux contextes doivent partager la meme taille, sinon les captures
#: ne se comparent pas.
VIEWPORT = {"width": 900, "height": 800}


def check(cond, msg):
    print(f"   [{'ok ' if cond else 'RED'}] {msg}")
    if not cond:
        FAILURES.append(msg)


def settle(page, wait=300):
    """Attendre que le runtime ait pris la main, puis lire l'etat."""
    page.wait_for_function(
        "document.documentElement.classList.contains('bz-ready')")
    page.wait_for_timeout(wait)
    return read_state(page)


def visit(page, wait=300):
    page.goto(BASE + "/")
    return settle(page, wait)


def read_state(page):
    """Ce que la page affiche vraiment, des deux cotes de la frontiere."""
    return page.evaluate("""() => {
      const a = document.querySelector('[data-probe="alert"] [aria-label]');
      const cal = document.querySelector('[data-probe="cal"]');
      // Le libelle de mois est le premier texte du header du calendrier.
      // ``fromCharCode(10)`` plutot qu'un saut echappe : ce JS voyage
      // dans une chaine Python NON brute, ou l'antislash est mange et
      // le navigateur recoit un vrai saut de ligne AU MILIEU d'un
      // litteral — SyntaxError, vecu en ecrivant ce fichier.
      const header = cal
        ? cal.innerText.split(String.fromCharCode(10)).filter(Boolean)[0]
        : '';
      return {
        html_lang: document.documentElement.lang,
        dismiss: a ? a.getAttribute('aria-label') : null,
        calendar: header,
        cookie: document.cookie,
      };
    }""")


def main():
    srv = subprocess.Popen(
        [sys.executable, str(HERE / "bench_lang.py"), str(PORT)],
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

        # Le HTML SERVI ne contient aucun nom de mois — c'est ce qui rend
        # le maillon navigateur necessaire, et ca se verifie sans lui.
        served = urllib.request.urlopen(BASE + "/", timeout=5).read().decode("utf-8")
        print("\n  0. dans le HTML servi")
        check("January" not in served and "janvier" not in served,
              "aucun nom de mois cote serveur (Intl les produit au navigateur)")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()

            print("\n  1. navigateur FRANCAIS, premiere visite")
            ctx = browser.new_context(locale="fr-FR", viewport=VIEWPORT)
            page = ctx.new_page()
            st = visit(page, wait=400)
            print(f"   {st}")
            check(st["html_lang"] == "fr", f"<html lang>=fr (vu {st['html_lang']})")
            check(st["dismiss"] == "Fermer",
                  f"mot du framework en francais (vu {st['dismiss']!r})")
            check(bool(st["calendar"]) and st["calendar"][0].islower(),
                  f"calendrier en francais — Intl rend en minuscules "
                  f"(vu {st['calendar']!r})")
            page.screenshot(path=str(HERE / "lang_fr.png"))

            print("\n  2. Language.set('en') — cookie pose, page rechargee")
            page.click('[data-probe="to-en"]')
            # Ici l'attente PRECEDE le ``bz-ready`` : c'est un rechargement
            # complet, donc le drapeau de l'ancienne page est encore la
            # quand le clic revient. C'est la SEULE difference entre cette
            # etape et les autres, et elle est visible parce que les
            # autres passent par ``visit``.
            page.wait_for_timeout(1200)
            st = settle(page, wait=0)
            print(f"   {st}")
            check("bz_lang=en" in (st["cookie"] or ""),
                  f"cookie bz_lang=en pose (vu {st['cookie']!r})")
            check(st["html_lang"] == "en",
                  f"la page ENTIERE a bascule (vu <html lang>={st['html_lang']})")
            check(st["dismiss"] != "Fermer",
                  f"mot du framework revenu en anglais (vu {st['dismiss']!r})")

            print("\n  3. le cookie gagne sur l'en-tete, au rechargement")
            st = visit(page)
            print(f"   {st}")
            check(st["html_lang"] == "en",
                  "un navigateur francais reste en anglais parce qu'on l'a "
                  f"choisi (vu {st['html_lang']})")
            page.screenshot(path=str(HERE / "lang_en.png"))

            print("\n  4. navigateur ALLEMAND — repli sur le defaut")
            ctx2 = browser.new_context(locale="de-DE", viewport=VIEWPORT)
            st = visit(ctx2.new_page())
            check(st["html_lang"] == "en",
                  f"langue non declaree -> defaut (vu {st['html_lang']})")

            print("\n  screenshots -> lang_fr.png / lang_en.png")
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)

    print()
    if FAILURES:
        print(f"LANG PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("LANG PROBE PASSED — en-tete, Intl, cookie : la chaine tient.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
