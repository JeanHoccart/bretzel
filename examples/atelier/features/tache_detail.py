"""features/tache_detail — page : la frise d'UNE tâche, appel par appel.

La liste dit qu'une tâche a coûté quinze cycles. Cet écran dit lesquels,
et sur quoi. C'est là qu'on lit le geste : trois lectures, une écriture,
une suite lancée, un rouge, une écriture de deux lignes, la suite
relancée — et ainsi de suite.

⚠️ La page est routée par un paramètre (``/tache/{tache_id}``), donc elle
se partage : c'est ce qui permet de pointer une tâche précise plutôt que
de la décrire.
"""

from __future__ import annotations

from bretzel import Feature, page, ui
from examples.atelier.core.phases import (
    COULEURS,
    CYCLES_MAX,
    LIBELLES,
    strip_prelude,
)
from examples.atelier.features.shell import shell
from examples.atelier.features.taches_data import appels_de, tache

#: La couleur de chaque phase. Elle porte le sens sur cet écran : c'est
#: par la couleur qu'on voit le ping-pong sans lire une ligne.
#: Importées, pas recopiées : la légende, la frise de la liste et celle
#: de la fiche doivent dire la MÊME chose.


def ligne_appel(appel: dict) -> None:
    """Un appel : sa phase, son outil, ce qu'il a lancé, son verdict."""
    with ui.hstack(gap="sm", align="center", classes="py-1"):
        ui.text(str(appel["ordre"]), size="xs", color="muted",
                classes="w-8 text-right font-mono")
        ui.badge(appel["phase"], color=COULEURS.get(appel["phase"], "muted"),
                 variant="soft", size="xs")
        ui.text(appel["outil"], size="xs", weight="medium", classes="w-28")
        # ⚠️ Sans le préambule. Chaque commande de ce dépôt commence par
        # les 45 mêmes caractères de ``cd "…/bretzel" &&``, qui poussaient
        # le verbe utile hors de la colonne. On le retire déjà pour
        # CLASSER l'appel ; ne pas le faire pour l'afficher était une
        # asymétrie, pas une décision.
        ui.text(strip_prelude(appel["commande"]) or "—", size="xs",
                color="muted", classes="flex-1 min-w-0 truncate font-mono")
        if appel["erreur"]:
            ui.badge("erreur", color="error", variant="soft", size="xs")


@page("/tache/{tache_id}", title="Tâche", layout=shell)
def tache_detail(tache_id: int) -> None:
    """Le déroulé complet d'une tâche."""
    fiche = tache(tache_id)
    if fiche is None:
        ui.alert("Cette tâche n'existe pas.", color="error")
        ui.link("Retour au rythme", href="/")
        return

    appels = appels_de(tache_id)

    with ui.vstack(gap="lg", classes="h-full min-h-0"):
        ui.link("← Retour au rythme", href="/")
        # ⚠️ Coupé : une demande peut être du code collé, et un titre de
        # trois lignes de `Bretzel(title=…, secret_key=…)` ne se lit pas.
        demande = (fiche["demande"] or "(demande vide)").replace("\n", " ")
        ui.heading(
            demande[:110].rstrip() + " …" if len(demande) > 110 else demande,
            level=2,
        )

        with ui.hstack(gap="md", wrap=True):
            ui.badge(fiche["verdict"], variant="soft",
                     color="error" if fiche["cycles"] > CYCLES_MAX else "success")
            ui.text(f"{fiche['appels']} appels", size="sm", color="muted")
            ui.text(f"{fiche['cycles']} cycles de vérification", size="sm",
                    color="muted")
            ui.text(f"{fiche['minutes']} min", size="sm", color="muted")
            ui.text(f"{fiche['erreurs']} erreurs", size="sm", color="muted")

        with ui.card(), ui.vstack(gap="xs"):
            ui.text("La frise", size="sm", weight="medium")
            ui.text(fiche["frise"] or "—", classes="font-mono text-sm")
            ui.text(
                " · ".join(f"{lettre} = {LIBELLES[phase]}" for phase, lettre in (
                    ("lecture", "L"), ("ecriture", "É"),
                    ("verification", "V"), ("livraison", "C"),
                )),
                size="xs", color="muted",
            )

        # Pas de `ui.pane` : la coque en pose déjà un, et deux régions
        # imbriquées font deux barres de défilement.
        with ui.vstack(gap="none"):
            for appel in appels:
                ligne_appel(appel)


feature = Feature(
    name="tache_detail",
    kind="page",
    uses=["taches_data", "shell", "phases"],
    provides=[tache_detail],
)
