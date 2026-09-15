"""``Radio`` + ``RadioGroup`` — single-choice input cluster.

Composition pattern : children ``Radio`` instances live inside a
``RadioGroup`` ``with`` block. The group provides the ``name=`` and
``value=`` (currently selected) ; each radio reads them at render
time and emits the matching ``<input type="radio" name="..." …>``
plus a styled fake-circle + dot overlay (same idiom as
checkbox / switch).

Two-way bind via ``value=state.field`` on the GROUP — the radio
children all wire ``bz-model`` to that path. Native browser semantics
(only one radio in a group can be checked) carry through.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import reject_sealed
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.inputs.radio.theme import (
    RADIO_GROUP_THEME,
    RADIO_THEME,
)
from bretzel.core.tree import Element


class RadioGroup(Component):
    """Container for a cluster of ``Radio`` items. Owns the ``name``
    and the bound ``value``."""

    THEME: ClassVar[dict[str, Any]] = RADIO_GROUP_THEME
    THEME_KEY: ClassVar[str] = "radio_group"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set",)
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, emit_attr=False, writes=True, names_field=True)
    direction: str = reactive_prop(default="col", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    # Pas de ``steps=`` ici : le groupe n'a pas de table à lui, et
    # celle de l'enfant ne se lit qu'À TRAVERS SA RÉSOLUTION (un
    # ``Theme(components={"radio": …})`` de l'app la remplace). C'est
    # l'enfant qui refuse la taille EFFECTIVE, au rendu — cf.
    # ``Radio.render``.
    size: str = reactive_prop(default="md", emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        name: str | None = None,
        value: Any = None,
        direction: str | None = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            name=name, value=value, direction=direction,
            color=color, size=size, disabled=disabled,
            required=required,
            on_change=on_change,
            **kwargs,
        )

    # ── Imperative write-only API ─────────────────────────────────────
    #
    # Only ``.set(value)`` — RadioGroup is one-of-N, so ``.clear()``
    # (deselect-all) has no use case and ``.focus()`` / ``.blur()`` have
    # no single target. Write-through when ``value=`` carries a binding ;
    # else DOM dispatch caught by the wrapper's ``bz-on:bz-set``. Cf.
    # `imperative-api.md`.

    def set(self, value: Any) -> str:
        return self._value_command(value)


    def render(self) -> Element:
        theme = self._resolved_theme()
        direction = self._reactive_values.get("direction") or "col"
        direction_class = theme.get("directions", {}).get(direction, "")
        # ``classes=`` posé sur le vrai root par le wrap métaclasse
        # ``_apply_universal_modifiers`` — pas ici (sinon doublon). Gardé
        # par test_no_manual_user_class_append.py.
        root_class = " ".join(
            p
            for p in (
                theme.get("slots", {}).get("root", ""),
                direction_class,
            )
            if p
        )
        attrs = self.emit_attrs()
        attrs["class"] = root_class
        # Server ``on_change`` lands on THIS group ``<div>`` (the
        # group-level event), but the picked value lives on a child
        # ``<input type="radio">`` — and only the checked one serialises.
        # A ``<div>`` has no form value of its own and htmx does NOT walk
        # descendants by default, so without this the POST carries an
        # EMPTY form and ``on_change(value=...)`` never sees the pick
        # (the bound value still rides as namespaced signal state, but
        # that's consumed as state-sync, not handler kwargs). Pull the
        # checked radio into the request via ``hx-include`` scoped to this
        # group's id. Works for BOTH bound (autoname ``name="value"``) and
        # unbound (explicit ``name=``) groups. (cf. traps.md § RadioGroup
        # on_change value vide.)
        if "hx-post" in attrs:
            group_id = attrs.get("id")
            if group_id:
                attrs["hx-include"] = (
                    f"#{group_id} input[type=\"radio\"]"
                )
        # role + aria-required for screen readers : the cluster is the
        # actual semantic radiogroup, not the individual <input>s.
        attrs.setdefault("role", "radiogroup")
        if self._reactive_values.get("required"):
            attrs.setdefault("aria-required", "true")
        # Imperative-API listener — catches ``radio_group.set(value)``
        # when no binding is in play. Iterate the child radios, flip
        # ``.checked`` to match the payload, then fire a synthetic
        # ``change`` on the selected one so ``on_change=`` handlers run
        # (and ``bz-model`` syncs in the binding case). Cf. `imperative-api.md`.
        attrs["bz-on:bz-set"] = (
            "$el.querySelectorAll('input[type=\"radio\"]').forEach("
            "r => { r.checked = (r.value === String($event.detail.value)); "
            "if (r.checked) r.dispatchEvent("
            "new Event('change', {bubbles: true})); })"
        )
        # Effective form name for the child radios : an explicit ``name=``
        # (cosmetic, in ``_reactive_values``) OR the autoname derived by
        # ``emit_attrs`` from a ``value=`` binding (lands in ``attrs``).
        # The radios read this — without it a BOUND group's radios emit no
        # ``name`` at all, so they never serialise and ``on_change`` gets
        # an empty form (the value only rides as namespaced signal state).
        self._radio_name = (
            self._reactive_values.get("name") or attrs.get("name")
        )
        return Element(
            tag=self._tag,
            attrs=attrs,
            children=self._render_children(),
        )


class Radio(Component):
    """One choice inside a :class:`RadioGroup`. Inherits ``name``,
    ``value`` (binding), ``color``, ``size`` from the group's
    reactive props at render time — explicit kwargs on the radio
    override per-item if needed."""

    THEME: ClassVar[dict[str, Any]] = RADIO_THEME
    THEME_KEY: ClassVar[str] = "radio"
    DEFAULT_TAG: ClassVar[str] = "label"
    IS_CONTAINER: ClassVar[bool] = False
    # An individual Radio item inherits the binding from the group ;
    # the only per-item bindable is ``disabled`` (rare but legit
    # for "this option locked, others available" patterns).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled",)
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    # The radio's own ``value`` (the option's value, not the bound
    # value) — kept distinct from the group's ``value=binding``.
    option_value: str = reactive_prop(default="", emit_attr=False)
    # Nourrie depuis le ``value`` positionnel de l'option. La passer
    # explicitement est refusé par ``reject_sealed``, appelé en tête
    # de ``__init__`` — il FAUT que ce soit là, avant le
    # ``super().__init__`` : la collision de kwargs est levée par
    # Python au moment de construire l'appel, donc le socle ne la
    # voit jamais.
    #
    # ⚠️ Ce commentaire disait « produit un multiple values » et
    # s'en contentait, jusqu'au 2026-09-04. C'était décrire un
    # message illisible au lieu de le réparer — rien n'aurait
    # rappelé d'y revenir.
    SEALED_PROPS: ClassVar[tuple[str, ...]] = ("option_value",)
    #: Le message du refus. Sans lui, le défaut de ``reject_sealed``
    #: parle d'AXE — vrai pour une pile, faux ici.
    SEALED_REASONS: ClassVar[dict[str, str]] = {
        "option_value": (
            "Radio(option_value=…) : ce prop est alimenté par le "
            "``value`` positionnel de l'option — écrivez "
            "``ui.radio(\"ma-valeur\")``. Le passer en plus produirait "
            "deux valeurs pour le même champ, ce qui est une "
            "ambiguïté, pas un raccourci."
        ),
    }
    name: str | None = reactive_prop(default=None)
    color: str | None = reactive_prop(default=None, emit_attr=False)
    # ``None`` = hériter du groupe, donc le refus générique ne peut pas
    # lire cette table : c'est le DÉFAUT qui sert d'ancre pour savoir
    # lequel des deux niveaux d'une table imbriquée porte les paliers.
    # La taille effective est donc refusée au rendu — cf. ``render``.
    size: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False)
    required: bool = reactive_prop(default=False)

    def __init__(
        self,
        value: str = "",
        *,
        label: str | None = None,
        name: str | None = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_sealed(kwargs, type(self))
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        # ``option_value`` (le ``value`` positionnel de l'option) est toujours
        # transmis — ce n'est pas une garde None.
        super().__init__(
            option_value=value,
            name=name, color=color, size=size,
            disabled=disabled, required=required,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )
        # ``adopt_slot`` + ``emit_text_slot`` sont un COUPLE (cf. le docstring
        # d'emit_text_slot) : le 1er détache le Component (sinon rendu 2×), le
        # 2nd le REND (sinon il file dans TextNode() qui attend une string →
        # `'Text' object has no attribute 'replace'` au serialize). Faire l'un
        # sans l'autre échange un bug contre un autre.
        self._label = Component.adopt_slot(label)
        # Capture the enclosing RadioGroup at construction time : the
        # ``with RadioGroup(...) as rg`` block is still active here, so
        # the group is on ``parent_stack``. By render time the ``with``
        # has exited and the stack lookup would return None.
        self._group: RadioGroup | None = self._lookup_group()

    def render(self) -> Element:
        # Inherit name / size / disabled / value-binding from the
        # enclosing RadioGroup captured at construction time.
        #
        # ``color`` n'est PAS dans cette liste, et ce n'est pas un oubli :
        # le groupe porte la classe-pont ``bz-c-<couleur>`` sur sa racine,
        # et les onze paliers descendent en CSS sur tout le sous-arbre. La
        # relire ici donnait une variable que personne n'utilisait —
        # supprimée le 2026-09-07, vérifié par rendu : un groupe
        # ``color="warning"`` rend bien ``bz-c-warning`` autour de ses
        # radios.
        group = self._group
        size_key = self._reactive_values.get("size") or (
            group._reactive_values.get("size") if group else None
        ) or "md"
        # Le refus hors-table, ICI et pas sur la prop — c'est le seul
        # point où la taille EFFECTIVE existe. Deux raisons, mesurées le
        # 2026-09-07 :
        #
        # - ``Radio.size`` vaut ``None`` par défaut (« hériter »), et le
        #   refus générique se sert du défaut comme ANCRE pour savoir
        #   lequel des deux niveaux d'une table imbriquée porte les
        #   paliers. Sans ancre il s'abstenait, et ``size="zzz"`` rendait
        #   un radio SANS AUCUNE taille ;
        # - la taille peut venir du GROUPE, qui n'a pas de table à lui.
        #   ``ui.radio_group(size="zzz")`` traversait donc tout le rendu
        #   sans un mot.
        #
        # La table est lue RÉSOLUE : un ``Theme(components={"radio": …})``
        # de l'app remplace les paliers, et une liste figée au corps de
        # classe refuserait alors une valeur juste.
        paliers = self._resolved_theme().get("sizes", {})
        if paliers and size_key not in paliers:
            raise ComponentUsageError(
                f"ui.radio: size={size_key!r} n'est pas dans la table du "
                f"thème. Valeurs connues : {', '.join(sorted(paliers))}.\n"
                f"  Une valeur hors table ne lève pas d'elle-même : le "
                f"radio rendrait sans aucune taille, sans un mot. La "
                f"taille peut venir du radio ou de son groupe."
            )
        # Inherit the group's EFFECTIVE name (explicit ``name=`` OR the
        # autoname derived from its ``value=`` binding), stashed on the
        # group at render time. A bound group's autoname (``name="value"``)
        # only reaches the radios this way — ``_reactive_values["name"]``
        # is None for autoname.
        name = self._reactive_values.get("name") or (
            getattr(group, "_radio_name", None) if group else None
        )
        # ``disabled`` from the group propagates to every radio (native
        # HTML has no "disable a radio group" — the only way to lock
        # the cluster is to stamp ``disabled`` on each ``<input>``).
        # Two paths :
        # - Group has a ClientBinding → adopt it as this radio's own
        #   ``disabled`` binding so emit_attrs stamps the reactive
        #   ``bz-attr:disabled`` directive on the input. Only when
        #   the radio doesn't already have its own per-item binding.
        # - Group has a literal truthy ``disabled`` → force-lock this
        #   radio (static, no reactivity). Wins over per-item state.
        if group is not None:
            group_disabled_binding = group._binding_metadata.get("disabled")
            if (
                group_disabled_binding is not None
                and "disabled" not in self._binding_metadata
            ):
                self._binding_metadata["disabled"] = group_disabled_binding
                # ``getattr(…, "value", False)`` : une ClientExpression n'a
                # pas de valeur serveur (elle est calculée par le runtime) —
                # même contrat que la base, qui stocke ``None`` pour le SSR
                # et laisse le runtime trancher au boot. Sans le défaut, un
                # ``ui.radio_group(disabled=expr)`` faisait planter le render
                # de chaque Radio enfant.
                self._reactive_values["disabled"] = bool(
                    getattr(group_disabled_binding, "value", False)
                )
            elif group._reactive_values.get("disabled"):
                self._reactive_values["disabled"] = True
        # Two streams from the group : the binding (for ``bz-model``)
        # and the underlying SSR value (for the static ``checked``
        # match below). The binding lives in ``_binding_metadata`` ;
        # ``_reactive_values["value"]`` carries the resolved SSR value
        # whether or not a binding was passed.
        group_binding = (
            group._binding_metadata.get("value") if group else None
        )
        bound_value = (
            group._reactive_values.get("value") if group else None
        )

        size_map: dict[str, str] = (
            self._resolved_theme().get("sizes", {}).get(size_key) or {}
        )
        opt_value = self._reactive_values.get("option_value") or ""

        # The real <input>. Sr-only ; carries name + value + framework
        # attrs ; bz-model when the group has a binding.
        input_attrs: dict[str, Any] = {
            "type": "radio",
            "value": str(opt_value),
            "class": self.compose_class(
                "input", apply_variant_size_modifiers=False
            ),
        }
        input_attrs.update(self.emit_attrs())

        if name:
            input_attrs["name"] = name
        # Binding lives on the GROUP, not on this radio — inject it
        # through ``_bind_x_model``'s explicit-binding overload. When
        # the group has no binding the helper is a no-op and we fall
        # back to the static-value match for the SSR initial state.
        if (
            self._bind_x_model(
                input_attrs, prop="value", binding=group_binding
            )
            is None
            and bound_value is not None
            and str(bound_value) == str(opt_value)
        ):
            input_attrs["checked"] = True

        circle_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "circle",
                    apply_variant_size_modifiers=False,
                ),
                size_map.get("circle", ""),
            )
            if p
        )
        dot_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "dot", apply_variant_size_modifiers=False
                ),
                size_map.get("dot", ""),
            )
            if p
        )

        container = Element(
            tag="div",
            attrs={
                "class": self.compose_class(
                    "container", apply_variant_size_modifiers=False
                )
            },
            children=(
                Element(tag="input", attrs=input_attrs, children=()),
                Element(
                    tag="div", attrs={"class": circle_class}, children=()
                ),
                Element(
                    tag="div", attrs={"class": dot_class}, children=()
                ),
            ),
        )

        children: list[Any] = [container]
        if self._label:
            label_class = " ".join(
                p
                for p in (
                    self.compose_class(
                        "label", apply_variant_size_modifiers=False
                    ),
                    size_map.get("label", ""),
                )
                if p
            )
            children.append(
                Element(
                    tag="span",
                    attrs={"class": label_class},
                    children=(self.emit_text_slot(self._label),),
                )
            )

        return Element(
            tag=self._tag,
            attrs={"class": self.compose_class("root", )},
            children=tuple(children),
        )

    def _lookup_group(self) -> RadioGroup | None:
        """Find the nearest ``RadioGroup`` on the parent stack at
        construction time. Called from ``__init__`` while the
        ``with RadioGroup(...)`` block is still active."""
        from bretzel.render.context import maybe_current_context

        ctx = maybe_current_context()
        if ctx is None:
            return None
        for parent in reversed(ctx.parent_stack):
            if isinstance(parent, RadioGroup):
                return parent
        return None
