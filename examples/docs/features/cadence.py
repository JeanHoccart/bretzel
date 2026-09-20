"""TOPIC — Keeping a page alive without anybody clicking.

``ui.interval`` is an INVISIBLE component: it draws nothing, it fires. An
`on_tick` every N seconds, and a flag that stops it.

What is worth writing down, because it is the design choice: the cadence
lives in the PAGE, not in a server task. A closed tab stops ticking on
its own — there is nothing to cancel, no life cycle to hold, and an app
that restarts leaves no orphan timer.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/cadence"


@page(PATH, layout=shell, title=tr('The cadence',
                                   'La cadence'))
def cadence_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Keeping a page alive without anybody clicking',
                          'Faire vivre une page sans que personne ne clique'),
                       level=1, size="3xl")
            ui.text(
                tr('A dashboard that refreshes, a counter going down, polling'
                   ' a running task. An invisible component is enough.',
                   'Un tableau de bord qui se rafraîchit, un compteur qui '
                   'descend, un sondage de tâche en cours. Un composant '
                   'invisible suffit.'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Three parameters, and that is all',
                                  "Trois paramètres, et c'est tout"), level=2)
                    ui.table(
                        columns=[
                            ui.column("p", label=tr('Parameter',
                                                    'Paramètre')),
                            ui.column("q", label="Ce qu'il fait"),
                        ],
                        rows=[
                            {"p": "on_tick",
                             "q": tr('what fires — a server handler, or a '
                                     'string evaluated in place',
                                     'ce qui se déclenche — un handler '
                                     'serveur, ou une chaîne évaluée sur '
                                     'place')},
                            {"p": "seconds",
                             "q": tr('the interval, in seconds (1.0 by '
                                     'default)',
                                     "l'intervalle, en secondes (1.0 par "
                                     'défaut)')},
                            {"p": "active",
                             "q": tr('a boolean OR a `ClientBinding` — that '
                                     'is what makes the cadence stoppable',
                                     'un booléen OU une `ClientBinding` — '
                                     "c'est ce qui rend la cadence arrêtable")},
                        ],
                        size="sm",
                    )
                    ui.code(
                        tr('# Server: the zone re-renders every 5 s.\n@refreshable(deps=[Metrics])\ndef board() -> None:\n    ui.text(f"{Metrics().running} running")\n\ndef sample() -> None:\n    Metrics().running = count()\n\nboard()\nui.interval(on_tick=sample, seconds=5)\n',
                           '# Serveur : la zone se re-rend toutes les 5 s.\n@refreshable(deps=[Metriques])\ndef tableau() -> None:\n    ui.text(f"{Metriques().en_cours} en cours")\n\ndef relever() -> None:\n    Metriques().en_cours = compter()\n\ntableau()\nui.interval(on_tick=relever, seconds=5)\n'),
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Stopping it — with no task to cancel',
                                  "L'arrêter — sans tâche à annuler"), level=2)
                    ui.text(
                        tr('`active=` accepts a `ClientBinding`. A switch '
                           'writes into the client state, the interval reads '
                           'it, and the cadence stops — with no round trip, '
                           'and with no server lifecycle needing to exist.',
                           '`active=` accepte une `ClientBinding`. Un '
                           "interrupteur écrit dans l'état client, "
                           "l'intervalle le lit, et la cadence s'arrête — "
                           "sans aller-retour, et sans qu'aucun cycle de vie "
                           "serveur n'ait à exister."),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('class Monitoring(ClientState):\n    running: bool = field(default=True)\n\nm = Monitoring()\nui.switch(value=m.running, label="Refresh")\nui.interval(on_tick=sample, seconds=5,\n            active=m.running)\n',
                           'class Suivi(ClientState):\n    en_marche: bool = field(default=True)\n\ns = Suivi()\nui.switch(value=s.en_marche, label="Rafraîchir")\nui.interval(on_tick=relever, seconds=5,\n            active=s.en_marche)\n'),
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Without touching the server',
                                  'Sans toucher au serveur'), level=2)
                    ui.text(
                        tr('`on_tick=` is polymorphic, like every `on_*`: a '
                           'callable leaves as a signed POST, a STRING is '
                           'evaluated in place. So a countdown needs no '
                           'request at all.',
                           '`on_tick=` est polymorphe, comme tous les `on_*` '
                           ': un callable part en POST signé, une CHAÎNE est '
                           "évaluée sur place. Un compte à rebours n'a donc "
                           "besoin d'aucune requête."),
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
                        tr('`active=m.remaining > 0` is an expression of the '
                           'client algebra: it becomes JavaScript, re-'
                           'evaluated on every change. So the timer stops by '
                           'itself at zero.',
                           '`active=m.restant > 0` est une expression de '
                           "l'algèbre client : elle devient du JavaScript, "
                           'réévalué à chaque changement. Le minuteur '
                           "s'arrête donc tout seul à zéro."),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce qu'il faut savoir avant de s'en servir",
                               level=2)
                    ui.alert(
                        tr('The cadence lives in the PAGE. A closed tab stops'
                           ' running — which is exactly what one wants for a '
                           'screen refresh, and exactly what one does not '
                           'want for work that must finish. For that, it is '
                           '`@background` — it survives the response, hence '
                           "the visitor's departure.",
                           'La cadence vit dans la PAGE. Un onglet fermé '
                           "cesse de tourner — ce qui est exactement ce qu'on"
                           " veut pour un rafraîchissement d'écran, et "
                           "exactement ce qu'on ne veut pas pour un travail "
                           "qui doit aboutir. Pour celui-là, c'est "
                           '`@background` — il survit à la réponse, donc au '
                           'départ du visiteur.'),
                        color="warning",
                        title=tr('This is NOT a background task',
                                 "Ce n'est PAS une tâche de fond"),
                    )
                    ui.alert(
                        tr('Every tick of a server `on_tick=` is a request. A'
                           ' one-second interval across fifty open tabs makes'
                           ' fifty requests a second. When the data comes '
                           'from the server and changes rarely, '
                           '`@refreshable(broadcast=True)` costs less: it is '
                           'the server that pushes, when it has something to '
                           'say.',
                           "Chaque tick d'un `on_tick=` serveur est une "
                           "requête. Une seconde d'intervalle sur cinquante "
                           'onglets ouverts fait cinquante requêtes par '
                           'seconde. Quand la donnée vient du serveur et '
                           'change rarement, `@refreshable(broadcast=True)` '
                           "coûte moins : c'est le serveur qui pousse, quand "
                           'il a quelque chose à dire.'),
                        color="warning", title=tr('The cost, in requests',
                                                  'Le coût, en requêtes'),
                    )

            with ui.card(color="surface"):
                with ui.hstack(gap="sm", wrap=True, align="baseline"):
                    ui.text(tr('The zone that re-renders, and realtime:',
                               'La zone qui se re-rend, et le temps réel :'),
                            color="muted", size="sm")
                    ui.link(tr('Server reactivity →',
                               'Réactivité serveur →'),
                            href="/reactivity-server")
                    ui.link(tr('Client reactivity →',
                               'Réactivité client →'),
                            href="/reactivity-client")
