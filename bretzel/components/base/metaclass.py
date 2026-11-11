"""The metaclass of every component, and the kwargs every component reserves."""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING, Any, Final

from bretzel.components.base.arguments import derive_display_bindings
from bretzel.components.base.attrs import (
    ComponentDefinitionError,
)
from bretzel.components.base.composition import (
    render_in_its_zone,
)
from bretzel.components.base.events import (
    cross_check_events,
    with_carriers,
)
from bretzel.components.base.reactive_prop import (
    ReactivePropDescriptor,
)
from bretzel.components.base.universals import finish_render

if TYPE_CHECKING:
    pass


#: The kwargs EVERY component accepts, removed by
#: :meth:`Component.__init__` **before** ``split_kwargs`` — they are
#: never in a signature (the "no universal kwargs in an API signature"
#: rule).
#:
#: This is the source, and
#: ``test_reserved_kwargs_match_the_socle`` checks by AST that it matches
#: the real ``pop``: the ``pop`` stay heterogeneous (each does a
#: different job with its value), so one cannot loop over them — but one
#: can refuse that they diverge from a declaration.
RESERVED_KWARGS: Final[tuple[str, ...]] = (
    "classes",
    "style",
    "slots",
    "key",
    "id",
    "tag",
    "attrs",
    "visible",
    "tooltip",
    "debounce",
    "throttle",
    "outlet",
    "loading",
    "autofocus",
)


#: Universal kwargs a component may ALSO declare as its own prop: the
#: socle reads them without taking them away. ``loading``: every trigger
#: has an automatic busy state, and a button draws its own spinner.
SHARED_RESERVED_KWARGS: Final[tuple[str, ...]] = ("loading",)


class _ComponentMeta(type):
    """Collect reactive props + cross-check events at class creation.

    The work is small but absolutely needs to run *once per class*,
    not on every instance — hence a metaclass rather than __init_subclass__
    (which would also work but reads less obviously when paired with
    introspection).
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
    ) -> type:
        cls = super().__new__(mcs, name, bases, namespace)

        # Walk the MRO so subclasses inherit parent props.
        collected: dict[str, ReactivePropDescriptor] = {}
        for base in reversed(cls.__mro__):
            for attr_name, attr in base.__dict__.items():
                if isinstance(attr, ReactivePropDescriptor):
                    collected[attr_name] = attr
        cls.__reactive_props__ = collected  # type: ignore[attr-defined]

        # Walk MRO annotations the same way the prop collection does
        # so subclass overrides win. Each descriptor learns its declared
        # type so future discipline checks (binding_discipline.py) can
        # validate scalar-vs-collection mismatches at __init__ time.
        # ``from __future__ import annotations`` (PEP 563) and PEP 649
        # both make annotations show up as strings on the class — resolve
        # them through ``typing.get_type_hints`` so descriptors carry the
        # actual ``type`` objects (cf. ``state/base.py`` for precedent).
        try:
            annotations: dict[str, Any] = typing.get_type_hints(cls)
        except (NameError, TypeError):
            annotations = {}
            for base in reversed(cls.__mro__):
                annotations.update(getattr(base, "__annotations__", {}) or {})
        for prop_name, descriptor in collected.items():
            ann = annotations.get(prop_name)
            if ann is not None:
                descriptor.declared_type = ann

        # ── Derived TWO_WAY_PROPS + the scope-key map ─────────────────
        # "What the client does with this prop" lives ON the prop
        # (``reactive_prop(writes=, scope_keys=)``), not in a ClassVar to
        # keep in phase. The metaclass derives from it:
        #   - ``TWO_WAY_PROPS`` = the ``writes=True`` props (when at least
        #     one exists; otherwise an explicit ClassVar is respected —
        #     coexistence for the duration of the migration);
        #   - ``__scope_keys__`` = prop → scope keys (default ``(prop,)``,
        #     overridden when the key differs from the name: Tabs value→active).
        writes_props = tuple(n for n, d in collected.items() if getattr(d, "writes", False))
        # UNCONDITIONAL assignment. Two ways of declaring the same fact
        # would go against the charter's principle 4, so a manual
        # declaration raises (below).
        cls.TWO_WAY_PROPS = writes_props  # type: ignore[attr-defined]

        # A hand declaration of either derived ClassVar cannot
        # coexist with the derivation: it is refused at CLASS CREATION,
        # so at import, with the replacement named.
        for _derived, _param in (
            ("TWO_WAY_PROPS", "writes=True"),
            ("AUTONAME_FROM", "names_field=True"),
        ):
            if name != "Component" and _derived in namespace:
                raise ComponentDefinitionError(
                    f"{name} declares ``{_derived}`` by hand. That "
                    f"ClassVar is DERIVED from the props: set ``{_param}`` "
                    f"on the prop concerned (``reactive_prop(...)``) and "
                    f"remove the line. Two places for one fact is the "
                    f"drift the derivation exists to prevent."
                )
        cls.__scope_keys__ = {  # type: ignore[attr-defined]
            n: (d.scope_keys or (n,)) for n, d in collected.items() if getattr(d, "writes", False)
        }

        # ── Derived AUTONAME_FROM ──────────────────────────────────────
        # The third fact to leave the ClassVar for the prop, same pattern
        # as ``writes=`` / ``scope_keys=``. The ClassVar REMAINS the
        # reading surface (``type(self).AUTONAME_FROM``) — only the
        # declaration moves, so no reader and no test has to change.
        naming = tuple(n for n, d in collected.items() if getattr(d, "names_field", False))
        if len(naming) > 1:
            raise ComponentDefinitionError(
                f"{name} : {len(naming)} props portent ``names_field=True`` "
                f"({naming}). A component has only ONE HTML ``name=`` — "
                f"only one prop can name it."
            )
        if naming:
            prop = naming[0]
            # ``names_field`` implies ``writes``: a field whose value
            # the client does not write has no ``name=`` to derive. It is
            # the AUTONAME ⊆ TWO_WAY inclusion the ``test_two_way_props``
            # gate imposed after the fact; here it becomes impossible to
            # violate.
            if not getattr(collected[prop], "writes", False):
                raise ComponentDefinitionError(
                    f"{name}.{prop} carries ``names_field=True`` without "
                    f"``writes=True``. A form field whose value the client "
                    f"does not write has no ``name=`` to derive — add "
                    f"``writes=True``."
                )
            declared = namespace.get("AUTONAME_FROM")
            if declared is not None and declared != prop:
                raise ComponentDefinitionError(
                    f"{name} declares ``AUTONAME_FROM = {declared!r}`` "
                    f"while ``{prop}`` carries ``names_field=True``. The "
                    f"two tell two stories — remove the ClassVar, the "
                    f"declaration lives on the prop."
                )
            cls.AUTONAME_FROM = prop  # type: ignore[attr-defined]

        derive_display_bindings(cls, name, namespace)  # a displayed content binds (R1)
        # Cross-check declared EVENTS vs ``on_<event>`` parameters in
        # ``__init__``. Skip the abstract base itself (it has no
        # EVENTS and a permissive ``**kwargs`` ctor).
        if name != "Component":
            cross_check_events(cls)

        # Wrap ``render()`` so the universal ``visible`` / ``tooltip``
        # modifiers are applied to every component automatically. The
        # wrap is idempotent : if a subclass inherits an already-wrapped
        # render, the marker stops a second wrap. The base Component's
        # own ``render`` skips the wrap (nothing to apply — universals
        # only kick in when set on an instance, and the base is
        # abstract anyway).
        original_render = namespace.get("render")
        if (
            original_render is not None
            and name != "Component"
            and not getattr(original_render, "_bz_universals_wrapped", False)
        ):

            def wrapped_render(self, _orig=original_render):
                return with_carriers(self, finish_render(self, render_in_its_zone(self, _orig)))

            wrapped_render._bz_universals_wrapped = True  # type: ignore[attr-defined]
            cls.render = wrapped_render  # type: ignore[assignment]

        # A Component passed to a parameter that renders it leaves the
        # parent it registered into — cf. ``adopt_owned_arguments``.
        from bretzel.components.base.arguments import adopt_owned_arguments

        adopt_owned_arguments(cls, next(k for k in reversed(cls.__mro__) if isinstance(k, mcs)))
        return cls
