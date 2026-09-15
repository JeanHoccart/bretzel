"""Le bascule de thème et la peinture lisent la MÊME résolution.

Le fait gardé
--------------
``ColorScheme.mode`` porte **trois** valeurs — ``light`` / ``dark`` /
``system`` — mais ce qui est à l'écran n'en a que **deux**. Entre les
deux il y a une résolution : ``system`` plus un OS sombre donne sombre.

Deux lecteurs en ont besoin, et ils doivent lire la même :

- la PEINTURE, ``document.documentElement.classList.toggle("dark", …)``
  dans un effet du runtime ;
- le BASCULE, la source client que ``ColorScheme.toggle()`` fabrique
  côté Python et que le navigateur évalue au clic.

Ce que ça a coûté quand ils divergeaient
-----------------------------------------
Jusqu'au 2026-09-04 le bascule ne résolvait pas : il comparait le
JETON, ``mode === 'dark' ? 'light' : 'dark'``. Un utilisateur en
``system`` sur un OS sombre voyait donc son PREMIER clic écrire
``dark`` — déjà la valeur peinte. Le contrôle ne faisait rien une fois
sur deux, et c'est exactement comme ça qu'il a été rapporté : « le
bouton ne marche pas ».

Rien ne pouvait le dire avant l'écran. L'expression était du JavaScript
valide, la valeur partait bien dans le magasin, la persistance
l'enregistrait, et le rendu serveur était identique dans les deux cas.
La docstring de ``toggle`` DÉCRIVAIT même le comportement — « tout ce
qui n'est pas ``dark`` atterrit sur ``dark`` » — donc une relecture le
confirmait au lieu de le trouver suspect.

Ce que la gate vérifie
-----------------------
1. le bascule appelle une fonction du runtime pour décider, au lieu de
   recalculer ;
2. c'est **la même** que celle dont la peinture se sert ;
3. et le runtime la définit pour de vrai.

Le point 2 est celui qui compte. Un troisième exemplaire de la
résolution serait du JavaScript juste, testable, et faux le jour où
l'un des trois change — c'est déjà arrivé sur l'algèbre du foreground
(cf. ``test_foreground_algebra_is_mirrored``).

Ce que la gate n'affirme PAS
-----------------------------
Que la résolution soit CORRECTE : elle garde l'unicité, pas l'algèbre.
Que ``system`` mène à sombre sur un OS sombre se vérifie dans un
navigateur — ``tests/probes/probe_theme_toggle.py``.

Le script anti-FOUC de ``render/shell.py`` reste une copie assumée : il
tourne AVANT le runtime, donc il ne peut appeler aucune de ses
fonctions. C'est la seule, et son commentaire le dit.
"""

from __future__ import annotations

import re

from bretzel.state.scopes.client import rendering_scope
from bretzel.theme import ColorScheme

from tests.consistency._discovery import (
    assert_runtime_sweep_is_not_vacuous,
    runtime_sources,
)

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"

#: La ligne qui PEINT : ``classList.toggle("dark", <décision>)``. On
#: capture la décision pour lire de qui elle vient.
_PAINT = re.compile(
    r"""classList\.toggle\(\s*["']dark["']\s*,\s*(?P<decision>[^;]*?)\s*\)"""
)

#: ``$bz.<nom>(`` — un appel de fonction du runtime dans une décision.
_CALL = re.compile(r"\$bz\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")

#: ``$bz.<nom> = `` — la seule forme de définition du runtime.
_DEFINITION = re.compile(r"\$bz\.([A-Za-z_][A-Za-z0-9_]*)\s*=")


def flip_source() -> str:
    """La source client que le bascule envoie vraiment au navigateur."""
    with rendering_scope():
        return ColorScheme.toggle()


def decides_by_rereading_what_it_writes(js: str) -> bool:
    """L'expression relit-elle le chemin qu'elle ASSIGNE pour décider ?

    Extrait pour être MUTABLE : c'est ce détecteur que
    ``test_the_detector_still_bites`` nourrit d'expressions fabriquées.

    ⚠️ La règle n'est **pas** « une expression ne se relit jamais ».
    ``open = !open`` sur un booléen est parfaitement honnête — le jeton
    EST l'état. Elle ne vaut que là où le jeton a plus de valeurs que le
    contrôle n'a de positions, et ``mode`` en a trois pour deux.
    """
    target, sep, decision = js.partition(" = ")
    if not sep:
        return False
    return target.strip() in decision


def painters() -> list[tuple[str, str]]:
    """``(slab, décision)`` pour chaque ligne du runtime qui peint le mode."""
    return [
        (name, match.group("decision"))
        for name, code in runtime_sources().items()
        for match in _PAINT.finditer(code)
    ]


def runtime_defines() -> set[str]:
    """Ce que ``_src/`` attache réellement à ``window.$bz``."""
    defined: set[str] = set()
    for code in runtime_sources().values():
        defined |= set(_DEFINITION.findall(code))
    return defined


def test_the_sweep_finds_both_readers() -> None:
    """Plancher ancré sur la DÉCOUVERTE, pas sur la population.

    Les deux extracteurs peuvent se taire — la regex de peinture si le
    runtime change d'orthographe, le bascule si ``toggle()`` cesse de
    rendre une affectation. Chacun se tairait en rendant du vide, donc
    en laissant les tests d'en dessous verts sans avoir rien lu.
    """
    assert_runtime_sweep_is_not_vacuous()

    found = painters()
    assert found, (
        "aucune ligne du runtime ne peint ``classList.toggle('dark', …)``. "
        "Soit la peinture du mode a disparu, soit elle a changé "
        "d'orthographe — et dans les deux cas cette gate ne lit plus rien."
    )

    js = flip_source()
    assert " = " in js, (
        f"``ColorScheme.toggle()`` ne rend plus une affectation ({js!r}). "
        f"Le détecteur ci-dessous coupe sur ``' = '`` : il rendrait "
        f"``False`` pour tout, donc un vert sans lecture."
    )
    assert "ColorScheme" in js, (
        f"le bascule n'écrit plus dans ``ColorScheme`` ({js!r}) — la gate "
        f"garderait un mécanisme qui n'est plus celui du thème."
    )


def test_the_flip_asks_the_runtime_instead_of_recomputing() -> None:
    js = flip_source()

    assert not decides_by_rereading_what_it_writes(js), (
        f"``ColorScheme.toggle()`` décide en relisant le jeton qu'il "
        f"écrit :\n  {js}\n\n``mode`` a TROIS valeurs et le bascule en a "
        f"deux : partir de ``system`` sur un OS sombre écrit ``dark``, "
        f"qui est déjà ce qui est peint. Le premier clic ne fait rien. "
        f"Décidez depuis l'état RÉSOLU — la fonction dont la peinture se "
        f"sert déjà."
    )

    called = _CALL.findall(js)
    assert called, (
        f"le bascule ne demande rien au runtime :\n  {js}\n\nS'il résout "
        f"lui-même, sa copie de l'algèbre dérivera de celle de la "
        f"peinture — en silence, les deux moitiés restant plausibles "
        f"séparément."
    )


def test_the_flip_and_the_paint_call_the_same_function() -> None:
    js = flip_source()
    by_the_flip = set(_CALL.findall(js))

    by_the_paint: set[str] = set()
    for _slab, decision in painters():
        by_the_paint |= set(_CALL.findall(decision))

    assert by_the_paint, (
        "la peinture INLINE sa résolution au lieu d'appeler une fonction "
        f"nommée : {[d for _s, d in painters()]}. Le bascule ne peut donc "
        "pas partager la sienne, et les deux vont diverger."
    )
    shared = by_the_flip & by_the_paint
    assert shared, (
        f"le bascule appelle {sorted(by_the_flip)} et la peinture "
        f"{sorted(by_the_paint)} : deux résolutions, donc deux algèbres "
        f"libres de dériver. C'est exactement ce qui a fait qu'un clic "
        f"sur deux ne changeait rien."
    )

    defined = runtime_defines()
    undefined = sorted(shared - defined)
    assert not undefined, (
        f"``$bz.{undefined[0]}`` est appelé des deux côtés et le runtime "
        f"ne le définit pas. L'expression jettera dans le navigateur, et "
        f"le clic restera muet — sans rien dire côté serveur."
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur des expressions FABRIQUÉES."""
    path = "$bz.state.ColorScheme.default.mode"

    # ── Versant ILLICITE : la forme d'avant le 2026-09-04 ─────────────
    assert decides_by_rereading_what_it_writes(
        f"{path} = {path} === 'dark' ? 'light' : 'dark'"
    ), "le détecteur ne voit plus le bug qui l'a fait écrire."

    # ── Versant LICITE, et c'est lui qui coûte cher ───────────────────
    # ``set`` écrit une constante : il ne se relit pas, et une gate qui
    # le ferait rougir serait débranchée dans la semaine.
    with rendering_scope():
        assert not decides_by_rereading_what_it_writes(ColorScheme.set("dark"))
    # La forme livrée : la décision vient d'ailleurs.
    assert not decides_by_rereading_what_it_writes(
        f"{path} = $bz._isDark() ? 'light' : 'dark'"
    )
    # Une expression qui n'assigne rien n'est pas un bascule cassé.
    assert not decides_by_rereading_what_it_writes("$bz.pending($el, 200)")
