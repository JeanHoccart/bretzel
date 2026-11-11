"""REFERENCE — Traps.

The gotchas condensed — above all the *silent* failures, the ones that do
not crash but simply do not work. Each trap: the symptom, the cause, the
fix.
"""

from __future__ import annotations

from bretzel import page, ui

from examples.docs.features.shell import shell

PATH = "/traps"

# (title, symptom, fix) — the silent traps first.
_TRAPS: list[tuple[str, str, str]] = [
    (
        'PEP 649 — State fields do not register',
        'A State looks correct but its fields are empty / the re-render '
        'does not fire. No error at all.',
        'Put `from __future__ import annotations` FIRST in every file that'
        ' declares a State. Without it, the annotations are not evaluated '
        'as expected and the metaclass does not see the fields.',
    ),
    (
        'A binding read outside a render scope',
        '`state.field.set(...)` produces nothing useful; the binding '
        'behaves like a raw value.',
        'Reading a ClientState field returns a `ClientBinding` ONLY inside'
        ' a render scope (`@page` / `@refreshable`). Inside a handler, it '
        'is the raw value. Driving the state from a handler → mutate, do '
        'not bind.',
    ),
    (
        '@validator returning nothing',
        'The field is `None` after writing.',
        'A `@validator("field")` receives `(self, value)` and MUST '
        '`return` the value (transformed or not). `def _n(self, v): '
        'v.strip()` writes `None` — the `return` is missing.',
    ),
    (
        'Passing a ClientBinding to a non-bindable prop',
        '`ComponentUsageError` at construction (that one is loud, and '
        'good).',
        'Only the props listed in `BINDABLE_PROPS` accept a binding. For '
        'something dynamic on variant/size/color → a conditional render on'
        ' the server (`color="error" if failed else "success"`). See the '
        'Catalogue for the per-component list.',
    ),
    (
        'a native for instead of ui.each on stateful components',
        'After a re-render/reorder, open overlays close, checkboxes lose '
        'their state.',
        'Iterate with `ui.each(items, key="id")` as soon as the list '
        'comes from data that can change: the key names each item, so its '
        'state follows it. A Python `for` is enough for a list written in '
        'the code, whose ranks never move. In debug mode, a list with no '
        'key that moves under a client state raises a RuntimeWarning '
        'naming the zone.',
    ),
    (
        'A bindable prop whose attribute does not act on the root',
        'The binding exists but the UI does not react (e.g. `disabled` on '
        'a `<div>` wrapper, `src` on a `<span>`).',
        'The attribute must land on the right carrier element. Call '
        '`forward_binding` in `render()` to '
        'forward the directive onto the child that really carries the '
        'attribute.',
    ),
    (
        'Writing name= / bz-on:click / hx-post by hand',
        'It works, but it is the escape hatch — not the idiom.',
        'The `name` is auto-derived from the binding (`AUTONAME_FROM`). '
        'Actions go through `on_<event>=` (a server callable or a client '
        'string). If you find yourself writing raw `hx-`, it is probably a'
        ' runtime primitive that is missing.',
    ),
]


@page(PATH, layout=shell, title="Traps · Bretzel docs",
      description="Bretzel gotchas, condensed: the silent failures that do not crash but do not work, and how to avoid them.")
def traps_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading('Traps', level=1, size="3xl")
            ui.text(
                'The gotchas, condensed — above all the silent failures, '
                'the ones that do not crash but simply do not work.',
                color="muted", size="lg",
            )

            for title, symptom, fix in _TRAPS:
                with ui.card():
                    with ui.vstack(gap="sm"):
                        with ui.hstack(align="center", gap="sm"):
                            ui.icon("triangle-alert", color="warning")
                            ui.heading(title, level=3)
                        with ui.hstack(align="baseline", gap="sm", wrap=True):
                            ui.badge('Symptom', color="error", variant="soft")
                            ui.text(symptom, color="muted", size="sm")
                        with ui.hstack(align="baseline", gap="sm", wrap=True):
                            ui.badge("Fix", color="success", variant="soft")
                            ui.text(fix, color="muted", size="sm")
