"""REFERENCE — The client runtime.

What the browser runs once the page has arrived: a signal engine, the
`bz-*` directives, and a bridge that owns the transport boundary. A
reference chapter: one does not write these directives by hand in a
Bretzel app — the components emit them. One comes to read it when
stepping outside the frame, or to know what is running.

Every table is introspected from `bretzel/runtime/`: the vocabulary
declared on the Python side, checked against what the JS really wires. No
count is written into this page.
"""

from __future__ import annotations

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.runtime_blocks import (
    directives_mirror,
    magics_mirror,
    runtime_api_mirror,
    runtime_modules_mirror,
    section,
)
from examples.docs.lib.runtime_surface import describe_magics

PATH = "/runtime"


@page(PATH, layout=shell, title="The client runtime · Bretzel docs",
      description="Bretzel's client runtime: the in-house browser engine behind the framework, what it guarantees, and its full bz-* vocabulary.")
def runtime_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading('The client runtime', level=1, size="3xl")
            ui.text(
                'The server stays the source of truth, but something runs '
                'in the browser: a home-made engine, with no npm and no '
                'third-party reactive framework. This page says what it '
                'guarantees, then enumerates its vocabulary.',
                color="muted", size="lg",
            )

            with section(
                'You do not write this',
                'In a Bretzel app, the `bz-*` directives are emitted by '
                'the components: passing `visible=binding` produces a `bz-'
                'show`, `value=binding` produces a `bz-model`. This page '
                'is the emergency exit — what one reads to understand what'
                ' was emitted, or to write by hand the case the components'
                ' do not cover.',
            ):
                pass

            with section(
                'The three guarantees',
                'A client runtime is judged on what it promises when the '
                'server rewrites the page under its feet.',
            ):
                ui.table(
                    columns=[
                        ui.column("g", label="Guarantee"),
                        ui.column("m", label='The mechanism'),
                    ],
                    rows=[
                        {
                            "g": 'A client state survives a server refresh',
                            "m": 'Every scope is keyed by bz-id. After a '
                                 'morph, the subtree is re-scanned: the '
                                 'bindings are thrown away then rewired, '
                                 'and the effects restore what the morph '
                                 'overwrote (text, display, value, '
                                 'classes).',
                        },
                        {
                            "g": 'No round trip just to display something',
                            "m": 'A client binding compiles into a JS '
                                 'expression evaluated in the browser. '
                                 'Showing, hiding, computing a class: '
                                 'nothing goes over the network.',
                        },
                        {
                            "g": "The transport boundary is the runtime's",
                            "m": 'A component never POSTs. It declares a '
                                 'handler; the bridge adds the HMAC '
                                 'signature, the CSRF token, the protocol '
                                 'headers and the client-state snapshot.',
                        },
                    ],
                    size="sm",
                )

            with section(
                'What the runtime weighs',
                'The bundle is concatenated from `_src/` and the `.js` beside each component, with no '
                'bundler and no minifier — the file served is the one you '
                'debug. The load order is declared in `runtime/sources.py`.',
            ):
                runtime_modules_mirror()

            with section(
                'The directives',
                'Grouped by what they guarantee. The vocabulary has two '
                'halves — a Python constant declares it, a JS module wires'
                ' it — and the runtime cannot import Python. A gate '
                'already checks that at commit time '
                '(test_python_js_mirror.py); this table shows it, one '
                'notch stricter: comments stripped, and per source module.',
            ):
                directives_mirror()

            with section(
                'Inside an expression',
                'A directive expression is compiled once then cached. The '
                'current scope is on the scope chain — a bare name reads '
                'the scope — and a few variables are injected.',
            ):
                magics_mirror()
                ui.code(
                    "{ open: false, pick(v) { this.open = false; } }",
                    lang="js",
                )
                ui.text(
                    'The trap: the rebinding of bare names holds for '
                    "inline expressions, not for a scope's methods. Inside"
                    ' a method it is `this.field` — without the `this`, '
                    'you create a global.',
                    color="muted", size="sm",
                )

            with section(
                'The $bz surface',
                'The global object, read module by module. The scope '
                'factories are what a component spreads into its `bz-'
                'data`; the rest is the engine. The “exposes” column is '
                'read from the JS literal, never copied by hand.',
            ):
                runtime_api_mirror()
