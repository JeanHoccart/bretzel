# -*- coding: utf-8 -*-
"""Probe — le miroir JS du foreground rend-il EXACTEMENT ce que Python rend ?

Le foreground d'une couleur est derive du fond : une clarte choisie par un
seuil de luminance WCAG, puis TEINTEE de la teinte du fond. L'algorithme
vit dans ``bretzel.theme.palette.resolve_color_pair`` et tourne a la
generation du CSS ; le theme studio le REDIT en JavaScript, parce qu'il ne
parle jamais au serveur.

``test_foreground_algebra_is_mirrored`` garde les NOMBRES des deux cotes,
a la seconde, a chaque commit. Ce qu'une gate ne peut pas faire, c'est
executer le JS. C'est le travail de ce probe : il fait tourner les deux
implementations sur un echantillon et exige l'egalite exacte de
l'hexadecimal.

Run :  py tests/probes/probe_foreground_mirror.py
"""
from __future__ import annotations

import sys

#: L'echantillon : les onze semantiques par defaut, les deux extremes,
#: un gris pile au milieu (le seuil de luminance s'y joue), et quatre
#: teintes quelconques.
ECHANTILLON = [
    "#ffffff", "#000000", "#2f5fd0", "#8e4ec6", "#309d64", "#f0a91b",
    "#e5484d", "#0e9bc3", "#f8fafc", "#020617", "#64748b", "#d6409f",
    "#12a594", "#ffe629", "#7f7f7f", "#010203", "#fefefe", "#123456",
]


def main() -> int:
    """Rend 0 si les deux implementations sont d'accord, 1 sinon."""
    from bretzel.theme.palette import resolve_color_pair
    from tests.audit.harness import audit_server, browser_context

    ecarts: list[str] = []
    with audit_server() as base:
        with browser_context() as ctx:
            page = ctx.new_page()
            page.goto(f"{base}/theme-studio", wait_until="networkidle")
            page.wait_for_timeout(6000)
            vus = page.evaluate(
                "(l) => l.map(h => (window.bzFg ? window.bzFg(h) : 'ABSENT'))",
                ECHANTILLON,
            )
            for hexa, vu in zip(ECHANTILLON, vus):
                attendu = resolve_color_pair(hexa)[1]
                accord = vu == attendu
                if not accord:
                    ecarts.append(f"{hexa} : python {attendu} != js {vu}")
                print(f"  {hexa}  python {attendu}  js {vu}  "
                      f"{'ok' if accord else 'ECART'}")

            # Bout-en-bout : on met `primary` au BLANC et on lit ce que la
            # page rend reellement. C'est le bug d'origine — blanc sur
            # blanc — donc le seul cas qui prouve que le miroir est CABLE.
            page.evaluate(
                "() => { $bz.state.Studio.default.primary = '#ffffff'; }"
            )
            page.wait_for_timeout(900)
            paire = page.evaluate("""() => {
              const cs = getComputedStyle(document.documentElement);
              return {
                bg: cs.getPropertyValue('--color-primary').trim(),
                fg: cs.getPropertyValue('--color-primary-foreground').trim(),
              };
            }""")
            print(f"\n  primary = #ffffff -> {paire}")
            attendu_fg = resolve_color_pair("#ffffff")[1]
            if paire.get("fg") != attendu_fg:
                ecarts.append(
                    f"bout-en-bout : foreground {paire.get('fg')} au lieu de "
                    f"{attendu_fg} — le miroir n'est pas CABLE dans l'effet"
                )

    if ecarts:
        print(f"\n  {len(ecarts)} ECART(S) :")
        for e in ecarts:
            print("   ", e)
        return 1
    print(f"\n  0 ecart sur {len(ECHANTILLON)} couleurs + le bout-en-bout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
