"""Gate ratchet — la liste des ``bz-data`` bâtis à la main ne grossit pas.

C'est la **dette n°1 du socle** (memory ``project_scope_literal_debt``) :
un composant à état client écrit son scope en concaténant une chaîne
``"{...$bz.<fabrique>.scope," + … + "}"``, avec la même bascule « valeur
locale → ``{state, target}`` » plus ``server_sync_marker``. Personne n'a
extrait le bloc, donc chaque composant neuf en recopie un.

**Pourquoi une gate plutôt qu'une note.** La note existait, dans
``todo.md``, et elle a menti trois fois en un mois — chaque fois d'un
composant de plus, chaque fois vers le bas :

===================  ==========================================
comptage             résultat
===================  ==========================================
memory (juillet)     5 composants
``todo.md``          9 copies, 8 fichiers
grep par NOM         12 définitions, 11 fichiers
grep par FORME       15 occurrences, **14 fichiers**
===================  ==========================================

La note prévenait pourtant elle-même que « chacun renomme, donc un grep
sur un seul nom sous-compte la dette ». C'est arrivé à la note. Les trois
derniers trouvés — ``tooltip``, ``tabs``, ``tree`` — n'ont **aucun**
helper nommé : ils assemblent le littéral en ligne, donc aucun grep sur
``_build_bz_data`` / ``_scope_literal`` ne pouvait les voir.

D'où la détection **par la FORME**, pas par le nom : ce qui identifie un
scope bâti à la main, c'est le littéral ``{...$bz.`` dans une source
Python. Renommer le helper ne dissout pas la dette, et ne trompe plus le
comptage.

**Ce que la gate autorise.** Elle ne demande pas de payer la dette
aujourd'hui — l'extraction doit se faire d'UN bloc (la memory dit
pourquoi : deux paramètres redondants à supprimer *à l'extraction*, les
corriger dans un seul fichier échangerait la duplication contre une
divergence). Elle demande seulement que le 15ᵉ composant ne s'ajoute pas
en silence : si tu en écris un, tu passes par ici et tu décides.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    component_sources,
)

#: Preuve de morsure : contrôle POSITIF — la marque de scope garde une orthographe que le
#: détecteur reconnaît.
MUTATION_PROOF = "test_the_sweep_reads_something"

_ROOT = Path(__file__).resolve().parents[2]

#: La marque d'un scope assemblé à la main : l'étalement de la fabrique
#: partagée dans un littéral d'objet JS. Indépendante du nom du helper —
#: c'est tout l'intérêt (cf. le docstring).
_MARK = "{...$bz."

#: Ce qui n'est PAS de la dette : un scope qui ÉTALE la fabrique
#: partagée et n'y ajoute rien. C'est la destination de l'extraction,
#: pas son point de départ — le refuser demanderait au premier composant
#: qui fait déjà bien de s'inscrire dans une liste de dette.
#:
#: La détection reste par la FORME (cf. le docstring : renommer un helper
#: ne dissout pas la dette). On affine seulement CE QU'EST la forme
#: fautive : un littéral qu'on CONCATÈNE, pas un littéral complet.
#:
#: ⚠️ Mesuré avant d'assouplir, le 2026-09-06 : sur les 14 fichiers de la
#: dette, **zéro** porte un littéral pur — ils ajoutent tous au moins la
#: bascule « valeur locale → {state, target} ». L'exception ne relâche
#: donc rien sur la population existante, et
#: ``test_a_hand_built_scope_is_still_caught`` le tient.
_PURE_SPREAD = re.compile(r"^\{\.\.\.\$bz\.[A-Za-z0-9_.]+\}$")

#: Les littéraux de chaîne d'une source Python qui contiennent la marque.
_LITERAL = re.compile(r'"([^"\n]*\{\.\.\.\$bz\.[^"\n]*)"')


def hand_builds_a_scope(source: str) -> bool:
    """Cette source assemble-t-elle un ``bz-data`` à la main ?

    Oui dès qu'un littéral portant la marque n'est pas un étalement pur.
    Une source dont TOUS les littéraux marqués sont purs est propre.
    """
    if _MARK not in source:
        return False
    literals = _LITERAL.findall(source)
    if not literals:
        # La marque est là mais hors d'un littéral d'une seule ligne :
        # concaténation multi-lignes, f-string découpée… — donc bâti à
        # la main, et c'est le cas le plus fautif.
        return True
    return any(not _PURE_SPREAD.match(lit) for lit in literals)


#: Dette MESURÉE le 2026-08-13. **Cette liste ne peut que rétrécir.**
#: On n'y ajoute pas un fichier : on extrait le bloc commun.
#: ``select`` porte DEUX occurrences (single + multi) et compte pour un
#: fichier — l'unité qui compte ici est le composant qui a recopié.
_HAND_BUILT: frozenset[str] = frozenset({
    "components/data/accordion/accordion.py",
    # 15ᵉ, le 2026-09-06, et c'est une DÉCISION — pas un oubli, pas un
    # silence : `ui.diagram` a reçu une prop ⇄ two-way (le nœud
    # sélectionné), et `client-reactive-surface.md` § *La règle* ne
    # laisse pas le choix — « la sélection → ⇄ two-way ».
    #
    # Mesuré avant de trancher : sur les 31 composants two-way du
    # catalogue, les 13 qui ont AUSSI un slab runtime partagé bâtissent
    # tous leur littéral. C'est la bascule « valeur locale → cellule du
    # magasin » qui l'impose, et elle est le cœur même de cette dette.
    # Les 18 autres n'ont aucun scope partagé : ils inlinent tout.
    #
    # L'alternative pesée et écartée : réinliner les cinq méthodes de
    # `$bz.diagram.scope` dans CHAQUE nœud. Ça sortait de la liste au
    # prix d'une centaine d'octets par nœud et d'un slab supprimé.
    "components/data/diagram/diagram.py",
    "components/data/tree/tree.py",
    "components/inputs/combobox/combobox.py",
    "components/inputs/number_input/number_input.py",
    "components/inputs/select/select.py",
    "components/inputs/signature_pad/signature_pad.py",
    "components/inputs/slider/slider.py",
    "components/inputs/time_picker/time_picker.py",
    "components/layout/carousel/carousel.py",
    "components/layout/resizable/resizable.py",
    "components/navigation/pagination/pagination.py",
    "components/navigation/stepper/stepper.py",
    "components/navigation/tabs/tabs.py",
    "components/overlay/tooltip/tooltip.py",
})


@functools.lru_cache(maxsize=1)
def _found() -> frozenset[str]:
    """Caché : les trois tests de ce fichier l'appellent, et sans cache il
    relit les 256 sources trois fois. ``frozenset`` et pas ``set`` — un
    mutable derrière un ``lru_cache`` laisserait un test empoisonner les
    autres."""
    found: set[str] = set()
    for path in component_sources():
        if hand_builds_a_scope(path.read_text(encoding="utf-8-sig")):
            found.add(
                path.relative_to(_ROOT / "bretzel").as_posix()
            )
    return frozenset(found)


def test_the_sweep_reads_something() -> None:
    assert_sweep_is_not_vacuous()
    assert _found(), (
        "aucun littéral de scope trouvé dans tout `bretzel/components` — "
        "la marque a changé de forme et cette gate ne garde plus rien. "
        "Retrouve la nouvelle orthographe AVANT de croire la dette payée."
    )


def test_no_new_component_hand_builds_its_scope() -> None:
    new = sorted(_found() - _HAND_BUILT)
    assert not new, (
        f"{new} assemblent leur `bz-data` à la main sans être dans la "
        f"dette mesurée.\n"
        f"  C'est la dette n°1 du socle, et elle a déjà grossi de 5 à 14 "
        f"composants faute d'une gate. N'ajoute pas d'entrée ici : le "
        f"livrable est l'extraction du bloc commun (`todo.md` § « Le "
        f"littéral de scope »), et elle se fait d'UN bloc.\n"
        f"  Si tu dois vraiment passer, dis-le dans le commit — pas en "
        f"silence."
    )


def test_a_hand_built_scope_is_still_caught() -> None:
    """L'assouplissement n'a pas rendu le détecteur aveugle.

    Deux versants, sur des sources fabriquées : la forme fautive — un
    littéral qu'on complète — reste attrapée, et l'étalement pur passe.
    C'est le seul moyen de savoir si l'exception a une largeur ou si
    elle a une porte.
    """
    assert hand_builds_a_scope('attrs["bz-data"] = "{...$bz.x.scope, v: 1}"')
    assert hand_builds_a_scope('"{...$bz.x.scope," + body + "}"')
    # La marque hors de tout littéral d'une ligne : concaténation
    # multi-lignes, le cas de `tabs` / `tree`.
    assert hand_builds_a_scope("parts = [\n  '{...$bz.x.scope'\n]")
    assert not hand_builds_a_scope('attrs["bz-data"] = "{...$bz.x.scope}"')
    assert not hand_builds_a_scope("aucune marque ici")


def test_the_debt_list_stays_true() -> None:
    """Une entrée payée doit sortir, sinon la dette affichée ment.

    Le symétrique de la précédente : sans elle, un composant migré vers
    le futur helper resterait listé et le compteur donnerait la dette
    d'hier pour celle d'aujourd'hui — exactement ce que `todo.md` a fait
    trois fois.
    """
    paid = sorted(_HAND_BUILT - _found())
    assert not paid, (
        f"{paid} ne portent plus de littéral de scope : retire-les de "
        f"`_HAND_BUILT` pour que le compte restant soit juste."
    )
