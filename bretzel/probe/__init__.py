"""Couche 7 — le framework PILOTE sa propre app en marche.

`describe` répond « qu'est-ce qui existe », `check` répond « est-ce que
ce que j'écris est légal ». Ce module répond à la troisième question :
**est-ce que ça marche vraiment**, sur une app qui tourne, dans un vrai
navigateur.

Il est public pour la même raison qu'``introspect`` : il pilote le
runtime INSTALLÉ, donc un paquet séparé mentirait par décalage de
version.

Ce qu'il donne et qu'aucun outil générique ne peut donner
---------------------------------------------------------
Un pilote de navigateur voit l'écran et jamais le serveur ; un
``TestClient`` voit le HTML et jamais le rendu. Ni l'un ni l'autre ne
distingue « le handler n'a rien écrit » de « l'écran ne s'est pas
re-rendu ». Ici les trois se lisent ensemble :

- **plusieurs fenêtres**, qui sont des CONTEXTES et donc des sessions
  distinctes — la mécanique fullstack (``broadcast=``, ``AppState``, un
  dépôt refusé) n'existe qu'à deux sessions ;
- **l'état serveur**, par :meth:`Probe.state` ;
- **le compte de requêtes** d'un geste, qui ne se voit ni dans le DOM ni
  dans les pixels.

Le harnais fournit les AXES, le probe fournit le SCÉNARIO :

.. code-block:: python

    from bretzel.probe import probe
    from examples.kanban.state import Tableau

    with probe("examples.kanban.main:app", windows=2) as p:
        a, b = p.windows
        a.goto("/"); b.goto("/")

        with p.requests() as net:
            a.drag("[data-carte=3]", "[data-colonne=fait]")
        p.settle()

        p.check("l'autre fenêtre a reçu", b.has("[data-colonne=fait] [data-carte=3]"))
        p.check("une écriture = une requête", net.total == 1, net.urls)
        p.check("le serveur est d'accord", p.state(Tableau).colonnes["fait"] == [3])

À la sortie du ``with``, un **balayage gratuit** passe sur chaque
fenêtre — débordement, ordre de tabulation, erreurs JS, requêtes en
échec, une seconde taille, les deux thèmes, les captures — puis rend un
bloc de verdict unique et lève :class:`ProbeFailedError` si une ligne est
rouge.

Installation : ``pip install bretzel[probe]`` (Playwright télécharge un
Chromium ; c'est un extra de développement, jamais une dépendance
d'exécution — « zéro npm » porte sur la prod).
"""

from __future__ import annotations

from bretzel.probe._probe import Net, Probe, ProbeFailedError, ScopeNotReadableError, probe
from bretzel.probe._window import Box, DropMissedError, ElementNotFoundError, Window

#: Les quatre refus du harnais sont PUBLICS, et pour une raison : un
#: probe qui mesure un cas limite veut parfois les attraper — « ce
#: sélecteur ne doit rien désigner », « ce dépôt doit rater ». Les
#: laisser dans un module privé obligeait à écrire
#: ``from bretzel.probe._window import …``, c'est-à-dire à dépendre d'un
#: chemin que rien ne promet. Ajoutées le 2026-09-11, sur décision de
#: l'utilisateur, après que la gate du glisser a dû le faire.
__all__ = [
    "Box",
    "DropMissedError",
    "ElementNotFoundError",
    "Net",
    "Probe",
    "ProbeFailedError",
    "ScopeNotReadableError",
    "Window",
    "probe",
]
