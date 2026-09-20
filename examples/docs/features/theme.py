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
    FONT_SLOT_NAMES,
    SEMANTIC_COLOR_NAMES,
    SHAPE_SLOT_NAMES,
    TEXT_SLOT_NAMES,
    Theme,
)

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

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
    "semantic": f"Les {len(SEMANTIC_COLOR_NAMES)} rôles de couleur — "
                "`primary`, `error`, `surface`… Reteinte `primary` et "
                "toute l'app suit.",
    "semantic_dark": tr('The same roles in dark mode. Omitted, a role keeps '
                        'its light colour — only the surfaces have a dark '
                        'value shipped.',
                        'Les mêmes rôles en mode sombre. Omis, un rôle garde '
                        'sa couleur claire — seules les surfaces ont une '
                        'valeur sombre livrée.'),
    "palette": tr('The named, fixed shades (`green`, `sky`…), served under '
                  'the `ui-` prefix so as not to collide with Tailwind.',
                  'Les teintes nommées et fixes (`green`, `sky`…), servies '
                  'sous le préfixe `ui-` pour ne pas heurter Tailwind.'),
    "palette_dark": tr('The same shades in dark mode.',
                       'Les mêmes teintes en sombre.'),
    "components": tr('The theme of one precise component — its slots, '
                     'variants, sizes, modifiers. Merged with the shipped '
                     'one.',
                     "Le thème d'un composant précis — ses slots, variants, "
                     'sizes, modifiers. Fusionné avec celui livré.'),
    "fonts": f"Les {len(FONT_SLOT_NAMES)} familles "
             f"({', '.join(FONT_SLOT_NAMES)}) → `--font-<slot>`.",
    "spacing": tr('The step the whole spacing scale derives from: `h-10` is '
                  "ten notches, like `p-4` or `gap-2`. Omitted, Tailwind's "
                  '(`0.25rem`) holds.',
                  "Le pas dont toute l'échelle d'espacement dérive : `h-10` "
                  'vaut dix crans, comme `p-4` ou `gap-2`. Omis, celui de '
                  'Tailwind (`0.25rem`) tient.'),
    "text": f"Les {len(TEXT_SLOT_NAMES)} paliers de texte → `--text-<palier>`. "
            f"Le médian se dit `base`, pas `md` — `md` est un nom de `size=`.",
    "shape": f"Les {len(SHAPE_SLOT_NAMES)} familles de rayon "
             f"({', '.join(SHAPE_SLOT_NAMES)}) → `--radius-<famille>`.",
    "stroke": tr('The stroke width. ONE value: the two other steps derive '
                 'from it in `calc()` (`-strong` ×2, `-accent` ×4).',
                 'La largeur de trait. UNE valeur : les deux autres crans en '
                 'dérivent en `calc()` (`-strong` ×2, `-accent` ×4).'),
    "css": tr("A CSS file of the app's, injected as is — that is where a "
              '`@font-face`, a `@keyframes`, a `@supports` lives.',
              "Un fichier CSS de l'app, injecté tel quel — c'est là que vit "
              'un `@font-face`, une `@keyframes`, un `@supports`.'),
    "scrollbar": tr("The scrollbar's width and colours.",
                    'Largeur et couleurs de la barre de défilement.'),
    "icons": tr('The default icon set, its style and its size.',
                "Le jeu d'icônes par défaut, son style et sa taille."),
    "base": f"Le thème dont on hérite. `base=None` part de zéro — et vous "
            f"devenez responsable des {len(SEMANTIC_COLOR_NAMES)} rôles.",
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
            ui.column("famille", label="Famille"),
            ui.column("roles", label=tr('Roles',
                                        'Rôles')),
            ui.column("sombre", label="En sombre"),
        ],
        rows=[
            {"famille": "Marque et statut",
             "roles": ", ".join(stable),
             "sombre": tr('colour UNCHANGED — only the foreground is '
                          'recomputed',
                          'couleur INCHANGÉE — seul le foreground est '
                          'recalculé')},
            {"famille": "Surfaces",
             "roles": ", ".join(bascule),
             "sombre": tr('colour replaced by its dark value',
                          'couleur remplacée par sa valeur sombre')},
        ],
        size="sm",
    )


def parametres_table() -> None:
    """``Theme``'s parameters, read from the signature."""
    ui.table(
        columns=[
            ui.column("param", label=tr('Parameter',
                                        'Paramètre')),
            ui.column("role", label=tr('What it settles',
                                       'Ce que ça règle')),
        ],
        rows=[
            {"param": nom, "role": ROLES.get(nom, tr('(undocumented)',
                                                     '(non documenté)'))}
            for nom in THEME_PARAMS
        ],
        size="sm",
    )


@page(PATH, layout=shell, title=tr('Theme',
                                   'Thème'))
def theme_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Theme',
                          'Thème'), level=1, size="3xl")
            ui.text(
                tr('The theme carries the visual identity: the colours, the '
                   'shapes, the stroke, the typography. Under the bonnet it '
                   'is Tailwind v4, compiled by a Rust binary — no Node.js in'
                   ' production.',
                   "Le thème porte l'identité visuelle : les couleurs, les "
                   "formes, le trait, la typographie. Sous le capot c'est du "
                   'Tailwind v4, compilé par un binaire Rust — aucun Node.js '
                   'en production.'),
                color="muted", size="lg",
            )

            # ── The overview, read from the signature ─────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(f"Les {len(THEME_PARAMS)} leviers", level=2)
                    ui.text(
                        tr('Everything is set from a single object. One '
                           'passes only what one changes; the rest inherits '
                           'the shipped theme.',
                           'Tout se règle depuis un seul objet. On ne passe '
                           "que ce qu'on change ; le reste hérite du thème "
                           'livré.'),
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
                    ui.heading(tr('Tailwind under the bonnet',
                                  'Tailwind sous le capot'), level=2)
                    ui.text(
                        tr('Every component compiles into Tailwind v4 '
                           'classes. You can always add your own through '
                           '`classes=` — it is the universal escape hatch, on'
                           ' any component. Your classes are placed last, so '
                           'they win on source order.',
                           'Chaque composant compile en classes Tailwind v4. '
                           'Tu peux toujours ajouter les tiennes via '
                           "`classes=` — c'est l'échappatoire universelle, "
                           "sur n'importe quel composant. Tes classes sont "
                           'posées en dernier, donc elles gagnent en source '
                           'order.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('ui.button("Pay", classes="rounded-full px-8 shadow-lg")\nui.card(classes="border-2 border-dashed")\n# raw Tailwind: p-4, flex gap-2, hover:bg-…, etc.\n',
                           'ui.button("Payer", classes="rounded-full px-8 shadow-lg")\nui.card(classes="border-2 border-dashed")\n# du Tailwind brut : p-4, flex gap-2, hover:bg-…, etc.\n'),
                        lang="python",
                    )
                    ui.alert(
                        tr('An ASSEMBLED class does not survive production. '
                           '`f"bg-{colour}-500"` works in dev — the browser '
                           'compiler sees everything — and disappears in '
                           'production, where the binary scans literal text. '
                           'The HTML is identical on both sides, so it only '
                           'shows IN production. Write the whole class, or go'
                           ' through the theme.',
                           'Une classe ASSEMBLÉE ne survit pas à la '
                           'production. `f"bg-{couleur}-500"` marche en dev —'
                           ' le compilateur navigateur voit tout — et '
                           'disparaît en prod, où le binaire scanne des '
                           'textes littéraux. Le HTML est identique des deux '
                           "côtés, donc ça ne se voit QU'EN production. Écris"
                           ' la classe entière, ou passe par le thème.'),
                        color="warning",
                        title=tr('The trap that only breaks in production',
                                 "Le piège qui ne casse qu'en prod"),
                    )

            # ── 1. Semantic colours ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The semantic colours (roles)',
                                  'Les couleurs sémantiques (rôles)'), level=2)
                    ui.text(
                        f"{len(SEMANTIC_COLOR_NAMES)} slots de RÔLE. "
                        "Leur intérêt : ils se remappent avec le thème — "
                        "reteinte `primary` et toute l'app suit. On les "
                        "passe en `color=`.",
                        color="muted", size="sm",
                    )
                    swatches(SEMANTIC_COLOR_NAMES)
                    ui.code(
                        tr('ui.button("OK", color="primary")\nui.alert("Failed", color="error")\n',
                           'ui.button("OK", color="primary")\nui.alert("Échec", color="error")\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('Automatic foreground: every role has a '
                           '`<color>-foreground` derived by contrast — the '
                           'text stays readable on the background, in light '
                           'as in dark.',
                           'Foreground auto : chaque rôle a un '
                           '`<color>-foreground` dérivé par contraste — le '
                           'texte reste lisible sur le fond, en clair comme '
                           'en sombre.'),
                        color="muted", size="sm",
                    )

            # ── 2. Couleurs palette ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The Bretzel palette colours (shades)',
                                  'Les couleurs palette Bretzel (teintes)'),
                               level=2)
                    ui.text(
                        f"{len(DEFAULT_PALETTE_NAMES)} teintes NOMMÉES ET "
                        "FIXES (pas des rôles — des couleurs concrètes). "
                        "Deux façons de les utiliser :",
                        color="muted", size="sm",
                    )
                    swatches(DEFAULT_PALETTE_NAMES)
                    ui.code(
                        tr('# 1) through color= — the framework rewrites with the ui- prefix\nui.badge("New", color="green")\n#    → bg-ui-green text-ui-green-foreground\n\n# 2) through classes= directly (the explicit form)\nui.badge("New", classes="bg-ui-green text-ui-green-foreground")\n',
                           '# 1) via color= — le framework réécrit avec le préfixe ui-\nui.badge("Nouveau", color="green")\n#    → bg-ui-green text-ui-green-foreground\n\n# 2) via classes= directement (la forme explicite)\nui.badge("Nouveau", classes="bg-ui-green text-ui-green-foreground")\n'),
                        lang="python",
                    )
                    ui.text(
                        tr("The `ui-` prefix avoids clashing with Tailwind's "
                           'stock utilities (`bg-green-500`). And of course '
                           'all the usual Tailwind stays available through '
                           '`classes=`.',
                           'Le préfixe `ui-` évite le clash avec les '
                           'utilitaires stock de Tailwind (`bg-green-500`). '
                           'Et bien sûr, tout Tailwind classique reste dispo '
                           'via `classes=`.'),
                        color="muted", size="sm",
                    )

            # ── 3. Clair et sombre ────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Clair et sombre", level=2)
                    ui.text(
                        f"Les {len(SEMANTIC_COLOR_NAMES)} rôles ne se "
                        "comportent pas pareil quand on éteint la lumière, "
                        "et la coupure est nette — mesurée sur le thème "
                        "livré, pas décrite de mémoire :",
                        color="muted", size="sm",
                    )
                    roles_par_mode()
                    ui.text(
                        tr('In other words: a brand colour does NOT change '
                           'because one switches to dark. It is the surfaces '
                           "that flip, and that is enough. Every role's "
                           '`foreground`, for its part, is ALWAYS recomputed '
                           'by contrast — which is why the text stays '
                           'readable in both modes without anyone writing '
                           'anything.',
                           'Autrement dit : une couleur de marque NE CHANGE '
                           "PAS parce qu'on passe en sombre. Ce sont les "
                           'surfaces qui basculent, et ça suffit. Le '
                           '`foreground` de chaque rôle, lui, est TOUJOURS '
                           "recalculé par contraste — c'est pourquoi le texte"
                           " reste lisible dans les deux modes sans qu'on "
                           'écrive quoi que ce soit.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('# The current mode READS like an ambient state.\nfrom bretzel import ColorScheme\n\nui.text(f"mode = {ColorScheme().mode}")   # light | dark | system\n\n# `semantic_dark=` is ONLY needed if the light mode\'s\n# value does not work in dark — a dark green on a dark\n# background, for instance.\nTheme(\n    semantic={"primary": "#14532d"},      # readable in light\n    semantic_dark={"primary": "#4ade80"}, # …not in dark\n)\n',
                           '# Le mode courant se LIT comme un état d\'ambiance.\nfrom bretzel import ColorScheme\n\nui.text(f"mode = {ColorScheme().mode}")   # light | dark | system\n\n# `semantic_dark=` ne sert QUE si la valeur du mode\n# clair ne convient pas en sombre — un vert foncé sur\n# fond sombre, par exemple.\nTheme(\n    semantic={"primary": "#14532d"},      # lisible en clair\n    semantic_dark={"primary": "#4ade80"}, # …pas en sombre\n)\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('The mode is applied before the first pixel — no '
                           'white flash when loading a page in dark mode.',
                           'Le mode est appliqué avant le premier pixel — pas'
                           " de flash blanc au chargement d'une page en "
                           'sombre.'),
                        color="muted", size="sm",
                    )

            # ── 4. Formes et trait ────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The shapes and the stroke',
                                  'Les formes et le trait'), level=2)
                    ui.text(
                        "Les rayons se règlent par FAMILLE, pas par "
                        "composant : "
                        f"{', '.join('`' + s + '`' for s in SHAPE_SLOT_NAMES)}. "
                        "`box` pour ce qui contient, `field` pour un "
                        "contrôle qu'on vise, `selector` pour une petite "
                        "marque ou un contrôle imbriqué.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('Theme(\n    shape={"box": "1rem", "field": "0.5rem"},\n    stroke="1.5px",   # -strong ×2, -accent ×4 derive from it\n)\n',
                           'Theme(\n    shape={"box": "1rem", "field": "0.5rem"},\n    stroke="1.5px",   # -strong ×2, -accent ×4 en dérivent\n)\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('An unknown family RAISES at startup, with the '
                           'message naming the three valid ones — an invented'
                           ' token would be read by no class, and the radius '
                           'would not move, in silence.',
                           'Une famille inconnue LÈVE au démarrage, avec le '
                           'message qui dit les trois valides — un jeton '
                           'inventé ne serait lu par aucune classe, et le '
                           'rayon ne bougerait pas en silence.'),
                        color="muted", size="sm",
                    )

            # ── 5. Typographie ────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Typography',
                                  'La typographie'), level=2)
                    ui.text(
                        f"`fonts=` déclare la famille pour les "
                        f"{len(FONT_SLOT_NAMES)} slots "
                        f"({', '.join(FONT_SLOT_NAMES)}) ; `css=` porte le "
                        "`@font-face` qui la rend disponible. Ce sont les "
                        "deux moitiés d'une même question : QUOI "
                        "charger, et COMMENT.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('Theme(\n    fonts={"sans": "Inter, ui-sans-serif, system-ui, sans-serif"},\n    css=Path("app/identity.css"),   # @font-face, keyframes\n)\n',
                           'Theme(\n    fonts={"sans": "Inter, ui-sans-serif, system-ui, sans-serif"},\n    css=Path("app/identity.css"),   # @font-face, keyframes\n)\n'),
                        lang="python",
                    )
                    ui.alert(
                        tr('Bretzel downloads no font and writes no `<link>` '
                           'to a third-party CDN. The font is served from '
                           '`Bretzel(static_dir=…)`, like the rest of the '
                           'assets — it is the only form that makes the '
                           'rendering depend on nobody else, and leaks no '
                           "visitor's IP address.",
                           "Bretzel ne télécharge aucune fonte et n'écrit "
                           'aucun `<link>` vers un CDN tiers. La fonte se '
                           'sert depuis `Bretzel(static_dir=…)`, comme le '
                           "reste des assets — c'est la seule forme qui ne "
                           "fasse pas dépendre le rendu d'un tiers, ni ne "
                           "fuite l'adresse IP du visiteur."),
                        color="info", title=tr('No CDN, and that is a choice',
                                               "Pas de CDN, et c'est un choix"),
                    )

            # ── 6. A component theme's structure ──────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The structure of a component theme',
                                  "La structure d'un thème de composant"),
                               level=2)
                    ui.text(
                        tr("A component's theme is ONE SINGLE DICT holding "
                           'everything: the `root` and the other `slots`, '
                           'plus the `variants` / `sizes` / `modifiers` axes.',
                           "Le thème d'un composant est UN SEUL DICT qui "
                           'range tout : le `root` et les autres `slots`, '
                           'plus les axes `variants` / `sizes` / `modifiers`.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('# bretzel/components/feedback/badge/theme.py\nBADGE_THEME = {\n    "slots": {                    # root + named slots\n        "root": "inline-flex items-center gap-1 …",\n        "dot":  "shrink-0 rounded-full bg-current",\n    },\n    "variants": {                 # the colour STEPS\n        "soft":  "bg-(--bz-bg) text-(--bz-text)",\n        "solid": "bg-(--bz-solid) text-(--bz-on-solid)",\n    },\n    "sizes": {                    # a string OR a multi-slot dict\n        "sm": "px-2 py-0.5 text-xs",\n    },\n    "modifiers": {                # a bool reactive_prop → a class\n        "loading": "cursor-progress",\n    },\n}\n',
                           '# bretzel/components/feedback/badge/theme.py\nBADGE_THEME = {\n    "slots": {                    # root + slots nommés\n        "root": "inline-flex items-center gap-1 …",\n        "dot":  "shrink-0 rounded-full bg-current",\n    },\n    "variants": {                 # les PALIERS de couleur\n        "soft":  "bg-(--bz-bg) text-(--bz-text)",\n        "solid": "bg-(--bz-solid) text-(--bz-on-solid)",\n    },\n    "sizes": {                    # string OU dict multi-slot\n        "sm": "px-2 py-0.5 text-xs",\n    },\n    "modifiers": {                # bool reactive_prop → classe\n        "loading": "cursor-progress",\n    },\n}\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('`compose_class("root")` assembles in order: the '
                           '`root` slot, then the active `variant`, then the '
                           '`size`, then the truthy `modifiers`. Every key of'
                           ' the dict has a precise role:',
                           '`compose_class("root")` assemble dans l\'ordre : '
                           'le slot `root`, puis le `variant` actif, puis la '
                           '`size`, puis les `modifiers` truthy. Chaque clé '
                           'du dict a un rôle précis :'),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("cle", label=tr('Key',
                                                      'Clé')),
                            ui.column("role", label=tr('Role',
                                                       'Rôle')),
                        ],
                        rows=[
                            {"cle": "slots", "role": tr("the component's pieces (`root`"
                                                        ' + named slots)',
                                                        'les morceaux du composant '
                                                        '(`root` + slots nommés)')},
                            {"cle": "variants", "role": tr('alternative styles — one '
                                                           'active value at a time',
                                                           'styles alternatifs — une '
                                                           'valeur active à la fois')},
                            {"cle": "sizes", "role": tr('sizes — one active value at a '
                                                        'time',
                                                        'tailles — une valeur active à '
                                                        'la fois')},
                            {"cle": "modifiers", "role": tr('bool flags — several can be on'
                                                            ' at once',
                                                            'flags bool — plusieurs '
                                                            'cumulables en même temps')},
                        ],
                        size="sm",
                    )

            # ── 7. Personnaliser ──────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Personnaliser — global ou local", level=2)
                    ui.text(
                        tr('Two scopes, and they do not compose the same way:'
                           ' the central theme REDEFINES the entry it names, '
                           "an instance override is ADDED to the theme's.",
                           'Deux portées, et elles ne se composent pas de la '
                           "même façon : le thème central REDÉFINIT l'entrée "
                           "qu'il nomme, une surcharge d'instance S'AJOUTE à "
                           'celle du thème.'),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("portee", label=tr('Scope',
                                                         'Portée')),
                            ui.column("comment", label="Comment"),
                        ],
                        rows=[
                            {"portee": "Global (toute l'app)",
                             "comment": "Bretzel(theme=Theme(components={…}, "
                                        "semantic={…}, shape={…}))"},
                            {"portee": tr('Local (one instance)',
                                          'Local (une instance)'),
                             "comment": "ui.button(classes=\"…\") ou "
                                        "ui.button(slots={\"root\": \"…\"})"},
                        ],
                        size="sm",
                    )
                    ui.code(
                        tr('from bretzel.theme import Theme\n\n# GLOBAL — applies to every Button in the app.\n# An entry supplied here REDEFINES that entry of the\n# shipped theme (the whole string); the rest (slots,\n# variants, sizes) is preserved by merging.\napp = Bretzel(theme=Theme(\n    semantic={"primary": "#27754a"},\n    components={"button": {"sizes": {"md": "h-11 px-5 text-sm gap-2"}}},\n))\n\n# LOCAL — this Button only: the string is ADDED to the slot.\nui.button("Just this one", slots={"root": "rounded-2xl"})\n',
                           'from bretzel.theme import Theme\n\n# GLOBAL — s\'applique à tous les Button de l\'app.\n# Une entrée fournie ici REDÉFINIT cette entrée du thème\n# livré (chaîne complète) ; le reste (slots, variants,\n# sizes) est préservé par fusion.\napp = Bretzel(theme=Theme(\n    semantic={"primary": "#27754a"},\n    components={"button": {"sizes": {"md": "h-11 px-5 text-sm gap-2"}}},\n))\n\n# LOCAL — seulement ce Button-ci : la chaîne S\'AJOUTE au slot.\nui.button("Un seul", slots={"root": "rounded-2xl"})\n'),
                        lang="python",
                    )

            # ── 8. Un paquet tiers ────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Theming a component that comes from '
                                  'elsewhere',
                                  "Thémer un composant qui vient d'ailleurs"),
                               level=2)
                    ui.text(
                        tr('A third-party library can publish its components '
                           "so they become themable like the framework's — "
                           'otherwise all that would be left is `classes=` at'
                           ' the call site, repeated everywhere, with no '
                           'cascade and no dark-mode coherence.',
                           'Une bibliothèque tierce peut publier ses '
                           "composants pour qu'ils deviennent thémables comme"
                           ' ceux du framework — sinon il ne resterait que '
                           "`classes=` au point d'appel, répété partout, sans"
                           ' cascade ni cohérence de mode sombre.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('# the third-party package\'s pyproject.toml\n[project.entry-points."bretzel.scan_roots"]\nmy-components = "my_components"     # sweep my files\n\n[project.entry-points."bretzel.components"]\nmy-components = "my_components"     # load my code\n\n# And in the app that installs it:\nTheme(components={"gauge": {"slots": {"root": "…"}}})\n',
                           '# pyproject.toml du paquet tiers\n[project.entry-points."bretzel.scan_roots"]\nmes-composants = "mes_composants"   # balaie mes fichiers\n\n[project.entry-points."bretzel.components"]\nmes-composants = "mes_composants"   # charge mon code\n\n# Et dans l\'app qui l\'installe :\nTheme(components={"gauge": {"slots": {"root": "…"}}})\n'),
                        lang="text",
                    )
                    ui.text(
                        tr('Two declarations because they are two different '
                           'contracts: “sweep my files” is not “load my '
                           'code”. A key colliding with a framework '
                           "component's is REFUSED at startup — otherwise the"
                           ' app would think it was styling one and would '
                           'style the other.',
                           'Deux déclarations parce que ce sont deux contrats'
                           " différents : « balaie mes fichiers » n'est pas «"
                           ' charge mon code ». Une clé qui heurterait celle '
                           "d'un composant du framework est REFUSÉE au "
                           "démarrage — sinon l'app croirait styler l'un et "
                           "stylerait l'autre."),
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.hstack(align="baseline", gap="sm", wrap=True):
                    ui.text(tr('The exact contract per component (slots, '
                               'variants, sizes available):',
                               'Le contrat exact par composant (slots, '
                               'variants, sizes disponibles) :'),
                            color="muted", size="sm")
                    ui.link("Catalogue ui.* →", href="/components")
