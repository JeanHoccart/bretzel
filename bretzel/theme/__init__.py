"""Visual identity, palettes, and Tailwind CSS generation."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from bretzel.theme.color_scheme import ColorScheme
from bretzel.theme.config import IconConfig, ScrollbarConfig
from bretzel.theme.css import generate_theme_css_full as generate_theme_css_full
from bretzel.theme.css import strip_safelist as strip_safelist
from bretzel.theme.css import strip_scan_roots as strip_scan_roots
from bretzel.theme.palette import (
    DEFAULT_PALETTE as DEFAULT_PALETTE,
)
from bretzel.theme.palette import (
    DEFAULT_SEMANTIC_DARK as DEFAULT_SEMANTIC_DARK,
)
from bretzel.theme.palette import (
    DEFAULT_SEMANTIC_LIGHT as DEFAULT_SEMANTIC_LIGHT,
)
from bretzel.theme.palette import (
    Palette as Palette,
)
from bretzel.theme.palette import (
    ResolvedColor as ResolvedColor,
)
from bretzel.theme.palette import (
    ThemeError,
)
from bretzel.theme.slots import merge_component_themes as merge_component_themes
from bretzel.theme.tokens import (
    DEFAULT_PALETTE_NAMES,
    DEFAULT_SHAPE,
    DEFAULT_SPACING,
    DEFAULT_STROKE,
    DEFAULT_TEXT,
    FONT_SLOT_NAMES,
    SEMANTIC_COLOR_NAMES,
    SHAPE_SLOT_NAMES,
    TEXT_SLOT_NAMES,
)
from bretzel.theme.tokens import (
    DEFAULT_SPACING_PX as DEFAULT_SPACING_PX,
)
from bretzel.theme.tokens import (
    AnyColor as AnyColor,
)
from bretzel.theme.tokens import (
    PaletteColors as PaletteColors,
)
from bretzel.theme.tokens import (
    SemanticColors as SemanticColors,
)

#: **Ce que l'utilisateur écrit.** Les outils internes de génération,
#: résolution et sérialisation restent importables par leur chemin précis.
__all__ = [
    # Point d'entrée : on en construit un, on le passe à Bretzel(theme=…)
    "Theme",
    # Mode clair/sombre courant — un ClientState fourni par le framework
    "ColorScheme",
    # Sections de configuration qu'on passe au constructeur
    "IconConfig",
    "ScrollbarConfig",
    # Ce qu'on nomme dans un slot : les couleurs sémantiques
    "SEMANTIC_COLOR_NAMES",
    # Les teintes nommées de la palette livrée.
    "DEFAULT_PALETTE_NAMES",
    # Ce qu'accepte ``Theme(fonts=…)`` — trois slots, fermés
    "FONT_SLOT_NAMES",
    # Ce qu'accepte ``Theme(shape=…)`` — trois familles, fermées
    "SHAPE_SLOT_NAMES",
    # Ce qu'accepte ``Theme(text=…)`` — les paliers de Tailwind, fermés.
    # Le palier médian s'y dit ``base`` et non ``md`` : c'est le seul
    # endroit du framework où les deux échelles se touchent.
    "TEXT_SLOT_NAMES",
    # Le pas d'espacement en PIXELS, pour une app qui compose une
    # géométrie en Python (la hauteur d'un bloc de N heures dans une
    # grille) — une classe Tailwind ne sait pas additionner.
    "DEFAULT_SPACING_PX",
    # L'erreur qu'un thème malformé lève
    "ThemeError",
]

#: **Ré-exporté pour les AUTRES COUCHES, pas pour l'auteur d'une app.**
#:
#: Chaque nom d'ici porte l'alias redondant ``X as X`` à l'import : c'est le
#: marqueur PEP 484 du ré-export intentionnel. La liste est vérifiée par
#: ``tests/consistency/test_public_surface_is_classified.py`` : rien n'entre
#: dans une façade sans être classé d'un côté ou de l'autre.
_INTERNAL = [
    "Palette",
    "ResolvedColor",
    "SemanticColors",
    "PaletteColors",
    "AnyColor",
    "merge_component_themes",
    "generate_theme_css_full",
    "strip_safelist",
    "strip_scan_roots",
    "DEFAULT_PALETTE",
    "DEFAULT_SEMANTIC_LIGHT",
    "DEFAULT_SEMANTIC_DARK",
]


# Sentinel to distinguish "user passed nothing" from "user passed None".
_UNSET: Any = object()


# ───────────────────────────────────────────────────────────────────────────
# Theme
# ───────────────────────────────────────────────────────────────────────────


class Theme:
    """Build a user-facing Bretzel theme."""

    __slots__ = (
        "_components",
        "_css",
        "_css_cache",
        "_fonts",
        "_icons",
        "_merged_components",
        "_palette",
        "_palette_dark",
        "_resolved_palette",
        "_scrollbar",
        "_semantic",
        "_semantic_dark",
        "_shape",
        "_spacing",
        "_stroke",
        "_text",
    )

    def __init__(
        self,
        *,
        semantic: Mapping[str, Any] | None = None,
        semantic_dark: Mapping[str, Any] | None = None,
        palette: Mapping[str, Any] | None = None,
        palette_dark: Mapping[str, Any] | None = None,
        components: Mapping[str, Any] | None = None,
        fonts: Mapping[str, str] | None = None,
        spacing: str | None = None,
        text: Mapping[str, str] | None = None,
        shape: Mapping[str, str] | None = None,
        stroke: str | None = None,
        css: str | Path | None = None,
        scrollbar: ScrollbarConfig | Mapping[str, Any] | None = _UNSET,
        icons: IconConfig | Mapping[str, Any] | None = _UNSET,
        base: Theme | None | Literal['default'] = "default",
    ) -> None:
        base_theme = _resolve_base(base)

        # ── Section-by-section merge with the resolved base ─────────────
        self._semantic = _merge_dict(_section(base_theme, "_semantic"), semantic)
        self._semantic_dark = _merge_dict(
            _section(base_theme, "_semantic_dark"), semantic_dark
        )
        self._palette = _merge_dict(_section(base_theme, "_palette"), palette)
        self._palette_dark = _merge_dict(
            _section(base_theme, "_palette_dark"), palette_dark
        )
        self._components = _deep_merge_dicts(
            _section(base_theme, "_components"), components
        )
        # Merges ``cls.THEME`` ↔ override, mémoïsés par THEME_KEY (cf.
        # ``merged_component_theme``). Les deux entrées sont immuables
        # après le boot, le merge est donc calculé UNE fois — sans
        # cache, ``compose_class`` re-mergait à chaque slot de chaque
        # render (mesuré : +76 % sur un render de Select overridé).
        self._merged_components: dict[str, dict[str, Any]] = {}
        self._fonts = _merge_fonts(_section(base_theme, "_fonts"), fonts)
        # L'échelle : sa base est un SCALAIRE (un seul réglage, comme le
        # trait), ses paliers de texte un dict de slots fermés (comme les
        # fontes). Les deux sont muets par défaut — cf. ``_emit_scale_block``.
        self._spacing = _merge_spacing(_scalar(base_theme, "_spacing"), spacing)
        self._text = _merge_text(_section(base_theme, "_text"), text)
        self._shape = _merge_shape(_section(base_theme, "_shape"), shape)
        # ``_scalar`` et pas ``_section`` : le trait est UNE chaîne,
        # pas un dict de slots — il n'a qu'une question à régler.
        self._stroke = _merge_stroke(
            _scalar(base_theme, "_stroke"), stroke
        )
        # La porte CSS s'AJOUTE à celle de la base, elle ne la remplace pas.
        #
        # La première version remplaçait, au motif qu'hériter de règles
        # invisibles depuis ``base=`` est désagréable. Mesuré, ça donnait une
        # moitié de thème : ``Theme(base=marque, css=…)`` gardait le
        # ``--font-sans`` de la marque (les sections dict, elles, se mergent)
        # et perdait le ``@font-face`` qui rendait cette fonte chargeable.
        # La page retombait sur la pile système **sans rien dire** — le mode
        # de défaillance exact que cette section existe pour fermer.
        #
        # En chaînes, le dernier morceau gagne à spécificité égale, donc
        # « ajouter » suffit aussi à surcharger : la cascade CSS EST le
        # mécanisme de retrait. Reste la remise à zéro, qu'un ``css=""``
        # explicite assure — même sortie que ``scrollbar=None``.
        self._css = _merge_css(_section_tuple(base_theme, "_css"), css)
        self._scrollbar = _coerce_scrollbar(
            scrollbar,
            base_theme._scrollbar if base_theme else ScrollbarConfig(),
        )
        self._icons = _coerce_icons(
            icons,
            base_theme._icons if base_theme else IconConfig(),
        )

        # ── Build the resolved Palette eagerly so any error surfaces here ──
        self._resolved_palette = Palette(
            semantic_light=self._semantic,
            semantic_dark=self._semantic_dark,
            palette_light=self._palette,
            palette_dark=self._palette_dark,
        )
        # CSS is generated lazily — first call to ``generate_css()``
        # caches it. Theme is immutable post-init, mais la safelist
        # dépend des gabarits passés à l'appel : le cache est un dict
        # clé par ces gabarits.
        self._css_cache: dict[tuple[str, ...], str] = {}

    # ── Read-only accessors ─────────────────────────────────────────────

    def get_palette(self) -> Palette:
        return self._resolved_palette

    def get_component_theme(self, name: str) -> dict[str, Any]:
        """Return the RAW user override dict for ``name`` — empty dict
        when the component has no override. Components resolve their
        effective theme via :meth:`merged_component_theme` (called by
        ``Component._resolved_theme``)."""
        return self._components.get(name, {})

    def get_component_overrides(self) -> Mapping[str, Any]:
        """Return component overrides exactly as declared."""
        return self._components

    def merged_component_theme(
        self, name: str, shipped: dict[str, Any]
    ) -> dict[str, Any]:
        """Deep-merge of ``shipped`` (the component's ``cls.THEME``)
        with the user override registered under ``name`` — memoized.

        Both inputs are immutable after startup (``cls.THEME`` is a
        module constant ; the override dict is built once at ``Theme``
        construction), so the merge is computed once per THEME_KEY.
        Classes sharing a THEME_KEY (the Sidebar / Navbar families)
        share the SAME ``THEME`` dict object, so keying by name alone
        is sound. Returns ``shipped`` itself when no override exists —
        identity fast path ; callers must treat the result as
        read-only either way."""
        override = self._components.get(name)
        if not override:
            return shipped
        cached = self._merged_components.get(name)
        if cached is None:
            cached = merge_component_themes(shipped, override)
            self._merged_components[name] = cached
        return cached

    def get_scrollbar(self) -> ScrollbarConfig:
        return self._scrollbar

    def get_icons(self) -> IconConfig:
        return self._icons

    # ── Generators ──────────────────────────────────────────────────────

    def generate_css(
        self,
        *,
        responsive_classes: Sequence[str] = (),
    ) -> str:
        """The full ``theme.css`` Lightning CSS will ingest. Cached.

        ``responsive_classes`` : les tokens des tables graduées (cf.
        :func:`bretzel.components.dynamic_responsive_classes`), injectés
        au démarrage.

        Le cache est clé par la liste — deux appels avec des listes
        différentes doivent produire deux CSS différents, sinon le
        premier appel (souvent un appel nu dans un test) figerait une
        safelist amputée pour tout le process. C'est aussi pourquoi la
        nouvelle liste entre dans la clé plutôt que de s'y ajouter en
        silence : sinon le CSS servi dépendrait de l'ordre des appels.

        """
        key = tuple(responsive_classes)
        if key not in self._css_cache:
            self._css_cache[key] = generate_theme_css_full(
                self._resolved_palette,
                scrollbar=self._scrollbar,
                responsive_classes=key,
                fonts=self._fonts,
                spacing=self._spacing,
                text=self._text,
                shape=self._shape,
                stroke=self._stroke,
                extra_css="\n".join(self._css),
            )
        return self._css_cache[key]

    # ── Introspection ───────────────────────────────────────────────────

    def dump(self, format: Literal["json", "python"] = "json") -> str:
        """Serialise the resolved theme — handy for debugging."""
        payload: dict[str, Any] = {
            "semantic": dict(self._semantic),
            "semantic_dark": dict(self._semantic_dark),
            "palette": dict(self._palette),
            "palette_dark": dict(self._palette_dark),
            "components": dict(self._components),
            "fonts": dict(self._fonts),
            "spacing": self._spacing,
            "text": dict(self._text),
            "shape": dict(self._shape),
            "stroke": self._stroke,
            "css": list(self._css),
            "scrollbar": dataclasses.asdict(self._scrollbar),
            "icons": dataclasses.asdict(self._icons),
        }
        if format == "json":
            return json.dumps(payload, indent=2, default=str, sort_keys=True)
        # Python repr — useful when the user wants to copy a snapshot
        # back into source code.
        return repr(payload)


# ───────────────────────────────────────────────────────────────────────────
# Internals
# ───────────────────────────────────────────────────────────────────────────


def _resolve_base(
    base: Theme | None | Literal['default'],
) -> Theme | None:
    """Resolve the ``base=`` argument into a concrete ``Theme | None``."""
    if base is None:
        return None
    if base == "default":
        return _default_theme()
    if isinstance(base, Theme):
        return base
    raise ThemeError(
        f"Unsupported ``base`` value : {base!r}. "
        "Expected None, 'default', or a Theme instance."
    )


_DEFAULT_THEME_INSTANCE: Theme | None = None


def _default_theme() -> Theme:
    """Lazy-construct the bundled default theme (cached after first call).

    Phase 1 builds it without component overrides — Layer 5 will land
    a ``presets/default.py`` aggregator that imports each component's
    theme dict and threads it through here.
    """
    global _DEFAULT_THEME_INSTANCE
    if _DEFAULT_THEME_INSTANCE is None:
        _DEFAULT_THEME_INSTANCE = Theme(
            base=None,
            semantic=DEFAULT_SEMANTIC_LIGHT,
            semantic_dark=DEFAULT_SEMANTIC_DARK,
            palette=DEFAULT_PALETTE,
            palette_dark=None,  # palette colors stay constant in dark
            components={},  # filled by presets/default.py once it ships
            scrollbar=ScrollbarConfig(),
            icons=IconConfig(),
        )
    return _DEFAULT_THEME_INSTANCE


def _section(base: Theme | None, attr: str) -> dict[str, Any]:
    """Read a section off the resolved base, defaulting to empty dict."""
    if base is None:
        return {}
    value = getattr(base, attr)
    return dict(value)


def _scalar(base: Theme | None, attr: str) -> str | None:
    """Read a scalar section off the resolved base, defaulting to None."""
    return None if base is None else getattr(base, attr)


def _section_tuple(base: Theme | None, attr: str) -> tuple[str, ...]:
    """Read a tuple section off the resolved base, defaulting to empty."""
    if base is None:
        return ()
    return tuple(getattr(base, attr))


def _merge_shape(
    base: Mapping[str, str], override: Mapping[str, str] | None
) -> dict[str, str]:
    """Merge shallow, **et refuse une famille inconnue** — même porte que
    :func:`_merge_fonts`, pour le même silence.

    ``Theme(shape={"card": "1rem"})`` n'est pas une extension : c'est un
    jeton que rien n'émettra et qu'aucune classe ne lira. Sans la garde,
    la section serait acceptée, le rayon ne bougerait pas, et il n'y
    aurait rien à voir.

    Le message nomme les trois familles ET dit où aller pour un
    composant seul, parce que c'est la question réelle derrière une clé
    inventée : « je veux juste arrondir mes cartes davantage ».
    """
    merged = {**DEFAULT_SHAPE, **base}
    if not override:
        return merged
    unknown = sorted(set(override) - set(SHAPE_SLOT_NAMES))
    if unknown:
        raise ThemeError(
            f"Theme(shape=…) : famille(s) inconnue(s) {unknown}. "
            f"Les trois familles sont {list(SHAPE_SLOT_NAMES)} — `box` pour "
            f"ce qui contient, `field` pour un contrôle qu'on vise, "
            f"`selector` pour une petite marque ou un contrôle imbriqué. "
            f"Pour le rayon d'UN composant, surcharge son thème : "
            f'Theme(components={{"card": {{"slots": {{"root": …}}}}}}).'
        )
    for slot, length in override.items():
        if not isinstance(length, str) or not length.strip():
            raise ThemeError(
                f"Theme(shape={{{slot!r}: {length!r}}}) : attendu une longueur "
                f'CSS non vide, par exemple "0.75rem" ou "0". Pour ne pas '
                f"surcharger cette famille, omets la clé."
            )
    merged.update(override)
    return merged


def _merge_spacing(base: str | None, override: str | None) -> str:
    """Le pas d'espacement : une chaîne, et elle peut rester absente.

    Absente, c'est :data:`DEFAULT_SPACING` qui sort — Bretzel CHOISIT son
    échelle au lieu d'hériter de celle de Tailwind, qui vise des pages.
    C'est l'inverse de la règle des fontes, et la différence est nette :
    recopier une valeur d'amont ne peut que diverger d'elle, en choisir
    une dit quelque chose.

    Une longueur CSS et non un nombre, pour la raison qui vaut déjà pour
    le trait : la valeur peut être ``3px``, ``0.1875rem`` ou ``0.2em``, et
    c'est le navigateur qui sait les multiplier là où nous devrions les
    parser.
    """
    if override is None:
        return base or DEFAULT_SPACING
    if not isinstance(override, str) or not override.strip():
        raise ThemeError(
            f"Theme(spacing={override!r}) : attendu une longueur CSS non "
            f'vide, par exemple "0.1875rem" (3 px, le défaut livré) ou '
            f'"0.25rem" (celui de Tailwind, soit une échelle de document). '
            f"Pour ne pas surcharger, omets le mot-clé."
        )
    return override.strip()


def _merge_text(
    base: Mapping[str, str], override: Mapping[str, str] | None
) -> dict[str, str]:
    """Les paliers de texte — mêmes gardes que les fontes, même raison.

    Un palier inconnu est refusé plutôt qu'ignoré : ``--text-md`` n'existe
    pas chez Tailwind, donc ``Theme(text={"md": "14px"})`` n'émettrait un
    jeton que personne ne lit — rien à voir, ni erreur, ni CSS, ni indice.
    C'est la famille de silences que la couche thème ferme à la porte
    depuis le 2026-08-16.

    ⚠️ ``base`` est le nom Tailwind du palier médian, là où le ``size=``
    d'un composant dit ``md``. Les deux échelles ne se confondent pas :
    celle-ci est celle des jetons CSS, celle-là est celle des paliers d'un
    composant, et c'est le thème du composant qui traduit l'une en
    l'autre (``"md": "text-base"``).
    """
    merged = {**DEFAULT_TEXT, **base}
    if not override:
        return merged
    unknown = sorted(set(override) - set(TEXT_SLOT_NAMES))
    if unknown:
        raise ThemeError(
            f"Theme(text=…) : palier(s) inconnu(s) {unknown}. Les paliers "
            f"sont {list(TEXT_SLOT_NAMES)} — ceux de Tailwind, donc les "
            f"seuls que les utilitaires `text-*` lisent. Attention : le "
            f"palier médian se dit `base`, pas `md` (`md` est un nom de "
            f"`size=`, pas un jeton CSS)."
        )
    for slot, size in override.items():
        if not isinstance(size, str) or not size.strip():
            raise ThemeError(
                f"Theme(text={{{slot!r}: {size!r}}}) : attendu une longueur "
                f'CSS non vide, par exemple "13px" ou "0.8125rem". Pour ne '
                f"pas surcharger ce palier, omets la clé."
            )
    merged.update({s: v.strip() for s, v in override.items()})
    return merged


def _merge_stroke(base: str | None, override: str | None) -> str:
    """La largeur de trait : une chaîne, pas un dict.

    Une seule valeur parce qu'il n'y a qu'une question — les deux autres
    crans en dérivent (cf. :data:`DEFAULT_STROKE`). La garde est la même
    que pour les fontes et les familles : une valeur vide ne peut vouloir
    dire que « je retire ma surcharge », et la façon de le dire est de ne
    pas écrire le mot-clé.
    """
    if override is None:
        return base or DEFAULT_STROKE
    if not isinstance(override, str) or not override.strip():
        raise ThemeError(
            f"Theme(stroke={override!r}) : attendu une longueur CSS non "
            f'vide, par exemple "1px" ou "0.5px". Pour ne pas surcharger, '
            f"omets le mot-clé. Pour un composant seul, surcharge son "
            f'thème : Theme(components={{"card": {{"slots": {{…}}}}}}).'
        )
    return override


def _merge_css(
    base: tuple[str, ...], css: str | Path | None
) -> tuple[str, ...]:
    """Ajoute le morceau de l'appelant à ceux de la base.

    Stocké en morceaux plutôt qu'en une chaîne recollée pour que la remise à
    zéro reste exprimable : une fois concaténé, on ne sait plus où finit la
    base. ``css=None`` hérite, ``css=""`` efface, tout le reste ajoute.
    """
    if css is None:
        return base
    chunk = _read_css(css).strip()
    if not chunk:
        return ()
    return (*base, chunk)


def _merge_fonts(
    base: Mapping[str, str], override: Mapping[str, str] | None
) -> dict[str, str]:
    """Merge shallow, **et refuse un slot inconnu**.

    Les trois slots sont ceux de Tailwind (:data:`FONT_SLOT_NAMES`), donc
    ``Theme(fonts={"body": …})`` n'est pas une extension : c'est un token
    que rien n'émettra et qu'aucune classe ne lira. Sans cette garde, la
    section serait acceptée, la fonte ne changerait pas, et il n'y aurait
    **rien à voir** — ni erreur, ni CSS, ni indice. C'est la famille de
    silences relevée le 2026-08-16 sur la couche thème (composant inconnu,
    slot mal orthographié, variante inexistante) ; celle-ci naît fermée
    plutôt que d'attendre sa règle de lint.

    Une famille vide (``{"sans": ""}``) est refusée par la même porte : la
    seule chose qu'elle puisse vouloir dire est « je retire ma
    surcharge », et la façon de le dire est de ne pas écrire la clé.
    """
    if not override:
        return dict(base)
    unknown = sorted(set(override) - set(FONT_SLOT_NAMES))
    if unknown:
        raise ThemeError(
            f"Theme(fonts=…) : slot(s) inconnu(s) {unknown}. "
            f"Les trois slots sont {list(FONT_SLOT_NAMES)} — ce sont ceux de "
            f"Tailwind, donc les seuls que les utilitaires `font-*` lisent. "
            f"Pour une fonte de titre distincte, surcharge le thème du "
            f'composant : Theme(components={{"heading": {{"slots": {{…}}}}}}).'
        )
    for slot, family in override.items():
        if not isinstance(family, str) or not family.strip():
            raise ThemeError(
                f"Theme(fonts={{{slot!r}: {family!r}}}) : attendu une valeur "
                f"CSS `font-family` non vide, par exemple "
                f'"Inter, ui-sans-serif, system-ui, sans-serif". Pour ne pas '
                f"surcharger ce slot, omets la clé."
            )
    # Le merge lui-même passe par ``_merge_dict``, le contrat des quatre
    # sections couleur : deux implémentations d'un merge plat à 40 lignes
    # d'écart finiraient par diverger, et c'est cette section-ci qui
    # garderait l'ancien comportement en silence.
    return _merge_dict(base, {s: f.strip() for s, f in override.items()})


def _read_css(css: str | Path) -> str:
    """Rend le CSS de ``Theme(css=…)`` — chaîne littérale ou fichier.

    Les deux formes existent parce que les deux usages existent : trois
    règles s'écrivent bien dans le source, une vraie feuille (``@font-face``
    + keyframes) veut un ``.css`` avec sa coloration syntaxique et son
    formateur. Le discriminant est le **type**, pas une heuristique sur le
    contenu — deviner qu'une chaîne « ressemble à un chemin » ferait
    dépendre le comportement de la présence d'une accolade.

    Un fichier absent LÈVE : le mode de défaillance qu'on refuse est
    précisément celui d'un style qui ne s'applique pas sans rien dire.
    """
    if isinstance(css, Path):
        try:
            return css.read_text(encoding="utf-8")
        except OSError as exc:
            raise ThemeError(
                f"Theme(css={str(css)!r}) : fichier illisible — {exc}. "
                f"Le chemin est résolu tel quel (relatif au dossier de "
                f"travail du processus, pas au module qui déclare le thème)."
            ) from exc
    if isinstance(css, str):
        return css
    raise ThemeError(
        f"Theme(css={css!r}) : attendu une chaîne CSS ou un `pathlib.Path` "
        f"vers un fichier `.css`."
    )


def _merge_dict(
    base: Mapping[str, Any], override: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Shallow merge — every key in ``override`` replaces the base
    entry at the top level. Used for color sections (the values are
    hex strings or tuples, not nested dicts)."""
    out = dict(base)
    if override:
        for k, v in override.items():
            out[k] = v
    return out


def _deep_merge_dicts(
    base: Mapping[str, Any], override: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Deep merge — for the components section where overrides describe
    nested ``{slots, variants, sizes}`` trees (cf. ``slots.py``)."""
    if not override:
        return dict(base)
    return merge_component_themes(dict(base), dict(override))


def _coerce_scrollbar(
    value: ScrollbarConfig | Mapping[str, Any] | None | object,
    fallback: ScrollbarConfig,
) -> ScrollbarConfig:
    if value is _UNSET:
        return fallback
    if value is None:
        return ScrollbarConfig()
    if isinstance(value, ScrollbarConfig):
        return value
    if isinstance(value, Mapping):
        # Allow ``{"width": "6px"}`` style overrides — fields not
        # mentioned fall through to the dataclass defaults.
        return dataclasses.replace(fallback, **dict(value))
    raise ThemeError(
        f"Unsupported scrollbar value : {value!r}. "
        "Expected ScrollbarConfig / mapping / None."
    )


def _coerce_icons(
    value: IconConfig | Mapping[str, Any] | None | object,
    fallback: IconConfig,
) -> IconConfig:
    if value is _UNSET:
        return fallback
    if value is None:
        return IconConfig()
    if isinstance(value, IconConfig):
        return value
    if isinstance(value, Mapping):
        return dataclasses.replace(fallback, **dict(value))
    raise ThemeError(
        f"Unsupported icons value : {value!r}. "
        "Expected IconConfig / mapping / None."
    )
