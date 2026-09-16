"""HTTP, authentication, routing, and application lifecycle services."""

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
