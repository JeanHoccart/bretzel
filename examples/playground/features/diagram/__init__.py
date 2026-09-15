"""Feature Diagram — l'API publique du banc.

N'exporte que ce dont ``app/routes.py`` a besoin. L'état, les
handlers et les panneaux restent privés au paquet.
"""

from examples.playground.features.diagram.ui import page

PATH = "/diagram"

__all__ = ["PATH", "page"]
