"""``Audio`` — le plus mince de la famille média, et il l'assume.

Contrairement à ses frères, ce composant n'apporte presque rien qu'une
balise ``<audio controls>`` ne fasse déjà :

- pas de ``ratio`` — un lecteur audio a une hauteur FIXE, connue avant le
  chargement, donc il ne provoque aucun saut de page ;
- pas de ``poster``, pas de ``fit`` — il n'y a pas d'image ;
- pas de thème digne de ce nom — la barre est dessinée par le navigateur.

Il existe pour deux raisons, toutes deux honnêtes :

1. **la symétrie de la famille** — quelqu'un qui a trouvé ``ui.video``
   cherchera ``ui.audio``, et l'absence lui coûterait un détour par
   ``ui.html`` pour une balise triviale ;
2. **``controls=True`` par défaut** — un ``<audio>`` sans contrôles est
   invisible ET inaudible. Le défaut de la plateforme (pas de contrôles)
   est un piège pour tout le monde sauf celui qui pilote la lecture en JS.

⚠️ **Pas de ``tracks=``, contrairement à ``ui.video`` — mesuré, pas
supposé.** ``ui.video`` a reçu les sous-titres le 2026-08-31 et la
symétrie de la famille voudrait qu'``ui.audio`` suive. Il ne suit pas,
parce que la piste serait INERTE ici : les contrôles natifs d'un
``<audio>`` n'ont pas de bouton CC. Vérifié dans Chromium le 2026-08-31
en photographiant deux lecteurs côte à côte, l'un avec une piste de
sous-titres et l'autre sans — **les deux captures sont octet pour octet
identiques** (2 637 octets, même empreinte). L'élément charge bien la
piste (``textTracks.length === 1``, mode ``showing``, une cue lue), donc
un lecteur maison en JS pourrait s'en servir ; mais ce composant a
tranché au cadrage qu'il n'en est pas un. Une prop qui n'affiche rien et
qui s'appelle ``tracks=`` promettrait des sous-titres et livrerait un
attribut — exactement la demi-livraison que ce dépôt traque. La sortie
accessible d'un fichier audio reste donc la **transcription posée à
côté, en texte réel**, ce que montre la carte *A11y* de son banc.

⚠️ **Pas de garde ``autoplay`` → ``muted``, contrairement à ``ui.video``,
et ce n'est pas un oubli.** Sur une vidéo, forcer le silence sauve la
lecture automatique : l'image reste, et c'était l'essentiel. Sur du son,
le silence supprime *tout* ce que la lecture apportait — on livrerait un
lecteur qui tourne pour rien. Une lecture audio automatique est de toute
façon bloquée tant que l'utilisateur n'a pas interagi avec la page ;
c'est une politique navigateur qu'aucun attribut ne contourne. On émet
donc ``autoplay`` tel que demandé, et on le dit.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.audio.theme import AUDIO_THEME
from bretzel.core.tree import Element


class Audio(Component):
    """Render a native audio player with visible controls by default."""

    THEME: ClassVar[dict[str, Any]] = AUDIO_THEME
    THEME_KEY: ClassVar[str] = "audio"
    DEFAULT_TAG: ClassVar[str] = "audio"
    IS_CONTAINER: ClassVar[bool] = False

    src: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    controls: bool = reactive_prop(default=True, emit_attr=False)
    autoplay: bool = reactive_prop(default=False, emit_attr=False)
    loop: bool = reactive_prop(default=False, emit_attr=False)
    muted: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        src: str | None = None,
        *,
        controls: bool | None = None,
        autoplay: bool | None = None,
        loop: bool | None = None,
        muted: bool | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            src=src, controls=controls, autoplay=autoplay,
            loop=loop, muted=muted, **kwargs,
        )

    def render(self) -> Element:
        values = self._reactive_values

        # ``classes=`` est posé par le wrap métaclasse — pas ici (doublon).
        root_class = self.slot_class("root")

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        # ``src`` omis plutôt que vide — un ``src=""`` est résolu contre
        # l'URL du document, donc le navigateur retélécharge la page en
        # croyant charger le son. Cf. le fix du 2026-08-14 sur image/video.
        if values.get("src"):
            attrs["src"] = values["src"]
        if values.get("controls"):
            attrs["controls"] = True
        # Pas de garde muted ici : cf. le docstring du module. Forcer le
        # silence sur du son supprimerait tout ce que la lecture apporte.
        if values.get("autoplay"):
            attrs["autoplay"] = True
        if values.get("muted"):
            attrs["muted"] = True
        if values.get("loop"):
            attrs["loop"] = True
        return Element(tag=self._tag, attrs=attrs, children=())
