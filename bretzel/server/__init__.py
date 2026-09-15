"""Layer 6 — the HTTP boundary.

Public surface :

- :class:`Bretzel` — the user-facing app class. Construct it, decorate
  your pages, hand the instance to uvicorn / gunicorn.
- :class:`BretzelConfig` — exposed for advanced introspection.
- :class:`BretzelError`, :class:`AuthRequiredError`, :func:`abort` —
  les types d'erreur et le court-circuit de handler.
- :func:`push_url` — renommer l'adresse affichée SANS naviguer :
  c'est ce qui donne une adresse à une vue (tri, filtre, onglet),
  donc un bouton retour qui marche et un lien qu'on peut partager.
  Le socle l'appelle seul quand un champ ``URL = {…}`` a bougé.
- :func:`redirect` — envoyer le navigateur ailleurs depuis un handler.
  Sa primitive niveau-requête, :func:`redirect_response`, est ce qu'un
  middleware utilisateur appelle : lui n'a pas de contexte de rendu. Cf.
  :mod:`bretzel.server.navigation`.
- :func:`background`, :func:`idempotent` — les deux décorateurs de
  handler.
- ``auth.source`` / ``auth.door`` — les deux moitiés de l'identité.
  Des décorateurs **libres**, comme :func:`page` : une feature ne doit
  pas importer l'instance d'app pour déclarer d'où vient une identité
  (``app-structure.md`` § 9). Ils vivent dans le namespace ``auth`` et
  non ici : ce sont des DÉCLARATIONS, et les mettre au même rang que les
  verbes impératifs faisait lire ``login_with`` comme une variante de
  ``auth.login``.
- The ``auth`` namespace re-exposed as a module attribute for the
  documented ``from bretzel import auth`` convenience, et ``oauth`` pour
  les deux portes (:class:`OIDC`, :class:`OAuth2`).
"""

from __future__ import annotations

from bretzel.server.app import Bretzel
from bretzel.server.config import BretzelConfig, ConfigError
from bretzel.server.decorators.background import background
from bretzel.server.errors import (
    AuthRequiredError,
    BretzelError,
    abort,
)
from bretzel.server.errors import (
    default_error_page as default_error_page,
)
from bretzel.server.feature import (
    FEATURE_KINDS as FEATURE_KINDS,
)
from bretzel.server.feature import (
    AppGraph,
    Feature,
    FeatureError,
    describe_app,
)
from bretzel.server.feature import (
    DriftReport as DriftReport,
)
from bretzel.server.feature import (
    FeatureNode as FeatureNode,
)
from bretzel.server.feature import (
    ProvideInfo as ProvideInfo,
)
from bretzel.server.feature import (
    dependency_drift as dependency_drift,
)
from bretzel.server.feature import (
    undeclared_provides as undeclared_provides,
)
from bretzel.server.feature import (
    validate_features as validate_features,
)
from bretzel.server.handlers import action_path as action_path
from bretzel.server.idempotency import idempotent
from bretzel.server.navigation import push_url, redirect
from bretzel.server.navigation import (
    redirect_response as redirect_response,
)
from bretzel.server.navigation import (
    reload as reload,
)
from bretzel.server.navigation import (
    response_is_read_by_htmx as response_is_read_by_htmx,
)

#: **Ce que l'utilisateur écrit.** La plupart de ces noms se tapent depuis
#: le top-level (``from bretzel import Bretzel, abort``) ; ils restent ici
#: parce que c'est la couche qui les définit.
from bretzel.server.pwa import PWA, PWAIcon

__all__ = [
    "PWA",
    "PWAIcon",
    "Bretzel",
    "BretzelConfig",
    "ConfigError",
    "BretzelError",
    "AuthRequiredError",
    # Le contrat de feature + l'introspection de la carte d'app
    "Feature",
    "FeatureError",
    "describe_app",
    "AppGraph",
    # Les helpers appelables depuis un handler
    "abort",
    "push_url",
    "redirect",
    "reload",
    "background",
    "idempotent",
]

#: **Ré-exporté pour les AUTRES COUCHES, pas pour l'auteur d'une app.**
#:
#: Chaque nom d'ici porte l'alias redondant ``X as X`` à l'import : c'est le
#: marqueur PEP 484 du ré-export intentionnel. La liste est vérifiée par
#: ``tests/consistency/test_public_surface_is_classified.py`` : rien n'entre
#: dans une façade sans être classé d'un côté ou de l'autre.
_INTERNAL = [
    # La primitive niveau-requête de redirect() : c'est un middleware
    # utilisateur qui l'appelle, pas le code d'une page. Documentée dans
    # handlers.md § « garde d'auth par middleware ».
    "redirect_response",
    # Même nature : le chemin d'action d'un handler, pour qu'une garde
    # puisse ouvrir la soumission d'un formulaire de connexion sans
    # recomposer un wire-id à la main.
    "action_path",
    "response_is_read_by_htmx",
    "FEATURE_KINDS",
    "validate_features",
    "FeatureNode",
    "ProvideInfo",
    "DriftReport",
    "dependency_drift",
    "undeclared_provides",
    "default_error_page",
]
