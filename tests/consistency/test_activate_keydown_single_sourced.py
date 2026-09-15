"""L'activation clavier d'un élément non natif sort d'UN seul endroit.

Un ``<button>`` reçoit Enter / Espace gratuitement du navigateur. Un
``<div role="button">``, une ``<tr role="button">``, un
``<div role="treeitem">`` ne reçoivent **rien** : sans handler explicite,
l'élément est atteignable au Tab et totalement inerte au clavier.

Trois modules l'implémentaient, de trois façons (recensement des
affordances, 2026-07-28) — et deux écarts étaient FONCTIONNELS :

- ``'Spacebar'`` (l'ancien nom de touche) n'était géré que par la dropzone
  de ``file_upload`` : la dropzone s'activait à l'Espace sur un vieux
  navigateur, un nœud d'arbre non ;
- la garde de cible ``$event.target === $el`` n'existait que dans
  ``table``. Sans elle, une frappe sur un contrôle ENFANT bulle jusqu'au
  parent et l'active aussi.

``_wiring.activate_keydown(action_js)`` porte le sur-ensemble correct. La
gate vérifie l'ADOPTION (personne ne réécrit le garde) et le CONTRAT (le
helper contient bien les trois touches et la garde) — parce qu'un helper
adopté mais amputé ne vaut rien.

⚠️ Hors périmètre : les **keymaps composites** de select / combobox /
slider / number_input. Ce ne sont pas « active ce truc non natif » mais un
contrat clavier riche (flèches, Home/End, Escape), et l'un d'eux omet
DÉLIBÉRÉMENT la branche Espace — le trigger du combobox est un
``<input type=text>``, où Espace doit taper un espace.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bretzel.components.base._wiring import activate_keydown
from tests.consistency._discovery import parsed_sources, source_of

_COMPONENTS = Path(__file__).resolve().parents[2] / "bretzel" / "components"

#: 272 fichiers sous ``bretzel/components`` le 2026-08-19 ; le plancher
#: laisse de la marge pour une réorganisation sans laisser passer un
#: balayage mort.
_COMPONENTS_FLOOR = 200
_OWNER = _COMPONENTS / "base" / "_wiring.py"

# Le garde réécrit à la main : un test de touche Enter dans une expression
# ``bz-on:keydown``. Les keymaps composites matchent ``$event.key`` via une
# variable (``const k = $event.key``), pas ce motif — d'où leur exemption
# naturelle, sans liste à maintenir.
_HAND_ROLLED = re.compile(r"""\$event\.key\s*===\s*['"]Enter['"]""")


def _sources() -> list[Path]:
    return [s.path for s in parsed_sources(_COMPONENTS, floor=_COMPONENTS_FLOOR)]


@pytest.mark.parametrize("path", _sources(), ids=lambda p: p.name)
def test_no_hand_rolled_activation_guard(path: Path) -> None:
    if path == _OWNER:
        pytest.skip("le module qui possède le helper")
    offenders = [
        (i, line.strip())
        for i, line in enumerate(source_of(path).text.splitlines(), 1)
        if _HAND_ROLLED.search(line)
    ]
    assert not offenders, (
        f"{path.name} réécrit le garde d'activation clavier :\n"
        + "\n".join(f"    :{i}  {t[:86]}" for i, t in offenders)
        + "\n  Passe par `activate_keydown(<action_js>)` (base/_wiring.py). "
          "Il porte les trois noms de touche — dont le legacy `Spacebar`, "
          "qu'un seul des trois sites gérait — et la garde de cible, qui "
          "empêche une frappe sur un enfant d'activer le parent."
    )


def test_the_helper_keeps_its_contract() -> None:
    """Un helper adopté mais amputé ne vaudrait rien."""
    js = activate_keydown("doThing();")
    assert "$event.target === $el" in js, "garde de cible perdue"
    for key in ("'Enter'", "' '", "'Spacebar'"):
        assert key in js, f"touche {key} perdue"
    assert "$event.preventDefault()" in js, "preventDefault perdu"
    assert js.rstrip().endswith("doThing(); }"), (
        f"l'action n'est pas exécutée en dernier : {js!r}"
    )


def test_the_gate_sees_its_consumers() -> None:
    """Garde-fou : si plus personne n'appelle le helper, la gate ment."""
    users = [
        p.name for p in _sources()
        if p != _OWNER and "activate_keydown(" in p.read_text(encoding="utf8")
    ]
    assert len(users) >= 3, (
        f"`activate_keydown` n'est appelé que par {users} — le recensement "
        f"en comptait trois (table, file_upload, tree). Adoption régressée ?"
    )


def test_the_detector_still_bites() -> None:
    """Mutation : une garde d'activation écrite à la main est reconnue.

    Le helper existe pour que ``Enter`` et ``Space`` soient traités
    partout pareil. Une regex aveugle laisserait chaque composant
    re-rouler la sienne — c'est exactement ce qui avait produit les
    dialectes que le helper a remplacés.
    """
    for offending in ("$event.key === 'Enter'", '$event.key==="Enter"'):
        assert _HAND_ROLLED.search(offending), f"{offending!r} devrait mordre"
    for licit in ("$bz.helpers.activate($event)", "$event.key === 'Escape'"):
        assert not _HAND_ROLLED.search(licit), f"{licit!r} : faux positif"
