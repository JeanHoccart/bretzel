"""Gate — un contrôle dont le contenu est une ICÔNE porte un nom.

Un ``<button>`` dont le seul enfant est un glyphe n'a **aucun nom
accessible** : un lecteur d'écran annonce « bouton », et un test ne peut
pas le trouver par rôle + nom. C'est la panne la plus banale de
l'accessibilité, et la plus facile à ne pas voir — le bouton s'affiche,
se clique, et fonctionne pour qui le regarde.

Trouvée le 2026-08-19 sur ``examples/crm`` (finding 18 du chantier) : le
hamburger de la coque mobile portait un ``tooltip="Menu"`` et restait
anonyme. Le ``tooltip=`` universel **enveloppe** le composant dans un
:class:`Tooltip` — c'est un survol, pas une étiquette — donc il ne donne
rien à l'arbre d'accessibilité. La connaissance existait pourtant dans le
dépôt : ``ui.datatable`` écrivait déjà ``tooltip=`` ET ``aria_label=``
côte à côte sur son « Clear filters ». Elle n'était simplement partagée
par rien.

La réparation vit dans ``IconButton.render`` : à défaut d'``aria_label``
explicite, le ``tooltip`` — qui dit déjà en toutes lettres à quoi sert le
bouton — devient le nom accessible.

Deux bras, deux populations, toutes deux **découvertes** :

1. **la règle** — tout composant dont le premier paramètre positionnel
   s'appelle ``icon`` est un contrôle icône-seule, et doit dériver son
   nom. Un cinquième composant de cette forme entrera dans le balayage
   sans que personne n'ait à l'inscrire ;
2. **les appelants du socle** — les ``IconButton`` que le framework
   construit lui-même doivent tous être nommés. C'est là que la dérive
   se voit en premier : un composant neuf copie le voisin.
"""

from __future__ import annotations

import ast
import inspect
import re

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from tests.consistency._discovery import (
    COMPONENTS_DIR,
    parsed_sources,
    public_component_classes,
    ui_name_of,
)

_COMPONENTS_FLOOR = 150

#: Ce qui compte comme un nom accessible sur un contrôle sans texte.
#: ``title`` en fait partie — c'est le dernier recours du calcul de nom
#: accessible, et ``ui.toggle_button`` s'en sert déjà. Faible, mais réel :
#: la gate juge la présence d'un nom, pas sa qualité.
_NAMED = re.compile(r'(?:aria-label|title)="([^"]+)"')


# ───────────────────────────────────────────────────────────────────────
# 1. La règle — un contrôle icône-seule dérive son nom de son tooltip
# ───────────────────────────────────────────────────────────────────────


def icon_first_components() -> list[type]:
    """Les composants publics dont le premier positionnel est ``icon``.

    C'est la définition mécanique de « contrôle icône-seule » : le glyphe
    n'est pas une décoration à côté d'un libellé, il EST le contenu.
    """
    found = []
    for cls in public_component_classes():
        params = list(inspect.signature(cls.__init__).parameters.values())[1:]
        positional = [
            p for p in params
            if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        ]
        if positional and positional[0].name == "icon":
            found.append(cls)
    return found


def test_the_icon_first_sweep_is_not_vacuous() -> None:
    """Le plancher lit la découverte de CETTE gate, pas une source fraîche."""
    found = icon_first_components()
    assert found, (
        "aucun composant icône-seule trouvé — l'inspection de signature ne "
        "rend plus rien, et les deux tests suivants passeraient sans avoir "
        "regardé un seul composant."
    )


def test_a_tooltip_becomes_the_accessible_name() -> None:
    """L'interdiction : avec un tooltip, le contrôle a un nom."""
    for cls in icon_first_components():
        with render_isolated():
            html = serialize(cls("menu", tooltip="Ouvrir le menu").render())
        names = _NAMED.findall(html)
        assert "Ouvrir le menu" in names, (
            f"{ui_name_of(cls)}(tooltip=…) ne porte aucun nom accessible "
            f"({names or 'aucun'}) : un lecteur d'écran annoncera « bouton », "
            f"et le contrôle sera introuvable par rôle + nom. C'est le "
            f"finding 18 du chantier CRM."
        )


def test_an_explicit_label_wins_over_the_tooltip() -> None:
    """Le versant LICITE — celui qui trouve les faux positifs.

    Écraser un ``aria_label`` posé par l'appelant ferait passer le test
    ci-dessus en remplaçant une étiquette choisie par une infobulle, qui
    n'a pas le même métier : l'une nomme, l'autre explique.
    """
    for cls in icon_first_components():
        with render_isolated():
            html = serialize(
                cls("menu", tooltip="Explication", aria_label="Nom").render()
            )
        assert 'aria-label="Nom"' in html, (
            f"{ui_name_of(cls)} : l'`aria_label` explicite a été écrasé."
        )
        assert 'aria-label="Explication"' not in html


def test_no_tooltip_no_invented_name() -> None:
    """Second versant licite : sans tooltip, rien n'est inventé.

    Fabriquer un nom depuis le nom de l'icône (« menu ») produirait une
    étiquette que personne n'a écrite et que personne ne traduira — pire
    qu'un bouton anonyme, parce qu'elle a l'air d'un choix.
    """
    for cls in icon_first_components():
        with render_isolated():
            html = serialize(cls("menu").render())
        assert not _NAMED.search(html), (
            f"{ui_name_of(cls)} sans tooltip ni aria_label s'invente un nom "
            f"({_NAMED.findall(html)})."
        )


def test_a_rich_tooltip_is_not_flattened() -> None:
    """Troisième versant licite : un tooltip qui n'est pas une chaîne.

    ``tooltip=ui.text(...)`` est du contenu riche. L'aplatir en étiquette
    produirait une phrase que personne n'a écrite — on ne dérive que d'une
    chaîne.
    """
    from bretzel.components.primitives.text import Text

    for cls in icon_first_components():
        with render_isolated():
            html = serialize(cls("menu", tooltip=Text("riche")).render())
        assert "aria-label" not in html, (
            f"{ui_name_of(cls)} a aplati un tooltip riche en aria-label."
        )


# ───────────────────────────────────────────────────────────────────────
# 2. Les appelants du socle — le framework nomme ses propres boutons
# ───────────────────────────────────────────────────────────────────────


def _icon_button_aliases(tree: ast.AST) -> set[str]:
    """Les noms sous lesquels CE module désigne ``IconButton``.

    ``from … import IconButton as _IconButton`` est la forme réelle dans
    ``calendar.py`` — deux appels qu'une comparaison au nom nu ne voyait
    pas. La population annoncée était 4 pour 6.
    """
    aliases = {"IconButton"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "IconButton" and alias.asname:
                    aliases.add(alias.asname)
    return aliases


def _names_a_button(node: ast.Call) -> bool:
    """Cet appel donne-t-il un nom accessible au bouton ?

    Trois formes acceptées, et une abstention :

    - ``aria_label=`` — l'étiquette explicite ;
    - ``tooltip="…"`` **littéral de chaîne** seulement. Un tooltip riche
      (``tooltip=ui.text(…)``) n'est PAS aplati en étiquette par le
      composant, donc l'accepter ici ferait passer un bouton anonyme —
      les deux bras de cette gate se contrediraient ;
    - un ``**{…}`` dont le dictionnaire porte ``aria-label`` / ``aria_label``.

    Et l'abstention : un ``**kwargs`` non littéral peut porter n'importe
    quoi. On ne peut pas prouver l'absence, donc on n'accuse pas.
    """
    for kw in node.keywords:
        if kw.arg == "aria_label":
            return True
        if kw.arg == "tooltip":
            if isinstance(kw.value, ast.Constant) and isinstance(
                kw.value.value, str
            ):
                return True
            continue
        if kw.arg is None:                    # ``**quelque_chose``
            if not isinstance(kw.value, ast.Dict):
                return True                   # indécidable → abstention
            keys = {
                k.value for k in kw.value.keys
                if isinstance(k, ast.Constant)
            }
            if keys & {"aria-label", "aria_label"}:
                return True
    return False


def icon_button_calls() -> list[tuple[str, ast.Call]]:
    """TOUS les appels à ``IconButton`` du socle — la population brute.

    Le plancher ET l'interdiction lisent cette liste, pas deux balayages
    jumeaux : un plancher qui recompte depuis sa propre découverte reste
    vert quand le détecteur cesse de reconnaître la construction (memory
    ``gate_floors_must_read_the_gate_source``).
    """
    calls: list[tuple[str, ast.Call]] = []
    for source in parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR):
        aliases = _icon_button_aliases(source.tree)
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.Call):
                continue
            called = getattr(node.func, "id", None) or getattr(
                node.func, "attr", None
            )
            if called in aliases:
                calls.append(
                    (f"{source.path.relative_to(COMPONENTS_DIR)}:{node.lineno}",
                     node)
                )
    return calls


def unnamed_icon_buttons() -> list[str]:
    """Ceux de ces appels qui ne donnent aucun nom — le détecteur."""
    return [where for where, node in icon_button_calls()
            if not _names_a_button(node)]


def test_the_call_site_sweep_is_not_vacuous() -> None:
    """Six sites au 2026-08-19. Un plancher BORNE, il ne fige pas."""
    calls = icon_button_calls()
    assert len(calls) >= 4, (
        f"seulement {len(calls)} appel(s) à IconButton trouvé(s) — le "
        f"balayage AST ne reconnaît plus la construction (un alias d'import ?), "
        f"et l'interdiction ci-dessous passerait sur une population vide."
    )


def test_the_framework_names_its_own_icon_buttons() -> None:
    assert not unnamed_icon_buttons(), (
        f"boutons-icône anonymes dans le socle : {unnamed_icon_buttons()}. "
        f"Passe un `aria_label=` (ou un `tooltip=\"…\"` littéral, dont il "
        f"dérive) — sinon le composant qui les copiera héritera de l'anonymat."
    )


def test_the_call_site_detector_still_bites() -> None:
    """La mutation, dans les deux sens, sur des appels FABRIQUÉS.

    Les cinq formes qui comptent, dont les trois que la première version de
    cette gate ratait — l'alias d'import, le ``**{…}``, et le tooltip riche
    qu'elle acceptait à tort.
    """

    def offenders_in(code: str) -> list[str]:
        tree = ast.parse(code)
        aliases = _icon_button_aliases(tree)
        return [
            str(node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (getattr(node.func, "id", None)
                 or getattr(node.func, "attr", None)) in aliases
            and not _names_a_button(node)
        ]

    # ── ce qui DOIT mordre ────────────────────────────────────────────
    assert offenders_in('IconButton("x", variant="ghost")'), (
        "le détecteur ne voit plus un IconButton anonyme"
    )
    assert offenders_in(
        "from a import IconButton as _IB\n_IB('x', variant='ghost')"
    ), "le détecteur ne suit pas un alias d'import"
    assert offenders_in('IconButton("x", tooltip=ui.text("riche"))'), (
        "un tooltip RICHE est accepté comme nom, alors que le composant ne "
        "l'aplatit pas — les deux bras de la gate se contrediraient"
    )

    # ── ce qui doit être ÉPARGNÉ ──────────────────────────────────────
    assert not offenders_in('IconButton("x", aria_label="Fermer")')
    assert not offenders_in('IconButton("x", tooltip="Fermer")')
    assert not offenders_in(
        "from a import IconButton as _IB\n_IB('x', aria_label='Fermer')"
    )
    assert not offenders_in('IconButton("x", **{"aria-label": "Fermer"})')
    assert not offenders_in("IconButton('x', **extra)"), (
        "un `**kwargs` opaque est ACCUSÉ : on ne peut pas prouver l'absence "
        "d'un nom dans un dictionnaire qu'on ne voit pas"
    )
