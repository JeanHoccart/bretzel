"""What a component's constructor does with its arguments: components it owns, bindings it accepts."""

from __future__ import annotations

import builtins
import functools
import inspect
import re
import sys
import types
import typing
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError, normalize_attr_name


def reject_attribute_component(
    value: Any, *, owner: str, prop: str, attribute: str | None = None,
) -> None:
    """Refuse a Component on a parameter written into an HTML attribute.

    A ``placeholder``, an ``alt``, an ``aria-label`` carry a string and
    nothing else: a Component there would show as its Python repr. A
    component that writes the attribute itself calls this in its
    ``__init__``; any other parameter that takes a value is refused by
    its constructor (:func:`adopt_owned_arguments`).
    ``attribute`` defaults to ``prop``.
    """
    if value is None or isinstance(value, str):
        return
    # Deferred: ``component`` imports this module.
    from bretzel.components.base.nodes import reject_component

    reject_component(
        value,
        owner=owner,
        prop=prop,
        because=(
            f"it is written into the HTML attribute ``{attribute or prop}``, "
            "and an attribute can only carry a string (the Component would "
            "show there as its Python repr)."
        ),
        instead="Pass the text itself, e.g. ``placeholder=\"Search\"``.",
    )


#: What a parameter does with a Component it receives — read from its
#: annotation, decided once per class.
OWNS, POINTS, REFUSES = "owns", "points", "refuses"


#: ``Component`` as a whole word: ``str | Component | None`` says the
#: parameter RENDERS what it receives. ``Sidebar`` or ``MyComponent``
#: name one component in particular: the parameter POINTS at it.
_NAMES_COMPONENT = re.compile(r"\bComponent\b")


_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


_NAME = re.compile(r"[A-Za-z_][\w.]*")


_UNRESOLVED = object()


def _role_of_type(annotation: Any, component_cls: Any) -> str | None:
    """The role of an EVALUATED annotation (a type, a union, ``Any``)."""
    if annotation is Any or annotation is type(None):
        return REFUSES
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        roles = {_role_of_type(arg, component_cls) for arg in typing.get_args(annotation)}
        for role in (OWNS, POINTS, None):
            if role in roles:
                return role
        return REFUSES
    if isinstance(annotation, type):
        if annotation is component_cls:
            return OWNS
        return POINTS if issubclass(annotation, component_cls) else REFUSES
    return REFUSES if typing.get_origin(annotation) is not None else None


def _resolve(name: str, namespace: dict[str, Any]) -> Any:
    head, *rest = name.split(".")
    found = namespace.get(head, getattr(builtins, head, _UNRESOLVED))
    for part in rest:
        found = getattr(found, part, _UNRESOLVED)
    return found


def component_role(annotation: Any, namespace: dict[str, Any], component_cls: Any) -> str | None:
    """What a parameter does with a Component, read from its annotation.

    - ``OWNS`` — the annotation names ``Component``: the parameter renders
      what it receives (``label: str | Component | None``);
    - ``POINTS`` — it names one component class (``sidebar: Sidebar``):
      it designates a component placed elsewhere;
    - ``REFUSES`` — every name it uses is something else, ``Any``
      included: a value (``value: str``, ``data: list[dict]``,
      ``open: bool | ClientBinding``) has no use for markup;
    - ``None`` — no annotation, or a name that does not resolve here (an
      import under ``TYPE_CHECKING``): no decision, nothing is done.
    """
    if annotation is inspect.Parameter.empty or annotation is None:
        return None
    if not isinstance(annotation, str):
        return _role_of_type(annotation, component_cls)
    if _NAMES_COMPONENT.search(annotation):
        return OWNS
    role = REFUSES
    for name in _NAME.findall(_QUOTED.sub("", annotation)):
        found = _resolve(name, namespace)
        if found is _UNRESOLVED:
            return None
        if isinstance(found, type) and issubclass(found, component_cls):
            role = POINTS
    return role


def _signature(init: Any) -> inspect.Signature:
    """``init``'s signature, its annotations left as text when they do not
    resolve (Python 3.14 without ``from __future__ import annotations``)."""
    try:
        return inspect.signature(init)
    except NameError:
        import annotationlib  # 3.14+: the only place a NameError comes from

        return inspect.signature(init, annotation_format=annotationlib.Format.STRING)


def component_roles(
    cls: Any, component_cls: Any,
) -> tuple[tuple[str, ...], dict[str, tuple[str, str]]]:
    """The positional order of ``cls``'s constructor, and for every
    parameter that decides one: ``(role, annotation as written)``.

    Three sources, the signature first: the constructor's own parameters,
    the reactive props it forwards through ``**kwargs``, and the
    ``NAMED_SLOTS``, which always own their Component.
    """
    init = inspect.unwrap(cls.__init__)
    params = list(_signature(init).parameters.values())[1:]
    positional = tuple(
        p.name for p in params
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    )
    module = vars(sys.modules[cls.__module__]) if cls.__module__ in sys.modules else {}
    roles: dict[str, tuple[str, str]] = {name: (OWNS, "slot") for name in cls.NAMED_SLOTS}
    for name, descriptor in cls.__reactive_props__.items():
        role = component_role(descriptor.declared_type, module, component_cls)
        if role is not None:
            roles[name] = (role, str(descriptor.declared_type))
    for p in params:
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        role = component_role(p.annotation, getattr(init, "__globals__", module), component_cls)
        if role is not None:
            roles[p.name] = (role, str(p.annotation))
    return positional, roles


def owned_parameters(cls: Any) -> frozenset[str]:
    """The parameters of ``cls`` that render the Component they receive."""
    return frozenset(n for n, (role, _) in cls.__component_roles__[1].items() if role == OWNS)


def _refusal(cls: Any, prop: str, annotation: str) -> Exception:
    """The clean refusal of a Component on a parameter that takes a value."""
    descriptor = cls.__reactive_props__.get(prop)
    attribute = normalize_attr_name(prop)
    because = (
        f"it is written into the HTML attribute ``{attribute}``, and an "
        "attribute can only carry a string."
        if descriptor is not None and descriptor.emit_attr else
        f"the parameter is declared ``{annotation}``: it takes a value, not "
        "markup — a Component there would be swallowed, shown as its repr, "
        "or crash further down."
    )
    return ComponentUsageError(
        f"{cls.__name__} does not accept a Component for ``{prop}=`` — "
        f"{because} Pass the value itself. A parameter that renders markup "
        f"says so in its annotation (``str | Component | None``)."
    )


def shown(component: Any, name: str) -> Any:
    """The content to DISPLAY for ``name``: its binding when it is bound —
    hand it to ``emit_text_slot`` / an ``Icon`` and the page follows it —
    else its resolved value.

    A reactive prop keeps the two apart: ``_reactive_values`` holds the
    value resolved for the server render, ``_binding_metadata`` the binding.
    Reading the first alone draws the text FROZEN at its first value."""
    bound = component._binding_metadata.get(name)
    return bound if bound is not None else component._reactive_values.get(name)


def has_content(value: Any) -> bool:
    """``if value:`` for a displayed content — a binding counts as present.

    A ``ClientBinding`` refuses a Python truth test on purpose
    (``ReactivityError``: ``if state.flag:`` in a page would freeze the
    server's value), so the ``if label:`` guarding a wrapper crashed the
    day a label became bindable (checkbox, radio, switch)."""
    from bretzel.state.scopes.client import ClientBinding

    return True if isinstance(value, ClientBinding) else bool(value)


def is_displayed_content(annotation: Any) -> bool:
    """``str | Component`` in the type: the parameter SHOWS something — a
    text or an icon — on the page. The convention the text-slot gate already
    holds (``test_text_slot_contract_universal``: a displayed text takes a
    Component, or refuses out loud), read here as a declaration."""
    names = {part.split(".")[-1].strip("'<>) ")
             for part in re.split(r"[|\[\],\s]+", str(annotation)) if part}
    return "str" in names and "Component" in names


def derive_display_bindings(cls: Any, name: str, namespace: dict) -> None:
    """Every DISPLAYED CONTENT is bindable — derived, never written.

    The fourth fact a class does not write by hand, after
    ``TWO_WAY_PROPS`` (``writes=``), ``AUTONAME_FROM`` (``names_field=``)
    and the scope keys. A parameter annotated ``str | Component`` — a
    label, a title, a description, an empty state's words, an icon —
    follows a client state on EVERY component: one way of doing things
    (the thesis), and nothing left for the next component to forget.

    It is derived from the annotation, not from the NAME (``icon`` /
    ``icon_left`` / ``icon_right``): a name is not a meaning (``empty_icon``
    IS an icon, ``ui.icon(name=)`` too).

    Whether the binding then reaches the HTML is held by
    ``tests/audit/test_binding_completeness.py``; that a displayed text is
    annotated so, by ``test_text_slot_contract_universal``.
    """
    from bretzel.components.base.attrs import ComponentDefinitionError

    if name == "Component":
        return
    from bretzel.components.base.metaclass import RESERVED_KWARGS

    params = inspect.signature(cls.__init__).parameters
    # Not a universal modifier a component re-declares (``tooltip=`` on a
    # toggle button): the socle owns those, on every component.
    shown = tuple(p for p, prm in params.items()
                  if p not in RESERVED_KWARGS and is_displayed_content(prm.annotation))
    written = [p for p in namespace.get("BINDABLE_PROPS", ()) if p in shown]
    if written:
        raise ComponentDefinitionError(
            f"{name} lists {written} in ``BINDABLE_PROPS``. A displayed "
            f"content (annotated ``str | Component``) is bindable by "
            f"construction — the metaclass adds it. Remove it from the "
            f"ClassVar: two places for one fact is the drift the derivation "
            f"exists to prevent."
        )
    # Kept apart too: a UNIVERSAL capability is shown once (like
    # ``visible=``), so the playground's « Client playground » card is due
    # for the props a component CHOOSES to bind, not for these.
    cls.__displayed_props__ = shown
    if shown:
        cls.BINDABLE_PROPS = tuple(dict.fromkeys((*cls.BINDABLE_PROPS, *shown)))


def refuse_an_undeclared_binding(cls: Any, name: str, value: Any) -> None:
    """A ``ClientBinding`` (or ``ClientExpression``) on a parameter that is
    not in ``BINDABLE_PROPS``: raise, at construction.

    **One place, every argument.** The base constructor sees only what
    reaches it — reactive props and named slots. A parameter a component
    keeps for itself (``self._label``, a text slot rendered through
    ``emit_text_slot``, an icon shortcut) never gets there: judged there,
    it would wire a binding live without declaring it, so ``bretzel
    describe`` would not show it, or drop it without a word (R6). The
    outermost constructor (``owning_init``) sees every argument by name,
    so the rule is held here, once: ``BINDABLE_PROPS`` is the ONE
    declaration — what ``describe`` prints is what the socle accepts.

    Not judged: the universal modifiers (``RESERVED_KWARGS`` — ``visible=``
    takes a binding on every component, the socle handles them), and the
    ``on_<event>`` handlers, which take a client expression by R3.
    """
    error = undeclared_binding(cls, name, value)
    if error is not None:
        raise error


def undeclared_binding(cls: Any, name: str, value: Any) -> ComponentUsageError | None:
    """The refusal :func:`refuse_an_undeclared_binding` raises, or ``None``
    — returned rather than raised so ``owning_init`` can let the
    component's own refusal speak first."""
    from bretzel.components.base.metaclass import RESERVED_KWARGS
    from bretzel.state.scopes.client import ClientBinding

    if (not isinstance(value, ClientBinding) or name in RESERVED_KWARGS
            or name.startswith("on_") or name in cls.BINDABLE_PROPS):
        return None
    bindable = sorted(cls.BINDABLE_PROPS) or (
        "(none — this component does not expose any bindable prop)")
    return ComponentUsageError(
        f"{cls.__name__}.{name} is not bindable. "
        f"Bindable props on {cls.__name__} : {bindable}. "
        f"To make {name} change at runtime, mutate the value on the server "
        f"and rely on @refreshable to re-render — the framework rebuilds "
        f"the component with the new value, no client-side binding needed."
    )


def adopt_owned_arguments(cls: Any, component_cls: Any) -> None:
    """Give ``cls``'s constructor the slot contract, read from its
    annotations: a Component passed to a parameter that RENDERS it leaves
    the parent it registered into; one passed to a parameter that takes a
    VALUE is refused; one passed to a parameter that POINTS at it stays
    where it is.

    The reason for the first: a Component registers with the open ``with``
    block as soon as it is built, so ``ui.checkbox(label=ui.text("Maths"))``
    builds the text INTO the page first, then hands it to the box — which
    renders it too. Without this, every slot would have to undo that by hand
    in its ``__init__``, and each forgotten one would render twice.

    The refusal comes AFTER the constructor: a component that refuses with
    its own reason (``code.text`` is a source to highlight) keeps its
    sentence; one that crashes obscurely, or swallows the Component in
    silence, gets this clean one instead.

    Done once per class, the app's own components included. The wrapper
    keeps the signature (``functools.wraps``: ``help()``, the editor and
    ``bretzel describe`` still read the real parameters) and acts only in
    the OUTERMOST constructor; the ``super().__init__`` chain passes
    straight through.
    """
    cls.__component_roles__ = component_roles(cls, component_cls)
    init = cls.__dict__.get("__init__")
    if init is None:
        return
    detach = component_cls._detach_from_parent

    @functools.wraps(init)
    def owning_init(self: Any, *args: Any, **kwargs: Any) -> None:
        if type(self).__init__ is not owning_init:
            init(self, *args, **kwargs)
            return
        positional, roles = type(self).__component_roles__
        refused: tuple[str, str] | None = None
        unbound: ComponentUsageError | None = None
        for name, value in (*zip(positional, args, strict=False), *kwargs.items()):
            if unbound is None:
                unbound = undeclared_binding(type(self), name, value)
            if isinstance(value, component_cls):
                role, annotation = roles.get(name, (None, ""))
                if role == OWNS:
                    detach(value)
                elif role == REFUSES and refused is None:
                    refused = (name, annotation)
        if refused is None and unbound is None:
            init(self, *args, **kwargs)
            return
        # Both refusals come AFTER the constructor, for the same reason: a
        # component that refuses with its own sentence (``ui.html`` names
        # its alternative) keeps it; one that crashes obscurely, or keeps
        # quiet, gets the socle's clean one.
        error = unbound or _refusal(type(self), *refused)
        try:
            init(self, *args, **kwargs)
        except ComponentUsageError:
            raise
        except Exception as exc:
            raise error from exc
        raise error

    cls.__init__ = owning_init


def reject_sealed(kwargs: dict[str, Any], cls: type) -> None:
    """A SEALED prop passed at the call: we say so, with a sentence.

    A sealed prop is declared on the class and deliberately REFUSED at the
    call — a ``VStack``'s axis is its identity, and a ``Radio``'s
    ``option_value`` is fed by its positional ``value``.
    ``bretzel.introspect`` subtracts them from the card, so they are
    announced nowhere; what remained was to answer properly whoever writes
    them anyway.

    ⚠️ Without this guard, the collision reaches ``super().__init__`` and
    renders ::

        TypeError: Component.__init__() got multiple values for
        keyword argument 'option_value'

    — which does not name the component, does not say the prop is sealed,
    and reads like a framework bug.

    The refusal must stay IN the subclass, before its ``super().__init__``:
    the collision is raised by Python when building the call, so the base
    layer never sees it.

    ``SEALED_REASONS`` lets a subclass seal something other than the axis
    (``Pane`` seals ``wrap``) without inheriting a wrong message.
    """
    reasons = getattr(cls, "SEALED_REASONS", {})
    for name in getattr(cls, "SEALED_PROPS", ()):
        if name in kwargs:
            raise ComponentUsageError(
                reasons.get(name)
                or f"{cls.__name__} has a fixed axis — pass no ``{name}``. "
                f"Use the other shortcut, or ``ui.flex(direction=…)`` for "
                f"a runtime-chosen axis."
            )
