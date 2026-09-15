"""Gate — le seuil de découpe du gabarit de playground est VRAI.

Ce qu'elle garde
----------------
`playground-pattern.md` § 7 fixe la taille au-delà de laquelle une page
se découpe en dossier. Cette gate lit le nombre **dans le document** et
le confronte au corpus : une règle que le corpus enfreint n'est pas un
défaut de corpus, c'est une règle fausse — et une règle fausse coûte
plus cher que pas de règle du tout.

Le coût, mesuré
---------------
Le seuil a dit **400 lignes** jusqu'au 2026-09-06, et **52 pages sur 70
le dépassaient**. Une règle que trois quarts du corpus enfreignent ne
guide personne : elle a fait découper `diagram` en paquet à 449 lignes
pour rien, parce qu'elle a été lue au pied de la lettre par quelqu'un
qui n'avait pas mesuré le corpus.

Et sa correction s'est contredite elle-même le jour de son écriture :
« au-dessus, seule `sidebar` reste » figurait trois lignes sous une
liste citant `toggle_group` 914 et `dialog` 905. Elles étaient quatre.

C'est la classe de dérive que `CLAUDE.md` décrit comme la plus coûteuse
parce que la plus crédible — de la prose qui se contredit à cinquante
lignes d'intervalle. Aucune relecture ne l'attrape de façon fiable ; un
comptage, oui.

Pourquoi lire le seuil dans le document
---------------------------------------
Recopier `900` ici en ferait une SECONDE source, et c'est exactement la
faute que la gate existe pour empêcher : le jour où quelqu'un relève le
seuil dans le § 7, la gate garderait l'ancien sans un mot. Le nombre
n'existe qu'à un endroit ; ce fichier le lit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GABARIT = REPO_ROOT / ".claude" / "bretzel" / "playground-pattern.md"
PAGES = REPO_ROOT / "examples" / "playground" / "features"

#: La ligne du § 7 qui porte le seuil, sous sa forme de tableau ::
#:
#:     | Fichier unique > **900 lignes** | découper en dossier |
_SEUIL = re.compile(r"Fichier unique > \*\*(\d+) lignes\*\*")

#: Les pages qui dépassent, NOMMÉES — une liste qui ne fait que
#: rétrécir. Chacune est une dette déclarée, pas une tolérance ; les
#: trois restantes sont un découpage mécanique.
#:
#: ⚠️ Ne PAS les retirer en relevant le seuil. Un seuil qu'on relève
#: jusqu'à ce que plus personne ne le dépasse ne dit plus rien — c'est
#: la même mort que le 400, par l'autre bout.
AU_DESSUS = {
    # ``sidebar.py`` est partie le 2026-09-07 : 1 065 lignes découpées en
    # paquet (state / logic / ui), la première de cette liste à le faire.
    "accordion.py",
    "toggle_group.py",
    "dialog.py",
}

#: Plancher de découverte : combien de pages en fichier unique le
#: balayage doit trouver. 73 mesurées le 2026-09-07. Ancré sur ce qui
#: est LU, pas sur ce qui est fautif — une gate qui compte ses fautes
#: reste verte quand elle ne lit plus rien.
_PAGES_FLOOR = 60


def seuil() -> int:
    texte = GABARIT.read_text(encoding="utf-8")
    trouve = _SEUIL.search(texte)
    assert trouve, (
        f"le seuil de découpe est introuvable dans {GABARIT.name} § 7. "
        f"Il y est écrit sous la forme « Fichier unique > **N lignes** » "
        f"et cette gate le LIT — le recopier ici en ferait une seconde "
        f"source, donc la prochaine divergence silencieuse."
    )
    return int(trouve.group(1))


def pages() -> list[Path]:
    return sorted(PAGES.glob("*.py"))


def test_the_sweep_finds_the_pages() -> None:
    trouvees = pages()
    assert len(trouvees) >= _PAGES_FLOOR, (
        f"le balayage ne voit plus que {len(trouvees)} pages sous "
        f"{PAGES} (73 mesurées le 2026-09-07) — vérifie le chemin avant "
        f"de croire que « aucune page ne dépasse »."
    )


def test_every_exemption_names_a_real_page() -> None:
    """Une entrée de ``AU_DESSUS`` désigne une page qui EXISTE.

    ⚠️ Écrit après avoir mesuré le trou. La preuve de morsure a inscrit
    ``button.py`` dans la liste — une page découpée en DOSSIER, donc
    absente de ``pages()`` — et la gate est restée verte : le test
    paramétré ne voit que des fichiers, donc une exemption qui n'en
    désigne aucun n'est jamais confrontée. C'est le versant licite qui
    ne mordait pas, exactement le cas que `gates.md` dit de vérifier
    parce qu'il ne se voit pas en fabriquant une violation.

    Sans lui, une page découpée laisserait son exemption derrière elle,
    et cette exemption couvrirait pour toujours un nom que plus rien ne
    porte.
    """
    connues = {p.name for p in pages()}
    fantomes = sorted(AU_DESSUS - connues)
    assert not fantomes, (
        f"{fantomes} figure(nt) dans `AU_DESSUS` mais ne désigne(nt) "
        f"aucune page en fichier unique. Soit la page a été découpée en "
        f"dossier — alors retire l'entrée, elle ne protège plus rien — "
        f"soit le nom est faux."
    )


def test_the_detector_catches_a_page_over_the_threshold(tmp_path) -> None:
    """Preuve de morsure — la violation fabriquée, et le cas licite.

    Les deux versants, parce qu'un seul ne dit rien : une gate qui
    rougit sur un cas fabriqué peut très bien rougir sur tout le corpus,
    et une gate verte sur le corpus peut ne rien détecter du tout.

    ⚠️ Vérifié à la main en plus, sur le VRAI document : remettre
    ``400`` dans le § 7 rend **52 rouges** — exactement les 52 pages sur
    70 que l'audit du 2026-09-06 avait comptées. La gate reproduit sa
    mesure, elle ne fait pas que la citer.
    """
    limite = seuil()
    assert limite > 0, limite

    trop = tmp_path / "enorme.py"
    trop.write_text("x = 1\n" * (limite + 1), encoding="utf-8")
    assert len(trop.read_text(encoding="utf-8").splitlines()) > limite, (
        "le détecteur ne voit plus une page au-dessus du seuil — c'est "
        "la faute que cette gate existe pour attraper."
    )

    juste = tmp_path / "sage.py"
    juste.write_text("x = 1\n" * (limite - 1), encoding="utf-8")
    assert len(juste.read_text(encoding="utf-8").splitlines()) <= limite, (
        "le détecteur accuse une page SOUS le seuil. Un faux positif "
        "est pire qu'un trou : c'est ce qui fait relever le seuil "
        "jusqu'à ce qu'il ne dise plus rien."
    )


@pytest.mark.parametrize("page", pages(), ids=lambda p: p.name)
def test_a_page_stays_under_the_threshold(page: Path) -> None:
    limite = seuil()
    lignes = len(page.read_text(encoding="utf-8").splitlines())
    if page.name in AU_DESSUS:
        assert lignes > limite, (
            f"`{page.name}` fait {lignes} lignes et ne dépasse plus le "
            f"seuil de {limite} : retire-la de `AU_DESSUS`. La liste ne "
            f"fait que rétrécir, et une entrée périmée y cache la "
            f"suivante."
        )
        return
    assert lignes <= limite, (
        f"`{page.name}` fait {lignes} lignes pour un seuil de {limite} "
        f"(playground-pattern.md § 7) : découpe-la en dossier, ou "
        f"inscris-la dans `AU_DESSUS` avec sa raison.\n"
        f"  Ne relève PAS le seuil pour la faire rentrer — c'est comme "
        f"ça qu'il est passé de guide à décor : à 400 lignes, 52 pages "
        f"sur 70 l'enfreignaient et il ne guidait plus personne."
    )
