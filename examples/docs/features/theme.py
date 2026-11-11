"""REFERENCE — Theme.

What the theme sets, in the order one uses it: the colours (roles and
hues), light/dark, the shapes and the stroke, the typography, a component
theme's structure, the two scopes of customisation, and the case of a
component coming from a third-party package.

⚠️ **The lists are read LIVE** — ``SEMANTIC_COLOR_NAMES``,
``DEFAULT_PALETTE_NAMES``, ``SHAPE_SLOT_NAMES``, ``FONT_SLOT_NAMES``, and
``Theme``'s parameters by introspecting its signature. So the page cannot
announce a colour that does not exist, nor forget a parameter added
tomorrow — which is precisely what had happened to it: it documented
three parameters out of twelve, and it took noticing by eye.
"""

from __future__ import annotations

import inspect

from bretzel import page, ui
from bretzel.theme import (
    DEFAULT_PALETTE_NAMES,
    DEFAULT_SPACING,
    FONT_SLOT_NAMES,
    SEMANTIC_COLOR_NAMES,
    SHAPE_SLOT_NAMES,
    TEXT_SLOT_NAMES,
    Theme,
)

from examples.docs.features.shell import shell

PATH = "/theme"

#: What ``Theme(...)`` accepts, read from its signature. The page's table
#: is built from this tuple: a parameter added to the builder appears
#: here without anybody touching this file, and a parameter removed
#: disappears instead of lying.
THEME_PARAMS: tuple[str, ...] = tuple(inspect.signature(Theme).parameters)

#: Each parameter's sentence. Written by hand — a signature says the
#: NAME and the TYPE, never what it is for. The gate
#: ``test_the_theme_chapter_covers_every_theme_parameter`` checks that
#: both lists coincide in both directions, so an omission is impossible
#: and so is an orphan sentence.
ROLES: dict[str, str] = {
    "semantic": f"The {len(SEMANTIC_COLOR_NAMES)} colour roles — "
                "`primary`, `error`, `surface`… Retint `primary` and "
                "the whole app follows.",
    "semantic_dark": 'The same roles in dark mode. Omitted, a role keeps '
                     'its light colour — only the surfaces have a dark '
                     'value shipped.',
    "palette": 'The named, fixed shades (`green`, `sky`…), served under '
               'the `ui-` prefix so as not to collide with Tailwind.',
    "palette_dark": 'The same shades in dark mode.',
    "components": 'The theme of one precise component — its slots, '
                  'variants, sizes, modifiers. Merged with the shipped '
                  'one.',
    "fonts": f"The {len(FONT_SLOT_NAMES)} families "
             f"({', '.join(FONT_SLOT_NAMES)}) → `--font-<slot>`.",
    "spacing": 'The spacing step: one length for everything, or three '
               'families named like the radii — `field` (the controls: '
               '`h-10` is ten notches), `box` (the padding inside a card '
               'or a pane), `gap` (the space between blocks). `box` and '
               '`gap` follow `field` unless given, so a page can tighten '
               "without shrinking its buttons. Omitted, Tailwind's "
               f"`{DEFAULT_SPACING}` holds.",
    "text": f"The {len(TEXT_SLOT_NAMES)} text steps → `--text-<step>`. "
            f"The middle one is called `base`, not `md` — `md` is a `size=` name.",
    "shape": f"The {len(SHAPE_SLOT_NAMES)} radius families "
             f"({', '.join(SHAPE_SLOT_NAMES)}) → `--radius-<family>`.",
    "stroke": 'The stroke width. ONE value: the two other steps derive '
              'from it in `calc()` (`-strong` ×2, `-accent` ×4).',
    "css": "A CSS file of the app's, injected as is — that is where a "
           '`@font-face`, a `@keyframes`, a `@supports` lives.',
    "scrollbar": "The scrollbar's width and colours.",
    "icons": 'The default icon set, its style and its size.',
    "base": f"The theme one inherits from. `base=None` starts from scratch — and "
            f"you become responsible for the {len(SEMANTIC_COLOR_NAMES)} roles.",
}


def swatches(names: tuple[str, ...]) -> None:
    """A row of solid swatches.

    Every colour is rendered in its own hue, with its auto-contrasted
    `foreground` — hence readable, the neutrals included.
    """
    with ui.hstack(gap="xs", wrap=True):
        for name in names:
            ui.badge(name, color=name, variant="solid")


def roles_par_mode() -> None:
    """Which roles FLIP in dark mode, and which do not — MEASURED.

    ⚠️ This table used to be a sentence, and the sentence was false: it
    said "every role is derived from the light one by contrast", whereas
    six roles out of eleven carry the SAME colour in both modes. What is
    derived by contrast is the ``foreground``, not the background.

    Hence a table that interrogates the shipped theme instead of
    narrating it.
    """
    palette = Theme().get_palette()
    bascule: list[str] = []
    stable: list[str] = []
    for nom in SEMANTIC_COLOR_NAMES:
        clair = palette.resolve(nom, mode="light")
        sombre = palette.resolve(nom, mode="dark")
        (bascule if clair.bg_hex != sombre.bg_hex else stable).append(nom)
    ui.table(
        columns=[
            ui.column("famille", label="Family"),
            ui.column("roles", label='Roles'),
            ui.column("sombre", label="In dark mode"),
        ],
        rows=[
            {"famille": "Brand and status",
             "roles": ", ".join(stable),
             "sombre": 'colour UNCHANGED — only the foreground is '
                       'recomputed'},
            {"famille": "Surfaces",
             "roles": ", ".join(bascule),
             "sombre": 'colour replaced by its dark value'},
        ],
        size="sm",
    )


def parametres_table() -> None:
    """``Theme``'s parameters, read from the signature."""
    ui.table(
        columns=[
            ui.column("param", label='Parameter'),
            ui.column("role", label='What it settles'),
        ],
        rows=[
            {"param": nom, "role": ROLES.get(nom, '(undocumented)')}
            for nom in THEME_PARAMS
        ],
        size="sm",
    )


@page(PATH, layout=shell, title="Theme · Bretzel docs",
      description="Theme a Bretzel app from one Theme object: colours, shapes, stroke and typography, compiled to Tailwind v4 with no Node.js.")
def theme_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading('Theme', level=1, size="3xl")
            ui.text(
                'The theme carries the visual identity: the colours, the '
                'shapes, the stroke, the typography. Under the bonnet it '
                'is Tailwind v4, compiled by a Rust binary — no Node.js in'
                ' production.',
                color="muted", size="lg",
            )

            # ── The overview, read from the signature ─────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(f"The {len(THEME_PARAMS)} levers", level=2)
                    ui.text(
                        'Everything is set from a single object. One '
                        'passes only what one changes; the rest inherits '
                        'the shipped theme.',
                        color="muted", size="sm",
                    )
                    parametres_table()
                    ui.code(
                        'app = Bretzel(theme=Theme(semantic={"primary": "#27754a"}))\n',
                        lang="python",
                    )

            # ── Tailwind sous le capot ────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Tailwind under the bonnet', level=2)
                    ui.text(
                        'Every component compiles into Tailwind v4 '
                        'classes. You can always add your own through '
                        '`classes=` — it is the universal escape hatch, on'
                        ' any component. Your classes are placed last, so '
                        'they win on source order.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'ui.button("Pay", classes="rounded-full px-8 shadow-lg")\nui.card(classes="border-2 border-dashed")\n# raw Tailwind: p-4, flex gap-2, hover:bg-…, etc.\n',
                        lang="python",
                    )
                    ui.alert(
                        'An ASSEMBLED class does not survive production. '
                        '`f"bg-{colour}-500"` works in dev — the browser '
                        'compiler sees everything — and disappears in '
                        'production, where the binary scans literal text. '
                        'The HTML is identical on both sides, so it only '
                        'shows IN production. Write the whole class, or go'
                        ' through the theme.',
                        color="warning",
                        title='The trap that only breaks in production',
                    )

            # ── 1. Semantic colours ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The semantic colours (roles)', level=2)
                    ui.text(
                        f"{len(SEMANTIC_COLOR_NAMES)} ROLE slots. "
                        "Their point: they remap with the theme — retint "
                        "`primary` and the whole app follows. They are "
                        "passed as `color=`.",
                        color="muted", size="sm",
                    )
                    swatches(SEMANTIC_COLOR_NAMES)
                    ui.code(
                        'ui.button("OK", color="primary")\nui.alert("Failed", color="error")\n',
                        lang="python",
                    )
                    ui.text(
                        'Automatic foreground: every role has a '
                        '`<color>-foreground` derived by contrast — the '
                        'text stays readable on the background, in light '
                        'as in dark.',
                        color="muted", size="sm",
                    )

            # ── 2. Couleurs palette ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The Bretzel palette colours (shades)',
                               level=2)
                    ui.text(
                        f"{len(DEFAULT_PALETTE_NAMES)} NAMED, FIXED hues "
                        "(not roles — concrete colours). "
                        "Two ways to use them:",
                        color="muted", size="sm",
                    )
                    swatches(DEFAULT_PALETTE_NAMES)
                    ui.code(
                        '# 1) through color= — the component wears the colour\'s bridge\nui.badge("New", color="green")\n#    → class="… bz-c-green": its own classes read --bz-bg, --bz-text…\n\n# 2) through classes= directly (the explicit form)\nui.badge("New", classes="bg-ui-green text-ui-green-foreground")\n',
                        lang="python",
                    )
                    ui.text(
                        "The `ui-` prefix avoids clashing with Tailwind's "
                        'stock utilities (`bg-green-500`). And of course '
                        'all the usual Tailwind stays available through '
                        '`classes=`.',
                        color="muted", size="sm",
                    )

            # ── 3. Clair et sombre ────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Light and dark", level=2)
                    ui.text(
                        f"The {len(SEMANTIC_COLOR_NAMES)} roles do not behave "
                        "the same when the lights go off, and the split is "
                        "clean — measured on the shipped theme, not "
                        "described from memory:",
                        color="muted", size="sm",
                    )
                    roles_par_mode()
                    ui.text(
                        'In other words: a brand colour does NOT change '
                        'because one switches to dark. It is the surfaces '
                        "that flip, and that is enough. Every role's "
                        '`foreground`, for its part, is ALWAYS recomputed '
                        'by contrast — which is why the text stays '
                        'readable in both modes without anyone writing '
                        'anything.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        '# The current mode READS like an ambient state.\nfrom bretzel import ColorScheme\n\nui.text(f"mode = {ColorScheme().mode}")   # light | dark | system\n\n# `semantic_dark=` is ONLY needed if the light mode\'s\n# value does not work in dark — a dark green on a dark\n# background, for instance.\nTheme(\n    semantic={"primary": "#14532d"},      # readable in light\n    semantic_dark={"primary": "#4ade80"}, # …not in dark\n)\n',
                        lang="python",
                    )
                    ui.text(
                        'The mode is applied before the first pixel — no '
                        'white flash when loading a page in dark mode.',
                        color="muted", size="sm",
                    )

            # ── 4. Formes et trait ────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The shapes and the stroke', level=2)
                    ui.text(
                        "Radii are set per FAMILY, not per "
                        "component: "
                        f"{', '.join('`' + s + '`' for s in SHAPE_SLOT_NAMES)}. "
                        "`box` for what contains, `field` for a control "
                        "one aims at, `selector` for a small mark or a "
                        "nested control.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        'Theme(\n    shape={"box": "1rem", "field": "0.5rem"},\n    stroke="1.5px",   # -strong ×2, -accent ×4 derive from it\n)\n',
                        lang="python",
                    )
                    ui.text(
                        'An unknown family RAISES at startup, with the '
                        'message naming the three valid ones — an invented'
                        ' token would be read by no class, and the radius '
                        'would not move, in silence.',
                        color="muted", size="sm",
                    )

            # ── 5. Typographie ────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Typography', level=2)
                    ui.text(
                        f"`fonts=` declares the family for the "
                        f"{len(FONT_SLOT_NAMES)} slots "
                        f"({', '.join(FONT_SLOT_NAMES)}); `css=` carries the "
                        "`@font-face` that makes it available. They are the "
                        "two halves of one question: WHAT to load, "
                        "and HOW.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        'Theme(\n    fonts={"sans": "Inter, ui-sans-serif, system-ui, sans-serif"},\n    css=Path("app/identity.css"),   # @font-face, keyframes\n)\n',
                        lang="python",
                    )
                    ui.alert(
                        'Bretzel downloads no font and writes no `<link>` '
                        'to a third-party CDN. The font is served from '
                        '`Bretzel(static_dir=…)`, like the rest of the '
                        'assets — it is the only form that makes the '
                        'rendering depend on nobody else, and leaks no '
                        "visitor's IP address.",
                        color="info", title='No CDN, and that is a choice',
                    )

            # ── 6. A component theme's structure ──────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The structure of a component theme',
                               level=2)
                    ui.text(
                        "A component's theme is ONE SINGLE DICT holding "
                        'everything: the `root` and the other `slots`, '
                        'plus the `variants` / `sizes` / `modifiers` axes.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        '# bretzel/components/feedback/badge/theme.py\nBADGE_THEME = {\n    "slots": {                    # root + named slots\n        "root": "inline-flex items-center gap-1 …",\n        "dot":  "shrink-0 rounded-full bg-current",\n    },\n    "variants": {                 # the colour STEPS\n        "soft":  "bg-(--bz-bg) text-(--bz-text)",\n        "solid": "bg-(--bz-solid) text-(--bz-on-solid)",\n    },\n    "sizes": {                    # a string OR a multi-slot dict\n        "sm": "px-2 py-0.5 text-xs",\n    },\n    "modifiers": {                # a bool reactive_prop → a class\n        "loading": "cursor-progress",\n    },\n}\n',
                        lang="python",
                    )
                    ui.text(
                        '`compose_class("root")` assembles in order: the '
                        '`root` slot, then the active `variant`, then the '
                        '`size`, then the truthy `modifiers`. Every key of'
                        ' the dict has a precise role:',
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("cle", label='Key'),
                            ui.column("role", label='Role'),
                        ],
                        rows=[
                            {"cle": "slots", "role": "the component's pieces (`root`"
                                                     ' + named slots)'},
                            {"cle": "variants", "role": 'alternative styles — one '
                                                        'active value at a time'},
                            {"cle": "sizes", "role": 'sizes — one active value at a '
                                                     'time'},
                            {"cle": "modifiers", "role": 'bool flags — several can be on'
                                                         ' at once'},
                        ],
                        size="sm",
                    )

            # ── 7. Personnaliser ──────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Customising — global or local", level=2)
                    ui.text(
                        'Two scopes, and they do not compose the same way:'
                        ' the central theme REDEFINES the entry it names, '
                        "an instance override is ADDED to the theme's.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("portee", label='Scope'),
                            ui.column("comment", label="How"),
                        ],
                        rows=[
                            {"portee": "Global (the whole app)",
                             "comment": "Bretzel(theme=Theme(components={…}, "
                                        "semantic={…}, shape={…}))"},
                            {"portee": 'Local (one instance)',
                             "comment": "ui.button(classes=\"…\") or "
                                        "ui.button(slots={\"root\": \"…\"})"},
                        ],
                        size="sm",
                    )
                    ui.code(
                        'from bretzel.theme import Theme\n\n# GLOBAL — applies to every Button in the app.\n# An entry supplied here REDEFINES that entry of the\n# shipped theme (the whole string); the rest (slots,\n# variants, sizes) is preserved by merging.\napp = Bretzel(theme=Theme(\n    semantic={"primary": "#27754a"},\n    components={"button": {"sizes": {"md": "h-11 px-5 text-sm gap-2"}}},\n))\n\n# LOCAL — this Button only: the string is ADDED to the slot.\nui.button("Just this one", slots={"root": "rounded-2xl"})\n',
                        lang="python",
                    )

            # ── 8. Un paquet tiers ────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Theming a component that comes from '
                               'elsewhere',
                               level=2)
                    ui.text(
                        'A third-party library can publish its components '
                        "so they become themable like the framework's — "
                        'otherwise all that would be left is `classes=` at'
                        ' the call site, repeated everywhere, with no '
                        'cascade and no dark-mode coherence.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        '# the third-party package\'s pyproject.toml\n[project.entry-points."bretzel.scan_roots"]\nmy-components = "my_components"     # sweep my files\n\n[project.entry-points."bretzel.components"]\nmy-components = "my_components"     # load my code\n\n# And in the app that installs it:\nTheme(components={"gauge": {"slots": {"root": "…"}}})\n',
                        lang="text",
                    )
                    ui.text(
                        'Two declarations because they are two different '
                        'contracts: “sweep my files” is not “load my '
                        'code”. A key colliding with a framework '
                        "component's is REFUSED at startup — otherwise the"
                        ' app would think it was styling one and would '
                        'style the other.',
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.hstack(align="baseline", gap="sm", wrap=True):
                    ui.text('The exact contract per component (slots, '
                            'variants, sizes available):',
                            color="muted", size="sm")
                    ui.link("ui.* catalogue →", href="/components")
