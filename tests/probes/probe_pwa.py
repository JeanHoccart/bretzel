# -*- coding: utf-8 -*-
"""Probe — le NAVIGATEUR accepte-t-il le manifeste ?

Un test Python peut affirmer que ``/manifest.webmanifest`` rend 200 avec
le bon type MIME et un JSON qui contient les bonnes clés. Il ne peut pas
dire que Chromium le RÉSOUT et le trouve valide — or c'est la seule
chose qui décide si l'app est installable.

Chromium sait le dire, et il faut le lui demander : ``Page.getAppManifest``
en CDP rend l'URL résolue et la liste de ses erreurs.

⚠️ Ce que ce probe ne prouve PAS, et il ne faut pas le lire autrement :
- il ne dit pas que l'invite « Installer » apparaît. Chrome a longtemps
  exigé en plus un *service worker* avec un gestionnaire ``fetch``, et
  Bretzel n'en livre pas ;
- il ne valide pas les ICÔNES. Une icône en 404 ne produit aucune erreur
  à cette étape — vérifié en pointant volontairement un chemin qui
  n'existe pas.

Run :  py tests/probes/probe_pwa.py
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
    from bretzel import PWA, Bretzel, PWAIcon, page, ui

    app = Bretzel(
        secret_key="probe-pwa-secret-key-thirty-two!!",
        title="Bretzel · PWA probe", mode="dev",
        pwa=PWA(name="Tracker Bretzel", short_name="Tracker",
                description="Un outil interne", theme_color="#0f172a",
                background_color="#ffffff",
                icons=[PWAIcon("/icon-192.png", "192x192")]),
    )

    @page("/")
    def home() -> None:
        ui.text("Une app installable.")

    app.include(home)
    return app


def main() -> int:
    from tests.audit.harness import audit_server, browser_context

    with audit_server(build_app()) as base, browser_context() as ctx:
        page = ctx.new_page()
        page.goto(f"{base}/", wait_until="networkidle")

        lie = page.evaluate(
            "() => { const l = document.querySelector('link[rel=manifest]');"
            "  return l ? l.getAttribute('href') : null; }"
        )
        check("le document LIE son manifeste", lie == "/manifest.webmanifest",
              f"href : {lie!r} — servir le fichier ne suffit pas, aucun "
              f"navigateur ne le cherche de lui-même")

        couleur = page.evaluate(
            "() => { const m = document.querySelector('meta[name=theme-color]');"
            "  return m ? m.getAttribute('content') : null; }"
        )
        check("la couleur de barre système est déclarée", couleur == "#0f172a",
              f"content : {couleur!r}")

        # LE verdict : c'est Chromium qui juge, pas nous.
        cdp = ctx.new_cdp_session(page)
        rapport = cdp.send("Page.getAppManifest")
        check("Chromium RÉSOUT le manifeste",
              (rapport.get("url") or "").endswith("/manifest.webmanifest"),
              f"url : {rapport.get('url')!r}")
        erreurs = rapport.get("errors") or []
        check("...et n'y trouve aucune erreur", not erreurs, str(erreurs[:3]))

        reponse = page.request.get(f"{base}/manifest.webmanifest")
        check("le type MIME est celui que la spec impose",
              reponse.headers.get("content-type", "").startswith(
                  "application/manifest+json"),
              f"reçu : {reponse.headers.get('content-type')!r} — servi en "
              f"application/json, les outils de diagnostic refusent le "
              f"manifeste et l'app paraît non installable sans qu'aucune "
              f"erreur ne le dise")

    print()
    if FAILURES:
        print(f"PWA PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("PWA PROBE PASSED — le navigateur accepte le manifeste.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
