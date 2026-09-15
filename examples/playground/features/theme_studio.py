"""``/theme-studio`` — régler le thème en direct, et repartir avec le code.

Cette page ne pilote pas les composants : elle pilote **les entrées du
générateur**. On bouge les onze couleurs sémantiques — en clair ET en
sombre — les trois familles de rayon, l'épaisseur du trait et la densité ;
tout ce qui est en dessous se recalcule : les douze paliers, les vrais
composants de l'aperçu, et le mode sombre avec.

Pourquoi elle règle des VARIABLES et n'appelle aucun serveur
------------------------------------------------------------

Les paliers (``--bz-bg``, ``--bz-text``…) sont dérivés en CSS depuis
``--color-<nom>`` : changer la source suffit à repeindre toute la page,
et le navigateur le fait seul.

Et la sortie est du **code**, pas un état sauvé : le bloc du bas rend le
``Theme(...)`` à coller dans ``core/theme.py``. Git est la persistance.

⚠️ **Un ``<style>`` injecté, pas des styles INLINE** — et c'est la
correction du 2026-08-30. Écrire ``--color-primary`` en style inline sur
``<html>`` gagne contre TOUTES les règles, donc contre le bloc ``.dark``
du thème : dès qu'on touchait une couleur, le mode sombre cessait de
fonctionner pour elle. Une feuille injectée porte les deux règles,
``:root`` et ``.dark``, et la cascade retrouve son travail.

⚠️ **Ce qui se règle ici se règle À CHAUD. Le reste ne s'y trouve pas.**
Tailwind inline un nombre nu pour ``ring-2``, ``duration-150``, ``z-40``
— aucune variable ne les porte, donc aucun curseur ne peut les bouger
sans recompiler. Les mettre ici donnerait l'illusion du contraire.

Ce que la page n'a pas encore
------------------------------

- la typographie (``--font-sans`` + l'échelle ``--text-*``) ;
- le relief (``--shadow-*``), qui redevient réglable si son jeton est
  écrit depuis des ``var()`` — cf. le chantier.
"""

import json

from bretzel import ui
from bretzel.state import ClientExpression, ClientState, field
from bretzel.theme import SHAPE_SLOT_NAMES

PATH = "/theme-studio"

#: Les onze slots sémantiques : (nom, rôle, défaut clair, défaut sombre).
#: L'ordre est celui de la lecture — l'accent d'abord, les fonds ensuite.
SLOTS: list[tuple[str, str, str, str]] = [
    ("primary",    "l'accent de marque",           "#3a52b0", "#3a52b0"),
    ("secondary",  "l'accent secondaire",          "#9c3f72", "#9c3f72"),
    ("success",    "ce qui a réussi",              "#2f9e64", "#2f9e64"),
    ("warning",    "ce qui demande attention",     "#f0a91b", "#f0a91b"),
    ("error",      "ce qui a échoué",              "#e5484d", "#e5484d"),
    ("info",       "une information neutre",       "#0e9bc4", "#0e9bc4"),
    ("background", "le fond de la page",           "#fafafa", "#0a0a0a"),
    ("surface",    "le fond d'un panneau",         "#ffffff", "#151515"),
    ("interface",  "le remplissage d'un contrôle", "#f0f0f1", "#212121"),
    ("text",       "le texte courant",             "#171717", "#f5f5f5"),
    ("muted",      "le texte secondaire",          "#6b6b6e", "#a0a0a3"),
]

#: Les défauts de couleur, DÉRIVÉS de :data:`SLOTS` — le mode clair pour
#: le champ nu, le sombre pour son jumeau ``d_``.
#:
#: Ils étaient écrits deux fois : dans ``SLOTS`` pour l'affichage, et en
#: littéral sur chaque champ de la classe. Deux copies d'une même valeur
#: dérivent toujours, et celle-ci ne pouvait diverger qu'en SILENCE — la
#: page aurait montré une valeur et le store en aurait retenu une autre.
COLOR_DEFAULTS: dict[str, str] = {
    **{name: light for name, _role, light, _dark in SLOTS},
    **{f"d_{name}": dark for name, _role, _light, dark in SLOTS},
}

#: Les défauts des cinq curseurs. Ils n'ont pas de table d'affichage d'où
#: les tirer — leur tuple vit dans ``page()`` — donc ils sont ici, au même
#: endroit que les couleurs, et la classe les lit comme elle.
SLIDER_DEFAULTS: dict[str, float] = {
    "box": 0.75,
    "field_": 0.75,
    "selector": 0.375,
    "stroke": 1.0,
    "spacing": 0.1875,
}

#: Les vingt-sept valeurs livrées, d'un bloc. C'est ce que « Réinitialiser »
#: repose, et c'est la MÊME source que les défauts de la classe — donc le
#: bouton ne peut pas ramener à un troisième état.
SHIPPED_DEFAULTS: dict[str, str | float] = {**COLOR_DEFAULTS, **SLIDER_DEFAULTS}

PREVIEW_COLORS = ["primary", "success", "warning", "error", "info", "muted"]


class Studio(ClientState, persist="local"):
    """Les réglages. ``persist="local"`` : on retrouve son thème en
    revenant, sans que rien ne parte au serveur."""

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


#: Le MIROIR JavaScript de ``bretzel.theme.palette.resolve_color_pair``.
#:
#: Pourquoi il existe. Le foreground d'une couleur n'est pas « noir ou
#: blanc » : il est dérivé du fond — clarté choisie par un seuil de
#: luminance WCAG, puis TEINTÉ de la teinte du fond pour que la paire
#: reste d'un seul morceau. Cet algorithme vit en Python et tourne à la
#: génération du CSS. Le studio, lui, ne parle jamais au serveur : sans
#: ce miroir, choisir du blanc pour ``primary`` laissait le texte blanc
#: sur blanc, et aucun rechargement n'y changeait rien — la page ne
#: renvoie ses couleurs nulle part.
#:
#: Pourquoi c'est une DUPLICATION assumée. C'est le même arbitrage que
#: ``protocol.py`` ↔ ``runtime.js`` : le JS ne peut pas importer Python.
#: Et comme là-bas, la duplication est GATÉE — les six nombres de
#: l'algèbre sont nommés dans ``palette.py`` et
#: ``test_the_foreground_algebra_is_mirrored_in_js`` vérifie qu'ils
#: apparaissent ici.
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
    // Miroir de ``palette._readable_fg`` : la teinte RECULE jusqu'à ce
    // que AA (4.5) soit clos, et on s'arrête au premier cran suffisant.
    // Sans cette boucle, le studio rendrait un foreground différent de
    // celui que Python calcule sur les trois couleurs qui en avaient
    // besoin — muted, pink, plum — et personne ne le verrait, les deux
    // moitiés étant plausibles séparément.
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


#: ``(famille de rayon, champ du store)``.
#:
#: Les familles viennent de ``SHAPE_SLOT_NAMES``, le tuple du framework
#: dont ``Theme(shape=…)`` et la gate du rayon se servent déjà : une
#: quatrième famille ajoutée là-bas apparaît ici sans qu'on y touche.
#: La seule information PROPRE à cette page est le décalage de nom —
#: ``field`` est une fonction de ``bretzel.state``, donc le champ du
#: store s'appelle ``field_``.
#:
#: Écrit une fois : la feuille injectée et le code exporté doivent nommer
#: les mêmes familles, et deux listes en auraient nommé deux jeux
#: distincts au premier ajout.
SHAPE_FIELDS: tuple[tuple[str, str], ...] = tuple(
    (family, "field_" if family == "field" else family)
    for family in SHAPE_SLOT_NAMES
)


def path(name: str) -> str:
    """Le chemin JS d'un champ du store.

    Il est déterministe — classe, clé d'instance, champ — donc on le
    construit ici plutôt que de le redeviner dans chaque expression.
    """
    return f"$bz.state.Studio.default.{name}"


def reset_expression() -> str:
    """Le JS qui remet CHAQUE champ à la valeur LIVRÉE par le framework.

    Pourquoi ce bouton existe
    --------------------------
    ``Studio`` est ``persist="local"`` : les réglages survivent à la
    fermeture de l'onglet, ce qui est le bon défaut pour une page où l'on
    revient. Mais la conséquence n'avait pas de sortie — une fois qu'on y
    a touché, **plus rien ne ramène aux valeurs du framework**, pas même
    un rechargement, et repeindre le thème par défaut ne change rien à ce
    qu'on voit. Signalé le 2026-09-13 : la page affichait encore un rose
    ``#e93d82`` saisi des semaines plus tôt, pendant que le défaut livré
    était un indigo.

    Pourquoi il se construit depuis la CLASSE
    ------------------------------------------
    :data:`SHIPPED_DEFAULTS` est la table que les CHAMPS de ``Studio``
    lisent eux-mêmes : le bouton et le store ne peuvent donc pas diverger.
    Écrire la liste à la main ici la ferait dériver au premier curseur
    ajouté — et ce serait la dérive silencieuse habituelle : le bouton
    remettrait tout SAUF le nouveau réglage, ce qui ressemble à un bouton
    qui marche. La gate ``test_the_studio_exports_every_knob`` tient les
    deux bouts.
    """
    return "; ".join(
        f"{path(name)} = {json.dumps(valeur)}"
        for name, valeur in sorted(SHIPPED_DEFAULTS.items())
    )


def repaint_effect() -> str:
    """L'effet qui repeint la page, via une FEUILLE injectée.

    Il écrit un ``<style>`` unique portant ``:root { … }`` et
    ``.dark { … }``. C'est ce qui rend le mode sombre réglable : un style
    inline sur ``<html>`` gagnerait contre la règle ``.dark`` du thème et
    figerait la couleur dans les deux modes.

    La feuille est ajoutée en fin de ``<head>``, donc APRÈS celle du
    thème : à spécificité égale, l'ordre décide, et c'est la nôtre qui
    gagne.
    """
    def block(prefix: str) -> str:
        """Chaque source écrit sa PAIRE : le fond ET son foreground.

        Écrire le fond seul laissait ``--color-<nom>-foreground`` à la
        valeur calculée au démarrage par le serveur — donc du blanc sur
        blanc dès qu'on choisissait une couleur claire, sans qu'aucun
        rechargement n'y puisse rien.
        """
        return " + ".join(
            f"'--color-{name}:' + {path(prefix + name)} + ';'"
            f" + '--color-{name}-foreground:'"
            f" + window.bzFg({path(prefix + name)}) + ';'"
            for name, _role, _light, _dark in SLOTS
        )

    # Les TROIS familles, et rien d'autre. Cette ligne écrivait
    # ``--radius-sm/md/lg/xl`` depuis un seul curseur × quatre
    # facteurs — donc elle bougeait quatre jetons dont rien ne disait
    # pourquoi ils différaient. Depuis le 2026-08-30 le thème n'écrit
    # plus que ``rounded-box`` / ``rounded-field`` / ``rounded-selector``,
    # qui sont trois questions distinctes.
    radius = " + ".join(
        f"'--radius-{family}:' + {path(attr)} + 'rem;'"
        for family, attr in SHAPE_FIELDS
    )
    # Le trait : une seule base, les deux crans en dérivent. Écrire les
    # trois ici plutôt que la base seule aurait figé le rapport dans la
    # page au lieu de le laisser au `calc()` du thème.
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
    """Le champ, arrondi au millième.

    Un curseur au pas de 0,05 rend ``0.7500000000000001`` une fois sur
    vingt. Invisible dans une feuille injectée ; recopié tel quel dans le
    code exporté, où ça se voit.

    ⚠️ **Pourquoi ce n'est pas ``round(binding, 3)``.** Le framework émet
    exactement ce JS — ``ClientBinding.__round__`` rend la même chaîne au
    caractère près. Il n'est pas utilisable d'ici : ces émetteurs sont
    des fonctions de module, appelées sans contexte de rendu pour que la
    gate puisse les lire à l'import, et hors contexte ``Studio().box``
    rend un ``float``, pas un binding. Vérifié le 2026-08-31, pas
    supposé. C'est le même arbitrage qui justifie ``path()`` juste
    au-dessus.
    """
    return f"(Math.round({path(name)} * 1000) / 1000)"


def export_expression() -> str:
    """Le code à coller, en une seule expression pour ``bz-text``.

    Il porte TOUT ce que la page règle, et c'est le point : jusqu'au
    2026-08-31 il n'émettait que les vingt-deux couleurs. Les quatre
    curseurs de forme et celui de densité se réglaient, s'affichaient à
    l'écran, et disparaissaient à la copie — sans rien dire. C'est le
    pire mode d'échec d'un exportateur : une sortie plausible et
    incomplète. ``test_the_studio_exports_every_knob`` le garde.

    La densité sort en ``spacing=`` depuis le 2026-09-13. Elle passait par
    ``css="@theme { --spacing: … }"``, faute de paramètre à elle — le
    framework n'ouvrait pas la densité, au motif que chaque composant a
    déjà son ``size=``. Le motif tenait pour un MULTIPLICATEUR ; il ne
    tenait pas pour la base de l'échelle, que deux apps ont fini par
    déplacer à la main. Le code exporté reste vrai dans les deux formes,
    mais celle-ci est validée à la construction là où un bloc CSS était
    cru sur parole.
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
    """De VRAIS composants, pas des pastilles. C'est le seul moyen de
    voir qu'un palier casse."""
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
            "Les onze couleurs sémantiques dans les DEUX modes, les trois "
            "familles de rayon, le trait et la densité. Tout se recalcule "
            "dans le navigateur, sans un aller-retour serveur. La sortie "
            "est du CODE : le bloc du bas se colle dans core/theme.py.",
            color="muted",
        )
        ui.text(
            "Le sélecteur clair / sombre / système vit dans le pied de la "
            "barre latérale. Les deux colonnes de couleur restent "
            "éditables quel que soit le mode affiché.",
            color="muted", size="sm",
        )

        # ⚠️ Le bouton n'est pas un ornement : sans lui, ``persist="local"``
        # est un aller SANS retour. Il écrit les signaux en clair (une
        # chaîne ``on_click``, donc du client pur), et la persistance suit
        # — pas de requête, pas de rechargement.
        with ui.hstack(gap="sm", align="center", classes="flex-wrap"):
            ui.button(
                "Réinitialiser",
                icon_left="rotate-ccw",
                variant="outline",
                size="sm",
                on_click=reset_expression(),
            )
            ui.text(
                "remet les vingt-sept réglages aux valeurs livrées par le "
                "framework. Vos réglages sont gardés dans ce navigateur, "
                "donc ils survivent à un thème qui change de côté serveur.",
                size="xs", color="muted",
            )

        # ⚠️ UNE seule colonne, sur toute la largeur. La page a été
        # bâtie en deux colonnes côte à côte — les réglages à gauche, un
        # aperçu à droite — et les deux se disputaient la place : les
        # champs se serraient à 144 px pendant que l'aperçu était coupé.
        # Deux choses qui ont besoin de largeur ne se mettent pas côte à
        # côte ; elles se mettent l'une sous l'autre.
        ui.divider()
        ui.heading("Les sources", level=2)
        ui.text(
            "Vingt-deux valeurs saisies. Tout le reste en descend — les "
            "douze paliers de chaque couleur, dans les deux modes.",
            size="sm", color="muted",
        )
        # ``min_col`` EST ``repeat(auto-fit, minmax(20rem, 1fr))`` — la
        # primitive existe, je l'avais réécrite à la main en classe
        # arbitraire dans un ``ui.container``, qui porte en plus un
        # ``px-6 py-8`` par défaut : d'où les 24 px d'indentation que la
        # grille n'aurait jamais dû avoir.
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
            "Dans chaque paire : le mode clair à gauche, le sombre à "
            "droite.",
            size="xs", color="muted",
        )

        ui.divider()
        ui.heading("Les formes", level=2)
        ui.text(
            "Trois familles de rayon, parce que trois questions "
            "différentes : ce qui CONTIENT, ce qu'on TOUCHE, les petites "
            "MARQUES. Une seule échelle globale ne serait pas réglable — "
            "elle bougerait les trois du même geste.",
            size="sm", color="muted",
        )
        ui.text(
            "Ce qui NE bouge pas : le switch, le radio, le spinner et la "
            "barre de progression restent ronds. Leur rond est leur "
            "forme — un switch carré se lit comme une case à cocher.",
            size="xs", color="muted",
        )
        # L'unité vit dans le tuple. Elle était collée en
        # ``f"{label} (rem)"`` pour tout le monde, ce qui donnait
        # « l'épaisseur du trait (px) (rem) ».
        with ui.grid(min_col="16rem", gap="lg"):
            for label, unit, binding, lo, hi, step in (
                ("--radius-box · ce qui CONTIENT", "rem",
                 settings.box, 0.0, 2.0, 0.05),
                ("--radius-field · ce qu'on TOUCHE", "rem",
                 settings.field_, 0.0, 2.0, 0.05),
                ("--radius-selector · les petites MARQUES", "rem",
                 settings.selector, 0.0, 1.0, 0.025),
                ("--bz-stroke · l'épaisseur du trait", "px",
                 settings.stroke, 0.0, 4.0, 0.5),
                ("--spacing · la densité", "rem",
                 settings.spacing, 0.15, 0.4, 0.01),
            ):
                with ui.vstack(gap="none"):
                    ui.text(f"{label} ({unit})", size="xs",
                            color="muted", weight="medium")
                    ui.slider(value=binding, min=lo, max=hi,
                              step=step, size="sm")

        ui.divider()
        ui.heading("L'aperçu", level=2)
        ui.text(
            "De VRAIS composants, et rien d'autre. La page montrait "
            "aussi les douze paliers en pastilles : douze carrés sans "
            "étiquette, coupés par la colonne, illisibles en sombre — "
            "et surtout redondants. Un badge `soft` EST `--bz-bg`, un "
            "badge `outline` EST `--bz-border`, un bouton plein EST "
            "`--bz-solid` avec `--bz-on-solid` écrit dessus. Le "
            "composant dit la même chose et dit en plus si elle marche.",
            size="sm", color="muted",
        )
        with ui.grid(min_col="24rem", gap="md"):
            for color in PREVIEW_COLORS:
                component_preview(color)

        ui.divider()
        ui.heading("Le code à coller", level=2)
        ui.text(
            "Git est la persistance. Cette page est un générateur, pas "
            "un magasin de thèmes — ce qu'on règle à l'œil finit dans "
            "core/theme.py, versionné et relu.",
            color="muted", size="sm",
        )
        # ⚠️ ``ui.code`` et plus un ``ui.container`` habillé à la main.
        # Le bloc était un ``<div>`` portant sa propre pile de classes
        # ``font-mono … border … bg-interface`` : il ne ressemblait à
        # AUCUN autre bloc de code de l'app, et il ne pouvait pas suivre
        # le thème qu'il sert justement à régler. ``text`` est bindable,
        # donc une ``ClientExpression`` y passe — le composant émet un
        # ``<span bz-text>`` dans son ``<code>``.
        ui.code(ClientExpression(export_expression()), lang="python")
