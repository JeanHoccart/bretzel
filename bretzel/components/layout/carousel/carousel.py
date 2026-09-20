"""``Carousel`` — snapping scroll through a series of contents.

Usage ::

    with ui.carousel(autoplay=5) as hero:
        ui.image(src="/a.jpg")
        ui.image(src="/b.jpg")

    with ui.carousel(value=state.slide, per_view={"base": 1, "md": 3}):
        for p in ui.each(products):
            ui.card(p.name)

**Every direct child is a slide.** Unlike ``Tabs``, there is only one
kind of child: so there is nothing to tell apart, so nothing to declare.
The decisive benefit is that it composes with ``ui.each`` without a line
of ceremony — the number-one use case. A slide with several elements is
made with a ``ui.vstack``, as everywhere else.

**The engine is CSS scroll-snap**, not a driven ``translateX``. The touch
swipe with inertia, the wheel, the keyboard and the snapping are the
browser's; the runtime only goes to an index and reads the index back
from the position (``$bz.carousel.scope``,
``runtime/_src/17_carousel.js``). That is what makes a responsive
``per_view`` free: the JS knows no breakpoint, it MEASURES what CSS
decided.

**The controls are not props.** They are derived, because rendering them
unconditionally would be wrong in two real cases:

- nothing at all when there is nowhere to go (``len(slides) <=
  per_view``) — and it does happen for real, the content coming from
  data (a single-item list);
- the dots only where ``per_view == 1``. A dot says "there are N slides,
  you are at the k-th"; with 3 slides visible out of 12 it has no
  referent any more. With a responsive ``per_view``, they come out in
  ``md:hidden`` — the decision stays in CSS.

The arrows, for their part, **disable themselves at the edges** by
reading the browser's real geometry (``scrollLeft`` vs ``scrollWidth -
clientWidth``), so without the slightest breakpoint computation in Python
or JS.

One accepted asymmetry: **the arrows stop, the autoplay loops.** An arrow
disabled at the end teaches there is nothing left; an automatic rotation
that stops is no longer a rotation.

``autoplay`` carries the activation AND the cadence in a single prop
(``autoplay=5`` → every 5 s, ``None`` → off): two props would make the
absurd state "off but timed" representable. It reuses ``$bz._tick``
(``06_helpers.js``), the morph-idempotent timer already written for
``ui.interval`` — so the autoplay adds no timer to the runtime. At the
user's first gesture it stops FOR GOOD: no resumption after a delay (a
content that starts moving again while you are reading it is the
number-one a11y complaint about carousels), and no pause on hover (it
does not exist on a coarse pointer).

Imperative API : ``.set(i)`` / ``.next()`` / ``.prev()`` — same family,
same names and same index semantics as :class:`Stepper`. Two components
driven alike are remembered once.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    bool_attr,
    coerce_index,
    hidden_carrier_attrs,
    server_sync_marker,
)
from bretzel.components.base._wiring import (
    pop_change_handler as _pop_change_handler,
)
from bretzel.components.base.responsive import (
    BASE_KEYS,
    responsive_classes,
)
from bretzel.components.layout.carousel.theme import CAROUSEL_THEME, DOTS_HIDDEN
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.render import text


def _per_view_class(value: Any) -> str:
    """One ``per_view`` value → a slide's width class.

    ``1`` → ``basis-full``; ``N`` → ``basis-1/N``. A string passes
    verbatim (the raw Tailwind escape hatch, same contract as
    ``Grid(cols=)``). Breakpoints are NOT handled here:
    :func:`responsive_classes` wraps this function and owns the ``{bp}:``
    prefixing for every graded prop in the library.
    """
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value
    count = int(value)
    return "basis-full" if count <= 1 else f"basis-1/{count}"


def _per_view_at_base(value: Any) -> int:
    """The ``per_view`` at the smallest breakpoint — the one that decides
    whether the dots exist AT ALL.

    Dots only make sense at ``per_view == 1``. With a responsive dict,
    they are rendered as soon as the base breakpoint is 1, then hidden in
    CSS at the breakpoints where it rises (cf.
    :meth:`Carousel._dots_hidden_class`) — the decision stays where the
    information lives, in the stylesheet.

    ``BASE_KEYS`` and not a list written here: copying it by hand had
    already drifted IN BOTH DIRECTIONS — it invented an upper-case
    ``DEFAULT`` (which ``responsive_classes`` refuses, so a dead branch)
    and forgot ``default`` (which it accepts). Measured result:
    ``per_view={"default": 3}`` rendered one dot per slide while showing
    three — exactly the state the module's docstring declares
    impossible.
    """
    if isinstance(value, dict):
        for key, raw in value.items():
            if key in BASE_KEYS:
                return _per_view_at_base(raw)
        return 1
    if value is None or isinstance(value, (str, bool)):
        return 1
    return max(1, int(value))


def _build_bz_data(
    *,
    scope_key: str,
    has_local_value: bool,
    initial_value: int,
    binding_path: str | None,
    server_synced: bool,
    autoplay: bool,
) -> str:
    """The instance's ``bz-data``: **data, not code**.

    The methods (geometry, ``goTo``/``next``/``prev``, the two
    position↔state bridges) live once in ``$bz.carousel.scope``.

    ``_track`` is declared ``null`` then filled by the root's
    ``bz-init``: a scope method has no access to ``$refs``, only
    directives do (same constraint and same remedy as Slider).

    ``still`` is only emitted if an autoplay exists, and it is a DECLARED
    signal, not a field set on the fly: it is the
    ``$bz._tick($el, !still, ms)`` effect that reads it, and an
    undeclared field would never re-run that effect — the rotation would
    never stop.

    ``_geom`` is declared for the SAME reason, and it is what makes the
    arrows right. The bound is MEASURED (``scrollWidth - clientWidth``),
    and a measurement is not a signal: without a declared field to read,
    ``bz-attr:disabled="_atEnd()"`` evaluates once at scan time and
    freezes. Hydrated before the stylesheet applies, it measures a track
    that is not yet ``flex`` — so nothing to scroll, so BOTH arrows
    disabled, so invisible (``disabled:opacity-0``), for good. The field
    must be declared HERE: set on the fly on the JS side, it would not
    exist at the effect's first pass, which would therefore never
    subscribe to it.
    """
    if has_local_value:
        sync = server_sync_marker(scope_key, enabled=server_synced)
        state = f"{scope_key}: {json.dumps(initial_value)},{sync} "
        target = f"this.{scope_key}"
    else:
        assert binding_path is not None
        state = ""
        target = binding_path

    return (
        "{...$bz.carousel.scope,"
        + state
        + ("still: false," if autoplay else "")
        + "_geom: 0,"
        + "_track: null,"
        + f"_read() {{ return {target}; }},"
        + f"_write(v) {{ {target} = v; }}"
        + "}"
    )


class Carousel(Component):
    """Render a snapping track whose direct children are slides."""

    THEME: ClassVar[dict[str, Any]] = CAROUSEL_THEME
    THEME_KEY: ClassVar[str] = "carousel"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "next", "prev")
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)
    # ``per_view`` is the only graded prop, and its class is assembled by
    # ``_per_view_class`` (closed by ``_LAYOUT_CLASSES``). What remains is
    # the hiding of the dots, whose class lives in the ``responsive``
    # table.
    RESPONSIVE_THEME_KEYS: ClassVar[tuple[str, ...]] = ("responsive",)
    RESPONSIVE_PROPS: ClassVar[frozenset[str]] = frozenset({"per_view"})

    value: Any = reactive_prop(
        default=0,
        emit_attr=False,
        writes=True,
        names_field=True,
    )
    # ``Any`` and not ``int``: a graded prop, it takes a breakpoint dict.
    per_view: Any = reactive_prop(default=1, emit_attr=False)
    autoplay: Any = reactive_prop(default=None, emit_attr=False)
    gap: str = reactive_prop(default="md", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        per_view: int | dict | str | None = None,
        autoplay: float | None = None,
        gap: str | None = None,
        size: str | None = None,
        color: str | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            value=value,
            per_view=per_view,
            autoplay=autoplay,
            gap=gap,
            size=size,
            color=color,
            name=name,
            on_change=on_change,
            **kwargs,
        )

    # ── Imperative API ─────────────────────────────────────────────────
    #
    # Ordinary class methods: none of these names is a
    # ``reactive_prop``, so the overlays' non-data-descriptor trick has
    # nothing to protect here — and it would make these methods
    # invisible to ``test_imperative_classvar_is_complete``, which only
    # reads a ClassDef's public methods.

    def set(self, index: int) -> str:
        """Go to ``index``. Write-through binding if there is one."""
        return self._value_command(coerce_index(index, minimum=0))

    def next(self) -> str:
        # Always the dispatch, binding or not: the destination depends
        # on the LIVE geometry (how many slides fit on screen at the
        # current breakpoint), which the server does not know at render.
        return self._dispatch_command("bz-next")

    def prev(self) -> str:
        return self._dispatch_command("bz-prev")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        gaps = theme.get("gaps", {})

        size_key = self._reactive_values.get("size") or "md"
        size_cfg = sizes.get(size_key, sizes.get("md", {}))
        per_view = self._reactive_values.get("per_view")
        autoplay = self._reactive_values.get("autoplay")
        gap_key = self._reactive_values.get("gap") or "md"

        # ── Binding de ``value`` ─────────────────────────────────────
        value_binding = self._binding_metadata.get("value")
        initial_index = coerce_index(self._reactive_values.get("value"), minimum=0)
        value_server_backed = self._value_server_backed("value")
        scope_key = self._scope_keys("value")[0]
        binding_path = (
            self.path_of(value_binding) if value_binding is not None else None
        )
        active_expr = binding_path or scope_key

        # ── The slides = the children, one by one ───────────────────
        slide_class = self.slot_class("slide", responsive_classes(per_view, _per_view_class)
        )
        slides: list[Element] = []
        for child in self._children:
            rendered = self._render_one(child)
            if isinstance(rendered, Element):
                slides.append(
                    Element(
                        tag="div",
                        attrs={"class": slide_class},
                        children=(rendered,),
                    )
                )

        count = len(slides)
        base_per_view = _per_view_at_base(per_view)
        # Nothing to drive if there is nowhere to go — and the case
        # happens for real, the content coming from data.
        has_controls = count > base_per_view
        # The dots only exist where they have a referent.
        has_dots = has_controls and base_per_view == 1

        track = Element(
            tag="div",
            attrs={
                "class": self.slot_class("track", gaps.get(gap_key, "")),
                "bz-ref": "bztrack",
                # What makes the bounds be re-measured when the layout
                # changes AFTER the scan (a late stylesheet, a collapsed
                # panel that opens, a breakpoint). Carried by the TRACK
                # and not by the root's ``bz-init``: ``bz-init`` is
                # one-shot per NODE and idiomorph morphs in place, so an
                # observer installed there would never see the slides
                # again. An effect is redone at every rescan. (Reasoned
                # from the code, not proved by a test: the track's box
                # follows its slides', so observing the track covers in
                # practice the cases we knew how to fabricate.)
                "bz-effect": "_observeGeom()",
                # With no modifier, and it is not an oversight:
                # ``bz-on:`` passes its suffix VERBATIM to
                # ``addEventListener``, so a ``.passive`` would listen
                # for an event named "scroll.passive" and this bridge
                # would be dead in silence. Paid right here (traps.md
                # § "bz-on: has NO modifier"), gated since.
                "bz-on:scroll": "_onScroll()",
                # The first gesture turns the autoplay off.
                # ``pointerdown`` covers finger and mouse, ``wheel`` the
                # scroll wheel.
                **(
                    {
                        "bz-on:pointerdown": "_touch()",
                        "bz-on:wheel": "_touch()",
                    }
                    if autoplay
                    else {}
                ),
            },
            children=tuple(slides),
        )

        # The arrows anchor on the VIEWPORT, not on the root: their
        # ``top-1/2`` would otherwise be computed on a height that
        # includes the dot row, and they would visibly fall below the
        # track's centre (measured at 10 px on a carousel with dots).
        viewport_children: list[Node] = [track]
        children: list[Node] = []

        # The prefix that turns the autoplay off, once: arrows AND dots
        # carry it, and ``has_dots`` implies ``has_controls`` — so
        # defining it in the arrows' branch made it available to the dots
        # by a side effect, which reads badly.
        touch = "_touch(); " if autoplay else ""

        if has_controls:
            arrow_size = size_cfg.get("arrow", "")
            icon_size = size_cfg.get("arrow_icon", "sm")
            for direction, icon_name, label_key, disabled_call in (
                ("prev", "chevron-left", "carousel.previous", "_atStart()"),
                ("next", "chevron-right", "carousel.next", "_atEnd()"),
            ):
                viewport_children.append(
                    Element(
                        tag="button",
                        attrs={
                            "type": "button",
                            "class": self.slot_class(
                                "arrow",
                                arrow_size,
                                self.slot_class(f"arrow_{direction}"),
                            ),
                            "aria-label": text(label_key),
                            "bz-attr:disabled": disabled_call,
                            "bz-on:click": f"{touch}{direction}()",
                        },
                        children=(
                            Component.render_detached(
                                Icon(icon_name, size=icon_size)
                            ),
                        ),
                    )
                )

        children.append(
            Element(
                tag="div",
                attrs={"class": self.slot_class("viewport")},
                children=tuple(viewport_children),
            )
        )

        if has_dots:
            dot_class = self.slot_class("dot", size_cfg.get("dot", ""))
            dot_nodes: list[Node] = []
            for index in range(count):
                dot_attrs: dict[str, Any] = {
                    "type": "button",
                    "class": dot_class,
                    "aria-label": text("carousel.go_to_slide", n=index + 1),
                    # ``bool_attr`` and not a hand-written ternary: it
                    # is THE helper for the literal ``"true"``/``"false"``
                    # string (a bare boolean would DROP the attribute at
                    # false and ``data-[selected=…]`` would never match).
                    # Nineteen sites had re-implemented it before its
                    # extraction, ten of them without parenthesising
                    # their operand.
                    "bz-attr:data-selected": bool_attr(
                        f"Number({active_expr}) === {index}"
                    ),
                    "bz-on:click": f"{touch}goTo({index})",
                }
                if index == initial_index:
                    # Static SSR — the active dot is right at the first
                    # paint, before the runtime hydrates.
                    dot_attrs["data-selected"] = "true"
                dot_nodes.append(
                    Element(tag="button", attrs=dot_attrs, children=())
                )
            children.append(
                # No ``role="tablist"``: the ARIA "tabbed carousel"
                # pattern ALSO requires ``role="tab"`` on each dot and
                # ``role="tabpanel"`` on each slide, with the
                # ``aria-controls`` linking them. Declaring half the
                # pattern announces to screen readers a structure that
                # does not exist — worse than declaring none. Labelled
                # buttons in a named group tell the truth.
                Element(
                    tag="div",
                    attrs={
                        "class": self.slot_class("dots", self._dots_hidden_class(
                                per_view,
                                theme.get("responsive", {}).get(
                                    DOTS_HIDDEN, ""
                                ),
                            ),
                        ),
                        "role": "group",
                        "aria-label": text("carousel.choose_slide"),
                    },
                    children=tuple(dot_nodes),
                )
            )

        # ── Hidden input — form data + source of the ``change`` ─────
        root_attrs = self.emit_attrs()
        relocated = _pop_change_handler(root_attrs)
        name = self._reactive_values.get("name") or self._derive_field_name()
        if name or relocated:
            hidden_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(active_expr, initial=initial_index),
            }
            if name:
                hidden_attrs["name"] = str(name)
            hidden_attrs.update(relocated)
            children.append(
                Element(tag="input", attrs=hidden_attrs, children=())
            )

        # ── Assemblage ───────────────────────────────────────────────
        root_attrs["class"] = self.slot_class("root")
        # The role lives on the ROOT and not on the track: it is the
        # root that ALSO contains the arrows and the dots, so it is the
        # root that is the "carousel" a screen reader must announce as
        # one block.
        root_attrs["role"] = "group"
        root_attrs["aria-roledescription"] = "carousel"
        root_attrs["bz-data"] = _build_bz_data(
            scope_key=scope_key,
            has_local_value=value_binding is None,
            initial_value=initial_index,
            binding_path=binding_path,
            server_synced=value_server_backed,
            autoplay=bool(autoplay),
        )
        # A scope method has no ``$refs`` — it is here, in directive
        # context, that we capture the track into the scope.
        root_attrs["bz-init"] = "_track = $refs.bztrack"
        effects = ["_syncFromValue()"]
        if autoplay:
            ms = max(1, int(float(autoplay) * 1000))
            # ``$bz._tick`` is ``ui.interval``'s timer:
            # morph-idempotent, self-cleaned when the element leaves the
            # DOM. So the autoplay adds no timer to the runtime.
            effects.append(f"$bz._tick($el, !still, {ms})")
            root_attrs["bz-on:tick"] = "next()"
        root_attrs["bz-effect"] = "; ".join(effects)
        root_attrs["bz-on:bz-set"] = "goTo($event.detail.value)"
        root_attrs["bz-on:bz-next"] = "next()"
        root_attrs["bz-on:bz-prev"] = "prev()"

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children)
        )

    @staticmethod
    def _dots_hidden_class(per_view: Any, hidden: str) -> str:
        """Hide the dots at the breakpoints where ``per_view`` exceeds 1.

        Rendered only when the base is 1 (otherwise there is no dot at
        all). The hiding lives in CSS and not in Python because the
        server does not know which breakpoint is active — it is the same
        reason that makes the geometry be read at runtime rather than
        computed.

        ``hidden`` comes from ``THEME["responsive"]["dots_hidden"]`` and
        is NOT hard-coded here: only a token present in a table declared
        by ``RESPONSIVE_THEME_KEYS`` is closed over the breakpoints by
        the safelist. Hard-coded, ``lg:hidden`` existed in no source, so
        the rule was missing from the compiled CSS and the dots stayed
        visible in production — exactly the behaviour this method exists
        to prevent.
        """
        if not isinstance(per_view, dict) or not hidden:
            return ""
        return " ".join(
            f"{bp}:{token}"
            for bp, raw in per_view.items()
            if bp not in BASE_KEYS
            and isinstance(raw, int)
            and not isinstance(raw, bool)
            and raw > 1
            for token in hidden.split()
        )


__all__ = ["Carousel"]
