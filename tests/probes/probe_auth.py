"""Playwright probe — la connexion, dans un vrai navigateur (port 8951).

BLOQUANT. ``TestClient`` a déjà dit que le HTML sort ; il ne dit rien de
ce qui suit, et c'est là que vivent les défauts qu'un humain voit en dix
secondes :

1. la page de connexion se rend, sans erreur console ;
2. **aucune barre de défilement horizontale** — la carte est centrée
   dans un cadre gelé (``ui.viewport`` + ``ui.pane``), la forme la plus
   facile à casser d'une largeur ;
2 bis. **le haut reste atteignable dans une fenêtre BASSE.** Une carte
   centrée plus haute que le cadre débordait des deux côtés, et le
   défilement ne remonte pas au-dessus de son origine : 108 px de titre
   et de champ étaient perdus, définitivement. Vu par un humain avant
   toute sonde ;
3. **l'ordre de tabulation** va adresse → mot de passe → bouton ;
4. un mot de passe faux affiche l'alerte **sans quitter la page** ;
5. la connexion aboutit : on arrive sur ``/``, le ``user_id`` s'affiche,
   et donc **le cookie a été posé et la garde l'a lu** ;
6. le ``UserState`` compte — la preuve que le scope par personne
   fonctionne ;
7. la déconnexion ramène à ``/login``, et ``/`` redevient interdit.

Le 5 est le seul qui vérifie la chaîne complète bout-en-bout dans les
conditions réelles : formulaire → ``auth.login`` → cookie → middleware
de garde → ``UserState``.

Run :  py tests/probes/probe_auth.py
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
SHOTS = HERE / "_shots"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'OK  ' if ok else 'FAIL'} {label}{'' if ok else ' — ' + detail}")
    if not ok:
        FAILURES.append(f"{label} — {detail}")


def ready(page: object) -> None:
    """Attend le drapeau de fin de boot du runtime.

    ``wait_for_selector("html.bz-ready")`` — ce qu'écrivent les autres
    probes — ne marche PAS ici : cette app pose un cadre gelé
    (``ui.viewport``), donc ``<html>`` n'a pas de boîte et Playwright le
    juge « hidden ». On teste la classe, pas la visibilité.
    """
    page.wait_for_function(  # type: ignore[attr-defined]
        "() => document.documentElement.classList.contains('bz-ready')",
        timeout=10000,
    )


def wait_server() -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen(BASE + "/login", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("le banc auth n'est jamais monté sur :8951")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_auth.py"), str(PORT)],
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
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )

            # ── 1. la page publique ────────────────────────────────────
            page.goto(BASE + "/")
            ready(page)
            check("anonyme redirigé sur /login", page.url.endswith("/login"), page.url)
            check("le titre est rendu", page.locator("h1").count() == 1)

            # ── 2. pas de défilement horizontal ────────────────────────
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            check("aucun débordement horizontal", overflow <= 0, f"{overflow}px")

            SHOTS.mkdir(exist_ok=True)
            page.screenshot(path=str(SHOTS / "auth_login.png"))

            # ── 2 bis. fenêtre basse : le haut reste atteignable ───────
            page.set_viewport_size({"width": 1280, "height": 600})
            page.wait_for_timeout(200)
            reach = page.evaluate("""() => {
              const first = document.querySelector('h1');
              const pane = first.closest('[class*="overflow-y-auto"]');
              pane.scrollTop = 0;
              return Math.round(pane.getBoundingClientRect().top
                                - first.getBoundingClientRect().top);
            }""")
            check("en 1280x600, le haut reste atteignable", reach <= 0, f"{reach}px coupes")
            page.set_viewport_size({"width": 1280, "height": 900})
            page.wait_for_timeout(200)

            # ── 3. ordre de tabulation ─────────────────────────────────
            page.keyboard.press("Tab")
            first = page.evaluate("() => document.activeElement.getAttribute('name')")
            page.keyboard.press("Tab")
            second = page.evaluate("() => document.activeElement.getAttribute('name')")
            page.keyboard.press("Tab")
            third = page.evaluate("() => document.activeElement.tagName")
            check(
                "tab : adresse → mot de passe → bouton",
                bool(first) and bool(second) and first != second and third == "BUTTON",
                f"{first} → {second} → {third}",
            )

            # ── 4. un refus reste sur place ────────────────────────────
            page.fill("input[type=text], input:not([type])", "jean@macorp.fr")
            page.fill("input[type=password]", "faux")
            page.click("button[type=submit]")
            page.wait_for_selector('[role="alert"], .bz-alert', timeout=4000)
            check("mot de passe faux : alerte, et on reste", page.url.endswith("/login"), page.url)

            # ── 5. la connexion aboutit ────────────────────────────────
            page.fill("input[type=password]", "demo")
            page.click("button[type=submit]")
            page.wait_for_url(BASE + "/", timeout=5000)
            ready(page)
            body = page.inner_text("body")
            check("arrivé sur /", page.url == BASE + "/", page.url)
            check("l'identité est celle de la table d'app", "u-1" in body, body[:120])

            # ── 6. le UserState compte ─────────────────────────────────
            before = page.inner_text("body")
            page.click("text=Compter une visite")
            page.wait_for_function(
                "prev => document.body.innerText !== prev", arg=before, timeout=4000
            )
            check(
                "le UserState a compté",
                "visites comptées dans un UserState : 1" in page.inner_text("body"),
                page.inner_text("body")[:160],
            )

            SHOTS.mkdir(exist_ok=True)
            page.screenshot(path=str(SHOTS / "auth_home.png"))

            # ── 7. la déconnexion ferme vraiment ───────────────────────
            page.click("text=Se déconnecter")
            page.wait_for_url(BASE + "/login", timeout=5000)
            page.goto(BASE + "/")
            check("après logout, / est de nouveau interdit", page.url.endswith("/login"), page.url)

            check("zéro erreur console", not console_errors, "; ".join(console_errors[:3]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} ÉCHEC(S)")
        return 1
    print("Tout vert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
