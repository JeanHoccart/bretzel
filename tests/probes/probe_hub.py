# -*- coding: utf-8 -*-
"""Playwright probe — ``ui.filter_each`` filtre-t-il VRAIMENT sans serveur ?

Le filtre de ``ui.filter_each`` est entierement client : chaque ligne est
enveloppee d'un ``bz-show`` derive par le framework, qui compare
``text(item)`` a ``query``. Les lignes sont donc CACHEES, jamais retirees
— et c'est ce qui rend le probe necessaire : cote serveur le HTML est
identique quoi qu'on tape, donc aucun test de rendu ne peut voir si le
filtre marche.

On lit la visibilite CALCULEE, pas le texte du DOM.

Histoire de ce fichier
----------------------

Il pilotait ``bench_hub.py`` sur le port 8975 — un hub filtrable qui
vivait dans la famille ``/matrix``. Cette famille a ete supprimee le
2026-08-30 et le banc avec ; le probe, lui, est reste, lancant un
``sys.executable`` sur un chemin inexistant. Il attendait vingt secondes
puis mourait sur « hub bench never came up ». Mort en silence depuis,
decouvert le 2026-08-31 en lancant ``-m probes``.

Deux choses ont change en le reparant :

1. Plus de banc a lui. Il monte le playground par ``audit_server()``,
   comme les probes recents — un fichier de moins a garder vivant, et
   c'est precisement le mode de panne qu'on vient de payer.
2. Sa cible est la carte ``filter_each`` de ``/meta``, ajoutee le meme
   jour. Elle existe parce que ce probe a revele que ``ui.filter_each``
   est PUBLIC et n'etait demontre NULLE PART depuis la suppression du
   hub — le trou etait dans le produit, pas seulement dans le test.

Run :  py tests/probes/probe_hub.py
"""
from __future__ import annotations

import sys

#: La liste est LUE dans la page, pas recopiee ici : deux listes
#: divergent, et c'est exactement le genre de copie manuelle qui a tue
#: quatre probes le 2026-08-30.
from examples.playground.features.meta import FRUITS

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FAILURES: list[str] = []

TOTAL = len(FRUITS)


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def visibles(page) -> list[str]:
    """Les FRUITS dont l'enveloppe ``bz-show`` est visible.

    On lit ``getComputedStyle().display``, pas le texte : le serveur rend
    les douze lignes quoi qu'il arrive, donc compter le DOM dirait
    toujours « douze ».

    On filtre ensuite sur les fruits connus, et ce n'est pas un detail :
    le noeud d'etat vide porte LUI AUSSI un ``bz-show`` — c'est ainsi
    qu'il apparait quand rien ne matche — donc le compter parmi les
    lignes ferait echouer le cas « aucun resultat » sur un comportement
    correct. Erreur faite en ecrivant ce probe, gardee ici.
    """
    vus = page.evaluate(
        """() => [...document.querySelectorAll('#meta-filter-rows [bz-show]')]
             .filter(e => getComputedStyle(e).display !== 'none')
             .map(e => e.innerText.trim())
             .filter(Boolean)"""
    )
    return [v for v in vus if v in set(FRUITS)]


def main() -> int:
    from tests.audit.harness import audit_server, browser_context

    with audit_server() as base:
        with browser_context() as ctx:
            page = ctx.new_page()
            errs: list[str] = []
            page.on("console", lambda m: errs.append(m.text)
                    if m.type == "error" else None)
            page.goto(f"{base}/meta", wait_until="networkidle")
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )
            box = page.locator("#meta-filter-input input, #meta-filter-input")

            def noeuds() -> int:
                return page.evaluate(
                    "() => document.querySelectorAll("
                    "'#meta-filter-rows [bz-show]').length"
                )

            # Combien de noeuds AU REPOS. On ne l'ecrit pas en dur : il y
            # en a treize pour douze fruits, parce que l'etat vide est
            # lui aussi la, cache. Le chiffrer ici ferait rougir ce probe
            # au premier fruit ajoute.
            au_repos = noeuds()

            print("\nAu repos — tout est visible")
            vus = visibles(page)
            check(f"les {TOTAL} lignes sont la", len(vus) == TOTAL, str(vus))

            print("\n'fra' — deux fruits commencent par la")
            box.fill("fra")
            page.wait_for_function(
                """() => [...document.querySelectorAll(
                     '#meta-filter-rows [bz-show]')]
                   .filter(e => getComputedStyle(e).display !== 'none')
                   .length === 2"""
            )
            vus = visibles(page)
            check("fraise et framboise, et rien d'autre",
                  sorted(vus) == ["fraise", "framboise"], str(vus))

            print("\n'kiwi' — un seul")
            box.fill("kiwi")
            page.wait_for_function(
                """() => [...document.querySelectorAll(
                     '#meta-filter-rows [bz-show]')]
                   .filter(e => getComputedStyle(e).display !== 'none')
                   .length === 1"""
            )
            check("kiwi seul", visibles(page) == ["kiwi"], str(visibles(page)))

            print("\n'zzz' — l'etat vide")
            box.fill("zzz")
            page.wait_for_function(
                """() => document.body.innerText
                     .includes('Aucun fruit ne correspond')"""
            )
            check("aucune ligne", visibles(page) == [], str(visibles(page)))
            check("le message d'etat vide s'affiche",
                  "Aucun fruit ne correspond" in page.inner_text("body"))

            print("\nOn efface — tout revient")
            box.fill("")
            page.wait_for_function(
                f"""() => [...document.querySelectorAll(
                     '#meta-filter-rows [bz-show]')]
                   .filter(e => getComputedStyle(e).display !== 'none')
                   .length === {TOTAL}"""
            )
            check(f"les {TOTAL} lignes de nouveau",
                  len(visibles(page)) == TOTAL, str(visibles(page)))

            # Le filtre ne doit RIEN demander au serveur : c'est tout son
            # interet. Une ligne retiree cote serveur ferait chuter le
            # compte des noeuds, pas seulement celui des visibles. On
            # compare donc le DOM a LUI-MEME, avant et apres.
            check("le DOM n'a pas bouge — rien n'est parti au serveur",
                  noeuds() == au_repos,
                  f"{noeuds()} noeuds contre {au_repos} au repos")

            check("aucune erreur console", not errs, "; ".join(errs[:5]))

    print()
    if FAILURES:
        print(f"FILTER_EACH PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("FILTER_EACH PROBE PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
