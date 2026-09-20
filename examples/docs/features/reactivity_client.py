"""REACTIVITY — Client reactivity.

The client side of reactivity: when a client state changes, the browser
updates the display on its own, with no round trip. Reading a
ClientState field in a render gives a ClientBinding; passing it to a
reactive prop (`bz-text`, `bz-show`, `visible=`) wires the live update.
The operators compose a ClientExpression.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.state import ClientState, field
from examples.docs.features.shell import shell
from examples.docs.lib.blocks import client_algebra_mirror
from examples.docs.lib.i18n import tr

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
            ui.text(tr('I show myself through `visible=binding` — bz-show, '
                       'zero round trips.',
                       "Je m'affiche via `visible=binding` — bz-show, zéro "
                       'aller-retour.'))


def number_demo() -> None:
    num = NumberUI()
    with ui.hstack(align="center", gap="md"):
        ui.button("−", variant="outline", on_click=num.n.decrement())
        ui.text(num.n, weight="bold", classes="font-mono w-8 text-center")
        ui.button("+", on_click=num.n.increment())
        ui.badge("n > 3", color="success", visible=(num.n > 3))


@page(PATH, layout=shell, title=tr('Client reactivity',
                                   'Réactivité client'))
def reactivity_client_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Client reactivity',
                          'Réactivité client'), level=1, size="3xl")
            with ui.hstack(align="baseline", gap="sm", wrap=True):
                ui.text(
                    tr('When a',
                       'Quand un'),
                    color="muted", size="lg",
                )
                ui.link(tr('client state',
                           'état client'), href="/state-client")
                ui.text(
                    tr('changes, the browser updates the display itself — '
                       'with no request. One wires that by passing a binding '
                       'to a reactive prop.',
                       "change, le navigateur met à jour l'affichage lui-même"
                       ' — sans requête. On câble ça en passant un binding à '
                       'une prop réactive.'),
                    color="muted", size="lg",
                )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Reading a client state = a binding',
                                  'Lire un état client = un binding'), level=2)
                    ui.text(
                        tr('Reading a ClientState field inside a render does '
                           'not return the raw value but a `ClientBinding` — '
                           'an object the component knows how to wire.',
                           "Lire un champ d'un ClientState dans un render ne "
                           'renvoie pas la valeur brute mais un '
                           '`ClientBinding` — un objet que le composant sait '
                           'câbler.'),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("prop", label=tr('Passed to…',
                                                       'Passé à…')),
                            ui.column("effet", label=tr('Cable',
                                                        'Câble')),
                        ],
                        rows=[
                            {"prop": "ui.text(binding)",
                             "effet": tr('bz-text — the text follows the value',
                                         'bz-text — le texte suit la valeur')},
                            {"prop": "visible=binding",
                             "effet": tr('bz-show — shown/hidden according to'
                                         ' the value',
                                         'bz-show — affiché/masqué selon la '
                                         'valeur')},
                            {"prop": "value=binding (input)",
                             "effet": tr('bz-model — two-way read/write',
                                         'bz-model — lecture/écriture two-way')},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Displaying a value',
                                  'Afficher une valeur'), level=2)
                    ui.text(
                        tr('A server value read inside a render is an '
                           'ordinary Python value: one displays it directly '
                           '(str, f-string). A ClientBinding is passed as is '
                           'to `ui.text()` to stay reactive; interpolating it'
                           ' into a `str()` or an f-string raises an error.',
                           'Une valeur serveur lue dans un render est une '
                           "valeur Python normale : on l'affiche directement "
                           '(str, f-string). Un ClientBinding se passe tel '
                           'quel à `ui.text()` pour rester réactif ; '
                           "l'interpoler dans un `str()` ou une f-string lève"
                           ' une erreur.'),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Demo — a binding drives a bz-show',
                                  'Démo — un binding pilote un bz-show'), level=2)
                    toggle_demo()

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Demo — a ClientExpression drives visible=',
                                  'Démo — une ClientExpression pilote visible='),
                               level=2)
                    ui.text(
                        tr('The operators on a binding (`num.n > 3`) compose '
                           'a `ClientExpression`, baked into a client-side '
                           '`bz-show`. Zero round trips.',
                           'Les opérateurs sur un binding (`num.n > 3`) '
                           'composent une `ClientExpression`, bakée en `bz-'
                           'show` côté client. Zéro aller-retour.'),
                        color="muted", size="sm",
                    )
                    number_demo()

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The whole binding → JS algebra',
                                  "Toute l'algèbre binding → JS"), level=2)
                    ui.text(
                        tr('Every `ClientBinding` operator and method, read '
                           'live from the class, with the JS it really emits '
                           '(captured by running a probe). Adding an operator'
                           ' to the algebra adds it here — with no editing. '
                           'Traps: `&`/`|`/`~` (not `and`/`or`/`not`), and '
                           'parenthesise compound comparisons `(x > 0) & (y <'
                           ' 10)`.',
                           'Chaque opérateur et méthode de `ClientBinding`, '
                           "lu en direct sur la classe, avec le JS qu'il émet"
                           ' réellement (capturé en exécutant une sonde). '
                           "Ajouter un opérateur à l'algèbre l'ajoute ici — "
                           'sans édition. Pièges : `&`/`|`/`~` (pas '
                           '`and`/`or`/`not`), et parenthéser les '
                           'comparaisons composées `(x > 0) & (y < 10)`.'),
                        color="muted", size="sm",
                    )
                    client_algebra_mirror()
