"""Gate : aucune gate ne fait sortir un COMPOSANT de son balayage en silence.

La gate qui garde les gates, troisième du nom.
``test_prohibition_gates_declare_a_floor`` garde « le balayage a-t-il
parlé ? », ``test_no_gate_swallows_a_file`` garde « le balayage a-t-il
tout LU ? ». Celle-ci garde « le balayage a-t-il tout CONSTRUIT ? ».

Le défaut qu'elle ferme
-----------------------
Le motif est le frère exact de celui des fichiers, une couche plus loin :

.. code-block:: python

    try:
        with render_isolated():
            html = serialize(cls().render())
    except Exception:
        return None          # le composant sort du balayage, sans un mot

Il vivait dans ``_discovery.bz_data_of``, donc sous les TROIS gates qui
l'appellent. Mesuré le 2026-08-19 en retirant l'``except`` : sur 97
composants publics, 36 émettent un ``bz-data`` et sont réellement jugés,
56 n'en émettent légitimement pas — et **quatre échouaient à la
construction sans que rien ne le dise** : ``Image``, ``Iframe``,
``MetaTag``, ``Title``. Tous les quatre pour la même raison sans intérêt
(un mot obligatoire : ``alt``, ``title``, ``content``, ``text``), donc
quatre composants invisibles pour rien.

Ce que la gate exige
---------------------
1. **La population est complète** : tout composant public se construit
   par la table partagée ``CONSTRUCT``, ou bien il est DÉCLARÉ comme
   exigeant un contexte (``_needs_context``, qui lève ``_Skip``). C'est
   ce test qui autorise les autres à ne plus rattraper : si personne ne
   peut échouer, personne n'a besoin d'un filet.
2. **Le filet silencieux ne revient pas** : un ``except`` large au corps
   vide autour d'une construction est refusé dans les gates neuves.

Rattraper est permis à UNE condition : nommer ce qu'on a raté
--------------------------------------------------------------
Neuf sites construisent encore avec un argument de sonde (``icon=``, ``size=``,
``src=``, un ``Callable``, une valeur backée serveur). Un composant qui
refuse cette sonde sort de la population **par définition**, pas par
accident : leur ``except`` est légitime.

Ce qui ne l'était pas, c'est que personne ne regardait CE QU'IL
rattrapait. Le 2026-08-19, en remplaçant chaque ``except`` par un
enregistrement :

- ``test_bz_data_literal_is_well_formed`` en avalait **32** — et la
  cause n'était pas les composants, c'était l'appel : le bâtisseur
  partagé prend ``(classe, NOM DE PROP, valeur)`` et on lui passait
  ``("slots", kwargs)``. Les 25 composants qui ont un bâtisseur
  sortaient du balayage en silence. Corrigé : **88 couples jugés au lieu
  de 65** ;
- ``test_bz_on_uses_dollar_event`` en avalait **six**, tous connus du
  socle (``CONSTRUCT`` et ``_BARE_ARGS``) ;
- ``test_no_component_emits_an_empty_resource_url`` en avalait **trois**,
  en devinant les arguments requis d'après leur ANNOTATION ;
- ``test_icon_follows_its_label`` et ``test_sizes_are_distinct`` n'en
  avalaient **aucun** — leur ``except`` ne rattrapait plus rien depuis
  un moment, et rien ne le disait non plus.

D'où la règle : un fichier qui rattrape une construction doit porter un
test qui **nomme** ses abstentions. Pas un plafond chiffré — une table.
Un plafond dirait « pas plus de deux » et laisserait passer « un qui
sort, un qui rentre » ; une table dit LESQUELS.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.consistency._discovery import (
    public_component_classes,
    rendered_html_of,
)

_GATES_DIR = Path(__file__).resolve().parent

#: ``_discovery`` EST l'implémentation autorisée : c'est le seul endroit
#: où le motif a le droit d'exister, et il n'y rattrape que ``_Skip`` —
#: la DÉCLARATION, pas l'accident.
_ALLOWED_FILES = frozenset({"_discovery.py"})

#: Ce qui, rattrapé au corps vide autour d'une construction, fait
#: disparaître un composant. ``_Skip`` n'y est pas : il est le canal
#: déclaré, et le rattraper est la bonne réponse.
_BROAD = frozenset({
    "Exception", "BaseException", "TypeError", "ValueError", "AttributeError",
})

#: Ce qu'on appelle quand on construit puis rend un composant.
_RENDER_CALLS = frozenset({"render", "serialize", "rendered_html_of", "bz_data_of"})

#: Le nom que doit porter le test qui nomme les abstentions d'un fichier.
#: Le nom EST le canal : ces tests n'ont pas de forme commune (l'un
#: compare des ensembles de couples, l'autre lit un ``.txt`` de 127
#: entrées), mais ils se nomment tous pour ce qu'ils font.
_DECLARATION_MARKER = "abstentions_are_declared"

#: ``fichier -> ce que sa sonde construit``. Ces fichiers ont le droit de
#: rattraper, PARCE QU'ils déclarent ce qu'ils ratent — vérifié par
#: ``test_a_catching_gate_names_what_it_missed``, sinon l'entrée serait
#: un laissez-passer.
_PROBE_KWARG_DEBT: dict[str, str] = {
    "test_a_changed_tag_drops_what_it_cannot_carry.py": "sonde `tag=` — trois composants la refusent par conception",
    "test_a_coloured_surface_declares_its_foreground.py": "sonde `color=` — tout conteneur n'en prend pas",
    "test_bz_data_literal_is_well_formed.py": "valeur backée serveur injectée dans chaque prop",
    "test_icon_follows_its_label.py": "sonde `icon=` — tout composant n'en prend pas",
    "test_no_manual_user_class_append.py": "instance construite par le banc appelant",
    "test_render_hatch_universal.py": "un Callable passé à chaque param typé Callable",
    "test_responsive_classes_are_safelisted.py": "sonde graduée par prop responsive",
    "test_server_config_is_resyncable.py": "deux jeux de config comparés",
    "test_sizes_are_distinct.py": "sonde `size=` sur chaque palier",
    "test_text_slot_contract_universal.py": "sentinelle passée à chaque slot textuel",
    "test_tooltip_wrapper_keeps_its_trigger_width.py": "factory du banc, avec et sans tooltip",
}


def _handler_names(handler: ast.ExceptHandler) -> set[str]:
    node = handler.type
    if node is None:
        return {"BaseException"}
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Tuple):
        return {e.id for e in node.elts if isinstance(e, ast.Name)}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    return set()


def _calls_in(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name:
                out.add(name)
    return out


def _is_silent(handler: ast.ExceptHandler) -> bool:
    body = handler.body
    if len(body) != 1:
        return False
    if isinstance(body[0], (ast.Continue, ast.Pass)):
        return True
    return (
        isinstance(body[0], ast.Return)
        and isinstance(body[0].value, ast.Constant)
        and body[0].value.value is None
    )


def swallowing_lines(tree: ast.AST) -> list[int]:
    """Les lignes où un ``except`` large au corps vide entoure un rendu."""
    out: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not _calls_in(node) & _RENDER_CALLS:
            continue
        for handler in node.handlers:
            if _handler_names(handler) & _BROAD and _is_silent(handler):
                out.append(handler.lineno)
    return out


def _gate_files() -> list[Path]:
    return sorted(
        p for p in _GATES_DIR.glob("*.py")
        if p.name not in _ALLOWED_FILES and not p.name.startswith("__")
    )


@pytest.mark.parametrize("cls", public_component_classes(), ids=lambda c: c.__name__)
def test_every_public_component_constructs(cls: type) -> None:
    """La population est COMPLÈTE — c'est ce qui autorise à ne plus rattraper.

    Un échec ici ne se répare pas en rattrapant : il se répare en
    déclarant. Deux canaux, et ils ne répondent pas à la même question —
    ``_discovery._BARE_ARGS`` dit « ce composant exige ce mot pour
    exister » (``alt=``, ``title=``…), ``CONSTRUCT`` dit « voici comment
    poser un binding sur sa prop ``p`` », et ``_needs_context("raison")``
    dit « aucun banc ne peut fabriquer son contexte ».

    ⚠️ Les fusionner ne marche pas : un bâtisseur ``CONSTRUCT`` qui
    ignore ``p`` pour satisfaire la construction nue fait croire aux
    gates de binding que la prop a été appliquée. Mesuré le 2026-08-19 —
    ``test_slot_never_orphans[Title.text]`` est passé de « skip honnête »
    à « rouge faux » en une ligne.
    """
    from tests.audit.test_binding_completeness import CONSTRUCT

    if rendered_html_of(cls) is None:
        assert cls.__name__ in CONSTRUCT, (
            f"{cls.__name__} sort du balayage sans être déclaré. Un "
            f"composant ne devient invisible que par un "
            f"_needs_context('raison') dans CONSTRUCT."
        )


def test_the_population_is_not_vacuous() -> None:
    """Plancher : le balayage voit bien la surface publique entière."""
    classes = public_component_classes()
    assert len(classes) >= 90, (
        f"Seulement {len(classes)} composants publics découverts (97 "
        f"mesurés le 2026-08-19) — la découverte est cassée, et tous les "
        f"balayages qui s'appuient dessus jugent sur un échantillon."
    )


@pytest.mark.parametrize("path", _gate_files(), ids=lambda p: p.name)
def test_no_gate_swallows_a_component(path: Path) -> None:
    lines = swallowing_lines(ast.parse(path.read_text(encoding="utf-8-sig")))
    declared = path.name in _PROBE_KWARG_DEBT

    if declared:
        assert lines, (
            f"{path.name} est dans _PROBE_KWARG_DEBT mais ne rattrape plus "
            f"rien. Retire l'entrée : une table qui garde des noms périmés "
            f"autorise plus que la réalité."
        )
        return

    assert not lines, (
        f"{path.name} fait sortir un composant de son balayage sans un mot "
        f"(ligne(s) {lines}). Un composant qui disparaît est la même "
        f"maladie qu'un fichier illisible sauté : le plancher vérifie « le "
        f"balayage a parlé », jamais « le balayage a tout construit ». "
        f"Quatre composants (Image, Iframe, MetaTag, Title) ont vécu hors "
        f"de trois gates de cette façon.\n\n"
        f"Utilise _discovery.rendered_html_of(cls) : elle bâtit par la "
        f"table partagée et ne rend None que pour un composant DÉCLARÉ. Si "
        f"ta construction passe une sonde (icon=, size=…), le refus est "
        f"définitionnel : compte tes abstentions et déclare un plafond, "
        f"plutôt que de les taire."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : le détecteur reconnaît encore le motif exact interdit.

    Les tests ci-dessus sont des interdictions ; ils passeraient tout
    aussi bien si ``_calls_in`` cessait de reconnaître un rendu. On le
    vérifie donc sur un cas fabriqué, et sur son jumeau licite.
    """
    faulty = ast.parse(
        "for cls in classes:\n"
        "    try:\n"
        "        with render_isolated():\n"
        "            html = serialize(cls().render())\n"
        "    except Exception:\n"
        "        continue\n"
    )
    assert swallowing_lines(faulty), (
        "Le détecteur ne voit plus le motif qu'il existe pour interdire — "
        "vérifie _calls_in / _handler_names avant de croire les gates saines."
    )

    declared = ast.parse(
        "for cls in classes:\n"
        "    try:\n"
        "        html = serialize(cls().render())\n"
        "    except _Skip:\n"
        "        continue\n"
    )
    assert not swallowing_lines(declared), (
        "Le détecteur rougit sur ``except _Skip`` — or c'est le canal "
        "DÉCLARÉ, celui qu'on veut voir utilisé. Faux positif."
    )


def test_the_debt_table_names_real_gates() -> None:
    """Une entrée de dette qui ne désigne aucun fichier est un mensonge."""
    known = {p.name for p in _gate_files()}
    ghosts = sorted(set(_PROBE_KWARG_DEBT) - known)
    assert not ghosts, (
        f"_PROBE_KWARG_DEBT nomme des gates qui n'existent pas : {ghosts}. "
        f"Une table qui survit à ses fichiers autorise en silence."
    )


@pytest.mark.parametrize("name", sorted(_PROBE_KWARG_DEBT), ids=lambda n: n)
def test_a_catching_gate_names_what_it_missed(name: str) -> None:
    """Rattraper est permis — se taire ne l'est pas.

    Sans ce test, ``_PROBE_KWARG_DEBT`` serait une simple liste
    d'exemptions, et le motif reviendrait par la porte qu'elle ouvre : il
    suffirait d'y ajouter une ligne. Avec lui, l'entrée coûte un test qui
    ÉNUMÈRE les composants ratés — donc le jour où un nouveau tombe dans
    le ``except``, il a un nom.
    """
    tree = ast.parse((_GATES_DIR / name).read_text(encoding="utf-8-sig"))
    declared = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
        and _DECLARATION_MARKER in node.name
    ]
    assert declared, (
        f"{name} rattrape une construction mais ne dit nulle part CE QU'IL "
        f"a raté.\n"
        f"  Ajoute un ``test_…{_DECLARATION_MARKER}`` qui compare les "
        f"abstentions mesurées à une table nommée — et refuse les deux "
        f"écarts : un composant qui tombe dans le ``except`` sans être "
        f"déclaré, ET une entrée qui ne tombe plus (sinon la table "
        f"pourrit).\n"
        f"  Un plafond chiffré ne suffit pas : il laisse passer « un qui "
        f"sort, un qui rentre »."
    )
