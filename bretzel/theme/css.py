"""Full ``theme.css`` generator.

What :func:`generate_theme_css_full` produces is the file Lightning CSS
ingests as its entry point — it carries the ``@import "tailwindcss"``,
the ``@theme`` block (color tokens), dark-mode overrides, scrollbar
styles, the body-autofill fix carried over from v1, and a tiny
transition rule for smooth theme swaps.

Pure functions ; the result is cached on the :class:`Theme` instance
at startup and served from memory thereafter.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from bretzel.theme.bridges import generate_color_bridges
from bretzel.theme.config import ScrollbarConfig
from bretzel.theme.palette import Palette
from bretzel.theme.sources import (
    all_source_roots,
    generate_source_directives,
)
from bretzel.theme.tailwind import (
    generate_safelist_comment,
    generate_theme_css,
)

# A scrollbar color reference accepts ``"<color-name>"`` or
# ``"<color-name>/<opacity-pct>"``. Tailwind v4 stores each
# ``--color-X`` as a full ``rgb(...)`` expression, so we cannot wrap
# ``var(--color-X)`` in another ``rgb()`` — that nests two ``rgb()``
# calls and the browser falls back to ``auto``. Instead we hand back
# the bare var for solid colors and a ``color-mix()`` form for
# opacity-modulated ones.
_REF_RE = re.compile(r"^([a-z][a-z0-9_-]*)(?:/(\d{1,3}))?$")


def _resolve_color_expression(value: str, palette: Palette) -> str:
    """Translate a scrollbar color spec into a usable CSS color value.

    Accepts :

    - ``"muted/30"`` → ``"color-mix(in srgb, var(--color-muted) 30%, transparent)"``.
    - ``"primary"`` → ``"var(--color-primary)"``.
    - ``"#abcdef"`` → ``"#abcdef"`` (passes straight through).
    - ``"transparent"`` / ``"currentColor"`` → preserved literally.
    - Anything else → preserved literally (CSS expressions, etc.).
    """
    if value.startswith("#") or value in {"transparent", "currentColor", "inherit"}:
        return value
    match = _REF_RE.match(value)
    if not match:
        return value
    color, opacity_str = match.group(1), match.group(2)
    css_class = palette.bg_class(color)  # raises ThemeError on unknown
    if opacity_str is None:
        return f"var(--color-{css_class})"
    pct = max(0, min(100, int(opacity_str)))
    return f"color-mix(in srgb, var(--color-{css_class}) {pct}%, transparent)"


# ───────────────────────────────────────────────────────────────────────────
# Scrollbar
# ───────────────────────────────────────────────────────────────────────────


def generate_scrollbar_css(scrollbar: ScrollbarConfig, palette: Palette) -> str:
    """Build the scrollbar rules for both WebKit and Firefox."""
    width = scrollbar.width
    track = _resolve_color_expression(scrollbar.track, palette)
    thumb = _resolve_color_expression(scrollbar.thumb, palette)
    thumb_hover = _resolve_color_expression(scrollbar.thumb_hover, palette)

    # The ``border + background-clip: content-box`` trick (V1 idiom) shrinks
    # the visible thumb inwards from the scrollbar's box edges. With a 4px
    # default width and a 1px transparent border on each side, the visible
    # thumb is 2px — discreet without disappearing entirely (a 2px border
    # would eat the entire width).
    # ``-button`` + ``-corner`` are explicitly neutralised so the OS chrome
    # doesn't sneak arrow caps or a frame square back in.
    return (
        "/* scrollbar */\n"
        "* {\n"
        f"  scrollbar-width: thin;\n"
        f"  scrollbar-color: {thumb} {track};\n"
        "}\n"
        "::-webkit-scrollbar {\n"
        f"  width: {width};\n"
        f"  height: {width};\n"
        "}\n"
        "::-webkit-scrollbar-track {\n"
        f"  background: {track};\n"
        "}\n"
        "::-webkit-scrollbar-thumb {\n"
        f"  background-color: {thumb};\n"
        "  border-radius: 9999px;\n"
        "  border: 1px solid transparent;\n"
        "  background-clip: content-box;\n"
        "}\n"
        "::-webkit-scrollbar-thumb:hover {\n"
        f"  background-color: {thumb_hover};\n"
        "}\n"
        "::-webkit-scrollbar-button {\n"
        "  display: none;\n"
        "}\n"
        "::-webkit-scrollbar-corner {\n"
        "  background: transparent;\n"
        "}\n"
    )


# ───────────────────────────────────────────────────────────────────────────
# Static fragments
# ───────────────────────────────────────────────────────────────────────────


# Carry-over from v1 : Chromium and Safari swap autofilled inputs to
# their own yellowish background AND their own whitish border, both
# ignoring Tailwind classes. Our fix **restores the input default**
# without changing the design :
#
# - **Fill** : paint a SUBTLE inverse tint of ``--color-interface``
#   (8% ``--color-text`` mixed in) via the ``-webkit-box-shadow inset``
#   trick. The autofilled field reads as gently elevated against a
#   typed one — light in dark mode, slightly darker in light mode —
#   so the user can tell at a glance which fields the browser filled
#   without breaking the calm aesthetic. ``--color-text`` is the
#   auto-derived foreground so the tint inverts the mode correctly.
# - **Border** : force ``color-mix(... var(--color-text) 10%, transparent)``
#   (= Tailwind ``border-text/10``, the input theme default), because
#   Chrome's UA stylesheet on ``:-webkit-autofill`` paints a lighter
#   border by default that doesn't match a typed input.
# - **Text** : ``-webkit-text-fill-color: var(--color-text)`` so the
#   value reads in the palette colour instead of Chrome's default black.
#
# Focus chrome (``focus:border-{bg_color}`` + ``focus:ring-*``) is NOT
# touched here — Tailwind's classes survive on the autofilled state
# fine (the colored ring + offset stay visible on focus regardless).
# Anything beyond fill / border / text is the component's responsibility.
#
# Tailwind v4 stores ``--color-X`` as a full ``rgb(...)`` expression,
# so we use ``var(...)`` directly — wrapping with another ``rgb()``
# nests two ``rgb()`` calls and the declaration is dropped.
_AUTOFILL_FIX = """\
/* autofill — restore the input defaults Chrome overrides */
input:-webkit-autofill,
input:-webkit-autofill:hover,
input:-webkit-autofill:focus,
input:-webkit-autofill:active,
textarea:-webkit-autofill,
textarea:-webkit-autofill:hover,
textarea:-webkit-autofill:focus,
textarea:-webkit-autofill:active {
  -webkit-text-fill-color: var(--color-text) !important;
  border-color: color-mix(in oklab, var(--color-text) 10%, transparent) !important;
  -webkit-box-shadow: 0 0 0 1000px color-mix(in oklab, var(--color-interface), var(--color-text) 8%) inset !important;
  caret-color: var(--color-text);
}
"""


# Tailwind v3's preflight carried ``button,[role=button]{cursor:pointer}``.
# v4 dropped it — the generated ``@layer base`` contains no ``cursor``
# declaration at all — and Bretzel has only ever run on v4, so every button
# in the catalogue showed the arrow while ``ui.link`` (which declares the
# class itself) showed the hand.
#
# This belongs HERE, not in each component theme. Nine slots that render a
# real ``<button>`` were missing the class — Alert / Notification dismiss,
# Calendar nav + day cell, both date pickers' clear + trigger, FileUpload
# remove — and FIVE of them already declared the ``disabled:`` half. Five
# authors reasoned about the cursor axis, wrote one side, and left the other
# undone : the default is invisible at the call site, so per-component is a
# treadmill, not a fix.
#
# ``@layer base`` is load-bearing. Unlayered, this rule would beat every
# ``cursor-*`` UTILITY (Tailwind v4 ranks unlayered CSS above @layer) and
# override Slider's ``cursor-grab``, Combobox's ``cursor-text``, Card's
# ``aria-disabled:cursor-default``. Inside ``base`` the utilities win, which
# is exactly how v3's preflight behaved.
#
# ``:not(:disabled)`` + ``:not([aria-disabled="true"])`` : a disabled control
# must keep ``cursor-not-allowed`` (cf. the disabled-affordance gate), and
# role-based controls disable via ``aria-disabled``, not the native attr.
_BUTTON_CURSOR = """\
/* button cursor — restore the pointer v3's preflight gave for free */
@layer base {
  button:not(:disabled):not([aria-disabled="true"]),
  [role="button"]:not([aria-disabled="true"]) {
    cursor: pointer;
  }
}
"""


# Tiny smoothing rule so toggling the ``.dark`` class doesn't snap.
# 150ms feels alive without leaving ghost frames during fast clicks.
_THEME_TRANSITIONS = """\
/* theme transitions — smooth toggle of the .dark class */
:root, .dark {
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-color 150ms ease;
}
"""


# Signal to the browser which scheme its **native widgets** should
# render in : autofill / password-manager preview borders, native
# scrollbars, OS-painted selection, the autofill yellow flash. Without
# this declaration Chrome paints all native UI in light mode regardless
# of the page background — so an autofilled or password-previewed
# field in dark mode gets a whitish border that no author CSS can
# override (the state is ``:-internal-autofill-previewed``, which is
# UA-only). Bretzel toggles dark mode by adding ``.dark`` on
# ``<html>`` ; mirror that exactly here so the browser tracks the
# same boundary.
_COLOR_SCHEME = """\
/* color-scheme — propagate light/dark intent to browser-native UI */
:root {
  color-scheme: light;
}
.dark {
  color-scheme: dark;
}
"""


# Without an explicit rule, browsers fall back to the OS highlight
# (Windows blue), which clashes with any non-blue preset and is
# unreadable in dark mode. Tinting with ``--color-text`` (the
# auto-derived foreground) guarantees contrast against any background
# the preset paints — same approach as macOS / Firefox defaults. We
# avoid ``--color-primary`` because it goes muddy on green/orange
# presets and selection should read as "selected", not "themed".
#
# The autofill block below re-asserts the rule with stronger opacity
# inside ``:-webkit-autofill`` inputs : the autofill fix paints an
# opaque ``-webkit-box-shadow`` inset, which sits ABOVE a normal
# ``::selection`` background and hides it. ``-webkit-text-fill-color``
# also wins over ``color: inherit`` on Chromium, so we don't override
# the foreground in that branch — selected text stays the autofill
# text color, only the background tint changes.
_SELECTION = """\
/* text selection — neutral tint that tracks --color-text */
::selection {
  background-color: color-mix(in oklab, var(--color-text) 20%, transparent);
  color: inherit;
}
input:-webkit-autofill::selection,
textarea:-webkit-autofill::selection {
  background-color: color-mix(in oklab, var(--color-text) 35%, transparent);
}
"""


# Collapsed desktop rail: an icon-only 64px strip wants NO visible scrollbar
# (the 4px gutter offsets the centred icons and reads as noise at that width —
# cf. VS Code's activity bar). We simply HIDE the scrollbar there so the icon
# column stays perfectly centred (no reserved gutter); scroll still works via
# wheel / trackpad. No overflow fade — a clean, empty rail matches the
# framework's minimal aesthetic. Scoped to ``[data-open=false]`` + ``md:`` so
# the expanded sidebar and the mobile drawer keep the normal thin scrollbar.
# Hook class: ``bz-rail-scroll`` on the sidebar's scroll region (see sidebar
# theme ``scroll`` slot). ``scrollbar-width:none`` covers Firefox + Chromium
# 121+; ``::-webkit-scrollbar{display:none}`` is the Safari (< 18.2) fallback.
#
# ⚠️ The attribute is ``data-collapse``, not ``data-variant``. This selector
# targeted the second one for the whole time the Sidebar emitted the first
# (``sidebar.py``: "``data-collapse`` replaces ``data-variant``"): the rule
# matched NOTHING any more, and the collapsed rail rendered its scrollbar —
# measured in the browser, ``scrollbar-width: thin`` instead of ``none``.
# Nothing raises when a CSS selector stops matching: it is the
# ``test_css_selectors_match_the_catalogue`` gate that says so now.
_RAIL_SCROLL = """\
/* collapsed rail : hidden scrollbar (centred icon column, no reserved gutter) */
@media (min-width: 768px) {
  aside[data-collapse="rail"][data-open="false"] .bz-rail-scroll {
    scrollbar-width: none;
  }
  aside[data-collapse="rail"][data-open="false"] .bz-rail-scroll::-webkit-scrollbar {
    width: 0;
    display: none;
  }
}
"""

# The GENERIC counterpart of ``_RAIL_SCROLL``: "this element scrolls, but
# does not show its bar". The sidebar's rail keeps a rule of its own
# because its one is CONDITIONAL (collapsed only, ``md:`` only), which a
# static class cannot express; this one is unconditional and serves any
# element that provides its own navigation.
#
# ⚠️ Why a real CSS class and not an arbitrary Tailwind utility
# (``[scrollbar-width:none] [&::-webkit-scrollbar]:hidden``) — and the
# reason was CORRECTED on 2026-08-29, because the old one was wrong.
#
# What stays true, measured: in **DEV**, neither rule exists in the
# page's sheets. The ``* { scrollbar-width: thin }`` above wins, and the
# bar stays visible on platforms that draw a classic one (Windows,
# Linux) — invisible in headless Chromium, which uses overlay bars. The
# arbitrary variant's ``&`` is furthermore escaped as ``&amp;`` in the
# HTML attribute.
#
# What was FALSE: "the JIT does not compile them", stated as a property
# of Tailwind. Re-measured on 2026-08-29 by passing both forms to the
# production binary (``.bretzel/bin/tailwindcss-*``): it emits BOTH,
# ``.[scrollbar-width\:none] { scrollbar-width: none }`` and the
# ``&::-webkit-scrollbar`` variant. It is the dev mode's BROWSER compiler
# that does not handle them, not Tailwind — same family as the
# ``project_tailwind_browser_breaks_transitions`` memory.
#
# The class stays, and for a reason that still holds: it works on BOTH
# sides, where the arbitrary form only exists in production. A class that
# applies only half the time depending on the mode is worse than a named
# hook. The comment on Sidebar's ``scroll`` slot already said it: "CSS
# hook (not a Tailwind utility)".
_NO_SCROLLBAR = """\
/* scrolls without showing its bar (the component provides its navigation) */
.bz-no-scrollbar {
  scrollbar-width: none;
}
.bz-no-scrollbar::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}
"""


# ───────────────────────────────────────────────────────────────────────────
# Drag preview — the node that follows the pointer
# ───────────────────────────────────────────────────────────────────────────
#
# A CSS hook, not a theme slot, and the reason is structural: this node
# is **created by the runtime** (``19_dnd.js`` clones the grabbed item),
# so no Python render ever goes through it. Composing a Tailwind class
# for it from JS would fall back into the measured trap of the
# ``project_assembled_tailwind_class_dev_only`` memory — a class
# assembled outside the scanner exists only in dev and disappears in
# production.
#
# The positioning (``left`` / ``top`` / ``width``) stays inline: it is
# recomputed on every ``pointermove`` and has no business in a sheet.
# What lives here is what does NOT move — taking it out of flow, the
# "lifted" shadow, and above all ``pointer-events: none``: without it
# ``elementFromPoint`` would see only the preview, glued under the
# cursor, and the card would never land anywhere.
_DRAG_PREVIEW = """\
/* the clone that follows the pointer during a drag (created by the runtime) */
.bz-drag-preview {
  position: fixed;
  z-index: 9999;
  pointer-events: none;
  margin: 0;
  box-shadow: 0 12px 28px -8px rgb(0 0 0 / 0.35);
  transform: scale(1.02);
  transform-origin: center;
  opacity: 0.95;
}
@media (prefers-reduced-motion: reduce) {
  .bz-drag-preview { transform: none; }
}
"""


# ───────────────────────────────────────────────────────────────────────────
# Composer
# ───────────────────────────────────────────────────────────────────────────


_SOURCE_INLINE_RE = re.compile(r'^@source inline\(".*?"\);\s*$\n?', re.M | re.S)
#: The other form: a disk root to scan. A deliberately distinct pattern
#: from the previous one — ``inline(…)`` is not a path, and confusing the
#: two would amount to removing the safelist while believing one is
#: removing a root (or the other way round).
_SOURCE_PATH_RE = re.compile(r'^@source "[^"]*";\s*$\n?', re.M)


def strip_safelist(theme_css: str) -> str:
    """Strip the **scan instructions** from the theme CSS — the
    ``@source inline(...)`` safelist and the ``@source "<dir>"`` roots.

    Both exist only for the PRODUCTION compiler, which reads source
    files. The dev mode's browser compiler reads the live DOM, where the
    classes are already resolved: the safelist changes nothing in what it
    produces and weighs down every page (69 KB measured), and a **disk**
    root literally makes no sense in a browser — ignored at best, a
    compilation error in the page at worst.

    The name stayed singular because the caller is unique and its need
    has not changed: ``_theme_css_inline`` wants the theme WITHOUT what
    only addresses the disk compiler.
    """
    return strip_scan_roots(_SOURCE_INLINE_RE.sub("", theme_css, count=1))


def strip_scan_roots(theme_css: str) -> str:
    """Strip the ``@source "<dir>"`` roots — and NOTHING else.

    Two callers, two reasons not to let an absolute path out:

    - the CSS inlined in dev, where a disk path makes no sense to the
      browser compiler (cf. :func:`strip_safelist`, which composes this
      one);
    - the ``/_bretzel/theme.css`` route, served "for inspection" and
      therefore **public**: it would otherwise publish the server's
      installation path in a response anyone can request.

    What the production compiler ingests keeps its roots — that is the
    whole point of
    :func:`~bretzel.theme.tailwind.generate_source_directives`.
    """
    return _SOURCE_PATH_RE.sub("", theme_css)


def generate_theme_css_full(
    palette: Palette,
    *,
    scrollbar: ScrollbarConfig | None = None,
    responsive_classes: Sequence[str] = (),
    fonts: Mapping[str, str] | None = None,
    spacing: str | None = None,
    text: Mapping[str, str] | None = None,
    shape: Mapping[str, str] | None = None,
    stroke: str | None = None,
    extra_css: str = "",
) -> str:
    """Assemble the full ``theme.css`` Lightning CSS will ingest.

    ``responsive_classes``: the tokens of the graded tables (cf.
    :func:`bretzel.components.dynamic_responsive_classes`), to be closed
    over the breakpoints. Same bridge, same reason.

    **The scan roots are not a parameter.** They come from
    :func:`bretzel.theme.sources.all_source_roots`: the framework
    package, plus what installed packages declare through the
    ``bretzel.scan_roots`` entry point. One more door here — a kwarg, a
    config option — would make two ways of doing the same thing, and the
    wrong one at that: it is the package THAT CARRIES the classes that
    knows where they are, not the app assembling it.

    The ``cwd`` is never declared: Tailwind scans it by itself, and that
    is exactly what masked the bug for the whole time the ``cwd``
    contained the package.

    Sections, in order:

    0. The scan roots (``@source "<dir>";``) — which folders the
       compiler reads to find classes in.
    1. Lightning CSS safelist comment (``@source inline {...}``) —
       keeps every framework class alive even when no source file
       references it literally.
    2. The ``@import + @theme + .dark`` block from
       :func:`generate_theme_css`.
    3. The **colour bridges** (``.bz-c-<name>``) — cf.
       :mod:`bretzel.theme.bridges`. After the ``@theme``/``.dark`` block
       because they READ its variables, before ``extra_css`` because the
       app must be able to redefine a step.
    4. Body-autofill fix.
    5. Button cursor (the pointer v4's preflight no longer gives).
    6. Theme transitions.
    7. ``color-scheme`` (light / dark) so browser-native UI tracks
       the active theme.
    8. Selection highlight (``::selection`` bound to ``--color-primary``).
    9. Collapsed-rail scrollbar hide (keeps the icon column centred).
    10. Scrollbar rules (omitted if ``scrollbar=None``).
    11. ``extra_css`` — the application's CSS way out.

    ``extra_css`` is **the last section, and that is the subject**. All
    those above belong to the framework; this one belongs to the app, so
    it must win the cascade at equal specificity — an escape hatch that
    loses against what it is meant to correct escapes nothing. That is
    exactly the illness measured on ``classes=`` on 2026-08-16
    (``bg-black`` losing against a theme's ``bg-surface`` because
    Tailwind orders its utilities itself): here the order is ours, so it
    is decided instead of suffered.

    It goes through the **same** pipeline as the rest — so it is
    compiled, minified, and above all **covered by the sha256
    fingerprint** of ``build.get_or_build_css``: changing a rule
    invalidates the cached ``style.css`` the way changing a colour does.
    CSS injected elsewhere (a ``<style>`` set in the ``<head>``) would
    have had none of those three properties.

    What it makes possible and that no component theming replaces:
    ``@font-face`` (hence self-hosting a font from ``static_dir``),
    ``@keyframes``, ``@supports``, custom properties, and survival CSS
    over third-party markup.
    """
    parts: list[str] = [
        generate_source_directives(all_source_roots()),
        generate_safelist_comment(palette, responsive_classes),
        "",
        generate_theme_css(
            palette,
            fonts=fonts,
            spacing=spacing,
            text=text,
            shape=shape,
            stroke=stroke,
        ).rstrip(),
        "",
        generate_color_bridges(palette),
        _AUTOFILL_FIX,
        _BUTTON_CURSOR,
        _THEME_TRANSITIONS,
        _COLOR_SCHEME,
        _SELECTION,
        _RAIL_SCROLL,
        _NO_SCROLLBAR,
        _DRAG_PREVIEW,
    ]
    if scrollbar is not None:
        # AFTER the two hiding rules: the global block sets a
        # ``* { scrollbar-width: thin }``, but a universal selector has
        # zero specificity, so a class beats it whatever the order. The
        # order stays written this way so that reading the file follows
        # the cascade.
        parts.append(generate_scrollbar_css(scrollbar, palette))
    if extra := extra_css.strip():
        parts.append("/* --- Theme(css=…) — l'app a le dernier mot --- */")
        parts.append(extra)
    return "\n".join(parts) + "\n"
