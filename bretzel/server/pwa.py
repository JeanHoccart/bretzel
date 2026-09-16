"""``PWA`` — la déclaration qui rend une app installable.

::

    app = Bretzel(secret_key=…, pwa=PWA(name="Tracker",
                                        icon="/static/logo.png"))

DEUX ÉTAGES, et le premier est celui qu'on écrit
-------------------------------------------------
``icon=`` prend UN chemin et le framework fait le reste. ``icons=``
existe pour les 20 % : du dessin PAR taille — une icône simplifiée à
48 px, détaillée à 512.

⚠️ **La première version de cette API n'avait que l'étage 2**, et
l'utilisateur l'a trouvée « pas naturelle » à la lecture. Il avait
raison, et la faute est identifiable : elle CALQUAIT la spec, qui
demande une liste d'icônes avec leurs tailles. Calquer une spec 1:1
donne une API de spec — on y écrivait ``192`` deux fois (dans le nom du
fichier ET dans l'argument), ``"192x192"`` était une chaîne pour dire un
carré, et ``maskable`` un mot de jargon. Cf. la memory
``two_tier_api_philosophy`` : le défaut magique pour les 80 %,
l'échappatoire pour les 20 %.

Ça monte ``GET /manifest.webmanifest`` et pose son ``<link>`` dans la
tête du document, plus le ``<meta name="theme-color">`` qui colore la
barre système une fois l'app installée.

Ce que ça donne, et ce que ça ne donne PAS
-------------------------------------------
Le manifeste est ce qui décrit l'app au système : son nom, son icône,
sa couleur, et le fait qu'elle s'ouvre en fenêtre PROPRE
(``display: "standalone"``) plutôt que dans un onglet. C'est ce qui
transforme un outil interne en quelque chose qui a une icône dans le
menu Démarrer.

⚠️ **Ça ne rend rien disponible hors ligne**, et il faut le dire net.
Le hors ligne demande un *service worker* — un script qui intercepte
chaque requête et sert un cache. Ce n'est PAS livré ici, délibérément :
un service worker est un cycle de vie à part entière (versions,
invalidation, mise à jour d'une app déjà installée chez l'utilisateur),
et c'est un endroit où l'on casse silencieusement une app en production
en croyant l'améliorer. Le ``cache="shell"`` que la thèse dessinait
attend donc sa propre tranche.

⚠️ **Et il faut VÉRIFIER, pas supposer, si l'invite d'installation
apparaît sans service worker.** Chrome a longtemps exigé les deux
(manifeste + service worker avec un gestionnaire ``fetch``) pour
proposer « Installer ». Cette exigence a bougé au fil des versions, et
ce commentaire n'a pas été mesuré — donc il ne promet rien. Ce qui EST
mesuré : le manifeste est servi, valide, correctement typé et lié.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: Le chemin du manifeste. Racine et pas ``/_bretzel/`` : sa PORTÉE est
#: le dossier qui le contient, et un manifeste servi sous ``/_bretzel/``
#: décrirait une app dont la racine serait ``/_bretzel/``.
MANIFEST_ROUTE = "/manifest.webmanifest"


#: ``sizes="any"`` dit « cette image vaut à toutes les tailles ». C'est
#: exact pour un SVG, et accepté pour un PNG que le système mettra à
#: l'échelle. C'est ce qui permet à l'étage 1 de ne demander QU'UN
#: chemin : sans elle, il faudrait connaître les pixels du fichier, donc
#: le lire — et un chemin peut pointer un CDN.
_TOUTES_TAILLES = "any"


@dataclass(frozen=True, slots=True)
class PWAIcon:
    """Describe one icon in the web application manifest."""

    src: str
    sizes: str | int
    type: str | None = None
    purpose: str | None = None

    def as_dict(self) -> dict[str, str]:
        # Un entier est un CARRÉ. C'est la forme de 99 % des icônes
        # d'app, et l'écrire ``"192x192"`` obligeait à répéter le nombre
        # déjà présent dans le nom du fichier.
        taille = (f"{self.sizes}x{self.sizes}"
                  if isinstance(self.sizes, int) else self.sizes)
        out = {"src": self.src, "sizes": taille}
        if self.type:
            out["type"] = self.type
        elif self.src.lower().endswith(".png"):
            out["type"] = "image/png"
        elif self.src.lower().endswith(".svg"):
            out["type"] = "image/svg+xml"
        if self.purpose:
            out["purpose"] = self.purpose
        return out


@dataclass(frozen=True, slots=True)
class PWA:
    """Declare the metadata that makes an application installable."""

    name: str
    short_name: str | None = None
    description: str | None = None
    #: **L'étage 1** : UN chemin, et le framework fait le reste. Émis en
    #: ``sizes="any"``, ce qui est exact pour un SVG et accepté pour un
    #: PNG que le système met à l'échelle.
    #:
    #: L'alternative aurait été de lire les pixels du fichier pour
    #: déclarer sa taille réelle. Écartée : un chemin peut pointer un
    #: CDN, donc ça ne marcherait qu'une fois sur deux — et une magie
    #: qui marche par intermittence coûte plus cher que pas de magie.
    icon: str | None = None
    #: Autorise le système à ROGNER l'icône dans sa propre forme. ⚠️ À
    #: n'activer que si le dessin a de la marge autour : sinon Android
    #: coupe dedans. Ne s'applique qu'à ``icon=``.
    maskable: bool = False
    #: ``standalone`` est le défaut parce que c'est la raison d'être :
    #: une fenêtre propre, sans barre d'adresse. ``browser`` annulerait
    #: l'intérêt, ``fullscreen`` est pour les bornes.
    display: str = "standalone"
    start_url: str = "/"
    #: La couleur de la barre système une fois installée. ``None`` →
    #: rien n'est émis, et le système choisit.
    theme_color: str | None = None
    background_color: str | None = None
    icons: tuple[PWAIcon, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "PWA(name=…) est vide. C'est le nom que le système "
                "affiche sous l'icône ; sans lui l'app s'installerait "
                "sans être nommable."
            )
        if self.icon and self.icons:
            raise ValueError(
                "PWA : ``icon=`` et ``icons=`` sont donnés tous les deux. "
                "Ce sont les DEUX ÉTAGES de la même chose — ``icon=`` "
                "pour le cas courant (un fichier, toutes les tailles), "
                "``icons=`` quand il faut du dessin par taille. Les "
                "laisser coexister obligerait à inventer une règle de "
                "priorité que personne ne devinerait."
            )
        if not self.start_url.startswith("/"):
            raise ValueError(
                f"PWA(start_url={self.start_url!r}) : un chemin de "
                f"démarrage commence par '/'. Relatif, il se résoudrait "
                f"contre l'emplacement du manifeste et ouvrirait une "
                f"page que personne n'a choisie."
            )

    def as_manifest(self) -> dict[str, Any]:
        """Return the web application manifest as a serializable dictionary."""
        out: dict[str, Any] = {
            "name": self.name,
            "short_name": self.short_name or self.name,
            "display": self.display,
            "start_url": self.start_url,
        }
        if self.description:
            out["description"] = self.description
        if self.theme_color:
            out["theme_color"] = self.theme_color
        if self.background_color:
            out["background_color"] = self.background_color
        if self.icon:
            unique = PWAIcon(
                self.icon,
                _TOUTES_TAILLES,
                purpose="maskable" if self.maskable else None,
            )
            out["icons"] = [unique.as_dict()]
        elif self.icons:
            out["icons"] = [icon.as_dict() for icon in self.icons]
        return out

    def as_json(self) -> str:
        # ``ensure_ascii=False`` : un nom d'app accentué doit arriver
        # tel quel, le manifeste étant servi en UTF-8.
        return json.dumps(self.as_manifest(), ensure_ascii=False)
