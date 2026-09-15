"""``Tooltip`` — text panel shown on hover / focus of a wrapped trigger.

Usage as a context manager wrapping the trigger ::

    with ui.tooltip("Reclaim 30% of your quota"):
        ui.button("Free up space", on_click=...)

The panel **teleports to ``<body>`` via ``bz-teleport``** at init —
no ancestor's ``overflow-hidden`` (accordion body clip, sticky page
header, table cell, …) can clip it because the panel isn't a
descendant of any of them at the DOM level. Positioning rides
``$bz.helpers.floating`` (``position: fixed``, main-axis flip +
cross-axis clamp), so the panel follows the trigger across scrolls
and reflows.

Works on hover AND keyboard focus so the affordance is keyboard-
accessible. The panel is ``pointer-events-none`` so it never
intercepts clicks meant for the trigger or siblings underneath.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop, stamp_display_none
from bretzel.components.base._wiring import (
    anchored_panel_effect,
    expand_fit_wrapper,
    server_sync_marker,
    teleport_to_body,
    trigger_is_full_width,
)
from bretzel.components.overlay.tooltip.theme import TOOLTIP_THEME
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.state.scopes.client import ClientBinding


class Tooltip(Component):
    """Hover-/focus-revealed text panel."""

    THEME: ClassVar[dict[str, Any]] = TOOLTIP_THEME
    THEME_KEY: ClassVar[str] = "tooltip"
    # hints, dynamic descriptions). Position/delay/color are
    # design-time. The text is passed as the first positional arg.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("text",)

    # Default ``auto`` = best-fit : ``$bz.helpers.floating`` picks the
    # roomiest side that fits (preference bottom → top → right → left)
    # and the arrow follows via ``data-side``. Apps can still pin a side
    # per-tooltip (``position="right"`` for a sidebar rail item that must
    # open away from the rail, etc.) — the pinned side then flips to its
    # opposite only when it lacks room.
    position: str = reactive_prop(default="auto", emit_attr=False)
    #: Le budget TOTAL, du survol au texte lisible. C'est ce nombre
    #: qui se ressent — pas le délai seul.
    #:
    #: Le tooltip est le SEUL de la famille à payer deux attentes qui
    #: s'AJOUTENT : ce délai, PUIS le fondu d'apparition. Écrire 300
    #: dans ``delay`` en donnait donc 450 à l'écran, et un survol qui
    #: met une demi-seconde à répondre se lit comme une panne, pas
    #: comme une garde anti-déclenchement. Rapporté à l'usage le
    #: 2026-09-04.
    REVEAL_BUDGET_MS: ClassVar[int] = 300

    #: La durée du fondu, en miroir du ``duration-75`` du thème.
    #: ⚠️ Les deux DOIVENT rester d'accord — le budget se répartit
    #: entre eux, donc changer la classe sans changer ce nombre
    #: allongerait le total en silence. Gardé par
    #: ``test_the_tooltip_budget_matches_its_fade``.
    FADE_MS: ClassVar[int] = 75

    #: Ce qu'on attend AVANT de commencer à peindre : le budget moins
    #: le fondu. Dérivé, jamais recopié — c'est la soustraction faite
    #: de tête qui redérive.
    DEFAULT_DELAY_MS: ClassVar[int] = REVEAL_BUDGET_MS - FADE_MS

    delay: int = reactive_prop(default=DEFAULT_DELAY_MS, emit_attr=False)
    # ``color="text"`` = neutral dark default ; any theme color works
    # (semantic info/success/warning/error or palette primary/muted/...).
    color: str = reactive_prop(default="text", emit_attr=False)

    def __init__(
        self,
        text: str | ClientBinding | None = None,
        *,
        position: str | None = None,
        delay: int | None = None,
        color: str | None = None,
        enabled: bool | ClientBinding | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            position=position,
            delay=delay,
            color=color,
            **kwargs,
        )
        # ``enabled`` gates whether hover/focus actually reveals the panel.
        # ``None`` (default) → always on. Accepts a literal ``bool``, a
        # ``ClientBinding`` (reactive server-driven flag), or a raw client
        # expression string (escape hatch — e.g. a DOM/media-query guard
        # like the Sidebar's "only in the collapsed rail"). Evaluated in
        # ``_show()`` against the tooltip root's scope (``$el`` = the
        # trigger wrapper), so it can read ancestors via ``$el.closest``.
        self._enabled: bool | ClientBinding | str | None = enabled
        # ``text`` accepts a literal string, a ``ClientBinding`` (reactive
        # panel content), or a Component. ``adopt_slot`` détache un Component
        # (sinon rendu 2×) et laisse passer string / ClientBinding intacts.
        # ``ClientBinding.__bool__`` LÈVE, donc le ``or ""`` est réservé au
        # cas non-binding.
        adopted = Component.adopt_slot(text)
        if isinstance(adopted, (ClientBinding, Component)):
            self._text: str | ClientBinding | Component = adopted
        else:
            self._text = adopted or ""

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})

        position = self._reactive_values.get("position") or "auto"
        delay = int(
            self._reactive_values.get("delay") or self.DEFAULT_DELAY_MS
        )
        # Pre-JS default side for the arrow (``floating`` overwrites
        # ``data-side`` on the first open) : the pinned side if any, a
        # sensible ``bottom`` for the ``auto`` case.
        initial_side = "bottom" if position == "auto" else position

        # ── Panel : the floating tooltip ─────────────────────────────
        # ``fixed`` (not ``absolute``) because the panel is teleported
        # to ``<body>`` — ancestor positioned containers no longer
        # exist for it. Coordinates are JS-set on every show from the
        # trigger's ``getBoundingClientRect()``.
        # ``group`` names the panel so the arrow's ``group-data-[side=…]``
        # variants can read the ``data-side`` that ``floating`` writes.
        panel_class = self.compose_class(
            "panel",
            apply_variant_size_modifiers=False,
        ).replace("absolute", "fixed") + " group"

        # ``emit_text_slot`` gère les 4 formes d'un slot textuel (string /
        # ClientBinding → span+bz-text via ``path_of`` / Component → rendu
        # en place / vide → None). Le ``or TextNode("")`` couvre le slot vide
        # (le panel existe toujours, sans texte).
        text_node: Node = self.emit_text_slot(self._text) or TextNode("")
        # Arrow stays absolute-positioned RELATIVE TO THE PANEL. Its
        # per-side anchor lives in the ``arrow`` slot as four
        # ``group-data-[side=…]`` variants — the one matching the panel's
        # runtime ``data-side`` applies. No SSR side lookup : the arrow
        # follows the flip / best-fit. Always present (no arrowless mode).
        panel_children: list[Node] = [text_node]
        arrow_class = self.compose_class(
            "arrow",
            apply_variant_size_modifiers=False,
        )
        panel_children.append(
            Element(
                tag="div",
                attrs={"class": arrow_class, "aria-hidden": "true"},
                children=(),
            )
        )
        panel_attrs: dict[str, Any] = {
            "class": panel_class,
            "role": "tooltip",
            "bz-ref": "bzpanel",
            # Initial arrow side before ``floating`` runs (it overwrites
            # ``data-side`` on the first open with the resolved side).
            "data-side": initial_side,
            # display toggle + floating attach against the trigger
            # root (anchored on its firstElementChild, the real
            # trigger box). Anchored on ``bzroot`` (the tooltip root).
            "bz-effect": anchored_panel_effect(
                "open", position, trigger_ref="bzroot"
            ),
        }
        # FOUC : pre-stamp hidden (tooltip starts closed).
        stamp_display_none(panel_attrs)
        panel = Element(
            tag="div",
            attrs=panel_attrs,
            children=tuple(panel_children),
        )
        # Teleport the panel under ``<body>`` (shared helper) : ancestor
        # ``overflow`` / stacking traps lose power over it, while it stays
        # bound to this tooltip's origin scope.
        teleport = teleport_to_body(panel, self)

        # ── Root wrapper : the trigger lives inside as children ──────
        # Carries the open flag + show/hide/position methods.
        root_slot = slots.get("root", "")
        if trigger_is_full_width(self._children):
            # A full-width trigger must expand the ``w-fit`` wrapper or it
            # collapses to content width. Shared with Popover / Dropdown.
            root_slot = expand_fit_wrapper(root_slot)
        attrs = self.emit_attrs()
        # ``classes=`` posé par le wrap métaclasse — pas ici (doublon).
        attrs["class"] = root_slot
        attrs["bz-data"] = _build_bzdata(delay, self._enabled_expr())
        attrs["bz-ref"] = "bzroot"
        attrs["bz-on:mouseenter"] = "_show()"
        attrs["bz-on:mouseleave"] = "_hide()"
        # Keyboard a11y : focusing inside (e.g. tabbing onto the
        # button) reveals the tooltip without delay.
        attrs["bz-on:focusin"] = "_show()"
        attrs["bz-on:focusout"] = "_hide()"

        children = list(self._render_children())
        children.append(teleport)
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))

    def _enabled_expr(self) -> str:
        """Resolve ``enabled`` to a JS predicate for ``_show()``'s guard.

        ``None`` → ``"true"`` (always reveal). A literal ``bool`` bakes
        ``"true"``/``"false"``. A :class:`ClientBinding` reads the reactive
        store path. A raw string is used verbatim (caller owns the
        expression — it's evaluated in the tooltip root's scope).
        """
        enabled = self._enabled
        if enabled is None:
            return "true"
        if isinstance(enabled, bool):
            return "true" if enabled else "false"
        if isinstance(enabled, ClientBinding):
            # ``path_of`` already unifies the ClientBinding /
            # ClientExpression resolution (the latter is a subclass and
            # must NOT get a second ``$bz.state.`` prefix) — reuse it
            # instead of hand-rolling the path here.
            return self.path_of(enabled)
        if not isinstance(enabled, str):
            # ⚠️ Une valeur BACKÉE SERVEUR n'est pas un ``bool`` au sens
            # d'``isinstance`` : ``ServerState`` la tamponne en
            # ``_BoundBool``, une sous-classe d'``int`` qui porte son
            # ``field_name``. Le test ``isinstance(enabled, bool)``
            # ci-dessus la rate donc, et le ``str()`` final émettait le
            # littéral PYTHON ``True`` dans du JavaScript — d'où un
            # ``ReferenceError: True is not defined`` au premier survol,
            # qui tuait l'effet.
            #
            # Trouvé au navigateur le 2026-07-29, sur la page tooltip du
            # playground (``enabled=state.enabled``). Bug ANTÉRIEUR à la
            # bascule vers ``$bz.tooltip.scope`` : l'ancien builder
            # interpolait la même expression dans ``if (!(True)) return;``.
            # Les 9 400 tests Python étaient verts — seul un vrai
            # navigateur pouvait le voir.
            return "true" if enabled else "false"
        return str(enabled)

    # ── Full-width detection ───────────────────────────────────────────

    # NB : ``_build_bzdata`` lives at module scope below ; it composes
    # the ``bz-data`` body that holds the open flag + the hover
    # debounce timer. Positioning is owned by the panel's
    # ``anchored_panel_effect`` (``$bz.helpers.floating``).

# ── bz-data builder ─────────────────────────────────────────────────────────


def _build_bzdata(delay_ms: int, enabled_expr: str = "true") -> str:
    """Compose the ``bz-data`` object literal for the tooltip root.

    - ``open`` (bool) : drives the panel's display + floating effect.
    - ``_t`` (timer handle) : pending hover debounce.
    - ``_show()`` : bails when ``enabled_expr`` is falsy ; otherwise
      starts the debounce ; on fire flips ``open`` (the panel's
      ``bz-effect`` then shows + positions it via floating).
    - ``_hide()`` : clears the debounce + closes.

    ``enabled_expr`` is a JS predicate evaluated on each hover/focus
    (``"true"`` by default). It's checked at SHOW time, not mount time,
    so a live condition (collapse state, media query) is honoured as it
    changes. Positioning is owned by ``$bz.helpers.floating`` (engaged by
    the panel's ``anchored_panel_effect``).
    """
    # ``_show`` / ``_hide`` vivent une seule fois dans ``$bz.tooltip.scope``
    # (``bretzel/runtime/_src/16_accordion.js``). Ce builder les sérialisait
    # par instance en y CUISANT la configuration — le corps contenait
    # ``if (!(true)) return;`` et le délai en littéral, donc deux tooltips
    # de délais différents produisaient deux CODES différents.
    #
    # ``_enabled`` doit rester une EXPRESSION relue à chaque survol — une
    # condition vivante (état replié, media query, ClientBinding) doit être
    # honorée au fil de ses changements. La bascule « config en données »
    # l'avait pourtant émis en CHAMP (``_enabled: <expr>``), ce qui produit
    # exactement le contraire : un champ est évalué une seule fois, hors
    # effet, et ``absorb`` en emballe le snapshot dans un signal découplé du
    # store. Le commentaire promettait le survol, le code figeait au
    # montage. Seul un corps de méthode est relu — d'où la surcharge de la
    # constante ``_enabled()`` du slab. ``_delay`` reste un champ : c'est un
    # littéral server-side, donc une vraie donnée.
    enabled_override = (
        f"_enabled() {{ return !!({enabled_expr}); }},"
        if enabled_expr != "true"
        else ""
    )
    # ``_delay`` est de la CONFIG (server-owned) → re-semé sans condition.
    # ``open`` et ``_t`` NON : état client (le panneau ouvert, le timer en
    # vol). Les re-semer refermerait un tooltip affiché à chaque swap voisin.
    return (
        "{...$bz.tooltip.scope,"
        "open: false,"
        "_t: null,"
        f"{enabled_override}"
        f"_delay: {delay_ms},"
        f"{server_sync_marker('_delay', enabled=True).strip()}"
        "}"
    )
