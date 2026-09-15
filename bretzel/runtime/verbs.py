"""Les verbes clients — des actions du NAVIGATEUR, écrites en Python.

::

    ui.button("Copier la clé", on_click=bretzel.copy(state.api_key))
    ui.button("Imprimer",      on_click=bretzel.print_page())
    ui.button("Plein écran",   on_click=bretzel.fullscreen(dashboard))

Pourquoi ça coûte presque rien
-------------------------------
Parce que le slot existe déjà. ``on_<event>=`` est **polymorphe** : un
callable part en POST signé vers le serveur, une **chaîne** est de la
source client évaluée sur place, sans aller-retour. C'est le contrat de
``dialog.open()`` et de ``ClientBinding.set()`` — les verbes n'y ajoutent
rien, ils s'y branchent. Aucune directive neuve, aucun scope, aucune
requête.

Pourquoi ils vivent dans ``runtime/`` et pas dans ``server/``
--------------------------------------------------------------
Les autres symboles exposés sur ``bretzel`` — ``abort``, ``redirect``,
``push_url``, ``reload``, ``background``, ``idempotent`` — vivent tous
dans ``bretzel/server/``, et pour une raison : ils agissent sur le cycle
requête/réponse. ``abort`` lève un statut HTTP, ``redirect`` écrit un
en-tête.

**Un verbe ne touche jamais le serveur.** Le mettre dans ``server/``
ferait mentir le nom du paquet. Sa place est ici parce qu'il est la
moitié Python d'un contrat à DEUX côtés : ``copy`` n'existe que si
``$bz.verbs.copy`` existe, et les deux doivent rester d'accord. C'est
exactement la situation de :mod:`bretzel.runtime.protocol` ↔
``runtime.js``, et le remède est le même — les deux moitiés dans le
même paquet, à portée de regard.

Le DAG le permet sans rien tordre : ``runtime`` est au-dessus de
``state`` (``envelope.py`` importe déjà ``ClientState``), et un verbe n'a
besoin de rien d'autre.

⚠️ Le nom, tranché le 2026-09-01
---------------------------------
La gate ``test_handler_helpers_have_one_home`` pose un critère
**mécanique** : ``ui.*`` s'appelle depuis un corps de rendu, ``bretzel.*``
depuis un handler. Un verbe s'écrit dans un corps de rendu, donc ce
critère seul le placerait sur ``ui``.

**L'utilisateur a tranché pour ``bretzel.*``**, et l'arbitrage se tient :
``ui`` nomme ce qui participe à l'ARBRE — des composants, des
descripteurs (``ui.column``, ``ui.track``), des clés d'itération, une
source réactive qu'une prop consomme (``ui.pending``). Un verbe ne
participe à aucun arbre : il déclenche un effet dans le navigateur, comme
``redirect`` en déclenche un dans la réponse. La ligne devient « ce qui
FAIT quelque chose est sur ``bretzel``, ce qui EST quelque chose est sur
``ui`` », et elle reste vérifiable.

Elle n'est pas parfaite, et le dire vaut mieux que de l'habiller :
``ui.notification`` produit un effet et vit sur ``ui``. Il est
antérieur, il est déjà déclaré en exception dans
``_EXPECTED_UI_FUNCTIONS``, et le déplacer serait une rupture publique
pour une cohérence de vocabulaire — pas un échange qu'on fait sans le
demander.

Ce qui n'est PAS ici, et pourquoi
----------------------------------
- ⚠️ **``share`` et ``vibrate`` étaient reportés ici « à la tranche
  tactile ». Livrés le 2026-09-02 — le report tenait pour l'un et pas
  pour l'autre.** ``navigator.vibrate`` EXISTE partout (mesuré :
  ``function`` sur le Chromium de bureau) et ne fait rien sans matériel,
  donc il n'y avait aucune décision d'absence à prendre : l'argument
  « axe mobile » ne tenait pas. ``navigator.share``, lui, est
  ``undefined`` sur ce même Chromium — le report était donc justifié,
  mais pas pour la raison écrite : l'absence n'est pas un cas limite,
  c'est le cas NORMAL sur la machine où l'on développe.
- **Un retour visuel de copie** — décision utilisateur du 2026-09-01 :
  rien par défaut. Le verbe copie, l'app câble le retour qu'elle veut.
  Un ``ui.copy_button`` qui bascule deux secondes reste la forme
  évidente le jour où le besoin remonte.

Cf. ``.claude/work/these-portee-2026-08-19.md`` § 6.a.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from bretzel.state.scopes.client import ClientBinding

__all__ = ["copy", "fullscreen", "print_page", "share", "vibrate"]


def _as_client_source(value: Any) -> str:
    """``value`` en source JS — un chemin lié, ou un littéral.

    Trois entrées possibles à un call-site, et les trois doivent marcher
    sans que l'appelant ait à savoir laquelle il tient :

    - un :class:`~bretzel.state.scopes.client.ClientBinding` (donc aussi
      une ``ClientExpression``, qui en hérite) → son chemin client, lu à
      l'exécution. C'est ce qui permet de copier une valeur que le
      serveur ne connaît pas ;
    - un champ d'état SERVEUR (``state.api_key``) → au rendu c'est déjà
      la chaîne elle-même, donc elle part en littéral ;
    - n'importe quelle valeur Python → ``json.dumps``, dont la sortie est
      un littéral JS valide pour les scalaires, les listes et les dicts.

    ``binding_path()`` plutôt qu'un ``isinstance`` en escalier : c'est la
    méthode que ``Component.path_of`` appelle pour la même question, et
    elle rend la bonne forme pour les deux sous-classes.
    """
    if isinstance(value, ClientBinding):
        return value.binding_path()
    return json.dumps(value)


def copy(value: Any) -> str:
    """Copier ``value`` dans le presse-papiers, au clic.

    ::

        ui.button("Copier", on_click=bretzel.copy(state.api_key))
        ui.button("Copier", on_click=bretzel.copy("bretzel"))

    ⚠️ **Aucun retour visuel** — c'est le contrat, pas un oubli. Rien
    n'indique à l'utilisateur que le clic a pris ; l'app câble ce qu'elle
    veut avec ce qui existe.

    ⚠️ Le repli hors contexte sécurisé est dans ``22_verbs.js``, et il
    n'est pas décoratif : sur ``http://`` + une IP de réseau local — la
    façon dont un outil interne se sert — ``navigator.clipboard`` vaut
    ``undefined``.
    """
    return f"$bz.verbs.copy({_as_client_source(value)})"


def print_page() -> str:
    """Ouvrir la boîte d'impression du navigateur, au clic.

    ::

        ui.button("Imprimer", on_click=bretzel.print_page())

    ⚠️ **``print_page`` et pas ``print``.** La thèse l'avait dessiné
    ``bretzel.print()``, ce qui se lit mieux — mais définir un
    ``print`` au niveau module masque la fonction intégrée à l'intérieur
    du paquet, et le masque une seconde fois chez qui écrirait
    ``from bretzel import print``. Le nom dit en plus CE QUI est
    imprimé : ``window.print()`` imprime le document, pas un élément.
    """
    return "window.print()"


def fullscreen(target: Any = None) -> str:
    """Passer en plein écran, au clic.

    ::

        ui.button("Plein écran", on_click=bretzel.fullscreen())          # la page
        ui.button("Plein écran", on_click=bretzel.fullscreen(dashboard)) # un composant

    ``target`` est un composant — n'importe quel objet portant un ``id``,
    ce qui est la même convention que l'API impérative
    (``document.getElementById(self.id)`` dans ``Component``). Sans
    ``target``, c'est le document entier.

    ⚠️ **Le plein écran exige un geste de l'utilisateur** : appelé hors
    d'un gestionnaire d'événement, le navigateur refuse. Un verbe étant
    toujours branché sur un ``on_*=``, la condition est tenue par
    construction — mais elle explique pourquoi ceci ne peut pas exister
    en version « serveur ».
    """
    if target is None:
        node = "document.documentElement"
    else:
        node_id = getattr(target, "id", None)
        if not node_id:
            raise ValueError(
                "bretzel.fullscreen(target=…) : la cible n'a pas d'``id`` "
                "rendu, donc le client ne peut pas la retrouver. Passe un "
                "composant construit — ``ui.container(id='dashboard')`` — "
                "ou rien du tout pour viser la page entière."
            )
        node = f"document.getElementById({json.dumps(str(node_id))})"
    # ``?.`` : un navigateur sans plein écran ne doit pas lever dans un
    # ``on_click``, où personne n'attrape. Et le ``catch`` couvre le refus
    # — l'utilisateur peut dire non, ce n'est pas une erreur de l'app.
    return (
        f"({node}.requestFullscreen && "
        f"{node}.requestFullscreen().catch(() => {{}}))"
    )


def share(
    url: Any = None, *, title: Any = None, text: Any = None
) -> str:
    """Ouvrir la feuille de partage native — ou copier l'URL, à défaut.

    ::

        ui.button("Partager", on_click=bretzel.share())
        ui.button("Partager", on_click=bretzel.share(title="Rapport Q3"))

    **Sans ``url``, c'est la page COURANTE qui part**, et ce défaut n'est
    pas de la commodité : depuis que l'état s'écrit dans l'adresse
    (``addressable=True`` + ``field(url=…)``, livrés fin août), l'URL
    courante PORTE la vue — les filtres, l'onglet, la page. Partager la
    page, c'est donc partager ce qu'on regarde, ce qui est très
    exactement la demande d'un outil interne.

    ⚠️ **Le repli n'est pas un accident, c'est le contrat.**
    ``navigator.share`` est ``undefined`` sur le Chromium de bureau
    (mesuré le 2026-09-02), donc l'absence est le cas NORMAL là où l'on
    développe. Un bouton « Partager » inerte pour la majorité serait
    exactement ce que ce dépôt refuse ailleurs — cf. le refus de
    ``tracks=`` sur ``ui.audio``, qui aurait promis des sous-titres et
    livré un attribut. Le repli **copie l'URL**.

    ⚠️ En revanche un partage ANNULÉ par l'utilisateur ne retombe pas
    sur la copie : fermer la feuille copierait alors dans son dos.
    """
    charge: dict[str, Any] = {}
    for cle, valeur in (("url", url), ("title", title), ("text", text)):
        if valeur is not None:
            charge[cle] = _as_client_source(valeur)
    corps = ", ".join(f"{c}: {v}" for c, v in charge.items())
    return f"$bz.verbs.share({{{corps}}})"


def vibrate(pattern: int | Sequence[int] = 50) -> str:
    """Faire vibrer l'appareil, au clic.

    ::

        ui.button("Scanner", on_click=vibrate())          # 50 ms
        ui.button("Erreur",  on_click=vibrate([50, 30, 50]))

    Un entier vibre une fois ; une liste alterne vibration et pause, en
    millisecondes.

    ⚠️ **Aucune absence à gérer**, contrairement à :func:`share` :
    ``navigator.vibrate`` existe partout (mesuré : ``function`` sur le
    Chromium de bureau) et ne fait simplement RIEN sans matériel. C'est
    ce qui rend ce verbe gratuit — et ce qui rendait faux l'argument
    « axe mobile » qui l'a d'abord fait reporter.
    """
    return f"$bz.verbs.vibrate({json.dumps(list(pattern) if not isinstance(pattern, int) else pattern)})"
