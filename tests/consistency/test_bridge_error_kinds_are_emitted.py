"""Gate : tout ce sur quoi le bridge AIGUILLE, Python doit pouvoir l'émettre.

Le bridge (``05_bridge.js``, ``applyPayload`` / ``handleError``) branche sur
deux vocabulaires que le serveur pose dans le ``<bz-patch>`` :

- les **clés réservées** (``instancePath === "_error"`` /
  ``"_notifications"``) — un chemin d'instance qui n'en est pas un ;
- les **kinds d'erreur** (``kind === "reload"``) à l'intérieur d'``_error``.

C'est un protocole à deux moitiés, écrites dans deux langages, dans deux
fichiers — donc rien ne garantit qu'elles se répondent.

Elles ne se répondaient pas. Mesuré le 2026-08-14 : le bridge lisait
``kind === "redirect" && err.url`` et faisait ``window.location =
err.url``. Aucun code Python n'émettait ce kind — et surtout, aucun ne le
POUVAIT : ``error_envelope(kind, message)`` construit ``{"kind": …,
"message": …}``, sans le moindre paramètre pour porter une ``url``. La
branche était donc morte par construction, tout en étant documentée comme
livrée dans le docstring d'``envelope.py`` (« ``"redirect"`` (with a
``url``) → navigate »). Le coût n'est pas la branche morte : c'est qu'on a
conclu à une redirection livrée en lisant la doc, puis à une redirection à
finir en lisant le bridge, alors que la vraie réponse était ailleurs
(l'en-tête ``HX-Redirect``, natif htmx — cf. :func:`bretzel.redirect`).

Ce que la gate protège : **le vocabulaire lu par le client est un
sous-ensemble de celui écrit par le serveur**. Elle rougit sur la
prochaine moitié de protocole, pas seulement sur celle-ci.

Le sens est volontairement UNIQUE. Un mot émis que le bridge ne connaît
pas n'est pas un bug : un kind inconnu tombe sur le toast générique, une
clé inconnue est traitée comme un chemin d'instance normal. Ce sont des
comportements voulus. C'est l'inverse qui ment — du code client prêt pour
un message que personne ne peut envoyer.

⚠️ **Cette gate constate, elle n'empêche pas.** La forme plus haute serait
que les deux vocabulaires vivent dans ``runtime/protocol.py`` et soient
substitués dans le JS au build (le mécanisme existe déjà :
``_build.py`` § ``_TOKENS``) — un kind absent de ``protocol.py`` serait
alors **inécrivable** côté JS, ce qui vaut mieux que remarqué après coup.
Chantier ouvert dans ``.claude/work/todo.md``.
"""

from __future__ import annotations

import ast
import functools
import re

from tests.consistency._discovery import (
    PACKAGE_FLOOR,
    REPO_ROOT,
    RUNTIME_SRC_DIR,
    parsed_sources,
    strip_js_comments,
)

#: Preuve de morsure : contrôle POSITIF — chacun des deux balayages a bien PARLÉ, ce qu'un
#: ``⊆`` ne prouve pas.
MUTATION_PROOF = "test_the_sweep_finds_both_vocabularies"

_BRIDGE = RUNTIME_SRC_DIR / "05_bridge.js"
_PACKAGE = REPO_ROOT / "bretzel"

#: ``kind === "…"`` et ``instancePath === "…"`` — les deux seules formes
#: d'aiguillage du bridge. On lit le fichier SOURCE (``_src/``) et non le
#: bundle : c'est lui qu'on édite, le bundle en est dérivé.
_JS_KIND_TEST = re.compile(r"""kind\s*===\s*["']([a-z_]+)["']""")
_JS_RESERVED_KEY_TEST = re.compile(r"""instancePath\s*===\s*["'](_[a-z_]+)["']""")

#: Les commentaires JS parlent des deux vocabulaires au fil du texte
#: (« kind "reload" → … »). Aucun n'emploie ``===`` aujourd'hui, donc le
#: strip est un no-op mesuré — on le garde parce qu'il ne coûte rien et
#: qu'il rend la gate insensible à une prose future ou à une branche
#: commentée, qui rougiraient pour rien.
#:
#: Le stripper vivait ICI jusqu'au 2026-08-15, où une deuxième gate en a
#: eu besoin et l'a recopié à l'identique. Promu dans ``_discovery.py``
#: plutôt que dupliqué : les deux copies portaient le même défaut connu
#: (un ``//`` dans un littéral de chaîne), et la seconde l'inlinait — donc
#: le grep qui aurait trouvé l'une manquait l'autre.

#: Un fichier qui ne contient pas ce token ne peut PAS porter d'appel :
#: le prédicat AST ci-dessous exige ce nom exact. Préfiltrer sur le texte
#: divise le balayage par cinq (1,16 s → 0,23 s sur 344 fichiers, mesuré
#: le 2026-08-14) sans changer d'un iota ce qu'il trouve.
_EMITTER = "error_envelope"


@functools.lru_cache(maxsize=1)
def _bridge_source() -> str:
    return strip_js_comments(_BRIDGE.read_text(encoding="utf-8"))


def _kinds_read_by_the_bridge() -> set[str]:
    return set(_JS_KIND_TEST.findall(_bridge_source()))


def _reserved_keys_read_by_the_bridge() -> set[str]:
    return set(_JS_RESERVED_KEY_TEST.findall(_bridge_source()))


@functools.lru_cache(maxsize=1)
def _python_sweep() -> tuple[frozenset[str], frozenset[str], tuple[str, ...]]:
    """``(kinds émis, clés réservées émises, fichiers illisibles)``.

    Balayage unique, mémoïsé : les trois tests d'ici le partagent, et il
    pesait 2,2 s de la suite ``consistency`` en étant refait à chaque
    appel.

    ``encoding="utf-8-sig"`` et non ``"utf-8"`` : ``bretzel/render/__init__.py``
    porte un BOM, que ``utf-8`` laisse en tête de chaîne et qu'``ast.parse``
    refuse. Le fichier était donc **silencieusement** hors du balayage.
    Les fichiers qu'on n'arrive quand même pas à lire sont REMONTÉS plutôt
    qu'avalés — un ``except: continue`` transforme une gate en gate
    partielle sans que personne ne l'apprenne, ce qui est la même maladie
    qu'une gate vacuous.

    Portée exacte de ``unreadable``, pour ne pas la surestimer : **tout**
    fichier dont la LECTURE échoue y entre (la lecture précède le
    préfiltre), mais un échec d'``ast.parse`` n'y entre que pour les
    fichiers contenant ``error_envelope`` — les seuls qu'on parse. C'est
    la bonne portée, pas une concession : un fichier sans le token ne peut
    pas porter d'appel, donc ne pas le parser ne perd rien.
    """
    kinds: set[str] = set()
    keys: set[str] = set()

    # La comptabilité ``unreadable`` qui vivait ici — lire, rattraper,
    # accumuler, asserter plus bas — était le bon RÉFLEXE, et elle est
    # désormais celle de ``parsed_sources`` : la primitive lit en
    # utf-8-sig et LÈVE, donc plus aucune gate n'a à le refaire chez elle.
    # C'est ce fichier-ci qui avait trouvé la classe de défaut ; il en est
    # maintenant le client, pas l'exception.
    for source in parsed_sources(_PACKAGE, floor=PACKAGE_FLOOR):
        text, tree = source.text, source.tree
        if _EMITTER not in text:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name != _EMITTER or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                kinds.add(first.value)

    # Les clés réservées ne passent pas par un appel nommé — elles sont
    # écrites en littéral dans le dict de patches. Un balayage textuel est
    # ici la bonne granularité : la clé EST la chaîne.
    # Une SEULE lecture : la primitive partagée a déjà lu et parsé ces
    # fichiers pour la boucle du dessus, et elle LÈVE sur un illisible.
    # Le ``try/except … continue`` qui vivait ici relisait le disque pour
    # ré-absorber en silence un échec qu'on venait de remonter.
    for source in parsed_sources(_PACKAGE, floor=PACKAGE_FLOOR):
        keys.update(re.findall(r"""["'](_[a-z_]+)["']\s*:""", source.text))

    return frozenset(kinds), frozenset(keys)


def _kinds_emitted_by_python() -> frozenset[str]:
    return _python_sweep()[0]


def _reserved_keys_emitted_by_python() -> frozenset[str]:
    return _python_sweep()[1]


def test_bridge_error_kinds_are_all_emittable() -> None:
    read = _kinds_read_by_the_bridge()
    emitted = _kinds_emitted_by_python()

    unreachable = read - emitted
    assert not unreachable, (
        "Le bridge aiguille sur des kinds d'erreur que rien n'émet côté "
        f"Python : {sorted(unreachable)}.\n\n"
        f"Émis par error_envelope() : {sorted(emitted) or '(aucun)'}.\n\n"
        "Soit la moitié serveur manque (l'écrire), soit la branche client "
        "est morte (la retirer). Ne pas la laisser : du code prêt pour un "
        "message que personne ne peut envoyer se lit comme une "
        "fonctionnalité livrée — c'est exactement ce qu'a fait le kind "
        "'redirect' avant le 2026-08-14."
    )


def test_bridge_reserved_keys_are_all_emittable() -> None:
    """La même règle, un cran au-dessus du kind.

    ``_error`` et ``_notifications`` sont branchés par la MÊME boucle
    (``applyPayload``) et sont exactement le même construct — un chemin
    d'instance réservé. N'en gater qu'un laissait l'autre libre de dériver.
    """
    read = _reserved_keys_read_by_the_bridge()
    emitted = _reserved_keys_emitted_by_python()

    unreachable = read - emitted
    assert not unreachable, (
        "Le bridge traite des clés de patch réservées que rien n'émet côté "
        f"Python : {sorted(unreachable)}.\n\n"
        "Une clé réservée lue mais jamais écrite est du code client prêt "
        "pour un message que personne ne peut envoyer."
    )


def test_the_sweep_finds_both_vocabularies() -> None:
    """Plancher de non-vacuité — il porte sur la DÉCOUVERTE.

    Les assertions du dessus sont des ``⊆`` : elles passent trivialement
    si l'un des deux balayages ne trouve plus rien. Trois façons d'y
    arriver sans le vouloir — ``handleError`` réécrit en ``switch`` (les
    regex ne matchent plus), ``error_envelope`` renommé (le préfiltre ne
    matche plus), ou un fichier que le balayage n'arrive pas à lire et
    saute en silence. Le plancher ne compte donc PAS une population
    attendue, il vérifie que chaque côté a bien parlé.

    ⚠️ Le troisième cas — le fichier tombé du balayage — était vérifié ici
    par une liste ``unreadable`` que ``_python_sweep`` accumulait. Cette
    comptabilité a déménagé dans ``_discovery.parsed_sources``, qui LÈVE
    au lieu d'accumuler : la garder ici serait désormais une assertion sur
    une liste toujours vide, c'est-à-dire du vert qui ne vérifie rien.
    C'est ce fichier-ci qui avait trouvé la classe de défaut ; il en est
    maintenant le client.
    """
    read_kinds = _kinds_read_by_the_bridge()
    read_keys = _reserved_keys_read_by_the_bridge()
    emitted_kinds = _kinds_emitted_by_python()
    emitted_keys = _reserved_keys_emitted_by_python()
    assert read_kinds, (
        "Aucun `kind === \"…\"` trouvé dans 05_bridge.js — le balayage "
        "client est débranché (handleError réécrit ?), et le ⊆ ne vérifie "
        "plus rien. Réparer _JS_KIND_TEST."
    )
    assert read_keys, (
        "Aucun `instancePath === \"_…\"` trouvé dans 05_bridge.js — même "
        "diagnostic pour les clés réservées. Réparer _JS_RESERVED_KEY_TEST."
    )
    assert emitted_kinds, (
        "Aucun appel `error_envelope(\"…\")` trouvé dans bretzel/ — le "
        "balayage serveur est débranché (fonction renommée ? préfiltre "
        "périmé ?). Réparer _EMITTER / _python_sweep."
    )
    assert emitted_keys, (
        "Aucune clé de patch réservée trouvée dans bretzel/ — le balayage "
        "textuel des clés est débranché. Réparer _python_sweep."
    )


def test_the_removed_redirect_kind_did_not_come_back() -> None:
    """Le cas concret, nommé — et il n'est PAS redondant avec le ⊆.

    Deux façons de faire revenir la redirection par le protocole d'erreur.
    Si seule la moitié client revient, le ⊆ rougit et celui-ci aussi. Mais
    si quelqu'un ajoute les DEUX moitiés — ``error_envelope("redirect",
    …)`` **et** la branche du bridge — le ⊆ passe au vert : les deux
    vocabulaires s'accordent. C'est le cas le plus plausible, parce que
    c'est ce que construirait naturellement quelqu'un qui redécouvre le
    besoin.

    Le ⊆ garde une *symétrie de protocole* ; celui-ci garde une *décision
    de conception* — une redirection est un en-tête ``HX-Redirect``, jamais
    un kind d'erreur — qu'aucun ⊆ ne sait exprimer.
    """
    assert "redirect" not in _kinds_read_by_the_bridge(), (
        "Le kind 'redirect' est de retour dans le bridge. La redirection "
        "se fait avec bretzel.redirect() → en-tête HX-Redirect, sans "
        "aucun code runtime. Cf. bretzel/server/errors.py."
    )
