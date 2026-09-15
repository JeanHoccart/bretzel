"""Gate : la fin de requête écrit des CHAMPS, jamais le document.

Le commit réécrivait tout le document (``backend.save(to_dict())``), ce
qui effaçait ce qu'une requête concurrente venait d'écrire dans les
autres champs — la mise à jour perdue, sans erreur ni trace. Depuis le
2026-09-04 il n'envoie que les champs touchés, et le backend les
applique atomiquement (:meth:`Backend.merge`).

Deux façons de perdre ça de nouveau, et cette gate ferme les deux :

1. **quelqu'un remet un ``save`` dans le commit.** C'est un geste d'une
   ligne, et il redonne exactement l'ancien bug — visible nulle part,
   parce qu'il n'échoue jamais : il écrase ;
2. **un backend neuf n'implémente pas ``merge``.** Le protocole est
   structurel (:class:`~typing.Protocol`), donc rien à la définition ne
   force la méthode : l'oubli ne se voit qu'à l'exécution, au commit,
   c'est-à-dire en production. La gate compare la surface du protocole
   à celle de CHAQUE implémentation.

⚠️ ``save`` n'a plus AUCUN appelant dans ``bretzel/`` — il survit pour
les tests et l'amorçage, et parce qu'écrire un document entier reste une
opération légitime hors requête. C'est le rappeler depuis le registre
qui est interdit. Le jour où plus personne n'en a besoin, le sortir du
protocole vaudrait mieux que de le garder sous surveillance.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil

from bretzel.state import persistence
from bretzel.state.persistence.base import Backend
from tests.consistency._discovery import PACKAGE_DIR, source_of

#: Le fichier qui ne doit plus écrire de document.
_COMMIT_SOURCE = PACKAGE_DIR / "state" / "registry.py"


def protocol_methods() -> set[str]:
    """Les méthodes que le protocole déclare."""
    return {
        name
        for name, value in vars(Backend).items()
        if not name.startswith("_") and callable(value)
    }


def backend_classes() -> list[type]:
    """Les implémentations concrètes, DÉCOUVERTES et non listées.

    Le paquet est balayé plutôt qu'énuméré : une liste écrite à la main
    laisserait un ``postgres.py`` neuf hors du contrôle, et la gate
    resterait verte sur le trou même qu'elle existe pour fermer. Le
    plancher ne l'aurait pas vu non plus — il compterait deux backends,
    et deux y seraient.
    """
    found: list[type] = []
    for info in pkgutil.iter_modules(persistence.__path__):
        module = importlib.import_module(f"{persistence.__name__}.{info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is Backend or obj.__module__ != module.__name__:
                continue
            if not obj.__name__.endswith("Backend"):
                continue
            found.append(obj)
    return found


def document_writes() -> list[str]:
    """Les endroits du registre qui écrivent le document entier."""
    tree = source_of(_COMMIT_SOURCE).tree
    return [
        f"registry.py:{node.lineno}"
        for node in ast.walk(tree)
        if _is_backend_save(node)
    ]


def _is_backend_save(node: ast.AST) -> bool:
    """``self._backend.save(...)`` — l'écriture qui écrase.

    On vise l'ATTRIBUT appelé sur le backend, pas le mot ``save`` seul :
    un ``save`` local ou un helper qui s'appellerait ainsi n'est pas le
    geste surveillé.
    """
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    return (
        isinstance(fn, ast.Attribute)
        and fn.attr == "save"
        and isinstance(fn.value, ast.Attribute)
        and fn.value.attr == "_backend"
    )


def test_the_sweep_is_not_vacuous() -> None:
    """① Les planchers, lus depuis la découverte de CETTE gate."""
    assert len(backend_classes()) >= 2, (
        f"{len(backend_classes())} backend(s) découvert(s) — la "
        "comparaison de surface ne porterait sur rien."
    )
    # Pas de compte figé : « au moins sept » serait un second endroit où
    # bumper une méthode, et ne dirait rien de plus que la ligne suivante.
    assert "merge" in protocol_methods(), (
        "le protocole ne déclare plus ``merge`` — le contrôle de surface "
        "ci-dessous ne vérifierait alors plus rien d'utile."
    )


def test_the_registry_never_writes_a_whole_document() -> None:
    """② L'interdiction."""
    offenders = document_writes()
    assert not offenders, (
        "Le registre réécrit un document entier :\n  "
        + "\n  ".join(offenders)
        + "\n\nC'est la mise à jour perdue : deux requêtes qui se "
        "chevauchent sur la même clé, et la seconde efface les champs "
        "que la première venait d'écrire. Passe par "
        "``self._backend.merge(scope, key, changes, ttl=...)`` avec les "
        "SEULS champs modifiés."
    )


def test_every_backend_implements_the_whole_protocol() -> None:
    """③ Le contrôle POSITIF — un backend neuf ne peut pas oublier.

    Un :class:`~typing.Protocol` est structurel : rien n'oblige une
    implémentation à être complète, et le manque ne se manifeste qu'à
    l'appel. Ici il se manifeste au ``pytest``.
    """
    attendu = protocol_methods()
    manques = {
        cls.__name__: sorted(attendu - set(dir(cls)))
        for cls in backend_classes()
        if attendu - set(dir(cls))
    }
    assert not manques, (
        f"implémentations incomplètes du protocole Backend : {manques}. "
        "Le protocole étant structurel, l'oubli ne lèverait qu'au "
        "moment de l'appel — en production, pour ``merge`` : au commit."
    )


def test_the_detector_still_bites() -> None:
    """④ La mutation, deux versants."""
    coupable = ast.parse("self._backend.save(scope, key, state.to_dict())")
    innocent = ast.parse("self._backend.merge(scope, key, changes)")
    autre_save = ast.parse("self._fichier.save(chemin)")

    assert any(_is_backend_save(n) for n in ast.walk(coupable))
    assert not any(_is_backend_save(n) for n in ast.walk(innocent))
    assert not any(_is_backend_save(n) for n in ast.walk(autre_save))

    # Le contrôle sur un cas RÉEL : le registre appelle bien le backend
    # quelque part, sinon l'interdiction serait verte sur un fichier qui
    # ne parle plus au stockage du tout.
    tree = source_of(_COMMIT_SOURCE).tree
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "merge"
        for node in ast.walk(tree)
    ), "le registre n'appelle plus ``merge`` — il n'écrit donc plus rien."
