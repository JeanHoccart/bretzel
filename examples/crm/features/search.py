"""features/search — écran 8 : la recherche globale.

Ce que cet écran met sous contrainte : le cas d'usage qui déciderait
``ui.command_palette``. Il est construit ici avec ce qui existe — un
``ui.input`` débouncé, trois listes groupées, et une navigation au clic —
pour que la question « qu'est-ce qui manque ? » ait une réponse mesurée
plutôt qu'une intuition.

Ce qu'une palette apporterait et que cette page n'a pas, constaté en la
construisant :

1. **elle s'ouvre par-dessus, depuis n'importe où** ; ici il faut naviguer
   vers ``/recherche``, donc quitter ce qu'on regardait — l'inverse du geste ;
2. **elle se pilote au clavier de bout en bout** (↑↓ à travers des groupes
   hétérogènes, Entrée pour ouvrir, Échap pour fermer). ``ui.combobox`` sait
   le faire, mais sur UNE liste d'options homogènes qui écrit une valeur ;
   ici chaque résultat mène à une URL différente et rien n'est sélectionné ;
3. **elle a un raccourci** (Ctrl+K) — aucun composant du catalogue n'écoute
   une combinaison globale.

Aucun de ces trois manques n'est rattrapé ici : la page reste une page.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.state import PageState, field
from examples.crm.core.domain import (
    STAGE_COLOR,
    STAGE_LABEL,
    euros,
    initials,
    status_badge,
)
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.search_data import PER_KIND, search_everywhere
from examples.crm.features.shell import shell


class SearchUI(PageState):
    needle: str = field(default='')


def search_changed(state: SearchUI) -> None:
    """La frappe hydrate ``needle`` ; ``deps=`` re-render les résultats."""


def result_row(icon: str, color: str, title: str, subtitle: str, href: str,
               trailing: str) -> None:
    with ui.card(padding="sm", hoverable=True, href=href):
        with ui.hstack(gap="sm", align="center"):
            ui.icon(icon, color=color, size="sm")
            with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                ui.text(title, size="sm", weight="medium", truncate=True)
                ui.text(subtitle, color="muted", size="xs", truncate=True)
            ui.text(trailing, color="muted", size="xs")


def result_group(title: str, icon: str, rows: list, render) -> None:
    with ui.vstack(gap="sm"):
        with ui.hstack(gap="sm", align="center"):
            ui.icon(icon, color="muted", size="sm")
            ui.heading(title, level=2, size="sm")
            ui.badge(f"{len(rows)}" + ("+" if len(rows) == PER_KIND else ""),
                     variant="soft", color="muted", size="xs")
        if not rows:
            ui.text("Rien ici.", color="muted", size="sm")
        for row in ui.each(rows, key="id"):
            render(row)


def account_result(row: dict) -> None:
    result_row("building-2", "primary", row["name"],
               f"{row['industry']} · {row['city']}",
               f"/comptes/{row['id']}", euros(row["arr"]))


def contact_result(row: dict) -> None:
    label, _color = status_badge(row["status"])
    result_row(
        "user", "info",
        f"{row['first_name']} {row['last_name']} "
        f"({initials(row['first_name'], row['last_name'])})",
        f"{row['email']} · {row['account_name']}",
        f"/contacts/{row['id']}", label,
    )


def deal_result(row: dict) -> None:
    result_row("folder-open", STAGE_COLOR.get(row["stage"], "muted"),
               f"{row['account_name']} — {row['name']}",
               f"{STAGE_LABEL.get(row['stage'], row['stage'])} · "
               f"échéance {row['close_date']}",
               f"/comptes/{row['account_id']}", euros(row["amount"]))


@refreshable(deps=[SearchUI, ViewerPrefs])
def results() -> None:
    state = SearchUI()
    needle = str(state.needle).strip()
    if len(needle) < 2:
        ui.empty_state(
            "Cherche un compte, un contact ou une affaire",
            icon="search",
            description="Deux caractères suffisent. La recherche porte sur "
                        "le DÉBUT du nom — c'est ce qu'un index sait faire "
                        "sans scanner 170 000 lignes à chaque frappe.",
        )
        return
    found = search_everywhere(needle, visible_owner())
    total = sum(len(v) for v in found.values())
    if not total:
        ui.empty_state(f"Rien ne commence par « {needle} »", icon="search-x",
                       description="Essaie les premières lettres du nom du "
                                   "compte, du nom de famille ou de l'email.")
        return
    with ui.grid(cols={"base": 1, "lg": 3}, gap="lg"):
        result_group("Comptes", "building-2", found["comptes"],
                     account_result)
        result_group("Contacts", "users", found["contacts"], contact_result)
        result_group("Affaires", "folder-open", found["affaires"],
                     deal_result)


@page("/recherche", layout=shell, title="Recherche")
def search_page() -> None:
    state = SearchUI()
    with ui.vstack(gap="lg"):
        ui.heading("Recherche", level=1, size="2xl")
        # ``on_input`` et non ``on_change`` : une recherche globale se lit
        # pendant la frappe. ``on_change`` est l'événement natif — il
        # n'arrive qu'au blur ou à Entrée, et le ``debounce`` n'y aurait
        # rien à temporiser.
        ui.input(value=state.needle, icon_left="search", clearable=True,
                 placeholder="Compte, nom de famille, email…",
                 on_input=search_changed, debounce=250)
        results()


feature = Feature(
    name="search",
    kind="page",
    provides=[search_page, SearchUI],
    uses=["search_data", "access"],
)
