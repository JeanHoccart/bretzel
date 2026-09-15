"""Gate : déclarer un handler DOIT suffire à le rendre atteignable.

``EVENTS = ("close",)`` + accepter ``on_close=`` câble un listener sur
le DOM. Mais si **rien ne dispatche jamais** l'event, le handler est un
dead-letter : aucune erreur, aucun POST, le log reste vide. C'est une
classe de bug documentée (traps.md § « ``EVENTS = (...)`` + ``on_X=``
kwarg ≠ event qui fire ») — elle a déjà mordu Popover / Dialog /
Dropdown en mai 2026, puis Alert / Banner (trouvés le 2026-07-15).

Deux invariants, deux familles :

1. **``close`` → l'affordance suit le handler.** Un ``ui.alert("m",
   on_close=h)`` doit rendre le bouton ×. Sinon le listener attend un
   ``close`` que personne n'émettra. C'est Badge qui avait la réponse
   (``badge.py`` § « Peek at the wired close handler ») ; Alert et
   Banner ne l'avaient pas — ils gataient sur ``dismissible=True``
   seul, et ne résolvaient ``emit_attrs()`` qu'APRÈS la décision, donc
   ils ne pouvaient même pas voir le handler.

2. **``focus`` / ``blur`` → le listener doit être sur un élément
   FOCUSABLE.** Ces events ne BULLENT PAS : un listener sur une root
   ``<div>`` sans ``tabindex`` ne se déclenchera jamais, quel que soit
   le CSS ou le JS. ``Select`` relocalise correctement sur son
   ``<button>`` trigger ; ``ToggleGroup`` ne le faisait pas.

⚠️ **Pourquoi cette gate et pas le catalogue de surface.**
``test_catalog_surface_coverage.py`` filtre ``focus`` / ``blur`` comme
``_TRIVIAL_EVENTS`` — « browser-native, donc gratuit ». C'est
précisément l'hypothèse qui casse : **natif ≠ gratuit quand le listener
est posé sur un élément qui ne peut pas recevoir l'event**. Le filtre
rendait la gate aveugle par construction.

⚠️ **Ce que cette gate ne teste PAS**, et pourquoi : « l'event fire-t-il
vraiment ? » n'est pas décidable en SSR. Un composant peut renommer son
event (NumberInput écoute ``bzchange``, un event privé, pour éviter le
``change`` natif sale — cf. traps.md), le relocaliser (Combobox met
``on_search`` sur l'``input`` natif), le passer en kebab
(``on_month_change`` → ``month-change``), ou le laisser buller depuis un
enfant (RadioGroup : le ``change`` monte des radios natifs). Une sonde
naïve qui cherche ``bz-on:<nom exact>`` produit ~60 % de faux positifs —
mesuré. On teste donc les deux invariants STRUCTURELS ci-dessus, qui
eux sont décidables ; le reste est du ressort des probes navigateur.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.tree import Element
from tests.consistency._discovery import (
    public_component_classes,
    walk_elements,
)

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "construit le composant avec son handler et vérifie que "
    "l'affordance est RENDUE : l'exécution est le test"
)

_FOCUSABLE_TAGS = frozenset({"input", "button", "select", "textarea", "a"})


def _dummy_handler() -> None:
    """Handler serveur factice — AU NIVEAU MODULE à dessein.

    Un ``def`` imbriqué dans un test porte ``<locals>`` dans son
    qualname et le framework le rejette (``HandlerError``) — cf.
    traps.md § « Closure capturée ». La première version de cette
    gate s'y est fait prendre : 5 faux échecs.
    """


def _has_close_dispatcher(root: Element) -> bool:
    """Quelque chose peut-il émettre ``close`` dans cet arbre ?

    DEUX formes légitimes, mesurées :
    - un **bouton ×** qui ``$dispatch('close')`` — la famille
      Badge / Alert / Banner, où l'affordance est conditionnelle ;
    - un **effect** qui surveille le flag ``open`` et dispatche à la
      transition — les overlays (``_wiring.dispatch_root_effect``),
      dont le close vient d'un Escape / clic-dehors, pas d'un bouton.

    Exiger un ``<button>`` pour tous serait faux : Dropdown et Popover
    n'en ont pas et ont raison.
    """
    for node in walk_elements(root):
        if getattr(node, "tag", None) == "button":
            return True
        effect = (getattr(node, "attrs", {}) or {}).get("bz-effect", "")
        if "dispatch" in str(effect).lower():
            return True
    return False


# ── 1. close : l'affordance suit le handler ───────────────────────────

_CLOSE_COMPONENTS = [
    cls for cls in public_component_classes()
    if "close" in (getattr(cls, "EVENTS", ()) or ())
    and "dismissible" in (getattr(cls, "__reactive_props__", {}) or {})
]


@pytest.mark.parametrize(
    "cls", _CLOSE_COMPONENTS, ids=lambda c: c.__name__
)
@pytest.mark.parametrize("handler", ["client_string", "server_callable"])
def test_close_handler_renders_its_affordance(cls: type, handler: str) -> None:
    on_close = "x = 1" if handler == "client_string" else _dummy_handler
    with render_isolated():
        rendered = cls(on_close=on_close).render()
    assert _has_close_dispatcher(rendered), (
        f"{cls.__name__}(on_close=…) n'a AUCUN dispatcher de `close` "
        f"(ni bouton ×, ni effect) → le handler est un dead-letter "
        f"silencieux (pas d'erreur, pas de POST). Fix : peek le handler "
        f"câblé AVANT de décider — résous `emit_attrs()` en tête de "
        f"`render()` puis teste `attrs.get(\"hx-trigger\") == \"close\" "
        f"or \"bz-on:close\" in attrs`. Référence : `badge.py` § « Peek "
        f"at the wired close handler »."
    )


# ── 2. focus / blur : le listener doit être atteignable ───────────────

# Le relais focus de ``<bz-calendar>`` vit en JS, invisible au SSR :
# ``07_calendar.js:535-545`` écoute ``focusin`` / ``focusout`` (qui, EUX,
# bullent depuis les cellules) et re-dispatche un ``focus`` / ``blur``
# bullant depuis le custom element. Le listener posé dessus le reçoit
# donc bien. Les deux pickers embarquent ce même custom element.
# ⚠️ Nuance connue et NON couverte ici : le focus ne fire alors que
# lorsqu'il entre dans le CALENDRIER, pas dans le champ texte du
# picker — « pas silencieux, mais mauvaise cible ». Ça demande un
# probe navigateur, pas une assertion SSR. Cf. todo.md § B.
_JS_RELAY = frozenset({"Calendar", "DatePicker", "DateRangePicker"})

_FOCUS_CASES = [
    (cls, ev)
    for cls in public_component_classes()
    for ev in ("focus", "blur")
    if ev in (getattr(cls, "EVENTS", ()) or ())
    and cls.__name__ not in _JS_RELAY
]


def _listener_host_is_focusable(root: Element, event: str) -> bool | None:
    """L'élément portant ``bz-on:<event>`` peut-il recevoir cet event ?

    ``None`` quand aucun listener n'est trouvé sous ce nom : le
    composant l'a renommé / relocalisé (idiome légitime — cf. la
    docstring du module), on ne conclut pas.
    """
    for node in walk_elements(root):
        attrs = getattr(node, "attrs", {}) or {}
        if f"bz-on:{event}" not in attrs and attrs.get("hx-trigger") != event:
            continue
        tag = str(getattr(node, "tag", ""))
        return tag in _FOCUSABLE_TAGS or "tabindex" in attrs
    return None


@pytest.mark.parametrize(
    "cls,event", _FOCUS_CASES, ids=[f"{c.__name__}.{e}" for c, e in _FOCUS_CASES]
)
def test_focus_listener_lands_on_a_focusable_element(
    cls: type, event: str
) -> None:
    with render_isolated():
        try:
            rendered = cls(**{f"on_{event}": "1"}).render()
        except TypeError as exc:
            pytest.skip(f"construction fidèle non câblée : {exc}")
    host_ok = _listener_host_is_focusable(rendered, event)
    if host_ok is None:
        pytest.skip(f"{cls.__name__} renomme / relocalise son `{event}`")
    assert host_ok, (
        f"{cls.__name__}.on_{event} : le listener est posé sur un élément "
        f"NON focusable (ni tag focusable, ni `tabindex`). `{event}` ne "
        f"BULLE PAS → il ne se déclenchera jamais. Fix : relocalise le "
        f"listener sur l'élément qui reçoit vraiment le focus. "
        f"Référence : `select.py` (relocalisation sur le `<button>` "
        f"trigger)."
    )


def test_gate_is_not_vacuous() -> None:
    assert len(_CLOSE_COMPONENTS) >= 3, _CLOSE_COMPONENTS
    assert len(_FOCUS_CASES) >= 8, _FOCUS_CASES
