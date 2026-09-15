"""Gate : un override utilisateur (``Theme(components={…})``) FUSIONNE
avec le thème livré du composant — il ne le remplace pas.

Bug d'origine (audit 2026-07-15) : ``Component._resolved_theme``
retournait l'override utilisateur WHOLESALE. L'exemple enseigné par la
doc (``components={"button": {"slots": {"root": "rounded-2xl"}}}``)
faisait passer un Button de 25 classes à 1 : plus de variant
(``bg-primary``), plus de size (``h-*``), plus de focus ring.
``merge_component_themes`` (theme/slots.py) existait, documentait
exactement ce cas dans son docstring, et n'était jamais appelé sur ce
chemin. Cf. traps.md § « Theme(components=…) écrasait le thème livré ».

Contrat verrouillé ici :

- **niveau dict** : merge clé-par-clé — variants, sizes, modifiers et
  slots frères survivent à l'override d'un seul slot ;
- **feuille string** : l'override REDÉFINIT cette entrée (chaîne
  complète) — c'est le contrat de ``merge_component_themes``, distinct
  du ``slots=`` par-instance qui AJOUTE (``compose_class`` étape 6).
"""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components import Button
from bretzel.components.base.testing import render_isolated
from bretzel.theme import Theme, merge_component_themes
from tests.consistency._discovery import public_component_classes

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "fusionne deux thèmes et lit le résultat : le comportement est "
    "exécuté, il n'y a aucun motif à reconnaître"
)


def test_resolved_theme_merges_not_replaces() -> None:
    override = Theme(components={"button": {"slots": {"root": "bz-audit-marker"}}})
    with render_isolated(theme=override):
        merged = ui.button("x")._resolved_theme()

    # Le slot visé est redéfini…
    assert merged["slots"]["root"] == "bz-audit-marker"
    # …et RIEN d'autre ne bouge : mêmes étages, mêmes variants/sizes,
    # mêmes slots frères.
    assert set(merged) == set(Button.THEME)
    for key, val in Button.THEME.items():
        if key == "slots":
            for slot, template in val.items():
                if slot != "root":
                    assert merged["slots"][slot] == template, (
                        f"slot frère {slot!r} perdu/modifié par l'override de root"
                    )
        else:
            assert merged[key] == val, f"étage {key!r} perdu par l'override d'un slot"


def test_doc_example_no_longer_nukes_the_button() -> None:
    """L'exemple historique de la doc rendait un bouton à 1 classe."""
    override = Theme(components={"button": {"slots": {"root": "rounded-2xl"}}})
    with render_isolated(theme=override):
        cls = ui.button("x", color="primary", size="lg").render().attrs["class"]

    parts = cls.split()
    assert "rounded-2xl" in parts
    assert any(p.startswith("bg-") for p in parts), f"variant perdu : {cls!r}"
    assert any(p.startswith("h-") for p in parts), f"size perdue : {cls!r}"
    assert len(parts) >= 8, f"l'override d'un slot a mangé le thème : {cls!r}"


def test_no_override_still_returns_shipped_theme_identity() -> None:
    """Sans override, pas de merge : le dict livré revient tel quel
    (pas de copie par render — le chemin chaud reste gratuit)."""
    with render_isolated():
        assert ui.button("x")._resolved_theme() is Button.THEME


@pytest.mark.parametrize(
    "cls",
    [c for c in public_component_classes() if getattr(c, "THEME", None)],
    ids=lambda c: c.__name__,
)
def test_partial_override_preserves_every_other_entry(cls: type) -> None:
    """Invariant structurel sur TOUS les thèmes livrés : un override qui
    n'ajoute qu'une clé étrangère ne perturbe aucune entrée existante —
    aucune forme de table (plate, ``sizes[size][slot]``, inversée) ne
    casse sous le merge."""
    merged = merge_component_themes(cls.THEME, {"slots": {"__bz_probe__": "x"}})
    assert set(merged) >= set(cls.THEME)
    for key, val in cls.THEME.items():
        if key == "slots":
            for slot, template in val.items():
                assert merged["slots"][slot] == template
        else:
            assert merged[key] == val
