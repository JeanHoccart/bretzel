"""Gate : un probe est capable de RENDRE ROUGE.

Le défaut qu'elle ferme (2026-08-26)
------------------------------------
``tests/probes/test_probes.py`` ne juge qu'une chose : le code de sortie
du script. Or **neuf probes sur soixante-trois** calculaient leur verdict,
imprimaient ``==> SOME CHECKS FAILED``, et se terminaient par ::

    if __name__ == "__main__":
        main()          # <- pas de sys.exit, donc code de sortie 0

Le verdict ne rejoignait jamais le code de sortie. ``pytest -m probes``
les comptait verts **quoi qu'ils mesurent**. Cinq des neuf couvraient la
sidebar et les overlays.

Ce n'était pas théorique : en les câblant, deux sont devenus rouges —
``probe_sidebar`` (déjà noté dans ``work/todo.md``, donc connu et invisible
à la suite) et ``probe_sidebar_footer``, que **personne n'avait vu**, avec
un panneau qui s'ouvre du mauvais côté et un repli de rail qui ne replie
pas. Les six autres passaient réellement.

Pourquoi c'est la pire forme
-----------------------------
``tests/probes/`` est le SEUL étage qui regarde le rendu depuis la
suppression de ``tests/visual/`` le 2026-08-16, et la discipline n°3 du
charter — « probe Playwright OBLIGATOIRE avant de dire que c'est livré » —
repose entièrement dessus. Un probe muet ne se contente pas de ne rien
dire : il **atteste**. C'est le mode d'échec que la docstring de
``test_probes.py`` nommait déjà — « 3 verts à tort, ce qui est pire que
rouge », mesuré le 2026-08-19 — sans qu'aucune gate n'en soit sortie.

L'invariant
-----------
Le contrat est **écrit** dans ``tests/probes/README.md`` § *Deux
formes* : « ``probe_X.py`` → … renvoie ``0`` (vert) / ``1`` (rouge) ».
Cette gate le rend mécanique : tout ``probe_*.py`` doit porter un chemin de sortie
non-nul — un ``sys.exit`` capable d'autre chose que ``0``, un ``raise``,
un ``assert``, ou un ``with probe(...)``, dont la sortie de bloc lève
:class:`~bretzel.probe.ProbeFailedError` dès qu'un constat est rouge.

⚠️ La quatrième forme est arrivée le 2026-09-11, avec le premier probe
porté sur le harnais. Elle a fait rougir cette gate, et la gate avait
tort : ce probe rend bien un code non nul, simplement ce n'est plus LUI
qui l'écrit. Une gate qui encode la FAÇON dont on obtenait un invariant,
et non l'invariant, finit par refuser la meilleure façon de l'obtenir.

Ce qu'elle ne fait PAS
-----------------------
Elle ne vérifie pas que le chemin rouge est ATTEIGNABLE, ni que les
mesures du probe sont justes. Un probe qui écrirait ``return 0`` en dur
passerait ici. Ce qu'elle ferme, c'est la classe mesurée : le verdict
existe mais n'atteint pas la sortie. Pour le reste, il n'y a pas de
substitut à lancer ``-m probes`` et à lire.
"""

from __future__ import annotations

import ast

import pytest

from tests.consistency._discovery import PROBES_DIR

#: Preuve de morsure par contrôle POSITIF : le détecteur reconnaît encore
#: les deux formes de sortie rouge sur du code fabriqué, ET refuse celle
#: qui a causé le bug. Un détecteur qui distingue les trois n'est pas
#: aveugle.
MUTATION_PROOF = "test_the_detector_tells_the_three_shapes_apart"

#: 63 probes le 2026-08-26, après deux mouvements du même jour :
#: ``probe_fdbg`` supprimé (un script de debug sans aucun check ni bench
#: jumeau, entré par un commit « SAFETY CHECKPOINT ») et
#: ``probe_sidebar_collapse`` sorti du ``--probe`` de son banc.
#: Le plancher attrape un glob cassé — la gate passerait en n'ayant lu
#: aucun fichier.
_PROBES_FLOOR = 55


def _probe_files() -> list:
    return sorted(PROBES_DIR.glob("probe_*.py"))


def can_signal_failure(source: str) -> bool:
    """Ce script a-t-il un chemin de sortie NON-NUL ?

    Quatre formes acceptées, parce que les probes du dépôt en utilisent
    quatre :

    - ``sys.exit(<autre chose que 0>)`` — la convention du README, via
      ``sys.exit(main())`` ;
    - ``raise`` — un probe qui lève sur un bench absent ;
    - ``assert`` — la forme courte de quelques probes d'une page ;
    - ``with probe(...)`` — le harnais lève à la sortie du bloc, donc le
      probe n'a plus à câbler son verdict jusqu'au code de sortie. C'est
      exactement le câblage que neuf probes avaient oublié.

    ``sys.exit(0)`` et ``sys.exit()`` ne comptent PAS : c'est exactement
    le camouflage qu'on cherche.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Raise, ast.Assert)):
            return True
        if isinstance(node, (ast.With, ast.AsyncWith)) and any(
            _calls_probe(item.context_expr) for item in node.items
        ):
            return True
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = (
            target.attr if isinstance(target, ast.Attribute)
            else target.id if isinstance(target, ast.Name)
            else None
        )
        if name != "exit":
            continue
        if not node.args:                       # ``sys.exit()`` -> 0
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and arg.value in (0, None):
            continue
        return True                             # exit(main()), exit(1), …
    return False


def _calls_probe(expr: ast.expr) -> bool:
    """``probe(...)`` ou ``bretzel.probe.probe(...)``, et rien d'autre.

    On vise le NOM, pas l'import : un fichier peut l'importer de six
    façons, et aucune ne change ce que le bloc fait à la sortie.
    """
    if not isinstance(expr, ast.Call):
        return False
    target = expr.func
    return (
        target.attr if isinstance(target, ast.Attribute)
        else target.id if isinstance(target, ast.Name)
        else None
    ) == "probe"


def test_the_sweep_is_not_vacuous() -> None:
    found = _probe_files()
    assert len(found) >= _PROBES_FLOOR, (
        f"seulement {len(found)} probes découverts sous {PROBES_DIR} "
        f"(63 le 2026-08-26) — vérifie le glob avant de croire que cette "
        f"gate passe. Elle serait verte en n'ayant rien lu."
    )


@pytest.mark.parametrize(
    "path", _probe_files(), ids=lambda p: p.name
)
def test_a_probe_has_a_red_exit_path(path) -> None:
    # ``utf-8-sig`` et pas ``errors="replace"`` : un octet indécodable doit
    # LEVER, pas disparaître — sinon le balayage cherche son motif dans un
    # texte qui n'est plus celui du fichier. Gardé par
    # ``test_no_gate_swallows_a_file``, qui a attrapé cette gate-ci le jour
    # de son écriture.
    source = path.read_text(encoding="utf-8-sig")
    assert can_signal_failure(source), (
        f"``{path.name}`` n'a aucun chemin de sortie non-nul : quoi qu'il "
        f"mesure, il sortira 0 et ``pytest -m probes`` le comptera VERT.\n"
        f"  C'est pire que rouge — un probe muet atteste au lieu de se "
        f"taire, et la discipline n°3 du charter repose sur cet étage.\n"
        f"  Le contrat est dans ``tests/probes/README.md`` § Deux formes : "
        f"un probe renvoie 0 (vert) / 1 (rouge). Le plus simple est de "
        f"passer par le harnais, qui lève à la sortie du bloc :\n"
        f"      from bretzel.probe import probe\n"
        f"\n"
        f"      with probe(\"mon.module:app\") as p:\n"
        f"          p.check(\"…\", ...)\n"
        f"\n"
        f"  Sinon, à la main :\n"
        f"      def main() -> int:\n"
        f"          return 0 if ok else 1\n"
        f"\n"
        f"      if __name__ == \"__main__\":\n"
        f"          sys.exit(main())\n"
        f"  Si ce fichier ne MESURE rien — pas de check, pas de bench "
        f"jumeau — ce n'est pas un probe : sors-le de ``probe_*.py``."
    )


def test_the_detector_tells_the_three_shapes_apart() -> None:
    """Le détecteur, sur les quatre formes qui comptent.

    Le versant ILLICITE seul ne dirait rien de ses faux positifs : un
    détecteur qui renvoie toujours ``False`` ferait rougir tout le monde
    et « prouverait » qu'il mord. On teste donc les deux sens sur du code
    fabriqué.
    """
    muet = (
        "def main():\n"
        "    ok = False\n"
        "    print('==> SOME CHECKS FAILED' if not ok else 'ok')\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )
    assert not can_signal_failure(muet), (
        "le détecteur accepte la forme EXACTE du bug (verdict imprimé, "
        "``main()`` appelé sans ``sys.exit``) — il est aveugle."
    )
    assert not can_signal_failure("import sys\nsys.exit(0)\n"), (
        "``sys.exit(0)`` est compté comme un chemin rouge — c'est le "
        "camouflage le plus court possible."
    )
    assert not can_signal_failure(
        "with open('x') as f:\n    print(f.read())\n"
    ), (
        "n'importe quel ``with`` compte comme un chemin rouge — seul "
        "``with probe(...)`` lève à la sortie du bloc."
    )
    for licite in (
        "import sys\ndef main() -> int:\n    return 1\nsys.exit(main())\n",
        "raise RuntimeError('bench never came up')\n",
        "assert False, 'nope'\n",
        "import sys\nsys.exit(1)\n",
        # Le harnais : le bloc lève tout seul sur un constat rouge.
        "from bretzel.probe import probe\n"
        "with probe('x:app') as p:\n"
        "    p.check('rien', True)\n",
    ):
        assert can_signal_failure(licite), (
            f"le détecteur ne reconnaît plus une sortie rouge légitime :\n"
            f"{licite}"
        )
