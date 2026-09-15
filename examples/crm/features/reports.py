"""features/reports — écran 7 : les cinq familles de graphiques, sur du SQL.

Ce que cet écran met sous contrainte : ``bar_chart``, ``line_chart``,
``pie_chart``, ``scatter_chart`` et ``sparkline`` nourris par des
``GROUP BY``, pas par des listes écrites à la main. Les données réelles
apportent ce qu'une liste de démo n'apporte jamais — des ordres de grandeur
qui ne s'alignent pas, des trous, des libellés longs, et des valeurs à neuf
chiffres sur un axe de 400 px.

``Series`` s'importe de ``bretzel.components`` — la porte publique existe
pour lui comme pour ``Move``. C'est le contraste avec ``Query``, qui n'en a
aucune (finding 2 du chantier) : trois objets-valeurs du même funnel, deux
exportés, un pas.
"""

from __future__ import annotations

from datetime import date

from bretzel import Feature, page, ui
from bretzel.components import Series
from examples.crm.core.domain import (
    MONTHS_FR_SHORT,
    OPEN_STAGES,
    STAGE_LABEL,
    euros,
)
from examples.crm.features.access import visible_owner
from examples.crm.features.reports_data import (
    accounts_by_industry,
    activities_by_month,
    arr_versus_contacts,
    pipeline_by_stage_and_owner,
    weekly_activity,
)
from examples.crm.features.analyse_nav import analyse_nav


def pipeline_series() -> list[Series]:
    """La matrice (étape, propriétaire) repliée en séries alignées.

    Chaque série doit porter TOUTES les étapes, dans le même ordre : une
    barre groupée aligne ses séries par position, donc un propriétaire qui
    n'a rien en négociation doit y valoir zéro, pas sauter la catégorie.
    """
    rows = pipeline_by_stage_and_owner(visible_owner())
    owners: list[str] = []
    for row in rows:
        if row["owner"] not in owners:
            owners.append(row["owner"])
    totals = {(r["stage"], r["owner"]): r["total"] for r in rows}
    return [
        Series(
            name=owner,
            data=[
                (STAGE_LABEL[stage], totals.get((stage, owner), 0) or 0)
                for stage in OPEN_STAGES
            ],
        )
        for owner in owners
    ]


def chart_card(title: str, subtitle: str, render, *args) -> None:
    with ui.card(padding="md"):
        with ui.vstack(gap="sm"):
            ui.heading(title, level=2, size="md")
            ui.text(subtitle, color="muted", size="xs")
            render(*args)


def pipeline_chart(series: list[Series]) -> None:
    ui.bar_chart(
        data=series,
        variant="grouped",
        orientation="horizontal",
        y_format="abbreviated",
        y_unit="€",
        size="md",
        empty_text="Aucune affaire ouverte.",
    )


def month_axis(moment) -> str:
    """L'axe temporel en français.

    Toujours nécessaire, et pour une raison qui ne bougera pas : l'axe
    d'un graphique est cuit dans le SVG **côté serveur**, donc hors de
    portée de l'``Intl`` du navigateur dont vivent les composants de
    date. Python ne sait pas nommer un mois sans dépendance — son module
    ``locale`` est un état global au processus. ``x_format=`` est donc la
    prise, et c'est bien ainsi.

    Ce qui a changé le 2026-08-24 : le paramètre arrive en ``datetime``,
    plus en timestamp POSIX. Cette fonction commençait par le reconvertir
    à la main, ce que fait maintenant le composant, qui SAIT que c'est
    une date.
    """
    return f"{MONTHS_FR_SHORT[moment.month - 1]} {moment.year}"


def activity_chart() -> None:
    rows = activities_by_month(visible_owner())
    ui.line_chart(
        data=[(date.fromisoformat(r["jour"]), r["n"]) for r in rows],
        area_fill=True,
        show_dots=True,
        x_format=month_axis,
        size="md",
        empty_text="Aucune activité sur la période.",
    )


def industry_chart() -> None:
    rows = accounts_by_industry(visible_owner())
    ui.pie_chart(
        data=[(r["industry"], r["n"]) for r in rows],
        variant="donut",
        center_text=f"{sum(r['n'] for r in rows)} comptes",
        size="md",
        empty_text="Aucun compte.",
    )


def correlation_chart() -> None:
    rows = arr_versus_contacts(visible_owner())
    ui.scatter_chart(
        data=[(r["contacts"], r["arr"]) for r in rows],
        x_unit=" contacts",
        y_format="abbreviated",
        y_unit="€",
        size="md",
        empty_text="Aucun compte dans l'échantillon.",
    )


def trend_card() -> None:
    weeks = weekly_activity(visible_owner())
    with ui.card(padding="md"):
        with ui.hstack(gap="md", align="center", justify="between"):
            with ui.vstack(gap="none"):
                ui.text("Activité, 12 dernières semaines", color="muted",
                        size="xs")
                ui.heading(str(sum(weeks)), level=3, size="lg")
            ui.sparkline(data=weeks, area_fill=True, show_last_dot=True,
                         size="md", color="primary")


def pipeline_total_card(series: list[Series]) -> None:
    total = sum(value for s in series for _label, value in s.data)
    with ui.card(padding="md"):
        with ui.hstack(gap="md", align="center"):
            with ui.flex(align="center", justify="center",
                         classes="w-10 h-10 rounded-lg bg-text/5 shrink-0"):
                ui.icon("trending-up", color="success")
            with ui.vstack(gap="none"):
                # ⚠️ Le libellé suit le CADRAGE. Cadré, il n'y a qu'un
                # porteur — annoncer « 3 premiers » serait un chiffre faux
                # à l'écran, la forme de mensonge qu'on ne relit jamais.
                ui.text("Pipeline ouvert, mon portefeuille"
                        if visible_owner() is not None
                        else "Pipeline ouvert, 3 premiers porteurs",
                        color="muted", size="xs")
                ui.heading(euros(total), level=3, size="lg")


@page("/rapports", layout=analyse_nav, title="Rapports")
def reports_page() -> None:
    # UNE seule fois : la carte de tête et le graphique lisaient le même
    # agrégat chacun de son côté, soit deux ``GROUP BY`` de trop sur la page
    # dont le sujet EST de tenir sur de vrais agrégats.
    series = pipeline_series()
    with ui.vstack(gap="lg"):
        ui.heading("Rapports", level=1, size="2xl")
        with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
            trend_card()
            pipeline_total_card(series)
        with ui.grid(cols={"base": 1, "xl": 2}, gap="lg"):
            chart_card(
                "Pipeline par étape",
                ("Montant ouvert — SUM(amount) GROUP BY stage"
                 if visible_owner() is not None else
                 "Montant ouvert, groupé par propriétaire — SUM(amount) "
                 "GROUP BY stage, owner"),
                pipeline_chart, series,
            )
            chart_card(
                "Activité par mois",
                "Douze mois glissants — COUNT(*) GROUP BY substr(at, 1, 7)",
                activity_chart,
            )
            chart_card(
                "Comptes par secteur",
                "Les huit premiers — COUNT(*) GROUP BY industry",
                industry_chart,
            )
            chart_card(
                "ARR contre nombre de contacts",
                "Échantillon de 250 comptes — LEFT JOIN + GROUP BY a.id",
                correlation_chart,
            )


feature = Feature(
    name="reports",
    kind="page",
    provides=[reports_page],
    uses=["reports_data", "access"],
)
