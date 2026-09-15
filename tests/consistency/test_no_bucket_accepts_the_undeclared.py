"""Gate : les CINQ seaux de `split_kwargs` refusent l'inconnu.

L'asymétrie que cette gate ferme, et qui a duré jusqu'au 2026-08-16 : un
event inconnu levait, un slot inconnu levait, une directive Alpine levait —
et le cinquième seau, le catch-all raw-HTML, ne disait **rien**. Le
garde-fou existait, il n'avait été posé que sur quatre entrées sur cinq.

Ce que ça coûtait, mesuré : **44 kwargs morts** sur `examples/` le
2026-08-01, dont `ui.input(label=…)` sur **22 sites** rendant
`<input label="…">` — aucun libellé, aucune erreur, rien à voir dans le
HTML. Plus cinq autres découverts en fermant, tous dans `tests/`.

⚠️ **Le refus n'est pas « refuser l'inconnu ».** Mesuré au runtime sur les
14 685 tests en instrumentant le seau : 17 kwargs distincts y passaient et
la grande majorité était légitime (34 `aria_label`, 6 `class_`, 6
directives `bz-*`, 4 `data_*`). Refuser sec aurait cassé 51 usages justes
pour attraper 5 fautes. L'échappatoire est donc **déclarée**, pas fermée —
et c'est cette déclaration que les tests ci-dessous gardent des deux
côtés : elle doit laisser passer ce qui est légitime, et **ne pas
s'élargir** jusqu'à réadmettre les noms de props inexistantes.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import (
    _RAW_HTML_NAMES,
    _RAW_HTML_PREFIXES,
    ComponentUsageError,
    split_kwargs,
)

#: Preuve de morsure : un attribut du dialecte mort doit LEVER, et
#: `test_the_declared_escapes_pass` garde l'autre sens.
MUTATION_PROOF = "test_a_dead_alpine_directive_raises"


def _stub(*, events: tuple[str, ...] = (), slots: tuple[str, ...] = ()) -> type:
    return type(
        "Stub",
        (),
        {"__reactive_props__": {}, "EVENTS": events, "NAMED_SLOTS": slots},
    )


#: Les dix familles mortes mesurées le 2026-08-01. Elles ont TOUTES la
#: forme d'un nom de prop, pas d'un attribut HTML — c'est le discriminant
#: que l'échappatoire déclarée exploite, et le vérifier ici empêche de
#: l'élargir jusqu'à les réadmettre.
_HISTORICAL_DEAD = (
    "label",
    "action",
    "variant",
    "language",
    "size",
    "align",
    "external",
    "autofocus",
    "clearable",
    "options",
)

#: Les familles légitimes, mesurées au runtime sur toute la suite.
_LEGITIMATE = (
    "aria_label",
    "aria-label",
    "data_testid",
    "data-x",
    "role",
    "class_",
    "bz-on:click",
    "bz-attr:placeholder",
    "bz-class",
    "bz-show",
    "href",
)


def test_the_allowlist_is_not_empty() -> None:
    """Plancher : l'échappatoire existe encore.

    Si les deux tables se vidaient, `test_the_declared_escapes_pass`
    rougirait bruyamment — mais si elles devenaient si LARGES que tout
    passe, seul `test_the_historical_dead_still_raise` le verrait. Les
    deux volets sont nécessaires.
    """
    assert _RAW_HTML_PREFIXES and _RAW_HTML_NAMES


@pytest.mark.parametrize("name", _LEGITIMATE)
def test_the_declared_escapes_pass(name: str) -> None:
    """Sens 1 — le refus ne ferme pas l'échappatoire."""
    _, _, _, passthrough, raw_html = split_kwargs(_stub(), {name: "x"})
    assert passthrough or raw_html, (
        f"`{name}` est une forme mesurée LÉGITIME dans ce dépôt et elle "
        f"n'atteint plus le DOM — l'échappatoire déclarée s'est refermée "
        f"dessus."
    )


@pytest.mark.parametrize("name", _HISTORICAL_DEAD)
def test_the_historical_dead_still_raise(name: str) -> None:
    """Sens 2 — l'échappatoire ne s'est pas élargie jusqu'à les réadmettre."""
    with pytest.raises(ComponentUsageError, match=name):
        split_kwargs(_stub(), {name: "x"})


def test_an_unknown_event_raises() -> None:
    with pytest.raises(ComponentUsageError, match="on_focus"):
        split_kwargs(_stub(events=("click",)), {"on_focus": lambda: None})


def test_a_dead_alpine_directive_raises() -> None:
    with pytest.raises(ComponentUsageError, match="Alpine"):
        split_kwargs(_stub(), {"@click": "alert(1)"})


def test_the_refusal_says_what_to_write_instead() -> None:
    """Un refus qui ne propose rien est un mur, pas une aide.

    C'est la norme du module — `reject_dead_alpine_attr` pointe vers son
    équivalent `bz-`. Le nouveau refus doit pointer vers `attrs={...}` et
    vers `describe`, sinon il transforme un bug silencieux en impasse.
    """
    with pytest.raises(ComponentUsageError) as caught:
        split_kwargs(_stub(), {"label": "Nom"})
    message = str(caught.value)
    assert "attrs=" in message, "le refus ne montre pas l'échappatoire explicite"
    assert "describe" in message, "le refus ne dit pas où lire l'API réelle"
