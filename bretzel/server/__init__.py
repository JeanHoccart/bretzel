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

#: **What the user writes.** Most of these names are typed from the
#: top level (``from bretzel import Bretzel, abort``); they stay here
#: because this is the layer that defines them.
from bretzel.server.pwa import PWA, PWAIcon

__all__ = [
    "PWA",
    "PWAIcon",
    "Bretzel",
    "BretzelConfig",
    "ConfigError",
    "BretzelError",
    "AuthRequiredError",
    # The feature contract + app-map introspection
    "Feature",
    "FeatureError",
    "describe_app",
    "AppGraph",
    # The helpers callable from a handler
    "abort",
    "push_url",
    "redirect",
    "reload",
    "background",
    "idempotent",
]

#: **Re-exported for the OTHER LAYERS, not for an app author.**
#:
#: Every name here carries the redundant ``X as X`` alias at import: that
#: is the PEP 484 marker of an intentional re-export. The list is checked
#: by ``tests/consistency/test_public_surface_is_classified.py``: nothing
#: enters a facade without being classified on one side or the other.
_INTERNAL = [
    # The request-level primitive behind redirect(): it is a user
    # middleware that calls it, not a page's code. Documented in
    # handlers.md § "middleware auth guard".
    "redirect_response",
    # Same nature: a handler's action path, so a guard can open a login
    # form's submission without recomposing a wire-id by hand.
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
