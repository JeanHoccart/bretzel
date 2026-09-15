"""Gate ratchet — les classes directionnelles PHYSIQUES ne se multiplient plus.

Ce que ça garde
----------------
``ml-auto`` pousse vers la DROITE. ``ms-auto`` pousse vers la fin de la
ligne — à droite en français, à gauche en arabe. Les deux rendent
exactement pareil tant que le document est en ``dir="ltr"`` ; l'une
survit à un ``dir="rtl"``, l'autre non.

Bretzel n'écrit aujourd'hui **que** des physiques. Tant qu'aucune app ne
demande le RTL, ça ne casse rien — et c'est précisément ce qui rend la
dette dangereuse : elle grossit sans jamais se signaler, et le jour où
quelqu'un pose ``dir="rtl"``, c'est le catalogue entier qui est à
reprendre d'un coup.

Cette gate ne demande pas de payer. Elle demande que le compte ne monte
plus : chaque fichier a son plafond, mesuré, et il ne peut que baisser.

⚠️ Les trois comptes qui circulaient étaient FAUX, chacun autrement
-------------------------------------------------------------------
``these-portee-2026-08-19.md`` a annoncé successivement **149 physiques
/ 16 logiques**, puis **148 / 10** en se re-mesurant. Le compte exact au
moment de poser cette gate était **101 / 0** — et l'écart n'est pas du
bruit, ce sont trois règles de comptage différentes dont aucune n'était
écrite :

- ``"left"`` et ``"right"`` comme **valeurs d'énumération**
  (``placement="left"``, ``side="right"``) étaient comptées comme des
  classes. Elles n'en sont pas.
- Les « logiques » comptaient ``align="start"``, ``justify="end"`` et
  jusqu'au mot ``ms`` de « 200 ms » dans une docstring. Il n'y a **aucune
  classe logique** dans le catalogue — zéro, pas seize.
- Le premier balayage ne lisait que les dicts de thème et ratait ce qui
  est composé dans le ``.py`` du composant.

D'où la règle, ÉCRITE et exécutable plutôt que décrite : un utilitaire
est un mot qui commence en début de chaîne, après une espace ou après un
``:`` de variante, et qui porte une VALEUR quand sa famille en prend une
(``ml-auto``, ``left-1/2``, ``rounded-l-none``). Un mot nu n'en est pas
un. C'est la seule façon d'obtenir deux fois le même nombre.

Ce que la gate ne dit PAS
--------------------------
Qu'un utilitaire physique soit une faute. Certains sont **justes** :
``left-1/2`` avec ``-translate-x-1/2`` centre, et un centre n'a pas de
direction. La gate compte une population et interdit qu'elle grossisse ;
elle ne juge pas site par site. C'est un cliquet, pas un jugement.

Et elle ne rend pas le framework RTL pour autant : convertir les classes
est nécessaire et pas suffisant — il faut encore que la coque pose un
``dir``. Cf. ``these-portee-2026-08-19.md`` § 9, décision n°1.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

from tests.consistency._discovery import (
    COMPONENTS_DIR,
    assert_sweep_is_not_vacuous,
    parsed_sources,
)

#: Preuve de morsure : le détecteur reconnaît un utilitaire réel ET
#: épargne son jumeau logique — le versant licite, qui est celui qui a
#: trouvé les deux seuls bugs de gate de ce dépôt.
MUTATION_PROOF = "test_the_detector_tells_a_utility_from_a_word"

_ROOT = Path(__file__).resolve().parents[2]
_SOURCES_FLOOR = 100

#: Un utilitaire Tailwind directionnel PHYSIQUE. La forme compte autant
#: que le nom : ``(?:^|[\\s:])`` exige un début de mot réel (une variante
#: ``md:ml-2`` passe, le ``ml`` de « html-like » non), et la plupart des
#: familles exigent une valeur — sans quoi ``"left"`` nu serait compté.
_PHYSICAL = re.compile(
    r"(?:^|[\s:])(?:!)?("
    r"m[lr]-[\w./\[\]-]+|p[lr]-[\w./\[\]-]+|"
    r"(?:left|right)-[\w./\[\]-]+|"
    r"border-[lr](?:-[\w./\[\]-]+)?|"
    r"rounded-[lr](?:-[\w./\[\]-]+)?|"
    r"text-(?:left|right)"
    r")(?![\w./-])"
)

#: Le plafond par fichier, MESURÉ le 2026-09-02 **après** une première
#: tranche de conversion : 101 → **79**, en portant ``text-left`` →
#: ``text-start`` et ``ml-auto``/``mr-auto`` → ``ms-auto``/``me-auto``
#: sur les 22 sites dont la sémantique est « bord de tête / bord de
#: queue » sans ambiguïté.
#:
#: ⚠️ Les tables de la prop ``align=`` (``ui.table`` et ``ui.text``) sont
#: exclues DÉLIBÉRÉMENT : un ``align="left"`` demande la gauche
#: physique, et le convertir changerait le sens de l'API publique. Leur
#: ouvrir ``start``/``end`` est une décision d'API, pas un ménage.
#:
#: **Il ne peut que baisser.** On n'ajoute pas d'entrée : on écrit la
#: classe logique.
_CEILING: dict[str, int] = {
    "components/data/table/theme.py": 2,
    "components/data/tree/theme.py": 3,
    "components/feedback/avatar/theme.py": 1,
    "components/feedback/notification/theme.py": 6,
    "components/inputs/calendar/calendar.py": 1,
    "components/inputs/calendar/theme.py": 3,
    "components/inputs/combobox/theme.py": 2,
    "components/inputs/date_picker/theme.py": 2,
    "components/inputs/date_range_picker/theme.py": 2,
    "components/inputs/file_upload/theme.py": 9,
    "components/inputs/form_field/theme.py": 1,
    "components/inputs/input/theme.py": 15,
    "components/inputs/month_picker/theme.py": 2,
    "components/inputs/radio/theme.py": 1,
    "components/inputs/select/theme.py": 2,
    "components/inputs/slider/theme.py": 3,
    "components/inputs/switch/theme.py": 1,
    "components/inputs/time_picker/theme.py": 2,
    "components/inputs/toggle_group/theme.py": 1,
    "components/inputs/week_picker/theme.py": 2,
    "components/layout/carousel/theme.py": 2,
    "components/navigation/bottom_bar/theme.py": 1,
    "components/navigation/navbar/theme.py": 1,
    "components/navigation/sidebar/theme.py": 4,
    "components/navigation/stepper/theme.py": 1,
    "components/overlay/tooltip/theme.py": 2,
    "components/primitives/markdown/theme.py": 3,
    "components/primitives/text/theme.py": 2,
}

#: Le total au moment de la pose. Sert au plancher de non-vacuité, pas à
#: l'interdiction — c'est le PLAFOND PAR FICHIER qui mord, sinon un
#: fichier pourrait doubler pendant qu'un autre se vide.
_TOTAL_AT_FREEZE = 79


@functools.lru_cache(maxsize=1)
def _measured() -> dict[str, int]:
    """``chemin relatif → nombre d'utilitaires physiques``.

    Sur les CHAÎNES LITTÉRALES du code, pas sur le texte brut : une
    docstring qui explique ``ml-auto`` ne doit pas compter, sinon ce
    fichier-ci se compterait lui-même et la dette monterait à chaque
    ligne de doc écrite pour la faire baisser.
    """
    found: dict[str, int] = {}
    for source in parsed_sources(COMPONENTS_DIR, floor=_SOURCES_FLOOR):
        total = 0
        for node in ast.walk(source.tree):
            if not (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)):
                continue
            # ````x```` est le rôle de prose du dépôt : une
            # docstring, pas une classe.
            if "``" in node.value:
                continue
            total += len(_PHYSICAL.findall(node.value))
        if total:
            rel = source.path.resolve().relative_to(_ROOT / "bretzel").as_posix()
            found[rel] = total
    return found


def test_the_sweep_reads_something() -> None:
    """Plancher, ancré sur la DÉCOUVERTE de cette gate."""
    assert_sweep_is_not_vacuous()
    mesure = _measured()
    assert mesure, (
        "aucun utilitaire directionnel trouvé dans tout "
        "`bretzel/components` — le détecteur ne reconnaît plus rien. "
        "Retrouve la forme AVANT de croire la dette payée."
    )
    assert sum(mesure.values()) >= _TOTAL_AT_FREEZE // 2, (
        f"seulement {sum(mesure.values())} utilitaires vus contre "
        f"{_TOTAL_AT_FREEZE} au gel : une chute de moitié est plus "
        f"probablement un balayage cassé qu'une migration silencieuse. "
        f"Si elle est réelle, baisse ce plancher DANS le même commit."
    )


def test_no_file_grows_its_physical_debt() -> None:
    """Le cliquet : chaque fichier ne peut que baisser."""
    mesure = _measured()
    monte = {
        chemin: (compte, _CEILING[chemin])
        for chemin, compte in mesure.items()
        if chemin in _CEILING and compte > _CEILING[chemin]
    }
    assert not monte, (
        f"des fichiers ont GROSSI (mesuré, plafond) : {monte}.\n"
        f"  Écris la classe LOGIQUE : `ms-` / `me-` / `ps-` / `pe-` / "
        f"`start-` / `end-` / `border-s` / `border-e` / `rounded-s` / "
        f"`rounded-e` / `text-start` / `text-end`. En `dir=\"ltr\"` elles "
        f"rendent exactement pareil, donc la conversion ne se voit pas ; "
        f"c'est justement pour ça que personne ne la fait spontanément.\n"
        f"  Si le physique est VOULU (un centrage `left-1/2`, un visuel "
        f"qui ne doit pas se retourner), dis-le en commentaire au "
        f"call-site et monte le plafond dans le même commit — pas en "
        f"silence."
    )


def test_no_new_file_joins_the_debt() -> None:
    neufs = sorted(set(_measured()) - set(_CEILING))
    assert not neufs, (
        f"{neufs} portent des classes directionnelles physiques sans "
        f"être dans la dette mesurée. Un composant NEUF n'a aucune raison "
        f"d'en écrire : la forme logique existe et rend pareil."
    )


def test_the_ceiling_does_not_rot() -> None:
    """Une entrée qui n'a plus de dette doit SORTIR de la table.

    Sans ça, le plafond garderait la mémoire d'une dette payée et
    laisserait un fichier la reprendre gratuitement.
    """
    mesure = _measured()
    guéris = sorted(c for c in _CEILING if c not in mesure)
    assert not guéris, (
        f"{guéris} n'ont plus aucune classe physique — retire-les de "
        f"`_CEILING` plutôt que de laisser la table mentir."
    )
    trop_larges = {
        c: (mesure[c], plafond)
        for c, plafond in _CEILING.items()
        if c in mesure and mesure[c] < plafond
    }
    assert not trop_larges, (
        f"le plafond est plus haut que la dette réelle (mesuré, "
        f"plafond) : {trop_larges}. Descends-le — un cliquet qui garde du "
        f"mou n'est pas un cliquet."
    )


def test_the_detector_tells_a_utility_from_a_word() -> None:
    """Les deux versants : il reconnaît, et il épargne.

    Le versant LICITE est celui qui compte ici. Les trois comptes faux
    de la thèse venaient tous de là — un détecteur trop large qui
    ramassait des valeurs d'énumération et des mots de prose.
    """
    # Il mord.
    for classe in ("ml-auto", "pr-2", "left-1/2", "rounded-l-none",
                   "text-left", "border-r-0", "md:ml-4", "!mr-1"):
        assert _PHYSICAL.search(f"flex {classe} gap-2"), classe

    # Il épargne — et chacun de ces cas a REELLEMENT gonflé un compte.
    for innocent in ("left", "right", "start", "end", "text-start",
                     "ms-auto", "pe-2", "border-s", "rounded-e-none",
                     "align-left-ish", "overflow-x-hidden", "duration-200"):
        assert not _PHYSICAL.search(f"flex {innocent} gap-2"), innocent

    # Un mot nu au DÉBUT d'une chaîne non plus — c'est la forme exacte
    # d'une valeur d'énumération (``placement="left"``).
    for nu in ("left", "right"):
        assert not _PHYSICAL.search(nu), nu
