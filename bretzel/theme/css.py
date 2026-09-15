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


# Collapsed desktop rail : an icon-only 64px strip wants NO visible scrollbar
# (the 4px gutter offsets the centred icons and reads as noise at that width —
# cf. VS Code's activity bar). We simply HIDE the scrollbar there so the icon
# column stays perfectly centred (no reserved gutter) ; scroll still works via
# wheel / trackpad. No overflow fade — a clean, empty rail matches the
# framework's minimal aesthetic. Scoped to ``[data-open=false]`` + ``md:`` so
# the expanded sidebar and the mobile drawer keep the normal thin scrollbar.
# Hook class : ``bz-rail-scroll`` on the sidebar's scroll region (see sidebar
# theme ``scroll`` slot). ``scrollbar-width:none`` covers Firefox + Chromium
# 121+ ; ``::-webkit-scrollbar{display:none}`` is the Safari (< 18.2) fallback.
#
# ⚠️ L'attribut est ``data-collapse``, pas ``data-variant``. Ce sélecteur a
# visé le second pendant tout le temps où la Sidebar a émis le premier
# (``sidebar.py`` : « ``data-collapse`` remplace ``data-variant`` ») : la
# règle ne matchait plus RIEN, et le rail replié rendait sa barre de
# défilement — mesuré au navigateur, ``scrollbar-width: thin`` au lieu de
# ``none``. Rien ne lève quand un sélecteur CSS cesse de matcher : c'est
# la gate ``test_css_selectors_match_the_catalogue`` qui le dit maintenant.
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

# Le pendant GÉNÉRIQUE de ``_RAIL_SCROLL`` : « cet élément défile, mais ne
# montre pas sa barre ». Le rail du sidebar garde sa règle à lui parce que
# la sienne est CONDITIONNELLE (seulement replié, seulement en ``md:``), ce
# qu'une classe statique ne peut pas exprimer ; celle-ci est
# inconditionnelle et sert à tout élément qui fournit sa propre navigation.
#
# ⚠️ Pourquoi une vraie classe CSS et pas un utilitaire Tailwind arbitraire
# (``[scrollbar-width:none] [&::-webkit-scrollbar]:hidden``) — et la raison
# a été CORRIGÉE le 2026-08-29, parce que l'ancienne était fausse.
#
# Ce qui reste vrai, mesuré : en **DEV**, aucune des deux règles n'existe
# dans les feuilles de la page. Le ``* { scrollbar-width: thin }`` ci-dessus
# gagne, et la barre reste visible sur les plateformes qui en dessinent une
# classique (Windows, Linux) — invisible en Chromium headless, qui utilise
# des barres en surimpression. Le ``&`` de la variante arbitraire est de
# surcroît échappé en ``&amp;`` dans l'attribut HTML.
#
# Ce qui était FAUX : « le JIT ne les compile pas », énoncé comme une
# propriété de Tailwind. Re-mesuré le 2026-08-29 en passant les deux formes
# au binaire de prod (``.bretzel/bin/tailwindcss-*``) : il émet les DEUX,
# ``.[scrollbar-width\:none] { scrollbar-width: none }`` et la variante
# ``&::-webkit-scrollbar``. C'est le compilateur NAVIGATEUR du mode dev qui
# ne les gère pas, pas Tailwind — même famille que la memory
# ``project_tailwind_browser_breaks_transitions``.
#
# La classe reste, et pour une raison qui tient toujours : elle marche des
# DEUX côtés, là où la forme arbitraire n'existe qu'en prod. Une classe qui
# ne s'applique qu'à moitié selon le mode est pire qu'un hook nommé. Le
# commentaire du slot ``scroll`` de Sidebar le disait déjà : « CSS hook
# (not a Tailwind utility) ».
_NO_SCROLLBAR = """\
/* défile sans montrer sa barre (le composant fournit sa navigation) */
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
# Aperçu de drag — le nœud qui suit le pointeur
# ───────────────────────────────────────────────────────────────────────────
#
# Un CSS hook, pas un slot de thème, et la raison est structurelle : ce
# nœud est **créé par le runtime** (``19_dnd.js`` clone l'item attrapé),
# donc aucun rendu Python ne passe jamais par là. Lui composer une classe
# Tailwind depuis le JS retomberait dans le piège mesuré de la memory
# ``project_assembled_tailwind_class_dev_only`` — une classe assemblée
# hors du scanner n'existe qu'en dev et disparaît en prod.
#
# Le positionnement (``left`` / ``top`` / ``width``) reste en style inline :
# il est recalculé à chaque ``pointermove`` et n'a rien à faire dans une
# feuille. Ce qui vit ici est ce qui NE bouge pas — la mise hors-flux,
# l'ombre de « soulevé », et surtout ``pointer-events: none`` : sans lui
# ``elementFromPoint`` ne verrait que l'aperçu, collé sous le curseur, et
# la carte n'atterrirait jamais nulle part.
_DRAG_PREVIEW = """\
/* le clone qui suit le pointeur pendant un drag (créé par le runtime) */
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
#: L'autre forme : une racine de disque à balayer. Motif volontairement
#: distinct du précédent — ``inline(…)`` n'est pas un chemin, et les
#: confondre reviendrait à retirer la safelist en croyant retirer une
#: racine (ou l'inverse).
_SOURCE_PATH_RE = re.compile(r'^@source "[^"]*";\s*$\n?', re.M)


def strip_safelist(theme_css: str) -> str:
    """Retire du CSS de thème **les instructions de balayage** — la
    safelist ``@source inline(...)`` et les racines ``@source "<dir>"``.

    Les deux n'existent que pour le compilateur de PROD, qui lit des
    fichiers source. Le compilateur navigateur du mode dev lit le DOM
    vivant, où les classes sont déjà résolues : la safelist ne change
    rien à ce qu'il produit et alourdit chaque page (69 Ko mesurés), et
    une racine de **disque** n'a littéralement aucun sens dans un
    navigateur — au mieux ignorée, au pire une erreur de compilation
    dans la page.

    Le nom est resté au singulier parce que l'appelant est unique et que
    son besoin, lui, n'a pas changé : ``_theme_css_inline`` veut le
    thème SANS ce qui ne s'adresse qu'au compilateur de disque.
    """
    return strip_scan_roots(_SOURCE_INLINE_RE.sub("", theme_css, count=1))


def strip_scan_roots(theme_css: str) -> str:
    """Retire les racines ``@source "<dir>"`` — et RIEN d'autre.

    Deux appelants, deux raisons de ne pas laisser un chemin absolu
    sortir :

    - le CSS inliné en dev, où un chemin de disque n'a aucun sens pour le
      compilateur navigateur (cf. :func:`strip_safelist`, qui compose
      celle-ci) ;
    - la route ``/_bretzel/theme.css``, servie « pour l'inspection » et
      donc **publique** : elle publierait sinon le chemin d'installation
      du serveur dans une réponse que n'importe qui peut demander.

    Ce que le compilateur de prod, lui, ingère, garde ses racines — c'est
    tout l'objet de :func:`~bretzel.theme.tailwind.generate_source_directives`.
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

    ``responsive_classes`` : les tokens des tables graduées (cf.
    :func:`bretzel.components.dynamic_responsive_classes`), à clôturer
    sur les breakpoints. Même bridge, même raison.

    **Les racines de balayage ne sont pas un paramètre.** Elles viennent
    de :func:`bretzel.theme.sources.all_source_roots` : le paquet du
    framework, plus ce que les paquets installés déclarent via le point
    d'entrée ``bretzel.scan_roots``. Une porte de plus ici — un kwarg,
    une option de config — ferait deux manières de faire la même chose,
    et surtout la mauvaise : c'est le paquet QUI PORTE les classes qui
    sait où elles sont, pas l'app qui l'assemble.

    Le ``cwd``, lui, n'est jamais déclaré : Tailwind le balaie de
    lui-même, et c'est exactement ce qui a masqué le bug tout le temps
    où le ``cwd`` contenait le paquet.

    Sections, in order :

    0. Les racines de balayage (``@source "<dir>";``) — quels dossiers
       le compilateur lit pour y trouver des classes.
    1. Lightning CSS safelist comment (``@source inline {...}``) —
       keeps every framework class alive even when no source file
       references it literally.
    2. The ``@import + @theme + .dark`` block from
       :func:`generate_theme_css`.
    3. Les **ponts de couleur** (``.bz-c-<nom>``) — cf.
       :mod:`bretzel.theme.bridges`. Après le bloc ``@theme``/``.dark``
       parce qu'ils en LISENT les variables, avant ``extra_css`` parce
       que l'app doit pouvoir redéfinir un palier.
    4. Body-autofill fix.
    5. Button cursor (the pointer v4's preflight no longer gives).
    6. Theme transitions.
    7. ``color-scheme`` (light / dark) so browser-native UI tracks
       the active theme.
    8. Selection highlight (``::selection`` bound to ``--color-primary``).
    9. Collapsed-rail scrollbar hide (keeps the icon column centred).
    10. Scrollbar rules (omitted if ``scrollbar=None``).
    11. ``extra_css`` — la porte de sortie CSS de l'application.

    ``extra_css`` est **la dernière section, et c'est le sujet**. Toutes
    celles d'au-dessus appartiennent au framework ; celle-ci appartient à
    l'app, donc elle doit gagner la cascade à spécificité égale — une
    échappatoire qui perd contre ce qu'elle vient corriger n'échappe à
    rien. C'est exactement la maladie mesurée sur ``classes=`` le
    2026-08-16 (``bg-black`` perdant contre le ``bg-surface`` d'un thème
    parce que Tailwind ordonne ses utilitaires lui-même) : ici l'ordre est
    le nôtre, donc il est décidé au lieu d'être subi.

    Elle traverse le **même** pipeline que le reste — donc elle est
    compilée, minifiée, et surtout **couverte par l'empreinte sha256**
    de ``build.get_or_build_css`` : changer une règle invalide le
    ``style.css`` en cache comme changer une couleur. Un CSS injecté
    ailleurs (un ``<style>`` posé dans le ``<head>``) n'aurait eu aucune
    de ces trois propriétés.

    Ce qu'elle rend possible et qu'aucun theming de composant ne
    remplace : ``@font-face`` (donc l'auto-hébergement d'une fonte
    depuis ``static_dir``), ``@keyframes``, ``@supports``, les propriétés
    custom, et le CSS de survie sur du balisage tiers.
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
        # APRÈS les deux règles de masquage : le bloc global pose un
        # ``* { scrollbar-width: thin }``, mais un sélecteur universel a
        # une spécificité nulle, donc une classe le bat quel que soit
        # l'ordre. L'ordre reste écrit dans ce sens pour que la lecture
        # du fichier suive celle de la cascade.
        parts.append(generate_scrollbar_css(scrollbar, palette))
    if extra := extra_css.strip():
        parts.append("/* --- Theme(css=…) — l'app a le dernier mot --- */")
        parts.append(extra)
    return "\n".join(parts) + "\n"
