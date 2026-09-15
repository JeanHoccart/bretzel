"""Une couche ``bz-class`` ne redit jamais un token de sa couche statique.

Le runtime protège désormais sa baseline (``02_directives.js``, ``base``),
donc un token partagé n'est plus DÉTRUIT. Cette gate garde l'autre moitié
du contrat : côté thème, la redite reste une erreur de conception, et elle
rearmerait le piège partout où la protection runtime ne couvre pas (une
couche dynamique qui doit pouvoir RETIRER un token ne le peut plus si la
baseline le contient — la protection est volontairement absolue).

Ce que ça coûtait, mesuré
--------------------------
Le thème Pagination composait la couche ``ellipsis`` PAR-DESSUS ``item``
en re-déclarant ``flex items-center justify-center`` + ``w-10 text-sm``,
que ``item`` posait déjà en statique. ``managed`` retenant ce que
l'EXPRESSION produit et ``classList`` étant un set, l'ajout était un
no-op mais le retrait supprimait pour de bon : un bouton qui cessait
d'être une ellipse s'effondrait de 40 px à **8 px**, ``h-10`` intacte.
Seuls les index 1 et ``slots-2`` étaient touchés — les deux seules
positions où ``compute_range`` place une ellipse — ce qui donnait le
symptôme illisible « seuls le 2e et l'avant-dernier sont rétrécis ».

La couche ``active`` du même thème s'en sortait par CHANCE : ``bg-*
shadow-sm scale-110 z-10`` n'a aucun token en commun avec ``item``. C'est
pour ça que le bug est resté invisible pendant que tout le monde
regardait la pastille active.

Le bon réflexe qu'elle encode : une couche dynamique porte ce qui
CHANGE, jamais ce que la base porte déjà.
"""

from __future__ import annotations

import html as _html
import re
from collections.abc import Iterator

import pytest

from bretzel.runtime.protocol import BZ_CLASS_PREFIX
from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    public_component_classes,
    rendered_html_of,
)

# Un élément porteur des DEUX couches. On lit les attributs à plat : le
# sérialiseur émet toujours `nom="valeur"`, guillemets doubles.
_ELEMENT = re.compile(r"<([a-zA-Z][\w-]*)((?:\s+[^\s=>]+(?:=\"[^\"]*\")?)*)\s*/?>")
_ATTR = re.compile(r"([^\s=]+)=\"([^\"]*)\"")
# Les littéraux de classe dans l'expression : "…" ou '…'. Un chemin de
# store ($bz.state.X.y) n'est pas un littéral — il ne peut pas être
# analysé statiquement, et c'est justement pour lui que la protection
# runtime existe.
_LITERAL = re.compile(r"\"([^\"]*)\"|'([^']*)'")


def _carriers(html: str) -> Iterator[tuple[str, set[str], set[str]]]:
    """Chaque élément portant les DEUX couches → (tag, statiques, dynamiques).

    UN seul parcours, consommé par la gate ET par son plancher. Les deux
    en avaient une copie ; deux parcours qui dérivent, c'est un plancher
    qui certifie une population que la gate ne lit plus — la panne exacte
    qu'on vient de corriger dans la gate directionnelle voisine.
    """
    for match in _ELEMENT.finditer(html):
        attrs = dict(_ATTR.findall(match.group(2)))
        raw = attrs.get(BZ_CLASS_PREFIX)
        static = set(_html.unescape(attrs.get("class", "")).split())
        if raw is None or not static:
            continue
        dynamic: set[str] = set()
        for double, single in _LITERAL.findall(_html.unescape(raw)):
            dynamic.update((double or single).split())
        if dynamic:
            yield match.group(1), static, dynamic


def _overlaps(html: str) -> list[tuple[str, set[str]]]:
    """Les ``(tag, tokens partagés)`` de chaque élément fautif."""
    return [
        (tag, static & dynamic)
        for tag, static, dynamic in _carriers(html)
        if static & dynamic
    ]


def _safe_render(cls: type) -> str | None:
    """Rendu par défaut, sans kwargs.

    Pas le registre ``CONSTRUCT`` de l'audit : ses builders ont la
    signature ``(classe, prop, binding)`` et existent pour tester les
    BINDINGS. Ici les littéraux à comparer sont dans le MARKUP, pas dans
    l'état — un rendu par défaut les porte tous (Pagination émet ses sept
    slots quel que soit ``total_pages``). Les composants qui exigent un
    parent ou des options se skippent d'eux-mêmes.
    """
    return rendered_html_of(cls)


@pytest.mark.parametrize("cls", public_component_classes(),
                         ids=lambda c: c.__name__)
def test_dynamic_layer_does_not_repeat_the_static_layer(cls: type) -> None:
    html = _safe_render(cls)
    if html is None:
        pytest.skip(f"{cls.__name__} non constructible sans contexte")

    faulty = _overlaps(html)
    assert not faulty, (
        f"{cls.__name__} : une couche `{BZ_CLASS_PREFIX}` redit "
        f"{[sorted(s) for _tag, s in faulty]} que le `class=` statique du "
        f"même élément porte déjà ({[t for t, _s in faulty]}).\n\n"
        f"Une couche dynamique porte ce qui CHANGE, jamais ce que la base "
        f"porte déjà. La redite est au mieux morte, au pire un piège : "
        f"c'est elle qui faisait s'effondrer un bouton Pagination de 40 px "
        f"à 8 px quand il cessait d'être une ellipse. Retire le token de "
        f"la couche dynamique (thème), pas de la statique."
    )


def test_the_sweep_actually_reads_dynamic_layers() -> None:
    """Plancher de non-vacuité (règle 8 du CLAUDE.md).

    « Zéro contrevenant » passe exactement aussi bien quand la gate n'a lu
    aucune couche dynamique — sérialiseur changé, préfixe renommé, rendu
    devenu vide. On exige donc de VOIR des `bz-class` porteurs de
    littéraux, et de les voir sur plusieurs composants.
    """
    assert_sweep_is_not_vacuous()

    carriers = 0
    components_seen: set[str] = set()
    for cls in public_component_classes():
        html = _safe_render(cls)
        if html is None:
            continue
        for _tag, _static, _dynamic in _carriers(html):
            carriers += 1
            components_seen.add(cls.__name__)

    assert carriers >= _CARRIER_FLOOR, (
        f"seulement {carriers} éléments portent un `{BZ_CLASS_PREFIX}` "
        f"à littéraux (plancher {_CARRIER_FLOOR}) — la gate ne lit plus "
        f"grand-chose, vérifie le rendu ou le préfixe avant de croire "
        f"qu'elle passe."
    )
    assert "Pagination" in components_seen, (
        f"Pagination doit rester dans le balayage — c'est le composant qui "
        f"a produit le bug. Vu : {sorted(components_seen)}."
    )


# Mesuré le 2026-08-02 : 11 porteurs sur 4 composants — Pagination 7,
# Select 2, Combobox 1, FileUpload 1. Plancher sous la mesure, pas dessus :
# il doit survivre à la disparition légitime d'un porteur, pas couvrir la
# disparition du balayage.
_CARRIER_FLOOR = 8


def test_the_detector_still_bites() -> None:
    """Mutation : un jeton présent dans les DEUX couches est reconnu.

    Répéter un jeton statique dans la couche dynamique, c'est laisser un
    morph le ré-ajouter indéfiniment. Si le détecteur cessait de croiser
    les deux couches, l'interdiction passerait sur tout le catalogue.
    """
    fautif = '<div class="flex gap-2" bz-class="{\'flex\': open}"></div>'
    assert _overlaps(fautif), "``flex`` des deux côtés devrait mordre"

    licite = '<div class="flex gap-2" bz-class="{\'hidden\': !open}"></div>'
    assert not _overlaps(licite), "aucun jeton partagé — faux positif"


# ═══════════════════════════════════════════════════════════════════
# Le même piège, UN CRAN AU-DESSUS : la FAMILLE d'utilitaire
# ═══════════════════════════════════════════════════════════════════
#
# La règle ci-dessus est clée sur l'IDENTITÉ du jeton. Elle laisse donc
# passer `py-8` en statique et `py-3` en dynamique : ils ne se répètent
# pas, et pourtant ils se battent — même famille, aucune variante, donc
# **même spécificité**, et c'est l'ordre de la feuille Tailwind qui
# tranche, pas l'auteur.
#
# Mesuré le 2026-08-02 sur la dropzone de `ui.file_upload` : un élément
# portant `py-8 py-3` calcule `padding-top: 32px`. L'état compact ne
# s'appliquait **jamais**, et rien ne le disait — le HTML est correct, les
# deux classes sont là, seul `getComputedStyle` le révèle.
#
# Une variante (`hover:`, `md:`, `data-[…]:`) change la spécificité : deux
# jetons ne se battent que si aucun des deux n'en porte. D'où l'exemption.
#
# **Population mesurée le 2026-08-29, après le fix de la dropzone : ZÉRO.**
# C'est ce qui rend la règle tenable — elle ne coûte aucun faux positif
# sur le corpus réel.

_SCALED = re.compile(r"^([a-z]+(?:-[a-z]+)*)-[\d.]+$")


def _family(token: str) -> str | None:
    """La famille d'un utilitaire à échelle numérique — ``py-8`` → ``py``.

    ``None`` pour tout ce qui ne peut pas se battre à spécificité égale :
    un jeton à variante (``:`` dans le nom), une propriété arbitraire
    (``[…]``), ou un utilitaire sans palier numérique (``flex``, dont
    l'identité suffit à la règle du dessus).
    """
    if ":" in token or token.startswith("["):
        return None
    match = _SCALED.match(token.lstrip("-").split("/")[0])
    return match.group(1) if match else None


def _family_clashes(html: str) -> list[tuple[str, str, str, str]]:
    """Les ``(tag, famille, jeton statique, jeton dynamique)`` en conflit."""
    clashes: list[tuple[str, str, str, str]] = []
    for tag, static, dynamic in _carriers(html):
        by_family_static = {
            f: t for t in static if (f := _family(t)) is not None
        }
        by_family_dynamic = {
            f: t for t in dynamic if (f := _family(t)) is not None
        }
        for family in set(by_family_static) & set(by_family_dynamic):
            if by_family_static[family] != by_family_dynamic[family]:
                clashes.append(
                    (tag, family, by_family_static[family],
                     by_family_dynamic[family])
                )
    return clashes


@pytest.mark.parametrize("cls", public_component_classes(),
                         ids=lambda c: c.__name__)
def test_the_two_layers_never_scale_the_same_family(cls: type) -> None:
    html = _safe_render(cls)
    if html is None:
        pytest.skip(f"{cls.__name__} non constructible sans contexte")

    clashes = _family_clashes(html)
    assert not clashes, (
        f"{cls.__name__} : la couche statique et la couche "
        f"`{BZ_CLASS_PREFIX}` posent deux paliers de la MÊME famille sur "
        f"le même élément — {clashes}.\n\n"
        f"Aucun des deux ne porte de variante, donc ils ont la même "
        f"spécificité : c'est l'ordre de la feuille Tailwind qui tranche, "
        f"pas l'ordre d'ajout au `classList`. L'un des deux ne s'applique "
        f"jamais, et le HTML a l'air juste — seul `getComputedStyle` le "
        f"montre.\n"
        f"  Le remède : sortir la famille de la couche statique et émettre "
        f"le ternaire COMPLET dans la couche dynamique "
        f"(`cond ? 'py-3' : 'py-8'`). Cf. `accordion.py` et la dropzone de "
        f"`file_upload`."
    )


def test_the_family_detector_still_bites() -> None:
    """Mutation : le cas RÉEL de la dropzone, et ses jumeaux licites."""
    fautif = (
        '<div class="flex px-6 py-8" '
        "bz-class=\"[n > 0 ? 'py-3' : '']\"></div>"
    )
    assert _family_clashes(fautif), (
        "`py-8` statique contre `py-3` dynamique devrait mordre — c'est le "
        "bug mesuré sur la dropzone de file_upload"
    )

    # 1. Le remède : la famille a QUITTÉ la couche statique.
    corrige = (
        '<div class="flex px-6" '
        "bz-class=\"[n > 0 ? 'py-3' : 'py-8']\"></div>"
    )
    assert not _family_clashes(corrige), "le ternaire complet est licite"

    # 2. Une VARIANTE change la spécificité — les deux coexistent sans se
    #    battre, et l'interdire ferait rougir la moitié du catalogue.
    variante = (
        '<div class="py-8" '
        "bz-class=\"[open ? 'md:py-3' : '']\"></div>"
    )
    assert not _family_clashes(variante), "une variante ne se bat pas"

    # 3. Deux familles différentes sur le même axe visuel : licite.
    voisines = (
        '<div class="px-6 py-8" '
        "bz-class=\"[open ? 'gap-2' : '']\"></div>"
    )
    assert not _family_clashes(voisines), "familles distinctes — faux positif"

    # 4. Le MÊME palier des deux côtés est déjà l'affaire de la règle
    #    d'identité au-dessus ; celle-ci ne doit pas le compter deux fois.
    identique = (
        '<div class="py-8" bz-class="[open ? \'py-8\' : \'\']"></div>'
    )
    assert not _family_clashes(identique), (
        "un jeton identique relève de `_overlaps`, pas de la famille"
    )
