"""Une valeur estampillée se copie en sa valeur simple.

Pendant le rendu, un champ
d'état se lit estampillé (``_BoundStr``… : la valeur, plus le nom de son
champ et son état d'origine). Rangée dans un AUTRE état
(``View().key = Page().doc``), elle cassait le commit de fin de rendu,
qui copie l'état en profondeur : ``_BoundStr.__new__() missing
'field_name'``. Copiée — ``deepcopy``, ``pickle`` —, une valeur
estampillée devient la valeur simple qu'elle porte : le nom de champ et
l'origine appartiennent à la LECTURE, pas à la valeur.
"""

from __future__ import annotations

import copy
import pickle
from datetime import date, datetime

import pytest

from bretzel.state.scopes.server import _stamp

VALUES = ["unit-12", 3, 1.5, True, False, ["a", "b"], ("a", 1), date(2026, 10, 29),
          datetime(2026, 10, 29, 8, 30)]


@pytest.mark.parametrize("value", VALUES, ids=lambda v: type(v).__name__ + repr(v)[:12])
def test_a_stamped_value_copies_as_its_plain_value(value) -> None:
    stamped = _stamp(value, "field")
    assert type(stamped) is not type(value), "the read is stamped"
    for copied in (copy.deepcopy(stamped), copy.copy(stamped),
                   pickle.loads(pickle.dumps(stamped))):
        assert type(copied) is type(value) and copied == value


def test_a_stamped_value_inside_a_dict_copies_too() -> None:
    copied = copy.deepcopy({"key": _stamp("unit-12", "doc"), "n": _stamp(2, "page")})
    assert copied == {"key": "unit-12", "n": 2}
    assert type(copied["key"]) is str and type(copied["n"]) is int
