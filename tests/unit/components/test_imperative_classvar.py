"""Guard: every name in a component's ``IMPERATIVE`` ClassVar must resolve
to a real callable on a constructed instance.

``IMPERATIVE`` is the single introspectable source of truth for the
write-only imperative API (read by the docs ui.* catalogue). The methods
are either plain class methods (``def set`` on inputs) or assigned
per-instance in ``__init__`` (the non-data-descriptor trick on overlays /
Accordion, where the name would shadow a reactive_prop like ``open``).
This test constructs each declaring component and asserts the contract
holds — so a rename that forgets to update ``IMPERATIVE`` fails loudly
instead of silently rotting the catalogue.
"""

from __future__ import annotations

import pytest

from bretzel.components import ui
from bretzel.components.base.component import Component
from bretzel.components.base.testing import render_isolated


def _ui_component_classes() -> dict[type, str]:
    """{Component subclass: first ui.* alias} for every shipped component."""
    seen: dict[type, str] = {}
    for name in vars(type(ui)):
        if name.startswith("_"):
            continue
        val = getattr(ui, name)
        if isinstance(val, type) and issubclass(val, Component):
            seen.setdefault(val, name)
    return seen


_WITH_IMPERATIVE = [
    (ui_name, cls)
    for cls, ui_name in _ui_component_classes().items()
    if cls.IMPERATIVE
]


def test_base_default_is_empty() -> None:
    """A component opts in explicitly ; the default is no imperative API."""
    assert Component.IMPERATIVE == ()


def test_some_components_declare_imperative() -> None:
    """Sanity floor : the overlays + inputs family ship the API, so an
    empty list here means the ClassVars got wiped, not that nothing has it."""
    assert len(_WITH_IMPERATIVE) >= 15


@pytest.mark.parametrize(
    "ui_name,cls",
    _WITH_IMPERATIVE,
    ids=[n for n, _ in _WITH_IMPERATIVE],
)
def test_imperative_names_are_callable(ui_name: str, cls: type) -> None:
    with render_isolated():
        instance = cls()
        for method in cls.IMPERATIVE:
            attr = getattr(instance, method, None)
            assert callable(attr), (
                f"{cls.__name__}.IMPERATIVE lists {method!r}, but it is not "
                f"a callable on a constructed instance — the ClassVar drifted "
                f"from the real methods."
            )


@pytest.mark.parametrize(
    "ui_name,cls",
    _WITH_IMPERATIVE,
    ids=[n for n, _ in _WITH_IMPERATIVE],
)
def test_imperative_component_needs_identity(ui_name: str, cls: type) -> None:
    """Un composant à API impérative DOIT rendre son ``id``.

    ``.open()`` / ``.set()`` / … visent leur cible par
    ``getElementById(self.id)`` ; sans id rendu le dispatch trouve
    ``null`` et échoue **en silence** (aucune erreur console) — le piège
    exact de traps.md § « API imperative sans id ». Auparavant chaque
    composant re-tapait ``def _needs_identity: return True`` (17 copies) ;
    c'est désormais DÉRIVÉ de ``IMPERATIVE`` dans la base (component.py).
    Cette gate fige l'invariant : peu importe qu'il soit dérivé ou
    overridé, un composant impératif rend un id.
    """
    with render_isolated():
        instance = cls()
        assert instance._needs_identity(), (
            f"{cls.__name__} expose l'API impérative ({cls.IMPERATIVE}) mais "
            f"`_needs_identity()` retourne False → son id ne sera pas rendu, "
            f"et `.{cls.IMPERATIVE[0]}()` dispatchera dans le vide (silencieux)."
        )
