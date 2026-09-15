"""Gate : ce qui rend un ``<img>`` exige un ``alt``, ce qui rend un
``<iframe>`` exige un ``title`` — sans defaut.

Le defaut qu'elle ferme
-----------------------
``ui.image`` exige ``alt`` (keyword-only, sans defaut) et ``ui.iframe``
exige ``title``, pour la meme raison : l'oubli est **invisible a l'ecran**
et ne se voit qu'au lecteur d'ecran. Personne ne le rattrape en revue.

Or ``ui.avatar`` declare ``alt: str = reactive_prop(default="")``. Donc
``ui.avatar(src="/photo.png")`` emet ``<img src="/photo.png" alt="">`` —
et ``alt=""`` ne veut pas dire « pas d'alternative », il veut dire
**« image decorative, ignore-moi »**. La photo d'un utilisateur devient
invisible au lecteur d'ecran, en silence.

Deux composants qui rendent la meme balise, deux politiques opposees, et
rien qui le signale. C'est ce que cette gate rend impossible a reconduire.

Ce qu'elle garde exactement
----------------------------
Une balise gardee doit porter une alternative NON VIDE, et il y a **deux
facons legitimes** de l'obtenir :

1. **L'appelant la fournit, et il n'a pas le choix** — parametre
   keyword-only, sans valeur par defaut. Un defaut, meme non vide, laisse
   l'oubli passer. C'est ``ui.image`` et ``ui.iframe``.
2. **Le composant la derive lui-meme** — il emet un ``bz-attr:alt`` que
   le runtime peint. C'est ``ui.file_upload``, dont la vignette porte
   ``bz-attr:alt="entry.name"`` (le nom du fichier), et c'est la
   MEILLEURE des deux : l'appelant n'a rien a savoir, donc rien a
   oublier.

   ⚠️ Un ``alt`` LITTERAL ne compte pas, et la mutation a montre
   pourquoi : le harnais de construction passe lui-meme une valeur,
   donc l'accepter revenait a mesurer « le banc a fourni un alt ». La
   premiere version de cette gate passait avec un defaut ajoute a
   l'``alt`` d'``ui.image``.

⚠️ La seconde voie n'etait pas prevue quand cette gate a ete ecrite. Elle
a ete ajoutee parce que le balayage a trouve un TROISIEME emetteur que
personne ne suivait — ``FileUpload`` — et qu'exiger de lui un ``alt=``
aurait ete un contresens.

La population est decouverte, pas listee : on rend chaque composant public
avec une sonde ``src`` / ``url`` et on regarde la balise qui sort. Un
composant media neuf entre donc dans la gate sans que personne y pense —
c'est tout l'objet.

Les abstentions portent leur raison, comme partout ailleurs dans ce
dossier. ``Avatar`` en est une, **datee** : la rendre obligatoire est un
changement cassant sur un composant livre, a faire sciemment.
"""

from __future__ import annotations

import inspect
import re

import pytest

from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    public_component_classes,
    rendered_html_of,
    ui_name_of,
)

#: La balise emise -> le parametre qui doit etre exige, et pourquoi.
_CONTRAT = {
    "img": ("alt", "un lecteur d'ecran n'a que lui pour dire ce qu'est l'image"),
    "iframe": ("title", "un lecteur d'ecran annonce les cadres d'une page par leur titre"),
}

#: Les sondes qui font qu'un composant media rend vraiment sa balise. Sans
#: elles, ``ui.avatar()`` nu rend un ``<span>`` d'initiales et sort du
#: balayage — la population serait vide et la gate verte pour rien.
_SONDES = (None, ("src", "/x.png"), ("url", "https://example.test/"))

#: Les composants qui rendent la balise SANS exiger le parametre, avec la
#: raison. Une entree ici est une DETTE datee, pas une dispense.
_EXEMPT: dict[str, str] = {
    "Avatar": (
        "2026-09-01, EXCEPTION TRANCHEE — ce n'est plus une dette qui "
        "attend une decision, c'est la decision. Elle est ici et pas "
        "seulement dans le todo, parce que c'est ici qu'on la relira.\n"
        "  Le 2026-08-30, ``ui.avatar`` a recu ``name=``, dont il derive "
        "les initiales ET l'``alt`` : la voie recommandee ne peut donc "
        "plus produire une photo muette. Ne restait que "
        "``ui.avatar(src=…)`` sans ``alt=`` NI ``name=``, qui emet "
        "``alt=''``.\n"
        "  Ce cas-la RESTE ouvert volontairement. ``alt=''`` ne veut pas "
        "dire « pas d'alternative », il veut dire « image decorative, "
        "ignore-moi » — et c'est parfois exactement juste : une pastille "
        "posee a cote d'un nom deja ecrit en toutes lettres ne doit pas "
        "etre annoncee deux fois. Fermer ce cas serait cassant ET "
        "discutable, pas seulement cassant : la difference avec "
        "``ui.image`` n'est pas un oubli de politique, c'est qu'un avatar "
        "a un usage decoratif ordinaire qu'une image de contenu n'a pas."
    ),
}

_BALISE = re.compile(r"<(img|iframe)\b")


#: Les refus de construction, COMPTES et non tus.
#:
#: ⚠️ Un ``except Exception: return None`` nu ferait sortir un composant du
#: balayage sans un mot — la version « composant » du fichier saute en
#: silence, interdite par ``test_no_gate_swallows_a_component``, et qui
#: avait deja fait vivre Image / Iframe / MetaTag / Title hors de TROIS
#: gates. Ici les refus sont attendus (on sonde ``src=`` sur des composants
#: qui n'en ont pas), mais « attendu » doit se compter, pas se supposer.
_REFUS: dict[str, str] = {}


def _render(cls: type, sonde: tuple[str, str] | None) -> str | None:
    """Le HTML de ``cls`` sous une sonde, ou ``None`` si elle ne s'applique pas.

    Le refus est ENREGISTRE dans :data:`_REFUS` — cf. le plafond declare
    par ``test_the_refusals_stay_definitional``.
    """
    cle = f"{cls.__name__}:{sonde[0] if sonde else '_nu'}"
    try:
        return rendered_html_of(
            cls,
            prop=sonde[0] if sonde else None,
            value=sonde[1] if sonde else None,
        )
    except Exception as exc:  # noqa: BLE001 — enregistre, pas avale
        _REFUS[cle] = type(exc).__name__
        return None


def _tags_emitted(cls: type) -> set[str]:
    """Les balises gardees que ``cls`` peut emettre, toutes sondes confondues."""
    seen: set[str] = set()
    for sonde in _SONDES:
        html = _render(cls, sonde)
        if html:
            seen.update(_BALISE.findall(html))
    return seen


def _demands(cls: type, param: str) -> bool:
    """``param`` est-il EXIGE — keyword-only et sans valeur par defaut ?"""
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return False
    p = sig.parameters.get(param)
    return p is not None and p.default is inspect.Parameter.empty


def _self_supplies(cls: type, tag: str, param: str) -> bool:
    """Le composant pose-t-il l'alternative LUI-MEME sur chaque balise ?

    **Seule la forme reactive compte** : ``bz-attr:alt="entry.name"``, une
    directive que le runtime peint depuis les donnees du composant.

    ⚠️ Un ``alt`` LITTERAL non vide ne compte pas, et c'est une correction
    apportee par la mutation : la premiere version l'acceptait, et elle
    passait quand on donnait un defaut a l'``alt`` d'``ui.image`` — parce
    que le harnais de construction, lui, passe une valeur. On mesurait
    donc « le banc a fourni un alt », pas « le composant le derive ». Une
    directive, elle, ne peut venir que du composant : un appelant qui
    ecrit ``alt="x"`` n'emet pas de ``bz-attr``.
    """
    ouvertures = [
        m for sonde in _SONDES
        for html in (_render(cls, sonde),)
        if html
        for m in re.finditer(rf"<{tag}\b[^>]*>", html)
    ]
    if not ouvertures:
        return False
    return all(
        re.search(rf'\bbz-attr:{param}="[^"]+"', m.group(0))
        for m in ouvertures
    )


def emitters() -> dict[str, set[str]]:
    """``NomDeClasse -> balises gardees emises``. Le balayage, une fois."""
    out: dict[str, set[str]] = {}
    for cls in public_component_classes():
        tags = _tags_emitted(cls)
        if tags:
            out[cls.__name__] = tags
    return out


def test_the_sweep_is_not_vacuous() -> None:
    assert_sweep_is_not_vacuous()


#: Sondes x composants = 3 x 100. La plupart des refus sont DEFINITIONNELS
#: (``src=`` sur un ``ui.button``), mais un plafond les empeche de devenir
#: le cas general sans que personne le voie. Mesure du 2026-08-29 : **192**
#: (186 ComponentUsageError, 6 TypeError).
_PLAFOND_REFUS = 210

#: Les seuls types de refus attendus. Un composant qui casse pour une
#: AUTRE raison sortirait du balayage en se faisant passer pour un refus
#: de principe — c'est exactement ce que la gate voisine interdit.
_REFUS_ATTENDUS = frozenset({"ComponentUsageError", "TypeError"})


def test_the_refusals_stay_definitional() -> None:
    """Les refus de construction sont COMPTES et de la bonne nature.

    On sonde ``src=`` / ``url=`` sur les 100 composants publics : la
    plupart n'en ont pas, et refusent — c'est voulu. Mais « voulu » se
    verifie : sans plafond, une regression qui ferait echouer la moitie du
    catalogue laisserait la gate verte sur une population vide.
    """
    for cls in public_component_classes():
        _tags_emitted(cls)

    assert len(_REFUS) <= _PLAFOND_REFUS, (
        f"{len(_REFUS)} refus de construction (plafond {_PLAFOND_REFUS}) — "
        f"trop de composants sortent du balayage. Soit une sonde a cesse "
        f"de s'appliquer, soit quelque chose casse en masse."
    )
    inattendus = {k: v for k, v in _REFUS.items() if v not in _REFUS_ATTENDUS}
    assert not inattendus, (
        f"refus d'une nature INATTENDUE : {inattendus}. Un composant qui "
        f"casse pour une autre raison qu'« ce parametre n'existe pas chez "
        f"moi » sort du balayage en se faisant passer pour un refus de "
        f"principe."
    )


def test_the_media_population_is_found() -> None:
    """Plancher : les trois emetteurs connus sont VUS.

    Sans lui, une sonde qui cesse de construire viderait la population et
    la gate passerait sans garder personne — le mode d'echec que le
    dossier documente partout.
    """
    vus = emitters()
    for attendu, balise in (("Image", "img"), ("Iframe", "iframe"), ("Avatar", "img")):
        assert balise in vus.get(attendu, set()), (
            f"{attendu} n'emet plus <{balise}> dans le balayage — la gate "
            f"ne mesure plus ce qu'elle croit. Vu : "
            f"{ {k: sorted(v) for k, v in vus.items()} }"
        )


@pytest.mark.parametrize("cls", public_component_classes(), ids=ui_name_of)
def test_a_media_component_demands_its_alternative(cls: type) -> None:
    tags = _tags_emitted(cls)
    if cls.__name__ in _EXEMPT:
        pytest.skip(f"dette declaree : {_EXEMPT[cls.__name__][:60]}…")
    for tag in sorted(tags):
        param, pourquoi = _CONTRAT[tag]
        assert _demands(cls, param) or _self_supplies(cls, tag, param), (
            f"{cls.__name__} peut emettre <{tag}> sans alternative — "
            f"{pourquoi}.\n"
            f"  Deux sorties, au choix :\n"
            f"    1. EXIGER ``{param}`` de l'appelant (keyword-only, sans "
            f"defaut). Un defaut, meme non vide, laisse l'oubli passer en "
            f"silence : rien a l'ecran, rien dans les tests, seul un lecteur "
            f"d'ecran le voit. C'est ``ui.image`` / ``ui.iframe``.\n"
            f"    2. La DERIVER soi-meme — un ``{param}`` litteral non vide, "
            f"ou un ``bz-attr:{param}`` que le runtime peint. C'est "
            f"``ui.file_upload``, dont la vignette porte le nom du fichier, "
            f"et c'est la meilleure : l'appelant n'a rien a oublier.\n"
            f"  Si aucune n'est possible aujourd'hui, ajoute une entree DATEE "
            f"dans ``_EXEMPT`` avec sa raison."
        )


def test_the_exemptions_are_still_needed() -> None:
    """Une dispense qui n'excuse plus rien pourrit — on la retire.

    Le jour ou ``Avatar`` exigera son ``alt``, cette assertion rougit pour
    qu'on vienne nettoyer la table plutot que de la laisser mentir.
    """
    inutiles = [
        nom for nom in _EXEMPT
        if any(
            cls.__name__ == nom
            and (_demands(cls, _CONTRAT[tag][0])
                 or _self_supplies(cls, tag, _CONTRAT[tag][0]))
            for cls in public_component_classes()
            for tag in _tags_emitted(cls)
        )
    ]
    assert not inutiles, (
        f"{inutiles} exige(nt) desormais leur parametre : retire l'entree "
        f"de ``_EXEMPT``, le contrat les juge."
    )


def test_the_detector_still_bites() -> None:
    """Mutation en memoire : le detecteur voit une signature laxiste.

    On fabrique les deux versants sur des classes jetables plutot que de
    muter un composant livre — le verdict porte sur ``_demands``, qui est
    tout ce que la gate lit d'une signature.
    """

    class Laxiste:
        def __init__(self, src: str, *, alt: str = "") -> None: ...

    class Stricte:
        def __init__(self, src: str, *, alt: str) -> None: ...

    assert not _demands(Laxiste, "alt"), "un defaut doit compter comme laxiste"
    assert _demands(Stricte, "alt"), "sans defaut, c'est exige — faux positif"
    assert not _demands(Stricte, "title"), "un parametre absent n'est pas exige"

    # Et le detecteur de balise, sur les deux versants.
    assert _BALISE.findall('<img src="x">') == ["img"]
    assert _BALISE.findall('<iframe src="x">') == ["iframe"]
    assert not _BALISE.findall('<image-placeholder>')

    # La SECONDE voie — l'alternative derivee par le composant. On
    # eprouve les deux motifs de ``_self_supplies`` sur des balises
    # fabriquees, licites et fautives.
    litteral = re.compile(r'\balt="[^"]+"')
    reactif = re.compile(r'\bbz-attr:alt="[^"]+"')

    assert reactif.search('<img bz-attr:alt="entry.name">')
    # Le litteral EXISTE mais ne satisfait PAS le contrat : il peut
    # venir du harnais. Cf. le docstring de ``_self_supplies``.
    assert litteral.search('<img alt="Photo de Jean">')
    assert not reactif.search('<img alt="Photo de Jean">')
    assert not litteral.search('<img alt="">'), (
        "un alt VIDE declare une image decorative — ce n'est pas une "
        "alternative, et c'est exactement le defaut d'Avatar"
    )
    assert not litteral.search('<img src="x">'), "pas d'alt du tout"
