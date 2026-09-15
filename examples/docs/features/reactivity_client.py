"""LA RÉACTIVITÉ — Réactivité client.

Le côté client de la réactivité : quand un état client change, le
navigateur met à jour l'affichage tout seul, sans aller-retour. Lire un
champ d'un ClientState dans un render donne un ClientBinding ; le passer
à une prop réactive (`bz-text`, `bz-show`, `visible=`) câble la mise à
jour live. Les opérateurs composent des ClientExpression.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.state import ClientState, field
from examples.docs.features.shell import shell
from examples.docs.lib.blocks import client_algebra_mirror

PATH = "/reactivity-client"


class PanelUI(ClientState, persist="memory"):
    open: bool = field(default=False)


class NumberUI(ClientState, persist="memory"):
    n: int = field(default=0)


def toggle_demo() -> None:
    panel = PanelUI()
    with ui.vstack(gap="sm"):
        ui.button("Afficher / masquer", on_click=panel.open.toggle())
        with ui.card(color="primary", visible=panel.open):
            ui.text("Je m'affiche via `visible=binding` — bz-show, zéro "
                    "aller-retour.")


def number_demo() -> None:
    num = NumberUI()
    with ui.hstack(align="center", gap="md"):
        ui.button("−", variant="outline", on_click=num.n.decrement())
        ui.text(num.n, weight="bold", classes="font-mono w-8 text-center")
        ui.button("+", on_click=num.n.increment())
        ui.badge("n > 3", color="success", visible=(num.n > 3))


@page(PATH, layout=shell, title="Réactivité client")
def reactivity_client_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("Réactivité client", level=1, size="3xl")
            with ui.hstack(align="baseline", gap="sm", wrap=True):
                ui.text(
                    "Quand un",
                    color="muted", size="lg",
                )
                ui.link("état client", href="/state-client")
                ui.text(
                    "change, le navigateur met à jour l'affichage lui-même — "
                    "sans requête. On câble ça en passant un binding à une "
                    "prop réactive.",
                    color="muted", size="lg",
                )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Lire un état client = un binding", level=2)
                    ui.text(
                        "Lire un champ d'un ClientState dans un render ne "
                        "renvoie pas la valeur brute mais un `ClientBinding` — "
                        "un objet que le composant sait câbler.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("prop", label="Passé à…"),
                            ui.column("effet", label="Câble"),
                        ],
                        rows=[
                            {"prop": "ui.text(binding)",
                             "effet": "bz-text — le texte suit la valeur"},
                            {"prop": "visible=binding",
                             "effet": "bz-show — affiché/masqué selon la valeur"},
                            {"prop": "value=binding (input)",
                             "effet": "bz-model — lecture/écriture two-way"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Afficher une valeur", level=2)
                    ui.text(
                        "Une valeur serveur lue dans un render est une valeur "
                        "Python normale : on l'affiche directement (str, "
                        "f-string). Un ClientBinding se passe tel quel à "
                        "`ui.text()` pour rester réactif ; l'interpoler dans "
                        "un `str()` ou une f-string lève une erreur.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Démo — un binding pilote un bz-show", level=2)
                    toggle_demo()

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Démo — une ClientExpression pilote visible=",
                               level=2)
                    ui.text(
                        "Les opérateurs sur un binding (`num.n > 3`) composent "
                        "une `ClientExpression`, bakée en `bz-show` côté "
                        "client. Zéro aller-retour.",
                        color="muted", size="sm",
                    )
                    number_demo()

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Toute l'algèbre binding → JS", level=2)
                    ui.text(
                        "Chaque opérateur et méthode de `ClientBinding`, lu en "
                        "direct sur la classe, avec le JS qu'il émet réellement "
                        "(capturé en exécutant une sonde). Ajouter un opérateur "
                        "à l'algèbre l'ajoute ici — sans édition. Pièges : "
                        "`&`/`|`/`~` (pas `and`/`or`/`not`), et parenthéser les "
                        "comparaisons composées `(x > 0) & (y < 10)`.",
                        color="muted", size="sm",
                    )
                    client_algebra_mirror()
