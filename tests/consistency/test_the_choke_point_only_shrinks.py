"""Gate : le point de passage obligé du socle ne grossit plus en silence.

Ce que la mesure a montré
--------------------------
`bretzel/components/base/component.py` est passé de **1 526 lignes** au
1ᵉʳ juin 2026 à **2 795** le 19 août — +83 % en deux mois et demi,
pendant que le reste du framework passait de 32 à 65 kLOC. Ce n'est pas
anormal en soi : c'est le socle, il absorbe ce que les composants
cessent de faire chacun dans leur coin, et c'est **voulu** (chaque
primitive promue ici supprime N copies ailleurs).

Ce qui l'est moins, c'est **où** ça grossit :

=========================  =======  ==================================
symbole                    lignes   ce qu'il est
=========================  =======  ==================================
``Component.__init__``       463    le choke point : TOUT composant y passe
``Component.emit_attrs``     175    la sortie d'attributs de racine
``_apply_universal_modifiers`` 143  les kwargs universels
=========================  =======  ==================================

Un constructeur de 463 lignes n'est pas une odeur de style : c'est le
seul endroit que **96 composants** traversent, donc l'endroit où une
régression touche tout, et celui qu'on relit le moins volontiers.

Ce que cette gate fait, et ce qu'elle ne fait pas
--------------------------------------------------
Elle ne découpe rien — ce serait un chantier, pas une gate, et un
découpage de classe de base se décide, il ne se fait pas en passant.

Elle transforme la croissance en **décision** : les plafonds ci-dessous
sont l'état du 2026-08-19, et ils ne peuvent que descendre. Ajouter dix
lignes au constructeur reste possible ; ça demande juste de monter le
plafond dans le même commit, donc de l'écrire, donc de le savoir.

C'est la forme de ``test_scope_literal_debt_only_shrinks``, pour la même
raison : une dette qu'on mesure sans la borner se re-découvre au
prochain audit, à l'identique et en pire.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_COMPONENT = (
    Path(__file__).resolve().parents[2]
    / "bretzel" / "components" / "base" / "component.py"
)

#: ``symbole -> plafond de lignes``, mesuré le 2026-08-19. Le fichier
#: entier est là aussi : sans lui, on déplacerait le gras du
#: constructeur vers une fonction module et le total ne bougerait pas.
#:
#: ⚠️ ``<module>`` est passé de 2 795 à 2 840 le 2026-08-19, et la raison
#: est écrite ici parce que la gate l'exige dans le MÊME commit : les
#: 45 lignes sont de la **docstring**, pas du code. C'est le recensement
#: des deux stratégies légitimes de garde du ``None`` d'``emit_text_slot``
#: (37 appels classés), plus le piège qui a cassé ``toggle_button`` et la
#: raison mesurée pour laquelle le filtre chez ``Element`` a été écarté.
#: Ça vit au point d'usage exprès — c'est ce qu'un auteur lit avant
#: d'écrire le 38ᵉ site, et le mettre ailleurs, c'est le mettre nulle
#: part. Aucun symbole exécutable n'a bougé : les autres plafonds sont
#: inchangés.
#: **Relevé le 2026-08-23 : +9 au module, +6 sur ``emit_attrs``.** La
#: raison, écrite comme la gate l'exige : ``emit_attrs`` retire désormais
#: les attributs que la balise ne peut pas porter (``type`` sur un
#: ``<a>``…), et c'est nécessairement ICI — le seul endroit du dépôt où
#: la balise et le sac d'attributs se rencontrent pour les 97 composants.
#: Un correctif par composant aurait laissé passer le cinquième ; il y en
#: avait quatre.
#:
#: Le message de cette gate a été SUIVI, pas contourné : la table et
#: l'algorithme sont partis dans ``base/_wiring.py``
#: (``drop_tag_bound_attrs``, 48 lignes), et il ne reste ici que l'appel
#: différé plus ``_author_written_attrs``, qui nomme ce que
#: l'échappatoire brute doit épargner. Sans ce déplacement le module
#: prenait +48.
#: ⚠️ **Relevé le 2026-08-29 : +5 / +6.** L'assignation d'id lisait
#: ``ctx.parent_stack[-1].id`` ; elle lit désormais ``child_scope_id``,
#: qui diverge de ``id`` sur l'outlet — il REND un id stable (htmx le
#: renvoie en ``HX-Target``) mais DONNE à ses enfants un id qualifié par
#: la page.
#:
#: La montée est assumée et non contournée : c'est le correctif du seul
#: 🔴 de la todo, et il n'a pas d'autre place. La ligne remplacée était
#: l'endroit UNIQUE où un id de parent se lit (vérifié : un seul lecteur
#: dans tout ``bretzel/``), donc l'extraire ailleurs aurait déplacé les
#: lignes sans réduire quoi que ce soit — ``<module>`` les aurait
#: reprises. Mesure : 13 collisions de scope entre pages → 0.
#: ⚠️ **Relevé le 2026-08-30 : +9 / +10.** Le socle pose désormais la
#: classe-PONT de couleur (``bz-c-<couleur>``) sur la racine rendue —
#: phase 2 du chantier des jetons de couleur.
#:
#: La raison, écrite comme la gate l'exige. C'est nécessairement ICI, et
#: pour la raison exacte qui a déjà fait remonter ``classes=`` et
#: ``slots={"root"}`` au même endroit : un composant dont la racine est
#: composée par un AUTRE slot, ou qui fabrique sa ``class=`` à la main,
#: ne passe pas par ``compose_class``. Le pont doit être sur la racine
#: RENDUE, quelle qu'elle soit.
#:
#: Le message de cette gate a été SUIVI, pas contourné : la décision (qui
#: reçoit un pont, les trois refus, et le cas qui lève) vit dans
#: ``base/_wiring.color_bridge_class``, 50 lignes. Ici il ne reste que
#: l'import différé et l'appel. Écrit au point d'usage, le bloc pesait
#: +34.
#:
#: Et cette montée **se rembourse** : la phase 5 du chantier supprime la
#: substitution ``{bg_color}`` entière — ``PLACEHOLDER_NAMES``,
#: ``SHAPE_TOKEN_RE``, ``resolve_slot``, ``dynamic_color_shapes`` — soit
#: bien plus que les dix lignes posées ici.
#: ── 2026-09-04 : ``Component.__init__`` 469 → 473, +4 ──────────────
#:
#: La raison, écrite comme la gate l'exige. Un dict de paliers
#: (``{"base": "sm", "md": "lg"}``) passé à un prop non gradué
#: traversait toute la construction et mourait trois frames plus bas
#: sur ``unhashable type: 'dict'`` — qui ne nomme ni le composant, ni
#: le prop, ni le fait qu'un dict de paliers n'a pas sa place là.
#: **91 couples ``Classe.prop``** étaient dans ce cas, recensés un par
#: un dans ``_not_graded.txt`` parce qu'on ne savait pas les réparer
#: d'un coup.
#:
#: Le message de cette gate a été SUIVI, pas contourné, exactement
#: comme au-dessus : la décision (le discriminant, la formulation, le
#: cas gradué) vit dans ``base/responsive.reject_stray_breakpoints``,
#: 40 lignes. Ici il ne reste que l'appel et deux lignes qui disent
#: pourquoi. Écrit au point d'usage, le bloc pesait +45.
#:
#: Et cette montée **se rembourse déjà** : les trois appels à la main
#: de ``reject_responsive`` (deux dans ``flex``, un dans ``carousel``)
#: sont partis avec, ainsi que ``_GRADED_PROPS_MESSAGE``. Le fichier
#: ``_not_graded.txt`` est passé de 91 entrées à ZÉRO.
_CEILINGS: dict[str, int] = {
    # 2864 → 2871 le 2026-09-06, et c'est la décision que cette gate
    # demande d'écrire. Ce qui entre : l'appel à
    # `refuse_a_value_off_the_table` dans `finish_render`, plus son
    # commentaire. Ce que ça ferme : 52 couples (composant, axe) qui
    # avalaient une valeur de `size` / `variant` hors table SANS un mot
    # — `ui.button(size="zzz")` perdait toutes ses classes de taille.
    #
    # Le point de passage est justement ce qui rend l'ajout légitime :
    # posée dans `compose_class`, la validation ne couvrait que 17
    # composants sur 57, parce que ceux dont les paliers sont des dicts
    # multi-slots ne passent pas par cette branche. Une validation
    # partielle est pire que pas de validation.
    # 2871 → 2883 et 473 → 485 le 2026-09-08, et c'est encore la
    # décision que cette gate demande d'écrire. Ce qui entre : le pop de
    # ``outlet=``, sa fusion dans ``attrs`` et trois lignes qui disent
    # pourquoi. Ce que ça achète, MESURÉ en A/B alterné dans le même
    # processus, vingt clics par variante : un lien qui nomme la région
    # qu'il remplace fait passer une navigation de 1 204 à 569 octets et
    # de 10 à 3 ms.
    #
    # Le message de la gate a été SUIVI : la décision — valider que
    # c'est bien une coque, composer le sélecteur — vit dans
    # ``base/_wiring.outlet_target_attrs``, qui est aussi le seul
    # endroit du socle autorisé à écrire du ``hx-``. Ici il ne reste que
    # le pop et la fusion.
    #
    # Pourquoi le point de passage et pas ailleurs : ``outlet=`` doit
    # marcher sur TOUT ce qui porte un ``href`` — carte, bouton, item de
    # sidebar, item de navbar, item de dropdown. Le poser par composant
    # ferait sept signatures à tenir d'accord, ce que la règle des
    # kwargs universels refuse précisément.
    "<module>": 2883,
    "Component.__init__": 485,
    "Component.emit_attrs": 175,
    "_apply_universal_modifiers": 153,
    "_ComponentMeta.__new__": 135,
}


def measured() -> dict[str, int]:
    """``symbole -> lignes``, lu sur l'AST du fichier réel."""
    text = _COMPONENT.read_text(encoding="utf-8-sig")
    out: dict[str, int] = {"<module>": len(text.splitlines())}
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{node.name}.{member.name}"] = (
                        member.end_lineno - member.lineno + 1
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node.end_lineno - node.lineno + 1
    return out


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les symboles plafonnés existent encore.

    Un renommage ferait disparaître la clé, et un plafond qui ne trouve
    plus son symbole ne plafonne rien — vert, sur rien.
    """
    seen = measured()
    assert len(seen) >= 40, (
        f"seulement {len(seen)} symboles lus dans component.py (45 le "
        f"2026-08-19) — le parseur ne voit plus le fichier."
    )
    absents = sorted(set(_CEILINGS) - set(seen))
    assert not absents, (
        f"{absents} : ces symboles n'existent plus sous ce nom. Un plafond "
        f"orphelin ne plafonne rien — renomme la clé (et vérifie la mesure "
        f"au passage), ou retire-la si le symbole a disparu pour de bon."
    )


@pytest.mark.parametrize("symbol", sorted(_CEILINGS), ids=lambda s: s)
def test_the_choke_point_does_not_grow(symbol: str) -> None:
    seen = measured()[symbol]
    ceiling = _CEILINGS[symbol]
    assert seen <= ceiling, (
        f"`{symbol}` fait {seen} lignes, plafond {ceiling} (mesuré le "
        f"2026-08-19).\n"
        f"  Ce n'est pas un interdit : c'est une décision à écrire. "
        f"96 composants traversent ce fichier, et son constructeur a pris "
        f"+83 % en deux mois et demi sans que personne ne l'ait décidé "
        f"une seule fois.\n"
        f"  Si la croissance est justifiée, monte le plafond DANS LE MÊME "
        f"commit, avec la raison. Sinon, la primitive que tu ajoutes a "
        f"peut-être sa place dans `base/_wiring.py`, à côté des autres."
    )


def test_the_ceilings_are_not_slack() -> None:
    """Un plafond très au-dessus du réel ne plafonne rien.

    Le mode d'échec est silencieux : on monte le plafond « avec de la
    marge » un jour de refactor, et la gate laisse passer la croissance
    suivante sans un mot. On tolère 5 %.
    """
    seen = measured()
    slack = {
        s: (seen[s], c) for s, c in _CEILINGS.items()
        if s in seen and c > seen[s] * 1.05
    }
    assert not slack, (
        f"Ces plafonds ont pris du mou (réel, plafond) : {slack}. Un "
        f"plafond se resserre quand le symbole maigrit — sinon il "
        f"autorise en silence de revenir où on était."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : le mesureur compte bien les lignes d'un symbole.

    S'il rendait 0 partout, tous les plafonds passeraient — et ce serait
    le vert le plus rassurant du dépôt.
    """
    seen = measured()
    assert seen["Component.__init__"] > 100, (
        "le mesureur ne compte plus les lignes de `Component.__init__` — "
        "vérifie `measured()` avant de croire que le socle a maigri."
    )
    assert seen["<module>"] > 1000, (
        "le mesureur ne compte plus les lignes du fichier."
    )
