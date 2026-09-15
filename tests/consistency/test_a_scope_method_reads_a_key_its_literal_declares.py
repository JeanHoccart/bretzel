"""Gate — un corps de méthode de scope n'adresse pas une clé fantôme.

Ce qu'elle garde
----------------
Le ``bz-data`` d'un composant porte deux choses dans le même littéral :
les CLÉS qui deviendront des signaux (``value: "09:30"``) et des CORPS
DE MÉTHODE qui les lisent (``_read() { return this.value; }``). Les deux
sont écrits par le même ``render()``, mais **par des chemins de code
différents** — et rien ne les confrontait.

Quand ils divergent, le résultat est le pire cas possible : ``this.val``
sur un scope qui déclare ``value`` rend ``undefined``, l'écriture crée
une propriété morte sur le proxy, et **il ne se passe rien**. Pas
d'erreur JS, pas de 500, pas de test rouge. Le panneau est simplement
inerte.

Le défaut qui l'a motivée (2026-09-07, TimePicker)
--------------------------------------------------
Les treize clés de scope du catalogue se sont normalisées en ``value``.
Douze composants ont suivi ; ``TimePicker._value_target()`` rendait
``"this.val"`` **en dur**, à un site que le balayage de renommage n'a
pas couvert. Résultat mesuré : les deux colonnes du panneau ne
répondaient plus au clic, en mode littéral uniquement.

Ce qui l'a attrapé : ``probe_time_picker_cells``, un probe Playwright —
donc l'étage le plus cher et le plus lent, pour une faute qui est
VISIBLE DANS LA CHAÎNE ÉMISE. Les 19 307 tests rapides étaient verts, y
compris ``test_scope_keys_match_emission`` : elle confronte la clé
déclarée à celle du ``_serverSync``, deux sources qui lisaient DÉJÀ
toutes deux ``_scope_keys``. Le corps de méthode, lui, n'était lu par
personne.

Le composant documentait pourtant le piège, en toutes lettres, dans la
docstring de la fonction fautive : « un corps de méthode n'est PAS
enveloppé dans ``with($scope)``… il faut ``this.X`` ». Savoir n'est pas
garder — c'est le point de la règle 8 du charter.

Pourquoi c'est mécanique
------------------------
« Ce composant est-il bien câblé » ne se mesure pas. « Ce littéral
référence ``this.X`` alors qu'il ne déclare pas ``X`` » se mesure sur la
chaîne rendue, sans navigateur, en une seconde.

⚠️ Un ``this.X`` peut aussi désigner un membre du SLAB étalé
(``{...$bz.time.scope, …}``) — ``_parts``, ``setActive``, … La gate
l'admet en lisant les slabs du runtime, jamais en devinant : un nom
inconnu des DEUX sources est un fantôme.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import (
    assert_runtime_sweep_is_not_vacuous,
    assert_sweep_is_not_vacuous,
    bz_data_of,
    public_component_classes,
    runtime_sources,
    ui_name_of,
)

#: Combien de littéraux portant au moins un ``this.X`` le balayage doit
#: trouver pour que « zéro fantôme » veuille dire quelque chose.
#:
#: Ancré sur la DÉCOUVERTE, pas sur la population fautive : c'est le
#: nombre de littéraux réellement EXAMINÉS. Une gate qui compte ses
#: fautes reste verte quand elle ne lit plus rien. 16 mesurés le
#: 2026-09-07 ; le plancher laisse la marge d'un composant retiré.
_EXAMINES_FLOOR = 12


def _declared_keys(literal: str) -> set[str]:
    """Les clés de PREMIER NIVEAU du littéral (``nom:`` ou ``nom()``).

    Un scanner à profondeur plutôt qu'une regex globale : le corps d'une
    méthode contient lui aussi des ``mot:`` (un ternaire, un objet
    intermédiaire) et les compter ferait passer un fantôme pour une clé.

    ⚠️ Ne PAS avancer le curseur au-delà du nom reconnu. La première
    version le faisait et sautait la parenthèse ouvrante de ``_read(`` :
    la fermante ramenait la profondeur à zéro, tout le reste du littéral
    passait pour du premier niveau, et ``Tree`` était accusé à tort. Une
    gate dont le PARSEUR est faux accuse le corpus.
    """
    keys: set[str] = set()
    depth = 0
    for match in re.finditer(r"[{\[(]|[}\])]|(\w+)\s*[:(]", literal):
        name = match.group(1)
        if name is not None:
            if depth == 1:
                keys.add(name)
            if match.group(0).rstrip().endswith("("):
                depth += 1
            continue
        depth += 1 if match.group(0) in "{[(" else -1
    return keys


def _spread_slabs(literal: str) -> set[str]:
    """Les slabs runtime étalés — ``...$bz.time.scope`` → ``time.scope``."""
    return set(re.findall(r"\.\.\.\$bz\.([\w.]+)", literal))


def _slab_members(path: str) -> set[str]:
    """Les noms définis par un slab ``$bz.<path>`` dans le runtime.

    Volontairement LARGE : tout identifiant en position de clé dans le
    module qui porte ce slab. Une gate d'interdiction se trompe du bon
    côté en admettant trop — un faux négatif laisse passer un fantôme,
    un faux positif accuse un composant sain et finit désarmé.
    """
    root = path.split(".")[0]
    members: set[str] = set()
    for name, source in runtime_sources().items():
        if f"$bz.{root}" not in source:
            continue
        members |= set(re.findall(r"^\s*(\w+)\s*[:(]", source, re.M))
    return members


def _ghosts(cls: type) -> tuple[set[str], str] | None:
    """Les ``this.X`` du littéral que rien ne déclare — ``None`` si aucun."""
    literal = bz_data_of(cls)
    if not literal:
        return None
    referenced = set(re.findall(r"this\.(\w+)", literal))
    if not referenced:
        return None
    known = _declared_keys(literal)
    for slab in _spread_slabs(literal):
        known |= _slab_members(slab)
    ghosts = referenced - known
    return (ghosts, literal) if ghosts else None


_PORTEURS = [
    cls for cls in public_component_classes() if (bz_data_of(cls) or "")
]


@pytest.mark.parametrize("cls", _PORTEURS, ids=ui_name_of)
def test_no_scope_method_reads_a_ghost_key(cls: type) -> None:
    found = _ghosts(cls)
    assert found is None, (
        f"``ui.{ui_name_of(cls)}`` : son ``bz-data`` appelle "
        f"{sorted(found[0])} sur ``this``, mais ne déclare "
        f"AUCUNE de ces clés et aucun slab étalé ne les définit.\n\n"
        f"  {found[1][:400]}\n\n"
        f"Un corps de méthode n'est pas enveloppé dans ``with($scope)`` : "
        f"il doit adresser ``this.<clé>``, et la clé doit venir de "
        f"``self._scope_keys(prop)`` — jamais d'un littéral retapé. "
        f"Sinon le composant devient INERTE en mode littéral, sans "
        f"erreur JS et sans un test rouge : c'est exactement ce qui est "
        f"arrivé au TimePicker le 2026-09-07, et seul un probe "
        f"Playwright l'a vu."
    )


def test_the_sweep_actually_read_something() -> None:
    """Plancher — le balayage a EXAMINÉ des littéraux, pas juste tourné."""
    assert_sweep_is_not_vacuous()
    assert_runtime_sweep_is_not_vacuous()
    examines = [
        cls
        for cls in _PORTEURS
        if re.search(r"this\.\w+", bz_data_of(cls) or "")
    ]
    assert len(examines) >= _EXAMINES_FLOOR, (
        f"seulement {len(examines)} littéraux portent un ``this.X`` "
        f"(16 mesurés le 2026-09-07). Si les composants ont cessé "
        f"d'écrire des corps de méthode dans leur ``bz-data``, cette "
        f"gate n'a plus d'objet ; sinon c'est la construction ou le "
        f"motif qui a cassé, et « zéro fantôme » ne veut plus rien dire."
    )


def test_the_detector_recognises_a_ghost() -> None:
    """Contrôle POSITIF — le détecteur sait dire oui.

    Un ``assert not trouvé`` répété sur 30 composants passe aussi bien
    quand le détecteur ne détecte plus rien. On lui donne donc les deux
    littéraux : celui qui doit rougir, et celui qui ne doit pas.
    """
    fantome = '{...$bz.time.scope,open: false,value: "09:30",' \
              '_read() { return this.val; }}'
    sain = '{...$bz.time.scope,open: false,value: "09:30",' \
           '_read() { return this.value; }}'

    assert "val" in (set(re.findall(r"this\.(\w+)", fantome))
                     - _declared_keys(fantome) - _slab_members("time.scope")), (
        "le détecteur ne voit plus un ``this.val`` sur un scope qui "
        "déclare ``value`` — c'est LE défaut du 2026-09-07, fabriqué ici."
    )
    assert not (set(re.findall(r"this\.(\w+)", sain))
                - _declared_keys(sain) - _slab_members("time.scope")), (
        "le détecteur accuse un littéral SAIN. Un faux positif est pire "
        "qu'un trou : c'est ce qui fait désarmer une gate."
    )
