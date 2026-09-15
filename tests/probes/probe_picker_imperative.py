"""Probe — la surface impérative des pickers FAIT-elle quelque chose ?

Un test Python peut affirmer que ``mp.open()`` rend du JavaScript. Il ne
peut pas dire que ce JavaScript ouvre le panneau — et c'est la seule
chose qui compte. Le mode d'échec redouté est précisément celui-là : la
méthode existe, elle émet une commande valide, **personne ne l'écoute**,
et il ne se passe rien. Ça ne lève pas, ça ne s'affiche pas, ça ne se
voit pas en revue.

⚠️ C'est arrivé pendant l'écriture : les sept méthodes rendaient leur JS
et le root ne portait AUCUN ``bz-on:bz-open`` — mesuré sur le HTML avant
d'ouvrir un navigateur. D'où ce fichier, qui clique pour de vrai.

Run :  py tests/probes/probe_picker_imperative.py
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FAILURES: list[str] = []

#: Les deux autres composants de la MÊME forme — un panneau ancré qui
#: porte une valeur. Ils ont reçu ``open`` / ``close`` / ``toggle`` le
#: même jour, pour que la nature et la surface coïncident.
#:
#: ⚠️ Ils ne passent QUE les trois vérifications de panneau : leur champ
#: visible n'est pas un ``<input>`` (Select rend un ``<button
#: role=combobox>``), donc les sondes de valeur écrites pour les pickers
#: n'y voudraient rien dire. Leur moitié valeur est livrée depuis
#: longtemps et couverte ailleurs.
PANNEAUX: tuple[tuple[str, dict], ...] = (
    ("select", {"options": ["fr", "de", "es"]}),
    ("combobox", {"options": ["fr", "de", "es"]}),
)

#: Les six pickers, avec une valeur valide pour chacun — le format est
#: leur seule vraie différence.
PICKERS: tuple[tuple[str, str], ...] = (
    ("date_picker", "2026-09-15"),
    ("date_range_picker", "2026-09-01"),
    ("month_picker", "2026-09"),
    ("week_picker", "2026-W37"),
    ("time_picker", "14:30"),
    ("color_picker", "#27754a"),
)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


def build_app():
    from bretzel import Bretzel, page, ui

    app = Bretzel(secret_key="probe-picker-imperative-secret!!!",
                  title="Bretzel · pickers", mode="dev")

    @page("/")
    def home() -> None:
        # ⚠️ La disposition est LOAD-BEARING, et la première version l'a
        # appris à ses dépens : les boutons étaient AU-DESSUS de leur
        # picker. `.open()` marchait — et le panneau ouvert RECOUVRAIT
        # les boutons, donc Playwright ne pouvait plus cliquer
        # « fermer ». L'échec disait donc le contraire de ce qu'il
        # mesurait.
        #
        # D'où : le picker à GAUCHE, étroit, et ses boutons à sa DROITE.
        # Un panneau ancré tombe sous son champ, à la largeur de son
        # champ — il ne peut plus atteindre ce qui est à côté.
        with ui.vstack(gap="lg", classes="p-8"):
            tous = [(n, v, {}) for n, v in PICKERS] + [
                (n, None, kw) for n, kw in PANNEAUX
            ]
            for nom, valeur, kwargs in tous:
                with ui.hstack(gap="lg", align="start"):
                    with ui.container(classes="w-64 shrink-0"):
                        composant = getattr(ui, nom)(id=nom, **kwargs)
                    with ui.hstack(gap="sm", align="center"):
                        ui.text(nom, size="sm", classes="font-mono")
                        ui.button("ouvrir", id=f"{nom}-open",
                                  on_click=composant.open())
                        ui.button("fermer", id=f"{nom}-close",
                                  on_click=composant.close())
                        ui.button("basculer", id=f"{nom}-toggle",
                                  on_click=composant.toggle())
                        if valeur is not None:
                            ui.button("poser", id=f"{nom}-set",
                                      on_click=composant.set(valeur))
                            ui.button("vider", id=f"{nom}-clear",
                                      on_click=composant.clear())
                            ui.button("focus", id=f"{nom}-focus",
                                      on_click=composant.focus())

    app.include(home)
    return app


def panneau_ouvert(page, nom: str) -> bool:
    """Le panneau du picker est-il VISIBLE ?

    ⚠️ Ce détecteur s'est trompé DEUX fois, et à chaque fois il a
    accusé le code d'un défaut qu'il n'avait pas :

    1. ``el.__bzScope.open`` — le runtime pose ``_bzScope`` (un seul
       souligné), et pas sur cet élément. Six faux rouges ;
    2. ``[bz-show=open]`` — il existe bien un élément qui porte ça, mais
       **ce n'est pas le panneau**. Le vrai panneau n'a aucun
       ``bz-show`` : il est piloté par un ``bz-effect`` et porte
       ``bz-ref`` + ``data-side``. Six faux rouges de plus, alors que le
       ``display`` du bon élément passait bien de ``none`` à ``block``.

    D'où la règle qu'on aurait dû suivre d'emblée : ne pas deviner le
    sélecteur, mais chercher **ce dont le display CHANGE** — c'est ainsi
    que le bon élément a fini par être trouvé.
    """
    return page.evaluate(
        """(nom) => {
             const el = document.getElementById(nom);
             if (!el) return false;
             // Ni `bz-show`, ni `bz-ref` : on cherche ce que l'oeil voit
             // — un panneau flottant AFFICHÉ. C'est la seule définition
             // qui n'ait pas eu besoin d'être corrigée.
             return [...el.querySelectorAll('*')].some(e =>
               (e.className || '').includes('absolute')
               && getComputedStyle(e).display !== 'none');
           }""",
        nom,
    )


def champ_visible(page, nom: str) -> str:
    """La valeur du champ que l'utilisateur VOIT.

    Le premier ``<input>`` d'un picker est le porteur caché ; lire sa
    valeur mesurerait le formulaire, pas l'écran.
    """
    return page.evaluate(
        "(nom) => document.getElementById(nom)"
        ".querySelector('input:not([type=hidden])').value",
        nom,
    )


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

        for nom, valeur in PICKERS:
            print(f"\n  ── {nom} ──")

            check(f"{nom} : le panneau part FERMÉ",
                  not panneau_ouvert(page, nom))

            page.click(f"#{nom}-open")
            page.wait_for_timeout(250)
            check(f"{nom} : .open() ouvre le panneau",
                  panneau_ouvert(page, nom))

            page.click(f"#{nom}-close")
            page.wait_for_timeout(250)
            check(f"{nom} : .close() le referme",
                  not panneau_ouvert(page, nom))

            page.click(f"#{nom}-set")
            page.wait_for_timeout(250)
            pose = champ_visible(page, nom)
            check(f"{nom} : .set() écrit la valeur", bool(pose),
                  f"champ = {pose!r} (posé : {valeur!r})")

            page.click(f"#{nom}-clear")
            page.wait_for_timeout(250)
            vide = champ_visible(page, nom)
            check(f"{nom} : .clear() la retire", not vide,
                  f"champ = {vide!r}")

            page.click(f"#{nom}-focus")
            page.wait_for_timeout(200)
            focus = page.evaluate(
                "(nom) => document.activeElement === "
                "document.getElementById(nom)"
                ".querySelector('input:not([type=hidden])')", nom)
            check(f"{nom} : .focus() vise son champ", focus)

        # Les deux autres de la même forme : seules les trois
        # vérifications de PANNEAU s'y appliquent (cf. `PANNEAUX`).
        for nom, _kwargs in PANNEAUX:
            print(f"\n  ── {nom} ──")
            check(f"{nom} : le panneau part FERMÉ",
                  not panneau_ouvert(page, nom))
            page.click(f"#{nom}-open")
            page.wait_for_timeout(250)
            check(f"{nom} : .open() ouvre le panneau",
                  panneau_ouvert(page, nom))
            page.click(f"#{nom}-close")
            page.wait_for_timeout(250)
            check(f"{nom} : .close() le referme",
                  not panneau_ouvert(page, nom))
            page.click(f"#{nom}-toggle")
            page.wait_for_timeout(250)
            check(f"{nom} : .toggle() le rouvre",
                  panneau_ouvert(page, nom))
            page.click(f"#{nom}-toggle")
            page.wait_for_timeout(250)

        check("aucune erreur JS", not erreurs, "; ".join(erreurs[:4]))

    print()
    if FAILURES:
        print(f"PICKER IMPERATIVE PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("PICKER IMPERATIVE PROBE PASSED — les sept méthodes AGISSENT.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
