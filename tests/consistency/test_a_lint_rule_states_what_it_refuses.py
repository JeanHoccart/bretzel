"""Gate : chaque règle de `check` dit en UNE phrase ce qu'elle refuse.

Le défaut qu'elle ferme
-----------------------
``rule_summaries()`` ne recopie rien : elle lit la première ligne du
module qui porte la règle. C'est ce qui l'empêche de dériver — et c'est
aussi ce qui la rend MUETTE en silence. Une règle dont le module perd sa
docstring, ou dont l'en-tête cesse de commencer par une phrase, rend une
chaîne vide : la doc vivante affiche alors une ligne blanche, le CLI
aussi, et rien ne lève.

C'est la forme d'échec propre aux lectures dérivées : elles ne mentent
pas, elles se taisent. Une valeur par défaut vide se lit exactement
comme « cette règle n'a rien à dire ».

Trois volets
------------
1. **Population identique** à ``available_rules()`` — les deux portes
   décrivent le même ensemble, sinon l'une des deux ment sur ce que
   l'outil couvre.
2. **Aucune phrase vide**, et aucune qui garde son préfixe ``Règle :``
   ni son balisage : le nettoyage doit avoir eu lieu, sans quoi la
   phrase part telle quelle dans une page.
3. **La lecture MORD** — sur un module fabriqué, la phrase sort ; sur un
   module sans docstring, elle est vide. Le second versant est celui qui
   compte : il montre exactement le silence que le volet 2 interdit.
"""

from __future__ import annotations

import types

from bretzel.lint import available_rules, rule_summaries
from bretzel.lint import _stated_by


def summaries_that_say_nothing() -> list[str]:
    """Les règles dont la phrase est vide, ou pas nettoyée."""
    fautives: list[str] = []
    for slug, phrase in rule_summaries().items():
        nettoyee = phrase.strip()
        if not nettoyee or nettoyee.startswith("Règle"):
            fautives.append(f"{slug} → {phrase!r}")
        elif "``" in phrase or "**" in phrase:
            fautives.append(f"{slug} → balisage restant : {phrase!r}")
    return fautives


def test_both_doors_describe_the_same_rules() -> None:
    """Volet 1 — et le plancher, puisque la population EST le sujet."""
    assert len(available_rules()) >= 10, (
        f"seulement {len(available_rules())} règles découvertes — la table "
        f"du linter est cassée, et tout ce qui suit s'affirmerait sur rien."
    )
    assert set(rule_summaries()) == set(available_rules()), (
        "les deux portes publiques de `bretzel.lint` ne décrivent pas le "
        "même ensemble de règles : l'une des deux ment sur ce que `check` "
        "couvre."
    )


def test_no_rule_states_nothing() -> None:
    assert not summaries_that_say_nothing(), (
        f"{summaries_that_say_nothing()} — une phrase vide s'affiche comme "
        f"une ligne blanche dans la doc vivante et dans le CLI, sans que "
        f"rien ne lève. C'est le silence, pas le mensonge, qui est le mode "
        f"d'échec d'une lecture dérivée."
    )


def test_the_reading_catches_a_stated_module_and_goes_empty_on_a_mute_one() -> None:
    """Volet 3 — la mutation, dans les deux sens."""
    parlant = types.ModuleType("parlant")
    parlant.__doc__ = "Règle : un ``kwarg`` **inconnu** part en attribut inerte."

    def check_parlant() -> None: ...
    check_parlant.__module__ = "parlant"
    import sys
    sys.modules["parlant"] = parlant
    try:
        assert _stated_by(check_parlant) == (
            "un `kwarg` inconnu part en attribut inerte"
        )
    finally:
        del sys.modules["parlant"]

    muet = types.ModuleType("muet")

    def check_muet() -> None: ...
    check_muet.__module__ = "muet"
    sys.modules["muet"] = muet
    try:
        assert _stated_by(check_muet) == "", (
            "un module sans docstring doit rendre la chaîne VIDE — c'est "
            "précisément ce que le volet 2 interdit de laisser passer."
        )
    finally:
        del sys.modules["muet"]
