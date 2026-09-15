"""Tout ``$bz.<nom>`` que Python ÉMET, le runtime le définit.

Le fait gardé
--------------
Python fabrique des morceaux de JavaScript. Pas beaucoup, mais des
morceaux qui comptent : ``bz-show="$bz.pending($el, 200)"``,
``bz-attr:icon="$bz._resolveIcon(…)"``, les appels de composant
(``$bz.combobox``, ``$bz.charts``…). Ces chaînes traversent la
frontière des langages **sans que rien ne les vérifie** : le Python les
écrit comme du texte, le navigateur les évalue à l'exécution, et entre
les deux il n'y a ni import, ni type, ni éditeur qui suive le lien.

Renommer une fonction du runtime — ou en émettre une qui n'a jamais été
écrite — ne lève donc rien à l'import, ne casse aucun test serveur, et
ne s'affiche pas en revue. Ça se voit à l'écran, une fois, quand
l'expression jette et que la directive reste morte : un spinner qui ne
tourne jamais, une icône qui ne se résout pas.

23 noms passent cette frontière au 2026-08-27. Cette gate les compte
tous, pas seulement le dernier arrivé.

Pourquoi elle ne lit QUE les littéraux de chaîne
-------------------------------------------------
Un balayage textuel naïf de ``bretzel/**.py`` remonte un 24e nom,
``$bz.resolve`` — et il n'existe pas. Ses deux occurrences sont de la
PROSE : ``envelope.py`` explique qu'un tel résolveur « n'a jamais été
construit », ``tailwind.py`` cite une ancienne phrase qu'il corrige.
Deux commentaires qui parlent d'une absence, lus comme une émission.

C'est le versant licite qui coûte cher — celui qui fait rougir la gate
sur du code juste — donc l'extraction passe par l'AST
(``_discovery.code_string_literals``). Un commentaire n'existe plus
après ``ast.parse`` ; une chaîne NUE en instruction est jetée par
l'interpréteur, donc elle ne peut atteindre aucun DOM, docstring ou
non. Ce qui reste est du texte que le programme fabrique — donc du
JavaScript qui partira vraiment dans le DOM. Le côté JS applique la
même règle par ``strip_js_comments``.

Ce que la gate n'affirme PAS
-----------------------------
Que l'appel a la bonne ARITÉ, ni les bons arguments : ``$bz.pending()``
sans son délai passerait ici. Elle ferme la dérive du VOCABULAIRE, pas
celle des signatures — la seule qui soit lisible depuis les deux côtés
sans exécuter le navigateur. L'arité, c'est le travail des probes
(``tests/probes/probe_pending.py`` pour celui-ci).

Elle ne descend pas non plus dans les SOUS-noms : ``$bz.helpers.foo``
n'est vérifié que sur ``helpers``. Les namespaces imbriqués
(``$bz.helpers``, ``$bz.charts``, ``$bz.combobox``…) sont des littéraux
d'objet, et renommer une clé à l'intérieur reste invisible aux deux
langages — c'est la prochaine marche, notée dans ``work/todo.md``.
Enfin elle balaie ``bretzel/`` seul : ``examples/`` est du code de
référence, pas du framework.
"""

from __future__ import annotations

import ast
import functools
import re

from tests.consistency._discovery import (
    PACKAGE_FLOOR,
    REPO_ROOT,
    ParsedSource,
    assert_runtime_sweep_is_not_vacuous,
    code_string_literals,
    parsed_sources,
    runtime_slabs,
    strip_js_comments,
)

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"

_REFERENCE = re.compile(r"\$bz\.([A-Za-z_][A-Za-z0-9_]*)")
#: ``$bz.foo = …`` — la seule forme de définition du runtime (vérifié :
#: aucun slab ne construit son namespace par ``Object.assign``).
_DEFINITION = re.compile(r"\$bz\.([A-Za-z_][A-Za-z0-9_]*)\s*=")

def names_emitted_by(source: ParsedSource) -> set[str]:
    """Les ``$bz.<nom>`` que ce module FABRIQUE, prose exclue.

    Extrait plutôt qu'inline pour être MUTABLE : c'est ce détecteur que
    ``test_the_detector_still_bites`` nourrit de sources fabriquées.
    """
    found: set[str] = set()
    for node in code_string_literals(source.tree):
        found |= set(_REFERENCE.findall(node.value))
    return found


def names_defined_in_runtime() -> set[str]:
    """Ce que ``_src/`` attache réellement à ``window.$bz``.

    ``strip_js_comments`` d'abord, et pour la MÊME raison que
    l'extraction Python ci-dessus ne lit pas la prose : sans lui, un
    ``// ``$bz.foo = …`` a été retiré`` garderait cette gate verte sur
    un global que le runtime ne définit plus.

    Les slabs, pas ``runtime.js`` : le bundle est un artefact concaténé
    dont la fraîcheur est gardée ailleurs (``test_runtime_bundle_is_fresh``),
    et le juger ici jugerait deux fois la même chose, la mauvaise fois.
    """
    defined: set[str] = set()
    for slab in runtime_slabs():
        code = strip_js_comments(slab.read_text(encoding="utf-8"))
        defined |= set(_DEFINITION.findall(code))
    return defined


@functools.cache
def _emitted_by_the_package() -> dict[str, set[str]]:
    """``nom → les fichiers qui l'émettent``, sur tout ``bretzel/``.

    Mémoïsé : les deux tests ci-dessous le demandent, et le balayage
    (402 fichiers) pesait 0,6 s à chaque appel. Les appelants ne font
    que lire.
    """
    out: dict[str, set[str]] = {}
    for source in parsed_sources(REPO_ROOT / "bretzel", floor=PACKAGE_FLOOR):
        rel = str(source.path.relative_to(REPO_ROOT))
        for name in names_emitted_by(source):
            out.setdefault(name, set()).add(rel)
    return out


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher ancré sur la DÉCOUVERTE, pas sur la population.

    Recompter les fichiers ne dirait rien : c'est l'EXTRACTEUR qui peut
    se taire (un changement d'AST, une regex trop stricte), et il se
    tairait en rendant un dict vide — soit un vert parfait.
    """
    assert_runtime_sweep_is_not_vacuous()

    emitted = _emitted_by_the_package()
    assert len(emitted) >= 15, (
        f"l'extracteur ne trouve plus que {len(emitted)} noms ``$bz.*`` "
        f"émis par Python (>= 15 attendus, 23 le 2026-08-27). Il s'est tu "
        f"— et une gate muette affirme « aucune dérive » sans avoir lu."
    )
    # Deux ancres choisies pour leurs FORMES d'émission différentes :
    # ``state`` sort de ``ClientBinding.binding_path`` (une f-string de
    # chemin), ``_resolveIcon`` d'un thème. Si l'une des deux disparaît,
    # c'est une famille entière d'émissions qui a cessé d'être vue.
    for anchor in ("state", "_resolveIcon"):
        assert anchor in emitted, (
            f"``$bz.{anchor}`` n'est plus vu comme émis par Python. Il "
            f"l'est pourtant — donc c'est l'extraction qui a cessé de "
            f"lire cette forme, pas le dépôt qui a changé."
        )

    assert names_defined_in_runtime(), "aucune définition ``$bz.x =`` dans ``_src/``"


def test_every_emitted_global_is_defined_by_the_runtime() -> None:
    emitted = _emitted_by_the_package()
    defined = names_defined_in_runtime()
    missing = {
        name: sorted(files) for name, files in emitted.items() if name not in defined
    }

    assert not missing, (
        "Python émet des ``$bz.*`` que le runtime ne définit pas :\n  "
        + "\n  ".join(
            f"$bz.{name} — émis par {', '.join(files)}"
            for name, files in sorted(missing.items())
        )
        + "\n\nL'expression sera évaluée dans le navigateur et jettera. "
        "Rien ne le dira côté serveur : la directive restera simplement "
        "morte, et le composant paraîtra inerte."
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur des sources FABRIQUÉES.

    Le versant LICITE est le plus important ici : c'est lui qui a fait
    écarter le balayage textuel (cf. l'en-tête, ``$bz.resolve``).
    """

    def extract(src: str) -> set[str]:
        return names_emitted_by(
            ParsedSource(path=REPO_ROOT / "x.py", text=src, tree=ast.parse(src))
        )

    # ── Versant ILLICITE : une émission réelle est vue ────────────────
    assert extract('attrs["bz-show"] = "$bz.pending($el, 200)"') == {"pending"}
    assert extract('f"$bz.state.{path}"') == {"state"}
    # Assigné, pas nu : une chaîne SEULE en tête de module EST une
    # docstring, et l'extracteur a raison de la sauter.
    assert extract('x = "$bz.jamaisEcrit()"') == {"jamaisEcrit"}

    # ── Versant LICITE : la prose n'est PAS une émission ──────────────
    assert extract("# $bz.resolve n'a jamais ete construit\nfoo()") == set(), (
        "un commentaire est lu comme du code émis — la gate rougirait "
        "sur du Python juste, et c'est ce qui la ferait désactiver."
    )
    assert extract('"""Doc : ``$bz.resolve`` est absent."""\nfoo()') == set(), (
        "une docstring de module est lue comme une émission."
    )
    assert extract('def f():\n    """Voir ``$bz.resolve``."""\n    return 1') == set(), (
        "une docstring de fonction est lue comme une émission."
    )

    # ── Et la comparaison distingue vraiment ──────────────────────────
    assert "jamaisEcrit" not in names_defined_in_runtime()
