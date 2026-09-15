"""Un type métier déclaré traverse le magasin et revient identique.

Avant le 2026-09-05, `jour: date` était **accepté**, le magasin mémoire
gardait l'objet Python vivant, et la faute attendait le branchement de
Redis : ça marchait en dev et cassait au déploiement — le pire profil.
Second symptôme, plus discret : un formulaire écrivant dans ce champ y
laissait une ``str``, sans erreur.

Trois propriétés sont gardées ici, et la première est celle qui manquait :

1. **l'encodage a lieu AVANT le magasin**, une seule fois, donc la
   mémoire et Redis ne peuvent plus diverger ;
2. l'aller-retour rend l'**égal** — sans quoi le registre réécrirait le
   champ à chaque requête en croyant qu'il a changé ;
3. une chaîne de formulaire est décodée vers le type déclaré.
"""

from __future__ import annotations

import datetime as dt
import decimal
import enum
import json
import uuid

import pytest

from bretzel.state import SessionState, field, register_type
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry


class Couleur(enum.Enum):
    ROUGE = "rouge"
    BLEU = "bleu"


class Reference:
    """Une classe d'app quelconque — le cas que ``register_type`` sert."""

    def __init__(self, code: str) -> None:
        self.code = code

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Reference) and other.code == self.code

    def __repr__(self) -> str:
        return f"Reference({self.code!r})"


register_type(Reference, encode=lambda r: r.code, decode=Reference)


class RefClient(Reference):
    """Un héritier — le cas que ``subclasses=True`` sert."""


class Famille:
    """Une base d'app dont les champs déclarent les HÉRITIERS."""

    def __init__(self, code: str) -> None:
        self.code = code

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and other.code == self.code

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.code!r})"


class Membre(Famille):
    pass


register_type(
    Famille,
    encode=lambda f: f.code,
    decode=lambda brut, cible: cible(brut),
    subclasses=True,
)


class Facture(SessionState):
    jour: dt.date = field(default_factory=lambda: dt.date(2026, 1, 1))
    quand: dt.datetime = field(
        default_factory=lambda: dt.datetime(2026, 1, 1, 0, 0)
    )
    heure: dt.time = field(default_factory=lambda: dt.time(0, 0))
    montant: decimal.Decimal = field(
        default_factory=lambda: decimal.Decimal("0")
    )
    ident: uuid.UUID = field(default_factory=lambda: uuid.UUID(int=1))
    teinte: Couleur = field(default=Couleur.ROUGE)


#: Ce qu'on écrit, et ce qu'on doit relire à l'identique.
_VALEURS = {
    "jour": dt.date(2026, 3, 4),
    "quand": dt.datetime(2026, 3, 4, 5, 6, 7),
    "heure": dt.time(8, 9, 10),
    # Deux décimales SIGNIFICATIVES : ``Decimal("19.90")`` et
    # ``Decimal("19.9")`` sont égales mais ne s'écrivent pas pareil, et un
    # encodage par ``float`` perdrait justement la raison d'être du type.
    "montant": decimal.Decimal("19.90"),
    "ident": uuid.UUID(int=42),
    "teinte": Couleur.BLEU,
}


async def _ecrire() -> tuple[MemoryBackend, dict]:
    backend = MemoryBackend()
    registre = StateRegistry(backend=backend, session_id="s1")
    etat = Facture()
    registre.register(etat)
    for nom, valeur in _VALEURS.items():
        setattr(etat, nom, valeur)
    await registre.commit()
    ligne = next(iter(backend._data.values())).data  # noqa: SLF001
    return backend, ligne


@pytest.mark.anyio
async def test_the_store_only_ever_sees_json() -> None:
    """L'interdiction, et la raison d'être de tout le mécanisme.

    Le magasin mémoire acceptait un objet Python vivant, donc le dev ne
    voyait rien et Redis levait en production. Encoder AVANT le magasin
    — dans le registre, pas dans chaque backend — rend la divergence
    impossible par construction plutôt que par vigilance.
    """
    _, ligne = await _ecrire()
    json.dumps(ligne)  # lève si un objet Python a survécu jusque-là
    for nom, valeur in ligne.items():
        assert isinstance(valeur, (str, int, float, bool, list, dict)), (
            f"{nom} arrive au magasin en {type(valeur).__name__} : le "
            f"backend mémoire l'acceptera et Redis lèvera en production."
        )


@pytest.mark.anyio
async def test_a_round_trip_gives_back_the_equal() -> None:
    """L'aller-retour, valeur par valeur.

    Le registre compare la photo prise à la lecture avec la valeur
    courante pour décider quoi écrire : un codec qui perd de
    l'information ferait réécrire le champ à chaque requête, sans que
    rien ne le signale.
    """
    backend, _ = await _ecrire()
    relu = StateRegistry(backend=backend, session_id="s1").try_sync_resolve(
        Facture
    )
    assert relu is not None, "l'état n'a pas été relu du tout"
    for nom, attendu in _VALEURS.items():
        obtenu = getattr(relu, nom)
        assert type(obtenu) is type(attendu), (
            f"{nom} revient en {type(obtenu).__name__} au lieu de "
            f"{type(attendu).__name__}"
        )
        assert obtenu == attendu, f"{nom} : {obtenu!r} != {attendu!r}"


@pytest.mark.anyio
async def test_a_decimal_keeps_its_written_form() -> None:
    """Le versant que ``float`` casserait, et qui ne se voit pas autrement.

    ``Decimal("19.90") == Decimal("19.9")`` est vrai, donc l'égalité seule
    ne prouve rien. C'est la FORME écrite qui dit si le codec est passé
    par un flottant.
    """
    _, ligne = await _ecrire()
    assert ligne["montant"] == "19.90", (
        f"montant écrit {ligne['montant']!r} : le codec est passé par un "
        f"float, ce qui retire à Decimal sa raison d'être."
    )


def test_a_form_string_lands_as_the_declared_type() -> None:
    """Le second symptôme : un champ typé qui gardait la chaîne.

    Même chemin que l'hydratation (``Field.__set__``), donc une seule
    mécanique pour les deux — les séparer avait laissé celle-ci muette.
    """
    etat = Facture()
    etat.jour = "2026-12-25"
    etat.montant = "3.50"
    etat.teinte = "bleu"
    assert etat.jour == dt.date(2026, 12, 25)
    assert etat.montant == decimal.Decimal("3.50")
    assert etat.teinte is Couleur.BLEU


def test_an_unstorable_type_is_refused_at_import() -> None:
    """Tôt, pas à l'écriture — sinon la faute attend la production."""
    with pytest.raises(TypeError, match="que le magasin ne sait pas écrire"):

        class Cassee(SessionState):
            truc: object = field(default=None)


def test_any_is_the_declared_escape_hatch() -> None:
    """Le versant LICITE. Sans lui, la garde interdirait un champ
    volontairement non typé et on ne le saurait qu'en cassant une app."""
    from typing import Any

    class Libre(SessionState):
        charge: Any = field(default=None)

    assert Libre().charge is None


def test_an_app_can_declare_its_own_type() -> None:
    """``register_type`` — le seul symbole que cette fonctionnalité ajoute.

    ⚠️ ``Reference`` est déclaré AU NIVEAU MODULE, et il le faut :
    ``typing.get_type_hints`` ne sait pas résoudre une classe définie
    dans un corps de fonction, donc le champ garderait son annotation en
    chaîne et le décodeur ne saurait pas quoi viser. C'est du Python
    standard, pas une limite de la table — mais ça se paie une fois
    quand on écrit le test.
    """
    class Dossier(SessionState):
        ref: Reference = field(default_factory=lambda: Reference("A1"))

    etat = Dossier()
    etat.ref = "B2"  # une chaîne de formulaire passe par le décodeur
    assert etat.ref == Reference("B2")


def test_enum_goes_through_the_public_door() -> None:
    """``Enum`` n'est plus un cas particulier, et ne doit pas le redevenir.

    Il était codé en dur en cinq branches jusqu'au 2026-09-06, et
    ``register_type`` REFUSAIT une énumération — le signe qu'un mécanisme
    public a une porte trop étroite. Il s'inscrit maintenant comme
    n'importe quelle famille d'app, en bas de ``state/types.py``.

    Cette gate lit la table : si quelqu'un remet un ``if isinstance(…,
    Enum)`` dans le code et retire l'inscription, elle rougit.
    """
    from enum import Enum

    from bretzel.state.types import _CODECS

    codec = _CODECS.get(Enum)
    assert codec is not None, (
        "Enum n'est plus inscrit dans la table : il est redevenu un cas "
        "particulier codé en dur."
    )
    assert codec.subclasses, (
        "le codec d'Enum n'est pas déclaré famille — une énumération "
        "concrète ne le trouverait donc pas par héritage."
    )


# ── Le catalogue : une seule règle, plus d'exception ────────────────────
#
# Chaque forme ci-dessous doit se déclarer, s'écrire en JSON et revenir
# ÉGALE. C'est la promesse que le module fait, et la raison pour laquelle
# ``list[date]``, ``tuple``, ``set`` et les familles ont cessé d'être des
# cas particuliers le 2026-09-06.

_CATALOGUE: list[tuple[str, object, object]] = [
    ("str", str, "x"),
    ("int", int, 3),
    ("bool", bool, True),
    ("nullable", str | None, None),
    ("date", dt.date, dt.date(2026, 3, 4)),
    ("datetime", dt.datetime, dt.datetime(2026, 3, 4, 5, 6)),
    ("Decimal", decimal.Decimal, decimal.Decimal("19.90")),
    ("UUID", uuid.UUID, uuid.UUID(int=42)),
    ("Enum", Couleur, Couleur.BLEU),
    ("liste de natifs", list[str], ["a", "b"]),
    ("liste de dates", list[dt.date], [dt.date(2026, 1, 1)]),
    ("dict de Decimal", dict[str, decimal.Decimal],
     {"ht": decimal.Decimal("1.10")}),
    ("tuple de dates", tuple[dt.date, dt.date],
     (dt.date(2026, 1, 1), dt.date(2026, 2, 2))),
    ("set d'UUID", set[uuid.UUID], {uuid.UUID(int=7)}),
    ("imbriqué", dict[str, list[Couleur]], {"x": [Couleur.ROUGE]}),
    ("type d'app", Reference, Reference("A1")),
    ("famille d'app", Membre, Membre("B2")),
]


@pytest.mark.parametrize(
    "nom, type_, valeur", _CATALOGUE, ids=[c[0] for c in _CATALOGUE]
)
def test_every_accepted_shape_round_trips(nom, type_, valeur) -> None:
    """Le catalogue, forme par forme : déclarable, JSON, et ÉGAL au retour."""
    from bretzel.state.types import decode_value, encode_value, is_storable

    assert is_storable(type_), f"{nom} est refusé à la déclaration"
    ecrit = encode_value(valeur)
    json.dumps(ecrit)  # lève si un objet Python a survécu
    relu = decode_value(type_, ecrit)
    assert type(relu) is type(valeur), (
        f"{nom} revient en {type(relu).__name__} au lieu de "
        f"{type(valeur).__name__}"
    )
    assert relu == valeur, f"{nom} : {relu!r} != {valeur!r}"


@pytest.mark.parametrize("type_", [object, bytes, list[object], tuple[object]])
def test_a_type_with_no_codec_is_still_refused(type_) -> None:
    """Le versant qui MORD. Sans lui, un ``is_storable`` qui rendrait
    toujours ``True`` passerait tout le catalogue ci-dessus."""
    from bretzel.state.types import is_storable

    assert not is_storable(type_)


def test_a_family_covers_its_heirs() -> None:
    """La porte publique qui remplace le cas particulier ``Enum``.

    ``Enum`` s'inscrit par elle, en bas de ``state/types.py`` : il était
    codé en dur en cinq branches jusqu'au 2026-09-06, et un mécanisme
    public qui doit REFUSER une entrée légitime — c'était le cas — dit
    que la porte est trop étroite.
    """
    class Dossier(SessionState):
        membre: Membre = field(default_factory=lambda: Membre("A"))

    etat = Dossier()
    etat.membre = "Z9"  # une chaîne de formulaire
    assert etat.membre == Membre("Z9")
    assert type(etat.membre) is Membre, (
        "la famille a rendu la classe de BASE : le décodeur n'a pas reçu "
        "la classe concrète."
    )


def test_a_declared_subclass_without_the_flag_is_refused() -> None:
    """Le pendant : sans ``subclasses=True``, un héritier reste refusé.

    C'est ce qui empêche un champ ``datetime`` de retomber sur le codec
    de ``date`` — une ``datetime`` EST une ``date``, et l'heure
    disparaîtrait en silence.
    """
    from bretzel.state.types import encode_value, is_storable

    assert not is_storable(RefClient), (
        "un héritier d'un type NON déclaré famille est accepté : le "
        "décodage rendrait la classe de base."
    )
    assert is_storable(dt.datetime) and is_storable(dt.date)
    assert encode_value(dt.datetime(2026, 3, 4, 5, 6)) == "2026-03-04T05:06:00"
