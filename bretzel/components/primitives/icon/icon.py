"""``Icon`` — Iconify wrapper, set-agnostic.

Renders the ``<iconify-icon>`` web component. Names without a prefix
are resolved against the active theme's default set
(``ICON_THEME["set"]`` — ``lucide`` out of the box) ; names with a
``set:icon`` prefix flow through verbatim. Sizing is done in ``em``
units via the wrapper's ``font-size`` so the glyph scales with the
size class.

The shell ships the iconify-icon CDN script (``shell.py``) so the
custom element is registered before the first paint.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.icon.theme import ICON_THEME
from bretzel.core.tree import Element


class Icon(Component):
    """Inline icon. ``name`` accepts ``"save"`` (resolved against the
    theme's default set) or ``"lucide:save"`` (explicit set)."""

    THEME: ClassVar[dict[str, Any]] = ICON_THEME
    THEME_KEY: ClassVar[str] = "icon"
    DEFAULT_TAG: ClassVar[str] = "iconify-icon"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — the icon name. Visual axes (size /
    # color / set / style) are design-time. ``name`` is the first
    # positional arg AND a reactive_prop (so the check fires on it).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("name",)

    name: str = reactive_prop(default="")
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="current", emit_attr=False)
    set: str | None = reactive_prop(default=None, emit_attr=False)
    # ⚠️ ``icon_style``, PAS ``style`` : ``style=`` fait partie des kwargs
    # universels que ``Component.__init__`` absorbe (classes / id / attrs /
    # visible / tooltip / style / tag). Il les ``pop`` AVANT le routage
    # vers les reactive_prop, donc une prop nommée ``style`` ne peut
    # jamais recevoir de valeur. Tant que ce paramètre s'appelait
    # ``style``, il était mort des deux côtés : le suffixe Iconify
    # n'atteignait jamais le glyphe, et la valeur partait en CSS inline
    # invalide (``style="bold"``). Le playground l'exerçait sur 4 icônes
    # Phosphor, sans effet. Audit F27 ; gaté par
    # ``test_no_universal_kwarg_shadowing``.
    icon_style: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        name: str | None = None,
        *,
        size: str | None = None,
        color: str | None = None,
        set: str | None = None,
        icon_style: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            name=name, size=size, color=color, set=set,
            icon_style=icon_style, **kwargs,
        )

    def render(self) -> Element:
        theme = self._resolved_theme()
        explicit_set = self._reactive_values.get("set")
        explicit_style = self._reactive_values.get("icon_style")
        default_set = explicit_set or theme.get("set", "lucide")
        default_style = explicit_style or theme.get("style")

        cls_string = self.compose_class("root")
        attrs = self.emit_attrs()
        attrs["class"] = cls_string

        # The iconify-icon web component reads its glyph from ``icon``, not
        # ``name`` — release the root's claim so ``icon`` / ``bz-attr:icon``
        # below own the attribute exclusively.
        self.release_root_attr("name", attrs)

        name_binding = self._binding_metadata.get("name")
        if name_binding is not None:
            # Reactive : emit BOTH a static ``icon=`` (SSR fallback from the
            # binding's underlying value) AND a ``bz-attr:icon=`` the runtime
            # re-evaluates live. Without the static fallback the iconify-icon
            # element has no glyph between SSR and runtime boot.
            from bretzel.core.escape import RawAttrValue
            from bretzel.runtime.protocol import BZ_ATTR_PREFIX
            name_js = self.path_of(name_binding)
            style_arg = (
                "null" if not default_style
                else f"'{default_style}'"
            )
            # SSR fallback stored in ``_reactive_values["name"]`` at
            # construction ; may be empty for fresh bindings — only emit when
            # present.
            ssr_name = self._reactive_values.get("name") or ""
            if ssr_name:
                attrs["icon"] = self._resolve_name(
                    ssr_name, default_set, default_style
                )
            attrs[f"{BZ_ATTR_PREFIX}icon"] = RawAttrValue(
                f"$bz._resolveIcon({name_js}, '{default_set}', {style_arg})"
            )
        else:
            name = self._reactive_values.get("name") or ""
            attrs["icon"] = self._resolve_name(name, default_set, default_style)
        return Element(tag=self._tag, attrs=attrs, children=())

    @staticmethod
    def _resolve_name(name: str, default_set: str, default_style: Any) -> str:
        """Translate a bare icon name into the full ``set:name`` Iconify form.
        Names that already contain a colon flow through verbatim. Phosphor /
        Tabler get their style suffix appended (``-bold``, ``-fill``…)."""
        if not name:
            return ""
        if ":" in name:
            # Full form — caller already chose a set.
            return name
        full = f"{default_set}:{name}"
        if default_style and default_set in ("phosphor", "tabler"):
            full = f"{full}-{default_style}"
        return full
