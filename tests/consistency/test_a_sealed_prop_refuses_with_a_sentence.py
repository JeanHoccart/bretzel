"""Un prop SCELLÉ refuse avec une PHRASE, pas avec une collision Python.

Le fait gardé
--------------
``SEALED_PROPS`` déclare les props qu'un composant hérite mais refuse à
l'appel : l'axe d'une ``VStack`` est son identité, le ``option_value``
d'un ``Radio`` est alimenté par son ``value`` positionnel.
``bretzel.introspect`` les soustrait de la fiche, donc ils ne sont
annoncés nulle part — reste à bien répondre à qui les écrit quand même.

Ce que la DÉCLARATION ne suffisait pas à garantir
--------------------------------------------------
Déclarer ``SEALED_PROPS`` ne refuse rien : il faut appeler
``reject_sealed``. La moitié de la famille ne le faisait pas, et
personne ne pouvait le voir — les deux moitiés étaient plausibles
séparément. Mesuré le 2026-09-04 :

- les piles (``VStack`` / ``HStack`` / ``Pane``) appelaient le garde et
  répondaient « HStack has a fixed axis — pass no ``direction`` » ;
- ``Radio`` et ``ToggleButton`` laissaient la collision remonter ::

      TypeError: Component.__init__() got multiple values for
      keyword argument 'option_value'

  qui ne nomme pas le composant, ne dit pas que le prop est scellé, et
  se lit comme un bug du framework.

⚠️ Et le commentaire de ces deux-là ASSUMAIT ce message (« la passer
explicitement produit un multiple values »). Une décision écrite qui
décrit un défaut au lieu de le réparer : rien n'aurait rappelé d'y
revenir, et une relecture y aurait vu une intention.

Pourquoi le refus ne peut PAS vivre dans le socle
---------------------------------------------------
La collision de kwargs est levée par Python au moment de CONSTRUIRE
l'appel ``super().__init__(option_value=value, **kwargs)`` — donc avant
que ``Component.__init__`` ne s'exécute. Le garde doit être appelé en
tête du ``__init__`` de la sous-classe. C'est la seule ligne de câblage
que cette famille demande, et cette gate est ce qui fait qu'on ne
l'oublie pas.

Ce que la gate n'affirme PAS
-----------------------------
Que le message soit BON. Elle exige qu'il nomme la classe et le prop —
le minimum pour agir — pas qu'il explique bien. Un message juste mais
inutile passerait, et c'est assumé : la qualité d'une phrase ne se
mesure pas par un test.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError

from tests.consistency._discovery import (
    bare_kwargs,
    public_component_classes,
    ui_name_of,
)

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"


def sealing_components() -> list[tuple[type, str]]:
    """``(classe, prop)`` pour chaque scellement déclaré dans le dépôt."""
    return [
        (cls, prop)
        for cls in public_component_classes()
        for prop in (getattr(cls, "SEALED_PROPS", ()) or ())
    ]


def refusal_of(cls: type, prop: str) -> BaseException | None:
    """Ce que lève l'écriture du prop scellé — ``None`` si rien ne lève."""
    from bretzel.components.base.testing import render_isolated

    #: Les composants scellants prennent tous un premier argument
    #: positionnel (la valeur d'option, le contenu d'une pile). On passe
    #: par la table PARTAGÉE pour les requis, plus une valeur bidon pour
    #: le prop scellé — c'est son PASSAGE qu'on teste, pas sa valeur.
    try:
        with render_isolated():
            cls(*_positional_for(cls), **bare_kwargs(cls), **{prop: "x"})
    except BaseException as exc:  # noqa: BLE001 — c'est la mesure
        return exc
    return None


def _positional_for(cls: type) -> tuple[object, ...]:
    """Le premier positionnel quand la signature l'exige.

    ``ToggleButton(value)`` et ``Radio(value="")`` diffèrent sur ce
    point, et un ``TypeError`` « missing 1 required positional » se
    lirait comme un refus manqué. On le lit sur la SIGNATURE plutôt que
    de tenir une table de plus.
    """
    import inspect

    try:
        params = list(inspect.signature(cls.__init__).parameters.values())[1:]
    except (TypeError, ValueError):  # pragma: no cover — pas de signature
        return ()
    requis = [
        p
        for p in params
        if p.kind
        in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        and p.default is inspect.Parameter.empty
    ]
    return tuple("x" for _ in requis)


def test_the_sweep_finds_every_sealing_component() -> None:
    """Plancher ancré sur la DÉCOUVERTE, pas sur la population.

    Le lecteur peut se taire — ``SEALED_PROPS`` renommé, un composant
    sorti du recensement — et il se tairait en rendant une liste vide,
    soit un vert parfait sur zéro lecture.
    """
    trouves = sealing_components()
    assert len(trouves) >= 4, (
        f"le balayage ne trouve plus que {len(trouves)} scellements "
        f"(>= 4 attendus, 6 le 2026-09-04). Il s'est tu."
    )
    noms = {cls.__name__ for cls, _ in trouves}
    # Les deux FAMILLES, qui scellent pour des raisons différentes : une
    # pile scelle son axe, un item d'option scelle sa valeur. Si l'une
    # des deux disparaît du balayage, la gate ne garde plus qu'un cas.
    for ancre in ("VStack", "Radio"):
        assert ancre in noms, (
            f"``{ancre}`` ne déclare plus de prop scellée — ou le lecteur "
            f"ne la voit plus."
        )


@pytest.mark.parametrize(
    ("cls", "prop"),
    sealing_components(),
    ids=lambda v: v if isinstance(v, str) else v.__name__,
)
def test_a_sealed_prop_names_itself(cls: type, prop: str) -> None:
    leve = refusal_of(cls, prop)

    assert leve is not None, (
        f"{cls.__name__}({prop}=…) ne lève RIEN alors que ``{prop}`` est "
        f"déclaré scellé. Le prop est donc passable, et ``introspect`` le "
        f"cache pourtant de la fiche : il est utilisable et invisible."
    )
    assert isinstance(leve, ComponentUsageError), (
        f"{cls.__name__}({prop}=…) lève {type(leve).__name__} :\n  {leve}\n\n"
        f"Un refus DÉLIBÉRÉ doit être distinguable d'un accident. Appelez "
        f"``reject_sealed(kwargs, type(self))`` en TÊTE du ``__init__`` — "
        f"avant le ``super().__init__``, parce que la collision de kwargs "
        f"est levée par Python au moment de construire l'appel et que le "
        f"socle ne la voit jamais."
    )
    message = str(leve)
    # ⚠️ La classe OU son nom public. Les deux nommages existent dans le
    # dépôt et les deux sont bons : ``VStack has a fixed axis`` cite la
    # classe, le refus de ``Pane.wrap`` cite ``ui.pane`` — celui que le
    # lecteur a réellement tapé. Exiger la classe seule faisait rougir
    # ce dernier, qui est le plus soigné des six. Le versant licite,
    # encore, et il a mordu au premier essai.
    noms = {cls.__name__, ui_name_of(cls), f"ui.{ui_name_of(cls)}"}
    assert any(n in message for n in noms), (
        f"le refus de {cls.__name__}.{prop} ne se nomme pas — ni "
        f"{sorted(noms)} :\n  {message}\n\nUn message qui ne dit pas OÙ "
        f"regarder oblige à lire la pile."
    )
    assert prop in message, (
        f"le refus de {cls.__name__}.{prop} ne nomme pas le prop :\n  "
        f"{message}"
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur des composants FABRIQUÉS."""
    from typing import ClassVar

    from bretzel.components.base import Component, reactive_prop
    from bretzel.components.base._wiring import reject_sealed
    from bretzel.components.base.testing import render_isolated

    class _Scelle(Component):
        """Il déclare ET il refuse — le cas licite."""

        THEME_KEY: ClassVar[str] = "card"
        scelle: str = reactive_prop(default="", emit_attr=False)
        SEALED_PROPS: ClassVar[tuple[str, ...]] = ("scelle",)
        SEALED_REASONS: ClassVar[dict[str, str]] = {
            "scelle": "_Scelle(scelle=…) : non."
        }

        def __init__(self, value: str = "", **kwargs: object) -> None:
            reject_sealed(kwargs, type(self))
            super().__init__(scelle=value, **kwargs)

    class _Oublieux(Component):
        """Il déclare et n'appelle rien — le cas que la gate attrape."""

        THEME_KEY: ClassVar[str] = "card"
        scelle: str = reactive_prop(default="", emit_attr=False)
        SEALED_PROPS: ClassVar[tuple[str, ...]] = ("scelle",)

        def __init__(self, value: str = "", **kwargs: object) -> None:
            super().__init__(scelle=value, **kwargs)

    # ── Versant LICITE : un refus posé passe ──────────────────────────
    with render_isolated():
        with pytest.raises(ComponentUsageError) as pris:
            _Scelle(scelle="x")
    assert "_Scelle" in str(pris.value) and "scelle" in str(pris.value)

    # ── Versant ILLICITE : l'oubli rend la collision de Python ────────
    with render_isolated():
        with pytest.raises(TypeError) as brut:
            _Oublieux(scelle="x")
    assert not isinstance(brut.value, ComponentUsageError), (
        "un composant qui déclare ``SEALED_PROPS`` sans appeler "
        "``reject_sealed`` doit rendre la collision brute — sinon cette "
        "gate n'a rien à attraper, et son versant illicite est mort."
    )
    assert "multiple values" in str(brut.value)
