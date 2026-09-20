"""Shared doc-UI blocks — built out of ``ui.*`` (the docs dogfood the
framework they document).

- :func:`emitted_html_block` — a collapsible "what HTML did Bretzel
  emit" reveal, bound to a session-wide toggle (same idea as the
  playground's inspector).
- :func:`state_mirror` — renders a live :class:`StateInfo` as a table:
  the anti-rot payoff, one call shows a State class exactly as it is in
  the code *right now*.
- :func:`source_view` — a collapsible "see the Python code" disclosure
  showing the REAL source of a demo (``inspect.getsource``), so the
  code the reader sees is the code that ran — it can't drift.
"""

from __future__ import annotations

import inspect
import itertools
import re
import textwrap

from bretzel import ui
from bretzel.state import ClientState, field
from examples.docs.lib.i18n import tr
from bretzel.introspect import (
    ComponentInfo,
    HelperInfo,
    ParamInfo,
    StateInfo,
    describe_callable,
    describe_client_algebra,
    describe_state,
    describe_toplevel_surface,
)


def callable_signature(fn: object, *, title: str | None = None) -> None:
    """Render a function's live signature as a table — read via
    :func:`describe_callable`, so a renamed / added parameter shows up
    with no doc edit. Used for the ``Bretzel(...)`` / ``run(...)``
    reference."""
    info = describe_callable(fn)
    ui.text(title or f"{info.name}(…)", weight="bold", classes="font-mono")
    # ⚠️ A function with NO parameter rendered an empty 200 px-tall
    # table with "No data." in the middle — seen on a screenshot of
    # `/browser`, where `print_page()` and `fullscreen()` take none. The
    # twin `params_table` already had this guard; this one did not, and
    # both live in this file.
    if not info.params:
        ui.text(tr('No parameter.',
                   'Aucun paramètre.'), color="muted", size="sm")
        return
    ui.table(
        columns=[
            ui.column("param", label=tr('Parameter',
                                        'Paramètre')),
            ui.column("type", label="Type"),
            ui.column("default", label=tr('Default',
                                          'Défaut')),
            ui.column("kind", label="Passage"),
        ],
        rows=[
            {
                "param": p.name,
                "type": p.type_label,
                "default": p.default_label or "—",
                "kind": p.kind,
            }
            for p in info.params
        ],
        size="sm",
    )


def live_source(objects: tuple[object, ...]) -> str:
    """Join the live Python source of each object — a function, a class,
    or a ``@refreshable`` handle. Read via :func:`inspect.getsource`, so
    the text IS the code that executes and can't drift.

    A ``@refreshable`` zone is a ``RefreshableHandle``, not a function ;
    we unwrap ``.fn`` so ``getsource`` finds the real ``def`` (and its
    decorator line)."""
    parts: list[str] = []
    for obj in objects:
        target = getattr(obj, "fn", obj)          # unwrap RefreshableHandle
        try:
            parts.append(textwrap.dedent(inspect.getsource(target)).rstrip())
        except (OSError, TypeError):
            continue                              # C-defined / no source — skip
    return "\n\n\n".join(parts)


def source_view(*objects: object, label: str = tr('See the Python code',
                                                  'Voir le code Python')) -> None:
    """Collapsible "see the code" disclosure — each object's live source,
    hidden behind a toggle. Reusable across every chapter: wrap a demo's
    building blocks (state class + handlers + zone) and the reader can
    open the exact Python that produced it."""
    source = live_source(objects)
    if not source:
        return
    with ui.accordion(collapsible=True):
        with ui.accordion_item("src", label=label, icon="code"):
            ui.code(source, lang="python")


def source_block(*objects: object) -> None:
    """Always-visible live source — for cards where the code IS the
    lesson (e.g. "declaring a state"), not an optional reveal. Same
    anti-drift guarantee as :func:`source_view`."""
    source = live_source(objects)
    if source:
        ui.code(source, lang="python")


class DocsInspector(ClientState, persist="local"):
    """Session-wide toggle for every "Emitted HTML" reveal in the docs."""

    show_html: bool = field(default=False)


def emitted_html_block(label: str, html_source: str) -> None:
    """One inspection row : a ``Show emitted HTML`` switch + the
    collapsible label + syntax-highlighted source. The switch is bound
    to the shared :class:`DocsInspector`, so flipping it anywhere flips
    every block on every page at once (sticky, client-reactive)."""
    inspector = DocsInspector()
    with ui.hstack(align="center", gap="sm"):
        ui.switch(checked=inspector.show_html)
        ui.text(tr('See the emitted HTML',
                   'Voir le HTML émis'), color="muted", size="sm")
    with ui.vstack(gap="xs", visible=inspector.show_html):
        ui.text(label, color="muted", size="xs")
        ui.code(html_source, lang="html")


def state_mirror(state_cls: type) -> None:
    """Render a State class *as it is in the code right now* — read live
    via :func:`describe_state`. Add a field, wire a validator, change a
    default : this table follows on the next render with no edits."""
    info: StateInfo = describe_state(state_cls)

    with ui.vstack(gap="sm"):
        with ui.hstack(align="center", gap="sm", wrap=True):
            ui.text(info.name, weight="bold", classes="font-mono")
            ui.badge(
                info.family,
                color="info" if info.family == "ServerState" else "warning",
                variant="soft",
            )
            ui.badge(info.scope, color="muted", variant="outline")

        if info.fields:
            rows = [
                {
                    "field": f.name,
                    "type": f.type_label,
                    "default": f.default_label,
                    "validators": ", ".join(f.validators) or "—",
                }
                for f in info.fields
            ]
            ui.table(
                columns=[
                    ui.column("field", label="Champ"),
                    ui.column("type", label="Type"),
                    ui.column("default", label=tr('Default',
                                                  'Défaut')),
                    ui.column("validators", label="@validator"),
                ],
                rows=rows,
                size="sm",
            )
        else:
            ui.text(tr('(no field declared)',
                       '(aucun champ déclaré)'), color="muted", size="sm")

        url_line(info)

        if info.computed:
            with ui.hstack(gap="xs", align="center", wrap=True):
                ui.text("@computed :", color="muted", size="sm")
                for n in info.computed:
                    ui.badge(n, color="success", variant="soft")

        if info.whole_validators:
            ui.text(
                f"+ {info.whole_validators} validator(s) d'instance "
                "(invariants multi-champs)",
                color="muted", size="sm",
            )


def url_line(info: StateInfo) -> None:
    """What the state publishes in the ADDRESS, or what it would publish.

    Three states, like ``describe``'s card — and telling them apart IS
    the information: on, named but off (only ``addressable=True`` is
    missing), nothing at all. A state declaring nothing writes no row:
    almost all of them are there, and an empty row would read as a failed
    read.

    A field ABSENT from this row never goes into the URL. It is the
    guarantee that keeps ``filters`` out of the address, and it shows
    nowhere else on this page.
    """
    if info.url_error:
        ui.text(f"URL — déclaration refusée : {info.url_error}",
                color="error", size="sm")
        return
    publies = info.url_params or info.url_named
    if not publies:
        return
    allume = bool(info.url_params)
    with ui.hstack(gap="xs", align="center", wrap=True):
        ui.text(tr('In the URL:',
                   "Dans l'URL :") if allume else tr('Named for the URL:',
                                                 "Nommés pour l'URL :"),
                color="muted", size="sm")
        for champ, param in publies:
            ui.badge(f"{champ} → {param}",
                     color="primary" if allume else "muted", variant="soft")
    ui.text(
        tr('A field missing from this row never goes into the URL.',
           "Un champ absent de cette ligne ne part jamais dans l'URL.")
        if allume else
        tr('Off: `addressable=True` on the class would publish those fields.',
           'Éteint : `addressable=True` sur la classe publierait ces champs-'
           'là.'),
        color="muted", size="xs",
    )


# ── ui.* catalogue blocks (Composants + helpers, lus en direct) ─────────

def first_line(doc: str | None) -> str:
    """First non-empty line of a docstring — the one-line summary."""
    for line in (doc or "").strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def params_table(params: tuple[ParamInfo, ...]) -> None:
    """Compact parameter / type / default table — shared by the component
    and helper mirrors (both read their params from :mod:`introspect`)."""
    if not params:
        return
    ui.table(
        columns=[
            ui.column("param", label=tr('Parameter',
                                        'Paramètre')),
            ui.column("type", label="Type"),
            ui.column("default", label=tr('Default',
                                          'Défaut')),
        ],
        rows=[
            {"param": p.name, "type": p.type_label,
             "default": p.default_label or "—"}
            for p in params
        ],
        size="sm",
    )


def contract_chips(label: str, items: tuple[str, ...], color: str) -> None:
    """A labelled row of soft badges — one per name in an introspectable
    contract (BINDABLE_PROPS / EVENTS / IMPERATIVE / NAMED_SLOTS). Renders
    nothing when the contract is empty."""
    if not items:
        return
    with ui.hstack(gap="xs", align="center", wrap=True):
        ui.text(f"{label} :", color="muted", size="xs", classes="font-mono")
        for it in items:
            ui.badge(it, color=color, variant="soft")


def component_mirror(info: ComponentInfo) -> None:
    """Render a :class:`ComponentInfo` live — the catalogue body for one
    ``ui.*`` component. Summary, params, and the four introspectable
    contracts, read from the class *right now*, so it can't drift."""
    with ui.vstack(gap="sm"):
        summary = first_line(info.doc)
        if summary:
            ui.text(summary, color="muted", size="sm")

        with ui.hstack(gap="xs", align="center", wrap=True):
            ui.badge(info.class_name, color="muted", variant="outline")
            ui.badge(f"<{info.tag}>", color="info", variant="soft")
            ui.badge("container" if info.is_container else "leaf",
                     color="muted", variant="soft")
            if info.autoname_from:
                ui.badge(f"name auto ← {info.autoname_from}",
                         color="warning", variant="soft")

        params_table(info.params)

        if info.bindable_audited:
            contract_chips("BINDABLE_PROPS", info.bindable, "success")
        else:
            ui.text(tr('BINDABLE_PROPS: not audited (legacy mode)',
                       'BINDABLE_PROPS : non audité (mode legacy)'),
                    color="muted", size="xs", classes="font-mono")
        contract_chips("EVENTS", info.events, "info")
        contract_chips("IMPERATIVE", info.imperative, "primary")
        contract_chips("NAMED_SLOTS", info.named_slots, "muted")


def client_algebra_mirror() -> None:
    """Render the ClientBinding Python→JS algebra *as it is in the code
    right now* — read via :func:`describe_client_algebra`, which executes
    each operator against a probe to capture the JS it really emits. Add
    an operator or a helper to ``ClientBinding`` and it appears here, with
    its real emitted JS, on the next render — zero edits."""
    # ``describe_client_algebra`` returns ops already sorted by (category,
    # name), so categories arrive contiguous — walk the runs directly.
    for category, group in itertools.groupby(
        describe_client_algebra(), key=lambda op: op.category
    ):
        items = list(group)
        with ui.vstack(gap="xs"):
            with ui.hstack(align="center", gap="sm"):
                ui.text(category, weight="bold", size="sm")
                ui.badge(str(len(items)), color="muted", variant="outline")
            ui.table(
                columns=[
                    ui.column("py", label="En Python"),
                    ui.column("js", label=tr('Emitted JS (live)',
                                             'JS émis (live)')),
                    ui.column("ret", label="→"),
                ],
                rows=[
                    {"py": op.python, "js": op.js or "—", "ret": op.returns_label}
                    for op in items
                ],
                size="sm",
            )


def helper_mirror(info: HelperInfo) -> None:
    """Render a :class:`HelperInfo` — a non-component ``ui.*`` symbol
    (iteration generator, fire-and-forget toast, descriptor). Signature +
    summary only : a helper has no props / events / slots, and the
    catalogue must not pretend otherwise."""
    with ui.vstack(gap="sm"):
        with ui.hstack(gap="xs", align="center", wrap=True):
            ui.badge(info.kind, color="warning", variant="soft")
            ui.text(tr('not a component',
                       'pas un composant'), color="muted", size="xs")
        summary = first_line(info.doc)
        if summary:
            ui.text(summary, color="muted", size="sm")
        params_table(info.params)


def toplevel_surface_mirror() -> None:
    """Render ``bretzel.__all__`` grouped by NEED, read live.

    Grouping by need is the point: knowing ``refresh`` is a function
    helps nobody, knowing it lives beside ``abort`` and ``redirect`` in
    "acting from a handler" answers the real question. The population
    comes from the package — a name added to ``__all__`` appears here at
    the next render, and ``test_docs_coverage`` requires it to have been
    given a category.
    """
    for category, group in itertools.groupby(
        describe_toplevel_surface(), key=lambda s: s.category
    ):
        items = list(group)
        with ui.vstack(gap="xs"):
            with ui.hstack(align="center", gap="sm"):
                ui.text(category, weight="bold", size="sm")
                ui.badge(str(len(items)), color="muted", variant="outline")
            ui.table(
                columns=[
                    ui.column("name", label="Nom"),
                    ui.column("kind", label="Nature"),
                    ui.column("doc", label=tr('What it does',
                                              'Ce que ça fait')),
                ],
                rows=[
                    {"name": s.name, "kind": s.kind, "doc": s.summary or "—"}
                    for s in items
                ],
                size="sm",
            )


#: The Sphinx roles the repository's docstrings use. The first group
#: captures the name, the role is thrown away.
_ROLE = re.compile(r":(?:class|func|meth|mod|data|attr|exc):`~?([^`]+)`")


def plain(texte: str) -> str:
    """An RST docstring → text readable ON SCREEN.

    This repository's docstrings are written for a developer reading the
    code: Sphinx roles (``:class:`X```), double backticks, RST bold. A
    gate even requires the role to quote a symbol (``test_prose_norm``).
    That is right, and it does not render as is in an interface —
    measured on 2026-09-02 on the tree page, which showed "Voir
    :mod:`bretzel.cli.main`" and "**façade utilisateur**" in so many
    characters.

    This function does not FORMAT, it UNMARKS: the name survives, the
    marker goes. Rendering the code in real monospace would require
    cutting the text into fragments, and a tree label is not worth the
    price — the catalogue already does it where it counts.

    ⚠️ The order of the replacements matters: the roles first, otherwise
    ``:class:`X``` would lose its backticks and become ``:class:X``.
    """
    sans_role = _ROLE.sub(r"\1", texte)
    sans_gras = re.sub(r"\*\*([^*]+)\*\*", r"\1", sans_role)
    return sans_gras.replace("``", "").replace("`", "")
