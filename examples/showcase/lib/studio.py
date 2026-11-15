"""The theme store, and the three JavaScript expressions that read it.

Every page of the showcase is painted by ONE client store, ``Studio``.
The shell carries :func:`repaint_effect`, so an identity picked in the
top bar, or a colour moved in ``/studio``, repaints the whole app — the
components never know. The studio page adds the knobs and
:func:`export_expression`, the ``Theme(...)`` to paste into
``core/theme.py``.

Why it sets VARIABLES and calls no server
------------------------------------------

The twelve steps (``--bz-bg``, ``--bz-text``…) are derived in CSS from
``--color-<name>``, the radii from ``--radius-<family>``, every size
from ``--spacing``: changing the sources is enough to repaint the page,
and the browser does it alone.

⚠️ **An injected ``<style>``, not INLINE styles.** Writing
``--color-primary`` as an inline style on ``<html>`` wins against ALL
the rules, hence against the theme's ``.dark`` block: dark mode stopped
working for any colour one touched. An injected sheet carries both
rules, ``:root`` and ``.dark``, and the cascade keeps its job.

⚠️ **What is set here is set HOT. The rest is not here.** Tailwind
inlines a bare number for ``ring-2``, ``duration-150``, ``z-40`` — no
variable carries them, so no knob can move them without recompiling.
The relief (``--shadow-*``) is in the same case today.
"""

import hashlib
import json

from bretzel.state import ClientState, field
from bretzel.theme import (
    DEFAULT_SEMANTIC_DARK,
    DEFAULT_SEMANTIC_LIGHT,
    DEFAULT_SHAPE,
    DEFAULT_SPACING,
    DEFAULT_STROKE,
    NEUTRAL_STEPS,
    SHAPE_SLOT_NAMES,
    STEP_RULES,
    WASH_COLOR_NAMES,
)

#: The eleven semantic slots and what each one is for. The order is the
#: reading one — the accents first, the planes next.
ROLES: list[tuple[str, str]] = [
    ("primary",    "the brand accent"),
    ("secondary",  "the second accent"),
    ("success",    "what succeeded"),
    ("warning",    "what needs attention"),
    ("error",      "what failed"),
    ("info",       "a neutral piece of information"),
    ("background", "the page"),
    ("surface",    "a panel"),
    ("interface",  "a control's fill"),
    ("text",       "the running text"),
    ("muted",      "the secondary text"),
]

#: (name, role, light default, dark default) — the defaults READ from the
#: framework's palette, never copied: a copy drifts from the shipped
#: colours in silence. A slot that does not swap in dark mode keeps its
#: light value there.
SLOTS: list[tuple[str, str, str, str]] = [
    (name, role, DEFAULT_SEMANTIC_LIGHT[name],
     DEFAULT_SEMANTIC_DARK.get(name, DEFAULT_SEMANTIC_LIGHT[name]))
    for name, role in ROLES
]

#: The colour defaults, DERIVED from :data:`SLOTS` — light mode for the
#: bare field, dark for its ``d_`` twin. One source: two copies of a
#: value drift, and this one would drift in silence.
COLOR_DEFAULTS: dict[str, str] = {
    **{name: light for name, _role, light, _dark in SLOTS},
    **{f"d_{name}": dark for name, _role, _light, dark in SLOTS},
}

#: The font stacks one can pick. System fonts only: Bretzel downloads no
#: font, and a stack that falls back cleanly on every OS is what an app
#: can ship without a ``@font-face``. Single quotes inside, because the
#: exported code wraps the stack in double quotes.
FONTS: list[tuple[str, str]] = [
    ("System", "ui-sans-serif, system-ui, sans-serif, 'Apple Color Emoji', "
               "'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji'"),
    ("Grotesk", "'Helvetica Neue', Helvetica, Arial, sans-serif"),
    ("Geometric", "'Century Gothic', 'Avenir Next', Avenir, Futura, "
                  "system-ui, sans-serif"),
    ("Humanist", "'Trebuchet MS', 'Gill Sans', 'Lucida Grande', "
                 "system-ui, sans-serif"),
    ("Rounded", "ui-rounded, 'SF Pro Rounded', 'Arial Rounded MT Bold', "
                "system-ui, sans-serif"),
    ("Serif", "ui-serif, Georgia, Cambria, 'Times New Roman', serif"),
    ("Book", "'Palatino Linotype', Palatino, 'Book Antiqua', Georgia, serif"),
    ("Mono", "ui-monospace, SFMono-Regular, Menlo, Consolas, "
             "'Liberation Mono', monospace"),
]

def length(token: str, unit: str) -> float:
    """``"0.625rem"`` → ``0.625`` : a shipped token as a slider's number."""
    if not token.endswith(unit):
        raise ValueError(f"{token!r} is not in {unit}: the slider reads {unit}.")
    return float(token.removesuffix(unit))


#: The shipped spacing step, in rem. The identities write their spacing
#: as multiples of it, so they keep their character when it moves.
STEP = length(DEFAULT_SPACING, "rem")

#: The knobs that are not colours, READ from the framework's tokens: a
#: copy here drifted for three days when the shipped scale moved from
#: 3 px to Tailwind's 4 px (2026-10-23), and the showcase kept painting
#: the old theme over every page. The font is Tailwind's stack, which is
#: what an app gets when its theme says nothing.
SLIDER_DEFAULTS: dict[str, float | str] = {
    "box": length(DEFAULT_SHAPE["box"], "rem"),
    "field_": length(DEFAULT_SHAPE["field"], "rem"),
    "selector": length(DEFAULT_SHAPE["selector"], "rem"),
    "stroke": length(DEFAULT_STROKE, "px"),
    "spacing": STEP,
    # The two other spacing families start where the controls' is: an
    # untouched theme follows ``field`` (``Theme(spacing=…)``, 2026-10-26).
    "space_box": STEP,
    "space_gap": STEP,
    "font": FONTS[0][1],
}

#: Every shipped value, in one block. It is what "Reset" puts back, and
#: the SAME source as the class's defaults — so the button cannot bring
#: things back to a third state.
SHIPPED_DEFAULTS: dict[str, str | float] = {**COLOR_DEFAULTS, **SLIDER_DEFAULTS}

#: A fingerprint of the shipped values. The store persists in the
#: visitor's browser, so a setting saved before the shipped theme moved
#: would repaint every page with a theme that no longer exists: when the
#: fingerprint kept beside it differs, :func:`repaint_effect` resets once.
SHIPPED_FINGERPRINT = hashlib.sha1(
    json.dumps(SHIPPED_DEFAULTS, sort_keys=True).encode()
).hexdigest()[:12]


class Studio(ClientState, persist="local"):
    """The theme being shown. ``persist="local"``: one finds one's theme
    again on coming back, without anything going to the server."""

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
    space_box: float = field(default=SLIDER_DEFAULTS["space_box"])
    space_gap: float = field(default=SLIDER_DEFAULTS["space_gap"])
    box: float = field(default=SLIDER_DEFAULTS["box"])
    field_: float = field(default=SLIDER_DEFAULTS["field_"])
    selector: float = field(default=SLIDER_DEFAULTS["selector"])
    stroke: float = field(default=SLIDER_DEFAULTS["stroke"])
    font: str = field(default=SLIDER_DEFAULTS["font"])


#: The JavaScript MIRROR of ``bretzel.theme.palette.resolve_color_pair``.
#:
#: A colour's foreground is not "black or white": it is derived from the
#: background — lightness chosen by a WCAG luminance threshold, then
#: TINTED with the background's hue so the pair stays of a piece. That
#: algorithm runs in Python when the CSS is generated; the studio never
#: talks to the server, so without this mirror a white ``primary`` left
#: white text on white.
#:
#: An accepted, GATED duplication — the same arbitration as
#: ``protocol.py`` ↔ ``runtime.js``. The algebra's numbers are named in
#: ``palette.py`` and ``test_foreground_algebra_is_mirrored`` checks
#: they appear here.
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
  window.bzLum = lum;
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


#: Every GENERATED colour, mirrored from the server: the twelve steps of a
#: colour's bridge (``bridges.step_percentages``), the vivid colours' named
#: steps (``bridges.wash_lines``) and the neutral steps
#: (``neutrals.neutral_percentages``). The studio repaints live, without a
#: server round trip; a colour set here measures its own doses, as the app
#: that receives the exported palette will. The thresholds are not copied:
#: ``STEP_RULES`` and ``NEUTRAL_STEPS`` are injected from the framework, and
#: ``test_the_studio_measures_text_steps_like_the_server`` holds the results
#: equal.
STEPS_JS = """
if (!window.bzSteps) {
  var R = __RULES__, N = __NEUTRALS__;
  var hexRgb = function (hex) {
    var n = parseInt(String(hex).replace('#', ''), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  var mix = function (a, b, pct) {
    var part = pct / 100;
    return a.map(function (x, i) { return Math.round(part * x + (1 - part) * b[i]); });
  };
  var ratio = function (a, b) {
    var la = window.bzLum(a[0], a[1], a[2]), lb = window.bzLum(b[0], b[1], b[2]);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  };
  var lin = function (v) { var c = v / 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  var oklab = function (c) {
    var r = lin(c[0]), g = lin(c[1]), b = lin(c[2]);
    var l = Math.pow(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b, 1 / 3);
    var m = Math.pow(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b, 1 / 3);
    var s = Math.pow(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b, 1 / 3);
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
  };
  var dist = function (a, b) {
    var x = oklab(a), y = oklab(b);
    return 100 * Math.sqrt(Math.pow(x[0] - y[0], 2) + Math.pow(x[1] - y[1], 2) + Math.pow(x[2] - y[2], 2));
  };
  var worst = function (grounds, f) { return Math.min.apply(null, grounds.map(f)); };
  var least = function (start, ceiling, reads) {
    for (var p = start; p <= ceiling; p++) if (reads(p)) return p;
    return ceiling;
  };
  var textPct = function (src, text, grounds, base, target) {
    for (var p = base; p >= R.text_floor; p -= R.text_down) {
      var m = mix(src, text, p);
      if (worst(grounds, function (g) { return ratio(m, g); }) >= target) return p;
    }
    return R.text_floor;
  };
  // A colour's doses in this mode's colours: bridges.step_percentages.
  // Remembered per input: a repaint that moves no colour (a radius, the
  // spacing) measures nothing, and a named step reuses its bridge's.
  var seen_doses = {};
  window.bzDoses = function (srcHex, textHex, pageHex, surfaceHex, interfaceHex) {
    var key = [srcHex, textHex, pageHex, surfaceHex, interfaceHex].join();
    if (!seen_doses[key]) seen_doses[key] = measure(srcHex, textHex, pageHex, surfaceHex, interfaceHex);
    return seen_doses[key];
  };
  var measure = function (srcHex, textHex, pageHex, surfaceHex, interfaceHex) {
    var src = hexRgb(srcHex), text = hexRgb(textHex), surface = hexRgb(surfaceHex);
    var grounds = [hexRgb(pageHex), surface, hexRgb(interfaceHex)];
    var B = R.base, d = {};
    var wash = function (p) { return mix(src, surface, p); };
    var seen = function (t) { return function (p) { return worst(grounds, function (g) { return dist(wash(p), g); }) >= t; }; };
    var after = function (prev) { return function (p) { return dist(wash(p), wash(prev)) >= R.apart; }; };
    var ring = function (t) { return function (p) { return worst(grounds, function (g) { return dist(mix(src, g, p), g); }) >= t; }; };
    d.bg = least(B.pct_bg, R.ceiling, seen(R.from_ground));
    d.bg_hover = least(Math.max(B.pct_bg_hover, d.bg + R.gap), R.ceiling, after(d.bg));
    d.bg_active = least(Math.max(B.pct_bg_active, d.bg_hover + R.gap), R.ceiling, after(d.bg_hover));
    d.border = least(B.pct_border, R.ceiling, seen(R.border));
    d.border_hover = least(Math.max(B.pct_border_hover, d.border + R.gap), R.ceiling, after(d.border));
    d.focus = least(B.pct_focus, R.ceiling, ring(R.ring));
    d.focus_soft = least(B.pct_focus_soft, R.ceiling, ring(R.soft_ring));
    d.solid_hover = B.pct_solid_hover; d.solid_hover_to = 'text';
    var toward = [['text', text], ['surface', surface]], found = false;
    for (var k = 0; k < toward.length && !found; k++) {
      for (var q = B.pct_solid_hover; q >= R.floor; q--) {
        if (dist(mix(src, toward[k][1], q), src) >= R.apart) {
          d.solid_hover = q; d.solid_hover_to = toward[k][0]; found = true; break;
        }
      }
    }
    var onText = grounds.concat([wash(d.bg)]);
    d.text = textPct(src, text, onText, R.text_base.pct_text, R.text_targets.pct_text);
    d.muted = textPct(src, text, onText, Math.max(R.text_base.pct_muted, d.text), R.text_targets.pct_muted);
    return d;
  };
  var decl = function (name, src, pct, to) { return name + ':color-mix(in srgb, ' + src + ' ' + pct + '%, ' + to + ');'; };
  var S = 'var(--color-surface)', T = 'var(--color-text)';
  // The declarations of a colour's bridge.
  window.bzSteps = function (srcHex, textHex, pageHex, surfaceHex, interfaceHex) {
    var d = window.bzDoses(srcHex, textHex, pageHex, surfaceHex, interfaceHex), v = 'var(--bz-src)';
    return decl('--bz-bg', v, d.bg, S) + decl('--bz-bg-hover', v, d.bg_hover, S)
      + decl('--bz-bg-active', v, d.bg_active, S) + decl('--bz-border', v, d.border, S)
      + decl('--bz-border-hover', v, d.border_hover, S) + decl('--bz-focus', v, d.focus, 'transparent')
      + decl('--bz-focus-soft', v, d.focus_soft, 'transparent')
      + decl('--bz-solid-hover', v, d.solid_hover, 'var(--color-' + d.solid_hover_to + ')')
      + decl('--bz-text-muted', v, d.muted, T) + decl('--bz-text', v, d.text, T);
  };
  // A vivid colour's named steps: bridges.wash_lines.
  window.bzWash = function (name, srcHex, textHex, pageHex, surfaceHex, interfaceHex) {
    var d = window.bzDoses(srcHex, textHex, pageHex, surfaceHex, interfaceHex), v = 'var(--color-' + name + ')';
    return decl('--color-' + name + '-wash', v, d.bg, S) + decl('--color-' + name + '-wash-hover', v, d.bg_hover, S)
      + decl('--color-' + name + '-edge', v, d.border, S) + decl('--color-' + name + '-ring', v, d.focus, 'transparent');
  };
  // The neutral steps: neutrals.neutral_percentages.
  window.bzNeutralDoses = function (textHex, mutedHex, pageHex, surfaceHex, interfaceHex) {
    var hexes = { text: hexRgb(textHex), muted: hexRgb(mutedHex) }, surface = hexRgb(surfaceHex);
    var grounds = [hexRgb(pageHex), surface, hexRgb(interfaceHex)], doses = {};
    N.forEach(function (row) {
      var step = row[0], src = hexes[row[1]], start = row[2], rule = row[3], target = row[4], reads;
      if (rule === 'seen') {
        reads = function (p) { return worst(grounds, function (g) { return dist(mix(src, g, p), g); }) >= target; };
      } else if (rule === 'read') {
        reads = function (p) { return worst(grounds, function (g) { return ratio(mix(src, g, p), g); }) >= target; };
      } else {
        var before = doses[rule.slice(6)];
        start = Math.max(start, before + R.gap);
        reads = function (p) { return dist(mix(src, surface, p), mix(src, surface, before)) >= target; };
      }
      doses[step] = least(start, R.neutral_ceiling, reads);
    });
    return doses;
  };
  window.bzNeutrals = function (textHex, mutedHex, pageHex, surfaceHex, interfaceHex) {
    var doses = window.bzNeutralDoses(textHex, mutedHex, pageHex, surfaceHex, interfaceHex);
    return N.map(function (row) {
      return decl('--color-' + row[0], 'var(--color-' + row[1] + ')', doses[row[0]], 'transparent');
    }).join('');
  };
}
""".replace("__RULES__", json.dumps(STEP_RULES)).replace("__NEUTRALS__", json.dumps(NEUTRAL_STEPS))


#: The slots whose bridge carries measured text steps — the planes keep
#: the server's (``bridges._SURFACE_SLOTS``).
STEPPED_SLOTS: tuple[str, ...] = tuple(
    name for name, _role, _light, _dark in SLOTS
    if name not in ("background", "surface", "interface")
)


#: ``(radius family, store field)``. The families come from
#: ``SHAPE_SLOT_NAMES``, the tuple ``Theme(shape=…)`` uses: a family
#: added there appears here. ``field`` is a function of
#: ``bretzel.state``, so its store field is called ``field_``.
SHAPE_FIELDS: tuple[tuple[str, str], ...] = tuple(
    (family, "field_" if family == "field" else family)
    for family in SHAPE_SLOT_NAMES
)


def path(name: str) -> str:
    """A store field's JS path — class, instance key, field."""
    return f"$bz.state.Studio.default.{name}"


def assign_expression(values: dict[str, str | float]) -> str:
    """The JS that writes ``values`` into the store, in one gesture.

    The persistence follows the store: no request, no reload.
    """
    return "; ".join(
        f"{path(name)} = {json.dumps(value)}"
        for name, value in sorted(values.items())
    )


def reset_expression() -> str:
    """The JS that puts EVERY knob back to the value the framework ships.

    ``persist="local"`` makes a setting survive everything, including a
    change of the shipped theme; without this button nothing brings the
    framework's values back. Built from :data:`SHIPPED_DEFAULTS`, the
    table the store's fields read, so the two cannot diverge —
    ``test_the_studio_exports_every_knob`` holds both ends.
    """
    return assign_expression(SHIPPED_DEFAULTS)


def repaint_effect() -> str:
    """The effect that repaints the page, through an INJECTED sheet.

    It writes a single ``<style>`` carrying ``:root { … }`` and
    ``.dark { … }``, appended at the end of ``<head>`` — AFTER the
    theme's, so at equal specificity ours wins.
    """
    def block(prefix: str) -> str:
        # Every source writes its PAIR, the background AND its
        # foreground: the foreground computed at startup would otherwise
        # stay, and a light colour would carry white text.
        return " + ".join(
            f"'--color-{name}:' + {path(prefix + name)} + ';'"
            f" + '--color-{name}-foreground:'"
            f" + window.bzFg({path(prefix + name)}) + ';'"
            for name, _role, _light, _dark in SLOTS
        )

    radius = " + ".join(
        f"'--radius-{family}:' + {path(attr)} + 'rem;'"
        for family, attr in SHAPE_FIELDS
    )
    # The stroke: a single base, the two steps derive from it in the
    # theme's own `calc()`.
    stroke = f"'--bz-stroke:' + {path('stroke')} + 'px;'"
    font = f"'--font-sans:' + {path('font')} + ';'"
    # Kept beside the store, not in it: every store field is a knob the
    # export carries. Wrapped, because a private window may refuse storage.
    upgrade = (
        "try { if (localStorage.getItem('bz-studio-shipped') !== "
        f"{json.dumps(SHIPPED_FINGERPRINT)}) {{ {reset_expression()};"
        " localStorage.setItem('bz-studio-shipped', "
        f"{json.dumps(SHIPPED_FINGERPRINT)}); }} }} catch (e) {{}}"
    )
    def grounds(prefix: str) -> str:
        # The text and the three grounds a dose is measured against.
        return ", ".join(path(prefix + k) for k in ("text", "background", "surface", "interface"))

    def generated(prefix: str) -> str:
        # The neutral steps and the vivid colours' named steps, in this
        # mode's own colours (``tokens.GENERATED_COLOR_NAMES``).
        rest = ", ".join(path(prefix + k) for k in ("background", "surface", "interface"))
        washes = " + ".join(
            f"window.bzWash('{name}', {path(prefix + name)}, {grounds(prefix)})"
            for name in WASH_COLOR_NAMES)
        return (f"window.bzNeutrals({path(prefix + 'text')}, {path(prefix + 'muted')}, {rest})"
                f" + {washes}")

    def steps(prefix: str, scope: str) -> str:
        # One rule per stepped colour, in this mode's own colours.
        return " + ".join(
            f"'{scope}.bz-c-{name}{{' + window.bzSteps({path(prefix + name)}, "
            f"{grounds(prefix)}) + '}}'"
            for name in STEPPED_SLOTS
        )

    return (
        FOREGROUND_JS
        + STEPS_JS
        + upgrade
        + "let s = document.getElementById('bz-studio');"
        " if (!s) { s = document.createElement('style');"
        " s.id = 'bz-studio'; document.head.appendChild(s); }"
        " s.textContent = ':root{' + "
        + block("")
        + " + " + generated("")
        + f" + '--spacing:' + {path('spacing')} + 'rem;'"
        + f" + '--bz-space-box:' + {path('space_box')} + 'rem;'"
        + f" + '--bz-space-gap:' + {path('space_gap')} + 'rem;' + "
        + radius
        + " + " + stroke
        + " + " + font
        + " + '}.dark{' + "
        + block("d_")
        + " + " + generated("d_")
        + " + '}' + "
        + steps("", "")
        + " + "
        + steps("d_", ".dark ")
        + ";"
    )


def rounded(name: str) -> str:
    """The field, rounded to the thousandth.

    A slider with a 0.05 step returns ``0.7500000000000001`` one time in
    twenty: invisible in a sheet, visible in the exported code. Not
    ``round(binding, 3)``: these emitters run at import, with no render
    context, where ``Studio().box`` is a ``float`` and not a binding.
    """
    return f"(Math.round({path(name)} * 1000) / 1000)"


def export_expression() -> str:
    """The code to paste, in a single expression for ``bz-text``.

    It carries EVERYTHING the page sets — an exporter that drops a knob
    produces plausible, incomplete code, the worst failure mode.
    ``test_the_studio_exports_every_knob`` guards it.
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
        + " + 'px\",\\n    spacing={\"field\": \"' + "
        + rounded("spacing")
        + " + 'rem\", \"box\": \"' + "
        + rounded("space_box")
        + " + 'rem\", \"gap\": \"' + "
        + rounded("space_gap")
        + " + 'rem\"},\\n    fonts={\"sans\": \"' + "
        + path("font")
        + " + '\"},\\n)'"
    )
