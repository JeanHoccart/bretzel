"""LES ACTIONS — Actions serveur.

Le côté serveur des actions : brancher un handler sur un événement, ce
qu'on a le droit d'y passer, passer des arguments, lire le formulaire.
Faits vérifiés dans ``server/handlers.py`` + ``server/routing/actions.py``.
"""

from bretzel import page, ui

from examples.docs.features.shell import shell


@page("/actions-server", layout=shell, title="Actions serveur")
def actions_server_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("Actions serveur", level=1, size="3xl")
            ui.text(
                "Le côté serveur des actions : quand une interaction change "
                "la vérité, `on_<event>=` reçoit une fonction Python — un "
                "handler. Un aller-retour, la vérité mute côté serveur.",
                color="muted", size="lg",
            )

            # ── Brancher ─────────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Brancher un handler", level=2)
                    ui.text(
                        "Chaque composant interactif expose des événements "
                        "(`click`, `change`, `input`, `focus`, `blur`, "
                        "`submit`, …). On relie une fonction avec "
                        "`on_<event>=`.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def save() -> None:\n"
                        "    ...\n"
                        "\n"
                        'ui.button("Enregistrer", on_click=save)\n',
                        lang="python",
                    )

            # ── Ce qu'on peut passer ─────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce qu'on peut passer à on_<event>=", level=2)
                    ui.text(
                        "Le handler est retrouvé par son chemin d'import "
                        "(`module::fonction`), sans table stockée par page. "
                        "Il doit donc être adressable.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("forme", label="Forme"),
                            ui.column("ok", label="Accepté ?"),
                        ],
                        rows=[
                            {"forme": "Fonction au niveau module "
                                      "(on_click=save)", "ok": "Oui"},
                            {"forme": "@staticmethod / @classmethod",
                             "ok": "Oui"},
                            {"forme": "functools.partial(handler, arg)",
                             "ok": "Oui — pour passer un argument"},
                            {"forme": "Lambda (on_click=lambda: …)",
                             "ok": "Non — erreur au render"},
                            {"forme": "Closure (fonction définie dans une "
                                      "fonction)", "ok": "Non — erreur au render"},
                            {"forme": "Méthode d'instance",
                             "ok": "Non — non adressable"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        "Une lambda ou une closure n'a pas de chemin d'import "
                        "stable, d'où le refus au moment du rendu.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(
                            "Ceci est le chemin serveur (une fonction). "
                            "`on_<event>=` accepte aussi une chaîne, évaluée "
                            "côté client sans handler — cf.",
                            color="muted", size="sm",
                        )
                        ui.link("Actions client", href="/actions-client")
                        ui.text(".", color="muted", size="sm")

            # ── Passer un argument ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Passer un argument — functools.partial", level=2)
                    ui.text(
                        "Pour donner un argument au handler (typiquement l'id "
                        "d'une ligne), on utilise `partial`. Les arguments "
                        "voyagent avec la requête.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from functools import partial\n"
                        "\n"
                        "def delete_item(item_id: str) -> None:\n"
                        "    ...\n"
                        "\n"
                        "# une ligne par item, chacune avec son id :\n"
                        'ui.icon_button("trash-2",\n'
                        "               on_click=partial(delete_item, item_id))\n",
                        lang="python",
                    )
                    ui.text(
                        "Les arguments doivent être JSON-sérialisables : "
                        "str, int, float, bool, None, list, dict.",
                        color="muted", size="sm",
                    )

            # ── Lire les données du formulaire ───────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Lire les données du formulaire", level=2)
                    ui.text(
                        "Trois façons, selon le besoin :",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from bretzel.state import get\n"
                        "\n"
                        "# 1. un paramètre nommé comme un champ → forwardé\n"
                        "def submit(title: str) -> None:\n"
                        "    ...\n"
                        "\n"
                        "# 2. un paramètre typé State → hydraté depuis le form\n"
                        "def save(form: Draft) -> None:\n"
                        "    # form.title, form.price … déjà remplis + validés\n"
                        "    ...\n"
                        "\n"
                        "# 3. get() → un champ brut, ponctuel\n"
                        "def other() -> None:\n"
                        '    note = get("note")\n',
                        lang="python",
                    )
                    ui.text(
                        "Pas de `name=` à écrire à la main : "
                        "`ui.input(value=draft.title)` dérive le champ `title` "
                        "automatiquement (cf. le chapitre Composants).",
                        color="muted", size="sm",
                    )

            # ── @idempotent ──────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Éviter les doubles envois — @idempotent",
                               level=2)
                    ui.text(
                        "Sur une action sensible (paiement, création), "
                        "`@idempotent` fait qu'un double-envoi du même rendu "
                        "ne s'exécute qu'une fois ; le second reçoit un 204.",
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

            # ── Frontière ────────────────────────────────────────────
            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading("Et ensuite", level=3)
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text("Ce qui se re-rend après le handler :",
                                color="muted", size="sm")
                        ui.link("Réactivité serveur →", href="/reactivity-server")
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text("Agir sans aller-retour :",
                                color="muted", size="sm")
                        ui.link("Actions client →", href="/actions-client")
