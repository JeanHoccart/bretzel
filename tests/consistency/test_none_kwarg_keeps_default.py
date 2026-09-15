"""Gate : un kwarg reactive à ``None`` garde le défaut du descripteur.

Le mécanisme. Un ``reactive_prop(default="md")`` doit valoir ``"md"`` quand
l'appelant ne fournit PAS la prop — y compris quand il la passe
explicitement à ``None`` (le signal universel « non fourni »). Sans ça,
``Button(size=None)`` stockerait ``None`` et écraserait le défaut.

Pourquoi cette gate (audit de standardisation, 2026-07-16). Avant, chaque
``__init__`` re-tapait la garde à la main — un dict ``forwarded`` +
``if x is not None: forwarded[x] = x`` avant ``super().__init__()`` — dans
50+ composants, pour empêcher un ``None`` de clobberer le défaut. C'est
désormais CENTRALISÉ dans ``Component.__init__`` : la boucle de stockage
des props reactive skippe les valeurs ``None`` (le défaut est rempli
juste après). Un composant peut donc forwarder ses kwargs directement
(``super().__init__(size=size, color=color, **kwargs)``) sans re-taper la
garde — le socle s'en charge, une fois, pour tous.

Cette gate fige l'invariant au CHOKE POINT (un composant synthétique sans
``__init__`` custom, donc ses kwargs traversent ``Component.__init__``
sans garde intermédiaire qui masquerait le comportement du socle) :

- ``prop=None``      → défaut préservé (le cœur du mécanisme).
- prop non fournie   → défaut préservé (comportement historique).
- ``prop="x"``       → valeur stockée (on ne skippe QUE None).
- ``prop=binding``   → binding adopté (une ``ClientBinding`` n'est jamais
                       ``None`` — la garde ne doit pas l'avaler).
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.testing import render_isolated
from bretzel.core.tree import Element
from bretzel.state.scopes.client import ClientBinding

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "construit un composant et LIT sa valeur stockée : le comportement "
    "est exécuté, il n'y a pas de motif à reconnaître"
)


class _Probe(Component):
    """Composant jetable : PAS de ``__init__`` custom, donc les kwargs vont
    droit à ``Component.__init__`` (aucune garde intermédiaire ne masque le
    comportement du socle testé ici)."""

    THEME: ClassVar[dict[str, Any]] = {"slots": {"root": "block"}}
    THEME_KEY: ClassVar[str] = "_probe"
    DEFAULT_TAG: ClassVar[str] = "div"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("size",)

    size: str = reactive_prop(default="md", emit_attr=False)
    enabled: bool = reactive_prop(default=True, emit_attr=False)

    def render(self) -> Element:
        return Element(tag="div", attrs={})


def test_explicit_none_keeps_default() -> None:
    """Le cœur : ``prop=None`` == prop non fournie == défaut."""
    with render_isolated():
        probe = _Probe(size=None, enabled=None)
    assert probe._reactive_values["size"] == "md", (
        "size=None a écrasé le défaut → la garde None centralisée dans "
        "Component.__init__ a été retirée (ou contournée). Un `None` reactive "
        "doit valoir « non fourni », pas clobberer le défaut du descripteur."
    )
    assert probe._reactive_values["enabled"] is True


def test_omitted_keeps_default() -> None:
    """Comportement historique : prop absente → défaut."""
    with render_isolated():
        probe = _Probe()
    assert probe._reactive_values["size"] == "md"
    assert probe._reactive_values["enabled"] is True


def test_explicit_value_is_stored() -> None:
    """On ne skippe QUE None — une vraie valeur passe."""
    with render_isolated():
        probe = _Probe(size="lg", enabled=False)
    assert probe._reactive_values["size"] == "lg"
    assert probe._reactive_values["enabled"] is False


def test_binding_is_not_swallowed_as_none() -> None:
    """Une ``ClientBinding`` n'est jamais ``None`` — elle doit être adoptée,
    pas confondue avec « non fourni »."""
    binding = ClientBinding(
        class_name="draft", instance_key="default", field_name="sz", value="lg"
    )
    with render_isolated():
        probe = _Probe(size=binding)
    assert probe._binding_metadata.get("size") is binding, (
        "un binding a été avalé par la garde None → la garde teste `is None` "
        "trop largement (une ClientBinding n'est pas None)."
    )
