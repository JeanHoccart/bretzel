"""Gate : la config de transport d'un ``ClientState`` est un protocole à
deux moitiés — elle doit être **déclarable** en Python et **lue** par le
runtime, aux deux bouts.

``build_envelope()`` émet, pour chaque instance de ``ClientState``, un petit
dictionnaire de config à côté de ses champs : ``persist``,
``send_to_server``. Le boot (``00_index.js``) le recopie dans
``$bz._config``, et le bridge (``05_bridge.js``) branche dessus. Trois
fichiers, deux langages, aucune vérification entre eux.

Il y en avait besoin. Mesuré le 2026-08-14, **les deux sens étaient
cassés en même temps** :

- ``send_to_server`` : lu par le bridge (``if (cfg.send_to_server ===
  false) continue``), sérialisé par l'envelope — mais en
  ``getattr(state, "__send_to_server__", True)``, et **rien dans tout
  ``bretzel/`` n'écrivait jamais cet attribut**. Le ``getattr`` retombait
  donc toujours sur son défaut, et la branche cliente était morte depuis
  toujours. Elle avait l'air livrée : elle est écrite, testée par
  personne, et le commentaire au-dessus disait « knobs land with the V3
  state layer ».
- ``sync`` : même forme, plus une faute de conception. La moitié cliente
  (un mémo ``lastSent`` par instance, n'envoyant que les champs modifiés)
  ne pouvait pas être correcte — un ``ClientState`` n'est jamais persisté
  côté serveur, donc un champ omis parce qu'« inchangé » retombe sur son
  défaut de classe, pas sur sa valeur précédente. Retiré du fil et du
  bridge plutôt que gardé en dormance.

C'est exactement le défaut du champ ``palette`` (émis par l'envelope, lu
par personne, retiré le 2026-08-01) pris par l'autre bout — **lu par
personne** vs **écrivable par personne**. Un champ mort dans chaque
direction, sur la même structure, à deux semaines d'écart. D'où une gate
qui tient les deux sens.

Parenté : ``test_bridge_error_kinds_are_emitted.py`` fait le même travail
un cran plus bas (le vocabulaire à l'intérieur du ``<bz-patch>``). Ici
c'est le vocabulaire de l'``<bz-envelope>``.
"""

from __future__ import annotations

import functools
import inspect
import re

import pytest

from bretzel.runtime.envelope import build_envelope, build_patch
from bretzel.state import field
from bretzel.state.scopes.client import ClientState
from tests.consistency._discovery import (
    assert_runtime_sweep_is_not_vacuous,
    runtime_slabs,
    strip_js_comments,
)

#: Les clés de l'entrée d'instance qui ne sont PAS de la config de
#: transport. ``fields`` porte les valeurs elles-mêmes — il n'a pas de
#: kwarg de classe correspondant, et c'est normal.
_NOT_CONFIG = frozenset({"fields"})

#: Le vocabulaire de config que le client consomme, DÉCLARÉ par le runtime
#: dans un littéral unique (``00_index.js`` § ``CONFIG_KEYS``).
#:
#: La première version de cette gate n'avait pas d'ancre : elle cherchait
#: les lectures à la regex (``\b(?:entry|cfg)\.([a-z_]+)\b``), ramassait
#: 14 clés dont 11 venaient du calendrier et du file_upload, et
#: compensait par un ensemble de noms écrit à la main. Le résultat avait
#: la forme d'un balayage et le pouvoir d'une liste : une clé NEUVE lue
#: sans moitié serveur passait au vert, parce qu'elle n'était pas dans la
#: liste. C'est le contraire de ce que la gate promet.
#:
#: La gate soeur (``test_bridge_error_kinds_are_emitted``) n'a pas ce
#: problème parce que ``kind === "…"`` est une ancre syntaxique
#: non-ambiguë. Ici l'ancre a dû être CRÉÉE côté JS — dix lignes de
#: runtime pour qu'une gate cesse de deviner.
_JS_CONFIG_KEYS = re.compile(r"CONFIG_KEYS\s*=\s*\[([^\]]*)\]")
_JS_QUOTED = re.compile(r"""["']([a-z_]+)["']""")


class _Probe(ClientState):
    """Sonde minimale — un ``ClientState`` nu, tous défauts."""

    flag: bool = field(default=False)


def _envelope_config_keys() -> frozenset[str]:
    """Les clés de config que l'envelope émet réellement, pour une instance.

    Lues sur la SORTIE de ``build_envelope`` et non dans son source : c'est
    ce qui part sur le fil qui fait foi, pas ce que le littéral a l'air de
    contenir.
    """
    envelope = build_envelope([_Probe()], "csrf-token")
    (entry,) = envelope["client_state"].values()
    return frozenset(entry) - _NOT_CONFIG


def _declarable_kwargs() -> frozenset[str]:
    """Les kwargs de classe que ``ClientState`` accepte.

    ``__init_subclass__`` est la seule porte : c'est là que
    ``class X(ClientState, persist="local")`` atterrit.
    """
    params = inspect.signature(ClientState.__init_subclass__).parameters
    return frozenset(
        name
        for name, p in params.items()
        if p.kind is inspect.Parameter.KEYWORD_ONLY
    )


@functools.lru_cache(maxsize=1)
def _js_config_reads() -> frozenset[str]:
    """Les clés déclarées dans ``CONFIG_KEYS``, commentaires ôtés.

    On balaie ``_src/`` (la source qu'on édite) et non ``runtime.js`` (le
    bundle qui en dérive), via :func:`runtime_slabs` — le glob écrit à la
    main est exactement ce contre quoi son docstring met en garde : chaque
    copie devient silencieusement vacuoise le jour où ``_src/`` bouge.

    Le strip des commentaires n'est pas décoratif : les modules concernés
    PARLENT de la clé ``sync`` en prose pour expliquer son retrait — sans
    le strip, la gate lirait une note historique comme une déclaration
    vivante.
    """
    keys: set[str] = set()
    for path in runtime_slabs():
        text = strip_js_comments(path.read_text(encoding="utf-8"))
        for literal in _JS_CONFIG_KEYS.findall(text):
            keys.update(_JS_QUOTED.findall(literal))
    return frozenset(keys)


def test_every_emitted_config_key_is_declarable() -> None:
    """Sens 1 — ce que le serveur émet, un utilisateur doit pouvoir le régler.

    C'est le sens qui a rougi pour ``send_to_server`` : la clé partait sur
    le fil avec une valeur qu'aucune classe ne pouvait changer.
    """
    emitted = _envelope_config_keys()
    declarable = _declarable_kwargs()

    unsettable = emitted - declarable
    assert not unsettable, (
        "L'envelope émet des clés de config qu'aucun kwarg de classe ne "
        f"peut régler : {sorted(unsettable)}.\n\n"
        f"Kwargs acceptés par ClientState.__init_subclass__ : "
        f"{sorted(declarable)}.\n\n"
        "Soit la moitié Python manque (ajouter le kwarg + le ClassVar), "
        "soit la clé n'a rien à faire sur le fil (la retirer de "
        "build_envelope). Ne pas la laisser : une clé figée à son défaut "
        "se lit comme un réglage livré — c'est ce qu'a fait "
        "``send_to_server`` avant le 2026-08-14."
    )


def test_every_config_key_the_runtime_reads_is_emitted() -> None:
    """Sens 2 — ce que le client lit, le serveur doit l'écrire.

    C'est le sens qui a rougi pour ``sync`` : le bridge branchait sur une
    clé que plus rien n'aurait dû produire.

    Le ⊆ est volontairement unique. Une clé émise que le JS ignore n'est
    pas un bug de protocole (le serveur peut enrichir l'envelope avant que
    le runtime s'en serve) ; l'inverse ment.
    """
    emitted = _envelope_config_keys()
    declared = _js_config_reads()

    unproduced = declared - emitted
    assert not unproduced, (
        "Le runtime déclare consommer des clés de config que le serveur "
        f"n'émet pas : {sorted(unproduced)}.\n\n"
        f"Émises par build_envelope : {sorted(emitted)}.\n"
        f"Déclarées dans 00_index.js § CONFIG_KEYS : {sorted(declared)}.\n\n"
        "Du code client prêt pour une valeur que personne ne peut envoyer "
        "— c'est ce qu'a été la clé `sync` jusqu'au 2026-08-14."
    )


def test_send_to_server_actually_reaches_the_wire() -> None:
    """Le kwarg n'est pas décoratif : il change ce qui part.

    Le ⊆ du dessus vérifie que la clé et le kwarg portent le même NOM.
    Il passerait au vert sur un kwarg accepté puis jeté — exactement l'état
    d'avant, en pire (l'API promettrait le réglage). Celui-ci mesure l'effet.
    """

    class _Silent(ClientState, send_to_server=False):
        answer: str = field(default='')

    class _Loud(ClientState):
        answer: str = field(default='')

    (silent,) = build_envelope([_Silent()], "t")["client_state"].values()
    (loud,) = build_envelope([_Loud()], "t")["client_state"].values()

    assert silent["send_to_server"] is False
    assert loud["send_to_server"] is True, (
        "Le défaut a changé : une classe qui ne déclare rien doit remonter "
        "au serveur. Un défaut inversé rendrait muets tous les états "
        "existants, sans erreur — les handlers liraient des défauts."
    )


def test_send_to_server_rejects_a_truthy_non_bool() -> None:
    """``send_to_server="false"`` est truthy — la faute la plus coûteuse.

    Elle ferait l'inverse de ce qu'on lit, en silence. C'est le seul des
    deux réglages dont une mauvaise valeur ne se voit pas à l'usage
    (``persist=`` lève déjà sur son enum fermé).
    """
    with pytest.raises(ValueError, match="send_to_server"):

        class _Bad(ClientState, send_to_server="false"):  # type: ignore[arg-type]
            pass


def test_the_seed_patch_carries_the_same_config_as_the_envelope() -> None:
    """Deux porteurs, un vocabulaire — sinon ils redérivent.

    La config voyage par DEUX chemins : l'``<bz-envelope>`` au chargement
    dur, et le ``<bz-patch>`` de seed en nav partielle (``hx-boost``, qui
    n'émet pas d'envelope). Elle n'avait qu'un porteur jusqu'au
    2026-08-15 : un ``ClientState`` découvert en nav partielle recevait
    ses champs sans sa config — ``send_to_server`` ignoré et, plus vieux,
    ``persist`` sans adaptateur, donc une valeur sauvegardée jamais relue.

    Le ⊆ ne suffirait pas ici : deux littéraux de dict séparés
    s'accordent le jour où on les écrit et divergent au bouton suivant.
    On exige donc l'ÉGALITÉ des clés, et ``_transport_config()`` est le
    point unique qui la garantit.
    """
    (entry,) = build_envelope([_Probe()], "t")["client_state"].values()
    patch = build_patch([_Probe()], include_unchanged=True)

    assert "config" in patch, (
        "Le patch de seed ne porte plus de config — une nav partielle "
        "redevient aveugle. Cf. build_patch(include_unchanged=True)."
    )
    (seeded,) = patch["config"].values()

    assert set(seeded) == set(entry) - _NOT_CONFIG, (
        "L'envelope et le patch de seed ne portent pas le même "
        f"vocabulaire de config.\n  envelope : {sorted(set(entry) - _NOT_CONFIG)}"
        f"\n  patch    : {sorted(seeded)}\n\n"
        "Les deux doivent dériver de _transport_config() — deux littéraux "
        "séparés divergent au réglage suivant."
    )


def test_an_ordinary_action_patch_carries_no_config() -> None:
    """La config est réservée au SEED, pas à chaque clic.

    Une réponse d'action ordinaire parle d'instances que le client a déjà
    configurées au boot ou au seed : y remettre la config serait des
    octets sur chaque interaction, pour rien. C'est la contrepartie
    directe du test précédent — sans elle, « faire porter la config au
    patch » se généraliserait silencieusement à tout le trafic.
    """
    probe = _Probe()
    probe.flag = True  # rend l'instance sale, donc présente dans le patch

    patch = build_patch([probe])

    assert patch["patches"], "l'instance sale devrait être dans le patch"
    assert "config" not in patch, (
        "Une réponse d'action ordinaire porte la config de transport : "
        "c'est du poids sur chaque clic, pour une valeur que le client "
        "connaît déjà."
    )


def test_a_two_way_prop_refuses_a_state_that_never_comes_back() -> None:
    """La seule perte de données SILENCIEUSE que le réglage rend possible.

    Une prop two-way est écrite par le client : sa valeur n'existe que dans
    le navigateur. Sur un état ``send_to_server=False`` elle n'est jamais
    postée — l'utilisateur tape, le handler lit le défaut de classe, et
    rien ne signale rien.

    La garde vit dans ``Component.__init__``, dans la boucle
    ``TWO_WAY_PROPS`` qui refusait déjà une ``ClientExpression`` pour une
    raison de même famille (cible non assignable). Elle a été rendue
    décidable en faisant porter au ``ClientBinding`` le drapeau de sa
    classe — il n'en portait que le NOM, et c'est ce qui avait fait
    documenter le piège en prose plutôt que le refuser.
    """
    from bretzel import ui
    from bretzel.components.base.component import ComponentUsageError
    from bretzel.components.base.testing import render_isolated
    from bretzel.state.scopes.client import rendering_scope

    class Down(ClientState, send_to_server=False):
        text: str = field(default='')

    class Up(ClientState):
        text: str = field(default='')

    # Les deux contextes sont nécessaires et distincts : ``render_isolated``
    # donne au composant son RenderContext, ``rendering_scope`` est ce qui
    # fait qu'une lecture de champ rend une ``ClientBinding`` plutôt que la
    # valeur Python.
    with render_isolated(), rendering_scope():
        with pytest.raises(ComponentUsageError, match="send_to_server"):
            ui.input(value=Down().text)

        # Le témoin : la même ligne sur un état ordinaire passe. Sans lui,
        # une garde trop large (refusant TOUTE ClientBinding) rendrait le
        # test vert en cassant le framework entier.
        ui.input(value=Up().text)


def test_the_sync_knob_did_not_come_back() -> None:
    """La décision, que le ⊆ ne sait pas exprimer.

    Les deux ⊆ passent au vert dès que les deux moitiés s'accordent. Or
    quelqu'un qui redécouvre le besoin — « on renvoie tout l'état à chaque
    clic, c'est du gâchis » — écrirait naturellement LES DEUX : le kwarg
    ``sync=`` et la branche du bridge. Le protocole serait cohérent et le
    comportement faux.

    Ce qui rend ``sync="delta"`` faux n'est pas côté fil : c'est que le
    serveur ne garde aucune trace d'un ``ClientState`` entre deux requêtes
    (``StateRegistry.commit`` l'exclut). Un champ omis retombe sur son
    défaut de classe. Le rouvrir demande d'abord cette mémoire serveur.
    """
    assert "sync" not in _declarable_kwargs(), (
        "Le kwarg `sync=` est de retour sur ClientState. Il ne peut pas "
        "être correct tant que le serveur ne mémorise pas le dernier état "
        "client connu : sans ça, un champ omis parce qu'inchangé est lu "
        "comme son DÉFAUT de classe, silencieusement, à partir du 2e POST."
    )
    assert "sync" not in _envelope_config_keys(), (
        "La clé `sync` est de retour sur le fil — voir ci-dessus."
    )
    assert "sync" not in _js_config_reads(), (
        "Le runtime relit `cfg.sync` / `entry.sync`. La moitié cliente "
        "(mémo lastSent) était écrite et fausse ; ne pas la restaurer "
        "sans sa moitié serveur."
    )


def test_the_sweeps_are_not_vacuous() -> None:
    """Plancher — il porte sur la DÉCOUVERTE, pas sur une population.

    Les trois assertions structurelles sont des ``⊆`` ou des ``not in`` :
    elles passent trivialement si un balayage ne trouve plus rien. Quatre
    façons d'y arriver sans le vouloir — ``build_envelope`` renommé,
    ``__init_subclass__`` réécrit avec un ``**kwargs`` fourre-tout (plus
    aucun KEYWORD_ONLY nommé), le littéral ``CONFIG_KEYS`` renommé ou
    reformaté hors du motif, ou ``_src/`` déplacé (d'où l'appel au
    plancher partagé, qui compte les modules balayés).

    On ancre donc sur ce que chaque balayage doit AVOIR TROUVÉ, en citant
    la clé la moins susceptible de disparaître sans qu'on le remarque.
    """
    assert_runtime_sweep_is_not_vacuous()

    emitted = _envelope_config_keys()
    declarable = _declarable_kwargs()
    declared = _js_config_reads()

    assert "persist" in emitted, (
        "build_envelope n'émet plus `persist` — le balayage de l'envelope "
        "est débranché (fonction renommée ? forme de l'entrée changée ?), "
        "et les ⊆ ne vérifient plus rien."
    )
    assert "persist" in declarable, (
        "ClientState.__init_subclass__ n'expose plus `persist=` en "
        "keyword-only — l'introspection des kwargs est débranchée "
        "(un **kwargs fourre-tout l'aurait avalé)."
    )
    assert "send_to_server" in declared, (
        "Le littéral `CONFIG_KEYS` de 00_index.js n'a pas été trouvé, ou "
        "ne contient plus `send_to_server` — l'ancre côté JS est perdue "
        "et le ⊆ client→serveur ne vérifie plus rien. Réparer "
        "_JS_CONFIG_KEYS, ou le littéral s'il a été reformaté "
        "(multi-lignes, concaténation, valeur calculée)."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : la liste ``CONFIG_KEYS`` du JS est encore lue.

    La gate confronte ce que le runtime LIT à ce que l'envelope ÉMET. Si
    la lecture du JS cessait de matcher, elle comparerait un ensemble
    vide — et une clé émise mais jamais lue passerait pour câblée.
    """
    found = _JS_CONFIG_KEYS.search("const CONFIG_KEYS = ['send_to_server', 'debounce_ms']")
    assert found, "la lecture de CONFIG_KEYS ne matche plus"
    assert set(_JS_QUOTED.findall(found.group(1))) == {"send_to_server", "debounce_ms"}
    assert not _JS_CONFIG_KEYS.search("const OTHER = ['x']"), "faux positif"
