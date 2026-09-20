"""Foundations — How Bretzel works.

The boundary page: the universal client vs server concept, what each is
for, UI = f(state), and Bretzel's general cycle. Conceptual — zero
signatures. All the rest of the docs rests on this.
"""

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr


_CYCLE = [
    ("mouse-pointer-click", tr('An interaction happens (a click, a keystroke).',
                               'Une interaction se produit (un clic, une '
                               'saisie).')),
    ("server", tr('If it changes the truth, it goes server side: a Python '
                  'function runs.',
                  'Si elle change la vérité, elle passe côté serveur : une '
                  "fonction Python s'exécute.")),
    ("database", tr('This function mutates the state.',
                    "Cette fonction mute l'état.")),
    ("refresh-cw", tr('The part of the interface that depends on that state '
                      'is re-rendered and sent back to the browser.',
                      "La partie de l'interface qui dépend de cet état est "
                      're-rendue et renvoyée au navigateur.')),
]


@page("/how", layout=shell, title="Comment Bretzel fonctionne")
def how_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Comment Bretzel fonctionne", level=1, size="3xl")
            ui.text(
                tr('Every web app has two halves: the browser (the client) '
                   'and the server. Knowing where the code runs — and when '
                   'one crosses from one to the other — is the frame that '
                   'lights up everything else.',
                   'Toute app web a deux moitiés : le navigateur (le client) '
                   'et le serveur. Savoir où tourne le code — et quand on '
                   "passe de l'un à l'autre — est le cadre qui éclaire tout "
                   'le reste.'),
                color="muted", size="lg",
            )

            # ── The two halves ───────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The two halves',
                                  'Les deux moitiés'), level=2)
                    ui.table(
                        columns=[
                            ui.column("cote", label=tr('Half',
                                                       'Moitié')),
                            ui.column("quoi", label=tr('What it is',
                                                       "C'est quoi")),
                        ],
                        rows=[
                            {"cote": "Client",
                             "quoi": tr("the browser, on the user's machine —"
                                        ' it displays and reacts',
                                        'le navigateur, sur la machine de '
                                        "l'utilisateur — il affiche et réagit")},
                            {"cote": "Serveur",
                             "quoi": tr('your machine, where the Python runs '
                                        '— it holds the truth',
                                        'ta machine, où tourne le code Python'
                                        ' — il détient la vérité')},
                        ],
                        size="sm",
                    )

            # ── Pourquoi le serveur ──────────────────────────────────
            with ui.card(color="primary"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Why on the server',
                                  'Pourquoi côté serveur'), level=2)
                    ui.text(
                        tr("The web's basic rule: the client is always wrong."
                           ' Everything arriving from the browser can be '
                           'tampered with. So what matters lives server side:',
                           'Règle de base du web : le client a toujours tort.'
                           ' Tout ce qui arrive du navigateur peut être '
                           'trafiqué. Donc ce qui compte vit côté serveur :'),
                    )
                    with ui.vstack(gap="xs"):
                        for t in [
                            tr('Security — the client is never trusted; the '
                               'validation that protects happens here.',
                               'Sécurité — on ne fait jamais confiance au '
                               'client ; la validation qui protège se fait '
                               'ici.'),
                            tr('Source of truth — the data is stored and '
                               'owned by the server, not by the tab.',
                               'Source de vérité — la donnée est stockée et '
                               "possédée par le serveur, pas par l'onglet."),
                            tr('Confidential logic — a price calculation, a '
                               'business rule must not leave for the browser.',
                               'Logique confidentielle — un calcul de prix, '
                               'une règle métier ne doivent pas partir dans '
                               'le navigateur.'),
                            tr('Sharing — a server state is seen by several '
                               'users / tabs; a client state is not.',
                               'Partage — un état serveur est vu par '
                               'plusieurs utilisateurs / onglets ; un état '
                               'client, non.'),
                        ]:
                            with ui.hstack(align="baseline", gap="sm"):
                                ui.icon("check", color="primary", size="sm")
                                ui.text(t, size="sm")

            # ── Pourquoi le client ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Why on the client',
                                  'Pourquoi côté client'), level=2)
                    ui.text(
                        tr('Going through the server costs a network request.'
                           ' For a purely visual interaction (opening a menu,'
                           ' ticking a box), it is waste. Staying client side'
                           ' means:',
                           'Passer par le serveur coûte une requête réseau. '
                           'Pour une interaction purement visuelle (ouvrir un'
                           " menu, cocher une case), c'est du gaspillage. "
                           "Rester côté client, c'est :"),
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="xs"):
                        for t in [
                            tr('No request — it works with no round trip, '
                               'hence instantly.',
                               'Aucune requête — ça marche sans aller-retour,'
                               " donc c'est instantané."),
                            tr("Lightening the server — it is the user's "
                               'machine doing the work, not yours.',
                               "Allègement du serveur — c'est la machine de "
                               "l'utilisateur qui travaille, pas la tienne."),
                        ]:
                            with ui.hstack(align="baseline", gap="sm"):
                                ui.icon("check", color="success", size="sm")
                                ui.text(t, size="sm")

            # ── UI = f(state) ────────────────────────────────────────
            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading("UI = f(state)", level=2)
                    ui.text(
                        tr('The interface is a function of the state. One '
                           'does not manipulate the DOM by hand: one '
                           'describes what the UI must be for a given state, '
                           'one mutates the state, and the UI is recomputed.',
                           "L'interface est une fonction de l'état. On ne "
                           'manipule pas le DOM à la main : on décrit ce que '
                           "l'UI doit être pour un état donné, on mute "
                           "l'état, et l'UI est recalculée."),
                    )

            # ── Le cycle de Bretzel ──────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr("Bretzel's cycle",
                                  'Le cycle de Bretzel'), level=2)
                    with ui.vstack(gap="sm"):
                        for i, (icon, text) in enumerate(_CYCLE, start=1):
                            with ui.hstack(align="center", gap="sm"):
                                ui.badge(str(i), color="primary", variant="soft")
                                ui.icon(icon, color="primary")
                                ui.text(text, size="sm")
                    ui.text(
                        tr('An interaction that does NOT change the truth '
                           '(opening a panel) short-circuits the server step '
                           'and stays in the browser.',
                           'Une interaction qui NE change PAS la vérité '
                           "(ouvrir un panneau) court-circuite l'étape "
                           'serveur et reste dans le navigateur.'),
                        color="muted", size="sm",
                    )

            # ── An event's paths ────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr("An event's routes",
                                  "Les chemins d'un événement"), level=2)
                    ui.text(
                        tr('Concretely, an event takes one of these routes:',
                           "Concrètement, un événement prend l'un de ces "
                           'chemins :'),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("quoi", label=tr('The event…',
                                                       "L'événement…")),
                            ui.column("ou", label="tourne"),
                            ui.column("ar", label="aller-retour ?"),
                        ],
                        rows=[
                            {"quoi": tr('calls a Python function',
                                        'appelle une fonction Python'),
                             "ou": "serveur", "ar": "oui"},
                            {"quoi": tr('drives a component / a client state',
                                        'pilote un composant / un état client'),
                             "ou": "client", "ar": "non"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        tr('It is the same boundary, applied everywhere: '
                           'state, actions and reactivity each have a server '
                           'side and a client side. The rest of the docs '
                           'follows that plan.',
                           "C'est la même frontière, appliquée partout : "
                           "l'état, les actions et la réactivité ont chacun "
                           'un côté serveur et un côté client. La suite de la'
                           ' doc suit ce plan.'),
                        color="muted", size="sm",
                    )
