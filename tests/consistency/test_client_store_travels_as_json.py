"""Gate — le magasin client part en JSON pour tout ce qui n'est pas scalaire.

Le pendant, côté pont, de ``test_a_bound_control_transmits_every_value`` :
là-bas c'est un porteur caché qui sérialise, ici c'est
``injectParameters``. Les deux chemins doivent porter la MÊME convention,
sinon un champ ``list`` d'état ne veut pas dire la même chose selon qu'un
composant l'écrit ou que le magasin le transporte.

Ce que ça garde, mesuré le 2026-08-19
--------------------------------------
htmx traite un tableau à part : ``formDataFromObject`` fait
``obj[key].forEach(v => append(key, v))``. Deux conséquences :

- ``["a","b"]`` partait en DEUX champs de même nom, et le serveur gardait
  le dernier — ``["a","b"]`` arrivait comme ``"b"`` ;
- ``[]`` n'ajoutait **rien**, donc la clé était absente du corps. Comme
  l'hydratation n'écrit que les champs présents, **une liste client vidée
  ne pouvait plus jamais vider son champ serveur**. C'est le jumeau exact
  de la case décochée qui ne soumet rien, sur l'autre transport.

Vérifié au navigateur avant d'être écrit : avec l'encodage,
``Magasin.default.pleine`` arrive en ``["a","b"]`` (une chaîne), le serveur
hydrate ``['a', 'b']``, et vider la liste côté client fait bien tomber le
champ serveur à ``[]``.

Pourquoi une gate de SOURCE et pas de comportement
--------------------------------------------------
Le comportement se prouve dans un navigateur, et il l'est —
``tests/runtime_js/test_client_store_travels_as_json.py``. Mais cette
suite-là ne tourne pas dans le sous-ensemble rapide, et la régression que
cette gate attrape tient à une seule ligne : quelqu'un qui réécrit
``injectParameters`` et repose la valeur brute. Elle est ici pour rougir en
trois secondes, pas pour remplacer le navigateur.
"""

from __future__ import annotations

import re

from tests.consistency._discovery import runtime_slabs

_BRIDGE = "05_bridge.js"

#: L'affectation qui pose une valeur du magasin dans le corps de la
#: requête. C'est LA ligne : elle doit passer par l'encodeur.
_ASSIGNMENT = re.compile(
    r"detail\.parameters\[[^\]]+\]\s*=\s*(?P<value>[^;]+);"
)

#: L'encodeur lui-même : il doit distinguer l'objet du scalaire.
_ENCODER = re.compile(
    r"function\s+wireValue\s*\([^)]*\)\s*\{(?P<body>.*?)\n\s{2}\}",
    re.DOTALL,
)


def bridge_source() -> str:
    """La source du pont, prise dans le balayage PARTAGÉ des modules.

    ``runtime_slabs()`` et pas un chemin réécrit ici : trois gates
    écrivaient ce glob à la main, et le jour où ``_src/`` bouge chacune
    devient silencieusement vacuoise (cf. sa docstring).
    """
    for path in runtime_slabs():
        if path.name == _BRIDGE:
            return path.read_text(encoding="utf-8-sig")
    raise AssertionError(
        f"{_BRIDGE} est introuvable dans les modules du runtime — le pont "
        f"a été renommé ou déplacé, et cette gate ne lit plus rien."
    )


def test_the_sweep_reads_the_bridge() -> None:
    """Le plancher : le fichier existe et porte bien l'injection.

    Un chemin cassé rendrait les deux tests suivants vacuously verts sur
    une chaîne vide.
    """
    source = bridge_source()
    assert "injectParameters" in source, (
        f"{_BRIDGE} ne contient plus `injectParameters` — le pont a été "
        f"réorganisé, et cette gate ne regarde plus rien."
    )
    assert _ASSIGNMENT.search(source), (
        f"aucune affectation `detail.parameters[…] = …` trouvée dans "
        f"{_BRIDGE} : le détecteur ne reconnaît plus l'injection."
    )


def test_the_store_is_encoded_before_it_ships() -> None:
    """L'interdiction : la valeur ne part jamais brute."""
    for match in _ASSIGNMENT.finditer(bridge_source()):
        value = match.group("value").strip()
        assert "wireValue(" in value, (
            f"le pont pose `{value}` tel quel dans le corps de la requête. "
            f"htmx éclate un tableau élément par élément et n'ajoute RIEN "
            f"pour un tableau vide — donc une liste client ne peut plus "
            f"vider son champ serveur. Passe par `wireValue()`."
        )


def test_the_encoder_spares_scalars() -> None:
    """Le versant LICITE, et il compte autant que l'autre.

    Encoder TOUT ferait arriver ``'\"texte\"'`` là où le champ attend
    ``texte`` : chaque champ ``str`` d'état client gagnerait une paire de
    guillemets à chaque aller-retour, et les recompterait au suivant.
    """
    body = _ENCODER.search(bridge_source())
    assert body, "`wireValue` a disparu ou changé de forme"
    text = body.group("body")
    assert "typeof value === \"object\"" in text, (
        "`wireValue` n'écarte plus les scalaires : il doit n'encoder que "
        "les valeurs composites."
    )
    assert "JSON.stringify" in text, (
        "`wireValue` n'encode plus rien."
    )
    assert "null" in text, (
        "`wireValue` ne traite plus `null` à part — `typeof null` vaut "
        "`\"object\"`, donc un champ nul partirait en `\"null\"`."
    )


def test_the_detector_still_bites() -> None:
    """La mutation, dans les deux sens, sur des lignes FABRIQUÉES."""
    offending = 'detail.parameters[path + "." + field] = fields[field];'
    licit = 'detail.parameters[path + "." + field] = wireValue(fields[field]);'

    assert "wireValue(" not in _ASSIGNMENT.search(offending).group("value"), (
        "le détecteur ne voit plus une valeur posée brute"
    )
    assert "wireValue(" in _ASSIGNMENT.search(licit).group("value"), (
        "le détecteur refuse la forme correcte"
    )
