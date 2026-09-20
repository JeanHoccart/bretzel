"""``/theme-studio`` — set the theme live, and leave with the code.

This page does not drive the components: it drives **the generator's
inputs**. One moves the eleven semantic colours — in light AND in dark —
the three radius families, the stroke width and the density; everything
below recomputes: the twelve steps, the preview's real components, and
dark mode with them.

Why it sets VARIABLES and calls no server
------------------------------------------

The steps (``--bz-bg``, ``--bz-text``…) are derived in CSS from
``--color-<name>``: changing the source is enough to repaint the whole
page, and the browser does it alone.

And the output is **code**, not a saved state: the block at the bottom
renders the ``Theme(...)`` to paste into ``core/theme.py``. Git is the
persistence.

⚠️ **An injected ``<style>``, not INLINE styles** — and it is the fix of
2026-08-30. Writing ``--color-primary`` as an inline style on ``<html>``
wins against ALL the rules, hence against the theme's ``.dark`` block: as
soon as one touched a colour, dark mode stopped working for it. An
injected sheet carries both rules, ``:root`` and ``.dark``, and the
cascade gets its job back.

⚠️ **What is set here is set HOT. The rest is not here.** Tailwind inlines
a bare number for ``ring-2``, ``duration-150``, ``z-40`` — no variable
carries them, so no slider can move them without recompiling. Putting
them here would give the illusion of the opposite.

What the page does not have yet
--------------------------------

- the typography (``--font-sans`` + the ``--text-*`` scale);
- the relief (``--shadow-*``), which becomes settable again if its token
  is written from ``var()`` — cf. the work note.
"""

import json

from bretzel import ui
from bretzel.state import ClientExpression, ClientState, field
from bretzel.theme import SHAPE_SLOT_NAMES

PATH = "/theme-studio"

#: The eleven semantic slots: (name, role, light default, dark default).
#: The order is the reading one — the accent first, the backgrounds
#: next.
SLOTS: list[tuple[str, str, str, str]] = [
    ("primary",    "l'accent de marque",           "#682747", "#682747"),
    ("secondary",  "l'accent secondaire",          "#3a52b0", "#3a52b0"),
    ("success",    'what succeeded',              "#2f9e64", "#2f9e64"),
    ("warning",    'what needs attention',     "#f0a91b", "#f0a91b"),
    ("error",      'what failed',              "#e5484d", "#e5484d"),
    ("info",       'a neutral piece of information',       "#0e9bc4", "#0e9bc4"),
    ("background", "the page's background",           "#fafafa", "#0a0a0a"),
    ("surface",    "a panel's background",         "#ffffff", "#151515"),
    ("interface",  "a control's fill", "#f0f0f1", "#212121"),
    ("text",       'the running text',             "#171717", "#f5f5f5"),
    ("muted",      'the secondary text',          "#6b6b6e", "#a0a0a3"),
]

#: The colour defaults, DERIVED from :data:`SLOTS` — light mode for the
#: bare field, dark for its ``d_`` twin.
#:
#: They were written twice: in ``SLOTS`` for the display, and as a
#: literal on every field of the class. Two copies of one value always
#: drift, and this one could only diverge in SILENCE — the page would
#: have shown one value and the store kept another.
COLOR_DEFAULTS: dict[str, str] = {
    **{name: light for name, _role, light, _dark in SLOTS},
    **{f"d_{name}": dark for name, _role, _light, dark in SLOTS},
}

#: The five sliders' defaults. They have no display table to draw them
#: from — their tuple lives in ``page()`` — so they are here, in the same
#: place as the colours, and the class reads them the same way.
SLIDER_DEFAULTS: dict[str, float] = {
    "box": 0.75,
    "field_": 0.75,
    "selector": 0.375,
    "stroke": 1.0,
    "spacing": 0.1875,
}

#: The twenty-seven shipped values, in one block. It is what "Reset"
#: puts back, and it is the SAME source as the class's defaults — so the
#: button cannot bring things back to a third state.
SHIPPED_DEFAULTS: dict[str, str | float] = {**COLOR_DEFAULTS, **SLIDER_DEFAULTS}

PREVIEW_COLORS = ["primary", "success", "warning", "error", "info", "muted"]


class Studio(ClientState, persist="local"):
    """The settings. ``persist="local"``: one finds one's theme again on
    coming back, without anything going to the server."""

    primary:    str = field(default=COLOR_DEFAULTS["primary"])
    secondary:  str = field(default=COLOR_DEFAULTS["secondary"])
    success:    str = field(default=COLOR_DEFAULTS["success"])
    warning:    str = field(default=COLOR_DEFAULTS["warning"])
    error:      str = field(default=COLOR_DEFAULTS["error"])
    info:       str = field(default=COLOR_DEFAULTS["info"])
    background: str = field(default=COLOR_DEFAULTS["background"])
    surface:    str = field(default=COLOR_DEFAULTS["surface"])
    interface:  str = field(default=COLOR_DEFAULTS["interface"])
    text:       str = field(default=COLOR_DEFAULTS["text"])
    muted:      str = field(default=COLOR_DEFAULTS["muted"])

    d_primary:    str = field(default=COLOR_DEFAULTS["d_primary"])
    d_secondary:  str = field(default=COLOR_DEFAULTS["d_secondary"])
    d_success:    str = field(default=COLOR_DEFAULTS["d_success"])
    d_warning:    str = field(default=COLOR_DEFAULTS["d_warning"])
    d_error:      str = field(default=COLOR_DEFAULTS["d_error"])
    d_info:       str = field(default=COLOR_DEFAULTS["d_info"])
    d_background: str = field(default=COLOR_DEFAULTS["d_background"])
    d_surface:    str = field(default=COLOR_DEFAULTS["d_surface"])
    d_interface:  str = field(default=COLOR_DEFAULTS["d_interface"])
    d_text:       str = field(default=COLOR_DEFAULTS["d_text"])
    d_muted:      str = field(default=COLOR_DEFAULTS["d_muted"])

    spacing: float = field(default=SLIDER_DEFAULTS["spacing"])
    box: float = field(default=SLIDER_DEFAULTS["box"])
    field_: float = field(default=SLIDER_DEFAULTS["field_"])
    selector: float = field(default=SLIDER_DEFAULTS["selector"])
    stroke: float = field(default=SLIDER_DEFAULTS["stroke"])


#: The JavaScript MIRROR of ``bretzel.theme.palette.resolve_color_pair``.
#:
#: Why it exists. A colour's foreground is not "black or white": it is
#: derived from the background — lightness chosen by a WCAG luminance
#: threshold, then TINTED with the background's hue so the pair stays of
#: a piece. That algorithm lives in Python and runs when the CSS is
#: generated. The studio, for its part, never talks to the server:
#: without this mirror, choosing white for ``primary`` left white text on
#: white, and no reload could change it — the page sends its colours
#: nowhere.
#:
#: Why it is an accepted DUPLICATION. It is the same arbitration as
#: ``protocol.py`` ↔ ``runtime.js``: the JS cannot import Python. And as
#: over there, the duplication is GATED — the algebra's six numbers are
#: named in ``palette.py`` and
#: ``test_the_foreground_algebra_is_mirrored_in_js`` checks they appear
#: here.
FOREGROUND_JS = """
if (!window.bzFg) {
  var toHls = function (r, g, b) {
    r /= 255; g /= 255; b /= 255;
    var mx = Math.max(r, g, b), mn = Math.min(r, g, b);
    var l = (mx + mn) / 2, h = 0, s = 0;
    if (mx !== mn) {
      var d = mx - mn;
      s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
      if (mx === r) h = (g - b) / d + (g < b ? 6 : 0);
      else if (mx === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h /= 6;
    }
    return [h, l, s];
  };
  var toRgb = function (h, l, s) {
    if (s === 0) { var v = Math.round(l * 255); return [v, v, v]; }
    var q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    var f = function (t) {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    return [Math.round(f(h + 1 / 3) * 255), Math.round(f(h) * 255),
            Math.round(f(h - 1 / 3) * 255)];
  };
  var lum = function (r, g, b) {
    var ch = function (v) {
      v /= 255;
      return v <= 0.03928 ? v / 12.92
                          : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
  };
  window.bzFg = function (hex) {
    var m = /^#([0-9a-f]{6})$/i.exec(String(hex || '').trim());
    if (!m) return '';
    var n = parseInt(m[1], 16);
    var r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    var hls = toHls(r, g, b);
    var baseL = lum(r, g, b) > 0.179 ? 0.08 : 0.96;
    var baseS = Math.min(hls[2] * 0.12, 0.08);
    // Mirror of ``palette._readable_fg``: the tint BACKS OFF until AA
    // (4.5) is cleared, and we stop at the first sufficient step.
    // Without this loop, the studio would render a foreground different
    // from the one Python computes on the three colours that needed it
    // — muted, pink, plum — and nobody would see it, the two halves
    // being plausible on their own.
    var extreme = baseL < 0.5 ? 0 : 1;
    var out = [0, 0, 0];
    for (var step = 0; step <= 5; step++) {
      var t = step / 5;
      out = toRgb(hls[0], baseL + (extreme - baseL) * t, baseS * (1 - t));
      var la = lum(r, g, b), lb = lum(out[0], out[1], out[2]);
      var hi = Math.max(la, lb), lo = Math.min(la, lb);
      if ((hi + 0.05) / (lo + 0.05) >= 4.5) break;
    }
    return '#' + out.map(function (v) {
      return ('0' + v.toString(16)).slice(-2);
    }).join('');
  };
}
"""


#: ``(radius family, store field)``.
#:
#: The families come from ``SHAPE_SLOT_NAMES``, the framework tuple
#: ``Theme(shape=…)`` and the radius gate already use: a fourth family
#: added there appears here without anybody touching it. The only
#: information SPECIFIC to this page is the name shift — ``field`` is a
#: function of ``bretzel.state``, so the store field is called
#: ``field_``.
#:
#: Written once: the injected sheet and the exported code must name the
#: same families, and two lists would have named two distinct sets at the
#: first addition.
SHAPE_FIELDS: tuple[tuple[str, str], ...] = tuple(
    (family, "field_" if family == "field" else family)
    for family in SHAPE_SLOT_NAMES
)


def path(name: str) -> str:
    """A store field's JS path.

    It is deterministic — class, instance key, field — so we build it
    here rather than re-guess it in every expression.
    """
    return f"$bz.state.Studio.default.{name}"


def reset_expression() -> str:
    """The JS that puts EVERY field back to the value the framework
    SHIPS.

    Why this button exists
    -----------------------
    ``Studio`` is ``persist="local"``: the settings survive closing the
    tab, which is the right default for a page one comes back to. But the
    consequence had no way out — once touched, **nothing brings back the
    framework's values**, not even a reload, and repainting the default
    theme changes nothing about what is seen. Flagged on 2026-09-13: the
    page still showed a ``#e93d82`` pink entered weeks earlier, while the
    shipped default was an indigo.

    Why it is built from the CLASS
    -------------------------------
    :data:`SHIPPED_DEFAULTS` is the table ``Studio``'s FIELDS read
    themselves: so the button and the store cannot diverge. Writing the
    list by hand here would make it drift at the first slider added — and
    it would be the usual silent drift: the button would reset everything
    EXCEPT the new setting, which looks like a button that works. The
    gate ``test_the_studio_exports_every_knob`` holds both ends.
    """
    return "; ".join(
        f"{path(name)} = {json.dumps(value)}"
        for name, value in sorted(SHIPPED_DEFAULTS.items())
    )


def repaint_effect() -> str:
    """The effect that repaints the page, through an INJECTED sheet.

    It writes a single ``<style>`` carrying ``:root { … }`` and
    ``.dark { … }``. It is what makes dark mode settable: an inline style
    on ``<html>`` would win against the theme's ``.dark`` rule and freeze
    the colour in both modes.

    The sheet is appended at the end of ``<head>``, hence AFTER the
    theme's: at equal specificity, the order decides, and ours wins.
    """
    def block(prefix: str) -> str:
        """Every source writes its PAIR: the background AND its
        foreground.

        Writing the background alone left ``--color-<name>-foreground``
        at the value computed at startup by the server — hence white on
        white as soon as one chose a light colour, with no reload able to
        do anything about it.
        """
        return " + ".join(
            f"'--color-{name}:' + {path(prefix + name)} + ';'"
            f" + '--color-{name}-foreground:'"
            f" + window.bzFg({path(prefix + name)}) + ';'"
            for name, _role, _light, _dark in SLOTS
        )

    # The THREE families, and nothing else. This line used to write
    # ``--radius-sm/md/lg/xl`` from a single slider × four factors — so
    # it moved four tokens with nothing saying why they differed. Since
    # 2026-08-30 the theme only writes ``rounded-box`` /
    # ``rounded-field`` / ``rounded-selector``, which are three distinct
    # questions.
    radius = " + ".join(
        f"'--radius-{family}:' + {path(attr)} + 'rem;'"
        for family, attr in SHAPE_FIELDS
    )
    # The stroke: a single base, the two steps derive from it. Writing
    # all three here rather than the base alone would have frozen the
    # ratio in the page instead of leaving it to the theme's `calc()`.
    stroke = f"'--bz-stroke:' + {path('stroke')} + 'px;'"
    return (
        FOREGROUND_JS
        + "let s = document.getElementById('bz-studio');"
        " if (!s) { s = document.createElement('style');"
        " s.id = 'bz-studio'; document.head.appendChild(s); }"
        " s.textContent = ':root{' + "
        + block("")
        + f" + '--spacing:' + {path('spacing')} + 'rem;' + "
        + radius
        + ' + ' + stroke
        + " + '}.dark{' + "
        + block("d_")
        + " + '}';"
    )


def rounded(name: str) -> str:
    """The field, rounded to the thousandth.

    A slider with a 0.05 step returns ``0.7500000000000001`` one time in
    twenty. Invisible in an injected sheet; copied as is into the
    exported code, where it shows.

    ⚠️ **Why it is not ``round(binding, 3)``.** The framework emits
    exactly that JS — ``ClientBinding.__round__`` returns the same string
    to the character. It is not usable from here: these emitters are
    module functions, called with no render context so the gate can read
    them at import, and outside a context ``Studio().box`` returns a
    ``float``, not a binding. Checked on 2026-08-31, not assumed. It is
    the same arbitration that justifies ``path()`` just above.
    """
    return f"(Math.round({path(name)} * 1000) / 1000)"


def export_expression() -> str:
    """The code to paste, in a single expression for ``bz-text``.

    It carries EVERYTHING the page sets, and that is the point: until
    2026-08-31 it only emitted the twenty-two colours. The four shape
    sliders and the density one were set, shown on screen, and vanished
    on copy — without a word. It is an exporter's worst failure mode: a
    plausible and incomplete output.
    ``test_the_studio_exports_every_knob`` guards it.

    The density comes out as ``spacing=`` since 2026-09-13. It went
    through ``css="@theme { --spacing: … }"``, for want of a parameter of
    its own — the framework did not open the density, on the grounds that
    every component already has its ``size=``. The grounds held for a
    MULTIPLIER; they did not hold for the scale's base, which two apps
    ended up moving by hand. The exported code stays true in both forms,
    but this one is validated at construction where a CSS block was taken
    on trust.
    """
    def block(prefix: str) -> str:
        return " + '\\n' + ".join(
            f"'        \"{name}\": \"' + {path(prefix + name)} + '\",'"
            for name, _role, _light, _dark in SLOTS
        )

    shape = " + ', ' + ".join(
        f"'\"{family}\": \"' + {rounded(attr)} + 'rem\"'"
        for family, attr in SHAPE_FIELDS
    )
    return (
        "'Theme(\\n    semantic={\\n' + "
        + block("")
        + " + '\\n    },\\n    semantic_dark={\\n' + "
        + block("d_")
        + " + '\\n    },\\n    shape={' + "
        + shape
        + " + '},\\n    stroke=\"' + "
        + rounded("stroke")
        + " + 'px\",\\n    spacing=\"' + "
        + rounded("spacing")
        + " + 'rem\",\\n)'"
    )


def component_preview(color: str) -> None:
    """REAL components, not swatches. It is the only way to see that a
    step breaks."""
    with ui.card(padding="sm"):
        with ui.hstack(gap="sm", align="center", classes="flex-wrap"):
            ui.badge(color, color=color, variant="soft")
            ui.badge(color, color=color, variant="solid")
            ui.badge(color, color=color, variant="outline")
            ui.button("Action", color=color, size="sm")
            ui.button("Douce", color=color, variant="soft", size="sm")
            ui.button("Contour", color=color, variant="outline", size="sm")
            ui.icon("sparkles", color=color)
            ui.progress(value=62, color=color, classes="w-32")


def page() -> None:
    settings = Studio()

    with ui.vstack(gap="lg", attrs={"bz-effect": repaint_effect()}):
        ui.heading("Theme studio", level=1)
        ui.text(
            'The eleven semantic colours in BOTH modes, the three radius '
                'families, the stroke and the density. Everything recomputes '
                'in the browser, with no server round trip. The output is '
                'CODE: the block at the bottom pastes into core/theme.py.',
            color="muted",
        )
        ui.text(
            "The light / dark / system selector lives in the sidebar's "
                'footer. Both colour columns stay editable whichever mode is '
                'displayed.',
            color="muted", size="sm",
        )

        # ⚠️ The button is not an ornament: without it, ``persist="local"``
        # is a one-way trip. It writes the signals in the clear (an
        # ``on_click`` string, hence pure client), and the persistence
        # follows — no request, no reload.
        with ui.hstack(gap="sm", align="center", classes="flex-wrap"):
            ui.button(
                'Reset',
                icon_left="rotate-ccw",
                variant="outline",
                size="sm",
                on_click=reset_expression(),
            )
            ui.text(
                'puts the twenty-seven settings back to the values the '
                    'framework ships. Your settings are kept in this browser,'
                    ' so they survive a theme changing on the server side.',
                size="xs", color="muted",
            )

        # ⚠️ ONE single column, across the whole width. The page was
        # built in two columns side by side — the settings on the left, a
        # preview on the right — and the two fought over the space: the
        # fields squeezed to 144 px while the preview was cut off. Two
        # things that need width do not go side by side; they go one
        # under the other.
        ui.divider()
        ui.heading('The sources', level=2)
        ui.text(
            'Twenty-two values typed in. Everything else descends from '
                'them — the twelve steps of every colour, in both modes.',
            size="sm", color="muted",
        )
        # ``min_col`` IS ``repeat(auto-fit, minmax(20rem, 1fr))`` — the
        # primitive existed, I had rewritten it by hand as an arbitrary
        # class in a ``ui.container``, which also carries a ``px-6 py-8``
        # by default: hence the 24 px of indentation the grid should
        # never have had.
        with ui.grid(min_col="20rem", gap="lg"):
            for name, role, _light, _dark in SLOTS:
                with ui.vstack(gap="xs"):
                    with ui.hstack(gap="sm", align="baseline",
                                   classes="flex-wrap"):
                        ui.text(name, size="sm", weight="medium")
                        ui.text(role, size="xs", color="muted")
                    with ui.grid(cols=2, gap="sm"):
                        ui.color_picker(getattr(settings, name), size="sm")
                        ui.color_picker(
                            getattr(settings, f"d_{name}"), size="sm"
                        )
        ui.text(
            'In each pair: light mode on the left, dark on the right.',
            size="xs", color="muted",
        )

        ui.divider()
        ui.heading('The shapes', level=2)
        ui.text(
            'Three radius families, because three different questions: '
                'what CONTAINS, what one TOUCHES, the small MARKS. A single '
                'global scale would not be adjustable — it would move all '
                'three with the same gesture.',
            size="sm", color="muted",
        )
        ui.text(
            'What does NOT move: the switch, the radio, the spinner and '
                'the progress bar stay round. Their roundness is their shape '
                '— a square switch reads as a checkbox.',
            size="xs", color="muted",
        )
        # The unit lives in the tuple. It was glued on as
        # ``f"{label} (rem)"`` for everybody, which gave "the stroke
        # width (px) (rem)".
        with ui.grid(min_col="16rem", gap="lg"):
            for label, unit, binding, lo, hi, step in (
                ('--radius-box · what CONTAINS', "rem",
                 settings.box, 0.0, 2.0, 0.05),
                ('--radius-field · what one TOUCHES', "rem",
                 settings.field_, 0.0, 2.0, 0.05),
                ('--radius-selector · the small MARKS', "rem",
                 settings.selector, 0.0, 1.0, 0.025),
                ('--bz-stroke · the stroke width', "px",
                 settings.stroke, 0.0, 4.0, 0.5),
                ('--spacing · the density', "rem",
                 settings.spacing, 0.15, 0.4, 0.01),
            ):
                with ui.vstack(gap="none"):
                    ui.text(f"{label} ({unit})", size="xs",
                            color="muted", weight="medium")
                    ui.slider(value=binding, min=lo, max=hi,
                              step=step, size="sm")

        ui.divider()
        ui.heading('The preview', level=2)
        ui.text(
            'REAL components, and nothing else. The page also showed the '
                'twelve steps as swatches: twelve unlabelled squares, cut off'
                ' by the column, unreadable in dark mode — and above all '
                'redundant. A `soft` badge IS `--bz-bg`, an `outline` badge '
                'IS `--bz-border`, a solid button IS `--bz-solid` with `--bz-'
                'on-solid` written on it. The component says the same thing, '
                'and says in addition whether it works.',
            size="sm", color="muted",
        )
        with ui.grid(min_col="24rem", gap="md"):
            for color in PREVIEW_COLORS:
                component_preview(color)

        ui.divider()
        ui.heading('The code to paste', level=2)
        ui.text(
            'Git is the persistence. This page is a generator, not a '
                'theme store — what you tune by eye ends up in core/theme.py,'
                ' versioned and reviewed.',
            color="muted", size="sm",
        )
        # ⚠️ ``ui.code`` and no longer a hand-dressed ``ui.container``.
        # The block was a ``<div>`` carrying its own stack of
        # ``font-mono … border … bg-interface`` classes: it looked like
        # NO other code block in the app, and it could not follow the
        # theme it exists to set. ``text`` is bindable, so a
        # ``ClientExpression`` goes through — the component emits a
        # ``<span bz-text>`` inside its ``<code>``.
        ui.code(ClientExpression(export_expression()), lang="python")
