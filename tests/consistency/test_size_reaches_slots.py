"""Gate : `size=` doit atteindre TOUS les slots qui portent une taille.

Un composant à slot unique reçoit `size` gratuitement : `compose_class`
lit `theme["sizes"][<size>]`, voit une **string**, et l'append à la root
([component.py] étape 3). Rien à câbler.

Un composant multi-slots range un **dict** par size — et là le composeur
fait `if isinstance(size_classes, str)` puis **passe en silence** (cf.
traps.md § "Substitution `{bg_color}` sur un dict de slot"). C'est au
`render()` de lire le dict et de composer slot par slot. Donc `size`
n'atteint que les slots que l'auteur a (1) tapés dans la table ET (2)
re-câblés dans `render()`. En oublier un n'est pas une erreur : c'est un
no-op. Aucun test ne pouvait s'en apercevoir — d'où cette gate.

Symptôme observé (juillet 2026) : `ui.combobox(size="xl")` grossissait le
trigger et les options, mais gardait des pills Badge `sm`, un chevron
`sm`, un `max-h-60` de panel (3,5 options visibles, la 4e coupée en deux)
et un compteur `text-xs`. 63 slots dans le même cas sur 20 composants.

Cinq invariants, un par test :

1. **Forme** (`test_size_table_shape_is_canonical`) — une table `sizes`
   est soit plate (`sizes[size] = "..."`, auto-appliquée), soit
   `sizes[size][slot]`. La forme inversée `sizes[slot][size]` existe
   encore sur 3 composants (`_INVERTED_SHAPE`) et reste à convertir.
2. **Couverture** (`test_size_reaches_every_sized_slot`) — un slot absent
   de la table `sizes` ne doit pas geler une utilitaire de taille
   (`text-sm`, `max-h-60`, `h-5`). Les slots qui ne portent que couleur /
   layout / reset (`option_active`, `min-w-0`) sont des non-participants
   légitimes et passent.
3. **Pas de collision** (`test_slot_does_not_fight_its_size_table`) — un
   slot scalé ne redéclare pas la famille que sa table lui fournit, sinon
   les deux classes coexistent et Tailwind tranche imprévisiblement.
4. **Keysets uniformes** (`test_size_rows_have_identical_keysets`) — toutes
   les lignes d'une table portent les mêmes clés, sinon le
   `size_map.get(clé, défaut)` du render retombe en silence sur le défaut.
5. **Enfants non figés** (`test_child_component_size_is_not_frozen`) — un
   composant sizé ne construit pas ses sous-composants avec un `size=`
   littéral. Seule passe AST : les tables ne voient pas ce câblage-là.
6. **Échelles dérivées** (`test_a_forwarded_size_shares_its_vocabulary`) —
   le pendant du 5 : quand un composant TRANSMET son propre `size=` à un
   enfant, les deux doivent porter le même vocabulaire. `Datatable`
   transmet le sien à `Table` ; `Table` n'a que trois crans, donc
   `Datatable` non plus — et rien nulle part n'écrit ce lien. Ajouter
   `xl` à `Table` sans l'ajouter à `Datatable` ferait rendre les LIGNES
   en `xl` et la barre d'outils au défaut ; l'ajouter à `Datatable`
   seulement enverrait `size="xl"` à une table qui n'a pas l'entrée, et
   le padding des cellules DISPARAÎTRAIT (le composeur ignore un manque).
   ⚠️ `bretzel check` ne peut pas voir ça : sa règle `value-outside-the-table`
   juge des littéraux dans du code d'APPLICATION, et ici la valeur est
   une variable, à l'intérieur du framework.

`_BASELINE` est la dette CONNUE, à faire fondre — pas une liste de cas
acceptés. L'assert est une égalité stricte : quand tu câbles un slot, la
gate échoue tant que tu ne l'as pas RETIRÉ de la baseline. La liste ne
peut donc pas pourrir.

⚠️ Les icônes se taillent en `text-*`, JAMAIS en `w-`/`h-` (traps.md §
"iconify-icon dimensionne son glyphe par font-size"). Un slot d'icône se
câble en passant un token de size au composant `Icon`, pas en ajoutant
des dimensions à la table.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from bretzel.components.base import SIZE_SCALE, size_vocabulary
from tests.consistency._discovery import (
    parsed_sources,
    public_component_classes,
)

#: Lu sur le socle (``bretzel.components.base.SIZE_SCALE``).
_SIZE_KEYS = set(SIZE_SCALE)

# Utilitaires Tailwind qui PORTENT une taille. Volontairement hors liste :
# la couleur (`text-{bg_color}`, `text-muted`), le layout pur (`flex`,
# `items-center`) et la graisse (`font-semibold`) — un slot qui n'a que ça
# n'a rien à scaler.
#
# PÉRIMÈTRE : typographie + dimensions uniquement. L'ESPACEMENT (`gap-1`,
# `px-2`, `mt-2`) dérive lui aussi — mais c'est du second ordre, et exiger
# cinq variantes de `gap-1` par slot produirait une table que personne ne
# maintient. Ce que l'œil attrape (pills figées, `max-h-60` qui coupe une
# option en deux, `text-xs` sur un compteur à `size="xl"`), c'est ici.
_N = r"\d+(?:\.\d+)?"
_DIM = r"(?:[wh]|max-h|max-w|min-h|min-w|size|leading)"
_SIZE_BEARING = re.compile("|".join([
    # `(?<![\w-])` sinon `min-w-0` se fait déchiqueter en `w-0`.
    r"(?<![\w-])text-(?:xs|sm|base|lg|xl|[2-9]xl)(?![\w-])",
    # Une seule alternative pour les deux formes de valeur — numérique
    # (`h-5`, `gap-1.5`) et arbitraire (`min-h-[2rem]`). Deux listes de
    # préfixes séparées avaient déjà divergé : `size-[3px]` et
    # `leading-[1.2]` échappaient à la maille.
    rf"(?<![\w-]){_DIM}-(?:{_N}(?![\w.-])|\[[^\]]+\])",
]))

# `-0` = reset structurel (`gap-0`, `p-0`, `h-0` sur un clip replié), pas
# une taille gelée.
_ZERO = re.compile(r"-0(?![\w.])")

# Forme `sizes[slot][size]`. À convertir vers `sizes[size][slot]` — le
# render() de ces 3 composants lit la table à l'envers.
_INVERTED_SHAPE = {"DatePicker", "DateRangePicker", "FileUpload"}


def _scaled_slots(sizes: dict) -> set[str]:
    """Les slots que la table `sizes` alimente réellement."""
    values = list(sizes.values())
    if not set(sizes) & _SIZE_KEYS:
        return set(sizes)                       # sizes[slot][size]
    if all(isinstance(v, str) for v in values):
        return {"root"}                         # plate -> composeur de base
    scaled: set[str] = set()
    for value in values:                        # sizes[size][slot]
        if isinstance(value, dict):
            scaled |= set(value)
    return scaled


def _size_hits(template: str) -> set[str]:
    """Les utilitaires de taille présents dans une string de classes."""
    return {
        m.group(0) for m in _SIZE_BEARING.finditer(template)
        if not _ZERO.search(m.group(0))
    }


def _frozen_slots(theme: dict) -> dict[str, str]:
    """slot -> les utilitaires de taille qu'il gèle. Vide = tout va bien."""
    sizes = theme.get("sizes") or {}
    if not sizes:
        return {}
    scaled = _scaled_slots(sizes)
    frozen: dict[str, str] = {}
    for slot, template in (theme.get("slots") or {}).items():
        if slot in scaled or not isinstance(template, str):
            continue
        hits = sorted(_size_hits(template))
        if hits:
            frozen[slot] = " ".join(hits)
    return frozen


_FAMILY = re.compile(r"(max-h|max-w|min-h|min-w|text|leading|size|[wh])-")


def _family(css_class: str) -> str:
    """`text-sm` -> `text`, `max-h-60` -> `max-h`. N'est jamais appelé
    qu'avec un match de `_SIZE_BEARING`, dont chaque alternative commence
    par un préfixe que `_FAMILY` reconnaît — d'où l'absence de fallback."""
    match = _FAMILY.match(css_class)
    assert match, (
        f"{css_class!r} n'a pas de famille — _SIZE_BEARING et _FAMILY "
        f"ont divergé."
    )
    return match.group(1)


def _conflicting_slots(theme: dict) -> dict[str, str]:
    """slot -> familles fournies À LA FOIS par le slot et par `sizes`.

    Sinon les deux classes atterrissent sur le même élément et Tailwind
    tranche par l'ordre CANONIQUE de la feuille, pas par l'ordre de la
    string (cf. traps.md § "Forcer l'héritage de couleur via
    classes='text-current'"). Le gagnant est imprévisible.
    """
    sizes = theme.get("sizes") or {}
    if not sizes:
        return {}
    scaled = _scaled_slots(sizes)
    clashes: dict[str, str] = {}
    for slot, template in (theme.get("slots") or {}).items():
        if slot not in scaled or not isinstance(template, str):
            continue
        slot_families = {_family(c) for c in _size_hits(template)}
        size_families: set[str] = set()
        for value in sizes.values():
            provided = (
                value.get(slot) if isinstance(value, dict)
                else (value if slot == "root" else None)
            )
            if isinstance(provided, str):
                size_families |= {_family(c) for c in _size_hits(provided)}
        overlap = slot_families & size_families
        if overlap:
            clashes[slot] = " ".join(sorted(overlap))
    return clashes


def _sized_components() -> list[type]:
    return [
        cls for cls in public_component_classes()
        if "size" in getattr(cls, "__reactive_props__", {})
        and isinstance(getattr(cls, "THEME", None), dict)
    ]


# ── Dette connue : slots qui gèlent une taille, à câbler ──────────────
# Générée depuis l'état réel du repo (juillet 2026). RETIRE l'entrée quand
# tu câbles le slot — la gate échoue tant qu'elle traîne.
_BASELINE: dict[str, set[str]] = {
    "Breadcrumb": {"item"},          # max-w-[12rem] = garde-fou de troncature
    # Le PANNEAU du ColorPicker ne suit pas `size=`, et c'est délibéré :
    # `size=` est la taille du CHAMP, pas celle de la palette. Un champ
    # `xs` dans une barre d'outils dense donnerait une grille de pastilles
    # de 16 px — inutilisable au pointeur, et pire au doigt. Les trois
    # slots gelés sont le panneau (son plafond de largeur), son étiquette
    # et la pastille d'une cellule.
    #
    # C'est le même raisonnement que `Datatable.head_button` juste en
    # dessous, à l'envers : là l'échelle est imposée par le voisinage, ici
    # elle est imposée par la CIBLE tactile.
    "ColorPicker": {"panel", "panel_label", "swatch_cell"},
    # `head_button` fige `text-xs` — et c'est le POINT : ce slot ramène un
    # `ui.button` composé à l'échelle typographique que Table impose à ses
    # `<th>` (`head_cell` : `text-xs uppercase`, identique à toutes les
    # densités). La faire varier désalignerait un en-tête triable de
    # l'en-tête non triable d'à côté. Sortir de cette baseline demanderait
    # d'abord que Table dérive SA propre échelle d'en-tête.
    # Les slots `filter_*` ont QUITTÉ la dette le 2026-08-06 : ils ont été
    # SUPPRIMÉS avec le panneau maison qu'ils habillaient. Le filtre est un
    # `ui.combobox`, donc son panneau, ses options et sa recherche se
    # mettent à l'échelle depuis la table `sizes` du combobox.
    "Datatable": {"head_button"},
    # Calendar a quitté la dette le 2026-08-01 : le slot event_dot
    # a été SUPPRIMÉ (rien ne le lisait, et sa doc le rattachait à un « mode
    # view » inexistant), donc plus aucune taille en dur hors table.
    # ``remove_btn`` a quitté la dette le 2026-07-28 : sa boîte vient de
    # ``sizes["remove_btn"]`` et son glyphe de ``sizes["remove_btn_icon_size"]``
    # (passé à ``Icon`` via ``dismiss_button``), donc le x suit enfin le
    # ``size=`` du composant.
    "FileUpload": {
        "error_text", "file_icon", "file_item", "file_list", "file_name",
        "file_progress_bar", "file_status_done", "file_status_error",
        "file_thumb",
        # ── Les mêmes, côté ``list="chips"`` (2026-08-18) ─────────────
        # Dette AJOUTÉE en connaissance de cause, et symétrique : chaque
        # entrée ci-dessous est le pendant exact d'une entrée ci-dessus
        # (``chip_icon`` ↔ ``file_icon``, ``chip_name`` ↔ ``file_name``…).
        # La présentation « puces » ne pouvait pas être mieux câblée que
        # celle qu'elle double : ``file_item`` fige déjà son ``w-28``.
        #
        # ⚠️ Conséquence à retenir : quand quelqu'un branchera enfin ces
        # slots sur ``sizes``, il devra le faire des DEUX côtés. Les
        # laisser diverger donnerait une liste qui suit ``size=`` en
        # tuiles et pas en puces — l'écart le plus dur à voir.
        "chip_icon", "chip_name", "chip_progress_bar",
        "chip_status_done", "chip_status_error",
    },
    "Input": {"prefix", "suffix"},
    "Progress": {"label"},
    "Slider": {"tooltip"},
    "Table": {"head_cell", "table"},
    # Charts : leur `size` veut dire "hauteur du graphe" (`sizes[*]["h"]`),
    # pas "échelle typographique". Légende / tooltip figés sont peut-être
    # voulus — statut non tranché, hors périmètre (juillet 2026).
    "BarChart": {"empty", "legend_dot", "legend_label"},
    "LineChart": {"empty", "legend_dot", "legend_label"},
    "PieChart": {"empty", "legend_dot", "legend_label"},
    "ScatterChart": {"empty", "legend_dot", "legend_label"},
    # Combobox / Select : câblés juillet 2026 (pilote de standardisation).
    # Ces deux-là partagent `_badge_pill_classes` — toute correction sur
    # l'un doit tomber sur l'autre.
}


# ── Sous-composants dont la taille est gelée dans le render() ────────
# La gate ci-dessus ne lit que les TABLES de thème. Un `Icon(size="sm")`
# écrit en dur dans `render()` lui échappe complètement — et c'est
# exactement le symptôme le plus visible du Combobox (pills Badge `sm`
# quel que soit le size, chevron figé). D'où cette seconde passe, en AST.
_FROZEN_CHILD_BASELINE: dict[str, set[str]] = {
    # ``Icon(size="sm")`` (le × de fermeture) a migré dans le helper
    # partagé ``_wiring.dismiss_button`` (size = paramètre, plus un
    # littéral construit ici) — la dette figée de Banner fond à la seule
    # auto-icône ``md``.
    "Banner": {'Icon(size="md")'},
    "Breadcrumb": {'Icon(size="xs")'},
    # Le bouton de tri d'un en-tête NE DOIT PAS suivre `size=` : Table fige
    # l'échelle typographique de ses `<th>` (`text-xs uppercase`, identique
    # à toutes les densités), donc un en-tête triable qui grandirait
    # cesserait de s'aligner sur l'en-tête NON triable d'à côté. Mesuré au
    # navigateur avant de baseliner : avec les overrides de layout du thème,
    # dériver cette taille ne changeait RIEN au rendu (une seule valeur
    # calculée sur sm/md/lg) — une dérivation inerte que seul le diff de
    # chaîne de classes fait passer pour vivante. Le pager et le compteur,
    # eux, sont bien dérivés (cf. `datatable/theme.py` § sizes).
    # Les DEUX contrôles d'en-tête sont volontairement fixes, même raison :
    # Table fige l'échelle typo de ses `<th>`, donc un en-tête qui grandirait
    # cesserait de s'aligner sur son voisin. Le pager, le compteur, le bouton
    # Seul le bouton de tri reste fixe : Table fige l'échelle typo de ses
    # `<th>` (`head_cell`), et un en-tête triable qui grandirait ne
    # s'alignerait plus sur l'en-tête statique d'à côté.
    # `IconButton(size="xs")` et `Text(size="xs")` ont QUITTÉ la dette le
    # 2026-08-06 : c'étaient les deux commandes et le compteur du panneau
    # de filtre maison, qui n'existe plus — le filtre est un `ui.combobox`
    # dont le `size=` descend du `sizes[<size>]["toolbar"]` de la table.
    "Datatable": {'Button(size="xs")'},
    # ⚠️ AUCUN de ces trois n'appartient a SidebarTrigger : ce sont les
    # glyphes de SidebarTitle (logo + chevron) et le chevron du pied,
    # deliberement fixes, et ces deux classes ne declarent pas `size=`.
    # La gate lit le MODULE entier (`inspect.getfile`) et attribue donc
    # ses litteraux a toute classe du fichier qui declare `size=` —
    # SidebarTrigger est la premiere. Mesure du 2026-08-24 : passer a
    # `inspect.getsource(cls)` rendrait la maille exacte ici mais
    # PERDRAIT Breadcrumb et Pagination, dont les enfants figes vivent
    # dans un helper au niveau module. La maille large est le bon
    # arbitrage ; l'entree est le prix a payer.
    # Le `size=` du declencheur, lui, EST derive : il descend dans
    # l'IconButton qu'il rend.
    "SidebarTrigger": {
        'Icon(size="lg")', 'Icon(size="sm")', 'IconButton(size="md")',
    },
    "NumberInput": {'Icon(size="xs")'},
    "Pagination": {'Icon(size="sm")'},
    # ``ToggleGroup`` a QUITTÉ la dette le 2026-08-18 : ToggleButton
    # garde le NOM de l'icône et la bâtit au rendu, où ``item_class``
    # porte enfin la taille du libellé du groupe. Vérifié : xs → 14 px,
    # xl → 24 px, alors que le littéral figeait 14 px partout.
    # C'est cette gate qui l'a exigé — le fix « un cran au-dessus » du
    # chantier icône corrigeait la VALEUR sans dégeler le mécanisme.
    # Combobox / Select : câblés juillet 2026 (pilote).
}


def _frozen_children(cls: type) -> set[str]:
    """Sous-composants construits avec un `size=` littéral dans le module."""
    try:
        source = Path(inspect.getfile(cls)).read_text(encoding="utf8")
    except OSError:  # pragma: no cover - composant sans fichier source
        return set()
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if not name:
            continue
        # Volontairement SANS filtre sur la casse du callee : un helper
        # (`_badge_pill_classes(size="sm")`) fige une taille aussi sûrement
        # qu'un constructeur. Aujourd'hui seuls des `Icon(...)` matchent,
        # mais la maille reste large pour la suite.
        for kw in node.keywords:
            if kw.arg == "size" and isinstance(kw.value, ast.Constant):
                found.add(f'{name}(size="{kw.value.value}")')
    return found


@pytest.mark.parametrize(
    "cls", _sized_components(), ids=lambda c: c.__name__
)
def test_size_rows_have_identical_keysets(cls: type) -> None:
    """Toutes les tailles d'une table couvrent les MÊMES clés.

    Les ``render()`` lisent la table en ``size_map.get(<clé>, <défaut>)``
    — un défaut reste nécessaire : un thème utilisateur peut redéfinir
    une LIGNE de ``sizes`` en entier (depuis le fix merge du 2026-07-15,
    ``_resolved_theme`` fusionne les dicts mais une string leaf remplace
    l'entrée, cf. ``test_theme_override_merge.py``), donc une clé peut
    manquer. Mais un défaut est aussi exactement ce qui a produit le
    bug d'origine : les pills tombaient en ``sm`` sans que rien ne le
    signale.

    Cette gate est ce qui rend ces défauts DÉFENDABLES : tant que les
    lignes ont le même keyset, aucun fallback n'est atteignable côté
    framework. Une ligne ``2xl`` qui oublierait ``pill_size`` ré-ouvrirait
    le bug en silence — ici elle échoue.
    """
    sizes = cls.THEME.get("sizes") or {}
    rows = {
        key: set(value) for key, value in sizes.items()
        if isinstance(value, dict)
    }
    if len(rows) < 2:
        pytest.skip(f"{cls.__name__} : table plate ou une seule ligne")
    reference = set().union(*rows.values())
    ragged = {
        key: sorted(reference - keys)
        for key, keys in rows.items() if keys != reference
    }
    assert not ragged, (
        f"{cls.__name__} : lignes de `sizes` à clés manquantes -> {ragged}.\n"
        f"  Le render() lira `size_map.get(<clé>, <défaut>)` et retombera "
        f"SILENCIEUSEMENT sur le défaut pour ces tailles — c'est le bug des "
        f"pills `sm` sur un picker `xl`.\n"
        f"  Toutes les lignes doivent porter les mêmes clés : {sorted(reference)}"
    )


@pytest.mark.parametrize(
    "cls", _sized_components(), ids=lambda c: c.__name__
)
def test_child_component_size_is_not_frozen(cls: type) -> None:
    """Un composant qui a un `size` ne fige pas celui de ses enfants."""
    frozen = _frozen_children(cls)
    expected = _FROZEN_CHILD_BASELINE.get(cls.__name__, set())
    assert frozen == expected, (
        f"{cls.__name__} déclare `size` mais construit {sorted(frozen)} "
        f"avec une taille LITTÉRALE (baseline : {sorted(expected)}).\n"
        f"  L'enfant reste figé quel que soit le `size=` du parent — c'est "
        f"le bug des pills Badge `sm` sur un `combobox(size='xl')`.\n"
        f"  Dérive le size de l'enfant depuis celui du parent (une entrée "
        f"dans `theme['sizes'][<size>]` qui porte le TOKEN de l'enfant), ou "
        f"baseline-le ici si la taille est délibérément fixe."
    )


# Slot ET table `sizes` fournissent la même famille -> collision Tailwind.
# ✅ VIDE depuis le 2026-07-15 (audit F). Calendar y était : `sizes["md"]`
# était VIDE et ses 4 slots (day_cell / weekday / nav_button /
# month_label) portaient les valeurs md en dur, que les autres tailles
# EMPILAIENT au lieu de remplacer (`calendar(size="xs")` sortait
# `w-9 h-7 text-xs w-6 h-5 text-[9px]` sur le même élément — Tailwind
# tranchait par l'ordre de sa feuille). Fix : sorties du slot vers
# `sizes["md"]`. Égalité stricte plus bas → la liste ne peut que rétrécir.
_CONFLICT_BASELINE: dict[str, set[str]] = {}


@pytest.mark.parametrize(
    "cls", _sized_components(), ids=lambda c: c.__name__
)
def test_slot_does_not_fight_its_size_table(cls: type) -> None:
    """Un slot scalé ne redéclare pas la famille que `sizes` lui donne."""
    clashes = _conflicting_slots(cls.THEME)
    expected = _CONFLICT_BASELINE.get(cls.__name__, set())
    assert set(clashes) == expected, (
        f"{cls.__name__} : {dict(sorted(clashes.items()))} — le slot ET la "
        f"table `sizes` posent la MÊME famille d'utilitaire sur l'élément "
        f"(baseline : {sorted(expected)}).\n"
        f"  Les deux classes coexistent dans le HTML ; Tailwind tranche par "
        f"l'ordre de SA feuille, pas par l'ordre de ta string — le gagnant "
        f"est imprévisible (traps.md).\n"
        f"  Le slot ne garde que ce qui NE dépend pas du size ; la valeur "
        f"par défaut va dans `sizes['md']`, pas dans le slot."
    )


@pytest.mark.parametrize(
    "cls", _sized_components(), ids=lambda c: c.__name__
)
def test_size_table_shape_is_canonical(cls: type) -> None:
    """La table `sizes` est plate ou `sizes[size][slot]` — pas l'inverse."""
    sizes = cls.THEME.get("sizes") or {}
    if not sizes:
        pytest.skip(f"{cls.__name__} n'a pas de table sizes")
    inverted = not (set(sizes) & _SIZE_KEYS)
    if cls.__name__ in _INVERTED_SHAPE:
        assert inverted, (
            f"{cls.__name__} est passé en forme canonique — retire-le de "
            f"_INVERTED_SHAPE."
        )
        pytest.xfail(f"{cls.__name__} : forme sizes[slot][size], à convertir")
    assert not inverted, (
        f"{cls.__name__} indexe sa table sizes par SLOT puis par size "
        f"(clés : {sorted(sizes)[:4]}…). La forme canonique est "
        f"sizes[<size>][<slot>] — sinon chaque lecteur doit deviner le sens."
    )


@pytest.mark.parametrize(
    "cls", _sized_components(), ids=lambda c: c.__name__
)
def test_size_reaches_every_sized_slot(cls: type) -> None:
    """Aucun slot hors table `sizes` ne gèle une utilitaire de taille."""
    frozen = _frozen_slots(cls.THEME)
    expected = _BASELINE.get(cls.__name__, set())
    assert set(frozen) == expected, (
        f"{cls.__name__} : slots qui gèlent une taille hors de la table "
        f"`sizes` = { dict(sorted(frozen.items())) }, baseline = "
        f"{sorted(expected)}.\n"
        f"  - Slot EN TROP : il porte une taille en dur que `size=` ne "
        f"pourra jamais bouger. Ajoute-le à `theme['sizes'][<size>]` et "
        f"compose-le dans render() (le composeur de base ne le fera pas : "
        f"il skip les dicts en silence).\n"
        f"  - Slot MANQUANT : tu viens de le câbler — retire-le de "
        f"`_BASELINE` pour que la dette reste juste.\n"
        f"  - Icônes : taille en `text-*` via le composant Icon, jamais en "
        f"`w-`/`h-` (traps.md)."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les composants dimensionnés sont bien découverts.

    Le filtre est double (``size`` dans ``__reactive_props__`` ET un
    ``THEME`` dict) : renommer l'un des deux viderait la population sans
    qu'aucune interdiction ne rougisse.
    """
    sized = _sized_components()
    assert len(sized) >= 35, (
        f"seulement {len(sized)} composants dimensionnés découverts (45 le "
        f"2026-08-19) — le filtre ne reconnaît plus la surface, et « aucun "
        f"slot ne gèle sa taille » ne juge presque plus rien."
    )


# ─────────────────────────────────────────────────────────────────────
# 6. Échelles DÉRIVÉES — un size transmis doit partager son vocabulaire
# ─────────────────────────────────────────────────────────────────────

#: Les noms de variable qui portent « ma propre taille » dans un render.
#: Volontairement courts et explicites : élargir la maille attraperait
#: `size=sizes.get("toolbar", "sm")`, qui est un DÉCOUPLAGE délibéré (la
#: barre d'outils d'une datatable ne suit pas la densité des lignes) —
#: exactement ce que l'invariant 5 autorise et baseline.
_SELF_SIZE_VARS = frozenset({"size", "size_key", "size_value"})

#: Les sites de transmission qui vivent dans un fichier PARTAGÉ, où le
#: parent n'est pas déductible du fichier. Déclarés avec leurs parents
#: réels, sinon le plancher plus bas refuse le site.
#:
#: `actions/_wiring.py` compose le spinner de chargement pour les DEUX
#: boutons ; sa variable `size` est celle du bouton appelant.
_SHARED_FORWARDERS: dict[tuple[str, str], tuple[str, ...]] = {
    ("bretzel/components/actions/_wiring.py", "Spinner"): ("Button", "IconButton"),
    # L'état vide des quatre charts — assemblé une fois dans la couche
    # partagée, comme le reste de ``_layers`` (audit F10/F43/F45). Il
    # transmet le palier du chart à l'``EmptyState`` pour la même raison
    # que ``diagram`` : sans ça, un ``size=`` ne changerait RIEN sur un
    # graphique vide, soit exactement le kwarg mort que ce dépôt traque.
    ("bretzel/components/charts/_layers.py", "EmptyState"): (
        "BarChart", "LineChart", "PieChart", "ScatterChart",
    ),
}


def _forwarding_sites() -> list[tuple[str, str, str]]:
    """``(parent, enfant, site)`` — tout endroit qui transmet SON size.

    Balayé sur la source, pas listé : un cinquième site entre dans la
    gate sans que personne n'y pense. Cf. la memory
    ``project_gate_floors_must_read_the_gate_source``.
    """
    root = Path(__file__).resolve().parents[2]
    owner = {
        Path(inspect.getfile(cls)).resolve(): cls.__name__
        for cls in public_component_classes()
    }
    sites: list[tuple[str, str, str]] = []
    # ``parsed_sources`` et non un ``rglob`` maison : elle lit en
    # utf-8-sig et LÈVE sur un fichier illisible. Ma première version
    # faisait `except SyntaxError: continue` — un fichier disparaissait
    # du balayage sans un mot, et `test_no_gate_swallows_a_file` l'a
    # refusé. C'est le défaut qui a sorti `render/__init__.py` de SEPT
    # gates pendant des mois, à cause d'un BOM.
    for source in parsed_sources(root / "bretzel" / "components", floor=150):
        path, tree = source.path, source.tree
        aliases = _import_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _is_super_init(node):
                continue
            callee = getattr(node.func, "id", None) or getattr(
                node.func, "attr", None)
            if not callee:
                continue
            if not any(
                kw.arg == "size"
                and isinstance(kw.value, ast.Name)
                and kw.value.id in _SELF_SIZE_VARS
                for kw in node.keywords
            ):
                continue
            # Le nom écrit peut être un ALIAS d'import (`_IconButton`).
            # Résolu par l'AST et non par `getattr` sur le module : les
            # imports qui cassent un cycle sont LOCAUX à la fonction,
            # donc absents de l'espace de noms du module. La première
            # version les manquait — `Calendar -> IconButton` sortait de
            # la gate déguisé en skip légitime.
            child_name = aliases.get(callee, callee)
            rel = path.resolve().relative_to(root).as_posix()
            site = f"{rel}:{node.lineno}"
            parents = _SHARED_FORWARDERS.get((rel, child_name))
            if parents is None:
                parents = (owner.get(path.resolve()),)
            for parent in parents:
                sites.append((parent, child_name, site))
    return sites


def _is_super_init(call: ast.Call) -> bool:
    """``super().__init__(size=size)`` transmet à SOI-MÊME, pas à un enfant."""
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "__init__"
        and isinstance(func.value, ast.Call)
        and isinstance(func.value.func, ast.Name)
        and func.value.func.id == "super"
    )


def _import_aliases(tree: ast.Module) -> dict[str, str]:
    """``{alias: nom réel}`` — y compris pour les imports LOCAUX.

    ``ast.walk`` et non les seuls noeuds de tête : les imports qui cassent
    un cycle vivent dans le corps d'une fonction (`from … import
    IconButton as _IconButton`, calendar.py:621), et un espace de noms de
    module ne les contient pas.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.asname:
                    out[alias.asname] = alias.name.rsplit(".", 1)[-1]
    return out


def _vocabulary(name: str) -> set[str]:
    """Le vocabulaire de `size` d'un composant, par son nom de classe."""
    for cls in public_component_classes():
        if cls.__name__ == name:
            return set(size_vocabulary(getattr(cls, "THEME", None)))
    return set()


def test_the_forwarding_sweep_finds_something() -> None:
    """Plancher : le balayage voit des sites, sinon l'interdiction est vide.

    Ancré sur la DÉCOUVERTE et non sur la population : si le motif
    `size=<variable>` cessait d'être reconnu, ce test rougirait avant que
    l'interdiction ne devienne muette.
    """
    sites = _forwarding_sites()
    assert len(sites) >= 4, (
        f"seulement {len(sites)} site(s) de transmission trouvé(s) : "
        f"{sites}. Le motif reconnu est `X(size=<variable>)` — s'il a "
        f"changé (renommage de la variable locale, passage par un dict), "
        f"l'interdiction plus bas ne porte plus sur rien."
    )


def test_no_forwarding_site_is_unattributed() -> None:
    """Aucun site avalé faute de savoir à qui il appartient.

    Un site dans un fichier partagé (`_wiring.py`) n'a pas de composant
    propriétaire. Le déclarer dans `_SHARED_FORWARDERS` est obligatoire —
    sans ça il sortirait de la gate en silence, ce qui est pire que de
    l'y voir échouer.
    """
    orphans = sorted({site for parent, _, site in _forwarding_sites()
                      if parent is None})
    assert not orphans, (
        f"{orphans} transmet un `size=` sans composant propriétaire "
        f"identifiable (fichier partagé ?). Déclare-le dans "
        f"`_SHARED_FORWARDERS` avec ses parents réels."
    )


@pytest.mark.parametrize(
    ("parent", "child", "site"), _forwarding_sites(),
    ids=lambda v: v if isinstance(v, str) else str(v),
)
def test_a_forwarded_size_shares_its_vocabulary(
    parent: str, child: str, site: str
) -> None:
    """Qui transmet son `size=` partage l'échelle de son destinataire."""
    mine, theirs = _vocabulary(parent), _vocabulary(child)
    # Pas de `skip` ici, et c'est le point : la première version en avait
    # un pour « pas de table `sizes` », et il a avalé une vraie paire
    # (`Calendar -> IconButton`) dont l'alias ne se résolvait pas. Un
    # vocabulaire vide veut dire soit un nom non résolu, soit un enfant
    # sans échelle qui reçoit quand même un `size=` — les deux méritent
    # d'être vus.
    assert mine, (
        f"{site} : `{parent}` n'a pas de table `sizes` exploitable — nom "
        f"de classe non résolu, ou composant sans échelle qui transmet "
        f"quand même une taille."
    )
    assert theirs, (
        f"{site} : `{child}` n'a pas de table `sizes` exploitable. Soit "
        f"le nom est un alias que la résolution AST n'a pas défait, soit "
        f"`{parent}` transmet un `size=` à un enfant qui n'en fait rien — "
        f"un no-op silencieux."
    )
    assert mine == theirs, (
        f"{site} : `{parent}` transmet son `size=` à `{child}`, mais les "
        f"deux échelles diffèrent.\n"
        f"  {parent} : {sorted(mine)}\n"
        f"  {child}  : {sorted(theirs)}\n"
        f"  chez l'un seulement : {sorted(mine ^ theirs)}\n"
        f"  Une valeur que le parent accepte et que l'enfant n'a pas est "
        f"un no-op SILENCIEUX : le composeur ignore l'entrée manquante et "
        f"l'enfant rend sans sa classe de taille. L'inverse — une valeur "
        f"que seul l'enfant connaît — est une échelle que personne ne peut "
        f"atteindre.\n"
        f"  Les deux tables doivent bouger ensemble, ou le parent doit "
        f"cesser de transmettre (dérive alors la taille de l'enfant par "
        f"une entrée de `theme['sizes'][<size>]`, cf. invariant 5)."
    )


def test_a_deliberate_decoupling_is_not_swept_in() -> None:
    """Le versant LICITE — et c'est la moitié qui coûte.

    ``Datatable`` passe trois autres tailles à des enfants : ``size="xs"``
    en dur sur l'en-tête triable (un ``<th>`` ne doit pas bouger quand les
    lignes changent de densité) et ``size=sizes.get("toolbar", "sm")`` sur
    la barre d'outils (elle suit une entrée de la table, pas la densité).
    Ce sont des DÉCOUPLAGES voulus, que l'invariant 5 possède et
    baseline. Si la maille de ce balayage s'élargissait pour les attraper,
    la gate rougirait sur du code juste et serait débranchée à la
    première session.

    Mesuré : ``Datatable`` ne doit avoir qu'UNE transmission, vers
    ``Table``.
    """
    from_datatable = sorted(
        (child, site) for parent, child, site in _forwarding_sites()
        if parent == "Datatable"
    )
    assert len(from_datatable) == 1 and from_datatable[0][0] == "Table", (
        f"le balayage voit {from_datatable} pour `Datatable`. Il ne doit "
        f"voir QUE la transmission vers `Table` : les tailles lues dans "
        f"une table (`sizes.get('toolbar', 'sm')`) ou écrites en dur "
        f"(`size='xs'` sur l'en-tête triable) sont des découplages "
        f"délibérés, et les signaler ici rendrait la gate nuisible."
    )
