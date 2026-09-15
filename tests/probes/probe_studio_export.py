# -*- coding: utf-8 -*-
"""Probe — le code exporte par le theme studio est-il du Python QUI MARCHE ?

Le bloc du bas de ``/theme-studio`` est la raison d'etre de la page : on
regle, on copie, on colle dans ``core/theme.py``. Il est produit par une
EXPRESSION JavaScript (``export_expression()``), donc rien cote serveur
ne voit jamais la chaine finale.

``test_the_studio_exports_every_knob`` garde le gabarit — chaque reglage
y est nomme, chaque mot-cle emis est un vrai parametre de ``Theme``. Ce
qu'une gate ne peut pas faire, c'est executer le JS et lire ce qui sort.
C'est le travail de ce probe : il bouge des curseurs, lit le bloc rendu,
l'EVALUE en construisant vraiment un ``Theme`` — et
verifie que les valeurs reglees y sont arrivees.

Run :  py tests/probes/probe_studio_export.py
"""
from __future__ import annotations

import sys

#: Ce qu'on pousse dans le store avant de lire l'export. Des valeurs qui
#: ne sont AUCUN defaut, sinon un export qui ignorerait les curseurs
#: rendrait quand meme le bon texte.
REGLAGES = {
    "primary": "#ff0000",
    "box": 1.5,
    "field_": 0.25,
    "selector": 0.05,
    "stroke": 2.0,
    "spacing": 0.3,
}

ATTENDU_SHAPE = {"box": "1.5rem", "field": "0.25rem", "selector": "0.05rem"}


def main() -> int:
    """Rend 0 si le code exporte se construit et porte les reglages."""
    from bretzel.theme import Theme
    from tests.audit.harness import audit_server, browser_context

    ecarts: list[str] = []
    with audit_server() as base:
        with browser_context() as ctx:
            page = ctx.new_page()
            page.goto(f"{base}/theme-studio", wait_until="networkidle")
            # Attendre l'ETAT, pas une duree. Un `wait_for_timeout` fixe
            # paye son plein tarif meme quand la page est prete en
            # 200 ms, et reste un pari perdant sur une machine chargee.
            page.wait_for_function(
                "() => window.$bz && $bz.state"
                " && $bz.state.Studio && $bz.state.Studio.default"
            )

            page.evaluate(
                "(r) => { for (const [k, v] of Object.entries(r))"
                " $bz.state.Studio.default[k] = v; }",
                REGLAGES,
            )
            # Meme chose du cote sortie : on sait ce qu'on attend, donc on
            # attend CA. Le bloc de code est le seul <code> de la page.
            page.wait_for_function(
                "(attendu) => { const n = document.querySelectorAll('code');"
                " return n.length"
                " && n[n.length - 1].textContent.includes(attendu); }",
                arg=ATTENDU_SHAPE["box"],
            )
            code = page.evaluate(
                "() => { const n = document.querySelectorAll('code');"
                " return n.length ? n[n.length - 1].textContent : ''; }"
            )
            print(f"  {len(code)} caracteres lus dans le bloc de code\n")
            print("  " + "\n  ".join(code.splitlines()[-4:]))

            if not code.strip():
                print("\n  bloc de code VIDE")
                return 1

            # `eval` compile lui-meme en mode "eval" : un `ast.parse`
            # prealable levait exactement la meme `SyntaxError`, pour un
            # message qu'`except` donne gratuitement.
            try:
                theme = eval(code, {"Theme": Theme})  # le sujet meme du probe
            except SyntaxError as exc:
                print(f"\n  le code exporte ne PARSE pas : {exc}")
                return 1
            except Exception as exc:  # pragma: no cover - c'est le sujet
                print(f"\n  le code exporte ne CONSTRUIT pas : {exc!r}")
                return 1

            css = theme.generate_css()
            for famille, valeur in ATTENDU_SHAPE.items():
                if f"--radius-{famille}: {valeur};" not in css:
                    ecarts.append(
                        f"--radius-{famille} attendu a {valeur}, absent de "
                        f"la feuille du Theme reconstruit"
                    )
            if "--bz-stroke: 2px;" not in css:
                ecarts.append("le trait regle a 2px n'est pas arrive")
            if "--spacing: 0.3rem" not in css:
                ecarts.append("la densite reglee a 0.3rem n'est pas arrivee")
            # `rgb(...)` et non l'hexadecimal : le generateur normalise
            # toute couleur en `rgb()`, et chercher `#ff0000` faisait
            # rougir ce probe sur un export CORRECT.
            if "--color-primary: rgb(255 0 0);" not in css:
                ecarts.append("la couleur `primary` reglee n'est pas arrivee")

            # ── Le bouton « Reinitialiser » ────────────────────────────
            #
            # Il ne se mesure QUE comme ca. `persist="local"` ecrit dans
            # le navigateur, donc un test Python ne peut pas savoir ce
            # que la page montre a quelqu'un qui y est deja venu — et
            # c'est exactement le defaut signale le 2026-09-13 : la page
            # affichait un rose saisi des semaines plus tot pendant que
            # le defaut livre etait un indigo.
            from bretzel.theme.palette import DEFAULT_SEMANTIC_LIGHT

            attendu_primary = DEFAULT_SEMANTIC_LIGHT["primary"]
            page.get_by_role("button", name="Réinitialiser").click()
            try:
                page.wait_for_function(
                    "(attendu) => $bz.state.Studio.default.primary === attendu",
                    arg=attendu_primary, timeout=3000,
                )
            except Exception:
                ecarts.append(
                    f"apres le clic, `primary` vaut "
                    f"{page.evaluate('() => $bz.state.Studio.default.primary')!r} "
                    f"au lieu du defaut livre {attendu_primary!r}"
                )
            # Les CURSEURS aussi, pas seulement les couleurs : c'etaient
            # eux la moitie oubliee de l'export en aout.
            apres = page.evaluate(
                "() => ({box: $bz.state.Studio.default.box,"
                " spacing: $bz.state.Studio.default.spacing,"
                " stroke: $bz.state.Studio.default.stroke})"
            )
            for champ, regle in (("box", 1.5), ("spacing", 0.3), ("stroke", 2.0)):
                if apres[champ] == regle:
                    ecarts.append(
                        f"apres le clic, le curseur `{champ}` porte encore "
                        f"la valeur reglee ({regle}) : le bouton remet les "
                        f"couleurs et oublie les curseurs"
                    )
            print(f"  apres reset : primary="
                  f"{page.evaluate('() => $bz.state.Studio.default.primary')}"
                  f" curseurs={apres}")

    if ecarts:
        print(f"\n  {len(ecarts)} ECART(S) :")
        for e in ecarts:
            print("   ", e)
        return 1
    print("\n  le code exporte se construit, et porte les 6 reglages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
