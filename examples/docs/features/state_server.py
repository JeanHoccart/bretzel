"""STATE — Server state.

The server side of state: the truth. Four scopes according to reach and
lifetime, the declaration (field / validator / computed), and "mutate →
re-render" shown live. The mirror at the bottom reads this page's classes
from the code.
"""

from __future__ import annotations

import datetime
import decimal
import enum
import uuid

from bretzel import page, refreshable, ui
from bretzel.state import (
    AppState,
    PageState,
    SessionState,
    computed,
    field,
    validator,
)
from examples.docs.features.shell import shell
from examples.docs.lib.blocks import source_block, state_mirror
from examples.docs.lib.i18n import tr

PATH = "/state-server"


# ── Demonstration states (the mirror reads them live) ───────────────────

class SrvCounter(SessionState):
    """A server counter — survives the session, mutated by a handler."""

    n: int = field(default=0)


class Cart(SessionState):
    """A rich example — field / factory / validator / computed together."""

    items: list[dict] = field(default_factory=list)
    coupon: str = field(default='')
    discount: float = field(default=0.0)

    @validator("coupon")
    def _upper(self, value: str) -> str:
        return value.strip().upper()

    @computed
    def total(self) -> float:
        raw = sum(it.get("price", 0.0) for it in self.items)
        return raw * (1 - self.discount)


class Etat(enum.Enum):
    """An app enum — the store files it by its VALUE."""

    BROUILLON = "brouillon"
    ENVOYEE = "envoyee"


class Facture(SessionState):
    """BUSINESS types filed as they are — not strings to re-parse."""

    emise: datetime.date = field(default_factory=datetime.date.today)
    montant: decimal.Decimal = field(default_factory=lambda: decimal.Decimal("0"))
    reference: uuid.UUID = field(default_factory=uuid.uuid4)
    etat: Etat = field(default=Etat.BROUILLON)


class Visites(AppState):
    """A total SHARED by the whole process — hence `merge="add"`."""

    vues: int = field(default=0, merge="add")


class Ventes(PageState, addressable=True):
    """State in the ADDRESS — two fields published, one that is not."""

    region: str = field(default="all", url="region")
    mini: int = field(default=0, url="mini")
    #: No ``url=``: so this field cannot be published, even with
    #: ``addressable=True``. It is the guarantee, not a guideline.
    notes: str = field(default="")


def bump() -> None:
    SrvCounter().n += 1


def decr() -> None:
    SrvCounter().n -= 1


@refreshable(deps=[SrvCounter])
def counter_demo() -> None:
    c = SrvCounter()
    with ui.hstack(align="center", gap="md"):
        ui.button("−", variant="outline", on_click=decr, disabled=c.n == 0)
        ui.heading(str(c.n), level=2, size="2xl",
                   classes="font-mono w-12 text-center")
        ui.button("+1", on_click=bump)
    ui.text(
        tr('Click → the handler mutates `SrvCounter().n` → the '
           '`deps=[SrvCounter]` zone re-renders. One server round trip.',
           'Clic → le handler mute `SrvCounter().n` → la zone '
           '`deps=[SrvCounter]` se re-render. Un aller-retour serveur.'),
        color="muted", size="sm",
    )


@page(PATH, layout=shell, title=tr('Server state',
                                   'État serveur'))
def state_server_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Server state',
                          'État serveur'), level=1, size="3xl")
            ui.text(
                tr('Server state is the source of truth: it lives in Python, '
                   'it is stored server side, it can be shared and protected.'
                   ' One inherits from one of the pre-scoped bases according '
                   'to the scope wanted.',
                   "L'état serveur est la source de vérité : il vit en "
                   'Python, il est stocké côté serveur, il peut être partagé '
                   "et protégé. On hérite d'une des bases pré-scopées selon "
                   'la portée voulue.'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The four scopes',
                                  'Les quatre scopes'), level=2)
                    ui.text(
                        tr('One does not pass `scope=`: one inherits from the'
                           ' base. The lifetime changes, the API is '
                           'identical.',
                           'On ne passe pas `scope=` : on hérite de la base. '
                           "La durée de vie change, l'API est identique."),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("scope", label="Base"),
                            ui.column("vit", label=tr('Scope',
                                                      'Portée')),
                            ui.column("survie", label=tr('Lifetime',
                                                         'Durée de vie')),
                        ],
                        rows=[
                            {"scope": "PageState", "vit": tr('1 page shown',
                                                             '1 page affichée'),
                             "survie": tr('survives actions (POST), reset on '
                                          'F5 / nav',
                                          'survit aux actions (POST), reset '
                                          'au F5 / nav')},
                            {"scope": "SessionState", "vit": "cookie de session",
                             "survie": tr('until the session expires',
                                          "jusqu'à expiration de la session")},
                            {"scope": "UserState", "vit": tr('authenticated account',
                                                             'compte authentifié'),
                             "survie": tr('AuthRequiredError with no auth',
                                          'AuthRequiredError sans auth')},
                            {"scope": "AppState", "vit": "process entier",
                             "survie": tr('shared by every request',
                                          'partagé par toutes les requêtes')},
                        ],
                        size="sm",
                    )
                    ui.text(
                        tr('A simple rule: start with `PageState`; move up to'
                           ' Session / User / App only when sharing demands '
                           'it.',
                           'Règle simple : commence par `PageState` ; monte '
                           'vers Session / User / App seulement quand le '
                           "partage l'exige."),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Muter → re-render", level=2)
                    ui.text(
                        tr('A handler mutates the state; every '
                           '`@refreshable(deps=[…])` zone that reads that '
                           'state is re-rendered automatically. The detail '
                           '(controlling what re-renders, realtime) is in '
                           '“Server reactivity”.',
                           "Un handler mute l'état ; toute zone "
                           '`@refreshable(deps=[…])` qui lit cet état est re-'
                           'rendue automatiquement. Le détail (contrôler ce '
                           'qui se re-rend, temps réel) est dans « Réactivité'
                           ' serveur ».'),
                        color="muted", size="sm",
                    )
                    ui.divider()
                    counter_demo()

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Declaring a state',
                                  'Déclarer un état'), level=2)
                    ui.text(
                        tr('An immutable default → directly. A mutable '
                           'default → `field(default_factory=…)`. '
                           '`@validator` normalises on write, `@computed` '
                           'derives automatically.',
                           'Défaut immutable → directement. Défaut mutable → '
                           '`field(default_factory=…)`. `@validator` '
                           "normalise à l'écriture, `@computed` dérive "
                           'automatiquement.'),
                        color="muted", size="sm",
                    )
                    source_block(Cart)

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Business types in the store',
                                  'Les types métier au magasin'), level=2)
                    ui.text(
                        tr('A field is not limited to what JSON can write. '
                           '`date`, `datetime`, `Decimal`, `UUID` and any app'
                           ' enumeration cross the store and come back the '
                           'RIGHT type — you never read back a string to re-'
                           'parse. The containers follow: `list[date]`, '
                           '`dict[str, Decimal]`.',
                           "Un champ n'est pas limité à ce que JSON sait "
                           'écrire. `date`, `datetime`, `Decimal`, `UUID` et '
                           "toute énumération d'app traversent le magasin et "
                           'reviennent du BON type — tu ne relis jamais une '
                           'chaîne à re-parser. Les conteneurs suivent : '
                           '`list[date]`, `dict[str, Decimal]`.'),
                        color="muted", size="sm",
                    )
                    source_block(Facture)
                    ui.text(
                        tr('For a type of your own, `register_type(MyType, '
                           'encode=…, decode=…)` once at startup. It is the '
                           'same route as the shipped types: there is no '
                           'special case reserved for the framework.',
                           'Pour un type à toi, `register_type(MonType, '
                           "encode=…, decode=…)` une fois au démarrage. C'est"
                           " la même route que les types livrés : il n'y a "
                           'pas de cas particulier réservé au framework.'),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What concurrency breaks',
                                  'Ce que la concurrence casse'), level=2)
                    ui.text(
                        tr('Two requests writing the SAME field do not see '
                           'each other. The commit writes only the fields '
                           'touched, so two gestures on different fields '
                           'coexist with no effort — but two gestures on the '
                           'same total lose each other, in silence: the '
                           'counter advances more slowly than the clicks, and'
                           ' only a second user reveals it.',
                           'Deux requêtes qui écrivent le MÊME champ ne se '
                           "voient pas. Le commit n'écrit que les champs "
                           'touchés, donc deux gestes sur des champs '
                           'différents cohabitent sans rien faire — mais deux'
                           " gestes sur le même total se perdent l'un "
                           "l'autre, en silence : le compteur avance moins "
                           'vite que les clics, et seul un second utilisateur'
                           ' le révèle.'),
                        color="muted", size="sm",
                    )
                    source_block(Visites)
                    ui.text(
                        tr('`merge="add"` declares the field ADDITIVE: the '
                           'store combines the two increments instead of '
                           'keeping one. With no waiting, no lock. `bretzel '
                           'check` has a rule for forgetting it (`undeclared-'
                           'shared-counter`), because the mistake neither '
                           'raises nor shows.',
                           '`merge="add"` déclare le champ ADDITIF : le '
                           "magasin combine les deux incréments au lieu d'en "
                           'garder un. Sans attente, sans verrou. `bretzel '
                           "check` a une règle pour l'oubli (`undeclared-"
                           'shared-counter`), parce que la faute ne lève pas '
                           "et ne s'affiche pas."),
                        color="muted", size="sm",
                    )
                    ui.divider()
                    ui.text(
                        tr('When the gesture COMPUTES from what it read — '
                           'filtering a list, removing an item — no merge can'
                           ' repair it. There, one serialises:',
                           "Quand le geste CALCULE à partir de ce qu'il a lu "
                           '— filtrer une liste, en retirer un élément — '
                           'aucune fusion ne peut le réparer. Là, on '
                           'sérialise :'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def supprimer(cible: str) -> None:\n"
                        "    with Kanban.lock() as store:\n"
                        "        store.taches = [t for t in store.taches\n"
                        "                        if t[\"id\"] != cible]\n",
                        lang="python",
                    )
                    ui.text(
                        tr('The block is a small transaction: the lock taken '
                           'THEN the state re-read on entry, the fields '
                           'written THEN the lock released on exit. Two '
                           'requests on the same key wait for each other — '
                           'that is the price, and it is paid only there. '
                           '`async with` inside an `async def`.',
                           'Le bloc est une petite transaction : verrou pris '
                           "PUIS état relu à l'entrée, champs écrits PUIS "
                           'verrou relâché à la sortie. Deux requêtes sur la '
                           "même clé s'attendent — c'est le prix, et il n'est"
                           ' payé que là. `async with` dans un `async def`.'),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('State in the URL',
                                  "L'état dans l'URL"), level=2)
                    ui.text(
                        tr('A `PageState` is keyed by a render uuid that is '
                           'NEW at every navigation: that is why a sort or a '
                           'filter survives neither a page change nor the '
                           'back button. Declaring the fields the URL is '
                           'authoritative for makes the view shareable by '
                           "link, and the browser's arrows go back and forth "
                           'again.',
                           'Un `PageState` est indexé par un uuid de rendu '
                           "NEUF à chaque navigation : c'est pourquoi un tri "
                           'ou un filtre ne survit ni au changement de page '
                           'ni au bouton retour. Déclarer les champs dont '
                           "l'URL fait foi rend la vue partageable par lien, "
                           "et les flèches du navigateur refont l'aller-"
                           'retour.'),
                        color="muted", size="sm",
                    )
                    source_block(Ventes)
                    ui.text(
                        tr('`field(url=…)` NAMES, `addressable=True` TURNS ON'
                           ' — and the two are separate because a published '
                           'field is PUBLIC: browser history, access logs, '
                           '`Referer` header. A field nothing has named '
                           'cannot leave by accident; that is how '
                           '`DatatableState.filters` stays out of the address'
                           ' by construction. To survive a navigation WITHOUT'
                           ' being published, it is the scope you need: '
                           '`scope="session"`.',
                           '`field(url=…)` NOMME, `addressable=True` ALLUME —'
                           " et les deux sont séparés parce qu'un champ "
                           'publié est PUBLIC : historique du navigateur, '
                           "logs d'accès, en-tête `Referer`. Un champ que "
                           "rien n'a nommé ne peut pas partir par accident ; "
                           "c'est ainsi que `DatatableState.filters` reste "
                           "hors de l'adresse par construction. Pour survivre"
                           " à une navigation SANS être publié, c'est la "
                           'portée qu\'il faut : `scope="session"`.'),
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="md"):
                    ui.heading(tr('The states, at a glance',
                                  'Récapitulatif des états'), level=2)
                    ui.text(
                        tr('Scope, fields (type, default, validators) and '
                           "computed of this page's states — read at render "
                           'time from the code.',
                           'Scope, champs (type, défaut, validators) et '
                           'computed des états de cette page — lus au render '
                           'dans le code.'),
                        color="muted", size="sm",
                    )
                    for cls in (SrvCounter, Cart, Facture, Visites, Ventes):
                        with ui.card():
                            state_mirror(cls)
