"""``Calendar`` — month-grid date picker, single or range.

Standalone primitive used directly OR wrapped by
``ui.date_picker`` / ``ui.date_range_picker``. Renders as a
**`<bz-calendar>` custom element** (cf. ``bretzel/runtime/_src/07_calendar.js``)
which owns its internal day-grid state ; configuration lives in
observed HTML attributes that idiomorph can morph freely on every
server refresh. Each attribute change triggers
``attributeChangedCallback`` in JS, which re-renders the internal
day grid.

This is the Web Component escape hatch documented in
``02_morph_hook.js`` philosophy : stateful widgets where the
"scope init-once" friction with idiomorph is intractable get to be
custom elements with their own attribute observers. Iconify-icon
already follows this pattern.

DatePicker et DateRangePicker ne sont pas des custom elements : leur racine
est un ``<div>`` qui héberge un ``<bz-calendar>`` et se synchronise avec lui
par ``bz-effect`` + ``setAttribute``.

Two modes :

- ``picker`` (default) : single date pick. ``value: date`` (or ``None``).
- ``range`` : start + end pick. ``value: tuple[date, date]`` (or ``None``).
  First click sets start ; second click closes the range. Hovering
  between the two highlights the preview.

Form integration : ``AUTONAME_FROM = "value"`` derives the HTML
``name`` from the bound field. A hidden ``<input type="hidden">``
child of ``<bz-calendar>`` serialises the value (ISO ``YYYY-MM-DD``
for single, JSON-stringified ISO pair for range) and the relocated
change handler rides onto it.

Runtime notes :

- Only the Python plumbing AROUND ``<bz-calendar>`` is framework-wired ;
  the custom element itself (day grid, range preview, dispatch,
  ``bz-set`` / ``bz-prev-month`` / ``bz-next-month`` listeners,
  ``$bz.state`` write-back) is untouched.
- The root's header coordination state is ``bz-data="{year, month}"``.
  ``bz-attr:month`` propagates a header dropdown / prev-next click onto
  the observed ``month`` attribute, firing ``attributeChangedCallback`` ;
  ``bz-on:month-change`` syncs the element's internal nav back into
  ``year`` / ``month``.
- The inline month / year dropdowns use their own ``bz-data="{open:
  false}"`` + ``bz-init`` clickOutside/escapeKey dismiss.
- A server-callable ``on_change`` is relocated to the hidden input
  (which fires a bubbling synthetic ``change``) ; a string ``on_change``
  rides ``bz-on:change`` on the root (the synthetic ``change`` bubbles).

Imperative API (cf. ``imperative-api.md``) :

- ``.set(value)`` — write-through binding if any, else dispatches
  ``bz-set`` CustomEvent on the element (the custom element listens
  for it and updates its state).
- ``.clear()`` — write ``None`` / empty pair.
- ``.focus()`` / ``.blur()`` — focus the first focusable day cell.
- ``.next_month()`` / ``.prev_month()`` — dispatch ``bz-next-month`` /
  ``bz-prev-month`` CustomEvent on the element.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentDefinitionError,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base._wiring import (
    SERVER_ACTION_ATTRS,
    anchored_dismiss_init,
    bool_attr,
    retrigger,
    server_sync_marker,
    theme_context,
    trigger_event,
)
from bretzel.components.inputs._wiring import date_to_iso
from bretzel.components.inputs.calendar.theme import CALENDAR_THEME
from bretzel.core.tree import Element, HtmlNode, Node
from bretzel.render import template, text

# ───────────────────────────────────────────────────────────────────────────
# Public defaults — English month/weekday names (Sunday-canonical order)
# ───────────────────────────────────────────────────────────────────────────


DEFAULT_WEEKDAY_NAMES_SUN_FIRST: tuple[str, ...] = (
    "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat",
)
"""Weekday names indexed by ``Date.getDay()`` (0 = Sunday, … 6 = Saturday).

``weekstart=`` rotates this tuple at render time. Override per call site
via ``weekday_names=`` (still in Sunday-first order, the rotation is the
component's job)."""

DEFAULT_MONTH_NAMES: tuple[str, ...] = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
"""Month names indexed 0..11 — matches ``Date.getMonth()``."""


# ───────────────────────────────────────────────────────────────────────────
# Pure helpers — exposed for tests, SSR, and custom date pickers
# ───────────────────────────────────────────────────────────────────────────


def compute_month_grid(
    year: int,
    month: int,
    weekstart: int = 1,
    today: _dt.date | None = None,
) -> list[list[dict[str, Any]]]:
    """Return 6 rows × 7 cells covering the displayed month.

    Mirror of the JS computation inside ``<bz-calendar>`` — used for
    SSR-rendered initial DOM and for tests."""
    weekstart = weekstart % 7
    today = today or _dt.date.today()
    first = _dt.date(year, month, 1)
    first_dow_sun = (first.weekday() + 1) % 7
    offset = (first_dow_sun - weekstart) % 7
    grid: list[list[dict[str, Any]]] = []
    for week in range(6):
        row: list[dict[str, Any]] = []
        for col in range(7):
            cell_date = first + _dt.timedelta(days=week * 7 + col - offset)
            row.append({
                "date": cell_date,
                "in_current_month": cell_date.month == month,
                "is_today": cell_date == today,
            })
        grid.append(row)
    return grid


def format_month_label(
    year: int,
    month: int,
    month_names: tuple[str, ...] | list[str] | None = None,
) -> str:
    """``"<MonthName> <Year>"`` (e.g. ``"March 2026"``)."""
    names = month_names or DEFAULT_MONTH_NAMES
    return f"{names[month - 1]} {year}"


def rotate_weekday_names(
    weekday_names: tuple[str, ...] | list[str] | None = None,
    weekstart: int = 1,
) -> list[str]:
    """Return the 7 weekday names rotated so ``weekstart`` comes first."""
    names = list(weekday_names or DEFAULT_WEEKDAY_NAMES_SUN_FIRST)
    weekstart = weekstart % 7
    return names[weekstart:] + names[:weekstart]


def _date_to_iso(value: Any) -> str:
    """``Calendar``'s date coercion — the shared one, bound to this
    component's name for the error message (audit F50 : les trois
    composants de la famille date en portaient une copie identique)."""
    return date_to_iso(value, owner="Calendar")


#: Le format que la grille compare : ``YYYY-MM-DD``, exactement.
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def normalise_marks(marks: Any) -> dict[str, int]:
    """``marks=`` → ``{"2026-08-14": 3}``, sous ses deux formes d'appel.

    Deux formes parce que les deux besoins existent, et que la plus
    simple ne doit pas payer pour l'autre :

    - un ITÉRABLE de dates — « ces jours-là ont quelque chose » ;
    - un DICTIONNAIRE date → entier — « ce jour-là en a trois ».

    L'entier couvre le booléen, donc une seule prop suffit : c'est
    l'arbitrage pris avec l'utilisateur le 2026-08-25. Il n'est pas
    dessiné (une pastille reste une pastille, à 24 px de cellule un
    chiffre de plus serait illisible) mais il est ANNONCÉ — le nom
    accessible de la case le porte, et un survol le montre.

    Un compte nul retire la marque plutôt que d'en poser une vide : un
    dictionnaire construit par un ``Counter`` en contient, et lever
    dessus obligerait chaque appelant à le filtrer.
    """
    if not marks:
        return {}
    pairs = (
        marks.items() if hasattr(marks, "items")
        else ((day, 1) for day in marks)
    )
    out: dict[str, int] = {}
    for day, count in pairs:
        iso = _date_to_iso(day)
        # ⚠️ ``date_to_iso`` rend une chaîne TELLE QUELLE — c'est ce qui
        # laisse passer un binding client, et c'est voulu là-bas. Ici la
        # clé finit dans un dictionnaire indexé par date : une chaîne
        # libre n'y correspondrait à aucune case, en silence. On vérifie
        # donc la FORME.
        if not _ISO_DAY.fullmatch(iso or ""):
            raise ComponentDefinitionError(
                f"marks : {day!r} n'est pas une date. Attendu un "
                f"``datetime.date`` ou une chaîne ISO ``YYYY-MM-DD``."
            )
        if not isinstance(count, int) or isinstance(count, bool):
            # ``bool`` est un ``int`` en Python, et ``{jour: True}`` est
            # une faute de frappe crédible pour ``[jour]``. La laisser
            # passer donnerait « 1 » à l'écran sans que personne le
            # veuille.
            raise ComponentDefinitionError(
                f"marks[{day!r}] doit être un entier, reçu {count!r}. "
                f"Pour un simple « il se passe quelque chose », passe une "
                f"liste de dates plutôt qu'un dictionnaire."
            )
        if count < 0:
            raise ComponentDefinitionError(
                f"marks[{day!r}] = {count} : un compte négatif n'a pas de "
                f"rendu possible."
            )
        if count:
            out[iso] = count
    return dict(sorted(out.items()))


def _disabled_dates_to_iso(
    disabled_dates: list[_dt.date] | None,
) -> list[str]:
    return [_date_to_iso(d) for d in (disabled_dates or [])]


# ───────────────────────────────────────────────────────────────────────────
# Component
# ───────────────────────────────────────────────────────────────────────────


# ``week`` (août 2026) rend une DATE SCALAIRE comme ``picker`` — le
# premier jour de la semaine cliquée, selon ``weekstart``. Il emprunte
# donc la même branche de sérialisation, et se distingue uniquement par
# ce que le custom element fait du clic (recalage sur le début de
# semaine) et par son surlignage (la ligne entière, rendue avec le
# vocabulaire de bande DÉJÀ écrit pour ``range`` — une semaine EST une
# plage fermée de sept jours).
#
# ``month`` (août 2026) est le seul mode qui ne rend PAS des jours : une
# grille d'année de 12 cellules, et une valeur en ``"YYYY-MM"``. Les
# flèches du header y avancent d'un AN, et le sélecteur de mois y est
# retiré — il ferait doublon avec la grille elle-même.
#: Plafond du menu de saut d'année. Le défaut, sans ``min`` ni ``max``,
#: est aujourd'hui ± 10 ans — soit 21 entrées. 200 laisse passer TOUS les
#: usages réels (une date de naissance remonte à ~120 ans, un registre
#: historique à quelques siècles) et coupe le cas pathologique, qui n'est
#: pas un usage : une étendue de 1 900 ans vient d'un ``min`` mal formé,
#: pas de quelqu'un qui veut ces années-là.
#:
#: Gardé par ``tests/consistency/test_a_year_dropdown_stays_bounded.py``.
MAX_YEARS_IN_DROPDOWN = 200

_VALID_MODES = ("picker", "range", "week", "month")

# Native HTMX action attrs a server-callable ``on_change`` lands on the
# root via ``emit_attrs`` ; relocated wholesale onto the hidden input
# that carries name+value (the dispatcher reads form-data from there).
# The custom element fires a bubbling synthetic ``change`` on the hidden
# input whenever the value mutates, so ``hx-trigger="change"`` fires.
_ACTION_ATTRS = SERVER_ACTION_ATTRS


class Calendar(Component):
    """Month-grid date picker, single or range. Web Component-backed."""

    THEME: ClassVar[dict[str, Any]] = CALENDAR_THEME
    THEME_KEY: ClassVar[str] = "calendar"
    DEFAULT_TAG: ClassVar[str] = "bz-calendar"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = (
        "value", "month", "min", "max", "disabled",
    )
    # ``next_month`` / ``prev_month`` étaient livrées et câblées mais pas
    # déclarées — donc absentes du catalogue ``ui.*`` de la doc, qui
    # énumère cette ClassVar (audit F20/F21). Même idiome que les
    # ``increment`` / ``decrement`` de NumberInput.
    IMPERATIVE: ClassVar[tuple[str, ...]] = (
        "set", "clear", "focus", "blur", "next_month", "prev_month",
    )
    EVENTS: ClassVar[tuple[str, ...]] = (
        "change", "month_change", "focus", "blur",
    )

    name: str | None = reactive_prop(default=None, emit_attr=False)
    # BINDABLE props ride emit_attr=True so a ``value=binding`` /
    # ``month=binding`` / etc. registers as ``bz-attr:<attr>="$bz.state.…"``
    # — the directive mutates the HTML attribute when the bound state
    # changes, which fires the custom element's ``attributeChangedCallback``
    # and re-renders. Final attribute values for non-trivial shapes (range
    # JSON, ISO dates) are overridden manually below ``emit_attrs()``.
    value: Any = reactive_prop(default=None, writes=True, names_field=True)
    month: Any = reactive_prop(default=None, writes=True, scope_keys=("year", "month"))
    min: Any = reactive_prop(default=None)
    max: Any = reactive_prop(default=None)
    disabled: bool = reactive_prop(default=False)
    # Non-bindable / design-time props : ``emit_attr=False``
    # because they're either irrelevant to the custom element
    # (color/size — encoded in the data-bz-theme blob) or carried
    # via dedicated attributes set explicitly in ``render()``
    # (mode/weekstart/required which never bind).
    mode: str = reactive_prop(default="picker", emit_attr=False)
    weekstart: int = reactive_prop(default=1, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        value: Any = None,
        *,
        mode: str | None = None,
        min: Any = None,
        max: Any = None,
        disabled_dates: list[_dt.date] | None = None,
        marks: Any = None,
        month: Any = None,
        weekstart: int | None = None,
        weekday_names: list[str] | None = None,
        month_names: list[str] | None = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_month_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        if mode is not None and mode not in _VALID_MODES:
            raise ComponentDefinitionError(
                f"Calendar mode={mode!r} not in {_VALID_MODES}"
            )
        # ``None`` quand l'appelant n'a rien dit — et surtout PAS la
        # table anglaise. Ce défaut-là rendait « August / MON TUE WED »
        # à toute app quelle que soit sa langue, et la seule prise était
        # de repasser les 19 chaînes À CHAQUE MONTAGE (trois fois sur un
        # seul écran du CRM). Sans liste explicite, c'est le navigateur
        # qui nomme, depuis ``<html lang>`` — cf. ``06_locale.js``.
        self._weekday_names = list(weekday_names) if weekday_names else None
        self._month_names = list(month_names) if month_names else None
        if self._weekday_names is not None and len(self._weekday_names) != 7:
            raise ComponentDefinitionError(
                f"weekday_names must have 7 entries, got "
                f"{len(self._weekday_names)}"
            )
        if self._month_names is not None and len(self._month_names) != 12:
            raise ComponentDefinitionError(
                f"month_names must have 12 entries, got "
                f"{len(self._month_names)}"
            )
        self._disabled_dates = list(disabled_dates or [])
        self._marks = normalise_marks(marks)

        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            name=name, value=value, month=month,
            mode=mode, min=min, max=max,
            weekstart=weekstart,
            color=color, size=size,
            disabled=disabled, required=required,
            on_change=on_change,
            on_month_change=on_month_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )

    # ── Imperative write-only API ─────────────────────────────────────

    def set(self, value: Any) -> str:
        if isinstance(value, _dt.date):
            value = value.isoformat()
        elif isinstance(value, (list, tuple)):
            value = [
                v.isoformat() if isinstance(v, _dt.date) else v
                for v in value
            ]
        return self._value_command(value)

    def clear(self) -> str:
        return self.set(None)

    def focus(self) -> str:
        return f"document.getElementById('{self.id}').focus()"

    def blur(self) -> str:
        return f"document.getElementById('{self.id}').blur()"

    def next_month(self) -> str:
        binding = self._binding_metadata.get("month")
        if binding is not None:
            return (
                f"(() => {{"
                f"const d = new Date({binding.binding_path()} || new Date());"
                f"d.setMonth(d.getMonth() + 1);"
                f"d.setDate(1);"
                f"{binding.binding_path()} = "
                f"d.getFullYear() + '-' + "
                f"String(d.getMonth() + 1).padStart(2, '0') + '-01';"
                f"}})()"
            )
        return self._dispatch_command("bz-next-month")

    def prev_month(self) -> str:
        binding = self._binding_metadata.get("month")
        if binding is not None:
            return (
                f"(() => {{"
                f"const d = new Date({binding.binding_path()} || new Date());"
                f"d.setMonth(d.getMonth() - 1);"
                f"d.setDate(1);"
                f"{binding.binding_path()} = "
                f"d.getFullYear() + '-' + "
                f"String(d.getMonth() + 1).padStart(2, '0') + '-01';"
                f"}})()"
            )
        return self._dispatch_command("bz-prev-month")


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, color = theme_context(self)
        size_map = sizes.get(size_key, sizes.get("md", {}))
        mode = self._reactive_values.get("mode") or "picker"
        is_range = mode == "range"
        is_month_mode = mode == "month"
        ws_raw = self._reactive_values.get("weekstart")
        weekstart = (
            int(ws_raw) if ws_raw not in (None, "") else 1
        ) % 7
        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))
        # When ``disabled`` rides a ClientBinding, the header controls
        # (nav arrows + month/year dropdowns) are rendered ONCE at SSR —
        # a frozen literal ``disabled=False`` would leave them live while
        # the binding flips True (the exact Client-playground bug). Pass
        # the binding through so IconButton / the dropdown triggers emit
        # ``bz-attr:disabled`` and toggle reactively ; fall back to the
        # resolved bool for the literal / design-time case.
        disabled_binding = self._binding_metadata.get("disabled")
        disabled_prop: Any = (
            disabled_binding if disabled_binding is not None else disabled
        )
        # The dropdown triggers are raw ``<button>`` (not a Component) so
        # they can't take ``disabled_prop`` directly — spread this instead :
        # a reactive ``bz-attr:disabled`` when bound, a static ``disabled``
        # for the literal case. ``disabled:`` (Tailwind) applies natively
        # on a ``<button>`` so the cursor/opacity feedback follows.
        if disabled_binding is not None:
            _header_disable_attrs: dict[str, Any] = {
                "bz-attr:disabled": self.path_of(disabled_binding)
            }
        elif disabled:
            _header_disable_attrs = {"disabled": True}
        else:
            _header_disable_attrs = {}

        def _resolve(template: str) -> str:
            return template

        # ── Compose theme classes once ────────────────────────────
        cell_class = " ".join(p for p in (
            _resolve(slots.get("day_cell", "")),
            size_map.get("day_cell", ""),
        ) if p)
        mark_class = " ".join(p for p in (
            _resolve(slots.get("day_mark", "")),
            size_map.get("day_mark", ""),
        ) if p)
        nav_class = " ".join(p for p in (
            slots.get("nav_button", ""),
            size_map.get("nav_button", ""),
        ) if p)
        label_class = " ".join(p for p in (
            slots.get("month_label", ""),
            size_map.get("month_label", ""),
        ) if p)
        weekday_class = " ".join(p for p in (
            slots.get("weekday", ""),
            size_map.get("weekday", ""),
        ) if p)
        chevron_class = (
            "inline-flex shrink-0 justify-center items-center "
            f"align-middle text-current {size_map.get('chevron', 'text-sm')}"
        )

        # Hand the full slot map to the custom element so its JS
        # re-render uses the SAME classes Python composed here. Single
        # source of truth — Python computes, JS executes.
        theme_blob = {
            "header": slots.get("header", ""),
            "month_label": label_class,
            "nav_button": nav_class,
            "weekday_row": slots.get("weekday_row", ""),
            "weekday": weekday_class,
            "week_row": slots.get("week_row", ""),
            "day_cell": cell_class,
            "day_mark": mark_class,
            "chevron_class": chevron_class,
            # Grille d'année du mode ``month``. Composées ici comme les
            # autres — Python compose, JS exécute — pour que la même
            # source de vérité serve les deux types de grille.
            "month_grid": slots.get("month_grid", ""),
            "month_cell": " ".join(p for p in (
                _resolve(slots.get("month_cell", "")),
                size_map.get("month_cell", ""),
            ) if p),
        }

        # ── Determine initial displayed month ─────────────────────
        # Priority : explicit ``month=`` → the SELECTED value's month →
        # today. Opening on the value's month (not today's) is what every
        # date picker does — otherwise a calendar built with a value in
        # another month paints today's grid and the selection is invisible
        # (the "value in June, grid shows July" bug that false-FAILed the
        # clear / focus function tests). A bound value (client/server) is
        # not a literal here, so it correctly falls through to today.
        month_raw = self._reactive_values.get("month")
        if isinstance(month_raw, _dt.date):
            initial_displayed = month_raw.replace(day=1)
        elif isinstance(month_raw, str) and month_raw:
            initial_displayed = _dt.date.fromisoformat(month_raw).replace(day=1)
        else:
            seed = self._reactive_values.get("value")
            if isinstance(seed, (list, tuple)):        # range → open on start
                seed = seed[0] if seed else None
            if isinstance(seed, str) and seed:
                try:
                    seed = _dt.date.fromisoformat(seed)
                except ValueError:
                    seed = None
            seed = seed if isinstance(seed, _dt.date) else None
            initial_displayed = (seed or _dt.date.today()).replace(day=1)

        # ── Initial value (ISO string for picker, JSON pair for range) ─
        raw_value = self._reactive_values.get("value")
        if is_range:
            if isinstance(raw_value, (list, tuple)) and len(raw_value) == 2:
                initial_range_start = _date_to_iso(raw_value[0])
                initial_range_end = _date_to_iso(raw_value[1])
                initial_value_attr = json.dumps(
                    [initial_range_start, initial_range_end]
                )
            else:
                initial_range_start = ""
                initial_range_end = ""
                initial_value_attr = ""
            initial_picker = ""
        elif mode == "month":
            # Valeur en ``"YYYY-MM"``. Une ``date`` est acceptée et
            # TRONQUÉE — le développeur qui passe ``date(2026, 8, 14)``
            # veut visiblement « août 2026 », et refuser lui coûterait un
            # ``.strftime`` pour rien. La chaîne, elle, passe telle
            # quelle : c'est la forme canonique.
            if isinstance(raw_value, _dt.date):
                initial_picker = f"{raw_value.year:04d}-{raw_value.month:02d}"
            else:
                initial_picker = str(raw_value or "")[:7]
            initial_value_attr = initial_picker
            initial_range_start = ""
            initial_range_end = ""
        else:
            initial_picker = _date_to_iso(raw_value) if raw_value else ""
            initial_value_attr = initial_picker
            initial_range_start = ""
            initial_range_end = ""

        value_binding = self._binding_metadata.get("value")
        month_binding = self._binding_metadata.get("month")

        # ── Event handling ─────────────────────────────────────────
        # A **server-callable** ``on_change`` lands its native HTMX
        # action bundle (``hx-post`` + ``hx-trigger`` + …) on the root
        # via ``emit_attrs`` ; relocate the whole bundle to the hidden
        # input — the dispatcher reads ``name`` + ``value`` from the
        # source element to build form data, and those live on the
        # hidden input. The custom element fires a bubbling synthetic
        # ``change`` on the hidden input whenever the value mutates, so
        # ``hx-trigger="change"`` fires there. (Mirror of Select's
        # change relocation.)
        #
        # A **string** ``on_change`` rides ``bz-on:change`` ; it stays
        # on the ``<bz-calendar>`` root because the synthetic ``change``
        # bubbles up to the root where the listener catches it (no
        # name/value read needed for a client string handler).
        #
        # ``month_change`` is dispatched as a CustomEvent on the root.
        # ``emit_attrs`` already produced ``bz-on:month_change`` (string)
        # or the HTMX bundle keyed on ``month_change`` ; rename to the
        # kebab event name ``month-change`` the custom element actually
        # dispatches.
        root_attrs = self.emit_attrs()
        # Autoname (base ``emit_attrs``) injects ``name`` onto the root,
        # but the form-data carrier is the hidden ``<input>`` below
        # (``name`` is derived independently a few lines down). Release it
        # from the ``<bz-calendar>`` root so the name lives in one place.
        self.release_root_attr("name", root_attrs)
        relocated_to_hidden: dict[str, Any] = {}
        # Server-callable bundle — route by the event it fires on. The
        # base emits ONE ``hx-post`` keyed to its event's ``hx-trigger`` :
        #   ``change``       → the hidden input (the value carrier, which
        #                      dispatches a synthetic ``change``) ;
        #   ``month_change`` → stays on the <bz-calendar> root, renamed to
        #                      the kebab ``month-change`` CustomEvent ;
        #   ``focus`` / ``blur`` → stay on the root with their native
        #                      trigger.
        # L'EVENT, pas la chaîne : ``hx-trigger`` porte les modificateurs
        # d'un ``debounce=`` / ``throttle=``. Les deux branches nommées
        # ci-dessous les écrasaient en réécrivant le trigger entier.
        server_trigger = root_attrs.get("hx-trigger", "")
        server_event = trigger_event(root_attrs)
        if "hx-post" in root_attrs:
            bundle = {a: root_attrs.pop(a)
                      for a in _ACTION_ATTRS if a in root_attrs}
            if server_event == "change":
                relocated_to_hidden.update(bundle)
            elif server_event == "month_change":
                bundle["hx-trigger"] = retrigger(server_trigger, "month-change")
                root_attrs.update(bundle)
            else:
                # focus / blur — keep the base's native trigger on the root.
                root_attrs.update(bundle)
        # ``month_change`` STRING form (``bz-on:month_change``) → kebab.
        for ev_attr in list(root_attrs.keys()):
            if ev_attr == "bz-on:month_change":
                root_attrs["bz-on:month-change"] = root_attrs.pop(ev_attr)

        # ── Form-data name (autoname) ─────────────────────────────
        fallback = "value" if relocated_to_hidden else None
        name = self._reactive_values.get("name") or self._derive_field_name() or fallback

        # ── Hidden input (form-data carrier) ──────────────────────
        hidden_nodes: list[Node] = []
        if name or relocated_to_hidden:
            hidden_attrs: dict[str, Any] = {
                "type": "hidden",
                "value": initial_value_attr,
            }
            if name:
                hidden_attrs["name"] = str(name)
            if required:
                hidden_attrs["required"] = True
            hidden_attrs.update(relocated_to_hidden)
            hidden_nodes.append(
                Element(tag="input", attrs=hidden_attrs, children=())
            )

        # ── SSR initial DOM : header + weekday row + EMPTY grid ─────
        # Day cells are NOT pre-rendered in HTML — the custom element
        # fills them on ``connectedCallback`` via the same code path
        # as subsequent ``attributeChangedCallback`` re-renders.
        # Single render path (JS) means : no drift between SSR layout
        # and runtime layout, smaller HTML payload (1700 cells × ~700
        # chars on the playground = ~1 MB saved), and the Tailwind
        # safelist already covers the day-cell classes from the
        # Reference card's color/size demos. Visual : the calendar
        # outline paints immediately, the grid cells appear ~50 ms later
        # when the runtime script runs.
        #
        # ⚠️ La ligne des JOURS a changé de camp le 2026-08-24 : sans
        # ``weekday_names=`` explicite, elle part en sept ``<div>`` VIDES
        # portant un ``bz-text`` — leurs noms viennent d'``Intl``, que
        # seul le navigateur a. Elle apparaît donc avec la grille, pas
        # avant. C'est le prix pour qu'un calendrier parle la langue de
        # l'app, et il ne se paie que sur le chemin par défaut : une
        # liste explicite se rend toujours côté serveur.
        min_raw = self._reactive_values.get("min")
        max_raw = self._reactive_values.get("max")
        min_iso = _date_to_iso(min_raw)
        max_iso = _date_to_iso(max_raw)
        disabled_iso_set = set(
            _disabled_dates_to_iso(self._disabled_dates)
        )

        # ── Python-rendered header : prev IconButton, month dropdown,
        #    year dropdown, next IconButton. We build the dropdowns
        #    inline as Elements (not via ui.dropdown) because :
        #    1. ui.dropdown re-renders the trigger Component internally,
        #       wiping any ``bz-text`` patch we apply to the trigger
        #       Element — labels would never become reactive ;
        #    2. we want a guaranteed ``max-h-64 overflow-y-auto`` on
        #       the panel so 21 year items + tall calendars scroll
        #       cleanly instead of running off the page.
        #    The state still lives in the ``<bz-calendar>`` root's
        #    ``bz-data="{year, month}"`` (see below) ; each inline
        #    dropdown adds its own ``open`` flag.
        from bretzel.components.actions.icon_button import (
            IconButton as _IconButton,
        )
        from bretzel.core.tree import TextNode as _TextNode

        today_year_for_range = _dt.date.today().year
        if isinstance(min_raw, _dt.date):
            year_min_hd = min_raw.year
        elif min_iso:
            year_min_hd = int(min_iso.split("-")[0])
        else:
            year_min_hd = today_year_for_range - 10
        if isinstance(max_raw, _dt.date):
            year_max_hd = max_raw.year
        elif max_iso:
            year_max_hd = int(max_iso.split("-")[0])
        else:
            year_max_hd = today_year_for_range + 10
        year_min_hd = min(year_min_hd, initial_displayed.year)
        year_max_hd = max(year_max_hd, initial_displayed.year)

        # ── La grille d'années est BORNÉE ────────────────────────────
        #
        # Le menu ci-dessous rend un ``<button>`` par année, en dur dans
        # le DOM. Sans plafond, l'étendue vient telle quelle de ``min`` /
        # ``max`` — et ``int("137".split("-")[0])`` vaut l'an 137.
        #
        # Mesuré le 2026-08-27 :
        #
        #     ui.date_picker(min="2026-01-01")  ->  17 622 o,    29 <button>
        #     ui.date_picker(min="137")         -> 463 581 o, 1 918 <button>
        #
        # Le rendu serveur reste instantané (0,01 s) — c'est le NAVIGATEUR
        # qui met ~114 s à avaler le résultat, ce qui faisait pendre
        # ``pytest -m audit`` sur ce composant.
        #
        # ⚠️ Borner ne change RIEN à la contrainte : ``min`` / ``max``
        # continuent de décider quelles dates sont sélectionnables. Ce
        # menu est une affordance de SAUT, et un saut ne se choisit pas
        # dans une liste de 1 900 boutons — au-delà, on tape la date.
        #
        # La fenêtre est CENTRÉE sur l'année affichée, pas tronquée d'un
        # bout : tronquer la fin rendrait le menu inutile pour qui vient
        # d'ouvrir le calendrier sur 1912.
        span = year_max_hd - year_min_hd + 1
        if span > MAX_YEARS_IN_DROPDOWN:
            half = MAX_YEARS_IN_DROPDOWN // 2
            anchor = initial_displayed.year
            lo = max(year_min_hd, anchor - half)
            hi = min(year_max_hd, lo + MAX_YEARS_IN_DROPDOWN - 1)
            # Si l'ancre est près du haut de l'étendue, ``hi`` a été
            # rogné par ``year_max_hd`` : on récupère la place en bas.
            lo = max(year_min_hd, hi - MAX_YEARS_IN_DROPDOWN + 1)
            year_min_hd, year_max_hd = lo, hi

        # En mode ``month`` la grille montre une ANNÉE entière, donc les
        # flèches avancent d'un an — sinon elles ne changeraient rien de
        # visible, la grille ne dépendant pas du mois affiché.
        prev_step = "year -= 1" if is_month_mode else (
            "month === 0 ? (year -= 1, month = 11) : (month -= 1)"
        )
        next_step = "year += 1" if is_month_mode else (
            "month === 11 ? (year += 1, month = 0) : (month += 1)"
        )
        prev_btn = _IconButton(
            "chevron-left",
            variant="ghost",
            size=size_key,
            color=color,
            disabled=disabled_prop,
            # ``shrink-0`` : sans lui la flèche RÉTRÉCIT quand le libellé
            # du mois est long — mesuré le 2026-08-25, 40 px en « août »
            # contre 31,6 px en « septembre ». Son bord droit est fixe,
            # donc c'est son bord GAUCHE qui bougeait de 8,4 px : on
            # clique, la cible se dérobe. C'est le libellé qui doit
            # céder (il a ``truncate``), jamais la commande.
            # La taille vient du thème du CALENDRIER, pas de celui
            # d'IconButton : son palier ``md`` fait 40 px quand ce
            # thème-ci déclare 32 (``nav_button: w-8``). Le jeton était
            # donc honoré par le rendu JS et ignoré par le rendu Python,
            # et ces 2 × 8 px de trop faisaient déborder l'en-tête —
            # les 16,8 px mesurés. Les ``!`` sont nécessaires : à
            # spécificité égale, Tailwind tranche par l'ordre de sa
            # feuille, donc sans eux le gagnant est imprévisible.
            classes="shrink-0 " + size_map.get("nav_button", ""),
            **{
                "bz-on:click": prev_step,
                "aria-label": text(
                    "calendar.previous_year" if is_month_mode
                    else "calendar.previous_month"
                ),
            },
        )
        Component._detach_from_parent(prev_btn)
        next_btn = _IconButton(
            "chevron-right",
            variant="ghost",
            size=size_key,
            color=color,
            disabled=disabled_prop,
            # ``shrink-0`` : sans lui la flèche RÉTRÉCIT quand le libellé
            # du mois est long — mesuré le 2026-08-25, 40 px en « août »
            # contre 31,6 px en « septembre ». Son bord droit est fixe,
            # donc c'est son bord GAUCHE qui bougeait de 8,4 px : on
            # clique, la cible se dérobe. C'est le libellé qui doit
            # céder (il a ``truncate``), jamais la commande.
            # La taille vient du thème du CALENDRIER, pas de celui
            # d'IconButton : son palier ``md`` fait 40 px quand ce
            # thème-ci déclare 32 (``nav_button: w-8``). Le jeton était
            # donc honoré par le rendu JS et ignoré par le rendu Python,
            # et ces 2 × 8 px de trop faisaient déborder l'en-tête —
            # les 16,8 px mesurés. Les ``!`` sont nécessaires : à
            # spécificité égale, Tailwind tranche par l'ordre de sa
            # feuille, donc sans eux le gagnant est imprévisible.
            classes="shrink-0 " + size_map.get("nav_button", ""),
            **{
                "bz-on:click": next_step,
                "aria-label": text(
                    "calendar.next_year" if is_month_mode
                    else "calendar.next_month"
                ),
            },
        )
        Component._detach_from_parent(next_btn)

        # Trigger button classes : ghost button look, small label,
        # gap before the chevron, focus ring. ``{bg_color}`` so the ring
        # follows ``color=`` (resolved via the local ``_resolve`` closure,
        # like the other slots), matching the prev/next IconButtons and
        # the wrapping date_picker's frame.
        trigger_cls = _resolve(
            "inline-flex items-center gap-1 px-2 py-1 "
            "rounded-selector text-sm font-medium text-text "
            "not-disabled:hover:bg-text/5 transition-colors "
            "disabled:opacity-40 disabled:cursor-not-allowed "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus)"
        )
        # Panel : absolute under the trigger, scrollable.
        #
        # ⚠️ Ce commentaire annonçait « with a transition on
        # open/close » et il n'y en avait AUCUNE — pas même la
        # classe morte que portaient les six autres panneaux.
        # Corrigé en la posant pour de vrai le 2026-09-04.
        #
        # Cadence des CHAMPS (75 ms) : ces deux menus s'ouvrent DANS
        # un panneau déjà ouvert, donc à la cadence des menus (150)
        # ils paraîtraient plus lourds que la surface qui les porte.
        # Mécanisme des trois classes : un seul exemplaire, dans
        # ``overlay/dropdown/theme.py``.
        panel_cls = (
            "absolute top-full left-0 mt-1 z-10 min-w-[120px] "
            "max-h-64 overflow-y-auto "
            "rounded-box border border-text/10 bg-interface shadow-lg "
            "py-1 "
            "transition-[opacity,display] transition-discrete duration-75 starting:opacity-0"
        )
        item_cls = (
            "flex items-center w-full px-3 py-1.5 text-sm cursor-pointer "
            "text-text not-disabled:hover:bg-text/5 transition-colors "
            "outline-none focus-visible:bg-text/5"
        )
        chevron_dropdown_cls = (
            "inline-flex shrink-0 text-current text-xs"
        )

        def _build_dropdown(
            label_expr: str,
            items: list[tuple[str, str]],
            aria_label: str,
            item_labels_are_expressions: bool = False,
        ) -> Element:
            """Build a self-contained dropdown :
            <div bz-data={open}><trigger><panel/items></div>.

            ``label_expr`` is a client expression for the trigger's
            ``bz-text`` (e.g. ``"(['Jan',...,'Dec'])[month]"`` or
            ``"year"``). ``items`` is a list of
            ``(label, on_click_expression)`` pairs.

            The panel starts hidden with a FOUC pre-stamp ; ``.stop`` is
            inlined as ``$event.stopPropagation()`` (no modifier grammar) ;
            dismiss (click-outside + Escape) rides the shared
            ``anchored_dismiss_init`` on ``$el``.
            """
            trigger = Element(
                tag="button",
                attrs={
                    "type": "button",
                    # ``min-w-0`` sur le DÉCLENCHEUR, pas seulement sur
                    # son enveloppe : ``truncate`` sur le libellé ne fait
                    # rien tant que la boîte qui le contient garde sa
                    # taille de contenu. Mesuré à ``xs`` en français, le
                    # libellé faisait 67,7 px dans un bouton de 61,2 —
                    # il DÉBORDAIT sur le sélecteur d'année, qui se
                    # retrouvait écrasé à 38,8 px : « septembre2026 »
                    # collés, chevron du mois avalé.
                    "class": trigger_cls + " min-w-0",
                    "aria-label": aria_label,
                    "bz-on:click": "$event.stopPropagation(); open = !open",
                    **_header_disable_attrs,
                },
                children=(
                    Element(
                        tag="span",
                        attrs={"bz-text": label_expr},
                        children=(),
                    ),
                    Element(
                        tag="iconify-icon",
                        attrs={
                            "icon": "lucide:chevron-down",
                            "class": chevron_dropdown_cls,
                        },
                        children=(),
                    ),
                ),
            )
            item_nodes: list[Node] = []
            for lbl, on_click in items:
                item_attrs: dict[str, Any] = {
                    "type": "button",
                    "class": item_cls,
                    "bz-on:click": f"{on_click}; open = false",
                }
                # Un DRAPEAU plutôt qu'un type de libellé : discriminer
                # sur ``isinstance`` ici ressemblait, à la lettre, au
                # tri d'enfants par classe que
                # ``test_a_parent_that_sorts_children_unwraps_them``
                # interdit — et elle avait raison de le dire, le motif
                # est le même à un cheveu près.
                if item_labels_are_expressions:
                    item_attrs["bz-text"] = lbl
                    item_children: tuple[Node, ...] = ()
                else:
                    item_children = (_TextNode(lbl),)
                item_nodes.append(Element(
                    tag="button", attrs=item_attrs, children=item_children,
                ))
            panel_attrs: dict[str, Any] = {
                "class": panel_cls,
                "bz-show": "open",
                "role": "menu",
                # Contrat de ``anchored_dismiss_init`` : tout overlay qui
                # l'appelle DOIT nommer son panneau ``bzpanel``, sinon
                # ``$refs.bzpanel`` remonte la chaîne de prototypes du scope
                # et résout le panneau d'un ANCÊTRE.
                #
                # Bug reproduit au navigateur le 2026-07-29 : ces dropdowns
                # vivent dans un ``<bz-calendar>`` qui vit lui-même dans le
                # panneau d'un ``date_picker``. Sans cette ref, le
                # ``clickOutside`` du dropdown mois considérait le panneau
                # DU PICKER comme « dedans » → un clic sur l'en-tête du
                # calendrier ne le fermait pas. Contrôle : un clic sur
                # ``<body>``, sur un ``<h1>`` ou Escape le fermaient bien —
                # donc le dismiss était câblé, il visait la mauvaise cible.
                "bz-ref": "bzpanel",
            }
            # FOUC pre-stamp : the dropdown starts closed at SSR.
            stamp_display_none(panel_attrs)
            panel = Element(
                tag="div",
                attrs=panel_attrs,
                children=tuple(item_nodes),
            )
            return Element(
                tag="div",
                attrs={
                    # ``min-w-0`` : c'est ce qui autorise le libellé à
                    # céder. Sans lui, un reste de 0,8 px suffisait à
                    # repousser la flèche — la garantie doit être
                    # STRUCTURELLE (la commande ne bouge jamais), pas
                    # « ça tient de justesse dans cette langue-ci ».
                    "class": "relative inline-block min-w-0",
                    "bz-data": "{open: false}",
                    "bz-init": anchored_dismiss_init("open"),
                },
                children=(trigger, panel),
            )

        # Sans liste explicite, les douze noms sont CALCULÉS par le
        # client : le serveur ne peut pas les produire (le module
        # ``locale`` de Python est un état global au processus, et Babel
        # serait une dépendance). Le panneau reste invisible jusqu'à
        # ``.bz-ready``, donc aucun scintillement — c'est la même
        # garantie qui couvre déjà la grille, remplie en JS.
        client_months = self._month_names is None
        if client_months:
            month_expr = "$bz.locale.monthName(month)"
            month_labels = [f"$bz.locale.monthName({mi})" for mi in range(12)]
        else:
            month_expr = f"({json.dumps(self._month_names)})[month]"
            month_labels = list(self._month_names)
        month_drop_el = _build_dropdown(
            label_expr=month_expr,
            items=[
                (label, f"month = {mi}")
                for mi, label in enumerate(month_labels)
            ],
            aria_label=text("calendar.month"),
            item_labels_are_expressions=client_months,
        )
        year_drop_el = _build_dropdown(
            label_expr="year",
            items=[
                (str(y), f"year = {y}")
                for y in range(year_min_hd, year_max_hd + 1)
            ],
            aria_label=text("calendar.year"),
        )

        header_el = Element(
            tag="div",
            attrs={
                "data-bz-cal-header": "",
                "class": slots.get("header", ""),
            },
            # En mode ``month``, le sélecteur de MOIS disparaît : la
            # grille EST le sélecteur de mois. Le garder ferait deux
            # chemins pour le même geste, dont un qui n'aurait aucun
            # effet visible sur la grille affichée.
            children=tuple(
                el for el in (
                    prev_btn.render(),
                    None if is_month_mode else month_drop_el,
                    year_drop_el,
                    next_btn.render(),
                ) if el is not None
            ),
        )

        # Même partage que les mois : nommés par le client faute de
        # liste explicite. L'index est celui de ``Date.getDay()``
        # (dimanche = 0), tourné ici pour ``weekstart`` — c'est le
        # composant qui tourne, jamais la liste (piège [14]).
        if self._weekday_names is None:
            # Les INDICES tournent, exactement comme les noms tournent
            # sur l'autre branche — même helper, donc une seule
            # implémentation du contrat dimanche-premier (piège [14]).
            weekday_html_parts = [
                f'<div class="{weekday_class}" '
                f'bz-text="$bz.locale.weekdayNames()[{i}]">'
                f'</div>'
                for i in rotate_weekday_names(list(range(7)), weekstart)
            ]
        else:
            weekday_html_parts = [
                f'<div class="{weekday_class}">{n}</div>'
                for n in rotate_weekday_names(self._weekday_names, weekstart)
            ]
        weekdays_html = (
            f'<div data-bz-cal-weekdays class="{slots.get("weekday_row", "")}">'
            f'{"".join(weekday_html_parts)}'
            f'</div>'
        )
        # Empty grid container — JS fills via insertAdjacentHTML at
        # connectedCallback. Un morph le RE-VIDE (les enfants reviennent
        # à la version serveur) sans réveiller aucun callback du custom
        # element : c'est le ``bz-init`` posé plus bas sur la racine qui
        # rattrape, en appelant ``rehydrate()`` après chaque rescan.
        grid_html = (
            f'<div data-bz-cal-grid class="{slots.get("week_row", "")}"></div>'
        )

        # Mode ``month`` : ni ligne de jours ni grille de jours. Émettre
        # la ligne de jours quand même la ferait CLIGNOTER — elle serait
        # peinte au premier rendu puis retirée par le premier
        # ``_replaceBody`` du custom element.
        ssr_html = HtmlNode(
            f'<div data-bz-cal-months class="{slots.get("month_grid", "")}">'
            f"</div>"
            if is_month_mode
            else weekdays_html + grid_html
        )

        # ── Root attributes on <bz-calendar> ──────────────────────
        # La LARGEUR vient de la table de tailles, pas du slot : elle
        # dépend du palier (7 cellules + les deux bords), et la mettre
        # dans le slot la ferait empiler avec la table sur le même
        # élément — la collision que ``traps.md`` § « size= : collision
        # slot ↔ table » décrit, dont Tailwind tranche l'issue par
        # l'ordre de sa feuille.
        root_attrs["class"] = " ".join(filter(None, (
            slots.get("root", ""),
            size_map.get("root", ""),
        )))
        # The root's whole-grid fade + cursor ride ``aria-disabled`` (the
        # ``disabled`` attr does nothing on a custom element — ``:disabled``
        # only matches real form controls). ``emit_attrs`` already put a
        # reactive ``bz-attr:disabled`` on the root for the JS to observe ;
        # mirror it onto ``aria-disabled`` so the CSS feedback toggles too.
        if disabled_binding is not None:
            # A ternary, not the bare path : ``bz-attr`` on a boolean sets
            # ``aria-disabled=""`` (empty), but Tailwind's ``aria-disabled:``
            # variant matches ``[aria-disabled="true"]`` (the string). Same
            # idiom as the header's ``bz-attr:aria-expanded`` ternary.
            root_attrs["bz-attr:aria-disabled"] = (
                bool_attr(self.path_of(disabled_binding))
            )
        elif disabled:
            root_attrs["aria-disabled"] = "true"
        # Le hook « après CHAQUE rescan » du framework, et c'est
        # ``bz-effect``, PAS ``bz-init`` : celui-ci est one-shot par NŒUD
        # (``el._bzInitDone``, qui survit au rebind), or idiomorph morphe
        # en place — le nœud survit, donc un ``bz-init`` ne re-tournerait
        # jamais. Un ``bz-effect`` est disposé puis refait à chaque
        # ``bindEl``, donc son corps re-tourne à chaque swap. Même choix
        # et même raison que ``_observe()`` du SignaturePad.
        #
        # Ce qu'il rattrape : un refresh de la zone qui contient le
        # calendrier remet ses enfants à la version serveur — c'est-à-dire
        # la grille VIDE (mesuré le 2026-08-21 : 42 cellules au premier
        # rendu, 0 après un refresh, et définitivement). ``rehydrate()``
        # ne repeint que si le corps a vraiment été effacé, donc un swap
        # sans rapport ne coûte qu'un ``querySelector``.
        root_attrs["bz-effect"] = "$el.rehydrate && $el.rehydrate()"
        root_attrs["mode"] = mode
        root_attrs["weekstart"] = str(weekstart)
        root_attrs["month"] = initial_displayed.isoformat()
        if initial_value_attr:
            root_attrs["value"] = initial_value_attr
        if min_iso:
            root_attrs["min"] = min_iso
        if max_iso:
            root_attrs["max"] = max_iso
        if disabled:
            root_attrs["disabled"] = True
        if disabled_iso_set:
            root_attrs["disabled-dates"] = json.dumps(
                sorted(disabled_iso_set)
            )
        if self._marks:
            root_attrs["marks"] = json.dumps(self._marks)
            # Le gabarit du nom accessible part d'ici, RÉSOLU côté
            # serveur : la grille est bâtie en JavaScript, et la table
            # des mots du framework n'existe qu'en Python. Sans ce
            # passage, une case marquée s'annoncerait en anglais quelle
            # que soit la langue de l'app.
            root_attrs["data-bz-mark-label"] = template("calendar.marked")
        if self._weekday_names is not None:
            root_attrs["weekday-names"] = json.dumps(self._weekday_names)
        if self._month_names is not None:
            root_attrs["month-names"] = json.dumps(self._month_names)
        root_attrs["data-bz-theme"] = json.dumps(theme_blob)
        # bz-data for the Python-rendered header. ``year`` and
        # ``month`` (0-indexed) drive the dropdown trigger labels and
        # the prev/next handlers. ``bz-attr:month`` (reactive attribute
        # binding below) propagates user changes to the bz-calendar's
        # observed ``month`` attribute, which fires the custom
        # element's ``attributeChangedCallback`` and re-renders the
        # grid. ``bz-on:month-change`` syncs back from the custom
        # element to the scope for nav driven from the imperative API
        # (``.prev_month()`` / ``.next_month()``) or internal grid nav.
        #
        # No getters here — ``year`` / ``month`` are flat signals, so the
        # ``scope.absorb`` getter-freeze trap doesn't apply. absorb also
        # preserves those signals across a morph — so a SERVER change to a
        # bound ``month=state.field`` is ignored on refresh unless the keys
        # opt into ``_serverSync``. Gate on server-backed (a ClientBinding
        # lives in the store; a literal keeps its client nav through an
        # unrelated refresh).
        month_sync = server_sync_marker(
            "year", "month", enabled=self._value_server_backed("month"))
        root_attrs["bz-data"] = (
            f"{{year: {initial_displayed.year}, "
            f"month: {initial_displayed.month - 1}"
            + (f",{month_sync}" if month_sync else "") + "}"
        )
        root_attrs["bz-attr:month"] = (
            "year + '-' + String(month + 1).padStart(2, '0') + '-01'"
        )
        # Inline sync handler stays present alongside any user-supplied
        # ``bz-on:month-change`` (string) so the wrapper state never
        # drifts. A server-callable ``on_change``/``on_month_change``
        # rides ``hx-*`` (not ``bz-on:``), so it never collides here.
        existing_mc = root_attrs.get("bz-on:month-change", "")
        sync_expr = (
            "year = $event.detail.year; "
            "month = $event.detail.month - 1"
        )
        root_attrs["bz-on:month-change"] = (
            f"{sync_expr}; {existing_mc}" if existing_mc else sync_expr
        )
        # Year range for the header year-select. Auto-derived from
        # ``min`` / ``max`` if set, otherwise default ±10 years from
        # ``today``. The custom element widens the range live if the
        # displayed year sits outside (e.g. ``month=date(1850, …)``
        # without bounds) so the select always shows the live year.
        today_year = _dt.date.today().year
        if isinstance(min_raw, _dt.date):
            year_min = min_raw.year
        elif min_iso:
            year_min = int(min_iso.split("-")[0])
        else:
            year_min = today_year - 10
        if isinstance(max_raw, _dt.date):
            year_max = max_raw.year
        elif max_iso:
            year_max = int(max_iso.split("-")[0])
        else:
            year_max = today_year + 10
        root_attrs["data-bz-year-min"] = str(year_min)
        root_attrs["data-bz-year-max"] = str(year_max)
        # Hand the bound state path(s) to the custom element so it can
        # write back on internal mutations (user pick, prev/next nav).
        # Without these the Client playground / Client events stay
        # silent — the framework's ``bz-attr:<attr>`` only flows state →
        # attribute, this closes the round-trip.
        # ⚠️ Ces deux chemins sont ASSIGNABLES : ``07_calendar.js::_writeBinding``
        # les split sur ``.`` puis walk jusqu'à la feuille pour y écrire. Une
        # ClientExpression y est structurellement invalide (elle n'est pas un
        # chemin dotté) — d'où ``value``/``month`` dans ``TWO_WAY_PROPS``, qui
        # la rejette à la construction. ``path_of`` reste correct pour le
        # binding simple.
        if value_binding is not None:
            root_attrs["data-bz-value-path"] = self.path_of(value_binding)
        if month_binding is not None:
            root_attrs["data-bz-month-path"] = self.path_of(month_binding)

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(*hidden_nodes, header_el, ssr_html),
        )
