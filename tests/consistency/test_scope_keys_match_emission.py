"""Gate : la clé émise dans ``_serverSync`` == les ``scope_keys`` déclarés.

Un composant two-way tient sa valeur dans un signal de scope ``bz-data``
sous une clé qui **diffère souvent du nom de la prop** : ``Tabs.value``
vit sous ``active``, ``ToggleGroup.value`` sous ``picked``,
``Accordion.value`` sous ``expanded``, ``Tree.value`` sous ``sel``,
``Calendar.month`` sous ``year``+``month``.

Avant 2026-07-15 cette clé était **hardcodée** dans chaque
``server_sync_marker("active"/"picked"/…)`` — éparpillée, sans lien avec
la prop. Résultat : 5 des 8 oublis ``_serverSync`` venaient de là (on
listait la mauvaise clé, ou on oubliait). Désormais elle est **déclarée
sur la prop** (``reactive_prop(scope_keys=(...))``) et lue via
``Component._scope_keys(prop)``.

Cette gate ferme la boucle : elle rend une prop two-way server-backed et
vérifie que le ``_serverSync`` ÉMIS liste **exactement** les
``scope_keys`` déclarés. Un composant qui déclarerait
``scope_keys=("picked",)`` mais émettrait ``_serverSync: ['value']``
(clé désynchronisée) rougit. C'est le niveau 1 sur la CLÉ, pas seulement
sur la présence — la garde que le mécanisme « déclaration sur la prop »
rend possible.

⚠️ Un composant peut légitimement N'ÉMETTRE AUCUN ``_serverSync`` : sa
valeur ne vit pas dans un scope (RadioGroup ride ``bz-model``,
``Calendar.value`` ride un attribut observé, ``FormField.error`` vit sur
le binding). L'absence n'est donc pas testée ici — c'est le rôle de
``test_server_sync_completeness.py``. Ici on teste : **quand il émet, la
clé est la bonne**.
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

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "confronte les `scope_keys` déclarés à ce que le rendu émet "
    "réellement : deux sources lues, aucune reconnue par motif"
)

_DATE_COMPONENTS = frozenset({"Calendar", "DatePicker", "DateRangePicker"})


def _sample(cls: type, prop: str):
    if cls.__name__ in _DATE_COMPONENTS:
        return _dt.date(2024, 3, 1)
    return {"open": True, "checked": True}.get(prop, "a")


def _build(cls: type, prop: str, value):
    kwargs: dict[str, object] = {prop: value}
    if "change" in (getattr(cls, "EVENTS", ()) or ()):
        kwargs["on_change"] = "1"
    try:
        return cls(**kwargs)
    except TypeError:
        builder = CONSTRUCT.get(cls.__name__)
        if builder is None:
            raise
        return builder(cls, prop, value)


def _emitted_keys(cls: type, prop: str) -> set[str] | None:
    value = _stamp(_sample(cls, prop), prop)
    with render_isolated():
        try:
            html = _html.unescape(serialize(_build(cls, prop, value).render()))
        except _Skip:
            return None
    m = re.search(rf"{re.escape(SERVERSYNC_KEY)}:\s*\[([^\]]*)\]", html)
    if not m:
        return set()  # pas de scope → pas de marker (cf. docstring)
    return set(re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)))


_CASES = [
    (cls, prop)
    for cls in public_component_classes()
    for prop in getattr(cls, "TWO_WAY_PROPS", ())
]


@pytest.mark.parametrize(
    "cls,prop", _CASES, ids=[f"{c.__name__}.{p}" for c, p in _CASES]
)
def test_emitted_serversync_key_matches_declared_scope_keys(
    cls: type, prop: str
) -> None:
    emitted = _emitted_keys(cls, prop)
    if emitted is None:
        pytest.skip("construction fidèle non câblée")
    if not emitted:
        return  # aucune émission : valeur hors scope, légitime (cf. docstring)
    # ``_serverSync`` porte deux catégories : les clés de VALEUR (objet de
    # cette gate) et la config server-owned, préfixée ``_`` par convention
    # (``_total`` / ``_maxVisible`` de Pagination — le serveur en est
    # toujours propriétaire, donc toujours re-semée). Vérifié : aucune
    # ``scope_keys`` déclarée ne commence par ``_``, la partition est nette.
    emitted = {k for k in emitted if not k.startswith("_")}
    if not emitted:
        return  # que de la config re-semée : hors périmètre de cette gate
    declared = set(cls.__scope_keys__.get(prop, (prop,)))
    assert emitted == declared, (
        f"{cls.__name__}.{prop} : `_serverSync` émet {sorted(emitted)} mais "
        f"`reactive_prop(scope_keys=…)` déclare {sorted(declared)}. La clé "
        f"de scope est désynchronisée entre l'émission et la déclaration — "
        f"corrige l'une des deux (la déclaration sur la prop fait foi ; "
        f"l'émission doit lire `self._scope_keys(\"{prop}\")`)."
    )


def test_gate_is_not_vacuous() -> None:
    assert len(_CASES) >= 20, _CASES
    # Au moins un cas où la clé DIFFÈRE du nom (sinon la gate ne teste
    # qu'un mapping identité trivial).
    #
    # ⚠️ Ce plancher a demandé **cinq** de ces cas jusqu'au 2026-09-07, et
    # il les avait : treize props déclaraient une clé unique qui n'était
    # qu'un SYNONYME de leur nom (``val``, ``active``, ``current``,
    # ``sel``, ``expanded``, ``picked``). Ces synonymes sont supprimés —
    # ``reactive_prop`` refuse désormais une ``scope_keys`` d'une seule
    # clé — donc le plancher mesurait une population qui n'existe plus.
    #
    # Il ne descend pas de 5 à 2 pour s'accommoder : il change de
    # CRITÈRE. Ce qui prouve que le mécanisme est encore branché n'est
    # pas qu'une clé porte un autre nom, c'est qu'une valeur vive sous
    # PLUSIEURS clés — la seule forme que le défaut ``(prop,)`` ne peut
    # pas exprimer, et donc la seule raison d'exister du paramètre.
    multi = [
        (c.__name__, p, keys)
        for c, p in _CASES
        if len(keys := c.__scope_keys__.get(p, (p,))) > 1
    ]
    assert len(multi) >= 2, (
        f"seulement {len(multi)} props à clés MULTIPLES — le mécanisme "
        f"`scope_keys` a-t-il été retiré ? Attendu au moins "
        f"``Calendar.month`` (year+month) et ``DateRangePicker.value`` "
        f"(vstart+vend) : {multi}"
    )
    # Le versant complémentaire : toutes les AUTRES tiennent l'identité.
    # Sans cette moitié, un synonyme d'une seule clé pourrait revenir
    # sans que rien ne le voie ici — la levée de ``reactive_prop`` est
    # la vraie garde, celle-ci en est le témoin au niveau du corpus.
    synonymes = [
        (c.__name__, p, keys)
        for c, p in _CASES
        if len(keys := c.__scope_keys__.get(p, (p,))) == 1 and keys != (p,)
    ]
    assert not synonymes, (
        f"une clé de scope UNIQUE diverge du nom de sa prop : {synonymes}. "
        f"Le défaut est le nom de la prop ; un synonyme rouvre les huit "
        f"orthographes qui ont causé 5 des 8 oublis de `_serverSync`."
    )
