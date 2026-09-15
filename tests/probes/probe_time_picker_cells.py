# -*- coding: utf-8 -*-
"""Probe — les cellules du ``time_picker`` naissent CÔTÉ CLIENT.

Depuis le 2026-09-01, Python ne rend plus les 28 (ou 84) cellules du
panneau : il rend deux colonnes qui se DÉCRIVENT
(``data-bz-values`` / ``data-bz-off``), et ``$bz.time.fill`` les peint.
Le gain est mesuré au rendu — ``ui.time_picker(step=1)`` passe de
**54 491 à 5 166 octets** — mais un octet économisé ne vaut rien si le
panneau ne marche plus, et **aucun test rapide ne peut le dire** : le
HTML SSR est désormais VIDE de cellules, donc un `TestClient` qui
cherche un bouton d'heure ne trouve plus rien, que le runtime marche ou
pas.

C'est donc ce fichier qui porte la preuve. Il vérifie les quatre choses
qu'un rendu client peut casser et qu'un rendu serveur donnait :

1. **les cellules existent**, et en bon nombre ;
2. **le bornage survit** — ``min``/``max`` grisent des heures, et ce
   calcul est resté en Python (les valeurs barrées voyagent en données) ;
3. **le clic écrit la valeur**, heure puis minute, et la minute referme
   le panneau — le seul comportement asymétrique du composant ;
4. **la sélection se repeint**. C'est le point le plus fragile du
   changement : les 84 ``bz-attr:data-selected`` ont été remplacés par
   UN effet. S'il ne se ré-abonne pas, la sélection reste celle du
   premier paint, et ça ne se voit que si on change la valeur.

⚠️ Un bug a été trouvé en écrivant ce probe, et il vaut d'être noté :
la première version passait le scope au helper via ``this``. Dans une
expression de directive, ``this`` n'est PAS le scope — le runtime
mourait au démarrage sur « scope._parts is not a function », donc la
page entière restait sans ``bz-ready``. Ce qui voyage maintenant, ce
sont les données (``_parts()``) et une flèche qui capture ``pick``.

Run :  py tests/probes/probe_time_picker_cells.py
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FAILURES: list[str] = []

#: Le premier picker de ``/time_picker``. La page en porte 49 : toute
#: mesure DOIT être scopée à une instance, sinon on lit le champ de
#: l'une et les cellules d'une autre — l'erreur faite en explorant.
PICKER = ".bz-time-picker"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


def main() -> int:
    from tests.audit.harness import audit_server, browser_context

    with audit_server() as base, browser_context() as ctx:
        page = ctx.new_page()
        erreurs: list[str] = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        page.on("console",
                lambda m: erreurs.append(m.text) if m.type == "error" else None)

        page.goto(f"{base}/time_picker", wait_until="networkidle")
        # Si le helper lève, le runtime ne finit pas son scan et cette
        # attente expire — c'est la panne exacte rencontrée en l'écrivant,
        # donc le premier verdict est gratuit.
        page.wait_for_function(
            "document.documentElement.classList.contains('bz-ready')"
        )
        page.wait_for_timeout(500)

        print("\n1. Les cellules existent")
        vue = page.evaluate("""() => {
            const cells = document.querySelectorAll('[data-bz-v]');
            return {
              colonnes: document.querySelectorAll('[data-bz-part]').length,
              cellules: cells.length,
              barrees: [...cells].filter(c => c.disabled).length,
            };
        }""")
        check("les colonnes sont peintes", vue["cellules"] > 0,
              f"{vue['cellules']} cellule(s) pour {vue['colonnes']} colonne(s)")
        # Deux colonnes par picker, et jamais une colonne vide : une
        # colonne sans cellule est le mode d'échec silencieux du rendu
        # client (le cadre s'affiche, il est creux).
        check("aucune colonne creuse",
              vue["cellules"] >= vue["colonnes"] * 4,
              f"{vue['cellules']} cellules pour {vue['colonnes']} colonnes")

        print("\n2. Le bornage min/max a survécu au déménagement")
        check("des cellules sont grisées quelque part", vue["barrees"] > 0,
              f"{vue['barrees']} cellule(s) disabled — la page a des "
              f"pickers bornés, donc zéro signifierait que ``data-bz-off`` "
              f"n'arrive plus")

        print("\n3. Le clic écrit la valeur — heure, puis minute")
        tp = page.locator(PICKER).first
        champ = tp.locator("input:not([type=hidden])").first
        avant = champ.input_value()
        tp.locator("button[aria-label='Open time picker']").click()
        page.wait_for_timeout(400)

        heure = tp.locator("[data-bz-part='0'] [data-bz-v='14']")
        check("une cellule d'heure est cliquable", heure.is_visible())
        heure.click()
        page.wait_for_timeout(300)
        apres_h = champ.input_value()
        check("le clic sur l'heure écrit la valeur",
              apres_h.startswith("14:"), f"{avant!r} -> {apres_h!r}")
        # Le panneau NE se referme pas sur une heure : l'ordre de lecture
        # est heure puis minute, refermer ici couperait le geste.
        minute = tp.locator("[data-bz-part='1'] [data-bz-v='30']")
        check("le panneau reste ouvert après une heure", minute.is_visible())

        minute.click()
        page.wait_for_timeout(400)
        apres_m = champ.input_value()
        check("le clic sur la minute écrit la valeur",
              apres_m == "14:30", f"{apres_h!r} -> {apres_m!r}")
        check("...et referme le panneau", not minute.is_visible())

        print("\n4. La sélection se REPEINT (l'effet est bien abonné)")
        marquees = tp.evaluate(
            "el => [...el.querySelectorAll('[data-bz-v][data-selected]')]"
            ".map(c => c.getAttribute('data-bz-v'))"
        )
        # Exactement deux : une par colonne. Trois voudrait dire que
        # l'ancienne sélection n'a pas été effacée — le mode d'échec d'un
        # repaint qui ajoute sans retirer.
        check("exactement une cellule marquée par colonne",
              sorted(marquees) == ["14", "30"],
              f"marquées : {marquees}")

        check("aucune erreur JS", not erreurs, "; ".join(erreurs[:4]))
        page.screenshot(path="tests/probes/time_picker_cells_screenshot.png")

    print()
    if FAILURES:
        print(f"TIME PICKER PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("TIME PICKER PROBE PASSED — les cellules vivent côté client.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
