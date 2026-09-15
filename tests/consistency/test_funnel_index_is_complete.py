"""Gate : l'index du funnel liste tous ses fichiers, et rien d'autre.

`.claude/bretzel/README.md` s'annonce comme « toujours lu en premier » et
comme la carte du dossier. Le 2026-08-01 il référençait **18 des 27**
fichiers : neuf documents n'étaient atteignables par aucun chemin de
lecture, dont deux (`chantier-socle`, `test-audit`) que **rien** dans tout
le dépôt ne citait — un tracker de chantier actif parmi eux.

Un fichier hors index est pire qu'un fichier absent : il continue de
vieillir, et le prochain qui le trouve par `ls` ne sait pas s'il décrit le
framework d'aujourd'hui ou une session de juillet. C'est exactement ce qui
rendait l'audit du dossier nécessaire.

Le sens inverse compte autant : un lien vers un fichier supprimé envoie le
lecteur dans le vide.

**Portée honnête.** Cette gate police la *complétude de la carte*, pas la
justesse des descriptions ni le classement d'un fichier dans la bonne
section (📘 Référence / 🚧 Tracker / ✏️ Design ouvert). Elle répond à « est-ce
que quelque chose est silencieusement introuvable ? », la dérive que la
relecture manuelle re-découvre à chaque passage.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import pytest

_FUNNEL = Path(__file__).resolve().parents[2] / ".claude" / "bretzel"
_INDEX = _FUNNEL / "README.md"

# Les liens markdown relatifs de l'index : ``[texte](fichier.md)``. On ne
# prend que les cibles ``.md`` sans ``/`` — un lien vers `bretzel/...` ou
# vers une ancre externe n'est pas une entrée d'index.
_LINK = re.compile(r"\]\((?!https?:)([^)/#]+\.md)\)")


# Cachés : la gate est paramétrée par fichier, donc sans mémo chaque cas
# relit l'index et re-globe le dossier.
@functools.lru_cache(maxsize=1)
def _indexed() -> frozenset[str]:
    return frozenset(_LINK.findall(_INDEX.read_text(encoding="utf-8")))


@functools.lru_cache(maxsize=1)
def _on_disk() -> frozenset[str]:
    return frozenset(p.name for p in _FUNNEL.glob("*.md")) - {"README.md"}


def test_index_exists() -> None:
    assert _INDEX.exists(), f"index du funnel absent : {_INDEX}"


def test_discovery_non_trivial() -> None:
    """Garde-fou : si le glob ou la regex ne rendent plus rien, la gate est
    aveugle et passerait sur un dossier vide."""
    assert len(_on_disk()) >= 15, "le dossier funnel semble vide — glob cassé ?"
    assert len(_indexed()) >= 15, (
        "aucun lien relatif trouvé dans README.md — la mise en forme de "
        "l'index a changé et la regex ne matche plus, donc la gate ne garde "
        "plus rien."
    )


@pytest.mark.parametrize("name", sorted(_on_disk()))
def test_every_funnel_file_is_indexed(name: str) -> None:
    assert name in _indexed(), (
        f"`.claude/bretzel/{name}` n'est cité nulle part dans l'index du "
        f"funnel (README.md).\n"
        f"  Un fichier hors index continue de vieillir sans lecteur : "
        f"personne ne sait s'il décrit le framework d'aujourd'hui ou une "
        f"session passée.\n"
        f"  Ajoute-le à la section qui correspond à sa nature — 📘 Référence "
        f"(comment ça marche aujourd'hui), 🚧 Tracker (chantier en cours) ou "
        f"✏️ Design ouvert (pas encore exécuté) — ou supprime-le : git est "
        f"l'archive."
    )


def test_index_has_no_dangling_link() -> None:
    dangling = sorted(_indexed() - _on_disk() - {"README.md"})
    assert not dangling, (
        f"l'index du funnel pointe vers des fichiers qui n'existent pas : "
        f"{dangling}. Un lien mort envoie le lecteur dans le vide — retire "
        f"la ligne (le fichier a été replié dans git : "
        f"`git log --diff-filter=D -- .claude/bretzel/`)."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : un lien Markdown vers un fichier du funnel est reconnu.

    L'index est comparé au disque ; si la regex cessait d'extraire les
    liens, l'index paraîtrait vide et « tout fichier est indexé »
    deviendrait faux dans les deux sens sans que rien ne le dise.
    """
    assert _LINK.search("voir [les pièges](traps.md) avant").group(1) == "traps.md"
    for licit in ("[ext](https://x.md)", "[sous-dossier](a/b.md)", "[ancre](#x)"):
        assert not _LINK.search(licit), f"{licit!r} : faux positif"
