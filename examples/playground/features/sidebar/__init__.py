"""Feature Sidebar — l'API publique du banc.

N'exporte que ce dont ``app/routes.py`` a besoin. L'état, les
handlers et les panneaux restent privés au paquet.
"""

from examples.playground.features.sidebar.state import PATH
from examples.playground.features.sidebar.ui import page

__all__ = ["PATH", "page"]
