"""Gate : ce qui DÉFILE ne se centre pas sans ``safe``.

Le défaut qu'elle ferme
-----------------------
Centrer un contenu plus haut que son cadre le fait déborder des **deux
côtés** — et le défilement ne remonte jamais au-dessus de son origine.
La partie haute devient donc **inatteignable, définitivement** : pas
« difficile à voir », impossible.

Mesuré le 2026-08-24 sur la page de connexion d'``examples/auth``,
en 1280×600 : contenu de 732 px, cadre de 600, et à ``scrollTop = 0`` le
contenu commençait à **-108 px**. Le titre et le champ d'adresse
n'existaient plus pour l'utilisateur, qui a demandé « on a un bug de
composant ? » — la bonne question, et la page n'avait l'air que tronquée.

Le mot-clé CSS ``safe`` dit au navigateur de retomber sur ``start``
quand ça déborde, ce qui est exactement le cas où le centrage nuit. Le
reste du temps il ne change rien : il n'y a donc aucune raison de
centrer sans lui dans un conteneur qui défile.

Les deux règles, et pourquoi il en faut deux
--------------------------------------------
1. **Un thème qui déclare un conteneur qui défile** ne centre pas nu.
   C'est la règle d'origine, et elle est LOCALE : le débordement et le
   centrage sont dans le même fichier, donc lisibles ensemble.
2. **La famille flex** (``flex`` / ``pane`` / ``viewport``) ne centre pas
   nu **du tout**, qu'elle déclare un débordement ou non. C'est la règle
   ajoutée le 2026-08-29, et elle existe parce que la première ne pouvait
   pas voir le cas réel : le défilement d'un ``ui.vstack`` est posé au
   **call-site** (``classes="… overflow-y-auto"`` — la recette d'``outlet``,
   une zone de dépôt du CRM), pendant que le centrage vient de
   ``flex/theme.py``, qui ne déclare aucun débordement. Aucune lecture
   locale ne pouvait les rapprocher.

Pourquoi la seconde se limite à ces trois-là, et pas « aucun thème » :
``safe`` ne sert que là où le contenu est celui de l'APP et peut donc
déborder. Le ``items-center`` qui centre une icône dans un bouton ne
déborde jamais, et l'élargir à lui n'achèterait rien contre des centaines
de sites touchés. Mesuré le 2026-08-24 : **581 call-sites** passent un
centrage à la famille flex.

⚠️ **Elle protège l'orthographe, pas la propriété.** Qu'une classe porte
``safe`` ne prouve pas qu'elle atteint le DOM ni que le navigateur
l'applique. C'est
``tests/runtime_js/test_a_centered_pane_keeps_its_top_reachable.py`` qui
mesure le pixel ; celle-ci est le plancher qui tourne à chaque commit.
"""

from __future__ import annotations

import re

from tests.consistency._discovery import (
    THEMES_FLOOR,
    theme_slot_strings,
    theme_sources,
)

#: Un conteneur qui COUPE : celui qui defile, et celui qui masque. Les
#: deux perdent le haut d'un contenu centre trop grand, et le second est
#: le pire des deux, puisque rien ne defile pour aller le chercher.
_SCROLLS = re.compile(r"\boverflow(-[xy])?-(auto|hidden)\b")

#: Le centrage NU, en valeur EXACTE d'entree de table. Les deux formes
#: sures n'en font pas partie : c'est le but.
_BARE_CENTER = frozenset({"items-center", "justify-center"})


def classes_of(source):
    """Les ``(cle, classes)`` d'un theme -- l'AST, jamais la source brute.

    ⚠️ Ecrit le 2026-08-29 apres que la gate se soit mordue ELLE-MEME :
    le commentaire qui EXPLIQUE pourquoi ``flex/theme.py`` porte ``safe``
    cite ``overflow-y-auto``, donc la version regex-sur-texte classait ce
    fichier « conteneur qui defile » et le faisait rougir sur sa propre
    documentation. C'est exactement le mode d'echec que le docstring de
    ``theme_slot_strings`` documente deja, retrouve dans une deuxieme
    gate -- la primitive existait, elle n'avait pas ete adoptee ici.
    """
    return theme_slot_strings(source.text)


def _scrolls(source) -> bool:
    return any(_SCROLLS.search(v) for _, v in classes_of(source))


def offenders() -> list[str]:
    """Les themes qui offrent un centrage nu ET un conteneur qui defile.

    ⚠️ Le centrage est cherche en valeur EXACTE, donc un slot COMPOSE
    (``"root": "overflow-y-auto items-center"``) lui echappe. C'etait deja
    vrai de la version regex ; le trou est ecrit plutot que referme, parce
    que le resserrer ferait rougir des dizaines de themes ou le contenu ne
    peut pas deborder (une icone centree dans un bouton).
    """
    found: list[str] = []
    for source in theme_sources():
        if not _scrolls(source):
            continue
        for key, value in classes_of(source):
            if value in _BARE_CENTER:
                found.append(
                    f"{source.path.parent.name}/theme.py -- {key!r}: {value!r}"
                )
    return found


def scrolling_themes() -> list[str]:
    """Les themes qui declarent un conteneur qui defile -- le controle positif.

    Sans lui, la gate serait verte le jour ou ``_SCROLLS`` cesserait de
    reconnaitre quoi que ce soit : zero contrevenant sur zero candidat.
    """
    return [s.path.parent.name for s in theme_sources() if _scrolls(s)]



def test_the_sweep_is_not_vacuous() -> None:
    assert len(theme_sources()) >= THEMES_FLOOR


def test_the_detector_finds_scrolling_containers() -> None:
    themes = scrolling_themes()
    assert len(themes) >= 5, (
        "le détecteur ne reconnaît presque plus de conteneur qui défile — "
        f"il ne mesure donc plus rien. Trouvés : {themes}"
    )


#: Les trois tables que l'APP pilote — ``align=`` / ``justify=`` y
#: reçoivent le contenu de l'app, donc il peut déborder. Nommées et pas
#: découvertes : la règle est un choix de périmètre, pas un balayage.
_APP_DRIVEN = ("flex", "pane", "viewport")


def app_driven_offenders() -> list[str]:
    """Les tables pilotees par l'app qui centrent encore nu."""
    found: list[str] = []
    for source in theme_sources():
        if source.path.parent.name not in _APP_DRIVEN:
            continue
        for key, value in classes_of(source):
            if value in _BARE_CENTER:
                found.append(
                    f"{source.path.parent.name}/theme.py -- {key!r}: {value!r}"
                )
    return found



def test_the_app_driven_tables_are_all_found() -> None:
    """Plancher : les trois fichiers existent et sont lus.

    Sans lui, renommer un dossier rendrait la règle verte sur zéro
    candidat — le mode d'échec que ``test_no_gate_swallows_a_file``
    interdit sur les fichiers.
    """
    seen = {
        s.path.parent.name
        for s in theme_sources()
        if s.path.parent.name in _APP_DRIVEN
    }
    assert seen == set(_APP_DRIVEN), (
        f"tables pilotées par l'app introuvables : {set(_APP_DRIVEN) - seen}"
    )


def test_no_app_driven_table_centers_unsafely() -> None:
    sites = app_driven_offenders()
    detail = "".join(f"{chr(10)}  {s}" for s in sites)
    assert not sites, (
        "``align=`` / ``justify=`` de la famille flex recoivent le "
        "contenu de l'APP, qui peut deborder — et le defilement est "
        "souvent pose au call-site, hors de portee de la regle locale "
        "ci-dessous. Ces tables doivent porter ``safe`` :" + detail
    )


def test_no_scrolling_theme_centers_unsafely() -> None:
    sites = offenders()
    assert not sites, (
        "Ces thèmes centrent SANS ``safe`` dans un conteneur qui défile, "
        "donc le haut du contenu devient inatteignable dès qu'il "
        "dépasse :\n  " + "\n  ".join(sites)
        + "\n\nÉcris ``[align-items:safe_center]`` / "
        "``[justify-content:safe_center]``. La forme entre crochets plutôt "
        "que ``justify-center-safe`` : cet utilitaire n'existe que depuis "
        "Tailwind 4.1, et le compilateur navigateur du mode dev peut être "
        "plus ancien."
    )


def test_the_detector_still_bites() -> None:
    assert _SCROLLS.search("flex flex-1 h-full min-h-0 overflow-y-auto")
    assert _SCROLLS.search("overflow-auto p-4")
    assert "justify-center" in _BARE_CENTER
    assert "items-center" in _BARE_CENTER
    # Les jumeaux LICITES : les deux formes sures, et l'utilitaire 4.1.
    assert "[justify-content:safe_center]" not in _BARE_CENTER
    assert "[align-items:safe_center]" not in _BARE_CENTER
    assert "justify-center-safe" not in _BARE_CENTER
    # Et le versant qui a MORDU pour de vrai : un commentaire qui cite une
    # classe ne doit rien declencher. C'est l'AST qui le garantit.
    assert not theme_slot_strings("# overflow-y-auto items-center" + chr(10))
    # ``overflow-hidden`` COMPTE désormais : c'est le cadre gelé, où le
    # haut coupé n'a même pas de défilement pour le rattraper.
    assert _SCROLLS.search("flex fixed inset-0 w-full overflow-hidden")
    assert not _SCROLLS.search("flex flex-col gap-4 p-4")
