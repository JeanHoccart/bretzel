"""L'ÉTAT — État serveur.

Le côté serveur de l'état : la vérité. Quatre scopes selon la portée
et la durée de vie, la déclaration (field / validator / computed), et
« muter → re-render » montré en direct. Le miroir en bas lit les classes
de cette page dans le code.
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

PATH = "/state-server"


# ── États de démonstration (le miroir les lit en direct) ────────────────

class SrvCounter(SessionState):
    """Compteur serveur — survit à la session, muté par un handler."""

    n: int = field(default=0)


class Cart(SessionState):
    """Exemple riche — field / factory / validator / computed réunis."""

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
    """Une énumération d'app — le magasin la range par sa VALEUR."""

    BROUILLON = "brouillon"
    ENVOYEE = "envoyee"


class Facture(SessionState):
    """Des types MÉTIER rangés tels quels — pas des chaînes à re-parser."""

    emise: datetime.date = field(default_factory=datetime.date.today)
    montant: decimal.Decimal = field(default_factory=lambda: decimal.Decimal("0"))
    reference: uuid.UUID = field(default_factory=uuid.uuid4)
    etat: Etat = field(default=Etat.BROUILLON)


class Visites(AppState):
    """Un total PARTAGÉ par tout le process — d'où `merge="add"`."""

    vues: int = field(default=0, merge="add")


class Ventes(PageState, addressable=True):
    """L'état dans l'ADRESSE — deux champs publiés, un qui ne l'est pas."""

    region: str = field(default="all", url="region")
    mini: int = field(default=0, url="mini")
    #: Pas de ``url=`` : ce champ ne peut donc pas être publié, même avec
    #: ``addressable=True``. C'est la garantie, pas une consigne.
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
        "Clic → le handler mute `SrvCounter().n` → la zone `deps=[SrvCounter]` "
        "se re-render. Un aller-retour serveur.",
        color="muted", size="sm",
    )


@page(PATH, layout=shell, title="État serveur")
def state_server_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("État serveur", level=1, size="3xl")
            ui.text(
                "L'état serveur est la source de vérité : il vit en Python, "
                "il est stocké côté serveur, il peut être partagé et protégé. "
                "On hérite d'une des bases pré-scopées selon la portée voulue.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les quatre scopes", level=2)
                    ui.text(
                        "On ne passe pas `scope=` : on hérite de la base. "
                        "La durée de vie change, l'API est identique.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("scope", label="Base"),
                            ui.column("vit", label="Portée"),
                            ui.column("survie", label="Durée de vie"),
                        ],
                        rows=[
                            {"scope": "PageState", "vit": "1 page affichée",
                             "survie": "survit aux actions (POST), reset au F5 / nav"},
                            {"scope": "SessionState", "vit": "cookie de session",
                             "survie": "jusqu'à expiration de la session"},
                            {"scope": "UserState", "vit": "compte authentifié",
                             "survie": "AuthRequiredError sans auth"},
                            {"scope": "AppState", "vit": "process entier",
                             "survie": "partagé par toutes les requêtes"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        "Règle simple : commence par `PageState` ; monte vers "
                        "Session / User / App seulement quand le partage "
                        "l'exige.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Muter → re-render", level=2)
                    ui.text(
                        "Un handler mute l'état ; toute zone `@refreshable"
                        "(deps=[…])` qui lit cet état est re-rendue "
                        "automatiquement. Le détail (contrôler ce qui se "
                        "re-rend, temps réel) est dans « Réactivité serveur ».",
                        color="muted", size="sm",
                    )
                    ui.divider()
                    counter_demo()

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Déclarer un état", level=2)
                    ui.text(
                        "Défaut immutable → directement. Défaut mutable → "
                        "`field(default_factory=…)`. `@validator` normalise "
                        "à l'écriture, `@computed` dérive automatiquement.",
                        color="muted", size="sm",
                    )
                    source_block(Cart)

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les types métier au magasin", level=2)
                    ui.text(
                        "Un champ n'est pas limité à ce que JSON sait "
                        "écrire. `date`, `datetime`, `Decimal`, `UUID` et "
                        "toute énumération d'app traversent le magasin et "
                        "reviennent du BON type — tu ne relis jamais une "
                        "chaîne à re-parser. Les conteneurs suivent : "
                        "`list[date]`, `dict[str, Decimal]`.",
                        color="muted", size="sm",
                    )
                    source_block(Facture)
                    ui.text(
                        "Pour un type à toi, `register_type(MonType, "
                        "encode=…, decode=…)` une fois au démarrage. C'est "
                        "la même route que les types livrés : il n'y a pas "
                        "de cas particulier réservé au framework.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce que la concurrence casse", level=2)
                    ui.text(
                        "Deux requêtes qui écrivent le MÊME champ ne se "
                        "voient pas. Le commit n'écrit que les champs "
                        "touchés, donc deux gestes sur des champs "
                        "différents cohabitent sans rien faire — mais deux "
                        "gestes sur le même total se perdent l'un l'autre, "
                        "en silence : le compteur avance moins vite que les "
                        "clics, et seul un second utilisateur le révèle.",
                        color="muted", size="sm",
                    )
                    source_block(Visites)
                    ui.text(
                        "`merge=\"add\"` déclare le champ ADDITIF : le "
                        "magasin combine les deux incréments au lieu d'en "
                        "garder un. Sans attente, sans verrou. "
                        "`bretzel check` a une règle pour l'oubli "
                        "(`compteur-partage-non-declare`), parce que la "
                        "faute ne lève pas et ne s'affiche pas.",
                        color="muted", size="sm",
                    )
                    ui.divider()
                    ui.text(
                        "Quand le geste CALCULE à partir de ce qu'il a lu — "
                        "filtrer une liste, en retirer un élément — aucune "
                        "fusion ne peut le réparer. Là, on sérialise :",
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
                        "Le bloc est une petite transaction : verrou pris "
                        "PUIS état relu à l'entrée, champs écrits PUIS "
                        "verrou relâché à la sortie. Deux requêtes sur la "
                        "même clé s'attendent — c'est le prix, et il n'est "
                        "payé que là. `async with` dans un `async def`.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("L'état dans l'URL", level=2)
                    ui.text(
                        "Un `PageState` est indexé par un uuid de rendu NEUF "
                        "à chaque navigation : c'est pourquoi un tri ou un "
                        "filtre ne survit ni au changement de page ni au "
                        "bouton retour. Déclarer les champs dont l'URL fait "
                        "foi rend la vue partageable par lien, et les flèches "
                        "du navigateur refont l'aller-retour.",
                        color="muted", size="sm",
                    )
                    source_block(Ventes)
                    ui.text(
                        "`field(url=…)` NOMME, `addressable=True` ALLUME — et "
                        "les deux sont séparés parce qu'un champ publié est "
                        "PUBLIC : historique du navigateur, logs d'accès, "
                        "en-tête `Referer`. Un champ que rien n'a nommé ne "
                        "peut pas partir par accident ; c'est ainsi que "
                        "`DatatableState.filters` reste hors de l'adresse par "
                        "construction. Pour survivre à une navigation SANS "
                        "être publié, c'est la portée qu'il faut : "
                        "`scope=\"session\"`.",
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="md"):
                    ui.heading("Récapitulatif des états", level=2)
                    ui.text(
                        "Scope, champs (type, défaut, validators) et computed "
                        "des états de cette page — lus au render dans le code.",
                        color="muted", size="sm",
                    )
                    for cls in (SrvCounter, Cart, Facture, Visites, Ventes):
                        with ui.card():
                            state_mirror(cls)
