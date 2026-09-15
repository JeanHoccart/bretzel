"""Gate : un Component passé en slot ne doit JAMAIS rester orphelin.

Le mécanisme. Un composant s'auto-enregistre chez le parent actif dès sa
construction — c'est son seul signal de « qui me possède ». Passé en slot
(``ui.badge(label=ui.text("hi"))``), cet enregistrement doit être ANNULÉ,
sinon il rend **deux fois** : une comme frère, une dans le slot.

``Component.adopt_slot(value)`` est l'unique helper : il détache un
Component, et laisse passer intacts une string, un ``ClientBinding`` et
``None``. Il doit être appelé **à la construction** — détacher dans
``render()`` est trop tard, le parent a déjà émis l'orphelin.

Pourquoi cette gate (audit 2026-07-15). Trois routes coexistaient pour le
même travail :

    self._label = Component.adopt_slot(label)                  # Button — OK
    Component._detach_from_parent(msg); self._message = msg    # Alert — à la main
    self._label = label                                        # Badge — CASSÉ

7 slots rendaient double : ``Badge.label``, ``Banner.title``,
``Banner.message``, ``EmptyState.title``, ``EmptyState.description``,
``Code.text``, ``Link.label``. Et le bug s'est propagé **par imitation** :
les commentaires de Banner (« same pattern as Badge ») et d'EmptyState
(« same idiom as Badge ») disent qu'ils ont copié Badge, qui était la
source cassée.

⚠️ **La gate ne teste QUE l'orphelinage**, pas le rendu du slot. Raison
mesurée : un composant enfant (``Tab``, ``AccordionItem``, ``TreeNode``)
est rendu par son PARENT, donc appeler ``child.render()`` isolément ne
prouve rien — un premier jet de cette sonde a produit ~50 % de faux
positifs par ce biais (il accusait ``Breadcrumb.separator``, qui est
correct depuis ``59906b0``). L'orphelinage, lui, se mesure sur le
``parent_stack`` : il est indépendant de qui rend le slot, donc fiable
pour tous. La stringification (``<bretzel…object at 0x…>`` en page) est un
défaut RÉEL et distinct — il vit dans le chantier slots (todo.md § E) et
demandait un rig parent-aware — et a été traitée à la source : les 6
composants concernés rendent désormais leur slot via ``emit_text_slot``
(qui a une branche Component), les 2 autres refusent explicitement.

Cf. traps.md § « Slot Component stocké sans adopt_slot ».
"""

from __future__ import annotations

import inspect

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.text import Text
from tests.audit.test_binding_completeness import CONSTRUCT, _Skip
from tests.consistency._discovery import public_component_classes

# Les noms de paramètres qui désignent un trou de CONTENU. Dérivés des
# signatures réelles, pas d'une liste de composants : un nouveau
# ``ui.foo(label=…)`` est couvert sans toucher ce fichier.
_CONTENT_PARAMS = frozenset({
    "label", "title", "message", "description", "content", "text", "hint",
    "separator", "prefix", "suffix", "trigger", "icon", "icon_left",
    "icon_right", "avatar", "badge",
})


def _slot_params(cls: type) -> list[str]:
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return []
    return [p for p in params if p in _CONTENT_PARAMS]


_CASES = [
    (cls, prop)
    for cls in public_component_classes()
    for prop in _slot_params(cls)
]


# ── Dette CONNUE — à faire fondre, PAS une liste de cas acceptés ──────
#
# ⚠️ Égalité STRICTE (même discipline que ``test_size_reaches_slots``) :
# réparer un slot sans le retirer d'ici fait échouer la gate. La liste ne
# peut donc pas pourrir en « exemptions » silencieuses.
#
# ✅ VIDE depuis le 2026-07-15 — les 8 sont résolus, de deux façons.
#
# **6 réparés** (Checkbox / Radio / Switch / Divider `label`,
# `DateRangePicker.separator`, `Tooltip.text`) : ils faisaient
# ``self._x = x`` puis ``TextNode(self._x)``. Le fix est un COUPLE —
# ``adopt_slot`` au constructeur (détache, sinon rendu 2×) ET
# ``emit_text_slot`` au render (rend le Component, sinon il file dans
# ``TextNode()`` qui attend une string). Le docstring d'``emit_text_slot``
# décrivait déjà les deux moitiés comme indissociables.
#
# **2 refusent explicitement**, et c'est un AFFINEMENT de la décision
# « réparer, pas refuser » (todo.md § E) : elle visait les slots de
# CONTENU, or ces deux-là n'en sont pas.
#   - ``Markdown.text`` est la SOURCE markdown (parsée par mistune) —
#     un Component y est une erreur de catégorie. Markdown refusait déjà
#     un ClientBinding pour la même raison ; on suit sa convention.
#   - ``FileUpload.label`` sert AUSSI de ``aria-label`` — un attribut HTML
#     ne porte qu'une string. Refuser est ici MEILLEUR pour l'a11y
#     qu'accepter (un label visible ≠ nom accessible serait un vrai bug).
#
# Si un nouveau slot casse, il atterrit ici — et cette liste ne doit que
# rétrécir (égalité stricte plus bas).
_BASELINE: frozenset[str] = frozenset()


def _build(cls: type, prop: str, value):
    try:
        return cls(**{prop: value})
    except TypeError:
        builder = CONSTRUCT.get(cls.__name__)
        if builder is None:
            raise
        return builder(cls, prop, value)


@pytest.mark.parametrize(
    "cls,prop", _CASES, ids=[f"{c.__name__}.{p}" for c, p in _CASES]
)
def test_component_slot_is_adopted_not_orphaned(cls: type, prop: str) -> None:
    from bretzel.components.layout.flex.flex import Flex

    with render_isolated():
        parent = Flex(direction="col")
        try:
            with parent:
                probe = Text("probe")
                _build(cls, prop, probe)
        except _Skip as exc:
            pytest.skip(str(exc))
        except ComponentUsageError:
            # REFUS EXPLICITE = comportement CORRECT, pas une lacune.
            # Une prop peut légitimement n'accepter qu'une string quand
            # ce n'est pas un slot de contenu : ``Markdown.text`` est de
            # la source parsée, ``FileUpload.label`` sert d'``aria-label``
            # (un attribut). Ce qui est interdit, c'est d'accepter en
            # silence PUIS de stringifier — le refus doit être bruyant et
            # expliquer l'issue. C'est le cas ici : on passe.
            return
        except TypeError as exc:
            pytest.skip(f"construction fidèle non câblée : {exc}")
        orphaned = any(child is probe for child in parent._children)

    key = f"{cls.__name__}.{prop}"
    if key in _BASELINE:
        assert orphaned, (
            f"{key} n'orpheline plus — RETIRE-le de `_BASELINE`. "
            f"(Égalité stricte : la baseline est la dette connue, elle ne "
            f"doit contenir que ce qui est encore cassé.)"
        )
        pytest.xfail("dette connue — chantier slots, cf. todo.md § E")

    assert not orphaned, (
        f"{key} : le Component passé en slot est resté enfant du parent → "
        f"il rendra DEUX FOIS (une en frère, une dans le slot). Fix : "
        f"`self._{prop} = Component.adopt_slot({prop})` dans __init__ "
        f"(PAS dans render() — trop tard, le parent a déjà émis "
        f"l'orphelin). Cf. traps.md § « Slot Component stocké sans "
        f"adopt_slot »."
    )


def test_baseline_has_no_stale_entry() -> None:
    """La baseline ne nomme que des paires qui EXISTENT encore."""
    known = {f"{c.__name__}.{p}" for c, p in _CASES}
    stale = sorted(_BASELINE - known)
    assert not stale, (
        f"`_BASELINE` nomme {stale}, qui n'existe plus (renommé / "
        f"supprimé) — nettoie la baseline."
    )


def test_gate_is_not_vacuous() -> None:
    assert len(_CASES) >= 25, (
        f"seulement {len(_CASES)} paires (composant, slot) découvertes — "
        f"un refactor a-t-il déplacé les composants ou renommé les slots ?"
    )
