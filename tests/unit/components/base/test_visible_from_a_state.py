"""``visible=`` lu dans un état serveur masque quand il vaut ``False``.

Vu sur la page d'un élève : ``visible=Saved().notes``,
un champ booléen d'un ``PageState`` à ``False``, laissait « Enregistré »
affiché avant tout mot tapé. Pendant le rendu, la lecture d'un champ rend
une valeur estampillée — ``_BoundBool``, un ``int`` qui porte son nom de
champ, ``bool`` ne se dérivant pas — et le modificateur testait
``visible is False`` : l'identité ratait le ``0`` estampillé. Il lit
désormais la valeur d'un booléen estampillé.

Les deux bras : un ``True`` estampillé montre, et le ``False`` littéral
masque toujours.
"""

from __future__ import annotations

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state.scopes.server import _BoundBool


def html(visible) -> str:
    with render_isolated():
        return serialize(ui.text("Enregistré", visible=visible).render())


def test_a_stamped_false_hides() -> None:
    assert "Enregistré" not in html(_BoundBool(False, "notes"))


def test_a_stamped_true_shows() -> None:
    assert "Enregistré" in html(_BoundBool(True, "notes"))


def test_a_literal_false_still_hides() -> None:
    assert "Enregistré" not in html(False)
