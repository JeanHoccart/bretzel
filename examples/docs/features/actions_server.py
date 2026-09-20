"""ACTIONS — Server actions.

The server side of actions: wiring a handler onto an event, what may be
passed to it, passing arguments, reading the form. Facts checked in
``server/handlers.py`` + ``server/routing/actions.py``.
"""

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr


@page("/actions-server", layout=shell, title="Actions serveur")
def actions_server_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Actions serveur", level=1, size="3xl")
            ui.text(
                tr('The server side of actions: when an interaction changes '
                   'the truth, `on_<event>=` receives a Python function — a '
                   'handler. One round trip, and the truth mutates server '
                   'side.',
                   'Le côté serveur des actions : quand une interaction '
                   'change la vérité, `on_<event>=` reçoit une fonction '
                   'Python — un handler. Un aller-retour, la vérité mute côté'
                   ' serveur.'),
                color="muted", size="lg",
            )

            # ── Brancher ─────────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Wiring a handler',
                                  'Brancher un handler'), level=2)
                    ui.text(
                        tr('Every interactive component exposes events '
                           '(`click`, `change`, `input`, `focus`, `blur`, '
                           '`submit`, …). One wires a function with '
                           '`on_<event>=`.',
                           'Chaque composant interactif expose des événements'
                           ' (`click`, `change`, `input`, `focus`, `blur`, '
                           '`submit`, …). On relie une fonction avec '
                           '`on_<event>=`.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def save() -> None:\n"
                        "    ...\n"
                        "\n"
                        'ui.button("Enregistrer", on_click=save)\n',
                        lang="python",
                    )

            # ── What may be passed ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What can be passed to on_<event>=',
                                  "Ce qu'on peut passer à on_<event>="), level=2)
                    ui.text(
                        tr('The handler is found again by its import path '
                           '(`module::function`), with no per-page table '
                           'stored. So it must be addressable.',
                           "Le handler est retrouvé par son chemin d'import "
                           '(`module::fonction`), sans table stockée par '
                           'page. Il doit donc être adressable.'),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("forme", label="Forme"),
                            ui.column("ok", label=tr('Accepted?',
                                                     'Accepté ?')),
                        ],
                        rows=[
                            {"forme": "Fonction au niveau module "
                                      "(on_click=save)", "ok": "Oui"},
                            {"forme": "@staticmethod / @classmethod",
                             "ok": "Oui"},
                            {"forme": "functools.partial(handler, arg)",
                             "ok": tr('Yes — to pass an argument',
                                      'Oui — pour passer un argument')},
                            {"forme": "Lambda (on_click=lambda: …)",
                             "ok": "Non — erreur au render"},
                            {"forme": tr('A closure (a function defined '
                                         'inside a function)',
                                         'Closure (fonction définie dans une '
                                         'fonction)'), "ok": "Non — erreur au render"},
                            {"forme": tr('Instance method',
                                         "Méthode d'instance"),
                             "ok": "Non — non adressable"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        tr('A lambda or a closure has no stable import path, '
                           'hence the refusal at render time.',
                           "Une lambda ou une closure n'a pas de chemin "
                           "d'import stable, d'où le refus au moment du "
                           'rendu.'),
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(
                            tr('This is the server route (a function). '
                               '`on_<event>=` also accepts a string, '
                               'evaluated client side with no handler — cf.',
                               'Ceci est le chemin serveur (une fonction). '
                               '`on_<event>=` accepte aussi une chaîne, '
                               'évaluée côté client sans handler — cf.'),
                            color="muted", size="sm",
                        )
                        ui.link("Actions client", href="/actions-client")
                        ui.text(".", color="muted", size="sm")

            # ── Passer un argument ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Passing an argument — functools.partial',
                                  'Passer un argument — functools.partial'), level=2)
                    ui.text(
                        tr('To give the handler an argument (typically a '
                           "row's id), one uses `partial`. The arguments "
                           'travel with the request.',
                           'Pour donner un argument au handler (typiquement '
                           "l'id d'une ligne), on utilise `partial`. Les "
                           'arguments voyagent avec la requête.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('from functools import partial\n\ndef delete_item(item_id: str) -> None:\n    ...\n\n# one row per item, each with its own id:\nui.icon_button("trash-2",\n               on_click=partial(delete_item, item_id))\n',
                           'from functools import partial\n\ndef delete_item(item_id: str) -> None:\n    ...\n\n# une ligne par item, chacune avec son id :\nui.icon_button("trash-2",\n               on_click=partial(delete_item, item_id))\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('The arguments must be JSON-serialisable: str, '
                           'int, float, bool, None, list, dict.',
                           'Les arguments doivent être JSON-sérialisables : '
                           'str, int, float, bool, None, list, dict.'),
                        color="muted", size="sm",
                    )

            # ── Reading the form data ───────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr("Reading the form's data",
                                  'Lire les données du formulaire'), level=2)
                    ui.text(
                        tr('Three ways, depending on the need:',
                           'Trois façons, selon le besoin :'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('from bretzel.state import get\n\n# 1. a parameter named like a field → forwarded\ndef submit(title: str) -> None:\n    ...\n\n# 2. a State-typed parameter → hydrated from the form\ndef save(form: Draft) -> None:\n    # form.title, form.price … already filled + validated\n    ...\n\n# 3. get() → one raw field, occasionally\ndef other() -> None:\n    note = get("note")\n',
                           'from bretzel.state import get\n\n# 1. un paramètre nommé comme un champ → forwardé\ndef submit(title: str) -> None:\n    ...\n\n# 2. un paramètre typé State → hydraté depuis le form\ndef save(form: Draft) -> None:\n    # form.title, form.price … déjà remplis + validés\n    ...\n\n# 3. get() → un champ brut, ponctuel\ndef other() -> None:\n    note = get("note")\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('No `name=` to write by hand: '
                           '`ui.input(value=draft.title)` derives the `title`'
                           ' field automatically (cf. the Components '
                           'chapter).',
                           'Pas de `name=` à écrire à la main : '
                           '`ui.input(value=draft.title)` dérive le champ '
                           '`title` automatiquement (cf. le chapitre '
                           'Composants).'),
                        color="muted", size="sm",
                    )

            # ── @idempotent ──────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Avoiding double submits — @idempotent',
                                  'Éviter les doubles envois — @idempotent'),
                               level=2)
                    ui.text(
                        tr('On a sensitive action (payment, creation), '
                           '`@idempotent` makes a double send of the same '
                           'render run only once; the second receives a 204.',
                           'Sur une action sensible (paiement, création), '
                           "`@idempotent` fait qu'un double-envoi du même "
                           "rendu ne s'exécute qu'une fois ; le second reçoit"
                           ' un 204.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from bretzel import idempotent\n"
                        "\n"
                        "@idempotent\n"
                        "def charge_card() -> None:\n"
                        "    ...\n",
                        lang="python",
                    )

            # ── Boundary ────────────────────────────────────────────
            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading("Et ensuite", level=3)
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(tr('What re-renders after the handler:',
                                   'Ce qui se re-rend après le handler :'),
                                color="muted", size="sm")
                        ui.link(tr('Server reactivity →',
                                   'Réactivité serveur →'), href="/reactivity-server")
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(tr('Acting with no round trip:',
                                   'Agir sans aller-retour :'),
                                color="muted", size="sm")
                        ui.link("Actions client →", href="/actions-client")
