"""SUJET — Faire vivre une page sans que personne ne clique.

``ui.interval`` est un composant INVISIBLE : il ne dessine rien, il
déclenche. Un `on_tick` toutes les N secondes, et un drapeau qui
l'arrête.

Ce qui mérite d'être écrit, parce que c'est le choix de conception : la
cadence vit dans la PAGE, pas dans une tâche serveur. Un onglet fermé
cesse de tourner tout seul — il n'y a rien à annuler, aucun cycle de vie
à tenir, et une app qui redémarre ne laisse pas de minuteur orphelin.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/cadence"


@page(PATH, layout=shell, title="La cadence")
def cadence_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Faire vivre une page sans que personne ne clique",
                       level=1, size="3xl")
            ui.text(
                "Un tableau de bord qui se rafraîchit, un compteur qui "
                "descend, un sondage de tâche en cours. Un composant "
                "invisible suffit.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Trois paramètres, et c'est tout", level=2)
                    ui.table(
                        columns=[
                            ui.column("p", label="Paramètre"),
                            ui.column("q", label="Ce qu'il fait"),
                        ],
                        rows=[
                            {"p": "on_tick",
                             "q": "ce qui se déclenche — un handler "
                                  "serveur, ou une chaîne évaluée sur "
                                  "place"},
                            {"p": "seconds",
                             "q": "l'intervalle, en secondes (1.0 par "
                                  "défaut)"},
                            {"p": "active",
                             "q": "un booléen OU une `ClientBinding` — "
                                  "c'est ce qui rend la cadence "
                                  "arrêtable"},
                        ],
                        size="sm",
                    )
                    ui.code(
                        "# Serveur : la zone se re-rend toutes les 5 s.\n"
                        "@refreshable(deps=[Metriques])\n"
                        "def tableau() -> None:\n"
                        "    ui.text(f\"{Metriques().en_cours} en cours\")\n"
                        "\n"
                        "def relever() -> None:\n"
                        "    Metriques().en_cours = compter()\n"
                        "\n"
                        "tableau()\n"
                        "ui.interval(on_tick=relever, seconds=5)\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("L'arrêter — sans tâche à annuler", level=2)
                    ui.text(
                        "`active=` accepte une `ClientBinding`. Un "
                        "interrupteur écrit dans l'état client, "
                        "l'intervalle le lit, et la cadence s'arrête — "
                        "sans aller-retour, et sans qu'aucun cycle de vie "
                        "serveur n'ait à exister.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class Suivi(ClientState):\n"
                        "    en_marche: bool = field(default=True)\n"
                        "\n"
                        "s = Suivi()\n"
                        "ui.switch(value=s.en_marche, label=\"Rafraîchir\")\n"
                        "ui.interval(on_tick=relever, seconds=5,\n"
                        "            active=s.en_marche)\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Sans toucher au serveur", level=2)
                    ui.text(
                        "`on_tick=` est polymorphe, comme tous les "
                        "`on_*` : un callable part en POST signé, une "
                        "CHAÎNE est évaluée sur place. Un compte à "
                        "rebours n'a donc besoin d'aucune requête.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class Minuteur(ClientState):\n"
                        "    restant: int = field(default=60)\n"
                        "\n"
                        "m = Minuteur()\n"
                        "ui.text(m.restant)\n"
                        "ui.interval(on_tick=m.restant.decrement(1),\n"
                        "            seconds=1, active=m.restant > 0)\n",
                        lang="python",
                    )
                    ui.text(
                        "`active=m.restant > 0` est une expression de "
                        "l'algèbre client : elle devient du JavaScript, "
                        "réévalué à chaque changement. Le minuteur "
                        "s'arrête donc tout seul à zéro.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce qu'il faut savoir avant de s'en servir",
                               level=2)
                    ui.alert(
                        "La cadence vit dans la PAGE. Un onglet fermé "
                        "cesse de tourner — ce qui est exactement ce "
                        "qu'on veut pour un rafraîchissement d'écran, et "
                        "exactement ce qu'on ne veut pas pour un travail "
                        "qui doit aboutir. Pour celui-là, c'est "
                        "`@background` — il survit à la réponse, donc au "
                        "départ du visiteur.",
                        color="warning",
                        title="Ce n'est PAS une tâche de fond",
                    )
                    ui.alert(
                        "Chaque tick d'un `on_tick=` serveur est une "
                        "requête. Une seconde d'intervalle sur cinquante "
                        "onglets ouverts fait cinquante requêtes par "
                        "seconde. Quand la donnée vient du serveur et "
                        "change rarement, `@refreshable(broadcast=True)` "
                        "coûte moins : c'est le serveur qui pousse, "
                        "quand il a quelque chose à dire.",
                        color="warning", title="Le coût, en requêtes",
                    )

            with ui.card(color="surface"):
                with ui.hstack(gap="sm", wrap=True, align="baseline"):
                    ui.text("La zone qui se re-rend, et le temps réel :",
                            color="muted", size="sm")
                    ui.link("Réactivité serveur →",
                            href="/reactivity-server")
                    ui.link("Réactivité client →",
                            href="/reactivity-client")
