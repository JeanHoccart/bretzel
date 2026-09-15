"""RÉFÉRENCE — Thème.

Ce que le thème règle, dans l'ordre où on s'en sert : les couleurs (rôles
et teintes), le clair/sombre, les formes et le trait, la typographie, la
structure d'un thème de composant, les deux portées de personnalisation,
et le cas d'un composant qui vient d'un paquet tiers.

⚠️ **Les listes sont lues EN DIRECT** — ``SEMANTIC_COLOR_NAMES``,
``DEFAULT_PALETTE_NAMES``, ``SHAPE_SLOT_NAMES``, ``FONT_SLOT_NAMES``, et
les paramètres de ``Theme`` par introspection de sa signature. La page ne
peut donc pas annoncer une couleur qui n'existe pas, ni oublier un
paramètre ajouté demain — c'est précisément ce qui lui était arrivé : elle
documentait trois paramètres sur douze, et il a fallu qu'on le remarque à
l'œil.
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

PATH = "/theme"

#: Ce que ``Theme(...)`` accepte, lu sur sa signature. Le tableau de la
#: page est construit à partir de ce tuple : un paramètre ajouté au
#: builder apparaît ici sans que personne ne touche ce fichier, et un
#: paramètre retiré disparaît au lieu de mentir.
THEME_PARAMS: tuple[str, ...] = tuple(inspect.signature(Theme).parameters)

#: La phrase de chaque paramètre. Écrite à la main — une signature dit le
#: NOM et le TYPE, jamais à quoi ça sert. La gate
#: ``test_the_theme_chapter_covers_every_theme_parameter`` vérifie que
#: les deux listes coïncident dans les deux sens, donc l'oubli est
#: impossible et la phrase orpheline aussi.
ROLES: dict[str, str] = {
    "semantic": f"Les {len(SEMANTIC_COLOR_NAMES)} rôles de couleur — "
                "`primary`, `error`, `surface`… Reteinte `primary` et "
                "toute l'app suit.",
    "semantic_dark": "Les mêmes rôles en mode sombre. Omis, un rôle garde "
                     "sa couleur claire — seules les surfaces ont une "
                     "valeur sombre livrée.",
    "palette": "Les teintes nommées et fixes (`green`, `sky`…), servies "
               "sous le préfixe `ui-` pour ne pas heurter Tailwind.",
    "palette_dark": "Les mêmes teintes en sombre.",
    "components": "Le thème d'un composant précis — ses slots, variants, "
                  "sizes, modifiers. Fusionné avec celui livré.",
    "fonts": f"Les {len(FONT_SLOT_NAMES)} familles "
             f"({', '.join(FONT_SLOT_NAMES)}) → `--font-<slot>`.",
    "spacing": "Le pas dont toute l'échelle d'espacement dérive : `h-10` "
               "vaut dix crans, comme `p-4` ou `gap-2`. Omis, celui de "
               "Tailwind (`0.25rem`) tient.",
    "text": f"Les {len(TEXT_SLOT_NAMES)} paliers de texte → `--text-<palier>`. "
            f"Le médian se dit `base`, pas `md` — `md` est un nom de `size=`.",
    "shape": f"Les {len(SHAPE_SLOT_NAMES)} familles de rayon "
             f"({', '.join(SHAPE_SLOT_NAMES)}) → `--radius-<famille>`.",
    "stroke": "La largeur de trait. UNE valeur : les deux autres crans en "
              "dérivent en `calc()` (`-strong` ×2, `-accent` ×4).",
    "css": "Un fichier CSS de l'app, injecté tel quel — c'est là que vit "
           "un `@font-face`, une `@keyframes`, un `@supports`.",
    "scrollbar": "Largeur et couleurs de la barre de défilement.",
    "icons": "Le jeu d'icônes par défaut, son style et sa taille.",
    "base": f"Le thème dont on hérite. `base=None` part de zéro — et vous "
            f"devenez responsable des {len(SEMANTIC_COLOR_NAMES)} rôles.",
}


def swatches(names: tuple[str, ...]) -> None:
    """Une rangée de pastilles solides.

    Chaque couleur est rendue dans sa propre teinte, avec son
    `foreground` auto-contrasté — donc lisible, y compris les neutres.
    """
    with ui.hstack(gap="xs", wrap=True):
        for name in names:
            ui.badge(name, color=name, variant="solid")


def roles_par_mode() -> None:
    """Quels rôles BASCULENT en sombre, et lesquels non — MESURÉ.

    ⚠️ Cette table était une phrase, et la phrase était fausse : elle
    disait « chaque rôle est dérivé du clair par contraste », alors que
    six rôles sur onze portent la MÊME couleur dans les deux modes. Ce
    qui est dérivé par contraste, c'est le ``foreground``, pas le fond.

    D'où une table qui interroge le thème livré au lieu de le raconter.
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
            ui.column("roles", label="Rôles"),
            ui.column("sombre", label="En sombre"),
        ],
        rows=[
            {"famille": "Marque et statut",
             "roles": ", ".join(stable),
             "sombre": "couleur INCHANGÉE — seul le foreground est recalculé"},
            {"famille": "Surfaces",
             "roles": ", ".join(bascule),
             "sombre": "couleur remplacée par sa valeur sombre"},
        ],
        size="sm",
    )


def parametres_table() -> None:
    """Les paramètres de ``Theme``, lus sur la signature."""
    ui.table(
        columns=[
            ui.column("param", label="Paramètre"),
            ui.column("role", label="Ce que ça règle"),
        ],
        rows=[
            {"param": nom, "role": ROLES.get(nom, "(non documenté)")}
            for nom in THEME_PARAMS
        ],
        size="sm",
    )


@page(PATH, layout=shell, title="Thème")
def theme_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Thème", level=1, size="3xl")
            ui.text(
                "Le thème porte l'identité visuelle : les couleurs, les "
                "formes, le trait, la typographie. Sous le capot c'est du "
                "Tailwind v4, compilé par un binaire Rust — aucun Node.js "
                "en production.",
                color="muted", size="lg",
            )

            # ── La vue d'ensemble, lue sur la signature ───────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(f"Les {len(THEME_PARAMS)} leviers", level=2)
                    ui.text(
                        "Tout se règle depuis un seul objet. On ne passe "
                        "que ce qu'on change ; le reste hérite du thème "
                        "livré.",
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
                    ui.heading("Tailwind sous le capot", level=2)
                    ui.text(
                        "Chaque composant compile en classes Tailwind v4. "
                        "Tu peux toujours ajouter les tiennes via "
                        "`classes=` — c'est l'échappatoire universelle, sur "
                        "n'importe quel composant. Tes classes sont posées "
                        "en dernier, donc elles gagnent en source order.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        'ui.button("Payer", classes="rounded-full px-8 shadow-lg")\n'
                        'ui.card(classes="border-2 border-dashed")\n'
                        '# du Tailwind brut : p-4, flex gap-2, hover:bg-…, etc.\n',
                        lang="python",
                    )
                    ui.alert(
                        "Une classe ASSEMBLÉE ne survit pas à la "
                        "production. `f\"bg-{couleur}-500\"` marche en dev "
                        "— le compilateur navigateur voit tout — et "
                        "disparaît en prod, où le binaire scanne des textes "
                        "littéraux. Le HTML est identique des deux côtés, "
                        "donc ça ne se voit QU'EN production. Écris la "
                        "classe entière, ou passe par le thème.",
                        color="warning",
                        title="Le piège qui ne casse qu'en prod",
                    )

            # ── 1. Couleurs sémantiques ───────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les couleurs sémantiques (rôles)", level=2)
                    ui.text(
                        f"{len(SEMANTIC_COLOR_NAMES)} slots de RÔLE. "
                        "Leur intérêt : ils se remappent avec le thème — "
                        "reteinte `primary` et toute l'app suit. On les "
                        "passe en `color=`.",
                        color="muted", size="sm",
                    )
                    swatches(SEMANTIC_COLOR_NAMES)
                    ui.code(
                        'ui.button("OK", color="primary")\n'
                        'ui.alert("Échec", color="error")\n',
                        lang="python",
                    )
                    ui.text(
                        "Foreground auto : chaque rôle a un "
                        "`<color>-foreground` dérivé par contraste — le "
                        "texte reste lisible sur le fond, en clair comme en "
                        "sombre.",
                        color="muted", size="sm",
                    )

            # ── 2. Couleurs palette ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les couleurs palette Bretzel (teintes)",
                               level=2)
                    ui.text(
                        f"{len(DEFAULT_PALETTE_NAMES)} teintes NOMMÉES ET "
                        "FIXES (pas des rôles — des couleurs concrètes). "
                        "Deux façons de les utiliser :",
                        color="muted", size="sm",
                    )
                    swatches(DEFAULT_PALETTE_NAMES)
                    ui.code(
                        '# 1) via color= — le framework réécrit avec le préfixe ui-\n'
                        'ui.badge("Nouveau", color="green")\n'
                        '#    → bg-ui-green text-ui-green-foreground\n'
                        '\n'
                        '# 2) via classes= directement (la forme explicite)\n'
                        'ui.badge("Nouveau", classes="bg-ui-green text-ui-green-foreground")\n',
                        lang="python",
                    )
                    ui.text(
                        "Le préfixe `ui-` évite le clash avec les "
                        "utilitaires stock de Tailwind (`bg-green-500`). Et "
                        "bien sûr, tout Tailwind classique reste dispo via "
                        "`classes=`.",
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
                        "Autrement dit : une couleur de marque NE CHANGE "
                        "PAS parce qu'on passe en sombre. Ce sont les "
                        "surfaces qui basculent, et ça suffit. Le "
                        "`foreground` de chaque rôle, lui, est TOUJOURS "
                        "recalculé par contraste — c'est pourquoi le texte "
                        "reste lisible dans les deux modes sans qu'on "
                        "écrive quoi que ce soit.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# Le mode courant se LIT comme un état d'ambiance.\n"
                        "from bretzel import ColorScheme\n"
                        "\n"
                        'ui.text(f"mode = {ColorScheme().mode}")   # light | dark | system\n'
                        "\n"
                        "# `semantic_dark=` ne sert QUE si la valeur du mode\n"
                        "# clair ne convient pas en sombre — un vert foncé sur\n"
                        "# fond sombre, par exemple.\n"
                        "Theme(\n"
                        '    semantic={"primary": "#14532d"},      # lisible en clair\n'
                        '    semantic_dark={"primary": "#4ade80"}, # …pas en sombre\n'
                        ")\n",
                        lang="python",
                    )
                    ui.text(
                        "Le mode est appliqué avant le premier pixel — pas "
                        "de flash blanc au chargement d'une page en sombre.",
                        color="muted", size="sm",
                    )

            # ── 4. Formes et trait ────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les formes et le trait", level=2)
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
                        "Theme(\n"
                        '    shape={"box": "1rem", "field": "0.5rem"},\n'
                        '    stroke="1.5px",   # -strong ×2, -accent ×4 en dérivent\n'
                        ")\n",
                        lang="python",
                    )
                    ui.text(
                        "Une famille inconnue LÈVE au démarrage, avec le "
                        "message qui dit les trois valides — un jeton "
                        "inventé ne serait lu par aucune classe, et le "
                        "rayon ne bougerait pas en silence.",
                        color="muted", size="sm",
                    )

            # ── 5. Typographie ────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("La typographie", level=2)
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
                        "Theme(\n"
                        '    fonts={"sans": "Inter, ui-sans-serif, system-ui, sans-serif"},\n'
                        '    css=Path("app/identity.css"),   # @font-face, keyframes\n'
                        ")\n",
                        lang="python",
                    )
                    ui.alert(
                        "Bretzel ne télécharge aucune fonte et n'écrit "
                        "aucun `<link>` vers un CDN tiers. La fonte se sert "
                        "depuis `Bretzel(static_dir=…)`, comme le reste des "
                        "assets — c'est la seule forme qui ne fasse pas "
                        "dépendre le rendu d'un tiers, ni ne fuite "
                        "l'adresse IP du visiteur.",
                        color="info", title="Pas de CDN, et c'est un choix",
                    )

            # ── 6. Structure d'un thème de composant ──────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("La structure d'un thème de composant",
                               level=2)
                    ui.text(
                        "Le thème d'un composant est UN SEUL DICT qui "
                        "range tout : le `root` et les autres `slots`, plus "
                        "les axes `variants` / `sizes` / `modifiers`.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# bretzel/components/feedback/badge/theme.py\n"
                        "BADGE_THEME = {\n"
                        '    "slots": {                    # root + slots nommés\n'
                        '        "root": "inline-flex items-center gap-1 …",\n'
                        '        "dot":  "shrink-0 rounded-full bg-current",\n'
                        "    },\n"
                        '    "variants": {                 # les PALIERS de couleur\n'
                        '        "soft":  "bg-(--bz-bg) text-(--bz-text)",\n'
                        '        "solid": "bg-(--bz-solid) text-(--bz-on-solid)",\n'
                        "    },\n"
                        '    "sizes": {                    # string OU dict multi-slot\n'
                        '        "sm": "px-2 py-0.5 text-xs",\n'
                        "    },\n"
                        '    "modifiers": {                # bool reactive_prop → classe\n'
                        '        "loading": "cursor-progress",\n'
                        "    },\n"
                        "}\n",
                        lang="python",
                    )
                    ui.text(
                        "`compose_class(\"root\")` assemble dans l'ordre : "
                        "le slot `root`, puis le `variant` actif, puis la "
                        "`size`, puis les `modifiers` truthy. Chaque clé du "
                        "dict a un rôle précis :",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("cle", label="Clé"),
                            ui.column("role", label="Rôle"),
                        ],
                        rows=[
                            {"cle": "slots", "role": "les morceaux du composant "
                                                     "(`root` + slots nommés)"},
                            {"cle": "variants", "role": "styles alternatifs — "
                                                        "une valeur active à la fois"},
                            {"cle": "sizes", "role": "tailles — une valeur active "
                                                     "à la fois"},
                            {"cle": "modifiers", "role": "flags bool — plusieurs "
                                                         "cumulables en même temps"},
                        ],
                        size="sm",
                    )

            # ── 7. Personnaliser ──────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Personnaliser — global ou local", level=2)
                    ui.text(
                        "Deux portées, et elles ne se composent pas de la "
                        "même façon : le thème central REDÉFINIT "
                        "l'entrée qu'il nomme, une surcharge d'instance "
                        "S'AJOUTE à celle du thème.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("portee", label="Portée"),
                            ui.column("comment", label="Comment"),
                        ],
                        rows=[
                            {"portee": "Global (toute l'app)",
                             "comment": "Bretzel(theme=Theme(components={…}, "
                                        "semantic={…}, shape={…}))"},
                            {"portee": "Local (une instance)",
                             "comment": "ui.button(classes=\"…\") ou "
                                        "ui.button(slots={\"root\": \"…\"})"},
                        ],
                        size="sm",
                    )
                    ui.code(
                        "from bretzel.theme import Theme\n"
                        "\n"
                        "# GLOBAL — s'applique à tous les Button de l'app.\n"
                        "# Une entrée fournie ici REDÉFINIT cette entrée du thème\n"
                        "# livré (chaîne complète) ; le reste (slots, variants,\n"
                        "# sizes) est préservé par fusion.\n"
                        "app = Bretzel(theme=Theme(\n"
                        '    semantic={"primary": "#27754a"},\n'
                        '    components={"button": {"sizes": {"md": "h-11 px-5 text-sm gap-2"}}},\n'
                        "))\n"
                        "\n"
                        "# LOCAL — seulement ce Button-ci : la chaîne S'AJOUTE au slot.\n"
                        'ui.button("Un seul", slots={"root": "rounded-2xl"})\n',
                        lang="python",
                    )

            # ── 8. Un paquet tiers ────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Thémer un composant qui vient d'ailleurs",
                               level=2)
                    ui.text(
                        "Une bibliothèque tierce peut publier ses "
                        "composants pour qu'ils deviennent thémables comme "
                        "ceux du framework — sinon il ne resterait que "
                        "`classes=` au point d'appel, répété partout, sans "
                        "cascade ni cohérence de mode sombre.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# pyproject.toml du paquet tiers\n"
                        '[project.entry-points."bretzel.scan_roots"]\n'
                        'mes-composants = "mes_composants"   # balaie mes fichiers\n'
                        "\n"
                        '[project.entry-points."bretzel.components"]\n'
                        'mes-composants = "mes_composants"   # charge mon code\n'
                        "\n"
                        "# Et dans l'app qui l'installe :\n"
                        'Theme(components={"gauge": {"slots": {"root": "…"}}})\n',
                        lang="text",
                    )
                    ui.text(
                        "Deux déclarations parce que ce sont deux contrats "
                        "différents : « balaie mes fichiers » n'est pas "
                        "« charge mon code ». Une clé qui heurterait celle "
                        "d'un composant du framework est REFUSÉE au "
                        "démarrage — sinon l'app croirait styler l'un et "
                        "stylerait l'autre.",
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.hstack(align="baseline", gap="sm", wrap=True):
                    ui.text("Le contrat exact par composant (slots, "
                            "variants, sizes disponibles) :",
                            color="muted", size="sm")
                    ui.link("Catalogue ui.* →", href="/components")
