"""``Video`` — un ``<video>`` habillé, pas un lecteur.

Périmètre tranché au cadrage (2026-08-14) : **les contrôles restent ceux
du navigateur**. Ce composant ne dessine pas de barre de progression, de
volume ni de vitesse — le jour où ça devient un besoin, c'est un AUTRE
composant, pas une prop de plus ici.

Ce qu'il apporte au-delà de la balise nue, et qui justifie qu'il existe
plutôt que de laisser faire ``ui.html`` :

- **``ratio=``** réserve la place. Une vidéo est le pire cas du saut de
  page : le navigateur ne connaît ses dimensions qu'après un aller-retour
  réseau, donc sans ratio tout ce qui suit se décale une seconde après
  l'affichage.
- **``autoplay=True`` force ``muted``.** Tous les navigateurs bloquent la
  lecture automatique avec du son ; sans la garde, la vidéo ne démarre
  simplement pas, sans erreur ni log. C'est LE piège que ce composant
  existe pour absorber.
- **``playsinline`` est toujours émis**, et ce n'est pas une prop. Sans
  lui, iOS sort la vidéo du flux et la passe en plein écran dès la
  lecture — jamais ce qu'on veut dans une application. Un réglage dont la
  bonne valeur est toujours la même n'est pas un choix à exposer.
- **``poster=``** évite le rectangle noir avant lecture.
- **``tracks=``** porte les sous-titres, livré le 2026-08-31 ::

      ui.video(
          "demo.mp4",
          tracks=[ui.track("fr.vtt", srclang="fr", label="Français",
                           default=True)],
      )

  Un ``<track>`` correct veut trois attributs (``src`` + ``srclang`` +
  ``label``) : une prop d'une seule chaîne aurait eu l'air complète sans
  l'être, d'où un descripteur typé qui exige les trois. Le composant
  reste une FEUILLE — les pistes sont des données, pas des enfants. Cf.
  :mod:`bretzel.components.primitives.video.track`.

Ce qu'il n'a **pas**, et pourquoi :

- pas de sources multiples (``<source>`` par format) : un seul ``src``.
  Quand le besoin remonte, il remonte avec sa forme — et ce sera un
  ``sources=`` sur le modèle de ``tracks=``, pas l'ouverture du
  composant aux enfants.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
)
from bretzel.components.primitives.video.theme import VIDEO_THEME
from bretzel.components.primitives.video.track import TRACK_KINDS, Track
from bretzel.core.tree import Element


class Video(Component):
    """Une vidéo, avec sa place réservée et les pièges natifs absorbés."""

    THEME: ClassVar[dict[str, Any]] = VIDEO_THEME
    THEME_KEY: ClassVar[str] = "video"
    DEFAULT_TAG: ClassVar[str] = "video"
    IS_CONTAINER: ClassVar[bool] = False
    #: Le composant parcourt ``tracks=`` lui-même, et l'auteur n'a rien à
    #: y ajouter : une piste est faite d'ATTRIBUTS, elle ne porte aucun
    #: balisage. Ni des enfants ni un rappel de contenu n'auraient de
    #: destinataire — d'où ``"data"`` plutôt que ``"component"``. Cf.
    #: ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "data"

    # Aucune surface bindable, même raison que ``image`` : une source
    # média change quand les données du serveur changent (re-rendu d'un
    # ``@refreshable``), jamais sous un driver client.
    src: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    poster: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    ratio: str | None = reactive_prop(default=None, emit_attr=False)
    fit: str = reactive_prop(default="contain", emit_attr=False)
    controls: bool = reactive_prop(default=True, emit_attr=False)
    autoplay: bool = reactive_prop(default=False, emit_attr=False)
    loop: bool = reactive_prop(default=False, emit_attr=False)
    muted: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        src: str | None = None,
        *,
        poster: str | None = None,
        ratio: str | None = None,
        fit: str | None = None,
        controls: bool | None = None,
        autoplay: bool | None = None,
        loop: bool | None = None,
        muted: bool | None = None,
        tracks: Iterable[Track] = (),
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            src=src, poster=poster, ratio=ratio, fit=fit,
            controls=controls, autoplay=autoplay, loop=loop, muted=muted,
            **kwargs,
        )
        self._tracks = list(tracks)
        self._reject_ambiguous_default()

    def _reject_ambiguous_default(self) -> None:
        """Deux pistes ``default=True`` du même ``kind`` : on lève.

        Le HTML n'en autorise qu'une par ``kind``. Au-delà, le document
        est invalide et le navigateur en garde une **sans dire
        laquelle** : l'auteur croit avoir choisi la piste affichée par
        défaut, et n'a rien choisi. Même raison d'être que
        ``Table._reject_datatable_columns`` — un réglage ignoré en
        silence coûte plus cher qu'un refus.
        """
        for kind in TRACK_KINDS:
            clashing = [t for t in self._tracks if t.kind == kind and t.default]
            if len(clashing) > 1:
                names = ", ".join(t.label for t in clashing)
                raise ComponentUsageError(
                    f"ui.video: {len(clashing)} pistes ``{kind}`` sont "
                    f"marquées default=True ({names}). Le HTML n'en "
                    f"autorise qu'une par kind ; le navigateur en "
                    f"choisirait une sans le dire. Garde default=True sur "
                    f"celle que tu veux voir activée."
                )

    def render(self) -> Element:
        theme = self._resolved_theme()
        values = self._reactive_values

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
        # télécharge LA PAGE COURANTE comme média — une requête inutile
        # par élément, invisible sauf à lire les logs du serveur. C'est
        # exactement comme ça qu'on l'a trouvé.
        if values.get("src"):
            attrs["src"] = values["src"]
        if values.get("poster"):
            attrs["poster"] = values["poster"]

        autoplay = values.get("autoplay")

        if values.get("controls"):
            attrs["controls"] = True
        if autoplay:
            attrs["autoplay"] = True
        # LA garde. Un ``autoplay`` non muet est bloqué par tous les
        # navigateurs : la vidéo ne démarre pas, et rien ne le dit — ni
        # erreur, ni log, ni indice visuel. On force plutôt que d'émettre
        # un attribut inerte.
        if values.get("muted") or autoplay:
            attrs["muted"] = True
        if values.get("loop"):
            attrs["loop"] = True
        # Toujours, jamais une prop : sans lui iOS sort la vidéo du flux
        # et la passe en plein écran dès la lecture. Un réglage dont la
        # bonne valeur est toujours la même n'est pas un choix à exposer.
        attrs["playsinline"] = True
        return Element(tag=self._tag, attrs=attrs, children=self._track_nodes())

    def _track_nodes(self) -> tuple[Element, ...]:
        """Les ``<track>``, dans l'ordre déclaré.

        Le composant reste une feuille : ces enfants-là sont les SIENS,
        pas ceux d'un ``with`` — ``IS_CONTAINER`` garde la porte de
        l'auteur fermée (cf. ``Component.add_child``).

        ``default`` n'est émis que s'il est vrai : la spec HTML en fait
        un booléen, donc ``default="false"`` ACTIVE la piste. C'est le
        piège classique de l'attribut booléen, et il se voit à l'écran
        seulement chez qui n'attendait pas de sous-titres.
        """
        nodes: list[Element] = []
        for t in self._tracks:
            attrs: dict[str, Any] = {
                "kind": t.kind,
                "src": t.src,
                "srclang": t.srclang,
                "label": t.label,
            }
            if t.default:
                attrs["default"] = True
            nodes.append(Element(tag="track", attrs=attrs))
        return tuple(nodes)
