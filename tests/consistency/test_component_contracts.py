"""Gate : component binding contracts stay internally valid.

Discovers every public component from the ``ui`` namespace (no hardcoded
list — a new ``ui.foo = Foo`` is covered automatically) and asserts the
class-level contract vars point at things that actually exist :

- ``AUTONAME_FROM`` must name a real ``reactive_prop``.
- Every ``BINDABLE_PROPS`` entry must be a real ``reactive_prop``, a
  ``NAMED_SLOT``, or an ``__init__`` parameter (the text-content props
  like ``label`` / ``content`` are plain params fed to
  ``emit_text_slot``).

The framework's own runtime gate (``Component.__init__``) only rejects a
binding passed for a *non-listed* prop — it never checks that the *listed*
names exist. A typo (``BINDABLE_PROPS = ("labl",)``) or a param rename
that leaves the list stale sits latent until this test. Caught in
practice : ``Link`` declared ``BINDABLE_PROPS = ("label", …)`` while its
content parameter had drifted to ``text`` — a name matching nothing.
"""

from __future__ import annotations

import inspect

import pytest

from tests.consistency._discovery import public_component_classes

_COMPONENTS = public_component_classes()


def _allowed_binding_names(cls: type) -> set[str]:
    names = set(getattr(cls, "__reactive_props__", {})) | set(
        getattr(cls, "NAMED_SLOTS", ())
    )
    try:
        names |= set(inspect.signature(cls.__init__).parameters) - {"self"}
    except (TypeError, ValueError):
        pass
    return names


@pytest.mark.parametrize("cls", _COMPONENTS, ids=lambda c: c.__name__)
def test_autoname_from_points_at_real_reactive_prop(cls: type) -> None:
    field = getattr(cls, "AUTONAME_FROM", None)
    if field is None:
        return
    reactive = getattr(cls, "__reactive_props__", {})
    assert field in reactive, (
        f"{cls.__name__}.AUTONAME_FROM = {field!r} is not a declared "
        f"reactive_prop ({sorted(reactive)})."
    )


@pytest.mark.parametrize("cls", _COMPONENTS, ids=lambda c: c.__name__)
def test_bindable_props_is_never_the_none_sentinel(cls: type) -> None:
    """``None`` DÉSACTIVE la vérification du framework — jamais un défaut.

    ``component.py`` gate son contrôle sur ``if cls.BINDABLE_PROPS is not
    None``. Un composant qui ne déclare rien hérite du ``None`` de la base
    et devient **muet** : un binding passé sur n'importe laquelle de ses
    props est ACCEPTÉ puis jeté en silence (la prop est ``emit_attr=False``
    → la valeur SSR se fige et n'évolue jamais). ``()`` dit « aucune prop
    bindable » et produit un ``ComponentUsageError`` explicite.

    Trouvé sur ``NavbarSection`` / ``SidebarSection`` (audit 2026-07-15) —
    les 2 seuls des 77, pendant que leurs pairs (``SidebarTitle``,
    ``Navbar``, ``Tab``…) déclaraient tous ``()``. Cette gate elle-même
    faisait ``if bindable is None: return`` : elle se désactivait sur
    exactement les composants à problème.
    """
    assert getattr(cls, "BINDABLE_PROPS", None) is not None, (
        f"{cls.__name__} ne déclare pas BINDABLE_PROPS → il hérite du "
        f"sentinel `None`, qui DÉSACTIVE le contrôle : un binding y sera "
        f"accepté puis jeté SANS erreur. Déclare "
        f"`BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()` (aucune prop "
        f"bindable) ou la liste réelle."
    )


@pytest.mark.parametrize("cls", _COMPONENTS, ids=lambda c: c.__name__)
def test_bindable_carriers_are_bindable_props(cls: type) -> None:
    """Une clé de ``BINDABLE_CARRIERS`` hors ``BINDABLE_PROPS`` est morte.

    Le constructeur rejette un binding sur une prop non listée → le walker
    de carriers n'est JAMAIS atteint pour cette clé. ``FileUpload``
    déclarait ``required`` dans ses carriers sans l'avoir dans ses props
    (audit 2026-07-15) : le carrier l'annonçait, le constructeur le
    refusait. ⚠️ ``components.md`` reproduisait cette entrée morte comme
    exemple canonique — qui suivait la doc héritait du bug.
    """
    carriers = set(getattr(cls, "BINDABLE_CARRIERS", {}) or {})
    bindable = set(getattr(cls, "BINDABLE_PROPS", ()) or ())
    orphans = sorted(carriers - bindable)
    assert not orphans, (
        f"{cls.__name__}.BINDABLE_CARRIERS déclare {orphans} hors de "
        f"BINDABLE_PROPS ({sorted(bindable)}) → config morte : le "
        f"constructeur rejette le binding avant que le carrier ne serve. "
        f"Ajoute la prop à BINDABLE_PROPS, ou retire l'entrée du carrier."
    )


@pytest.mark.parametrize("cls", _COMPONENTS, ids=lambda c: c.__name__)
def test_icon_slots_is_a_subset_of_named_slots(cls: type) -> None:
    """``ICON_SLOTS ⊆ NAMED_SLOTS`` — un slot ne peut coercer une ``str``
    en ``Icon`` que s'il est d'abord routé comme slot.

    Les deux ClassVar répondent à des questions DIFFÉRENTES, et c'est
    pourquoi on les garde toutes les deux malgré des valeurs identiques
    sur les 6 déclarants :

    - ``NAMED_SLOTS`` : « ce kwarg est-il un slot ? » — le routage dans
      ``split_kwargs`` ;
    - ``ICON_SLOTS`` : « ce slot coerce-t-il une ``str`` en ``ui.icon`` ? »
      — une décision d'ergonomie.

    Les fusionner ferait coercer TOUT slot nommé. Le jour où un composant
    déclare un slot textuel (``prefix="$"`` sur Input), ``prefix``
    deviendrait ``ui.icon("$")``. La coïncidence actuelle des valeurs est
    un accident de population, pas une identité de sens.

    (Décision D1, tranchée le 2026-07-29. L'audit posait « ``NAMED_SLOTS``
    ou ``adopt_slot`` comme route unique ? » — fausse dichotomie, mesurée :
    ``NAMED_SLOTS`` route un kwarg arrivé par ``**kwargs``, ``adopt_slot``
    DÉTACHE une valeur de slot. Orthogonaux. Un composant qui consomme son
    slot localement — ``Input.prefix`` — n'a pas besoin du premier ; un qui
    le forwarde à ``super()`` — ``Button.icon_left`` — lève sans lui.)
    """
    named = set(getattr(cls, "NAMED_SLOTS", ()) or ())
    icons = set(getattr(cls, "ICON_SLOTS", ()) or ())
    orphans = sorted(icons - named)
    assert not orphans, (
        f"{cls.__name__}.ICON_SLOTS déclare {orphans} hors de NAMED_SLOTS "
        f"({sorted(named)}) → config morte : le kwarg n'est pas routé comme "
        f"slot, donc la coercion str→Icon n'est jamais atteinte."
    )


def test_every_component_is_re_exported() -> None:
    """``__all__`` nomme chaque composant public.

    ⚠️ ``_UI`` est la RACINE de l'arbre de découverte
    (``_discovery.public_component_classes``) : un composant qui manque à
    l'aliasing devient invisible à ``test_every_public_symbol_is_describable`` +
    ``test_audit_coverage`` + ``test_catalog_surface_coverage``
    SIMULTANÉMENT, sans qu'aucune ne rougisse. Oublier la seule chose
    non gardée désactive les trois qui le sont. Cette gate ferme la
    moitié ``__all__`` (4 classes manquaient : Navbar, NavbarItem,
    NavbarSection, SidebarTitle — importées et aliasées, donc
    ``ui.navbar`` marchait et rien ne bronchait).
    """
    import bretzel.components as pkg

    exported = set(getattr(pkg, "__all__", []))
    missing = sorted(c.__name__ for c in _COMPONENTS if c.__name__ not in exported)
    assert not missing, (
        f"{missing} sont exposés sur `ui` mais absents de "
        f"`bretzel/components/__init__.py::__all__` — contrat de "
        f"re-export cassé."
    )
    stale = sorted(n for n in exported if not hasattr(pkg, n))
    assert not stale, f"`__all__` nomme {stale}, qui n'existe pas."


@pytest.mark.parametrize("cls", _COMPONENTS, ids=lambda c: c.__name__)
def test_bindable_props_reference_real_names(cls: type) -> None:
    bindable = getattr(cls, "BINDABLE_PROPS", None)
    if bindable is None:
        return  # couvert par test_bindable_props_is_never_the_none_sentinel
    allowed = _allowed_binding_names(cls)
    orphans = [p for p in bindable if p not in allowed]
    assert not orphans, (
        f"{cls.__name__}.BINDABLE_PROPS names {orphans} that are neither a "
        f"reactive_prop, a NAMED_SLOT, nor an __init__ parameter. "
        f"Allowed : {sorted(allowed)}."
    )


def test_discovery_non_trivial() -> None:
    # A refactor that hides the components would make every parametrized
    # case vanish and the suite pass vacuously — pin a floor.
    assert len(_COMPONENTS) >= 50
