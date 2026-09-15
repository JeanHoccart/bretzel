"""``Image`` — afficher une image, avec sa place réservée.

Ce que ce composant apporte au-delà d'une balise ``<img>`` nue, et qui
justifie qu'il existe :

- **``ratio=``** réserve la place AVANT que l'image arrive. Sans lui, la
  page saute au chargement (chaque image pousse le contenu d'en dessous).
  C'est le gain principal, pas un raffinement.
- **``alt=`` obligatoire.** Comme le ``title`` d'``ui.iframe``, et pour
  la même raison : une image décorative se déclare ``alt=""``,
  explicitement. L'oubli d'un ``alt`` est silencieux, invisible au rendu,
  et ne se voit qu'au lecteur d'écran — exactement le mode de défaut que
  ce dépôt gate ailleurs.
- **``fit=``** dit comment l'image remplit le ratio. Sans lui, une image
  dont le ratio naturel diffère serait étirée.

Ce qu'il n'a **pas**, délibérément :

- pas de ``skeleton=`` ni de ``fallback=`` — les deux états sont le fond
  de l'image elle-même, cf. ``theme.py`` ;
- pas de ``width=`` / ``height=`` — ``ratio`` les remplace, et ``attrs=``
  reste pour les dimensions intrinsèques ;
- pas de ``rounded=`` — c'est ``classes=`` ;
- pas de légende : ça demande ``<figure>`` / ``<figcaption>``, donc un
  autre composant, si le besoin remonte.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.image.theme import IMAGE_THEME
from bretzel.core.tree import Element


class Image(Component):
    """Une image, avec sa place réservée par ``ratio=``."""

    THEME: ClassVar[dict[str, Any]] = IMAGE_THEME
    THEME_KEY: ClassVar[str] = "image"
    DEFAULT_TAG: ClassVar[str] = "img"
    IS_CONTAINER: ClassVar[bool] = False

    # ``src`` reste design-time, comme dans ``avatar`` et pour la même
    # raison : une image change quand les données du serveur changent
    # (donc au re-rendu d'un ``@refreshable``), pas sous l'effet d'un
    # driver client. Aucun binding ne se justifie ici — la règle bindable
    # demande un driver côté client, il n'y en a aucun.
    src: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    alt: str = reactive_prop(default="", emit_attr=False)
    ratio: str | None = reactive_prop(default=None, emit_attr=False)
    fit: str = reactive_prop(default="cover", emit_attr=False)

    def __init__(
        self,
        src: str | None = None,
        *,
        alt: str,
        ratio: str | None = None,
        fit: str | None = None,
        **kwargs: Any,
    ) -> None:
        # ``alt`` est keyword-only SANS défaut : l'omettre est une
        # ``TypeError`` à l'appel, pas un rendu silencieusement inaccessible.
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(src=src, alt=alt, ratio=ratio, fit=fit, **kwargs)

    def render(self) -> Element:
        theme = self._resolved_theme()
        values = self._reactive_values

        # ``slot_class`` compose le slot racine et écarte les vides — c'est
        # la route du charter, celle que ``markdown`` / ``code`` prennent
        # déjà. Elle coûte 1,6 µs de plus que la jointure à la main (mesuré,
        # A/B alterné) : 0,05 ms sur une galerie de 30 images, contre trois
        # dialectes différents entre cinq composants frères.
        # ``classes=`` est posé par le wrap métaclasse — pas ici (doublon).
        root_class = self.slot_class(
            "root",
            theme.get("ratios", {}).get(values.get("ratio"), ""),
            theme.get("fits", {}).get(values.get("fit"), ""),
        )

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        # ``src`` OMIS quand il n'y a pas de source, jamais ``src=""``.
        # La spec HTML exige « a valid non-empty URL » ; un attribut vide
        # est résolu contre l'URL du document, donc le navigateur
        # retélécharge LA PAGE COURANTE en croyant charger une image.
        # Trouvé sur ``ui.video`` en lisant les logs du serveur de dev —
        # le défaut était identique ici.
        if values.get("src"):
            attrs["src"] = values["src"]
        # Toujours émis, même vide : un ``<img>`` SANS attribut ``alt`` est
        # annoncé par son URL au lecteur d'écran, alors qu'un ``alt=""``
        # le fait ignorer — ce qui est le comportement voulu pour une
        # image décorative. Les deux ne sont pas équivalents.
        # ``alt`` n'a de sens que sur une image : sur un ``tag=`` autre,
        # il n'annonce rien à personne. Même raison que le ``type`` de
        # ``menu_item`` — posé APRÈS ``emit_attrs``, donc hors du
        # garde-fou central.
        if self._tag in ("img", "area", "input"):
            attrs["alt"] = values.get("alt") or ""
        # ``setdefault`` : ``attrs={"loading": "eager"}`` doit gagner. Le
        # cas réel est l'image d'en-tête, que le lazy retarde au détriment
        # du LCP.
        attrs.setdefault("loading", "lazy")
        attrs.setdefault("decoding", "async")
        return Element(tag=self._tag, attrs=attrs, children=())
