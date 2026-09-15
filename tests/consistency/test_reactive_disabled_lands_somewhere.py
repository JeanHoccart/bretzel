"""Gate — un ``disabled`` bindable atterrit sur quelque chose qui rend inerte.

27 composants publics acceptent une binding sur ``disabled``. Elle n'a que
**deux** destinations utiles :

1. un support **nativement désactivable** (``<button>``, ``<input>``,
   ``<select>``, ``<textarea>``, ``<fieldset>``) — le navigateur fait tout ;
2. n'importe quel élément, via ``bz-attr:aria-disabled`` — le thème
   l'habille par ses variantes ``aria-disabled:``, un lecteur d'écran
   l'annonce, et le socle runtime en dérive l'inertie (``$bz._inert``,
   ``02_directives.js`` + ``05_bridge.js``).

Toute autre destination ne fait **rien**, en silence. C'est le bug trouvé
le 2026-08-13 : ``MenuItem`` posait ``bz-attr:disabled`` sur un ``<a>`` —
attribut qui n'existe pas sur une ancre — donc
``ui.dropdown_item(disabled=<binding>)`` gardait son ``href``, son
``bz-on:click`` et son apparence d'entrée active. Le chemin STATIQUE du
même composant était, lui, irréprochable ; c'est ce qui l'a rendu
invisible à la relecture comme aux 12 000 tests.

⚠️ **La gate rend le composant et regarde où l'attribut ATTERRIT**, elle
ne lit pas une déclaration. C'est délibéré : la version déclarative de
cette question (« ``disabled`` est-il dans ``BINDABLE_PROPS`` ? ») répond
oui pour les 27, y compris les cassés.
"""

from __future__ import annotations

import functools
from html.parser import HTMLParser

import pytest

from bretzel import ui
from bretzel.state import field
from bretzel.components.base.component import Component
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientState, rendering_scope

#: Preuve de morsure : contrôle POSITIF — la découverte trouve encore les composants à
#: ``disabled`` bindable.
MUTATION_PROOF = "test_the_sweep_population_is_not_empty"

#: Les supports que le navigateur rend inertes tout seul.
_NATIVE_HOSTS = frozenset(
    {"button", "input", "select", "textarea", "fieldset", "option"}
)


class _Flags(ClientState):
    off: bool = field(default=False)


#: Comment construire un cas rendable. Un composant absent d'ici n'est pas
#: exempté : il fait rougir :func:`test_every_bindable_disabled_is_covered`.
_BUILD: dict[str, dict] = {
    "button": dict(label="X"),
    "icon_button": dict(icon="x"),
    "dropdown_item": dict(label="X", href="/y"),
    "sidebar_footer_item": dict(label="X", href="/y"),
    "navbar_item": dict(label="X", href="/y"),
    "sidebar_item": dict(label="X", href="/y"),
    "bottom_bar_item": dict(label="X", href="/y"),
    "checkbox": {},
    "switch": {},
    "input": {},
    "textarea": {},
    "radio": dict(value="a"),
    "select": dict(options=["a"]),
    "combobox": dict(options=["a"]),
    "slider": {},
    "number_input": {},
    "file_upload": {},
    "pagination": dict(total_pages=3),
    "calendar": {},
    "date_picker": {},
    "time_picker": {},
    "color_picker": {},
    "month_picker": {},
    "week_picker": {},
    "date_range_picker": {},
    # ``options=`` n'existe PAS sur RadioGroup (ses radios sont des
    # enfants) — le kwarg partait dans le catch-all et ne faisait rien.
    # Retiré le 2026-08-16, quand la fermeture du seau 5 l'a révélé.
    "radio_group": dict(),
}

#: Composants qui ne rendent aucun contrôle propre — leur ``disabled`` se
#: propage à des enfants qui, eux, sont couverts.
_DELEGATES: dict[str, str] = {
    "toggle_group": "délègue à ses ``toggle_button``",
    "toggle_button": "ne se rend pas hors d'un ``toggle_group``",
    "form": "propage à ses champs",
    "tree_node": "rendu par ``tree``, pas constructible seul",
}

class _Carriers(HTMLParser):
    """Où atterrit le câblage réactif. Un parseur et pas une regex : les
    expressions JS émises contiennent des ``>``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hits: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        for name, _ in attrs:
            if name in ("bz-attr:disabled", "bz-attr:aria-disabled"):
                self.hits.append((tag, name))


@functools.cache
def _carriers(name: str) -> tuple[tuple[str, str], ...]:
    with render_isolated(), rendering_scope():
        if name == "radio_group":
            with ui.radio_group(disabled=_Flags().off) as component:
                ui.radio("a", label="A")
        else:
            component = getattr(ui, name)(disabled=_Flags().off, **_BUILD[name])
        out = serialize(component.render())
    parser = _Carriers()
    parser.feed(out)
    return tuple(parser.hits)


def _bindable_disabled() -> list[str]:
    return sorted(
        name for name in dir(ui)
        if not name.startswith("_")
        and isinstance(getattr(ui, name, None), type)
        and issubclass(getattr(ui, name), Component)
        and "disabled" in (getattr(getattr(ui, name), "BINDABLE_PROPS", ()) or ())
    )


def test_the_sweep_population_is_not_empty() -> None:
    """Plancher de non-vacuité — sur la DÉCOUVERTE, pas sur la population
    de contrevenants (qui doit pouvoir tomber à zéro sans rien casser)."""
    found = _bindable_disabled()
    assert len(found) >= 20, (
        f"seulement {len(found)} composants à ``disabled`` bindable "
        f"(27 mesurés le 2026-08-13) — la découverte a cassé, et cette "
        f"gate affirmerait « aucun câblage mort » sans rien avoir lu."
    )


def test_every_bindable_disabled_is_covered() -> None:
    """Complétude : la table est écrite à la main, donc elle a l'angle
    mort de toutes les tables écrites à la main — c'est comme ça que
    ``draggable`` avait échappé à ``test_disabled_affordance``."""
    known = set(_BUILD) | set(_DELEGATES)
    missing = sorted(set(_bindable_disabled()) - known)
    assert not missing, (
        f"{missing} acceptent un ``disabled`` bindable et ne sont ni dans "
        f"``_BUILD`` (donc jamais rendus par cette gate), ni déclarés dans "
        f"``_DELEGATES`` avec leur raison."
    )


@pytest.mark.parametrize("name", sorted(_BUILD))
def test_reactive_disabled_lands_on_an_inert_host(name: str) -> None:
    if "disabled" not in (getattr(getattr(ui, name), "BINDABLE_PROPS", ()) or ()):
        pytest.skip(f"{name} n'expose plus ``disabled`` en bindable")
    hits = _carriers(name)
    assert hits, (
        f"{name} : une binding sur ``disabled`` n'émet AUCUN câblage "
        f"réactif. Le contrôle restera actif quand elle passera à vrai."
    )
    usable = [
        (tag, attr) for tag, attr in hits
        if attr == "bz-attr:aria-disabled" or tag in _NATIVE_HOSTS
    ]
    assert usable, (
        f"{name} : le câblage réactif atterrit sur {list(hits)}, où il ne "
        f"rend rien inerte.\n"
        f"  ``disabled`` n'est un attribut QUE sur "
        f"{sorted(_NATIVE_HOSTS)} ; ailleurs il est ignoré en silence — "
        f"c'est le bug de ``dropdown_item`` (un ``<a>`` qui restait "
        f"cliquable en paraissant désactivé).\n"
        f"  Émets ``bz-attr:aria-disabled`` : le thème l'habille, l'a11y "
        f"l'annonce, et le socle en dérive l'inertie."
    )
