"""``Iframe`` — un document tiers, borné par défaut.

Ce que le composant apporte au-delà de la balise nue :

- **``title=`` obligatoire.** Un lecteur d'écran annonce les cadres d'une
  page par leur titre ; sans lui, l'utilisateur entend « cadre », sans
  savoir s'il contient une carte, une vidéo ou un formulaire de paiement.
  C'est le pendant exact de l'``alt`` d'``ui.image``, et il est requis
  pour la même raison : l'oubli est invisible à l'écran.
- **``ratio=``** réserve la hauteur. Un embed est la première cause de
  saut de page, et un ``<iframe>`` sans dimensions retombe sur un
  300×150 hérité des années 90.
- **``loading="lazy"``** par défaut : un embed hors écran ne charge pas.
- **``sandbox=``, avec une valeur par défaut non vide** — cf. ci-dessous.

Le sandbox par défaut
---------------------

``SANDBOX_BASELINE`` = ``allow-scripts allow-same-origin allow-forms
allow-popups``. Le point n'est pas ce que la liste autorise, c'est ce
qu'elle **n'autorise pas** : dès qu'un attribut ``sandbox`` est présent,
``allow-top-navigation`` et ``allow-downloads`` sont refusés tant qu'on
ne les demande pas. Autrement dit le document embarqué ne peut plus
**changer la page sous vos pieds** ni **déclencher un téléchargement** —
les deux vecteurs qui transforment un embed en hameçonnage.

Les quatre permissions accordées sont celles sans lesquelles les embeds
courants (carte, lecteur, widget de paiement) ne fonctionnent pas du
tout. Un défaut que tout le monde désactive au premier essai
n'apprendrait qu'une chose : à le désactiver.

⚠️ ``allow-scripts`` + ``allow-same-origin`` ensemble, sur un document de
**votre propre origine**, permettent à ce document de retirer son propre
attribut ``sandbox``. C'est sans effet sur un embed tiers (origine
différente), qui est le cas d'usage. Pour encadrer une page à vous en
vous en protégeant vraiment, passez une liste sans ``allow-same-origin``.

Trois façons de sortir, toutes explicites :

- ``sandbox="allow-scripts"`` — votre propre liste, à la place de la base.
- ``sandbox=""`` — sandbox maximal (tout refusé). Utile pour du HTML
  statique de confiance douteuse.
- ``sandbox=None`` — **aucun** attribut, donc aucune restriction. C'est le
  comportement du web nu ; il faut l'écrire pour l'obtenir.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.iframe.theme import IFRAME_THEME
from bretzel.core.tree import Element

#: Bloque top-navigation et downloads, laisse marcher les embeds usuels.
#: Cf. le docstring du module pour le raisonnement complet.
SANDBOX_BASELINE: Final[str] = (
    "allow-scripts allow-same-origin allow-forms allow-popups"
)




class Iframe(Component):
    """Un document embarqué, avec un titre et un sandbox par défaut."""

    THEME: ClassVar[dict[str, Any]] = IFRAME_THEME
    THEME_KEY: ClassVar[str] = "iframe"
    DEFAULT_TAG: ClassVar[str] = "iframe"
    IS_CONTAINER: ClassVar[bool] = False

    # Aucune surface bindable : une URL d'embed change au re-rendu
    # serveur. Et laisser un driver client réécrire le ``src`` d'un cadre
    # sandboxé serait un moyen commode de pointer ailleurs.
    src: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    title: str = reactive_prop(default="", emit_attr=False)
    ratio: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        src: str | None = None,
        *,
        title: str,
        ratio: str | None = None,
        sandbox: str | None = SANDBOX_BASELINE,
        **kwargs: Any,
    ) -> None:
        # ``title`` keyword-only SANS défaut : l'omettre est une TypeError
        # à l'appel, pas un cadre anonyme au lecteur d'écran.
        #
        # ``sandbox`` n'est PAS une ``reactive_prop`` : le socle drope les
        # kwargs reactive ``None``, or ici ``None`` est une VALEUR — « retire
        # l'attribut ». Le défaut vit donc dans la signature, où il est aussi
        # lisible dans ``help()`` et les info-bulles d'éditeur.
        self._sandbox = sandbox
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(src=src, title=title, ratio=ratio, **kwargs)

    def render(self) -> Element:
        theme = self._resolved_theme()
        values = self._reactive_values

        # ``classes=`` est posé par le wrap métaclasse — pas ici (doublon).
        root_class = self.slot_class(
            "root", theme.get("ratios", {}).get(values.get("ratio"), "")
        )

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        # ``src`` omis plutôt que vide : un ``src=""`` est résolu contre
        # l'URL du document, donc le cadre chargerait LA PAGE COURANTE
        # dans lui-même. Trouvé sur ``ui.video`` en lisant les logs du
        # serveur, et ici la conséquence serait pire — une page qui se
        # contient elle-même, récursivement.
        if values.get("src"):
            attrs["src"] = values["src"]
        attrs["title"] = values.get("title") or ""

        # Une seule branche pour les trois états : rien passé → la base
        # (défaut de signature), une liste → la liste, ``""`` → émis tel
        # quel car ``"" is not None`` (sandbox MAXIMAL, significatif),
        # ``None`` → aucun attribut, aucune restriction.
        if self._sandbox is not None:
            attrs["sandbox"] = self._sandbox

        attrs.setdefault("loading", "lazy")
        return Element(tag=self._tag, attrs=attrs, children=())
