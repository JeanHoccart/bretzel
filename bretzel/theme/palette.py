"""Resolved palette — semantic + extras, with auto-foreground derivation.

The palette is the single source of truth for *what hex value* every
named color carries. Components consult it via :func:`Palette.resolve`
at render time to interpolate ``{bg_color}``/``{fg_color}`` tokens in
their slot templates.

Two responsibilities live here :

1. **Color algebra** : parse hex strings, derive a foreground that has
   enough contrast with the background, expose :class:`ResolvedColor`
   to downstream consumers.
2. **Palette assembly** : aggregate semantic + palette dictionaries
   for both light and dark modes, with sensible inheritance (dark
   omitting an entry → falls through to light).

Pure module — no I/O, no global state. The default palette and the
default semantic dictionaries that ship with Bretzel live here as
plain ``dict`` constants ; a user theme can take them as the basis
and overlay just the entries they want to change.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Final, Literal

from bretzel.theme.tokens import (
    FOREGROUND_SUFFIX,
    PALETTE_CLASS_PREFIX,
    SEMANTIC_COLOR_NAMES,
)


class ThemeError(ValueError):
    """Raised on invalid theme input (missing slot, unknown color, …)."""


# ───────────────────────────────────────────────────────────────────────────
# Hex / RGB / HSL primitives
# ───────────────────────────────────────────────────────────────────────────


def _parse_hex(hex_str: str) -> tuple[int, int, int]:
    """Parse a ``#rrggbb`` (or ``#rgb``) string into ``(r, g, b)`` 0-255.

    Raises :class:`ThemeError` on malformed input — we'd rather fail
    at theme construction than emit a broken stylesheet.
    """
    s = hex_str.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6 or not all(c in "0123456789abcdefABCDEF" for c in s):
        raise ThemeError(
            f"Invalid hex color {hex_str!r} : expected ``#rrggbb`` or ``#rgb``."
        )
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


#: Les coefficients WCAG de la luminance relative. Nommés — et non
#: laissés en littéraux — parce qu'ils sont MIROITÉS en JavaScript par le
#: theme studio, qui ne peut pas importer Python. C'est le même dispositif
#: que ``protocol.py`` ↔ ``runtime.js``, et la même gate le garde :
#: ``test_the_foreground_algebra_is_mirrored_in_js``.
_LUM_COEFFICIENTS: Final[tuple[float, float, float]] = (0.2126, 0.7152, 0.0722)
_LUM_LINEAR_CUTOFF: Final[float] = 0.03928
_LUM_LINEAR_DIVISOR: Final[float] = 12.92
_LUM_GAMMA_OFFSET: Final[float] = 0.055
_LUM_GAMMA_DIVISOR: Final[float] = 1.055
_LUM_GAMMA_EXPONENT: Final[float] = 2.4

#: Le seuil W3C « à partir d'ici, écris en sombre sur ce fond ».
_FG_DARK_CUTOFF: Final[float] = 0.179
#: La clarté du texte sombre, et celle du clair.
_FG_DARK_LIGHTNESS: Final[float] = 0.08
_FG_LIGHT_LIGHTNESS: Final[float] = 0.96
#: La teinte que le texte emprunte au fond, et son plafond. C'est ce qui
#: rend la paire « d'un seul morceau » au lieu de noir-ou-blanc.
_FG_TINT_FACTOR: Final[float] = 0.12
_FG_TINT_CAP: Final[float] = 0.08

#: Le contraste que ``--bz-on-solid`` doit atteindre — WCAG AA texte
#: normal. Une valeur, pas un « à peu près » : c'est le seuil que la gate
#: ``test_the_colour_steps_stay_readable`` applique.
_FG_AA_TARGET: Final[float] = 4.5
#: Le nombre de crans de la remontée. Cinq suffisent : le pire cas mesuré
#: (``plum``) clôt AA au deuxième.
_FG_ESCALATION_STEPS: Final[int] = 5


def _relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG relative luminance — 0 for black, 1 for white.

    Used by :func:`resolve_color_pair` to decide whether the
    auto-foreground should be light or dark. Also exposed (via the
    test suite) so we can assert the contrast ratio in tests.
    """
    def channel(v: int) -> float:
        c = v / 255.0
        if c <= _LUM_LINEAR_CUTOFF:
            return c / _LUM_LINEAR_DIVISOR
        return (
            (c + _LUM_GAMMA_OFFSET) / _LUM_GAMMA_DIVISOR
        ) ** _LUM_GAMMA_EXPONENT

    kr, kg, kb = _LUM_COEFFICIENTS
    return kr * channel(r) + kg * channel(g) + kb * channel(b)


def _contrast_ratio(rgb_a: tuple[int, int, int], rgb_b: tuple[int, int, int]) -> float:
    """WCAG contrast ratio — 1 for identical, 21 for white on black."""
    la = _relative_luminance(*rgb_a)
    lb = _relative_luminance(*rgb_b)
    light, dark = max(la, lb), min(la, lb)
    return (light + 0.05) / (dark + 0.05)


# ───────────────────────────────────────────────────────────────────────────
# Foreground derivation
# ───────────────────────────────────────────────────────────────────────────


def resolve_color_pair(hex_color: str) -> tuple[str, str]:
    """Return ``(bg_hex, fg_hex)`` for a single hex.

    Strategy : compare the background's luminance to a perceptual
    midpoint and pick a near-black or near-white foreground, then
    tint it lightly with the background's hue so the pair still
    feels of-a-piece visually — and back that tint off if it would
    cost readability (:func:`_readable_fg`).

    ⚠️ Cette ligne disait « clears AA Large (>= 3.0) … and AA (>= 4.5)
    for MOST » jusqu'au 2026-09-01, et le « most » était une concession
    chiffrable que personne n'avait chiffrée : trois couleurs de la
    palette livrée en sortaient. Depuis la remontée, AA est tenu pour
    toutes — c'est une garantie, plus une tendance, et
    ``test_the_colour_steps_stay_readable`` la vérifie.

    A pure invert-lightness approach (the v1 attempt) crashes on
    mid-luminance colors like ``#3e63dd`` whose inverted lightness
    is too close to the original — same hue + similar luminance =
    insufficient contrast.
    """
    r, g, b = _parse_hex(hex_color)
    h, _l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    bg_lum = _relative_luminance(r, g, b)

    # 0.179 is the W3C-suggested cutoff for "use dark text on this bg".
    # Above the cutoff: near-black foreground, lightly tinted with the bg's
    # hue + saturation so the pair stays visually unified. Below: near-white,
    # which tolerates a touch more saturation without losing legibility.
    base_l = (
        _FG_DARK_LIGHTNESS if bg_lum > _FG_DARK_CUTOFF
        else _FG_LIGHT_LIGHTNESS
    )
    base_s = min(s * _FG_TINT_FACTOR, _FG_TINT_CAP)
    return _to_hex(r, g, b), _readable_fg((r, g, b), h, base_l, base_s)


def _readable_fg(
    bg: tuple[int, int, int], hue: float, base_l: float, base_s: float
) -> str:
    """Le foreground teinté, RECULÉ jusqu'à ce qu'il soit lisible.

    Pourquoi ça existe (2026-09-01)
    --------------------------------
    Trois couleurs de la palette livrée manquaient AA sur leur propre
    ``--bz-on-solid``, et la table ``_KNOWN_BELOW`` de la gate les
    portait en dette : ``muted`` 4,36 · ``pink`` 4,48 · ``plum`` 4,33.

    Le coupable n'était **pas** la direction du foreground. Mesuré, le
    seuil de 0,179 choisit déjà le meilleur des deux candidats pour les
    31 couleurs — sur ``plum``, un noir pur donnerait 4,42 là où le
    blanc pur donne 4,75. Le coupable est la **teinte** : les 0,08 de
    lumière gardés en réserve et la saturation empruntée au fond coûtent
    entre 0,40 et 0,61 de ratio, et c'est ce qui fait passer ces trois-là
    sous la barre.

    D'où la forme : on garde la teinte, mais on la RECULE — vers
    l'extrême de lumière et vers zéro de saturation — jusqu'à ce que AA
    soit clos, et on s'arrête au premier cran qui suffit. L'unité
    visuelle est une intention ; la lisibilité est un contrat.

    Ce que ça change, et c'est le point : **rien pour les autres**. Une
    couleur qui clôt AA au cran 0 sort au cran 0, à l'octet près — 73
    des 78 couples (nom, mode) du thème par défaut. Seules les trois en
    dette bougent : ``pink`` au cran 1, ``muted`` et ``plum`` au cran 2.
    """
    extreme = 0.0 if base_l < 0.5 else 1.0
    fg = (0, 0, 0)
    for step in range(_FG_ESCALATION_STEPS + 1):
        t = step / _FG_ESCALATION_STEPS
        light = base_l + (extreme - base_l) * t
        sat = base_s * (1 - t)
        cr, cg, cb = colorsys.hls_to_rgb(hue, light, sat)
        fg = (round(cr * 255), round(cg * 255), round(cb * 255))
        if _contrast_ratio(bg, fg) >= _FG_AA_TARGET:
            break
    return _to_hex(*fg)


# ───────────────────────────────────────────────────────────────────────────
# Default palette + semantic dicts
# ───────────────────────────────────────────────────────────────────────────


# Lifted verbatim from spec § *DEFAULT_PALETTE*. Keeping the colors
# inline (vs. an external file) means the framework is reproducible
# without I/O at startup.
DEFAULT_PALETTE: Final[dict[str, str]] = {
    "gray":    "#8d8d93",
    "mauve":   "#8e8c99",
    "slate":   "#8b8d98",
    "sage":    "#868e8b",
    "olive":   "#868e80",
    "sand":    "#8d8d86",
    "tomato":  "#e54d2e",
    "red":     "#e5484d",
    "ruby":    "#e54666",
    "crimson": "#e93d82",
    "pink":    "#d6409f",
    "plum":    "#682747",
    "purple":  "#8e4ec6",
    "violet":  "#6e56cf",
    "iris":    "#5b5bd6",
    "indigo":  "#3e63dd",
    "blue":    "#0090ff",
    "cyan":    "#00a2c7",
    "sky":     "#30a5e2",
    "teal":    "#12a594",
    "jade":    "#29a383",
    "green":   "#30a46c",
    "grass":   "#46a758",
    "yellow":  "#f5d90a",
    "amber":   "#ffc53d",
    "orange":  "#f76b15",
    "gold":    "#e99536",
    "bronze":  "#a18072",
    "brown":   "#ad7f58",
    "black":   "#000000",
    "white":   "#ffffff",
}  # fmt: skip


# The six BRAND hues are spread across the colour wheel (blue / violet /
# green / amber / red / cyan) so every semantic pair stays perceptually
# distinct — worst-pair ΔE(CIE76) ≈ 36 vs the old palette's 17.7, where
# ``secondary``≈``warning`` (both amber) and ``primary``≈``success`` (both
# green) collapsed into confusable tints. Enforced by
# ``tests/consistency/test_palette_distinctness.py`` (min ΔE gate) — retune a
# hue here and the gate fails if it re-introduces a collision.
# ⚠️ **Les neutres sont STRICTEMENT ACHROMATIQUES, et c'est une décision du
# 2026-09-13.** Ils étaient le ``slate`` de Tailwind — donc bleutés, et
# reconnaissables au premier coup d'œil comme « un projet qui n'a pas choisi
# ses couleurs ». Un gris qui porte une teinte prend parti pour elle : il
# réchauffe ou refroidit tout ce qu'on pose dessus, et il se querelle avec
# l'accent de l'app dès que celui-ci part dans l'autre sens. À teinte nulle,
# le fond ne dit rien et **la marque est la seule couleur de l'écran** — ce
# qui est exactement ce qu'on attend du défaut d'un framework, qui ne
# connaît pas la marque de l'app qui l'utilisera.
#
# ⚠️ **``interface`` ne vaut plus ``background``.** Les deux étaient à
# ``#f8fafc`` en clair : un champ, un panneau de select, un creux de
# contrôle rendaient donc EXACTEMENT la couleur de la page, et toute la
# hiérarchie de profondeur reposait sur la seule bordure. Ce n'était pas un
# choix — c'était le même jeton recopié deux fois.
DEFAULT_SEMANTIC_LIGHT: Final[dict[str, str]] = {
    # L'accent : un indigo PROFOND plutôt que le bleu roi d'avant
    # (``#2f5fd0``). Il cesse de crier sur une page claire, il reste
    # franchement distinct du cyan d'``info``, et il porte assez de
    # violet pour ne pas se confondre avec un lien de navigateur.
    #
    # Le second est une PRUNE sourde, et sa distance est mesurée : ΔE 47
    # de l'accent, 47 du rouge d'erreur, 96 du vert. Un améthyste (#8455ab)
    # a été essayé le même jour et refusé par
    # ``test_palette_distinctness`` — ΔE 21 de l'accent, donc deux
    # couleurs sémantiques qui se ressemblent et une matrice de variantes
    # ambiguë.
    "primary":    "#682747",
    "secondary":  "#3a52b0",
    "success":    "#2f9e64",
    "error":      "#e5484d",
    "warning":    "#f0a91b",
    "info":       "#0e9bc4",
    "background": "#fafafa",
    "surface":    "#ffffff",
    "interface":  "#f0f0f1",
    "text":       "#171717",
    "muted":      "#6b6b6e",
}  # fmt: skip


# Only the slots that actually swap in dark mode — everything else
# falls through to light (the brand colors stay constant).
# Le sombre est neutre lui aussi, et **ce n'est plus un quasi-noir marine**.
# ``#020617`` était presque du noir pur ET très bleu : sous un aplat saturé
# il fatigue en quelques secondes, et l'écart jusqu'à ``surface`` était un
# saut. Les trois plans montent maintenant par crans réguliers, ce qui est
# ce qui fait lire une profondeur.
#
# Seuls les slots qui BASCULENT vraiment sont ici — les couleurs de marque
# et de statut gardent leur valeur claire dans les deux modes.
DEFAULT_SEMANTIC_DARK: Final[dict[str, str]] = {
    "background": "#0a0a0a",
    "surface":    "#151515",
    "interface":  "#212121",
    "text":       "#f5f5f5",
    "muted":      "#a0a0a3",
}  # fmt: skip


# ───────────────────────────────────────────────────────────────────────────
# ResolvedColor + Palette
# ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ResolvedColor:
    """A color name + hex pair + the CSS class names that point to it."""

    name: str
    bg_hex: str
    fg_hex: str
    bg_class: str
    fg_class: str


# A palette entry can be either ``"#hex"`` (auto fg) or ``("#bg", "#fg")``
# (explicit fg). We normalise both shapes when building the palette.
_PaletteValue = str | tuple[str, str]


Mode = Literal["light", "dark"]


class Palette:
    """Resolved palette — semantic + extras for both light and dark modes.

    Built once at app startup ; every render call shares the same
    instance. The class is small on purpose : it owns the *resolution
    table*, not the user-facing :class:`Theme` ergonomics.
    """

    __slots__ = (
        "_palette_dark",
        "_palette_light",
        "_palette_prefix",
        "_semantic_dark",
        "_semantic_light",
    )

    def __init__(
        self,
        semantic_light: dict[str, _PaletteValue],
        semantic_dark: dict[str, _PaletteValue] | None = None,
        palette_light: dict[str, _PaletteValue] | None = None,
        palette_dark: dict[str, _PaletteValue] | None = None,
        *,
        palette_prefix: str = PALETTE_CLASS_PREFIX,
    ) -> None:
        # Validate semantic completeness — every slot must be present.
        missing = set(SEMANTIC_COLOR_NAMES) - set(semantic_light.keys())
        if missing:
            raise ThemeError(
                f"Missing semantic colors : {sorted(missing)}. "
                "Every slot in SEMANTIC_COLOR_NAMES must be defined."
            )

        # Reject unknown semantic keys. C'est ICI que le silence vivait :
        # ``semantic_light`` était recomposé par compréhension SUR
        # ``SEMANTIC_COLOR_NAMES`` (donc une clé en trop n'était jamais
        # itérée) et ``semantic_dark`` portait un ``if name in
        # SEMANTIC_COLOR_NAMES`` qui la filtrait. Dans les deux cas
        # ``Theme(semantic={"primry": "#f00"})`` était accepté, la clé
        # disparaissait, et rien — ni erreur, ni CSS, ni indice — ne
        # distinguait ça d'une couleur appliquée.
        #
        # Les slots sémantiques sont **fermés** : ce sont les 11 noms que
        # tout composant connaît, c'est-à-dire de la grammaire du
        # framework. Une clé hors liste ne peut rien vouloir dire d'autre
        # qu'une faute — au contraire de ``palette=``, qui est une liste
        # OUVERTE et le reste (le charter : « the user can add, remove or
        # override entries »).
        for label, mapping in (("semantic", semantic_light), ("semantic_dark", semantic_dark)):
            unknown = sorted(set(mapping or {}) - set(SEMANTIC_COLOR_NAMES))
            if unknown:
                raise ThemeError(
                    f"Theme({label}=…) : slot(s) inconnu(s) {unknown}. "
                    f"Les 11 slots sémantiques sont "
                    f"{list(SEMANTIC_COLOR_NAMES)} — une clé hors de cette "
                    f"liste n'est lue par aucun composant. Pour ajouter une "
                    f"couleur NOMMÉE (liste ouverte), c'est `palette=`."
                )

        # Reject collisions between palette names and semantic ones —
        # an "primary" entry under ``palette=`` is almost always a
        # confusion between the two.
        palette_light_clean = palette_light or {}
        overlap = set(palette_light_clean.keys()) & set(SEMANTIC_COLOR_NAMES)
        if overlap:
            raise ThemeError(
                f"Palette names {sorted(overlap)} collide with semantic "
                "slots. You probably meant ``semantic=`` ."
            )

        self._semantic_light = {
            name: _coerce_pair(name, semantic_light[name])
            for name in SEMANTIC_COLOR_NAMES
        }
        # Plus de filtre ``if name in SEMANTIC_COLOR_NAMES`` : la garde
        # ci-dessus a déjà levé, donc il ne pourrait plus rien retirer. Le
        # laisser ferait croire qu'une clé hors liste peut arriver ici.
        self._semantic_dark = {
            name: _coerce_pair(name, value)
            for name, value in (semantic_dark or {}).items()
        }
        self._palette_light = {
            name: _coerce_pair(name, value)
            for name, value in palette_light_clean.items()
        }
        self._palette_dark = {
            name: _coerce_pair(name, value)
            for name, value in (palette_dark or {}).items()
        }
        self._palette_prefix = palette_prefix

    # ── Lookups ─────────────────────────────────────────────────────────

    def resolve(self, color: str, mode: Mode = "light") -> ResolvedColor:
        """Look up a color by name. Honours dark-mode overrides.

        Raises :class:`ThemeError` if the color is unknown — a typo
        or rename would otherwise silently produce ``bg-tomatto`` and
        an empty Tailwind compile.
        """
        bg_hex, fg_hex = self._lookup(color, mode)
        return ResolvedColor(
            name=color,
            bg_hex=bg_hex,
            fg_hex=fg_hex,
            bg_class=self.bg_class(color),
            fg_class=self.fg_class(color),
        )

    def bg_class(self, color: str) -> str:
        """The CSS class name for backgrounds.

        - Semantic colors : no prefix (``bg-primary``).
        - Palette colors : the configured prefix (``bg-ui-tomato``).
        """
        if color in SEMANTIC_COLOR_NAMES:
            return color
        if color in self._palette_light or color in self._palette_dark:
            return f"{self._palette_prefix}{color}"
        raise ThemeError(self.unknown_color_message(color))

    def unknown_color_message(self, color: str) -> str:
        """Le message d'une couleur refusée — écrit UNE fois.

        Il dit la conséquence, pas seulement la faute, parce que la
        conséquence est invisible : la classe finale est ASSEMBLÉE au
        rendu, donc elle n'existe dans aucune source, donc le compilateur
        Tailwind de production ne la génère pas. Ça marche en dev (le
        compilateur navigateur lit le DOM vivant) et ça sort sans style
        en prod, avec un HTML identique des deux côtés. Un message qui
        dirait juste « couleur inconnue » laisserait l'auteur croire à un
        détail cosmétique.
        """
        from bretzel.theme.slots import COLOR_KEYWORDS

        known = sorted(
            {*SEMANTIC_COLOR_NAMES, *self._palette_light, *self._palette_dark}
        )
        return (
            f"Couleur inconnue : {color!r}.\n\n"
            f"Cette palette accepte : {', '.join(known)}.\n"
            f"Plus les mots-clés CSS : {', '.join(sorted(COLOR_KEYWORDS))}.\n\n"
            f"Pourquoi ça LÈVE au lieu de passer : le thème écrit "
            f"``bg-{{bg_color}}/15``, qui devient ``bg-{color}/15`` au rendu "
            f"— une classe qui n'apparaît littéralement dans AUCUNE source. "
            f"Le compilateur Tailwind de PRODUCTION ne génère que ce qu'il "
            f"trouve écrit, et la safelist ne développe que les couleurs "
            f"ci-dessus. L'élément serait donc sorti SANS STYLE en prod, tout "
            f"en étant correct en dev (le compilateur navigateur, lui, lit le "
            f"DOM vivant). HTML identique des deux côtés, aucune erreur : "
            f"invisible avant déploiement.\n\n"
            f"Pour une couleur de marque, déclare-la — elle entre alors dans "
            f"la safelist : Theme(palette={{{color!r}: '#hex'}})."
        )

    def fg_class(self, color: str) -> str:
        """The CSS class name for foregrounds (auto ``-foreground`` suffix)."""
        return f"{self.bg_class(color)}{FOREGROUND_SUFFIX}"

    def all_colors(self, mode: Mode = "light") -> dict[str, ResolvedColor]:
        """Every color the palette knows about, resolved for ``mode``."""
        out: dict[str, ResolvedColor] = {}
        for name in SEMANTIC_COLOR_NAMES:
            out[name] = self.resolve(name, mode)
        for name in self._palette_light:
            out[name] = self.resolve(name, mode)
        return out

    def envelope_dict(self) -> dict[str, dict[str, str]]:
        """Compact JSON-friendly summary for the runtime envelope.

        Format de sortie, destiné au runtime ::

            { "primary": {"bg": "primary", "fg": "primary-foreground"}, … }

        Only class names are sent — hex values live in the compiled
        CSS variables and don't need to round-trip through JS.
        """
        out: dict[str, dict[str, str]] = {}
        for name in SEMANTIC_COLOR_NAMES:
            out[name] = {"bg": self.bg_class(name), "fg": self.fg_class(name)}
        for name in self._palette_light:
            out[name] = {"bg": self.bg_class(name), "fg": self.fg_class(name)}
        return out

    # ── Internal lookup walking light/dark/palette/semantic ─────────────

    def _lookup(self, color: str, mode: Mode) -> tuple[str, str]:
        if mode == "dark":
            if color in self._semantic_dark:
                return self._semantic_dark[color]
            if color in self._palette_dark:
                return self._palette_dark[color]
        if color in self._semantic_light:
            return self._semantic_light[color]
        if color in self._palette_light:
            return self._palette_light[color]
        raise ThemeError(self.unknown_color_message(color))


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _coerce_pair(name: str, value: _PaletteValue) -> tuple[str, str]:
    """Normalise a palette entry to ``(bg_hex, fg_hex)``.

    Accepts :

    - ``"#hex"`` → derives fg via :func:`resolve_color_pair`.
    - ``("#bg", "#fg")`` tuple → both hex values explicit.

    Validates the hex format eagerly so a typo trips at theme
    construction, not at first render.
    """
    if isinstance(value, str):
        return resolve_color_pair(value)
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and all(isinstance(v, str) for v in value)
    ):
        bg, fg = value
        # Normalise via _parse_hex+_to_hex so casing and shorthand
        # (#abc) are smoothed to a canonical form.
        r, g, b = _parse_hex(bg)
        fr, fg_, fb = _parse_hex(fg)
        return _to_hex(r, g, b), _to_hex(fr, fg_, fb)
    raise ThemeError(
        f"Invalid palette entry for {name!r} : expected ``'#hex'`` "
        f"or ``('#bg','#fg')`` tuple, got {value!r}."
    )
