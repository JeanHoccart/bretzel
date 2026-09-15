# -*- coding: utf-8 -*-
"""Probe — les verbes clients font-ils vraiment ce qu'ils annoncent ?

Les CINQ verbes (``copy`` / ``print_page`` / ``fullscreen`` /
``share`` / ``vibrate``) produisent une CHAÎNE
de JavaScript. Un test Python ne peut donc juger que la chaîne — et une
chaîne juste qui ne s'exécute pas est exactement le mode d'échec que ce
dossier existe pour attraper. Ce fichier exécute.

Ce qu'il mesure, et pourquoi chacun
------------------------------------
1. **La copie atteint le presse-papiers**, relue par
   ``navigator.clipboard.readText()`` — pas « l'appel n'a pas levé ».
2. **Elle copie la valeur VIVANTE.** On tape dans le champ AVANT de
   cliquer, et on exige de relire ce qu'on vient de taper. C'est tout le
   point de l'API : le verbe interpole le CHEMIN du champ, pas sa valeur
   au rendu. Un ``copy`` qui figerait la graine SSR passerait le test 1
   et échouerait ici.
3. **Le repli hors contexte sécurisé marche.** On force
   ``isSecureContext`` à ``false``, ce qui est la situation d'un outil
   interne servi en ``http://`` sur une IP de réseau local — le public
   visé. Sans repli, ``navigator.clipboard`` y vaut ``undefined`` et le
   bouton ne fait rien, sans un mot.
4. **``print`` appelle bien la boîte native**, vérifié en la remplaçant :
   la laisser s'ouvrir bloquerait le navigateur pour de bon.
5. **``fullscreen`` vise la bonne cible**, et n'explose pas si le
   navigateur refuse.
6. **``share`` retombe sur la copie**, et c'est le chemin NORMAL :
   ``navigator.share`` est ``undefined`` sur le Chromium de bureau. Le
   probe l'affirme d'abord — si l'API apparaît un jour, il mesurera
   l'autre branche, et il doit le dire plutôt que de passer au vert en
   testant autre chose.
7. **``vibrate`` n'a aucune absence à gérer** — la fonction existe
   partout et ne fait rien sans matériel.
8. Zéro erreur JS sur toute la séquence.

⚠️ ``127.0.0.1`` EST un contexte sécurisé pour le navigateur, au même
titre que ``localhost``. C'est ce qui permet de tester le chemin nominal
ici — et c'est aussi pourquoi le repli DOIT être testé en forçant le
drapeau : le banc ne le rencontrerait jamais tout seul.

Run :  py tests/probes/probe_verbs.py
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FAILURES: list[str] = []

COPY = "#meta-verb-copy"
INPUT = "#meta-verb-input"
PRINT = "#meta-verb-print"
FULLSCREEN = "#meta-verb-fullscreen"
ZONE = "meta-verb-zone"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


def main() -> int:
    from tests.audit.harness import audit_server, browser_context

    with audit_server() as base, browser_context() as ctx:
        # Lire le presse-papiers demande une permission explicite ;
        # l'ÉCRIRE non. Sans ça le test 1 ne pourrait que constater
        # l'absence d'exception.
        ctx.grant_permissions(["clipboard-read", "clipboard-write"],
                              origin=base)
        page = ctx.new_page()
        erreurs: list[str] = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        page.on("console",
                lambda m: erreurs.append(m.text) if m.type == "error" else None)

        page.goto(f"{base}/meta", wait_until="networkidle")
        page.wait_for_function(
            "document.documentElement.classList.contains('bz-ready')"
        )
        page.wait_for_timeout(400)

        print("\n1 + 2. La copie atteint le presse-papiers — et c'est la "
              "valeur VIVANTE")
        check("le contexte du banc est sécurisé",
              page.evaluate("window.isSecureContext") is True,
              "127.0.0.1 devrait l'être")
        page.fill(INPUT, "")
        page.type(INPUT, "tape-a-la-main-42")
        page.wait_for_timeout(200)
        page.click(COPY)
        page.wait_for_timeout(300)
        lu = page.evaluate("navigator.clipboard.readText()")
        check("le presse-papiers porte ce qu'on vient de TAPER",
              lu == "tape-a-la-main-42",
              f"lu : {lu!r} — une graine SSR signifierait que le verbe "
              f"a figé la valeur au rendu au lieu d'interpoler le chemin")

        print("\n3. Le repli hors contexte sécurisé")
        # ``isSecureContext`` est en lecture seule, mais redéfinissable.
        # C'est la seule façon d'atteindre le chemin qu'un outil interne
        # servi en http:// sur une IP locale prend TOUJOURS.
        page.evaluate(
            "Object.defineProperty(window, 'isSecureContext', "
            "{value: false, configurable: true})"
        )
        page.evaluate(
            "window.__execCopy = 0;"
            "const vrai = document.execCommand.bind(document);"
            "document.execCommand = function (cmd) {"
            "  if (cmd === 'copy') window.__execCopy++;"
            "  return vrai.apply(document, arguments); };"
        )
        page.fill(INPUT, "")
        page.type(INPUT, "sans-contexte-securise")
        page.wait_for_timeout(200)
        page.click(COPY)
        page.wait_for_timeout(300)
        appels = page.evaluate("window.__execCopy")
        check("le repli execCommand est emprunté", appels >= 1,
              f"{appels} appel(s) — zéro voudrait dire que le verbe a "
              f"quand même tenté navigator.clipboard, donc ne ferait "
              f"rien sur un outil interne en http://")
        page.evaluate(
            "Object.defineProperty(window, 'isSecureContext', "
            "{value: true, configurable: true})"
        )

        print("\n4. print appelle la boîte native")
        # Remplacée : la laisser s'ouvrir bloque le navigateur, et le
        # probe attendrait jusqu'au timeout.
        #
        # ⚠️ On compte les CLICS NATIFS en même temps, et on compare. La
        # première version exigeait « exactement 1 appel » et rougissait
        # à 2 — j'y ai vu un double-binding du runtime, et j'ai eu tort.
        # Instrumenté depuis un ``add_init_script``, il attache
        # EXACTEMENT un écouteur ``click`` par nœud (mesuré : 7 nœuds sur
        # cette page, aucun en double). Ce que ``page.click()`` faisait,
        # c'était livrer DEUX clics — Playwright ré-essaie quand
        # l'élément bouge, et taper dans le champ juste avant fait bouger
        # la mise en page.
        #
        # L'invariant qui compte n'est donc pas « une fois », c'est
        # « autant de fois qu'on a cliqué ». Le mesurer ainsi rend le
        # probe insensible au ré-essai ET plus strict sur ce qui compte :
        # un clic qui n'appellerait rien, ou qui appellerait deux fois,
        # rougissent tous les deux.
        page.evaluate(
            "window.__printed = 0; window.__clics = 0;"
            "window.print = () => { window.__printed++; };"
            "document.addEventListener('click', (e) => {"
            "  if (e.target.closest('#meta-verb-print')) window.__clics++;"
            "}, true);"
        )
        page.click(PRINT)
        page.wait_for_timeout(300)
        appels = page.evaluate("window.__printed")
        clics = page.evaluate("window.__clics")
        check("window.print est appelé UNE fois par clic",
              appels == clics and appels >= 1,
              f"{appels} appel(s) pour {clics} clic(s) natif(s)")

        print("\n5. fullscreen vise la bonne cible")
        page.evaluate(
            "window.__fsTarget = null;"
            "Element.prototype.requestFullscreen = function () {"
            "  window.__fsTarget = this.id; return Promise.resolve(); };"
        )
        page.click(FULLSCREEN)
        page.wait_for_timeout(200)
        cible = page.evaluate("window.__fsTarget")
        check("c'est la carte qui est demandée, pas la page",
              cible == ZONE, f"cible : {cible!r}")

        print("\n6. share — le REPLI est le chemin normal sur bureau")
        # ``navigator.share`` est undefined ici (mesuré). Ce qui doit
        # arriver n'est donc pas « rien » mais « l'URL est copiée » —
        # c'est le contrat, pas un accident.
        absente = page.evaluate("typeof navigator.share === 'undefined'")
        check("navigator.share est bien absente sur ce navigateur", absente,
              "si elle apparaît un jour, ce probe mesure l'autre branche "
              "et il faut le dire ici plutôt que de le laisser mentir")
        issue = page.evaluate("$bz.verbs.share({url: 'https://exemple.test/vue?f=42'})")
        check("share retombe sur la copie", issue == "copied",
              f"issue : {issue!r}")
        colle = page.evaluate("navigator.clipboard.readText()")
        check("...et c'est bien l'URL qui est dans le presse-papiers",
              colle == "https://exemple.test/vue?f=42", f"lu : {colle!r}")
        defaut = page.evaluate(
            "$bz.verbs.share({}).then(() => navigator.clipboard.readText())")
        check("sans url, c'est la page COURANTE qui part",
              defaut.endswith("/meta"), f"lu : {defaut!r}")

        print("\n7. vibrate — aucune absence à gérer")
        check("navigator.vibrate existe",
              page.evaluate("typeof navigator.vibrate === 'function'"))
        check("l'appel ne lève pas et rend un booléen",
              page.evaluate("typeof $bz.verbs.vibrate(10)") == "boolean")

        check("aucune erreur JS", not erreurs, "; ".join(erreurs[:4]))
        page.screenshot(path="tests/probes/verbs_screenshot.png")

    print()
    if FAILURES:
        print(f"VERBS PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("VERBS PROBE PASSED — les cinq verbes agissent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
