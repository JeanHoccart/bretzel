"""Generate the Tailwind v4 ``@theme`` block.

Tailwind v4's design lets you declare CSS custom properties under
``@theme {}`` and have them flow into every utility automatically —
``--color-primary`` becomes ``bg-primary``, ``text-primary``, ``ring-primary``,
etc., free of charge.

We emit two things :

- The **theme block** itself : every semantic + palette color, plus a
  ``-foreground`` companion. RGB triples are space-separated (Tailwind
  v4 convention) so ``bg-primary/50`` works without further setup.
- A **dark-mode override block** (``.dark { ... }``) carrying only the
  slots whose hex actually swaps.

The output is a string fed directly to Lightning CSS at compile time —
no AST, no template engine, no quoted CSS-in-Python tricks.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from bretzel.theme.palette import Palette
from bretzel.theme.tokens import (
    BREAKPOINTS,
    DEFAULT_SHAPE,
    DEFAULT_SPACING,
    DEFAULT_STROKE,
    DEFAULT_TEXT,
    FONT_SLOT_NAMES,
    FOREGROUND_SUFFIX,
    PALETTE_CLASS_PREFIX,
    SEMANTIC_COLOR_NAMES,
    SHAPE_SLOT_NAMES,
    TEXT_SLOT_NAMES,
)


def _hex_to_rgb_value(hex_str: str) -> str:
    """Convert ``#rrggbb`` to ``"rgb(R G G)"`` — Tailwind v4 form.

    v4 expects ``--color-X`` to hold an actual CSS colour value
    (``rgb()`` / ``oklch()`` / hex). Earlier drafts used the v3
    space-separated triplet, but that produces invalid CSS in v4 :
    ``text-primary`` resolves to ``color: var(--color-primary)`` and
    a bare ``39 117 74`` is not a colour. The ``rgb()`` wrapper makes
    alpha modifiers (``bg-primary/50``) keep working — v4's
    ``color-mix`` engine handles the alpha step on its side.
    """
    s = hex_str.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    return f"rgb({r} {g} {b})"


# ───────────────────────────────────────────────────────────────────────────
# Block builders
# ───────────────────────────────────────────────────────────────────────────


def generate_theme_css(
    palette: Palette,
    *,
    fonts: Mapping[str, str] | None = None,
    spacing: str | None = None,
    text: Mapping[str, str] | None = None,
    shape: Mapping[str, str] | None = None,
    stroke: str | None = None,
) -> str:
    """Build the ``@import`` + ``@theme`` + ``.dark`` blocks.

    ``fonts`` : les familles déclarées par ``Theme(fonts=…)``, clés dans
    :data:`~bretzel.theme.tokens.FONT_SLOT_NAMES`. Émises DANS le bloc
    ``@theme`` comme ``--font-<slot>``, donc lues par Tailwind au même
    titre que ses propres tokens : les utilitaires ``font-sans`` /
    ``font-serif`` / ``font-mono`` en héritent, et ``--font-sans``
    redéfini change la fonte du document entier (le preflight v4 pose
    ``html { font-family: var(--default-font-family, …) }`` et
    ``--default-font-family: var(--font-sans)``). Une section absente
    ou vide n'émet **rien** — les piles de Tailwind restent en place,
    et aucun défaut n'est recopié de notre côté.

    Output structure ::

        @import "tailwindcss";

        @custom-variant dark (&:where(.dark, .dark *));
        @custom-variant hover (&:hover);

        @theme {
          --font-sans: Inter, ui-sans-serif, system-ui, sans-serif;
          --color-primary: 39 117 74;
          --color-primary-foreground: 250 250 250;
          ...
          --color-ui-tomato: 229 77 46;
          --color-ui-tomato-foreground: 18 9 7;
          ...
        }

        .dark {
          --color-background: 2 6 23;
          --color-background-foreground: 247 248 250;
          ...
        }

    Note on ``@custom-variant dark`` : Tailwind v4 ships with
    ``@media (prefers-color-scheme: dark)`` as the default ``dark:``
    variant. Bretzel uses class-based dark mode (``.dark`` on
    ``<html>``, written by the FOUC script + the ``ColorScheme``
    ClientState) so we MUST redefine the variant to match the class.
    Without this line every ``dark:hidden`` / ``dark:inline-flex`` /
    etc. silently fails to react to the user's toggle — they're
    bound to the OS preference instead.

    Note on ``@custom-variant hover`` : Tailwind v4 wraps EVERY
    ``hover:`` utility in ``@media (hover: hover)``. Where the primary
    pointer doesn't hover, that query is false and **the rule doesn't
    exist** — class in the DOM, selector in the stylesheet, nothing
    applied. Redefining the variant restores the v3 semantics (the
    escape hatch Tailwind documents for this case). The trade-off is
    sticky hover on touch, taken deliberately : our hovers *enrich*, so
    a lingering tint is cosmetic where an invisible affordance is
    functional breakage. Measurements and date in ``traps.md`` ;
    ``hover:`` must still never CARRY an affordance.
    """
    light_lines = list(_emit_block(palette, mode="light"))
    dark_lines = list(_emit_dark_block(palette))

    parts = [
        '@import "tailwindcss";',
        "",
        "@custom-variant dark (&:where(.dark, .dark *));",
        "@custom-variant hover (&:hover);",
        "",
        "@theme {",
    ]
    # Les fontes AVANT les couleurs : l'ordre n'a aucun effet sur la
    # cascade (ce sont des déclarations de custom properties dans le même
    # bloc), il est là pour la lecture — la première chose qu'on cherche
    # dans un thème généré est ce qui a été personnalisé, pas les 80
    # lignes de palette.
    parts.extend("  " + line for line in _emit_font_block(fonts))
    parts.extend("  " + line for line in _emit_scale_block(spacing, text))
    parts.extend("  " + line for line in _emit_shape_block(shape))
    parts.extend("  " + line for line in _emit_stroke_block(stroke))
    parts.extend("  " + line for line in light_lines)
    parts.append("}")

    if dark_lines:
        parts.append("")
        parts.append(".dark {")
        parts.extend("  " + line for line in dark_lines)
        parts.append("}")

    return "\n".join(parts) + "\n"


def _emit_font_block(fonts: Mapping[str, str] | None) -> Iterable[str]:
    """``--font-<slot>: <family>`` pour chaque slot déclaré.

    Itère sur :data:`FONT_SLOT_NAMES` et non sur les clés reçues : l'ordre
    de sortie ne dépend donc pas de l'ordre d'écriture du dict de
    l'utilisateur, et deux thèmes équivalents produisent le même CSS —
    donc la même empreinte sha256, donc le même cache de compilation.
    La validation des clés vit dans ``Theme.__init__`` (une clé inconnue
    lève à la construction) ; ici on ignore simplement l'absent.
    """
    if not fonts:
        return
    for slot in FONT_SLOT_NAMES:
        family = fonts.get(slot)
        if family:
            yield f"--font-{slot}: {family};"


def _emit_scale_block(
    spacing: str | None, text: Mapping[str, str] | None
) -> Iterable[str]:
    """``--spacing`` et ``--text-<palier>`` — la BASE de l'échelle.

    **Toujours émis**, comme les rayons et contrairement aux fontes.
    Tailwind livre bien les deux, mais Bretzel ne les hérite plus : il
    CHOISIT les siens (cf. :data:`DEFAULT_SPACING` et
    :data:`DEFAULT_TEXT`), parce que l'échelle d'amont vise des pages et
    que celle d'un outil est plus serrée. Se taire ici rendrait la page
    à l'échelle d'un document sans que personne l'ait décidé.

    Les paliers d'AFFICHE (``3xl`` et au-delà) restent absents de
    :data:`DEFAULT_TEXT`, donc muets : aucun chrome ne les écrit, et les
    compresser abîmerait une page d'accueil pour rien.

    Un seul ``--spacing`` suffit à déplacer toute l'échelle
    d'espacement : Tailwind v4 dérive ``h-10``, ``p-4``, ``gap-2``,
    ``w-6`` en ``calc(var(--spacing) * n)``. Les paliers de texte, eux,
    sont des jetons indépendants — d'où un dict, et non un facteur.

    ⚠️ **La hauteur de ligne n'est pas touchée, et c'est voulu.** Tailwind
    range chaque palier avec son ``--text-<palier>--line-height``, exprimé
    en RAPPORT (``calc(1.5 / 1)``) : il suit donc la taille qu'on pose ici
    sans qu'on l'écrive. Émettre la paire demanderait à l'app de décider
    deux choses là où elle en décide une.

    Itère sur :data:`TEXT_SLOT_NAMES` et non sur les clés reçues : sortie
    déterministe, donc empreinte sha256 stable, donc cache de compilation
    stable. Même contrat que les fontes et les rayons.
    """
    yield f"--spacing: {spacing or DEFAULT_SPACING};"
    merged = {**DEFAULT_TEXT, **(text or {})}
    for slot in TEXT_SLOT_NAMES:
        size = merged.get(slot)
        if size:
            yield f"--text-{slot}: {size};"


def _emit_shape_block(shape: Mapping[str, str] | None) -> Iterable[str]:
    """``--radius-<famille>: <longueur>`` pour les trois familles.

    Toujours émis, contrairement aux fontes : une famille absente ne
    laisse pas Tailwind retomber sur un défaut — elle rend
    ``rounded-box`` INEXISTANT, donc tous les slots qui l'écrivent
    perdent leur rayon d'un coup, en silence. Les fontes peuvent se
    taire parce que Tailwind en a ; ces trois-là n'existent que si on
    les écrit.

    Itère sur :data:`SHAPE_SLOT_NAMES` et non sur les clés reçues, même
    raison que pour les fontes : sortie déterministe, donc empreinte
    sha256 stable, donc cache de compilation stable.
    """
    merged = {**DEFAULT_SHAPE, **(shape or {})}
    for slot in SHAPE_SLOT_NAMES:
        yield f"--radius-{slot}: {merged[slot]};"


def _emit_stroke_block(stroke: str | None) -> Iterable[str]:
    """``--bz-stroke`` et ses deux crans, dérivés en ``calc()``.

    Dérivés et non réglés : voir :data:`DEFAULT_STROKE`. Un ``calc()``
    plutôt qu'un calcul Python parce que la valeur peut être n'importe
    quelle longueur CSS — ``0.5px``, ``2px``, ``0.0625rem`` — et que le
    navigateur sait les multiplier alors que nous devrions les parser.
    """
    base = stroke or DEFAULT_STROKE
    yield f"--bz-stroke: {base};"
    yield "--bz-stroke-strong: calc(var(--bz-stroke) * 2);"
    yield "--bz-stroke-accent: calc(var(--bz-stroke) * 4);"


def _emit_block(palette: Palette, *, mode: str) -> Iterable[str]:
    # Semantic slots first (no prefix), in declaration order.
    for name in SEMANTIC_COLOR_NAMES:
        resolved = palette.resolve(name, mode=mode)  # type: ignore[arg-type]
        yield _color_line(name, resolved.bg_hex)
        yield _color_line(_with_suffix(name), resolved.fg_hex)

    # Palette colors with the configured prefix.
    for name in palette.envelope_dict():
        if name in SEMANTIC_COLOR_NAMES:
            continue
        resolved = palette.resolve(name, mode=mode)  # type: ignore[arg-type]
        yield _color_line(_with_prefix(name), resolved.bg_hex)
        yield _color_line(_with_suffix(_with_prefix(name)), resolved.fg_hex)


def _emit_dark_block(palette: Palette) -> Iterable[str]:
    """Emit only the entries whose dark-mode hex differs from light.

    Skipping unchanged entries keeps the dark block small and makes
    visual diffs of the generated CSS easy to read.
    """
    for name in SEMANTIC_COLOR_NAMES:
        light = palette.resolve(name, "light")
        dark = palette.resolve(name, "dark")
        if light.bg_hex == dark.bg_hex and light.fg_hex == dark.fg_hex:
            continue
        if light.bg_hex != dark.bg_hex:
            yield _color_line(name, dark.bg_hex)
        if light.fg_hex != dark.fg_hex:
            yield _color_line(_with_suffix(name), dark.fg_hex)

    # Palette overrides (rare — most named colors stay constant in dark).
    for name in palette.envelope_dict():
        if name in SEMANTIC_COLOR_NAMES:
            continue
        light = palette.resolve(name, "light")
        dark = palette.resolve(name, "dark")
        if light.bg_hex != dark.bg_hex:
            yield _color_line(_with_prefix(name), dark.bg_hex)
        if light.fg_hex != dark.fg_hex:
            yield _color_line(_with_suffix(_with_prefix(name)), dark.fg_hex)


def _color_line(stem: str, hex_value: str) -> str:
    return f"--color-{stem}: {_hex_to_rgb_value(hex_value)};"


def _with_prefix(name: str) -> str:
    return f"{PALETTE_CLASS_PREFIX}{name}"


def _with_suffix(stem: str) -> str:
    return f"{stem}{FOREGROUND_SUFFIX}"


# ───────────────────────────────────────────────────────────────────────────
# Safelist generator
# ───────────────────────────────────────────────────────────────────────────


#: Classes de LAYOUT dont la valeur est un scalaire d'exécution.
#:
#: ``ui.grid(cols=3)`` produit ``grid-cols-3`` par f-string, et
#: ``ui.carousel(per_view=4)`` produit ``basis-1/4``. Ces chaînes
#: n'existent dans AUCUN fichier source, donc le compilateur de prod ne
#: les voit pas — comme les classes de couleur, et pour la même raison.
#: Mesuré le 2026-08-07 : **la grille du playground retombait sur une
#: colonne en mode compilé**, sans erreur ni trace, alors qu'elle était
#: juste en dev (le compilateur navigateur scanne le DOM vivant).
#:
#: Le domaine est BORNÉ, donc la clôture complète est écrivable — c'est
#: exactement l'argument de la safelist couleur. Au-delà de 12 colonnes,
#: Tailwind n'a de toute façon pas d'utilitaire : il faut l'échappatoire
#: ``cols="grid-cols-[…]"``, littérale au call-site donc scannée.
#:
#: Gaté par ``tests/consistency/test_emitted_classes_exist_in_source.py``.
_LAYOUT_CLASSES: tuple[str, ...] = (
    *(f"grid-cols-{n}" for n in range(1, 13)),
    "grid-cols-none", "grid-cols-auto",
    "basis-full",
    *(f"basis-1/{n}" for n in range(2, 13)),
)



# Plancher : les gabarits que la safelist garantit même quand l'appelant
# ne passe rien (``generate_safelist_comment(palette)`` nu — un Theme
# utilisé hors app, un test). Ce plancher ÉTAIT toute la safelist ; il ne
# suffit pas, d'où le paramètre ``shapes`` ci-dessous.
def generate_safelist_comment(
    palette: Palette,
    responsive_classes: Sequence[str] = (),
) -> str:
    """Return a Tailwind v4 ``@source inline(...)`` directive.

    Lightning CSS / le CDN v4 balaient les sources à la recherche de
    motifs d'utilitaires. Une classe qu'aucun fichier n'écrit
    LITTÉRALEMENT n'existera donc pas dans le CSS compilé — elle marche
    en dev (le compilateur navigateur scanne le DOM vivant) et disparaît
    en prod, sans erreur ni trace. La safelist nomme ce qui est dans ce
    cas.

    ``responsive_classes`` : les tokens qu'un prop gradué peut ressortir
    préfixés d'un breakpoint (``gap-6`` → ``md:gap-6``), fournis par
    :func:`bretzel.components.dynamic_responsive_classes`. Ce paramètre
    existe parce que le socle ``theme`` n'a pas le droit d'importer
    ``components`` — c'est l'appelant qui fait le pont.

    ⚠️ **La moitié COULEUR de cette fonction a été déposée le
    2026-08-30** (phase 5 du chantier des jetons). Elle développait
    chaque gabarit de thème (``bg-{bg_color}/10``) sur **toutes** les
    couleurs de la palette : 3 791 classes, 576 Ko sur 717, **80 % de la
    feuille**. Il n'y a plus rien à développer — un thème écrit
    ``bg-(--bz-bg)``, une classe complète que le compilateur voit, et
    c'est la classe-pont posée sur la racine qui dit la couleur (cf.
    :mod:`bretzel.theme.bridges`). Mesuré : ``style.css`` passe de
    758 268 à 354 778 octets.

    Ce qui reste ici est le domaine où le problème existe encore : les
    classes de LAYOUT, qu'une f-string assemble depuis un scalaire
    (``grid-cols-3``, ``basis-1/4``) ou qu'un prop gradué tire d'une
    table de thème. Les deux moitiés sont nécessaires : la première seule
    shippait le 2026-08-07 et laissait
    ``ui.flex(direction={"base":"col","md":"row"})`` sans règle ``md:``
    en prod — la feature entière morte, sans erreur ni trace.

    Syntaxe v4 : ``@source inline("class-1 class-2 …");`` (une vraie
    directive, pas un commentaire CSS — la forme ``/* @source ... */``
    était silencieusement ignorée, ce qui est la raison pour laquelle les
    utilitaires de couleur manquaient).
    """
    classes: list[str] = []
    # Les classes de layout : domaine borné, et ``responsive_classes``
    # peut préfixer n'importe laquelle par n'importe quel breakpoint —
    # d'où la clôture sur les deux axes.
    #
    # ``_LAYOUT_CLASSES`` couvre ce qu'une f-string assemble depuis un
    # SCALAIRE (``grid-cols-3``, ``basis-1/4``) ; ``responsive_classes``
    # couvre ce qu'un prop gradué tire d'une TABLE de thème (``gap-6``,
    # ``flex-row``, ``hidden``). Les deux moitiés sont nécessaires : la
    # première seule shippait le 2026-08-07 et laissait
    # ``ui.flex(direction={"base":"col","md":"row"})`` sans règle ``md:``
    # en prod — la feature entière morte, sans erreur ni trace.
    for cls in (*_LAYOUT_CLASSES, *responsive_classes):
        classes.append(cls)
        classes.extend(f"{bp}:{cls}" for bp in BREAKPOINTS)

    inline_value = " ".join(classes)
    return f'@source inline("{inline_value}");'
