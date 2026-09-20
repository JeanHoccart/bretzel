"""The words the framework wrote itself, and how to replace them.

A Bretzel component writes sentences: "Clear filters" on the datatable's
button, "Dismiss alert" on an alert's cross, "Accepted: …" under a drop
zone. They are in English, and **no API in the world knows how to
translate them** — unlike month names, date formats or number
separators, which are DERIVED from a language code and which
:attr:`~bretzel.server.config.BretzelConfig.lang` is enough to obtain
(cf. that field's docstring).

Hence this module: a flat table, one key per sentence, overridable by the
app in a single place ::

    Bretzel(lang="fr", texts={
        "datatable.clear_filters": "Effacer les filtres",
        "alert.dismiss": "Fermer l'alerte",
    })

This module owns the **words**. The choice of LANGUAGE — negotiation,
cookie, the visitor's table — lives next door, in
:mod:`bretzel.render.lang`: two questions, two modules, and it is that
split that makes each readable on its own.

⚠️ This is **not** i18n (out of scope for v2.0), and it is worth knowing
where the promise stops: the framework translates THE WORDS IT WROTE.
Yours — "Contacts", "Save" — have no catalogue, no extraction, no
marking. :attr:`bretzel.Language.code` returns the resolved language, and
a dict per language in your app does the rest in six lines. The only
plural rule is *one / other*, which covers English and French, not
Russian.

It is also the repair of an inconsistency: until now half the visible
texts were props (``search_placeholder=``, ``empty_text=``, ``label=``)
and the other half were hard-coded, with no rule saying which would be
which.

Why a table rather than one prop per sentence
---------------------------------------------
One prop per sentence means twenty-six more props on sixteen components,
to be passed again **at every mount** — exactly the flaw ``month_names=``
already had, and which cost three repetitions on a single CRM screen. The
table is declared once for the app.

How to add an entry to it
-------------------------
A new sentence in a component is written ``text("my_component.my_key")``
and its English value is set here. The reverse order — hard-coding the
string "for now" — is what
``tests/consistency/test_framework_words_go_through_the_table.py``
forbids: it is invisible in review and only shows on screen, in a
language one does not speak.
"""

from __future__ import annotations

from collections.abc import Mapping
from string import Formatter
from typing import Any

__all__ = [
    "DEFAULT_TEXTS", "TextsError", "plural", "resolve_texts", "template", "text",
]


#: The English values. The key is ``<component>.<role>`` — the prefix is
#: not decorative: "Clear", "Clear date", "Clear time" and "Clear range"
#: are FOUR distinct sentences, and merging them would give a button that
#: lies half the time.
DEFAULT_TEXTS: Mapping[str, str] = {
    # ── Champs de saisie ─────────────────────────────────────────────
    "input.clear": "Clear",
    "combobox.clear": "Clear",
    "select.clear": "Clear",
    "combobox.empty": "No results",
    "slider.range_start": "Range start",
    "slider.range_end": "Range end",
    # ── Dates and times ──────────────────────────────────────────────
    # Month and day NAMES are not here: they derive from ``lang`` through
    # ``Intl`` in the browser. Only the words we wrote ourselves have a
    # key.
    "calendar.month": "Month",
    "calendar.year": "Year",
    # The accessible name of a MARKED cell. ``{day}`` is the day number,
    # ``{n}`` the count passed to ``marks=``. A whole sentence: the comma
    # and the order change from one language to another.
    "calendar.marked": "{day}, {n} events",
    "calendar.previous_month": "Previous month",
    "calendar.next_month": "Next month",
    "calendar.previous_year": "Previous year",
    "calendar.next_year": "Next year",
    "month_picker.clear": "Clear month",
    "month_picker.open": "Open month picker",
    "week_picker.clear": "Clear week",
    "week_picker.open": "Open week picker",
    "signature_pad.placeholder": "Sign here",
    "signature_pad.clear": "Clear",
    "date_picker.clear": "Clear date",
    "date_picker.open": "Open date picker",
    "date_range_picker.clear": "Clear range",
    "date_range_picker.open": "Open date range picker",
    "color_picker.clear": "Clear color",
    "color_picker.open": "Open color palette",
    "time_picker.clear": "Clear time",
    "time_picker.open": "Open time picker",
    # ── File drop ────────────────────────────────────────────────────
    # The three hints under the drop zone. ``{types}`` is the list of
    # accepted extensions, ``{size}`` the ceiling already formatted with
    # its unit, ``{max}`` the maximum number of files.
    "file_upload.accepted": "Accepted: {types}",
    "file_upload.max_size": "Max size: {size}",
    "file_upload.multiple": "Multiple files allowed",
    "file_upload.multiple_capped": "Multiple files allowed (up to {max})",
    "file_upload.remove": "Remove file",
    "file_upload.dropzone": "Drop files here or click to browse",
    "file_upload.button": "Upload file",
    "file_upload.drop_more": "Drop more files here",
    "file_upload.drop_replace": "Drop a different file to replace",
    # ── Data table ───────────────────────────────────────────────────
    "datatable.clear_filters": "Clear filters",
    "datatable.filter_placeholder": "Filter values…",
    # Four WHOLE sentences rather than a word glued to a number: a
    # translation moves the order of the pieces, and " of " is not a
    # reusable brick. ``{n}`` = what is displayed, ``{total}`` = what
    # exists before filtering.
    "datatable.results_one": "{n} result",
    "datatable.results_other": "{n} results",
    "datatable.results_narrowed_one": "{n} result of {total}",
    "datatable.results_narrowed_other": "{n} results of {total}",
    # ── Retours et surimpressions ────────────────────────────────────
    "alert.dismiss": "Dismiss alert",
    "badge.remove": "Remove",
    "banner.dismiss": "Dismiss",
    "modal.close": "Close",
    # ── Composite controls ───────────────────────────────────────────
    # Those eight were not written ``aria_label=`` but
    # ``attrs={"aria-label": …}``, a form no ``grep`` finds when looking
    # for the other — hence the gate reading the AST rather than the
    # text. The eighth was even written in FRENCH in the framework, alone
    # in the whole repository.
    "picker.remove": "Remove",
    "picker.select_all": "Select all",
    "picker.clear": "Clear",
    "carousel.choose_slide": "Choose slide",
    "carousel.go_to_slide": "Go to slide {n}",
    "carousel.previous": "Previous slide",
    "carousel.next": "Next slide",
    "show_more.label": "Show more",
    "resizable.resize_panel": "Resize panel {n}",
    "draggable.reorder": "Drag to reorder",
    "file_upload.complete": "Upload complete",
    "file_upload.error": "Upload error",
    "number_input.increment": "Increment",
    "number_input.decrement": "Decrement",
    "sidebar.rail_toggle": "Collapse or expand the sidebar",
    # The accessible name of the logo when the bar is collapsed: all it
    # has left is its glyph, so it would announce itself as plain "link".
    # Written in FRENCH in the framework until 2026-08-24 — the second of
    # two, and the first had been declared "alone in the whole
    # repository" for want of a detector that saw that form.
    "sidebar.home": "Home",
    # ── Charts ───────────────────────────────────────────────────────
    # The chart's name goes into the ``aria-label`` of its ``<svg>`` when
    # it is empty — that is what a screen reader announces.
    "chart.bar": "Bar chart",
    "chart.line": "Line chart",
    "chart.pie": "Pie chart",
    "chart.donut": "Donut chart",
    "chart.scatter": "Scatter plot",
    "chart.scatter_date_axis": "Scatter plot (date axis)",
    "chart.empty": "No data",
    "chart.series": "Series",
    # The summary a screen reader reads on the ``<svg>``. WHOLE
    # sentences: "Bar chart — 12 categories across Nord, Sud" does not
    # translate by gluing "across" to two fragments. ``{kind}`` is the
    # chart's name, already translated by its own key.
    "chart.summary": "{kind} — {what}",
    "chart.summary_across": "{kind} — {what} across {names}",
    "chart.categories": "{n} categories",
    "chart.points": "{n} points",
    "chart.slices": "{n} slices",
    "chart.series_count": "{n} series",
    "chart.sparkline": "Sparkline",
    "chart.sparkline_empty": "Sparkline — no data",
    "chart.sparkline_summary": "Sparkline — {n} points, min {low}, max {high}",
    # ``fmt="currency"`` hard-coded the dollar, and its docstring owned
    # up to it ("USD-only v1"). A French CRM read its amounts there as
    # ``$1,234.50``. ``{value}`` already arrives grouped — thousands
    # SEPARATION, on the other hand, stays English: that would be a
    # number-formatting axis, not a framework word.
    "chart.currency": "${value}",
    # ── Navigation ───────────────────────────────────────────────────
    "pagination.previous": "Previous page",
    "pagination.next": "Next page",
    "sidebar.toggle": "Toggle sidebar",
}


class TextsError(ValueError):
    """Raised when a ``texts=`` key does not match a known framework phrase."""


def resolve_texts(overrides: Mapping[str, str] | None) -> Mapping[str, str]:
    """Merge application text overrides into the built-in English values."""
    if not overrides:
        return DEFAULT_TEXTS
    unknown = sorted(set(overrides) - set(DEFAULT_TEXTS))
    if unknown:
        raise TextsError(
            f"texts= has {len(unknown)} unknown key(s): "
            f"{', '.join(repr(k) for k in unknown)}. "
            f"The valid keys are listed in "
            f"bretzel.render.texts.DEFAULT_TEXTS."
        )
    # And the HOLES, not just the keys. An override renaming ``{size}``
    # to ``{taille}`` starts up without a word and raises a bare
    # ``KeyError`` on the page that displays it — that is to say exactly
    # the failure the validation above exists to prevent, one square
    # further on.
    for key, template in overrides.items():
        expected = _holes(DEFAULT_TEXTS[key])
        got = _holes(template)
        if got != expected:
            raise TextsError(
                f"texts[{key!r}] does not have the same holes as the "
                f"template: expected {sorted(expected) or 'none'}, got "
                f"{sorted(got) or 'none'}. Reference template: "
                f"{DEFAULT_TEXTS[key]!r}."
            )
    return {**DEFAULT_TEXTS, **overrides}


def _holes(template: str) -> set[str]:
    """A template's field names — ``"{n} of {total}"`` → ``{n, total}``."""
    return {
        field for _, field, _, _ in Formatter().parse(template) if field
    }


def text(key: str, /, **fmt: Any) -> str:
    """Return a framework phrase for ``key`` in the application's language."""
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    table = getattr(ctx, "texts", None) or DEFAULT_TEXTS
    try:
        template = table[key]
    except KeyError:
        raise TextsError(
            f"{key!r} is not a framework text key. "
            f"Add it to bretzel.render.texts.DEFAULT_TEXTS."
        ) from None
    try:
        return template.format(**fmt)
    except (KeyError, IndexError) as exc:
        raise TextsError(
            f"the text {key!r} expects a hole the caller did not supply "
            f"({exc}). Template: {template!r}."
        ) from None


def template(key: str, /) -> str:
    """Return the raw framework text template before interpolation."""
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    table = getattr(ctx, "texts", None) or DEFAULT_TEXTS
    try:
        return table[key]
    except KeyError:
        raise TextsError(
            f"{key!r} is not a framework text key."
        ) from None


def plural(key: str, n: int, /, **fmt: Any) -> str:
    """Return the ``…_one`` or ``…_other`` variant of ``key`` for ``n``."""
    return text(f"{key}_one" if n == 1 else f"{key}_other", n=n, **fmt)
