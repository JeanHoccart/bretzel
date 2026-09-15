"""Default :class:`Html` theme — délibérément presque vide.

Un seul slot, et il ne porte **aucune** classe visuelle. C'est le point :
``ui.html`` injecte du balisage que le framework n'a pas produit, donc il
n'a pas à lui imposer une typographie, un espacement ou une couleur. Le
contraste avec ``ui.markdown`` est volontaire — celui-là POSSÈDE le HTML
qu'il émet (c'est lui qui l'a fabriqué depuis la source markdown), donc
il a le droit et le devoir de le styler.

``bz-html`` est une classe **marqueur**, pas une classe de style : elle
donne une prise CSS à l'app et un sélecteur stable aux sondes d'audit.
"""

from __future__ import annotations

from typing import Any

HTML_THEME: dict[str, Any] = {
    "slots": {
        "root": "bz-html",
    },
}
