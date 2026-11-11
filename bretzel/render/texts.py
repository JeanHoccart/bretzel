"""The words the framework wrote itself, and how to replace them.

A Bretzel component writes sentences: "Clear filters" on the datatable's
button, "Dismiss alert" on an alert's cross, "Accepted: …" under a drop
zone. **No API in the world knows how to translate them** — unlike
month names, date formats or number separators, which are DERIVED from a
language code (``Intl``, in the browser). So each sentence has a key,
and a table per language says it: English here, the languages the
framework ships in :mod:`bretzel.render.languages` (French). The
table follows :attr:`~bretzel.server.config.BretzelConfig.lang`, and an
app replaces a sentence in its own table, by the sentence's name ::

    Bretzel(lang="fr", translations={"fr": {"sidebar.toggle": "Ouvrir le menu"}})

This module owns the **words**. The choice of LANGUAGE — negotiation,
cookie, the visitor's table — lives next door, in
:mod:`bretzel.render.lang`: two questions, two modules, and it is that
split that makes each readable on its own.

This module is the framework's words; an app's own — "Contacts",
"Save" — go through :func:`bretzel.t`, in the same ``translations=``
table (:mod:`bretzel.render.translations`), with the sentence as its
key. A counted
sentence (:func:`plural`) takes the form the LANGUAGE says — the singular
for 0 in French, "0 results" in English, Russian's ``few`` and ``many``
(:func:`bretzel.render.languages.plural_category`).

It is also the repair of an inconsistency: until now half the visible
texts were props (``search_placeholder=``, ``empty_text=``, ``label=``)
and the other half were hard-coded, with no rule saying which would be
which.

Why a table rather than one prop per sentence
---------------------------------------------
One prop per sentence means twenty-six more props on sixteen components,
to be passed again **at every mount**, as ``month_names=`` is on every
calendar of a screen. The table is declared once for the app.

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
    "DEFAULT_TEXTS", "PLURAL_FORMS", "TextsError", "plural", "resolve_texts", "template",
    "text",
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
    # ``creatable=True``: the row that creates what was typed. ``{text}``
    # is the typed text, filled in the browser.
    "combobox.create": 'Create "{text}"',
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
    # The letters of a date field's hint, « MM/DD/YYYY ». Their ORDER and
    # separators are not here: the browser asks ``Intl`` for them, the
    # order ``lang`` writes a day in (``$bz.dates.pattern``).
    "date.typed_day": "DD",
    "date.typed_month": "MM",
    "date.typed_year": "YYYY",
    # A date field's accessible name when nothing labels it.
    "date_picker.label": "Date",
    "week_picker.label": "Week",
    "month_picker.label": "Month",
    "date_range_picker.start": "Start date",
    "date_range_picker.end": "End date",
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
    "color_picker.label": "Color",
    "time_picker.clear": "Clear time",
    "time_picker.open": "Open time picker",
    "time_picker.label": "Time",
    # The columns' short headers, and the words a screen reader says
    # before each cell (« Hours 14 »).
    "time_picker.hour": "H",
    "time_picker.minute": "M",
    "time_picker.hours": "Hours",
    "time_picker.minutes": "Minutes",
    "time_picker.period": "AM or PM",
    # ── File drop ────────────────────────────────────────────────────
    # The three hints under the drop zone. ``{types}`` is the list of
    # accepted extensions, ``{size}`` the ceiling already formatted with
    # its unit, ``{max}`` the maximum number of files.
    "message.mine": "Your message",
    "message.theirs": "Message",
    "message.from": "Message from {author}",
    "message.sending": "Sending…",
    "message.error": "Not sent",
    "message.copy": "Copy",
    "message.retry": "Retry",
    "message_list.label": "Conversation",
    "message_list.bottom": "Back to the latest message",
    "message_input.label": "Your message",
    "message.writing": "Writing…",
    "message_input.send": "Send",
    "message_input.stop": "Stop",
    "message_input.attach": "Attach a file",
    "message_input.voice": "Dictate",
    "file_upload.accepted": "Accepted: {types}",
    "file_upload.max_size": "Max size: {size}",
    "file_upload.multiple": "Multiple files allowed",
    "file_upload.multiple_capped": "Multiple files allowed (up to {max})",
    "file_upload.remove": "Remove file",
    "file_upload.dropzone": "Drop files here or click to browse",
    "file_upload.button": "Upload file",
    "file_upload.drop_more": "Drop more files here",
    "file_upload.drop_replace": "Drop a different file to replace",
    # What the browser says when it refuses a file — filled in by the
    # runtime (file_upload.js). ``{name}`` the file, ``{size}`` the
    # ceiling with its unit, ``{count}`` / ``{max}`` numbers, ``{reason}``
    # one of the three ``reason_*`` texts.
    "file_upload.too_large": "{name} — exceeds {size}",
    "file_upload.wrong_format": "{name} — format not supported",
    "file_upload.skipped": "{count} files skipped ({reason}).",
    "file_upload.reason_too_large": "too large",
    "file_upload.reason_wrong_format": "wrong format",
    "file_upload.reason_size_or_format": "size or format",
    "file_upload.only_one": "Only one file allowed.",
    "file_upload.max_reached": "Maximum {max} files reached.",
    "file_upload.over_limit": "{count} files skipped — limit {max} reached.",
    "file_upload.network_error": "Network error",
    # ── Data table ───────────────────────────────────────────────────
    "datatable.clear_filters": "Clear filters",
    "datatable.export_csv": "Export CSV",
    "notification.dismiss": "Dismiss notification",
    "datatable.search": "Search…",
    "table.empty": "No data.",
    "diagram.empty": "No graph.",
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
    # The shape of an amount (``fmt="currency"``), its symbol and where
    # it goes. ``{value}`` already arrives grouped, with the marks of
    # ``chart.thousands`` and ``chart.decimal``.
    "chart.currency": "${value}",
    # The decimal mark of every chart number: axis ticks, bar values,
    # tooltips. A French app read « 13.2 » above its bars, beside
    # « 13,2 » everywhere else on the page.
    "chart.decimal": ".",
    # The thousands mark of an amount (``fmt="currency"``) and the shape
    # of a share (``fmt="percent"``): without them a French page would
    # read « 1,234.50 € » and « 42% ».
    "chart.thousands": ",",
    # The table behind every chart (``show_data``, and always for a
    # screen reader): its toggle and its headers when the app gave none.
    "chart.show_data": "Show the data",
    "chart.hide_data": "Hide the data",
    "chart.category": "Category",
    "chart.value": "Value",
    "chart.share": "Share",
    "chart.histogram": "Histogram",
    "chart.mean": "Mean {value}",
    # ``ui.stat``: its objective — under its gauge, or said in a line
    # when the value has no range (« Target ≤ 2% · not reached »).
    "stat.target": "Target {value}",
    "stat.target_at_most": "Target ≤ {value}",
    "stat.reached": "reached",
    "stat.missed": "not reached",
    # A share, « 42% » — charts and ``ui.progress`` alike.
    "number.percent": "{value}%",
    # ── Navigation ───────────────────────────────────────────────────
    "pagination.previous": "Previous page",
    "pagination.next": "Next page",
    # ``{n}`` is filled in the browser: the page numbers move with the
    # current page.
    "pagination.page": "Page {n}",
    "pagination.more": "More pages",
    "pagination.label": "Pagination",
    "sidebar.toggle": "Toggle sidebar",
    "sidebar.label": "Sidebar",
    "breadcrumb.label": "Breadcrumb",
    "spinner.label": "Loading",
}


class TextsError(ValueError):
    """Raised when a replaced framework sentence is not one Bretzel says."""


#: The forms a counted sentence may take beyond ``_one`` / ``_other``
#: (CLDR's categories): a language that has them — Czech's ``few`` for
#: 2 to 4 — gives them through ``translations=``.
PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")


def _reference(key: str) -> str | None:
    """The English template ``key`` is checked against: itself, or for
    ``datatable.results_few`` the ``_other`` of its sentence."""
    if key in DEFAULT_TEXTS:
        return DEFAULT_TEXTS[key]
    base, _, form = key.rpartition("_")
    if form in PLURAL_FORMS and f"{base}_other" in DEFAULT_TEXTS:
        return DEFAULT_TEXTS[f"{base}_other"]
    return None


def resolve_texts(overrides: Mapping[str, str] | None, *, lang: str = "en"
                  ) -> Mapping[str, str]:
    """The table of ``lang``: the framework's words in it — French ships
    with the framework, an unshipped language is English — then the app's
    overrides on top."""
    from bretzel.render.languages import built_in

    shipped = built_in(lang)
    base = {**DEFAULT_TEXTS, **shipped} if shipped else DEFAULT_TEXTS
    if not overrides:
        return base
    unknown = sorted(k for k in overrides if _reference(k) is None)
    if unknown:
        raise TextsError(
            f"translations= names {len(unknown)} unknown Bretzel sentence(s): "
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
        reference = _reference(key) or ""
        expected = _holes(reference)
        got = _holes(template)
        if got != expected:
            raise TextsError(
                f"texts[{key!r}] does not have the same holes as the "
                f"template: expected {sorted(expected) or 'none'}, got "
                f"{sorted(got) or 'none'}. Reference template: "
                f"{reference!r}."
            )
    return {**base, **overrides}


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
    """The form of ``key`` the request's language takes for ``n``: in
    French the singular for 0 (``_one``), in English "0 results"
    (``_other``); a form the table lacks falls back on ``_other``."""
    from bretzel.render.context import maybe_current_context
    from bretzel.render.languages import plural_category

    ctx = maybe_current_context()
    table = getattr(ctx, "texts", None) or DEFAULT_TEXTS
    form = f"{key}_{plural_category(getattr(ctx, 'lang', None) or 'en', n)}"
    return text(form if form in table else f"{key}_other", n=n, **fmt)
