"""``Avatar`` — round / square user image with initials fallback.

**``name=`` is the recommended way of calling this component**: it
derives the initials AND the image's ``alt`` from it, so the caller has
nothing to forget. ``ui.avatar(name="Jean Hoccart", src="/photo.png")``
renders ``<img alt="Jean Hoccart">``; with no ``src``, the chip shows
``JH``.

Three render modes:

- ``src=``: an ``<img>`` covers the chip. Its ``alt`` comes from
  ``alt=`` if given, otherwise from ``name=``. ⚠️ Neither of the two
  leaves ``alt=""``, which declares a DECORATIVE image — legitimate
  beside a name already written out in full, silent and wrong elsewhere.
- ``initials=`` or ``name=`` (with no ``src``): a tinted square shows
  the letters in the chosen ``color``. ``initials=`` wins when both are
  given.
- None of the three: an empty chip in the chosen colour.

Optional ``status=`` overlays a small dot in the bottom-right corner
(``online`` / ``offline`` / ``busy`` / ``away``).

``shape=`` picks ``circle`` (default) or ``square``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop, stamp_display_none
from bretzel.components.base._wiring import theme_context
from bretzel.components.feedback.avatar.theme import AVATAR_THEME
from bretzel.core.tree import Element, Node


def initials_of(name: str) -> str:
    """A name's initials — ``"Jean Hoccart"`` → ``"JH"``.

    First letter of the first word, first of the LAST: it is what the
    repository's four examples each copied on their own, to the letter.
    A single word gives only one initial, rather than its first two
    letters — ``"Jean"`` → ``"J"``, not ``"JE"``.

    Returns ``""`` for an empty or blank name, and the caller decides:
    the component then shows no letter chip, which is more honest than a
    ``"?"`` that looks like data.
    """
    parts = name.split()
    if not parts:
        return ""
    return (parts[0][:1] + (parts[-1][:1] if len(parts) > 1 else "")).upper()


class Avatar(Component):
    """Round / square user chip with image or initials fallback."""

    THEME: ClassVar[dict[str, Any]] = AVATAR_THEME
    THEME_KEY: ClassVar[str] = "avatar"
    DEFAULT_TAG: ClassVar[str] = "span"
    IS_CONTAINER: ClassVar[bool] = False
    # Only ``status`` earns a client binding — presence flips live from a
    # client driver (SSE / polling) via ``bz-attr:class`` + ``bz-show``.
    # ``src`` / ``initials`` change only on a server re-render (new user
    # data → ``@refreshable``), so they stay design-time.
    # Cf. .claude/bretzel/client-reactive-surface.md.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("status",)

    src: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    alt: str = reactive_prop(default="", emit_attr=False)
    #: The person's name. **The recommended way of calling this
    #: component**: it derives the initials AND the image's ``alt`` from
    #: it.
    #:
    #: The defect that closes: ``ui.avatar(src="/photo.png")`` emitted
    #: ``alt=""``, which does not mean "no alternative" but
    #: **"decorative image, ignore me"** — a user's photo became
    #: invisible to the screen reader, in silence. ``ui.image`` requires
    #: its ``alt`` for exactly that reason, but requiring it here would
    #: break every existing call.
    #:
    #: Deriving rather than requiring is the route ``ui.file_upload``
    #: already takes (its thumbnail carries the file's name): the caller
    #: has nothing to know, so nothing to forget. And the call sites gain
    #: — they all computed their initials by hand.
    name: str | None = reactive_prop(default=None, emit_attr=False)
    initials: str | None = reactive_prop(default=None, emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    shape: str = reactive_prop(default="circle", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    status: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        src: str | None = None,
        alt: str | None = None,
        name: str | None = None,
        initials: str | None = None,
        size: str | None = None,
        shape: str | None = None,
        color: str | None = None,
        status: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            src=src, alt=alt, name=name, initials=initials,
            size=size, shape=shape, color=color,
            status=status,
            **kwargs,
        )

    def render(self) -> Element:
        theme, slots, sizes, size_key, _color = theme_context(self)
        shapes = theme.get("shapes", {})
        statuses = theme.get("statuses", {})

        shape = self._reactive_values.get("shape") or "circle"
        src = self._reactive_values.get("src")
        person = self._reactive_values.get("name")
        # Explicit ``alt`` > name > empty. The empty stays possible and
        # it is LEGITIMATE: a purely decorative avatar beside a name
        # already written out in full must not be announced twice.
        alt = self._reactive_values.get("alt") or (str(person) if person else "")
        # Same for the initials: explicit > derived from the name.
        initials = self._reactive_values.get("initials") or (
            initials_of(str(person)) or None if person else None
        )
        status = self._reactive_values.get("status")
        size_map = sizes.get(size_key, sizes.get("md", {}))

        children: list[Node] = []

        if src:
            # Image carries rounded-{shape} so IT clips itself : the root
            # has no ``overflow-hidden`` (see theme) so the status dot's
            # ring can extend outside the box.
            image_class = " ".join(
                p
                for p in (
                    slots.get("image", ""),
                    shapes.get(shape, shapes.get("circle", "")),
                )
                if p
            )
            img_attrs: dict[str, Any] = {
                "src": src,
                "alt": alt,
                "class": image_class,
                # ``loading="lazy"`` saves bandwidth in avatar lists
                # (table rows, contributor strips).
                "loading": "lazy",
                # ``src`` is not bindable: the ``<img>`` reflects its
                # static ``src`` attribute, no carrier to wire.
            }
            children.append(
                Element(tag="img", attrs=img_attrs, children=())
            )
        else:
            # ``initials`` is design-time: ``BINDABLE_PROPS = ("status",)``,
            # so the base layer RAISES on a ClientBinding before reaching
            # here. The ``_binding_metadata.get("initials")`` branch that
            # lived here was unreachable — removed on 2026-08-01. If
            # reactive initials become a need, the prop must first be
            # added to ``BINDABLE_PROPS``.
            # Truncated to 3 characters: an avatar is sized for 1-3
            # letters by convention.
            if isinstance(initials, str) and len(initials) > 3:
                initials = initials[:3]
            initials_node = self.emit_text_slot(initials)
            if initials_node is not None:
                children.append(
                    Element(
                        tag="span",
                        attrs={"class": slots.get("initials", "")},
                        children=(initials_node,),
                    )
                )

        # Status dot — overlaid bottom-right. Two paths :
        # 1. literal string → bake the bg-color class statically.
        # 2. ClientBinding → render unconditionally with reactive
        #    ``bz-attr:class`` + ``bz-show`` so the colour flips live.
        # The class = slot (positioning + ring) + colour entry (bg-…) +
        # per-size dimensions ; only the colour is reactive.
        status_binding = self._binding_metadata.get("status")
        status_base_class = " ".join(
            p
            for p in (
                slots.get("status", ""),
                size_map.get("status", ""),
            )
            if p
        )
        if status_binding is not None:
            # Reactive : ``bz-attr:class`` is the single writer that
            # rebuilds the class ; the static ``class`` carries the SSR
            # snapshot for first paint. FOUC : pre-stamp ``display:none``
            # when the SSR value resolves to no visible dot.
            path = status_binding.binding_path()
            color_lookup_js = (
                "{"
                + ", ".join(
                    f"'{name}': '{cls}'" for name, cls in statuses.items()
                )
                + "}"
            )
            ssr_color = statuses.get(status, "") if status else ""
            initial_visible = bool(status and status in statuses)
            status_attrs: dict[str, Any] = {
                "class": " ".join(
                    p for p in (status_base_class, ssr_color) if p
                ),
                "bz-attr:class": (
                    f"'{status_base_class} ' + "
                    f"(({color_lookup_js})[{path}] || '')"
                ),
                "bz-show": f"!!{path} && !!(({color_lookup_js})[{path}])",
                "bz-attr:aria-label": path,
                "role": "status",
            }
            if status:
                status_attrs["aria-label"] = status
            if not initial_visible:
                stamp_display_none(status_attrs)
            children.append(
                Element(
                    tag="span",
                    attrs=status_attrs,
                    children=(),
                )
            )
        elif status and status in statuses:
            status_class = " ".join(
                p
                for p in (
                    status_base_class,
                    statuses.get(status, ""),
                )
                if p
            )
            children.append(
                Element(
                    tag="span",
                    attrs={
                        "class": status_class,
                        "aria-label": status,
                        "role": "status",
                    },
                    children=(),
                )
            )

        attrs = self.emit_attrs()
        attrs["class"] = " ".join(
            p
            for p in (
                self.compose_class(
                    "root",
                    apply_variant_size_modifiers=False,
                ),
                shapes.get(shape, shapes.get("circle", "")),
                size_map.get("root", ""),
            )
            if p
        )
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))
