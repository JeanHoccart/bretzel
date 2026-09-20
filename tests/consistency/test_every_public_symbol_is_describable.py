"""Gate : tout symbole public du framework a une fiche, pas qu'une ligne.

Le problème qu'elle ferme
-------------------------
``describe`` ne résolvait que les 109 ``ui.*`` et les 7 noms de module.
Pour les 150 autres noms publics — ``page``, ``PageState``,
``ClientBinding``, ``ROUTE_ACTION`` — il répondait « ``ui.page`` n'existe
pas », ce qui est vrai et trompeur : le symbole existe, ailleurs. Un
lecteur en concluait que le décorateur n'existait pas ; une IA lisait
dans l'index que ``@page`` existe sans jamais pouvoir l'appeler, faute de
signature.

Ce que la gate exige, et pourquoi ces trois choses
---------------------------------------------------
**Couverture** — aucun nom d'un ``__all__`` couvert ne fait échouer
``describe``. C'est l'interdiction, et elle serait vide sans son
plancher : la population vient de ``symbol_owners()``, donc un
``SECTIONS`` cassé la viderait et le zéro contrevenant resterait vert.

**Substance** — une fiche doit porter ce que l'index ne peut PAS porter.
Sinon « combler le trou » se réduirait à rendre une ligne de plus, et le
manque réel — la signature — resterait. La forme attendue dépend de la
nature du symbole, et chaque branche est comptée (§ suivant).

**Le bruit ne revient pas** — ``inspect.getdoc`` sur une constante rend
la docstring de sa CLASSE : 46 lignes de l'index affichaient
``str(object='') -> str``. Une constante se résume par sa VALEUR.

⚠️ Pourquoi les branches sont COMPTÉES
---------------------------------------
Cette gate code en dur des identifiants — les étiquettes de nature
(``valeur``, ``fonction``, ``décorateur``, ``classe``) que produit
``kind_of``. Un identifiant se renomme, et une branche qui ne
reconnaît plus rien se lit exactement comme « tout est propre »
(cf. ``.claude/bretzel/gates.md`` § « Une gate qui cherche un NOM peut
être vide sans le dire »). ``test_every_kind_branch_sees_something``
exige donc que chaque nature soit réellement représentée.

⚠️ Ce que cette gate ne vérifie PAS
------------------------------------
Que la fiche soit **juste**. Elle lit des signatures vivantes, donc elle
ne peut pas mentir sur les paramètres ; mais la docstring qu'elle
recopie, elle, n'est pas jugée ici. C'est le domaine de
``test_docs_coverage`` et des relectures de prose.
"""

from __future__ import annotations

import dataclasses
import inspect
from collections import Counter

import pytest

from bretzel.introspect import (
    SymbolDetail,
    describe,
    describe_symbol,
    module_names,
    symbol_names,
    symbol_owners,
    ui_symbol_names,
)

#: Le socle publie ~150 noms sur ses sept modules. Un plancher BORNE, il
#: ne fige pas : il doit rougir si la découverte casse, pas si un symbole
#: part. Lu depuis ``symbol_names()`` — la découverte de CETTE gate — et
#: non d'un ``__all__`` relu à côté, sinon débrancher le balayage laisse
#: le plancher vert (memory ``gate_floors_must_read_the_gate_source``).
_SYMBOL_FLOOR = 120

#: Les natures que ``kind_of`` sait produire pour un symbole de module.
#: ``module`` en fait partie : ``auth`` et ``oauth`` sont des modules
#: exportés au premier étage, et leur fiche liste leur ``__all__``.
_KINDS = ("class", "function", "decorator", "value", "module")

#: Les modules couverts, **écrits en toutes lettres**. C'est un des
#: rares cas où `gates.md` autorise à recopier une population : elle EST
#: le sujet. La première version comparait ``module_names()`` aux modules
#: présents dans la découverte — deux projections du MÊME ``SECTIONS``,
#: donc en retirer ``bretzel.theme`` le faisait disparaître des deux côtés
#: et le test restait vert, ce qui est exactement le scénario que sa
#: docstring prétendait attraper.
#:
#: Deux entrées du 2026-09-06. ``bretzel.state.datatable`` est le seul
#: SOUS-paquet, et ``bretzel.components`` n'apporte que ses treize noms
#: HORS catalogue : ses 102 classes de composant sont filtrées par
#: ``describe_module``, parce que leur fiche est celle d'``ui.<nom>``.
_COVERED_MODULES = frozenset({
    "bretzel",
    "bretzel.state",
    "bretzel.state.datatable",
    "bretzel.components",
    "bretzel.server",
    "bretzel.render",
    "bretzel.theme",
    "bretzel.runtime",
    "bretzel.core",
    # 2026-09-12. La couche 7 décrivait les six couches du dessous et pas
    # son propre tiers : `describe probe` répondait « n'est ni dans les
    # composants ni les modules » sur le symbole qu'on utilise pour
    # VÉRIFIER une app. `cli`, `introspect` et `lint` restent dehors —
    # on ne les appelle pas depuis le code d'une app, `bretzel.probe` si.
    "bretzel.probe",
})

#: Les docstrings de types **builtin** de CPython, celles qui remplissaient
#: 46 lignes de l'index. Elles ne viennent pas de ce dépôt : si CPython les
#: reformule, les aiguilles cessent de mordre et le test passe au vert pour
#: toujours. D'où le contrôle positif ci-dessous, qui vérifie qu'elles
#: décrivent encore quelque chose de réel.
_LEAK_PROBES = (("x", "str(object='') -> str"), ({}, "new empty dictionary"), ((), "Built-in immutable sequence"))


def undescribable() -> list[str]:
    """Les symboles publics dont ``describe`` ne rend pas de fiche.

    Extrait pour être mutable : c'est le détecteur, et il doit pouvoir
    être exercé sur un cas fabriqué.
    """
    broken: list[str] = []
    for name in symbol_names():
        try:
            fiche = describe(name)
        except KeyError:
            broken.append(name)
            continue
        if not fiche.strip():
            broken.append(name)
    return broken


def hollow() -> list[str]:
    """Les fiches qui n'apprennent rien de plus que la ligne d'index.

    « Rien de plus » a un sens différent par nature, et c'est le point :
    une constante doit montrer sa valeur, un appelable ses paramètres (ou
    l'absence explicite de paramètres — ``logout()`` en a zéro, et le
    dire est une réponse), une classe au moins une des quatre lectures.
    """
    fiches = (describe_symbol(name) for name in symbol_names())
    return [f"{d.name} ({d.kind})" for d in fiches if not _carries(d)]


def _carries(detail: SymbolDetail) -> bool:
    """Le verdict, pour UNE fiche — extrait pour être mutable.

    ``hollow()`` balaie ; c'est ici que se prend la décision, et c'est
    donc ici qu'une preuve peut mordre.
    """
    if detail.kind == "value":
        # Un objet constant (``TRACKER``, ``ui``) n'a pas de ``repr``
        # montrable — il porte une adresse mémoire, et son affichage ferait
        # bouger l'index d'un process à l'autre. Là, la docstring de sa
        # classe EST le résumé, et c'est la réponse.
        return detail.value_repr is not None or bool(detail.doc)
    if detail.kind in ("function", "decorator"):
        return detail.signature is not None or bool(detail.doc)
    if detail.kind == "module":
        return bool(detail.methods)
    return bool(
        detail.doc or detail.signature or detail.methods or detail.algebra or detail.state
    )


def type_docstring_leaks() -> list[str]:
    """Les constantes dont le résumé est la docstring de leur TYPE.

    Le motif exact que 46 lignes de l'index portaient. Cherché sur la
    SORTIE, pas sur la fonction qui l'évite : c'est la seule façon de
    voir revenir le bruit par un chemin qu'on n'a pas prévu.
    """
    leaks = ["str(object='') -> str", "new empty dictionary", "Built-in immutable sequence"]
    index_text = "\n".join(describe(module) for module in module_names())
    return [leak for leak in leaks if leak in index_text]


# ── ① Les planchers — la découverte n'est pas vide ────────────────────────
def test_the_symbol_sweep_is_not_vacuous() -> None:
    assert len(symbol_names()) >= _SYMBOL_FLOOR, (
        f"{len(symbol_names())} symboles découverts pour un plancher de "
        f"{_SYMBOL_FLOOR} — `SECTIONS` ou un `__all__` a cassé, et "
        "l'interdiction ci-dessous serait verte sur une population vide."
    )


def test_every_covered_module_contributes_symbols() -> None:
    """Les modules du roster sont décrits, et chacun pèse dans la population.

    Deux assertions, et la première a besoin du roster littéral : sans
    lui, retirer un module de ``SECTIONS`` le retire des deux côtés d'une
    comparaison et personne ne voit que ``bretzel.theme`` n'est plus
    décrit du tout."""
    assert set(module_names()) == _COVERED_MODULES, (
        "la liste des modules décrits a bougé — si c'est voulu, mets à "
        "jour `_COVERED_MODULES` ; sinon un module a perdu sa table de "
        "classement et n'est plus décrit."
    )
    contributing = {module for modules in symbol_owners().values() for module in modules}
    missing = sorted(_COVERED_MODULES - contributing)
    assert not missing, f"module(s) couvert(s) sans aucun symbole découvert : {missing}"


def test_every_kind_branch_sees_something() -> None:
    """Chaque nature est représentée — aucune branche n'est muette.

    C'est le contrôle qu'un plancher ne peut pas rendre : il borne la
    population lue, jamais ce que le détecteur y RECONNAÎT."""
    seen = Counter(describe_symbol(name).kind for name in symbol_names())
    blind = sorted(set(_KINDS) - seen.keys())
    assert not blind, (
        f"aucun symbole classé {blind} — l'étiquette a probablement été "
        "renommée dans `kind_of`, et la branche correspondante de `hollow()` "
        "ne juge plus rien."
    )


# ── ② Les interdictions ───────────────────────────────────────────────────
def test_every_public_symbol_has_a_fiche() -> None:
    assert not undescribable(), (
        "`describe` échoue sur des symboles publics — ils n'ont donc "
        "qu'une ligne d'index tronquée, sans signature."
    )


def test_no_fiche_is_hollow() -> None:
    assert not hollow(), (
        "des fiches ne portent rien de plus que la ligne d'index : la "
        "commande répond, mais sans la signature/valeur qui est la raison "
        "de l'ouvrir."
    )


def test_no_type_docstring_leaks_into_the_index() -> None:
    assert not type_docstring_leaks(), (
        "la docstring d'un type builtin est revenue dans l'index — une "
        "constante se résume par sa VALEUR (cf. `value_summary`)."
    )


# ── ③ Les deux versants de la morsure ─────────────────────────────────────
def test_the_leak_needles_still_match_real_builtin_docstrings() -> None:
    """Les aiguilles décrivent encore quelque chose de RÉEL.

    ``type_docstring_leaks`` cherche trois chaînes qui viennent de
    CPython, pas de ce dépôt. Si un interpréteur futur reformule
    ``str.__doc__``, les trois cessent de matcher, le test passe au vert
    pour toujours, et les 46 lignes mortes peuvent revenir sans que rien
    ne rougisse. C'est la pathologie que ce fichier applique déjà aux
    étiquettes de ``kind_of`` — elle vaut ici aussi.
    """
    stale = [needle for probe, needle in _LEAK_PROBES if needle not in (inspect.getdoc(probe) or "")]
    assert not stale, (
        f"aiguilles qui ne décrivent plus aucune docstring builtin : {stale} — "
        "cet interpréteur les a reformulées, `type_docstring_leaks` est aveugle."
    )


def test_the_hollow_verdict_still_bites_on_a_fabricated_fiche() -> None:
    """La seconde détectrice a sa propre preuve.

    ``test_the_resolution_still_bites…`` exerce la RÉSOLUTION, pas le
    verdict à quatre branches de ``hollow()``. Une fiche vide de tout doit
    être reconnue creuse, et une fiche qui ne porte que sa valeur ne doit
    pas l'être.
    """
    empty = SymbolDetail(
        name="fabrique", module="bretzel", exported_by=("bretzel",), also_known_as=(),
        category="other", kind="value", doc=None, signature=None, methods=(),
        value_repr=None, algebra=(), state=None,
    )
    assert not _carries(empty), "une fiche vide de tout doit être creuse"
    assert _carries(dataclasses.replace(empty, value_repr="'/_bretzel/action'"))


def test_the_resolution_still_bites_on_a_fabricated_name() -> None:
    """Le versant qui MORD : un nom inventé lève encore.

    Sans ce volet, faire de ``describe`` un attrape-tout — rendre une
    fiche vide plutôt que lever — satisferait toutes les interdictions
    ci-dessus d'un coup."""
    with pytest.raises(KeyError):
        describe("symbole_qui_nexiste_pas_du_tout")


def test_the_error_message_names_both_pools() -> None:
    """Et il dit OÙ on a cherché.

    L'ancien message répondait « ``ui.page`` n'existe pas » pour un nom
    non-composant : vrai, et il envoyait le lecteur conclure que le
    symbole n'existait nulle part."""
    with pytest.raises(KeyError) as exc:
        describe("zzz_inexistant")
    message = str(exc.value)
    assert "components" in message and "modules" in message


def test_a_homonym_resolves_to_the_component_and_says_so() -> None:
    """Le versant LICITE : ``text`` reste le composant, et l'autre est dit.

    ``text`` est le SEUL nom porté par les deux surfaces — le composant
    ``ui.text`` et ``bretzel.render.text``, le mot du framework. C'est le
    seul endroit où la résolution neuve pouvait voler un nom à
    l'ancienne, et sur le corpus réel c'est ce versant-là qui trouve les
    vrais bugs (memory ``project_consistency_gates``).

    L'assertion sur l'unicité de la collision est délibérée : si un
    deuxième homonyme apparaît, il doit être arbitré exprès et non hérité
    d'un test écrit pour un seul cas."""
    collisions = sorted(set(ui_symbol_names()) & set(symbol_names()))
    assert collisions == ["text"], f"nouvel homonyme à arbitrer : {collisions}"

    fiche = describe("text")
    assert fiche.startswith("ui.text"), "le nom nu doit rester le composant"
    assert "bretzel.render.text" in fiche, "l'homonyme doit être nommé"
    assert describe("bretzel.render.text").startswith("text →")


def test_a_re_exported_symbol_names_its_other_homes() -> None:
    """``page`` sort de ``bretzel`` ET de ``bretzel.render``.

    Le taire ferait croire à deux symboles distincts, ou à un seul chemin
    d'import légal. Contrôle POSITIF : il prouve que la lecture des
    ré-exports reconnaît encore un cas réel."""
    detail = describe_symbol("page")
    assert detail.module == "bretzel"
    assert "bretzel.render" in detail.exported_by


def test_a_signature_reaches_the_fiche() -> None:
    """Le payload entier de la gate, sur le symbole qui l'a motivée.

    ``@page`` est le premier appel de toute app Bretzel ; sa signature
    est exactement ce qu'aucune ligne d'index tronquée ne portait."""
    fiche = describe("page")
    assert "Parameters" in fiche
    for param in ("path", "layout", "title", "methods"):
        assert param in fiche, f"`{param}` absent de la fiche de `@page`"
