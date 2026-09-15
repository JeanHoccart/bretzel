# -*- coding: utf-8 -*-
"""Probe — un ``@download`` se TÉLÉCHARGE-t-il vraiment ?

Un test Python peut affirmer qu'une route rend 200 avec le bon
``Content-Disposition``. Il ne peut pas dire que le navigateur en fait un
téléchargement plutôt qu'une navigation — et c'est la seule chose qui
compte pour l'utilisateur : s'il clique et que la page s'en va, le
routable a échoué même si la réponse était parfaite.

Ce fichier clique pour de vrai et attend l'événement ``download`` de
Chromium.

Il sert aussi son app plutôt que le playground : le sujet n'est PAS un
composant mais une propriété du ROUTAGE, et ``audit_server(app)`` existe
exactement pour ça.

⚠️ Ce que le probe garde et qu'aucun test Python ne peut voir : que le
lien ne soit pas avalé par ``hx-boost``. La coque pose ``hx-boost`` sur
la page, donc un ``<a>`` ordinaire est intercepté par htmx et swappé
dans le document — le fichier arriverait alors comme du HTML dans
l'outlet, ce qui n'a AUCUN signe visible côté serveur.

⚠️⚠️ **ET CE PROBE A ÉTÉ VERT EN NE TESTANT RIEN.** Sa première version
montait une page SANS coque, donc sans ``hx-boost`` — il affirmait « le
lien n'est pas avalé » sur un banc où rien ne pouvait l'avaler. Le bug
existait pourtant : mesuré le 2026-09-02 sur ``/meta`` du playground,
un ``ui.link(href="/x.csv")`` ordinaire partait en ``resource_type:
'xhr'`` et la page naviguait vers le CSV.

La leçon vaut au-delà d'ici : **un probe qui teste une NÉGATION doit
d'abord prouver que la condition est atteignable.** Ce fichier monte
donc son app AVEC un layout, et vérifie explicitement que la page porte
bien ``hx-boost`` avant de conclure quoi que ce soit.

Run :  py tests/probes/probe_download.py
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


def build_app():
    from bretzel import Bretzel, download, layout, page, ui

    app = Bretzel(secret_key="probe-download-secret-key-32-chars!!",
                  title="Bretzel · download probe", mode="dev")

    @download("/clients.csv")
    async def clients_csv() -> list[dict]:
        return [
            {"nom": "Ada Lovelace", "ville": "Londres"},
            {"nom": 'Dupont, "Jean"', "ville": "Lille"},
        ]

    # La coque, et elle est LOAD-BEARING : c'est elle qui pose
    # ``hx-boost`` sur la page. Sans elle, ce probe ne peut pas voir le
    # bug qu'il existe pour attraper.
    @layout
    def coque() -> None:
        with ui.vstack(gap="md", classes="p-8"):
            ui.heading("Téléchargement", level=1)
            ui.outlet()

    @page("/", layout=coque)
    def home() -> None:
        # ``download=True`` : le lien porte un FICHIER. Sans lui, la
        # coque l'avale — c'est ce que le verdict 3 vérifie.
        ui.link("Exporter les clients", href="/clients.csv",
                download=True, id="lien-export")

    app.include(clients_csv)
    app.include(home)
    return app


def main() -> int:
    from tests.audit.harness import audit_server, browser_context

    with audit_server(build_app()) as base, browser_context() as ctx:
        page = ctx.new_page()
        erreurs: list[str] = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))

        page.goto(f"{base}/", wait_until="networkidle")
        page.wait_for_function(
            "document.documentElement.classList.contains('bz-ready')"
        )

        # LE garde-fou du garde-fou : si la page ne porte pas
        # ``hx-boost``, le verdict « la page n'a pas navigué » ne prouve
        # rien, et ce probe redeviendrait le faux vert qu'il a été.
        boost = page.evaluate(
            "() => !!document.querySelector('[hx-boost]')"
        )
        check("la page porte bien hx-boost", boost,
              "sans lui, rien ne peut avaler le lien et les verdicts "
              "suivants sont vides de sens")

        avant = page.url
        with page.expect_download(timeout=10_000) as attente:
            page.click("#lien-export")
        telechargement = attente.value

        check("le clic déclenche un TÉLÉCHARGEMENT", telechargement is not None)
        check("le navigateur reçoit le bon nom de fichier",
              telechargement.suggested_filename == "clients.csv",
              f"reçu : {telechargement.suggested_filename!r}")
        # LE point du probe : la page ne doit pas avoir bougé. Un lien
        # avalé par hx-boost aurait navigué, et la réponse CSV se serait
        # retrouvée swappée dans le document.
        page.wait_for_timeout(400)
        check("la page n'a PAS navigué", page.url == avant,
              f"{avant!r} → {page.url!r}")

        chemin = telechargement.path()
        contenu = chemin.read_bytes().decode("utf-8-sig")
        check("le CSV porte son en-tête", contenu.startswith("nom,ville"),
              f"début : {contenu[:40]!r}")
        check("...et cite ce qui doit l'être",
              '"Dupont, ""Jean"""' in contenu,
              f"contenu : {contenu!r}")
        check("le BOM est là pour Excel",
              chemin.read_bytes().startswith(b"\xef\xbb\xbf"))

        check("aucune erreur JS", not erreurs, "; ".join(erreurs[:4]))

    print()
    if FAILURES:
        print(f"DOWNLOAD PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("DOWNLOAD PROBE PASSED — le fichier arrive comme un fichier.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
