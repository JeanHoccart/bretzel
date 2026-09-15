"""Gate : tout composant qui garde sa valeur dans un scope client
synchronise avec le serveur — et NE synchronise PAS autrement.

Le mécanisme. Un composant qui tient sa valeur dans un signal de scope
(``bz-data``) la voit PRÉSERVÉE au morph : ``scope.absorb`` skippe
délibérément les clés dont le signal existe déjà, sinon un refresh
voisin écraserait l'état client vivant (dropdown ouvert, query à
moitié tapée). Conséquence : quand le SERVEUR change la valeur et
rafraîchit, le signal ne la ré-adopte jamais. Le marker
``_serverSync`` est l'opt-in qui dit au bridge « ré-adopte cette clé ».

Trois cas, un seul émet :

- ``value=10`` littéral → PAS de marker (rien à ré-adopter ; l'émettre
  écraserait la saisie du client à chaque swap) ;
- ``value=state.champ`` (serveur) → marker (le serveur fait foi) ;
- ``value=clientstate.champ`` → PAS de marker (la valeur vit dans
  ``$bz._store``, que l'envelope patche déjà).

Pourquoi cette gate (audit 2026-07-15). Ce bug a été oublié **HUIT
fois** : Tabs, Pagination, Accordion, Tree, le cas multi, NumberInput,
select/combobox en multi, Sidebar. Ce n'est pas de l'étourderie, c'est
mécanique : la décision « cette valeur vient-elle du serveur ? » était
re-tapée dans **5 dialectes divergents** pour 12 call-sites, et le
dialecte le plus complet (toggle_group) et l'émetteur le plus propre
(calendar) vivaient dans deux composants différents — quoi qu'un auteur
copie, il héritait d'un défaut. La décision vit désormais **une** fois
dans ``Component._value_server_backed``.

⚠️ **Pourquoi cette gate et pas ``test_serversync_gating``.** Celle-ci
est pilotée par ``TWO_WAY_PROPS`` + ``public_component_classes()`` : un
composant qui déclare écrire une valeur est testé, qu'on y ait pensé ou
non. L'autre repose sur une table ``_CASES`` écrite à la main —
Sidebar n'y était pas, et **personne ne savait qu'il fallait l'y
mettre**. Une liste teste la mémoire de l'auteur, pas le contrat.

⚠️ **« Pas de marker » n'est pas toujours un bug** : ça dépend d'où vit
la valeur. RadioGroup n'a AUCUN ``bz-data`` (la sélection ride
``bz-model`` sur les radios natifs) et la value de Calendar ride un
attribut observé que le morph re-stampe nativement — les deux ont
raison de ne rien émettre. C'est ``_NO_SCOPE`` : le jour où l'un d'eux
se met à tenir sa valeur dans un scope, la gate le réclame.
"""

from __future__ import annotations

import datetime as _dt
import html as _html
import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.runtime.protocol import SERVERSYNC_KEY
from bretzel.state.scopes.server import _stamp
from tests.audit.test_binding_completeness import CONSTRUCT, _Skip
from tests.consistency._discovery import public_component_classes

#: Preuve de morsure : l'autre moitié du contrat : une valeur littérale ne doit SURTOUT pas
#: émettre le marker, et `test_server_backed_value_is_synced` garde le sens direct.
MUTATION_PROOF = "test_literal_value_is_not_synced"

# Composants dont la valeur NE vit PAS dans un signal de scope — ils ont
# donc raison de ne jamais émettre le marker. Vérifié : RadioGroup ne rend
# aucun ``bz-data`` ; le scope de Calendar ne porte que ``{year, month}``
# (sa value ride ``root_attrs["value"]``, ré-stampé nativement au morph).
# Sortir d'ici = tenir sa valeur dans un scope = devoir synchroniser.
_NO_SCOPE: frozenset[tuple[str, str]] = frozenset({
    ("RadioGroup", "value"),
    ("Calendar", "value"),
    # ``error`` est bien two-way (``bz-on:input`` fait ``<path> = ''``)
    # mais FormField ne rend AUCUN ``bz-data`` — l'erreur vit sur le
    # binding, pas dans un signal de scope. Rien à ré-adopter.
    ("FormField", "error"),
})

# Valeur serveur CRÉDIBLE par prop : le stamp doit survivre à la
# normalisation du composant. Un ``month`` qui reçoit ``"a"`` lève un
# ``ValueError: Invalid isoformat string`` — le faux échec vient de la
# sonde, pas du composant.
_SAMPLE: dict[str, object] = {
    "open": True,
    "checked": True,
    "expanded": True,
    "month": _dt.date(2024, 3, 1),
}
_SAMPLE_BY_COMPONENT: dict[tuple[str, str], object] = {
    ("Calendar", "value"): _dt.date(2024, 3, 1),
    ("DatePicker", "value"): _dt.date(2024, 3, 1),
    ("DateRangePicker", "value"): (_dt.date(2024, 3, 1), _dt.date(2024, 3, 5)),
}


def _raw_value(cls: type, prop: str):
    key = (cls.__name__, prop)
    if key in _SAMPLE_BY_COMPONENT:
        return _SAMPLE_BY_COMPONENT[key]
    return _SAMPLE.get(prop, "a")


def _server_value(cls: type, prop: str):
    return _stamp(_raw_value(cls, prop), prop)


_CASES = [
    (cls, prop)
    for cls in public_component_classes()
    for prop in getattr(cls, "TWO_WAY_PROPS", ())
    if (cls.__name__, prop) not in _NO_SCOPE
]


def _build(cls: type, prop: str, value):
    """Construire ``cls`` INTERACTIF.

    ⚠️ Le ``on_change`` n'est pas décoratif. Les inputs simples
    (Input / Textarea / Checkbox / Switch) ne créent leur scope de
    valeur QUE s'ils sont interactifs (``inputs/_wiring.py`` : « no-op si
    ``_event_attrs`` est vide → un input 100 % statique reste un wrapper
    natif, pas de poids DOM »). Les construire sans handler donne donc
    « pas de scope » — un faux échec de la SONDE, pas du composant. La
    première version de cette gate s'y est fait prendre sur 4 composants.
    """
    kwargs: dict[str, object] = {prop: value}
    if "change" in (getattr(cls, "EVENTS", ()) or ()):
        kwargs["on_change"] = "1"  # string handler : pas de contexte requis
    try:
        return cls(**kwargs)
    except TypeError:
        builder = CONSTRUCT.get(cls.__name__)
        if builder is None:
            raise
        return builder(cls, prop, value)


def _emits(cls: type, prop: str, value) -> bool | None:
    """La VALEUR de ``prop`` est-elle re-semée ?

    Pas « un marker existe-t-il » : ``_serverSync`` porte aussi la config
    server-owned (``_total`` / ``_maxVisible``), toujours re-semée parce que
    le serveur en est toujours propriétaire. La présence du marker ne dit
    donc plus rien sur la valeur — il faut lire les CLÉS. Les clés de config
    sont préfixées ``_`` par convention (vérifié : aucune ``scope_keys``
    déclarée ne l'est).
    """
    with render_isolated():
        try:
            comp = _build(cls, prop, value)
        except _Skip:
            return None
        html = serialize(comp.render())
    keys = set()
    for raw in re.findall(rf"{SERVERSYNC_KEY}: \[([^\]]*)\]",
                          _html.unescape(html)):
        keys |= {k.strip().strip("'\"") for k in raw.split(",") if k.strip()}
    value_keys = {k for k in keys if not k.startswith("_")}
    return bool(value_keys)


@pytest.mark.parametrize(
    "cls,prop", _CASES, ids=[f"{c.__name__}.{p}" for c, p in _CASES]
)
def test_server_backed_value_is_synced(cls: type, prop: str) -> None:
    """``value=state.champ`` → le serveur DOIT pouvoir la reprendre."""
    emitted = _emits(cls, prop, _server_value(cls, prop))
    if emitted is None:
        pytest.skip("construction fidèle non câblée")
    assert emitted, (
        f"{cls.__name__}.{prop} = <valeur serveur> n'émet pas "
        f"`{SERVERSYNC_KEY}` → une mutation serveur suivie d'un refresh "
        f"ne changera RIEN à l'écran (idiomorph préserve le signal "
        f"client). Fix : `server_sync_marker(\"<clé de scope>\", "
        f"enabled=self._value_server_backed(\"{prop}\"))` dans le "
        f"`bz-data`. Si {cls.__name__} ne tient PAS sa valeur dans un "
        f"scope, inscris-le dans `_NO_SCOPE` avec la raison."
    )


@pytest.mark.parametrize(
    "cls,prop", _CASES, ids=[f"{c.__name__}.{p}" for c, p in _CASES]
)
def test_literal_value_is_not_synced(cls: type, prop: str) -> None:
    """``value=10`` littéral → surtout PAS de marker.

    C'est l'autre moitié du contrat, et elle a mordu autant : émettre
    sans condition faisait réécrire le signal à sa valeur SSR à CHAQUE
    swap — la saisie de l'utilisateur était écrasée, et un ``change``
    fantôme partait au serveur (NumberInput, 6ᵉ récidive).
    """
    emitted = _emits(cls, prop, _raw_value(cls, prop))
    if emitted is None:
        pytest.skip("construction fidèle non câblée")
    assert not emitted, (
        f"{cls.__name__}.{prop} = <littéral> émet `{SERVERSYNC_KEY}` → à "
        f"chaque swap le bridge réécrit le signal à la valeur SSR et "
        f"écrase ce que l'utilisateur vient de faire. Gate le marker sur "
        f"`self._value_server_backed(\"{prop}\")`."
    )


def test_no_scope_entries_are_still_scope_less() -> None:
    """``_NO_SCOPE`` n'est pas une exemption : c'est un fait vérifiable.

    Le jour où RadioGroup / Calendar se mettent à tenir leur valeur dans
    un scope, ils DOIVENT synchroniser — et cette gate doit le réclamer
    au lieu de les laisser passer sur une vieille promesse.
    """
    known = {(c.__name__, p) for c in public_component_classes()
             for p in getattr(c, "TWO_WAY_PROPS", ())}
    stale = sorted(_NO_SCOPE - known)
    assert not stale, f"`_NO_SCOPE` nomme {stale}, qui n'est plus two-way."

    import re

    for name, prop in sorted(_NO_SCOPE):
        cls = next(c for c in public_component_classes() if c.__name__ == name)
        with render_isolated():
            try:
                html = serialize(_build(cls, prop, _server_value(cls, prop)).render())
            except _Skip:
                continue
        # L'invariant exact : la prop ne doit pas être une CLÉ d'un scope.
        # (Pas « aucun bz-data » — Calendar en a un, portant ``{year,
        # month}`` : sa chrome de navigation, pas sa value.)
        scopes = re.findall(r'bz-data="([^"]*)"', html)
        holds_it = any(
            re.search(rf"[{{,]\s*{re.escape(prop)}\s*:", s) for s in scopes
        )
        assert not holds_it, (
            f"{name}.{prop} est dans `_NO_SCOPE` (« sa valeur ne vit pas "
            f"dans un signal de scope ») mais son `bz-data` porte "
            f"maintenant une clé `{prop}:` → idiomorph la préservera au "
            f"morph, donc une mutation serveur ne l'atteindra plus. "
            f"Retire-le de `_NO_SCOPE` et émets le marker."
        )


def test_gate_is_not_vacuous() -> None:
    assert len(_CASES) >= 15, (
        f"seulement {len(_CASES)} paires two-way testées — "
        f"`TWO_WAY_PROPS` a-t-il disparu des composants ?"
    )
