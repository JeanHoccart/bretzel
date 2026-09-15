"""features/pipeline — écran 1 : le pipeline, en kanban glissable.

Ce que cet écran met sous contrainte : ``ui.dropzone`` + ``ui.drag_each``
dans des colonnes qui **défilent**, avec des cartes en largeur contrainte.
Les 17 apps existantes ne glissent que des listes de trois éléments dans un
conteneur qui ne déborde jamais.

Le drop est OPTIMISTE : le navigateur bouge la carte avant toute requête, le
handler mute ou refuse, et le morph remet en place ce que le serveur
contredit. Refuser, c'est ne rien muter — il n'y a pas de ``reject()``.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.components import Move
from bretzel.state import PageState, field, validator
from examples.crm.core.domain import (
    OPEN_STAGES,
    STAGE_COLOR,
    STAGE_LABEL,
    euros,
)
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.deals_data import (
    DealsRev,
    move_deal,
    pipeline_deals,
    pipeline_totals,
)
from examples.crm.features.analyse_nav import analyse_nav

#: Les horizons proposés, en jours. Un pipeline se lit sur un trimestre ;
#: « tout » n'est pas une option — 9 400 cartes ne sont pas une vue.
HORIZONS: tuple[tuple[str, str], ...] = (
    ("30", "30 jours"), ("90", "90 jours"), ("180", "6 mois"),
)

#: Le groupe de glissement. Une carte d'affaire ne tombe que dans une colonne
#: d'affaires — le jour où l'écran gagne une autre zone, le groupe la refuse.
DEAL_GROUP = "deal"


class PipelineUI(PageState):
    """Jusqu'où on regarde. **Plus « qui »** : le portefeuille est un
    cadrage, pas un filtre d'écran, et il vit dans la barre latérale
    (cf. ``access.visible_owner``). Un sélecteur ici serait un second
    contrôle pour la même chose — et, pour un commercial, un contrôle
    qui n'aurait le droit d'avoir qu'une valeur."""

    horizon: str = field(default='90')

    @validator("horizon")
    def _horizon(cls, value: str) -> str:
        allowed = {key for key, _label in HORIZONS}
        return value if value in allowed else "90"


def filter_changed(state: PipelineUI) -> None:
    """La valeur du contrôle changé est hydratée ; ``deps=`` re-render."""


def drop_deal(m: Move) -> None:
    """Ce qu'un drop applique — ou refuse. La vue suffit à le décrire."""
    ui_state = PipelineUI()
    if not move_deal(m, owner=visible_owner(),
                     horizon_days=int(ui_state.horizon)):
        ui.notification(
            "Déplacement refusé — l'affaire n'existe plus, ou la colonne "
            "n'accepte pas cette carte.",
            variant="warning", duration_ms=3000,
        )


def deal_card(deal: dict) -> None:
    with ui.card(padding="sm"):
        with ui.vstack(gap="xs"):
            ui.text(deal["account_name"], weight="medium", size="sm",
                    truncate=True)
            ui.text(deal["name"], color="muted", size="xs", truncate=True)
            with ui.hstack(justify="between", align="center"):
                ui.badge(euros(deal["amount"]), variant="soft",
                         color=STAGE_COLOR[deal["stage"]], size="xs")
                ui.text(deal["close_date"], color="muted", size="xs")


def stage_column(stage: str, deals: list[dict], total: dict | None) -> None:
    shown, overall = len(deals), (total or {}).get("n", 0)
    # Le montant de la FENÊTRE, pas celui des cartes affichées : le plafond
    # coupe le rendu, pas le pipeline.
    amount = (total or {}).get("total") or 0
    with ui.vstack(gap="sm", classes="min-h-0"):
        with ui.hstack(justify="between", align="center"):
            with ui.hstack(gap="xs", align="center"):
                ui.heading(STAGE_LABEL[stage], level=3, size="sm")
                ui.badge(f"{shown} / {overall}", variant="soft",
                         color=STAGE_COLOR[stage], size="xs")
            ui.text(euros(amount), color="muted", size="xs")
        # La colonne défile : c'est ce que l'écran met sous contrainte. La
        # hauteur est bornée par le viewport, pas par le nombre de cartes.
        #
        # ⚠️ **C'est la ZONE qui défile, pas un conteneur autour d'elle.**
        # L'inverse — une ``dropzone`` posée DANS le conteneur qui défile —
        # fait glisser sa bordure avec les cartes : mesuré, après 300 px de
        # défilement la boîte de la zone passe de [52, 472] à [-248, 172],
        # donc son cadre coupe le milieu de la colonne au lieu de
        # l'encadrer, et le surlignage « cette colonne accepte » sort de
        # l'écran pendant le glisser — au moment précis où il sert.
        # Ici la zone EST la fenêtre : sa boîte ne bouge pas d'un pixel.
        with ui.dropzone(
            name=stage, accepts=[DEAL_GROUP], on_move=drop_deal,
            classes="min-h-0 max-h-[calc(100vh-19rem)] overflow-y-auto pr-1",
        ):
            with ui.vstack(gap="sm", classes="pb-2"):
                for deal in ui.drag_each(deals, group=DEAL_GROUP,
                                         key="id"):
                    deal_card(deal)


@refreshable(deps=[PipelineUI, DealsRev, ViewerPrefs])
def board() -> None:
    ui_state = PipelineUI()
    scope = visible_owner()
    deals = pipeline_deals(scope, int(ui_state.horizon))
    totals = pipeline_totals(scope, int(ui_state.horizon))
    with ui.grid(cols={"base": 1, "md": 2, "xl": 4}, gap="md"):
        for stage in OPEN_STAGES:
            stage_column(stage, deals[stage], totals.get(stage))


def filter_bar() -> None:
    # ``ui.grid``, pas ``ui.hstack`` : cf. le commentaire jumeau dans
    # ``contacts.py`` — un ``form_field`` est ``w-full``.
    ui_state = PipelineUI()
    with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
        with ui.form_field(label="Échéance sous"):
            ui.select(value=ui_state.horizon, options=list(HORIZONS),
                      on_change=filter_changed)


@page("/", layout=analyse_nav, title="Pipeline")
def pipeline_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Pipeline", level=1, size="2xl")
        filter_bar()
        board()


feature = Feature(
    name="pipeline",
    kind="page",
    provides=[pipeline_page, PipelineUI],
    uses=["deals_data", "access"],
)
