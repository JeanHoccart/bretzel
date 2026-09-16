"""Gate : aucun nom importable ne s'entend répondre « n'existe pas ».

Le défaut qu'elle ferme
-----------------------
``describe`` répond sur deux populations — les composants ``ui.*`` et
les sept modules qui ont une table de classement. Tout le reste tombait
dans un message qui commence par « n'est ni dans… », et ce message se lit
comme **« ce nom n'existe pas »**.

C'est faux pour tout ce que ``bretzel.components`` exporte, et le cas
mesuré le 2026-09-06 est ``DatatableState`` : la classe qu'une app
sous-classe pour toute table du framework, importable en une ligne,
rapportée introuvable. Un lecteur en conclut qu'il s'est trompé de nom —
c'est la faute la plus chère du lot, parce qu'elle est CRÉDIBLE et
qu'elle fait renoncer. Le même défaut avait déjà été fermé une fois pour
``page`` (« ``ui.page`` n'existe pas »), sans que la classe entière le
soit.

L'invariant, et ce qu'il ne dit PAS
------------------------------------
« Un nom qui s'importe depuis ``bretzel.*`` obtient une fiche **ou** on
lui dit où il vit. » Pas « tout nom a une fiche » : classer
``bretzel.components`` est une décision de surface ouverte
(``.claude/work/todo.md`` § C), et une gate n'arbitre pas à la place de
l'utilisateur.

⚠️ **Elle balaie TOUTE la surface publique**, pas seulement la moitié
non classée — c'est ce qui la rend vraie des deux côtés de cette
décision. La première version comptait les noms SANS fiche et exigeait
qu'il y en ait cent : elle aurait rougi le jour où le trou se bouche, en
accusant son propre balayage. Une gate qui épingle un manque le rend
obligatoire.

⚠️ L'outillage (``cli`` / ``lint`` / ``introspect``) est hors population
et le reste : ``describe`` sert à écrire une app. Et importer
``bretzel.lint`` pour balayer son ``__all__`` retirerait la garantie qui
le rend arrachable (``.importlinter``).
"""

from __future__ import annotations

from bretzel.introspect import _where_it_lives, resolve
from bretzel.introspect.modules import describe_module, module_names, public_owners


def public_names() -> dict[str, str]:
    """Nom public → un paquet qui l'exporte, sur toute la surface d'app.

    Les deux moitiés, réunies : ce que les paquets exportent VRAIMENT
    (``public_owners``, non filtré — les 102 classes du catalogue en
    sont) et ce que les sections classent. Un nom qui passe d'une moitié
    à l'autre — ce qu'a fait la classification de ``bretzel.components``
    le 2026-09-06 — ne change donc rien au compte.

    ⚠️ La version qui lisait ``uncovered_owners`` s'est vidée le jour
    même où le trou s'est bouché : couvrir un paquet le retirait du
    balayage, et ``describe Button`` a pu perdre son renvoi sans que
    rien ne rougisse. Une population « ce qui reste » ne garde rien.
    """
    names = dict(public_owners())
    for module in module_names():
        for symbol in describe_module(module).symbols:
            names.setdefault(symbol.name, module)
    return names


def names_reported_as_missing() -> list[str]:
    """Les noms publics dont le message ne dit rien de plus que « non »."""
    orphelins: list[str] = []
    for name, owner in public_names().items():
        try:
            resolve(name)
        except KeyError as absent:
            message = str(absent)
            if owner not in message and "It is the class behind" not in message:
                orphelins.append(name)
    return orphelins


def test_the_sweep_sees_the_whole_public_surface() -> None:
    """Plancher — lu sur la découverte de CETTE gate.

    286 noms le 2026-09-06 (171 classés + 115 hors table). Le seuil
    borne les deux moitiés à la fois : un balayage cassé d'un côté comme
    de l'autre le fait tomber, et déplacer un paquet d'une moitié vers
    l'autre ne le bouge pas."""
    assert len(public_names()) >= 250, (
        f"seulement {len(public_names())} noms publics découverts — le "
        f"balayage des façades est cassé, et « aucun nom n'est rapporté "
        f"manquant » s'affirmerait sur presque rien."
    )


def test_no_public_name_is_reported_as_missing() -> None:
    assert not names_reported_as_missing(), (
        f"ces noms s'importent et s'entendent répondre « n'est ni dans… » : "
        f"{names_reported_as_missing()}. Le message doit nommer leur porte "
        f"— une façade neuve entre dans le balayage sans édition, c'est "
        f"``uncovered_owners`` qui la découvre."
    )


def test_the_pointer_catches_a_real_name_and_spares_an_invented_one() -> None:
    """La mutation, dans les deux sens.

    Le versant qui épargne compte autant : un pointeur qui répondrait
    quelque chose à TOUT nom passerait le versant qui mord sans rien
    savoir, et noierait le message d'un vrai typo sous une piste fausse.
    """
    assert "describe datatable" in _where_it_lives("Datatable")
    # ⚠️ Le versant catalogue se prouve sur un nom COMPOSÉ. Avec
    # ``Button`` seul, la version par orthographe passait — et ratait
    # 37 noms sur 48, tous ceux qui portent un underscore.
    assert "describe accordion_item" in _where_it_lives("AccordionItem")
    assert "describe button" in _where_it_lives("Button")
    assert _where_it_lives("Buttn") == ""
    assert _where_it_lives("zzz_invente") == ""
