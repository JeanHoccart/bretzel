"""Un ``aria-*`` réactif émet la CHAÎNE ``"true"``/``"false"``.

``bz-attr`` traite un booléen comme HTML le veut : ``true`` → attribut
**vide**, ``false`` → attribut **retiré** (``02_directives.js``). C'est
correct pour ``disabled`` / ``checked`` / ``required``, où la présence de
l'attribut EST l'information.

ARIA ne marche pas comme ça. ``aria-disabled`` veut littéralement
``"true"`` ou ``"false"`` :

- la variante Tailwind ``aria-disabled:`` compile vers
  ``[aria-disabled="true"]`` — un attribut vide ne matche pas, donc le
  style verrouillé ne s'applique jamais ;
- un lecteur d'écran lit la VALEUR, pas la présence.

Le bug (recensement des affordances, 2026-07-28) : `select` multi et
`combobox` passaient par ``forward_binding(as_attr="aria-disabled")``, qui
posait le chemin nu. Sur ``ui.select(multiple=True, disabled=<binding>)``,
ni le style ni l'annonce ne s'activaient. Silencieux des deux côtés.

Ce qui rend le cas intéressant : **le framework connaissait le piège**. Le
ternaire était écrit à la main, avec son commentaire, dans
``navigation/_wiring.py:182`` et ``calendar.py:792``. Deux sites l'ont
manqué parce que la règle vivait dans des commentaires, pas dans le code.
Elle est maintenant **dérivée** par ``forward_binding`` — d'où cette gate,
qui vérifie la dérivation ET le rendu réel.
"""

from __future__ import annotations

import re

import pytest

from bretzel import ui
from bretzel.state import field
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientState, rendering_scope

# Un chemin d'état NU — exactement ce qu'il ne faut pas voir sur un aria-*.
_BARE_PATH = re.compile(r"^\$bz\.state\.[\w.]+$")

_ARIA_ATTR = re.compile(r'bz-attr:(aria-[\w-]+)="([^"]*)"')


class _Flag(ClientState):
    off: bool = field(default=True)


# Les composants qui émettent un ``aria-*`` réactif quand on leur passe un
# binding. Liste explicite : chacun a sa propre signature de construction,
# et on veut exercer le chemin où l'aria est RÉELLEMENT produit.
_CASES: dict[str, object] = {
    "select_multi": lambda s: ui.select(
        options=["a", "b"], multiple=True, disabled=s.off,
    ),
    "select_single": lambda s: ui.select(options=["a", "b"], disabled=s.off),
    "combobox": lambda s: ui.combobox(options=["a", "b"], disabled=s.off),
    "calendar": lambda s: ui.calendar(disabled=s.off),
    "slider": lambda s: ui.slider(disabled=s.off),
    "file_upload": lambda s: ui.file_upload(disabled=s.off),
    "checkbox": lambda s: ui.checkbox(label="x", disabled=s.off),
}


def _render(build) -> str:
    with render_isolated(), rendering_scope():
        return serialize(build(_Flag()).render())


@pytest.mark.parametrize("name", sorted(_CASES))
def test_reactive_aria_is_never_a_bare_path(name: str) -> None:
    """Un ``bz-attr:aria-*`` ne porte jamais un chemin d'état nu."""
    html = _render(_CASES[name])
    offenders = [
        (attr, value)
        for attr, value in _ARIA_ATTR.findall(html)
        if _BARE_PATH.match(value.strip())
    ]
    assert not offenders, (
        f"{name} émet un `aria-*` réactif en chemin NU : {offenders}.\n"
        f"  `bz-attr` sur un booléen pose un attribut VIDE (true) ou le "
        f"retire (false) — la variante Tailwind `aria-…:` matche "
        f"`[aria-… =\"true\"]` et ne verra rien, et un lecteur d'écran lit "
        f"la valeur, pas la présence.\n"
        f"  Passe par `forward_binding(as_attr=\"aria-…\")`, qui dérive le "
        f"ternaire, ou écris-le : `({{path}}) ? 'true' : 'false'`."
    )


def test_forward_binding_derives_the_ternary_for_aria() -> None:
    """La règle vit dans le code, plus dans un commentaire.

    Le pendant du test ci-dessus, au niveau du mécanisme : c'est la
    dérivation qui doit distinguer ARIA d'un attribut natif, sinon chaque
    appelant doit se souvenir de la règle — et deux l'avaient oubliée.
    """
    # Plus de déséchappement : ``escape_attr`` laisse l'apostrophe
    # intacte depuis le 2026-08-28, donc le ternaire arrive tel quel.
    html = _render(_CASES["select_multi"])
    aria = dict(_ARIA_ATTR.findall(html))
    assert "aria-disabled" in aria, "aucun aria-disabled réactif émis"
    assert aria["aria-disabled"].endswith("? 'true' : 'false'"), (
        f"attendu un ternaire stringifié, obtenu {aria['aria-disabled']!r}"
    )


def test_native_boolean_attrs_keep_the_bare_path() -> None:
    """Le pendant négatif : la dérivation ne déborde pas sur le natif.

    Sur ``disabled`` / ``checked``, la sémantique « attribut vide » est
    justement la bonne — stringifier casserait le contrat HTML.
    """
    html = _render(_CASES["file_upload"])
    native = re.findall(r'bz-attr:disabled="([^"]*)"', html)
    assert native, "aucun `disabled` natif réactif émis"
    assert all(_BARE_PATH.match(v.strip()) for v in native), (
        f"un attribut booléen NATIF a été stringifié : {native}"
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les cas d'aria réactif sont toujours là."""
    assert len(_CASES) >= 6, (
        f"seulement {len(_CASES)} cas d'aria réactif (7 le 2026-08-19) — "
        f"la table a rétréci, et « aucun chemin nu » juge moins qu'avant."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : un chemin d'état NU dans un ``aria-*`` est encore reconnu.

    Un ``aria-expanded="$bz.state.X"`` rend la chaîne ``"false"``, qui
    est TRUTHY pour un lecteur d'écran : l'état annoncé est faux dans un
    sens sur deux. Deux regex se relaient — l'extraction de l'attribut
    et la reconnaissance du chemin nu.
    """
    found = _ARIA_ATTR.search(
        '<div bz-attr:aria-expanded="$bz.state.UI.default.open">'
    )
    assert found, "l'extraction de l'attribut aria ne matche plus"
    assert found.group(1) == "aria-expanded"
    assert _BARE_PATH.match(found.group(2)), "le chemin nu devrait mordre"
    for ternary in ("$bz.state.UI.default.open ? 1 : 0", "String(x)"):
        assert not _BARE_PATH.match(ternary), f"{ternary!r} : faux positif"
