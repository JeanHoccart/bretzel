"""L'icône d'un item fait UN CRAN de plus que son libellé.

Le problème, mesuré le 2026-08-18 sur les huit composants-items du
catalogue : **quatre ratios différents**, dont trois arrivés par accident.

| composant | libellé | icône | verdict |
|---|---|---|---|
| `tab`, `step`, `accordion_item`, `navbar_item` | 14 px | 18 px | ✅ un cran |
| `sidebar_item`, `toggle_button`, `tree_node` | 14 px | 14 px | ❌ même cran |
| `breadcrumb_item` | 12 px | 18 px | ❌ deux crans |
| `bottom_bar_item` | — | 24 px | exception déclarée |

Aucune gate ne le disait, et personne ne l'avait décidé : chaque
composant a choisi dans son coin.

⚠️ Une mesure à la main faite avant cette gate donnait `sidebar_item` à
14/12 — faux, elle lisait la mauvaise classe de libellé. C'est la gate
qui a la bonne valeur, parce qu'elle lit la table d'``Icon`` au lieu de
convertir des pixels de tête.

La règle, et pourquoi c'est un CRAN et pas un ratio
---------------------------------------------------

``<iconify-icon>`` se dimensionne en ``1em`` — sa taille EST sa
``font-size``. À taille égale un glyphe paraît plus petit que le texte :
pas de hampe, pas de jambage, rien qui accroche la ligne de base. Le
thème d'``Icon`` porte déjà cette intention pour son défaut
(``"md": "text-lg",  # slightly bigger than text for readability``) —
sauf qu'elle était calibrée contre un corps de page à 16 px (18/16 =
1,125), et que les items ont des libellés de 12 à 14 px.

D'où :data:`~bretzel.components.base.sizes.ICON_SIZE_ABOVE` : l'icône
prend le cran juste au-dessus, **sur l'échelle d'``Icon``**, qui est
trouée (``sm`` = 14 px puis ``md`` = 18 px, rien à 16). Cinq des huit
composants la respectaient déjà avant qu'elle soit écrite — la règle
décrit le catalogue plus qu'elle ne le réforme.

Les exceptions sont légitimes, mais DÉCLARÉES
----------------------------------------------

``bottom_bar_item`` monte à 24 px : c'est une cible tactile, pas un
ornement de ligne de texte. Une icône plus grosse y est un choix
d'ergonomie, pas une dérive. :data:`DECLARED` porte ces cas **avec leur
raison** — et ``test_a_declared_exception_is_still_an_exception``
re-mesure chaque entrée à chaque run, pour qu'une exemption ne survive
pas au besoin qui l'a justifiée.

⚠️ Ce que cette gate ne dit PAS
--------------------------------

Elle lit le HTML rendu. Elle prouve que la classe de taille émise est la
bonne, **pas** que l'icône est belle à côté de son texte. Le rapport
optique dépend de la fonte et du glyphe, et ça, seul un œil le tranche.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.sizes import icon_size_for
from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.icon.theme import ICON_THEME
from bretzel.core.serialize import serialize
from bretzel.introspect import describe_component
from bretzel.theme import Theme
from tests.consistency._discovery import public_component_classes, ui_name_of
from tests.consistency.test_text_slot_contract_universal import MOUNT

#: Les composants dont l'icône ne suit PAS son libellé, et pourquoi.
#: Chaque entrée est re-mesurée à chaque run — une allowlist qu'on ne
#: re-vérifie pas est une gate qui a déjà perdu.
DECLARED: dict[str, str] = {
    "BottomBarItem": (
        "cible tactile : la barre du bas est manipulée au pouce, son "
        "icône est l'affordance principale et le libellé n'est qu'une "
        "étiquette. 24 px est un choix d'ergonomie, pas une dérive."
    ),
}

#: Plancher de non-vacuité. Mesuré le 2026-08-18 : 8 composants-items
#: exercés. Sous ce seuil la construction a cassé et la gate n'exerce
#: plus rien — ne le baisse pas.
_FLOOR = 7

#: Le glyphe qu'on injecte — et **seulement lui**. Un item monté sous
#: son parent n'est pas seul dans l'arbre : une sidebar rend d'abord le
#: chevron de son bouton de repli. Une regex qui prendrait le PREMIER
#: ``<iconify-icon>`` mesurerait donc l'icône du parent et accuserait
#: l'enfant. Mesuré : ``SidebarItem`` était accusé à tort.
_PROBE_GLYPH = "zzprobeglyph"
_ICON_CLASS = re.compile(
    r'<iconify-icon[^>]*class="([^"]*)"[^>]*icon="lucide:' + _PROBE_GLYPH + '"'
    r'|<iconify-icon[^>]*icon="lucide:' + _PROBE_GLYPH + r'"[^>]*class="([^"]*)"'
)


def _probe_icon_class(html: str) -> str | None:
    """Les classes de l'icône INJECTÉE, quelle que soit la place de
    ``class=`` par rapport à ``icon=`` dans l'attribut rendu."""
    m = _ICON_CLASS.search(html)
    if m is None:
        return None
    return m.group(1) or m.group(2)


def _icon_size_name(icon_class: str) -> str | None:
    """Le nom de taille d'``Icon`` (``xs``/``sm``/``md``…) que porte
    cette chaîne de classes — lu depuis la table d'``Icon``, jamais
    recopié : si quelqu'un change ``md`` de ``text-lg`` à autre chose,
    cette gate suit."""
    tokens = set(icon_class.split())
    for name, cls in ICON_THEME["sizes"].items():
        if cls in tokens:
            return name
    return None


def _label_class(html: str) -> str:
    """Les classes du LIBELLÉ — celles de l'élément qui PORTE l'icône.

    ⚠️ **On lit l'ENVELOPPE de la sonde, pas le document.** Un composant
    monté sous son parent rend l'arbre entier — la sidebar, sa section,
    son en-tête, et jusqu'au tooltip du rail. Concaténer toutes les
    ``class`` faisait lire à ``icon_size_for`` le premier ``text-*``
    venu, qui pouvait appartenir à n'importe qui : la gate mesurait
    l'enfant contre un libellé qui n'est pas le sien.

    C'est exactement le point aveugle que ce fichier documente déjà pour
    l'ICÔNE (« une regex qui prendrait le PREMIER ``<iconify-icon>``
    mesurerait l'icône du parent »), rencontré une seconde fois de
    l'autre côté de la comparaison. Mesuré le 2026-08-21 : retirer un
    bouton du PARENT faisait passer la taille attendue de ``SidebarItem``
    de ``md`` à ``sm``, sans que l'enfant ait bougé d'une classe.

    L'enveloppe est la dernière balise ouvrante avant la sonde qui ne
    soit pas l'``<iconify-icon>`` elle-même — le ``<a>`` d'un
    ``SidebarItem``, le ``<button>`` d'un ``NavbarItem``. C'est elle qui
    porte la taille de texte que l'icône doit dépasser d'un cran. À
    défaut (sonde absente, enveloppe sans ``class``), on retombe sur
    l'ancien balayage complet.
    """
    body = re.sub(
        r"<iconify-icon[^>]*>.*?</iconify-icon>", "", html, flags=re.S
    )
    probe = html.find(_PROBE_GLYPH)
    if probe != -1:
        before = html[:probe]
        wrappers = re.findall(
            r"<(?!iconify-icon)[a-zA-Z][\w-]*[^>]*\sclass=\"([^\"]*)\"",
            before,
        )
        if wrappers:
            return wrappers[-1]
    return " ".join(re.findall(r"class=\"([^\"]*)\"", body))


# ⚠️ ``BreadcrumbItem`` rend ses classes de libellé VIDES monté seul —
# c'est son parent qui les lui passe. La gate le voyait donc « sans
# taille lisible » et le sautait, alors qu'il portait le PIRE écart du
# catalogue. Même point aveugle qu'en tête de
# ``test_text_slot_contract_universal``, rencontré une troisième fois.
#: Ce que la sonde ``icon=`` ne construit pas, avec sa raison.
#: **VIDE**, et mesuré : le 2026-08-19, les neuf composants qui déclarent
#: ``icon=`` ET ``label=`` se construisent tous. L'``except`` qui vivait
#: ici ne rattrapait donc plus rien depuis un moment — mais rien ne le
#: disait, et le jour où il aurait rattrapé quelque chose, personne ne
#: l'aurait su non plus.
_CANNOT_BUILD: dict[str, str] = {}


def _render_with_icon(cls: type) -> str | None:
    """Le HTML du composant, icône de sonde injectée.

    ``None`` = la construction a échoué. C'est une ABSTENTION, et
    ``test_the_abstentions_are_declared`` la refuse tant qu'elle n'est
    pas dans ``_CANNOT_BUILD`` : un composant qui cesse de se construire
    sortirait sinon du balayage sans un mot.
    """
    if cls.__name__ == "BreadcrumbItem":
        from bretzel.components import Breadcrumb

        try:
            with render_isolated(theme=Theme()):
                with Breadcrumb() as parent:
                    cls("Texte", icon=_PROBE_GLYPH, href="/x")
                return serialize(parent.render())
        except Exception:
            return None
    builder = MOUNT.get(cls.__name__)
    try:
        with render_isolated(theme=Theme()):
            comp = (
                builder(cls, "icon", _PROBE_GLYPH)
                if builder
                else cls(icon=_PROBE_GLYPH, label="Texte")
            )
            return serialize(comp.render())
    except Exception:
        return None


def icon_label_candidates() -> list[type]:
    """Les composants qui déclarent ``icon=`` ET ``label=`` — détectés."""
    out = []
    for cls in public_component_classes():
        params = {p.name for p in describe_component(ui_name_of(cls), cls).params}
        if "icon" in params and "label" in params:
            out.append(cls)
    return out


def _items() -> list[type]:
    """Ceux des candidats dont le rendu porte VRAIMENT l'icône sondée."""
    return [
        cls for cls in icon_label_candidates()
        if (html := _render_with_icon(cls)) and _probe_icon_class(html)
    ]


def test_the_abstentions_are_declared() -> None:
    """Ce que la sonde ne construit pas est NOMMÉ, pas compté.

    La table est vide aujourd'hui, et c'est le but : une exemption se
    déclare avec sa raison, elle ne s'obtient pas en échouant en
    silence.
    """
    missing = {
        cls.__name__ for cls in icon_label_candidates()
        if _render_with_icon(cls) is None
    }
    surprise = sorted(missing - set(_CANNOT_BUILD))
    assert not surprise, (
        f"{surprise} déclare(nt) `icon=` et `label=` mais ne se "
        f"construi(sen)t plus sous la sonde : ils sortent du balayage EN "
        f"SILENCE, et la règle « l'icône fait un cran de plus que son "
        f"libellé » ne les juge plus.\n"
        f"  Répare la construction, ou ajoute l'entrée à `_CANNOT_BUILD` "
        f"AVEC sa raison."
    )
    stale = sorted(set(_CANNOT_BUILD) - missing)
    assert not stale, (
        f"{stale} se construi(sen)t de nouveau — retire l'entrée de "
        f"`_CANNOT_BUILD`."
    )


_ITEMS = _items()


@pytest.mark.parametrize("cls", _ITEMS, ids=lambda c: c.__name__)
def test_the_icon_is_one_notch_above_its_label(cls: type) -> None:
    html = _render_with_icon(cls)
    assert html is not None

    icon_cls = _probe_icon_class(html)
    assert icon_cls is not None, "l'icône injectée n'est pas dans le rendu"
    got = _icon_size_name(icon_cls)
    expected = icon_size_for(_label_class(html))

    if cls.__name__ in DECLARED:
        assert got != expected, (
            f"{cls.__name__} est dans DECLARED (« {DECLARED[cls.__name__]} ») "
            f"mais son icône suit maintenant la règle ({got}). Retire "
            f"l'entrée — une exemption qu'on garde après coup masque la "
            f"règle au lieu de la nuancer."
        )
        return

    if expected is None:
        pytest.skip(
            f"{cls.__name__} : aucune classe de taille lisible sur son "
            f"libellé — rien à comparer."
        )

    assert got == expected, (
        f"{cls.__name__} : icône en taille {got!r}, attendu {expected!r} — "
        f"le cran juste au-dessus de son libellé.\n\n"
        f"``<iconify-icon>`` se dimensionne en 1em, donc sa taille EST sa "
        f"font-size : à taille égale le glyphe paraît plus petit que le "
        f"texte. La table est "
        f"``bretzel.components.base.sizes.ICON_SIZE_ABOVE``.\n\n"
        f"Si c'est VOULU (une cible tactile, pas un ornement de ligne), "
        f"ajoute une entrée dans ``DECLARED`` avec sa raison — elle sera "
        f"re-mesurée à chaque run."
    )


def test_a_declared_exception_is_still_an_exception() -> None:
    """Chaque nom de :data:`DECLARED` doit exister et être un item.

    Une entrée qui nomme un composant disparu ou renommé exempterait
    dans le vide, et la gate le dirait jamais."""
    known = {c.__name__ for c in _ITEMS}
    unknown = set(DECLARED) - known
    assert not unknown, (
        f"DECLARED nomme {sorted(unknown)}, qui ne sont pas dans la "
        f"population exercée. Composant renommé, supprimé, ou qui ne rend "
        f"plus d'icône — l'exemption ne protège plus rien."
    )


def test_the_notch_table_reads_the_icon_theme() -> None:
    """La table doit produire des noms que la table d'``Icon`` connaît.

    Sans ce test, ``ICON_SIZE_ABOVE`` peut nommer une taille qui n'existe
    pas : le composant passerait ``size="xxl"``, ``Icon`` retomberait sur
    son défaut, et la gate principale rougirait sur le mauvais coupable."""
    from bretzel.components.base.sizes import ICON_SIZE_ABOVE

    unknown = set(ICON_SIZE_ABOVE.values()) - set(ICON_THEME["sizes"])
    assert not unknown, (
        f"ICON_SIZE_ABOVE nomme des tailles qu'``Icon`` ne connaît pas : "
        f"{sorted(unknown)}. Les valeurs valides sont "
        f"{sorted(ICON_THEME['sizes'])}."
    )


def test_the_population_is_not_vacuous() -> None:
    """Sans plancher, une construction cassée viderait la population et
    la gate resterait verte en n'ayant mesuré aucun composant."""
    names = sorted(c.__name__ for c in _ITEMS)
    assert len(_ITEMS) >= _FLOOR, (
        f"la gate n'exerce plus que {len(_ITEMS)} composants (plancher "
        f"{_FLOOR}, 8 mesurés le 2026-08-18) : {names}."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : la classe de l'icône et son nom de taille sont lus.

    Deux lectures s'enchaînent — extraire les classes de l'icône
    injectée, puis les traduire en nom de palier. Si l'une cessait de
    matcher, la comparaison porterait sur ``None`` et la règle
    « l'icône fait un cran de plus » ne jugerait plus rien.
    """
    from bretzel.components.primitives.icon.theme import ICON_THEME

    md = ICON_THEME["sizes"]["md"]
    # Les DEUX ordres d'attributs, parce que le sérialiseur peut placer
    # ``class=`` avant ou après ``icon=`` — c'est la raison d'être des
    # deux alternatives de la regex.
    for html in (
        f'<iconify-icon class="{md}" icon="lucide:{_PROBE_GLYPH}"></iconify-icon>',
        f'<iconify-icon icon="lucide:{_PROBE_GLYPH}" class="{md}"></iconify-icon>',
    ):
        assert _probe_icon_class(html) == md, (
            "les classes de l'icône sondée devraient être vues dans cet ordre"
        )
    assert _probe_icon_class(
        f'<iconify-icon class="{md}" icon="lucide:autre"></iconify-icon>'
    ) is None, "une AUTRE icône n'est pas la sonde — faux positif"

    assert _icon_size_name(md) == "md", "la classe de taille doit se retraduire"
    assert _icon_size_name("text-[13px]") is None, "faux positif"
