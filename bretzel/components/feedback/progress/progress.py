"""``Progress`` — horizontal value indicator.

Two modes :

- *determinate* (default) : ``value`` between 0 and ``max`` (default
  100) drives the fill width. Pass a :class:`ClientBinding` for the
  value and the bar updates live as the bound state mutates — the
  width is wired via a ``bz-attr:style="`width: ${...}%`"`` runtime
  directive so it reacts without a server round-trip.
- *indeterminate* : ``indeterminate=True`` replaces the fill with an
  animated stripe. Useful when the operation has no measurable
  progress (waiting for a server response, parsing an unknown-size
  stream).

Label control :
- ``show_label=True`` puts a short ``"42%"`` next to the bar.
- ``label="Uploading…"`` overrides with a custom string.
- Without either, no label renders.

A11y : the root element carries ``role="progressbar"`` plus
``aria-valuenow / aria-valuemin / aria-valuemax``. Indeterminate
mode drops ``aria-valuenow`` per the WAI-ARIA spec.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import theme_context
from bretzel.components.feedback.progress.theme import PROGRESS_THEME
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode


class Progress(Component):
    """Horizontal progress bar."""

    THEME: ClassVar[dict[str, Any]] = PROGRESS_THEME
    THEME_KEY: ClassVar[str] = "progress"
    IS_CONTAINER: ClassVar[bool] = False
    # Reactive surface — current value + label text. max / color / size /
    # show_label / indeterminate are design-time.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "label")

    value: Any = reactive_prop(default=0, emit_attr=False)
    max: float = reactive_prop(default=100, emit_attr=False)
    indeterminate: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    show_label: bool = reactive_prop(default=False, emit_attr=False)
    label: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        value: Any = None,
        *,
        max: float | None = None,
        indeterminate: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        show_label: bool | None = None,
        label: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            value=value, max=max,
            indeterminate=indeterminate,
            color=color, size=size,
            show_label=show_label, label=label,
            **kwargs,
        )

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme, _slots, _sizes, size, _color = theme_context(self)
        indeterminate = bool(self._reactive_values.get("indeterminate"))
        max_val = float(self._reactive_values.get("max") or 100)
        # Binding drives live width/label ; the resolved SSR value (in
        # ``_reactive_values["value"]``) drives initial width + aria-valuenow.
        value_binding = self._binding_metadata.get("value")
        value_raw = self._reactive_values.get("value")
        show_label = bool(self._reactive_values.get("show_label"))
        custom_label = self._reactive_values.get("label")

        size_cls = theme.get("sizes", {}).get(size, "")

        # SSR percentage of the resolved value, clamped to [0, 100] —
        # shared by the fill width, the percentage labels and the
        # FOUC snapshots below.
        ssr_pct = max(0.0, min(100.0, (float(value_raw or 0) / max_val) * 100))

        # ── Track + fill ─────────────────────────────────────────────
        track_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "track",
                    apply_variant_size_modifiers=False,
                ),
                size_cls,
            )
            if p
        )

        if indeterminate:
            fill_attrs: dict[str, Any] = {
                "class": self.compose_class(
                    "fill_indeterminate",
                    apply_variant_size_modifiers=False,
                ),
            }
        else:
            fill_class = self.compose_class(
                "fill",
                apply_variant_size_modifiers=False,
            )
            fill_attrs = {"class": fill_class}
            if value_binding is not None:
                # Live binding : ``bz-attr:style`` is the single writer
                # rewriting the width ; the clamp bounds over/under values.
                # ⚠️ Parenthesising ``path_of`` is NOT cosmetic: a
                # ClientExpression is raw JS, a comparison does not
                # parenthesise itself. Without the parens ``n > 0 / 100 *
                # 100`` evaluates to 100 instead of 1 — wrong, silently.
                expr = (
                    f"`width: ${{Math.max(0, Math.min(100, "
                    f"(({self.path_of(value_binding)}) / {max_val}) * 100"
                    f"))}}%`"
                )
                fill_attrs["bz-attr:style"] = expr
            # SSR snapshot of the resolved value (binding or literal)
            # so the bar paints at the right width before the runtime
            # boots (FOUC discipline, .claude/bretzel/runtime.md).
            fill_attrs["style"] = f"width: {ssr_pct:.1f}%"

        track = Element(
            tag="div",
            attrs={"class": track_class},
            children=(Element(tag="div", attrs=fill_attrs, children=()),),
        )

        # ── Label (optional) ─────────────────────────────────────────
        # Mutex order custom_label > show_label > none ; each has a
        # reactive flavour when the prop is a ClientBinding :
        # 1. ``label=ClientBinding`` → bz-text ; with ``show_label`` it
        #    falls back to the percentage when the bound label is empty.
        # 2. ``label="literal"`` → static text.
        # 3. ``show_label=True`` → reactive percentage if ``value`` bound,
        #    else static.
        # 4. none → no span.
        children: list[Any] = [track]
        label_binding = self._binding_metadata.get("label")
        label_class = self.compose_class(
            "label",
            apply_variant_size_modifiers=False,
        )

        if label_binding is not None and not indeterminate:
            label_path = self.path_of(label_binding)
            if show_label and value_binding is not None:
                # Fallback to live percentage when the bound label is
                # empty. Both reactive ; the OR picks the truthy one.
                value_path = self.path_of(value_binding)
                text_expr = (
                    f"({label_path}) || "
                    f"(Math.round((({value_path}) / {max_val}) * 100) + '%')"
                )
            elif show_label:
                # Static percentage as fallback.
                text_expr = f"({label_path}) || '{int(round(ssr_pct))}%'"
            else:
                text_expr = label_path
            label_attrs: dict[str, Any] = {
                "class": label_class,
                "bz-text": text_expr,
            }
            # SSR-stamped initial value (the binding's resolved value
            # at render time) so the span shows the right text before
            # the runtime boots, no flash.
            initial = (
                str(custom_label) if custom_label
                else (f"{int(round(ssr_pct))}%" if show_label else "")
            )
            children.append(
                Element(
                    tag="span",
                    attrs=label_attrs,
                    children=(TextNode(initial),),
                )
            )
        elif custom_label:
            # A literal label — beats ``show_label``, static text.
            #
            # It is here, and only here, that a Component lands: the
            # branch above is only taken for a ClientBinding. The two
            # therefore cannot compete for the same node — ``bz-text``
            # and arbitrary markup are exclusive by the value's TYPE, not
            # competitors. (Same shape as Badge, bindable on ``label``
            # and accepting a Component.)
            children.append(
                Element(
                    tag="span",
                    attrs={"class": label_class},
                    children=(self.emit_text_slot(custom_label),),
                )
            )
        elif show_label and not indeterminate:
            if value_binding is not None:
                # Reactive percentage tracking the bound value. SSR
                # snapshot as child text so the span shows the right
                # percentage before the runtime boots.
                label_attrs = {
                    "class": label_class,
                    "bz-text": (
                        f"Math.round((({self.path_of(value_binding)})"
                        f" / {max_val}) * 100) + '%'"
                    ),
                }
                children.append(
                    Element(
                        tag="span",
                        attrs=label_attrs,
                        children=(TextNode(f"{int(round(ssr_pct))}%"),),
                    )
                )
            else:
                children.append(
                    Element(
                        tag="span",
                        attrs={"class": label_class},
                        children=(TextNode(f"{int(round(ssr_pct))}%"),),
                    )
                )

        # ── Root ─────────────────────────────────────────────────────
        attrs = self.emit_attrs()
        attrs["class"] = self.compose_class(
            "root", apply_variant_size_modifiers=False
        )
        attrs.setdefault("role", "progressbar")
        attrs.setdefault("aria-valuemin", "0")
        attrs.setdefault("aria-valuemax", str(int(max_val)))
        if not indeterminate:
            # SSR snapshot (setdefault) + reactive ``bz-attr:`` half so
            # screen readers see the value pre-boot AND track mutations —
            # otherwise a11y freezes at the SSR value while the visual
            # fill (bound via ``bz-attr:style``) moves on.
            attrs.setdefault("aria-valuenow", str(int(float(value_raw or 0))))
            if value_binding is not None:
                attrs["bz-attr:aria-valuenow"] = (
                    f"Math.round(Number({self.path_of(value_binding)}) || 0)"
                )
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))
