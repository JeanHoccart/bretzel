"""Unit tests for :class:`bretzel.components.base.component.Component`."""

from __future__ import annotations

from typing import Any

import pytest

from bretzel.components.base import (
    Component,
    ComponentDefinitionError,
    ComponentUsageError,
    HandlerError,
    reactive_prop,
)
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.core.tree import Element, TextNode
from bretzel.runtime.protocol import BZ_ID_ATTR
from bretzel.state.scopes.client import ClientBinding
from bretzel.state.scopes.server import _BoundStr


class _NamedInput(Component):
    """Minimal AUTONAME_FROM component to exercise ``_derive_field_name``."""

    THEME_KEY = "_named_input"
    DEFAULT_TAG = "input"
    BINDABLE_PROPS = ("value",)

    # ``AUTONAME_FROM`` n'est plus un ClassVar écrit à la main : il est
    # DÉRIVÉ de ``names_field=True``, et le déclarer lève désormais. Même
    # patron que ``writes=`` / ``scope_keys=``.
    #
    # ``names_field`` implique ``writes`` (vérifié par la métaclasse), et
    # les deux impliquent l'appartenance à ``BINDABLE_PROPS`` : c'est
    # l'inclusion ``AUTONAME ⊆ TWO_WAY ⊆ BINDABLE``, qu'une gate imposait
    # après coup et que le socle rend maintenant impossible à violer.
    value: str = reactive_prop(default="", writes=True, names_field=True)


class TestDeriveFieldName:
    """The single autoname derivation the base + ~12 carrier components share."""

    def test_binding_source(self) -> None:
        binding = ClientBinding(
            class_name="Form", instance_key="default",
            field_name="email", value="",
        )
        with render_isolated():
            c = _NamedInput(value=binding)
        assert c._derive_field_name() == "email"

    def test_server_stamp_source(self) -> None:
        with render_isolated():
            c = _NamedInput(value=_BoundStr("hi", "greeting"))
        assert c._derive_field_name() == "greeting"

    def test_none_when_plain_literal(self) -> None:
        with render_isolated():
            c = _NamedInput(value="plain")
        assert c._derive_field_name() is None


# Module-level handler — addressable via ``module::qualname``.
def _module_handler() -> None:
    pass


# ───────────────────────────────────────────────────────────────────────────
# Basic concrete subclass used across the suite
# ───────────────────────────────────────────────────────────────────────────


class _Btn(Component):
    THEME_KEY = "_btn"
    DEFAULT_TAG = "button"
    EVENTS = ("click", "focus")
    NAMED_SLOTS = ("icon",)
    # Obligatoire depuis le 2026-07-29 : le sentinel ``BINDABLE_PROPS = None``
    # (« pas encore audité, check sauté ») a été retiré du socle, le défaut
    # est le tuple vide. Cette fixture exerce le dispatch d'une
    # ``ClientBinding`` sur ``disabled`` — sous le contrat d'aujourd'hui, un
    # vrai composant doit donc le déclarer. La fixture le fait maintenant
    # aussi : elle teste ce que le framework autorise, pas un mode mort.
    BINDABLE_PROPS = ("disabled",)

    color: str = reactive_prop(default="primary")
    disabled: bool = reactive_prop(default=False)

    def __init__(
        self,
        label: str = "",
        *,
        on_click: Any = None,
        on_focus: Any = None,
        **kwargs: Any,
    ) -> None:
        # Component authors MUST forward ``on_*`` kwargs to super so the
        # base class can route them through the event bucket. Naming the
        # parameters in the signature is purely for IDE / mypy.
        super().__init__(on_click=on_click, on_focus=on_focus, **kwargs)
        self._label = label

    def render(self) -> Element:
        attrs = self.emit_attrs()
        # Append a class only if there's one to set.
        return Element(tag="button", attrs=attrs, children=(TextNode(self._label),))


class _LeafIcon(Component):
    """Leaf component used to test IS_CONTAINER=False guard rails."""

    IS_CONTAINER = False
    DEFAULT_TAG = "span"
    THEME_KEY = "_leaf_icon"


# ───────────────────────────────────────────────────────────────────────────
# Construction / context registration
# ───────────────────────────────────────────────────────────────────────────


class TestConstruction:
    def test_registers_in_root_children(self) -> None:
        with render_isolated() as ctx:
            btn = _Btn("Save")
            assert btn in ctx.root_children

    def test_id_uses_kind_and_parent(self) -> None:
        with render_isolated():
            btn = _Btn("Save")
        # ``THEME_KEY`` ('_btn') is the kind segment.
        assert "_btn" in btn.id

    def test_with_block_collects_children(self) -> None:
        with render_isolated() as ctx:
            with _Btn("Outer") as outer:
                inner = _Btn("Inner")
            # Outer landed in root, inner landed in outer.
            assert outer in ctx.root_children
            assert inner in outer._children
            assert inner not in ctx.root_children

    def test_explicit_key_threads_into_id(self) -> None:
        with render_isolated():
            a = _Btn("A", key="alpha")
        assert a.id.endswith("alpha")

    def test_two_anonymous_siblings_get_distinct_ids(self) -> None:
        with render_isolated():
            a = _Btn()
            b = _Btn()
        assert a.id != b.id

    def test_explicit_id_kwarg_wins(self) -> None:
        with render_isolated():
            btn = _Btn(id="custom")
        assert btn.id == "custom"

    def test_explicit_id_kwarg_reaches_the_dom(self) -> None:
        """User-supplied ``id=`` must emit ``id="..."`` on the rendered
        element even when ``_needs_identity()`` would otherwise skip the
        framework identity triplet (no bindings, no events, no raw bz-*).
        """
        with render_isolated():
            btn = _Btn(id="my-explicit")
        attrs = btn.emit_attrs()
        assert attrs["id"] == "my-explicit"
        # No reactive plumbing → no bz-* overhead.
        assert BZ_ID_ATTR not in attrs

    def test_custom_tag(self) -> None:
        with render_isolated():
            btn = _Btn(tag="a")
        assert btn._tag == "a"

    def test_classes_kwarg_stored(self) -> None:
        with render_isolated():
            btn = _Btn(classes="extra")
        assert btn._classes == "extra"


# ───────────────────────────────────────────────────────────────────────────
# Reactive prop dispatch (static / binding / alpine)
# ───────────────────────────────────────────────────────────────────────────


class TestReactivePropDispatch:
    def test_static_value(self) -> None:
        with render_isolated():
            btn = _Btn(color="primary", disabled=True)
        attrs = btn.emit_attrs()
        assert attrs["color"] == "primary"
        assert attrs["disabled"] is True

    def test_false_static_is_dropped(self) -> None:
        with render_isolated():
            btn = _Btn(disabled=False)
        # ``False`` shouldn't surface as ``disabled=""`` — the runtime
        # treats absence as "not disabled".
        assert "disabled" not in btn.emit_attrs()

    def test_alpine_string_emits_bz_attr(self) -> None:
        with render_isolated():
            btn = _Btn(disabled="$bz.state.cart.default.empty")
        attrs = btn.emit_attrs()
        assert "bz-attr:disabled" in attrs
        assert attrs["bz-attr:disabled"] == "$bz.state.cart.default.empty"
        # The static slot stays empty so we don't double-emit.
        assert "disabled" not in attrs

    def test_client_binding_emits_bz_attr(self) -> None:
        binding = ClientBinding(
            class_name="cart",
            instance_key="default",
            field_name="empty",
            value=False,
        )
        with render_isolated():
            btn = _Btn(disabled=binding)
        attrs = btn.emit_attrs()
        assert "bz-attr:disabled" in attrs
        assert attrs["bz-attr:disabled"] == "$bz.state.cart.default.empty"

    def test_default_used_when_kwarg_omitted(self) -> None:
        with render_isolated():
            btn = _Btn()
        # Reactive defaults still flow into emit_attrs.
        assert btn.emit_attrs().get("color") == "primary"

    def test_bind_x_model_swaps_bz_attr_for_model(self) -> None:
        binding = ClientBinding(
            class_name="draft",
            instance_key="default",
            field_name="email",
            value="",
        )
        with render_isolated():
            btn = _Btn(disabled=binding)
        attrs = btn.emit_attrs()
        # Sanity : emit_attrs put the one-way bz-attr directive in.
        assert "bz-attr:disabled" in attrs

        returned = btn._bind_x_model(attrs, prop="disabled")
        assert returned is binding
        assert "bz-attr:disabled" not in attrs
        assert attrs["bz-model"] == "$bz.state.draft.default.email"

    def test_bind_x_model_no_op_when_no_binding(self) -> None:
        with render_isolated():
            btn = _Btn(disabled=True)
        attrs = btn.emit_attrs()
        returned = btn._bind_x_model(attrs, prop="disabled")
        assert returned is None
        assert "bz-model" not in attrs
        # Literal stays unchanged.
        assert attrs.get("disabled") is True

    def test_bind_x_model_explicit_binding_override(self) -> None:
        # Composite-input case : Radio inherits the binding from its
        # enclosing RadioGroup ; the binding is NOT on Radio's own
        # _binding_metadata. The ``binding=`` kwarg lets the child
        # plumb its parent's binding through the same helper.
        external = ClientBinding(
            class_name="form",
            instance_key="default",
            field_name="colour",
            value="red",
        )
        with render_isolated():
            btn = _Btn()  # no binding on btn itself
        attrs = btn.emit_attrs()
        returned = btn._bind_x_model(attrs, prop="value", binding=external)
        assert returned is external
        assert attrs["bz-model"] == "$bz.state.form.default.colour"

    def test_bind_x_model_no_op_when_literal_binding_in_reactive_values_only(
        self,
    ) -> None:
        # Regression : the bug we're fixing was reading
        # ``_reactive_values[prop]`` and ``isinstance(..., ClientBinding)``
        # — which is always False, since the split stores the
        # underlying SSR value there. Confirm the helper doesn't fall
        # for the same trap : a literal value (even one happening to
        # match a binding shape) must not produce x-model.
        with render_isolated():
            btn = _Btn(disabled=False)
        attrs = btn.emit_attrs()
        assert btn._bind_x_model(attrs, prop="disabled") is None
        assert "bz-model" not in attrs


# ───────────────────────────────────────────────────────────────────────────
# Events
# ───────────────────────────────────────────────────────────────────────────


class TestEvents:
    def test_callable_routes_to_hx_post_action(self) -> None:
        with render_isolated() as ctx:
            btn = _Btn(on_click=_module_handler)
        attrs = btn.emit_attrs()
        # V3 wire : full HTMX attribute set targeting the sink.
        assert attrs["hx-trigger"] == "click"
        assert attrs["hx-target"] == "#bz-sink"
        assert attrs["hx-swap"] == "innerHTML"
        assert attrs["hx-post"].startswith("/_bretzel/action/")
        # The same id was registered on the active context.
        action_id = attrs["hx-post"].removeprefix("/_bretzel/action/")
        assert action_id in ctx.action_registry
        # Le rig isolé SIGNE, depuis le 2026-08-28. Cette ligne assertait
        # l'inverse — « pas de clé d'app, donc pas de signature » —, ce qui
        # décrivait un défaut plutôt qu'une propriété : le bridge refuse
        # tout POST sans porteur de signature depuis ``ad3b7f33``, donc un
        # montage navigateur bâti sur ce rig produisait des boutons qu'un
        # clic ne pouvait pas faire partir.
        assert attrs["data-bz-sig"]

    def test_string_routes_to_bz_on(self) -> None:
        with render_isolated():
            btn = _Btn(on_click="$bz.toggle('menu')")
        attrs = btn.emit_attrs()
        assert attrs["bz-on:click"] == "$bz.toggle('menu')"
        assert "hx-post" not in attrs

    def test_two_server_handlers_on_one_element_rejected(self) -> None:
        with render_isolated(), pytest.raises(HandlerError, match="ONE hx-post"):
            _Btn(on_click=_module_handler, on_focus=_module_handler)

    def test_lambda_rejected(self) -> None:
        with render_isolated(), pytest.raises(HandlerError, match="Lambda"):
            _Btn(on_click=lambda: None).emit_attrs()

    def test_unknown_event_rejected_at_init(self) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError, match="on_change"):
            _Btn(on_change=_module_handler)

    def test_event_in_init_but_not_in_events_list_raises_at_class_def(self) -> None:
        # Class definition with a mismatched EVENTS / __init__ pair.
        with pytest.raises(ComponentDefinitionError):

            class Bad(Component):
                EVENTS = ("click", "focus")

                def __init__(self, *, on_click=None, **kwargs: Any) -> None:
                    # Missing ``on_focus`` → cross-check fires.
                    super().__init__(**kwargs)


# ───────────────────────────────────────────────────────────────────────────
# Slots
# ───────────────────────────────────────────────────────────────────────────


class TestSlots:
    def test_named_slot_accepted(self) -> None:
        with render_isolated():
            icon = _LeafIcon()
            btn = _Btn(icon=icon)
        assert btn._slot_components["icon"] is icon

    def test_undeclared_slot_rejected(self) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError, match="trailing"):
            _Btn(trailing=_LeafIcon())  # ``trailing`` not in NAMED_SLOTS


# ───────────────────────────────────────────────────────────────────────────
# Raw HTML / Alpine attrs
# ───────────────────────────────────────────────────────────────────────────


class TestRawAttrs:
    def test_aria_label_normalised(self) -> None:
        with render_isolated():
            btn = _Btn(aria_label="Save")
        attrs = btn.emit_attrs()
        assert attrs["aria-label"] == "Save"

    def test_data_attr_normalised(self) -> None:
        with render_isolated():
            btn = _Btn(data_testid="save-btn")
        assert btn.emit_attrs()["data-testid"] == "save-btn"

    def test_raw_htmx_passthrough(self) -> None:
        with render_isolated():
            btn = _Btn(**{"hx-get": "/rows"})
        attrs = btn.emit_attrs()
        assert attrs["hx-get"] == "/rows"

    def test_dead_alpine_prefix_raises_on_both_entry_paths(self) -> None:
        """``**kwargs`` ET ``attrs={...}``.

        ``attrs=`` court-circuite ``split_kwargs`` : sans le contrôle posé
        dans ``Component.__init__``, un ``@click`` refusé par la première
        voie passerait en silence par la seconde. Un attribut Alpine est
        aussi inerte par l'une que par l'autre.
        """
        from bretzel.components.base.attrs import ComponentUsageError

        with pytest.raises(ComponentUsageError, match="Alpine"), render_isolated():
            _Btn(**{":data-active": "x === 1"})

        with pytest.raises(ComponentUsageError, match="Alpine"), render_isolated():
            _Btn(attrs={"@click": "alert(1)"})


class TestAttrsEscapeHatch:
    """Tests for ``attrs={"data-x": "y", ...}`` — the universal kwarg
    that lets callers pass arbitrary HTML attributes without going
    through the framework's reactive_prop / slot / event plumbing."""

    def test_attrs_dict_is_unpacked_into_dom_attrs(self) -> None:
        with render_isolated():
            btn = _Btn(attrs={"data-testid": "save", "aria-describedby": "h1"})
        out = btn.emit_attrs()
        assert out["data-testid"] == "save"
        assert out["aria-describedby"] == "h1"
        # Critical : the dict must NOT land as a literal "attrs" key.
        assert "attrs" not in out

    def test_attrs_keys_normalised_to_dash_form(self) -> None:
        with render_isolated():
            btn = _Btn(attrs={"data_testid": "x"})
        out = btn.emit_attrs()
        assert out["data-testid"] == "x"
        assert "data_testid" not in out

    def test_attrs_none_is_a_noop(self) -> None:
        with render_isolated():
            btn = _Btn(attrs=None)
        out = btn.emit_attrs()
        assert "attrs" not in out

    def test_attrs_empty_dict_is_a_noop(self) -> None:
        with render_isolated():
            btn = _Btn(attrs={})
        out = btn.emit_attrs()
        assert "attrs" not in out

    def test_attrs_non_dict_raises(self) -> None:
        with render_isolated(), pytest.raises(
            ComponentUsageError, match="expects a dict"
        ):
            _Btn(attrs="data-testid=save")

    def test_attrs_combines_with_individual_data_kwargs(self) -> None:
        """The two surfaces co-exist : individual kwargs land in
        ``raw_html`` via the catch-all branch, ``attrs={...}`` lands in
        the same bag — both reach the DOM."""
        with render_isolated():
            btn = _Btn(data_role="primary",
                       attrs={"data-testid": "save"})
        out = btn.emit_attrs()
        assert out["data-role"] == "primary"
        assert out["data-testid"] == "save"


# ───────────────────────────────────────────────────────────────────────────
# Render — default behaviour + framework attrs
# ───────────────────────────────────────────────────────────────────────────


def _module_click() -> None:
    """Module-level handler — Mode A requires ``module::qualname``
    addressability, so closures are rejected upstream."""


class TestRender:
    def test_default_render_carries_framework_attrs_when_eventful(
        self,
    ) -> None:
        # A click handler triggers the conditional identity emission.
        # V3 : ``id`` + ``bz-id`` only — no ``bz-version`` (the scope
        # store keyed by bz-id makes morph version-guards unnecessary).
        with render_isolated():
            btn = _Btn("Save", on_click=_module_click)
        node = btn.render()
        assert isinstance(node, Element)
        assert BZ_ID_ATTR in node.attrs
        assert "bz-version" not in node.attrs
        assert node.attrs["id"] == btn.id

    def test_default_render_skips_framework_attrs_for_static(self) -> None:
        # No handler, no reactive binding → no need for identity ;
        # the DOM stays clean (the v1 rule, ported to v2).
        with render_isolated():
            btn = _Btn("Save")
        node = btn.render()
        assert isinstance(node, Element)
        assert BZ_ID_ATTR not in node.attrs
        assert "id" not in node.attrs

    def test_render_serialises(self) -> None:
        with render_isolated():
            btn = _Btn("Save")
        out = serialize(btn.render())
        assert "<button" in out
        assert ">Save<" in out


# ───────────────────────────────────────────────────────────────────────────
# Leaf components — IS_CONTAINER=False
# ───────────────────────────────────────────────────────────────────────────


class TestLeafComponents:
    def test_with_block_raises(self) -> None:
        with render_isolated():
            leaf = _LeafIcon()
            with pytest.raises(TypeError, match="leaf"), leaf:
                pass

    def test_add_child_rejected(self) -> None:
        with render_isolated():
            leaf = _LeafIcon()
            child = _LeafIcon()
            with pytest.raises(TypeError, match="leaf"):
                leaf.add_child(child)


# ───────────────────────────────────────────────────────────────────────────
# Idempotence — same construction → same render output
# ───────────────────────────────────────────────────────────────────────────


def test_render_idempotent() -> None:
    with render_isolated():
        btn = _Btn("Save", color="primary")
    a = btn.render()
    b = btn.render()
    # Same Element value (frozen dataclass equality).
    assert a == b


def test_is_rendering_resets_after_render() -> None:
    """Regression — ``ctx.is_rendering`` MUST be back to False after a render.

    Without proper reset, a component constructed after a first render
    would think it's a sub-component (skip parent_stack registration),
    silently breaking the render tree on the second pass.
    """
    with render_isolated() as ctx:
        first = _Btn("First")
        first.render()
        assert ctx.is_rendering is False
        second = _Btn("Second")
        assert second in ctx.root_children
