"""``examples/ecole`` ne décide AUCUNE taille de texte lui-même.

Pourquoi cette gate existe
--------------------------
Le cahier des charges de l'app porte une exigence, EF-U3 : *« rien ne
s'affiche sous 19 px — la tablette est un poste de travail, pas une
consultation »*. L'app l'a tenue à la lettre, en posant
``html { font-size: 19px }`` dans son thème. Devant l'écran,
l'utilisateur a tranché le 2026-09-12 : *« c'est trop gros »*. À cette
racine, la semaine d'emploi du temps sortait de l'écran — l'exigence
était tenue et son intention ratée.

La racine est donc partie, et avec elle le plancher en pixels que
``tests/probes/probe_ecole.py`` mesurait. Ce qui reste vrai, et que
cette gate tient : **l'app n'écrit aucune classe de taille**. Ça a deux
conséquences, et la seconde est la raison d'être du fichier :

1. la taille du texte vient d'un seul endroit — les paliers de
   composant (``size="lg"``, ``ui.heading``), donc du thème ;
2. la densité a un seul PROPRIÉTAIRE. C'est ``core/theme.py``, qui la
   prend en ``base=COMPACT`` — et un ``text-sm`` posé sur un écran la
   contredirait en silence, sans apparaître nulle part comme une
   décision.

⚠️ **Le thème est exempté, et c'est tout l'intérêt.** ``core/theme.py``
n'est pas un call-site : c'est le fichier DONT LE MÉTIER est de fixer des
tailles. L'exempter n'affaiblit pas la gate, ça la rend précise — elle dit
« la taille se décide au thème », pas « personne n'écrit jamais de
taille ».

Ça reste une règle d'app, pas du framework : elle se relâche
délibérément si le besoin remonte. Mais alors le constat ③ du probe perd
son sujet, et c'est lui qu'il faut reprendre — pas cette liste qu'il
faut allonger en silence.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    REPO_ROOT,
    ParsedSource,
    code_string_literals,
    parsed_sources,
)

ECOLE = REPO_ROOT / "examples" / "ecole"

#: Le fichier DONT LE MÉTIER est de fixer des tailles.
#:
#: Une liste nommée, courte, et qui ne s'allonge pas toute seule : c'est
#: la différence entre une exemption et un trou. Ajouter un nom ici veut
#: dire qu'un écran a gagné le droit de décider sa typographie, ce qui est
#: précisément ce que la gate refuse.
#:
#: ⚠️ ``preset.py`` y était jusqu'au 2026-09-13 : l'app portait sa propre
#: échelle. Elle vient maintenant de ``bretzel.theme.presets.COMPACT``,
#: donc l'exemption n'a plus qu'un fichier — et ``theme.py`` n'écrit en
#: fait plus aucune taille, il ne garde que les couleurs. Le nom reste
#: parce que c'est LÀ que la question se décide, pas parce qu'il en use.
LE_THEME = ("theme.py",)

#: Les utilitaires Tailwind qui FIXENT une taille de police.
#:
#: ``\b`` en tête n'est pas décoratif : sans lui, ``context-xl`` (ou
#: n'importe quel mot finissant par ``text``) déclencherait la gate.
TAILLE_DE_TEXTE = re.compile(r"\btext-(xs|sm|base|lg|[2-9]?xl)\b")

#: Ce qui prouve que le balayage a vraiment vu des chaînes de CLASSES, et
#: pas seulement des noms de colonnes SQL et des libellés français.
#:
#: Sans ce second plancher, la gate resterait verte si ``examples/ecole``
#: cessait d'écrire la moindre classe — ou si le lecteur cassait. Elle
#: affirmerait « aucune taille » en n'ayant regardé aucune classe.
RESSEMBLE_A_DES_CLASSES = re.compile(
    r"\b(bg-|border-|flex\b|font-|grid-cols-|gap-|px-|py-|rounded-|"
    r"text-(muted|primary|error|center))"
)

#: 37 fichiers Python sous ``examples/ecole`` le 2026-09-12, le thème
#: déduit.
FICHIERS_ATTENDUS = 30

#: 15 chaînes portant des classes le 2026-09-12 (``classes=`` + les
#: tables de teintes de l'emploi du temps et du plan de salle).
CHAINES_DE_CLASSES_ATTENDUES = 10


def sources_de_lecole() -> list[ParsedSource]:
    """Les sources d'``examples/ecole``, prises dans le balayage partagé.

    Passer par ``parsed_sources(examples/)`` plutôt que par un ``rglob``
    local a deux effets qu'un balayage maison n'a pas : le plancher fort
    d'``EXAMPLES_FLOOR`` s'applique d'abord, et un fichier illisible LÈVE
    au lieu de disparaître (cf. le BOM qui avait sorti un fichier de sept
    gates pendant des mois).
    """
    tous = parsed_sources(REPO_ROOT / "examples", floor=EXAMPLES_FLOOR)
    return [s for s in tous
            if ECOLE in s.path.parents and s.path.name not in LE_THEME]


def test_le_balayage_voit_bien_lapp():
    """Le plancher de non-vacuité : les deux moitiés du constat."""
    sources = sources_de_lecole()
    assert len(sources) >= FICHIERS_ATTENDUS, (
        f"seulement {len(sources)} fichiers d'examples/ecole balayés "
        f"(>= {FICHIERS_ATTENDUS} attendus) — le chemin a bougé, et "
        f"« l'app n'écrit aucune taille » serait affirmé sur rien."
    )

    avec_classes = [
        texte
        for s in sources
        for noeud in code_string_literals(s.tree)
        if RESSEMBLE_A_DES_CLASSES.search(texte := noeud.value)
    ]
    assert len(avec_classes) >= CHAINES_DE_CLASSES_ATTENDUES, (
        f"seulement {len(avec_classes)} chaîne(s) de classes trouvées "
        f"(>= {CHAINES_DE_CLASSES_ATTENDUES} attendues) — le lecteur ne "
        f"voit plus les classes, donc il ne peut plus voir une taille."
    )


def test_lapp_necrit_aucune_taille_de_texte():
    """L'interdiction elle-même, sur ce que le code PRODUIT.

    ``code_string_literals`` écarte les chaînes nues en instruction,
    docstrings comprises : ce paragraphe-ci nomme ``text-sm`` sans être
    une infraction, et une gate qui lisait le texte brut aurait compté
    sa propre explication comme une occurrence.
    """
    fautes = [
        f"{s.path.relative_to(REPO_ROOT)}:{noeud.lineno} — "
        f"{TAILLE_DE_TEXTE.search(valeur).group(0)} dans {valeur[:60]!r}"
        for s in sources_de_lecole()
        for noeud in code_string_literals(s.tree)
        if TAILLE_DE_TEXTE.search(valeur := noeud.value)
    ]
    assert not fautes, (
        "examples/ecole fixe une taille de texte à la main :\n  "
        + "\n  ".join(fautes)
        + "\n\nUn palier de composant (size=…, ui.heading) dit la même "
        "chose en laissant le thème décider. Si la taille doit vraiment "
        "être écrite là, c'est le constat ③ de tests/probes/"
        "probe_ecole.py qu'il faut reprendre : il gèle les genres de "
        "petit texte en supposant qu'ils ont un seul propriétaire."
    )


@pytest.mark.parametrize(
    "valeur, mord",
    [
        # Le versant INTERDIT — la gate doit rougir.
        ("text-sm font-semibold text-text truncate", True),
        ("text-xs uppercase tracking-wide", True),
        ("grid-cols-[76px_repeat(6,minmax(92px,1fr))] text-2xl", True),
        ("text-base", True),
        # Le versant LICITE — c'est lui qui trouve les bugs de gate.
        # Une couleur, un alignement, un mot qui FINIT par « text ».
        ("bg-primary/5 border-l-2 border-l-primary", False),
        ("text-muted", False),
        ("text-error ml-0.5", False),
        ("text-center", False),
        ("context-xl", False),
        ("contexte : text", False),
    ],
)
def test_une_violation_fabriquee_est_vue_et_pas_sa_voisine(
    valeur: str, mord: bool,
):
    """La preuve de morsure, dans les deux sens (règle 8).

    Qu'un détecteur rougisse sur un cas fabriqué ne dit rien de son taux
    de faux positifs : dans ce dépôt, les deux seuls bugs de gate trouvés
    en remboursant la dette l'ont été par le versant licite.
    """
    assert bool(TAILLE_DE_TEXTE.search(valeur)) is mord
