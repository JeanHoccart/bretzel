"""How a component composes its CSS classes from its theme."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bretzel.components.base.nodes import merge_attr, stamp_display_none
from bretzel.core.tree import Element, Node
from bretzel.runtime.protocol import (
    BZ_SHOW_PREFIX,
)

if TYPE_CHECKING:
    pass


class ClassComposition:
    """Mixed into :class:`Component`."""

    def slot_class(self, slot: str, *extra: str) -> str:
        """Compose classes for a non-root slot and optional extra fragments."""
        return " ".join(
            part for part in (self.compose_class(slot), *extra) if part
        )

    def _size_key(self) -> str | None:
        """The step this instance is drawn at: ``size=`` as given.

        Overridden where the step is INHERITED (a radio takes its
        group's). Everything that reads the size table reads it through
        here — the base composer and the renders — so the two cannot
        disagree on the row."""
        value = self._reactive_values.get("size")
        return value if isinstance(value, str) else None

    def _size_row(self, theme: dict[str, Any] | None = None) -> Any:
        """``theme["sizes"][<step>]``: a class string (the root's) or a
        dict keyed by slot and setting; ``None`` without a step."""
        key = self._size_key()
        if key is None:
            return None
        return (theme or self._resolved_theme()).get("sizes", {}).get(key)

    def compose_class(
        self,
        slot: str = "root",
        *,
        apply_variant_size_modifiers: bool = True,
    ) -> str:
        """Compose the Tailwind class string for one of this component's slots.

        Reads the resolved theme dict (with app-level overrides applied
        when a render context is active), pulls the slot template,
        applies variant / size / modifier lookups when relevant. The
        user-supplied ``classes=`` are NOT added
        here — they land on the true root later, in
        ``_apply_universal_modifiers`` (the metaclass render wrap), so
        cosmetic overrides still win in source order (see step 5 below).

        Parameters:
        - ``slot``: key in ``theme["slots"]``. Defaults to ``"root"``.
          Multi-slot components (checkbox with root/input/label,
          dropdown with backdrop/panel/item, …) call this once per
          slot they want to compose.
        The colour is carried by the bridge class set on the rendered
        root (cf. :mod:`bretzel.theme.bridges`); composing the slot
        therefore does not depend directly on the colour.
        - ``apply_variant_size_modifiers``: when True (default),
          appends the slot's size (see step 3) and, on the root,
          ``theme["variants"][<variant>]`` and every truthy modifier
          from ``theme["modifiers"]``. False composes the bare
          template — for a render that draws its root by hand.

        Most components fit this template; complex composites
        (datatable cells, dropdown items inheriting from parent
        context) override or skip it.
        """
        theme = self._resolved_theme()
        parts: list[str] = []

        # 1. The slot template itself.
        slot_template = theme.get("slots", {}).get(slot)
        if slot_template:
            parts.append(slot_template)

        if apply_variant_size_modifiers and slot == "root":
            # 2. Variant.
            variant_value = self._reactive_values.get("variant")
            if variant_value is not None:
                variant_template = theme.get("variants", {}).get(variant_value)
                # A variant row may be keyed by slot, like a size row
                # (Badge: ``root`` and ``close``); the root takes its own.
                if isinstance(variant_template, dict):
                    variant_template = variant_template.get(slot)
                if variant_template:
                    parts.append(variant_template)

        # 3. Size — ONE rule, every slot. A row of ``theme["sizes"]`` is
        # either a class string, the root's (Button, Text), or a dict:
        # an entry that NAMES A SLOT holds that slot's classes and lands
        # here, on the slot; the other entries are settings the render
        # reads (``icon_size``, ``pill_size``). The composer handles the
        # dict so that no call site pastes ``size_map.get(slot)`` by hand:
        # forgetting one would be silent.
        if apply_variant_size_modifiers:
            row = self._size_row(theme)
            sized = (
                row if slot == "root" and isinstance(row, str)
                else row.get(slot) if isinstance(row, dict) else None
            )
            if isinstance(sized, str) and sized:
                parts.append(sized)

        if apply_variant_size_modifiers and slot == "root":
            # 4. Modifiers — boolean reactive props that map to a class
            #    when truthy. Looked up under ``theme["modifiers"]``.
            for mod_name, mod_class in theme.get("modifiers", {}).items():
                if self._reactive_values.get(mod_name):
                    parts.append(mod_class)

        # 5. User classes — NOT appended here. They land on the
        # component's true root in ``_apply_universal_modifiers`` (the
        # metaclass render wrap), so every component honours ``classes=``
        # uniformly regardless of which slot composes its root. See
        # ``_user_classes_str``.

        # 6. No slot override here. ``slots={"<slot>": "..."}`` is already
        # IN the template of step 1: ``_resolved_theme`` merges it into
        # ``theme["slots"]`` (non-root slots; the root's lands on the true
        # root in ``_apply_universal_modifiers``). Appending it here would
        # give every non-root slot composed here the override twice.

        return " ".join(p for p in parts if p).strip()

    @property
    def _raw_class_str(self) -> str:
        """The ``class`` written as raw HTML — ``class_="x"`` or
        ``attrs={"class": "x"}``, which ``split_kwargs`` normalises to the
        same key and which therefore both land in ``_raw_attrs``.

        Read by the metaclass wrap, NOT by ``emit_attrs``: a component
        that rebuilds its ``class=`` in ``render()`` would overwrite what
        ``emit_attrs`` had set there. It is the same reason that moved
        ``classes=`` and ``slots={"root"}`` up to the wrap.
        """
        raw = self._raw_attrs.get("class")
        return raw if isinstance(raw, str) else ""

    def _user_classes_str(self) -> str:
        """The literal ``classes=`` flattened to a string ('' when unset
        or when it's a ``ClientBinding``).

        Single source for appending the user's ``classes=`` onto a
        component's TRUE root. ``compose_class`` uses it for the canonical
        "root" slot ; components whose root is composed via another slot
        (Input's bare/affix paths, Slider) call it directly so ``classes=``
        is never silently dropped."""
        if not self._classes:
            return ""
        if isinstance(self._classes, str):
            return self._classes
        return " ".join(str(v) for v in self._classes if v)

    def apply_class_attrs(
        self,
        attrs: dict[str, Any],
        slot: str = "root",
    ) -> None:
        """Set the composed ``class=`` on ``attrs``.

        The user's ``classes=`` — literal **as well as** binding — is NOT
        this helper's business: ``_apply_universal_modifiers`` (the
        metaclass wrap) sets it on every component's true root, so all 55
        benefit and not only those that call here. This helper only
        composes the theme's slot.

        (History: the reactive branch lived here and emitted
        ``:class="…"`` — Alpine syntax, dead in V3 — dropping the static
        ``class=`` on the way. Two components called it, so they rendered
        with no class at all as soon as they were passed a
        ``classes=binding``. Cf. the
        ``tests/consistency/test_reactive_classes_universal.py`` gate.)

        Note: reactive variant/size/color axes are NOT supported.
        Those are design-time configuration per the ``BINDABLE_PROPS``
        contract — if a use case for dynamic theme axes appears,
        server-side conditional render at the call site covers it
        (``ui.button(label, color="error" if state.failed else
        "success")``).

        ``style=`` is NOT handled here; it's materialised by
        :meth:`emit_attrs` so every component gets it for free, not
        just the ones that call this helper.

        """
        cls_string = self.compose_class(slot)
        if cls_string:
            # ``merge_attr`` and not ``attrs["class"] = …``: a
            # ``class_=`` or an ``attrs={"class": …}`` already set by
            # ``emit_attrs`` must SURVIVE the theme's composition, not be
            # replaced by it.
            merge_attr(attrs, "class", cls_string)

    @staticmethod
    def with_slot_class(node: Node, slot_class: str, **extra_attrs: Any) -> Node:
        """Clone ``node`` with ``slot_class`` PREPENDED to its ``class``.

        The gesture: a component receives a subcomponent as a slot (a nav
        item's icon, an Input's affix, a Breadcrumb's separator, a
        Sidebar's badge), renders it, then must set its slot class on it
        **without** overwriting the one the child composed for itself.
        ``Element`` being immutable, that means cloning.

        Prepended, not appended: the child's classes stay last, so they
        win at equal Tailwind specificity — the slot dresses, the child
        decides.

        ``extra_attrs`` covers the Breadcrumb case, which sets an
        ``aria-hidden`` on the same clone (otherwise two would be
        needed).

        A ``node`` that is not an ``Element`` (FragmentNode, TextNode)
        comes back as-is: it has no attributes to set the class on.
        """
        if not isinstance(node, Element):
            return node
        existing = str(node.attrs.get("class", "")).strip()
        merged = f"{slot_class} {existing}".strip() if existing else slot_class
        import dataclasses as _dc

        return _dc.replace(node, attrs={**node.attrs, "class": merged, **extra_attrs})

    @staticmethod
    def _cloak_show(elem: Node, expr: str, *, initial: bool = False) -> Element:
        """Wrap ``elem`` with ``bz-show`` for a mutex branch (V3).

        Used by every component that emits BOTH branches of a reactive
        structural toggle in the DOM and lets the runtime pick which to
        show via ``bz-show`` (Button.loading spinner ↔ icon, IconButton
        same). ⚠️ NOT Alert: it never calls ``_cloak_show``, and
        ``dismissible`` is in no ``BINDABLE_PROPS`` (the only two callers
        are Button and ``actions/_wiring``). FOUC strategy: the
        server pre-stamps ``style="display:none"``
        on the branch whose ``initial`` evaluation is falsy, so nothing
        flashes before the runtime's first effect takes over.

        Static-only renders don't call this — the helper is purely for
        the binding-aware structural-mutex pattern.

        ``elem`` is typed ``Node`` because callers pass the result of
        ``component.render()`` (whose base signature is ``-> Node``).
        At runtime every mutex branch must be an :class:`Element` —
        the assertion documents that contract and surfaces violations
        loudly instead of silently dropping ``bz-show`` on a TextNode node.
        """
        assert isinstance(elem, Element), (
            f"bz-show mutex requires an Element wrapper (got {type(elem).__name__})"
        )
        attrs = {**elem.attrs, BZ_SHOW_PREFIX: expr}
        if not initial:
            stamp_display_none(attrs)
        return Element(
            tag=elem.tag,
            attrs=attrs,
            children=elem.children,
        )

    def _resolved_theme(
        self,
        key: str | None = None,
        shipped: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Merge the user's app-level override onto ``cls.THEME``.

        ``key`` / ``shipped`` default to its own. Passing them resolves
        ANOTHER component's theme — a real case: Combobox and Select
        compose their pills from ``BADGE_THEME`` (they render the pills
        in a client ``bz-for`` template, so they cannot instantiate real
        ``ui.badge``). Reading the module constant directly would bypass
        the user's override: a ``Theme(components={"badge": …})`` would
        not touch the pills.

        ``Theme.merged_component_theme(name, shipped)`` deep-merges the
        user override (``Theme(components={<THEME_KEY>: {...}})``) onto
        the component-shipped default, memoized per THEME_KEY — the
        merge inputs are immutable after boot, and ``compose_class``
        calls this once PER SLOT. Dict levels merge key-by-key so
        overriding one slot never drops the sibling slots, variants or
        sizes; a string leaf REDEFINES that entry wholesale (full
        template — unlike the per-instance ``slots=`` kwarg, which
        appends). Falls back to the bare ``cls.THEME`` when no render
        context is active (typical in unit tests) or when no override
        exists.
        """
        own = key is None and shipped is None
        if own and getattr(self, "_own_theme", None) is not None:
            return self._own_theme
        from bretzel.render.context import maybe_current_context

        name = key if key is not None else self.THEME_KEY
        default = shipped if shipped is not None else type(self).THEME

        ctx = maybe_current_context()
        resolved = default
        if ctx is not None:
            theme_obj = getattr(ctx.app, "theme", None)
            getter = getattr(theme_obj, "merged_component_theme", None) if theme_obj else None
            if callable(getter):
                resolved = getter(name, default)
        # ``slots={"panel": …}`` — the per-instance override, for
        # NON-root slots — is added here, at the point where the
        # reads of ``theme["slots"][X]`` already draw from.
        #
        # Why here and not in ``compose_class``: many reads are done by
        # hand (``slots.get("item")``) and never go through it. An override
        # set in the composer would therefore not reach them, and
        # ``ui.toggle_group(slots={"item": …})`` would be **lost
        # silently**. The base layer cannot patch a deep descendant after
        # the fact — but it can hand it the right theme BEFORE.
        #
        # ⚠️ ``root`` is EXCLUDED: it is applied post-render by the
        # metaclass wrap (the only one that knows the true root whatever
        # slot composed it). Adding it here would double it.
        #
        # Semantics: the per-instance kwarg ADDS, the app-level
        # ``Theme(components=…)`` override REPLACES.
        # ``_user_slots_validated``: set by ``_reject_unknown_slot_keys``
        # once the keys are checked. Without that guard, the validator —
        # which reads this very theme — would see its own keys injected
        # and would declare any typo KNOWN. Circularity caught by
        # ``test_unknown_slot_key_croaks_at_construction``.
        user_slots = (
            getattr(self, "_user_slots", None)
            if getattr(self, "_user_slots_validated", False)
            else None
        )
        if user_slots and key is None:
            extra = {k: v for k, v in user_slots.items() if k != "root"}
            if extra:
                slots = dict(resolved.get("slots", {}))
                for slot_name, addition in extra.items():
                    base = slots.get(slot_name, "")
                    slots[slot_name] = f"{base} {addition}".strip() if base else str(addition)
                resolved = {**resolved, "slots": slots}
        if own and getattr(self, "_user_slots_validated", False):
            # Asked several times per component (each slot, the size check…),
            # and it cannot change during the render. Not before the
            # ``slots=`` keys are validated: until then the instance's own
            # additions are deliberately left out (cf. just above).
            self._own_theme = resolved
        return resolved
