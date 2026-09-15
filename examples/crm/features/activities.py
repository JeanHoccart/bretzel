"""features/activities — écran 6 : le journal, et les pickers EN FILTRE.

Ce que cet écran met sous contrainte : ``ui.date_range_picker``,
``ui.calendar`` et ``ui.date_picker`` **dans une vraie barre de filtres et
dans un vrai formulaire**, pas montés seuls sur un banc. Le playground les
rend tous les trois — mais aucun n'y est lié à un état serveur, donc le
chemin « je choisis une période, le serveur relit la base » n'avait jamais
été parcouru.

Trois usages distincts, pris au mot :

- la **période** est un ``date_range_picker`` : deux bornes, un seul geste ;
- le **jour** est un ``ui.calendar`` : on le survole du regard avant de
  cliquer, ce qu'un champ ne permet pas ;
- la **date d'une activité qu'on journalise** est un ``date_picker`` : un
  champ dans un formulaire, entre deux autres champs.
"""

from __future__ import annotations

from datetime import timedelta

from bretzel import Feature, page, refreshable, ui
from bretzel.state import PageState, field, validator
from examples.crm.core.domain import (
    ACTIVITY_KEYS,
    ACTIVITY_KINDS,
    MONTHS_FR,
    OWNERS,
    TODAY,
    WEEKDAYS_FR,
    activity_badge,
)
from examples.crm.core.ui import kpi
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.activities_data import (
    ActivitiesRev,
    activities_between,
    activity_counts,
    add_activity,
    busiest_days,
)
from examples.crm.features.shell import shell

#: La fenêtre par défaut : le mois écoulé. Calculée depuis ``TODAY``, la date
#: figée du jeu de données — pas depuis l'horloge, sinon la page serait vide
#: le jour où on relit ce dépôt.
DEFAULT_END = TODAY
DEFAULT_START = TODAY - timedelta(days=30)


def parse_range(raw) -> tuple[str, str]:
    """Les deux bornes de la période, remises dans l'ordre.

    Le décodage JSON n'est plus ici : le socle le fait au bord du champ.
    Ce qui reste est du métier — une période dont la fin précède le début
    est une saisie, pas une erreur, et on la retourne plutôt que de la
    refuser.
    """
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return DEFAULT_START.isoformat(), DEFAULT_END.isoformat()
    start, end = raw
    if not start or not end:
        return DEFAULT_START.isoformat(), DEFAULT_END.isoformat()
    return (start, end) if start <= end else (end, start)


class ActivitiesUI(PageState):
    """La fenêtre regardée : période, jour choisi, type.

    **Plus de propriétaire** : le portefeuille est un cadrage, pas un
    filtre d'écran — cf. ``access.visible_owner``.
    """

    #: Une LISTE, et son défaut s'écrit en clair. Le composant sérialise
    #: ses deux bornes en JSON dans un champ caché, et le socle le décode
    #: à l'arrivée (``_coerce_composite``) — c'était le finding 10 du
    #: chantier, levé par la réparation du 19 : les deux étaient le même
    #: trou, vu depuis deux composants.
    periode: list = field(
        default_factory=lambda: [DEFAULT_START.isoformat(),
                                 DEFAULT_END.isoformat()]
    )
    jour: str = field(default='')
    kind: str = field(default='all')
    #: Le mois AFFICHÉ par l'agenda.
    #:
    #: Un vrai champ, et **pas** `jour or fin_de_periode` au point d'appel.
    #: `a or b` rend l'opérande TELLE QUELLE : l'estampille de provenance
    #: survivait donc quand `jour` était rempli et disparaissait quand il
    #: était vide, et le calendrier se resynchronisait une fois sur deux
    #: selon la donnée. Conséquence visible : sans jour choisi, changer la
    #: période ne déplaçait pas le calendrier.
    #:
    #: C'est le même piège que celui déjà écrit dans `save_activity`, où
    #: un `or` défaisait le verrou de portefeuille. Gardé par la règle
    #: `etat-perdu-par-un-cast`, élargie aux `BoolOp` le 2026-08-30.
    mois: str = field(default=DEFAULT_END.isoformat())

    @validator("kind")
    def _kind(cls, value: str) -> str:
        return value if value in ACTIVITY_KEYS else "all"


class ActivityDraft(PageState):
    """Le formulaire de journalisation."""

    contact_id: int = field(default=0)
    kind: str = field(default='call')
    subject: str = field(default='')
    at: str = field(default=TODAY.isoformat())
    owner: str = field(default=OWNERS[0])

    @validator("kind")
    def _kind(cls, value: str) -> str:
        return value if value in ACTIVITY_KEYS else "call"


def filter_changed(state: ActivitiesUI) -> None:
    """La période ou le type a bougé ; ``deps=`` re-render la zone.

    Le mois affiché SUIT la période : sans ça, on déplace la fenêtre et
    l'agenda reste sur l'ancien mois.
    """
    state.mois = parse_range(list(state.periode))[1]


def pick_day(state: ActivitiesUI) -> None:
    """Un clic dans l'agenda : le jour choisi devient la fenêtre."""
    if state.jour:
        state.mois = str(state.jour)


def clear_day() -> None:
    """Retour à la période entière — le mois repart de sa fin."""
    state = ActivitiesUI()
    state.jour = ""
    state.mois = parse_range(list(state.periode))[1]


def save_activity(form: ActivityDraft) -> None:
    subject = str(form.subject).strip()[:120]
    if not subject or not form.contact_id:
        ui.notification("Un sujet et un identifiant de contact sont requis.",
                        variant="warning", duration_ms=2500)
        return
    # Le cadrage ÉCRASE le champ : il arrive du navigateur, donc un
    # commercial pourrait le forger pour journaliser au nom d'un collègue.
    # Le champ n'est lu que là où il n'y a pas de cadrage — la direction.
    #
    # ⚠️ Le test est `is None`, pas un `or`. Une première écriture disait
    # `effective_owner(...) or str(form.owner)` : pour un anonyme le
    # cadrage vaut `NOBODY` (`""`), qui est FAUX, donc le `or` rendait la
    # valeur du navigateur — le verrou défait par sa propre écriture.
    scope = visible_owner()
    stamped = str(form.owner) if scope is None else scope
    if stamped not in OWNERS:
        ui.notification("Propriétaire inconnu.", variant="error",
                        duration_ms=3000)
        return
    created = add_activity(int(form.contact_id), str(form.kind), subject,
                           str(form.at), stamped, scope)
    if not created:
        ui.notification(f"Aucun contact n'a l'identifiant {form.contact_id}.",
                        variant="error", duration_ms=3000)
        return
    form.subject = ""
    ui.notification("Activité journalisée", variant="success",
                    duration_ms=2000)


def window_of(state: ActivitiesUI) -> tuple[str, str]:
    """La fenêtre effective : le jour choisi l'emporte sur la période."""
    if state.jour:
        return str(state.jour), str(state.jour)
    return parse_range(list(state.periode))


# ``ViewerPrefs`` dans les ``deps`` : sans lui, changer de portefeuille
# dans la barre latérale laisserait la zone sur la donnée de l'ancien.
@refreshable(deps=[ActivitiesUI, ActivitiesRev, ViewerPrefs])
def counters() -> None:
    state = ActivitiesUI()
    start, end = window_of(state)
    counts = activity_counts(start, end, str(state.kind), visible_owner())
    with ui.grid(cols={"base": 2, "md": 5}, gap="md"):
        for key, (label, icon, color) in ACTIVITY_KINDS.items():
            kpi(label, str(counts.get(key, 0)), icon, color)


@refreshable(deps=[ActivitiesUI, ActivitiesRev, ViewerPrefs])
def agenda() -> None:
    """L'agenda + le palmarès des journées chargées.

    ⚠️ Les deux vont ensemble par défaut du composant : ``ui.calendar`` ne
    sait pas MARQUER un jour (ni prop d'événements, ni slot de cellule), donc
    il ne peut pas montrer où il se passe quelque chose. Le tableau à côté
    dit ce que l'agenda devrait porter.
    """
    state = ActivitiesUI()
    start, end = window_of(state)
    with ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center"):
            ui.heading("Agenda", level=2, size="md")
            if state.jour:
                ui.button("Toute la période", size="xs", variant="ghost",
                          icon_left="x", on_click=clear_day)
        ui.calendar(value=state.jour, month=state.mois,
                    weekstart=1, size="sm", month_names=MONTHS_FR,
                    weekday_names=WEEKDAYS_FR, on_change=pick_day)
        ui.divider(label="Journées chargées")
        days = busiest_days(start, end, str(state.kind), visible_owner())
        if not days:
            ui.text("Rien sur cette fenêtre.", color="muted", size="sm")
        for day in ui.each(days, key="jour"):
            with ui.hstack(justify="between", align="center"):
                ui.text(day["jour"], size="sm")
                ui.badge(str(day["n"]), variant="soft", color="muted",
                         size="xs")


@refreshable(deps=[ActivitiesUI, ActivitiesRev, ViewerPrefs])
def journal() -> None:
    state = ActivitiesUI()
    start, end = window_of(state)
    rows = activities_between(start, end, str(state.kind),
                              visible_owner())
    with ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="center"):
            ui.heading("Journal", level=2, size="md")
            ui.text(f"{start} → {end}", color="muted", size="xs")
        if not rows:
            ui.empty_state("Aucune activité", icon="calendar-x",
                           description="Élargis la période ou change de type.")
        for row in ui.each(rows, key="id"):
            _label, icon, color = activity_badge(row["kind"])
            with ui.card(padding="sm"):
                with ui.hstack(gap="sm", align="center"):
                    ui.icon(icon, color=color, size="sm")
                    with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                        ui.text(row["subject"], size="sm", weight="medium",
                                truncate=True)
                        ui.link(
                            f"{row['first_name']} {row['last_name']} · "
                            f"{row['account_name']}",
                            href=f"/contacts/{row['contact_id']}",
                            variant="hover", color="muted",
                        )
                    with ui.vstack(gap="none", align="end"):
                        ui.text(row["at"], color="muted", size="xs")
                        ui.text(row["owner"], color="muted", size="xs")


def filter_bar() -> None:
    state = ActivitiesUI()
    start, end = parse_range(list(state.periode))
    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
        with ui.form_field(label="Période",
                           hint="La borne du jour choisi dans l'agenda "
                                "l'emporte sur celle-ci."):
            ui.date_range_picker(value=state.periode,
                                 month_names=MONTHS_FR,
                                 weekday_names=WEEKDAYS_FR,
                                 placeholder_start=start, placeholder_end=end,
                                 on_change=filter_changed)
        with ui.form_field(label="Type"):
            ui.select(
                value=state.kind,
                options=[("all", "Tous les types"),
                         *[(k, lbl) for k, (lbl, _i, _c)
                           in ACTIVITY_KINDS.items()]],
                on_change=filter_changed,
            )



@refreshable(deps=[ActivityDraft, ViewerPrefs])
def log_form() -> None:
    draft = ActivityDraft()
    with ui.form(on_submit=save_activity):
        with ui.vstack(gap="md"):
            ui.heading("Journaliser une activité", level=2, size="md")
            with ui.grid(cols={"base": 1, "md": 5}, gap="md"):
                with ui.form_field(label="Contact (id)", required=True):
                    ui.number_input(value=draft.contact_id, min=1,
                                    max=120_000)
                with ui.form_field(label="Type"):
                    ui.select(value=draft.kind,
                              options=[(k, lbl) for k, (lbl, _i, _c)
                                       in ACTIVITY_KINDS.items()])
                with ui.form_field(label="Sujet", required=True):
                    ui.input(value=draft.subject, maxlength=120,
                             placeholder="Point d'avancement")
                with ui.form_field(label="Date"):
                    ui.date_picker(value=draft.at, clearable=False,
                                   month_names=MONTHS_FR,
                                   weekday_names=WEEKDAYS_FR)
                if visible_owner() is None:
                    # La direction DOIT dire pour qui elle journalise ;
                    # un commercial n'a pas ce choix à faire.
                    with ui.form_field(label="Propriétaire"):
                        ui.select(value=draft.owner,
                                  options=[(o, o) for o in OWNERS])
            with ui.hstack(justify="end"):
                ui.button("Journaliser", type="submit", color="primary",
                          icon_left="plus")


@page("/activites", layout=shell, title="Activités")
def activities_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Activités", level=1, size="2xl")
        filter_bar()
        counters()
        with ui.card(padding="md"):
            log_form()
        # Deux colonnes ÉGALES, pas un tiers / deux tiers : ``ui.grid``
        # n'expose que ``cols`` et ``gap``, donc aucun de ses enfants ne peut
        # occuper deux colonnes. La seule façon d'obtenir « un tiers / deux tiers » serait un
        # ``classes="lg:col-span-2"``, que ce chantier interdit de poser.
        with ui.grid(cols={"base": 1, "lg": 2}, gap="lg"):
            with ui.card(padding="md"):
                agenda()
            journal()


feature = Feature(
    name="activities",
    kind="page",
    provides=[activities_page, ActivitiesUI, ActivityDraft],
    uses=["activities_data", "access"],
)
