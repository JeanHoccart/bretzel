"""Playwright probe — une porte OIDC, contre un VRAI fournisseur (8953/8954).

BLOQUANT. C'est le seul endroit où le flux entier existe pour de bon :
deux serveurs, deux origines, un navigateur qui suit les redirections, et
un fournisseur qui vérifie PKCE. Ce que l'intégration ne pouvait pas
mesurer, parce qu'elle remplace ``oauth._fetch`` :

1. l'aller-retour HTTP réel — ``urllib.request`` poussé dans un thread
   ``anyio``, le POST form-encodé, l'en-tête ``Accept`` ;
2. **PKCE vérifié par l'autre bout** : le fournisseur recalcule le
   SHA-256 du vérifieur et refuse s'il ne colle pas ;
3. **le cookie de transaction survit à un retour INTER-SITE.** Le
   fournisseur est sur ``localhost`` et l'app sur ``127.0.0.1`` : deux
   SITES distincts pour le navigateur, donc un ``SameSite=strict`` ne
   reviendrait pas et la connexion échouerait. ⚠️ Deux PORTS du même
   hôte n'auraient rien prouvé — c'est inter-ORIGINE, pas inter-site, et
   la première version de cette sonde se le racontait (mesuré :
   ``strict`` y restait vert) ;
4. le refus : un compte hors du domaine autorisé ressort sur ``/login``
   **sans session** — ``on_user`` est le seul filtre entre « a un compte
   chez le fournisseur » et « entre chez moi » ;
5. un code ne s'échange qu'une fois (rejeu du callback).

Run :  py tests/probes/probe_oauth_door.py
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
APP = "http://127.0.0.1:8953"
IDP = "http://localhost:8954"
SHOTS = HERE / "_shots"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'OK  ' if ok else 'FAIL'} {label}{'' if ok else ' — ' + detail}")
    if not ok:
        FAILURES.append(f"{label} — {detail}")


def wait_up(url: str, name: str) -> None:
    for _ in range(80):
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"{name} n'est jamais monté ({url})")


def back_on_app(page: object) -> None:
    """Attend le retour sur l'app, quelle que soit la page d'arrivée.

    Attendre ``/`` directement paraissait plus court, et rendait la sonde
    ILLISIBLE quand la porte cassait : au lieu d'un rouge nommé, on
    recevait un timeout Playwright de trente lignes, parce que la porte
    refusait proprement vers ``/login``. Une sonde qui casse au lieu de
    rougir se lit comme une panne d'outillage — le mode d'échec qui a
    fait pourrir les 52 probes de ce dossier.
    """
    page.wait_for_url(lambda url: url.startswith(APP), timeout=10000)  # type: ignore[attr-defined]


def ready(page: object) -> None:
    page.wait_for_function(  # type: ignore[attr-defined]
        "() => document.documentElement.classList.contains('bz-ready')",
        timeout=10000,
    )


def main() -> int:
    idp = subprocess.Popen(
        [sys.executable, str(HERE / "bench_oidc_provider.py")],
        cwd=HERE.parent.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    app = subprocess.Popen(
        [sys.executable, str(HERE / "bench_auth_sso.py")],
        cwd=HERE.parent.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_up(IDP + "/.well-known/openid-configuration", "le fournisseur")
        wait_up(APP + "/login", "l'app")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            console_errors: list[str] = []
            page.on(
                "console",
                lambda m: console_errors.append(m.text) if m.type == "error" else None,
            )

            # ── la porte est annoncée ──────────────────────────────────
            page.goto(APP + "/login")
            ready(page)
            door = page.locator("a[href='/auth/testidp']")
            check("la page de connexion propose la porte", door.count() == 1)

            # ── le chemin nominal ──────────────────────────────────────
            door.click()
            page.wait_for_url(f"{IDP}/authorize*", timeout=8000)
            check("le navigateur est chez le fournisseur", page.url.startswith(IDP), page.url)
            check("PKCE est bien parti", "code_challenge_method=S256" in page.url, page.url)

            page.click("#pick-jean")
            back_on_app(page)
            ready(page)
            body = page.inner_text("body")
            check("retour sur l'app, connecté", page.url == APP + "/", page.url)
            check(
                "les deux portes convergent sur UNE identité",
                # ``jean@macorp.fr`` a déjà une ligne dans la table de la
                # démo — celle qu'on atteint par mot de passe, ``u-1``. La
                # porte OIDC prouve une ADRESSE ; c'est l'app qui joint, et
                # elle doit retomber sur la même personne. ``prov-jean``,
                # l'identifiant chez le fournisseur, ne doit jamais
                # remonter jusqu'à l'écran : ce n'est pas un ``user_id``.
                "user_id : u-1" in body and "prov-jean" not in body,
                body[:400],
            )
            check("le compte créé porte l'adresse du fournisseur", "jean@macorp.fr" in body,
                  body[:200])
            cookies = {c["name"] for c in context.cookies()}
            check("le cookie de session Bretzel est posé", "Bretzel_auth" in cookies,
                  str(sorted(cookies)))
            check(
                "le cookie de transaction est retiré",
                not any(c.startswith("Bretzel_oauth_") for c in cookies),
                str(sorted(cookies)),
            )

            SHOTS.mkdir(exist_ok=True)
            page.screenshot(path=str(SHOTS / "oauth_door_home.png"))

            # ── le refus : bon fournisseur, mauvais domaine ────────────
            page.click("text=Se déconnecter")
            page.wait_for_url(APP + "/login", timeout=8000)
            page.click("a[href='/auth/testidp']")
            page.wait_for_url(f"{IDP}/authorize*", timeout=8000)
            page.click("#pick-intrus")
            page.wait_for_url(APP + "/login*", timeout=10000)
            ready(page)
            after = {c["name"] for c in context.cookies()}
            check("un domaine non autorisé ressort sur /login",
                  page.url.startswith(APP + "/login"), page.url)
            check("et sans session", "Bretzel_auth" not in after, str(sorted(after)))

            # ── le rejeu ───────────────────────────────────────────────
            page.click("a[href='/auth/testidp']")
            page.wait_for_url(f"{IDP}/authorize*", timeout=8000)
            page.click("#pick-jean")
            back_on_app(page)
            used = page.url
            replay = page.context.request.get(
                APP + "/auth/testidp/callback?code=deja-utilise&state=x",
                max_redirects=0,
            )
            check(
                "un retour sans transaction valide est refusé",
                replay.status in (302, 307) and "/login" in replay.headers.get("location", ""),
                f"{replay.status} → {replay.headers.get('location')}",
            )
            check("la session en cours n'a pas bougé", used == APP + "/", used)

            check("zéro erreur console", not console_errors, "; ".join(console_errors[:3]))
            browser.close()
    finally:
        app.terminate()
        idp.terminate()
        app.wait(timeout=10)
        idp.wait(timeout=10)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} ÉCHEC(S)")
        return 1
    print("Tout vert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
