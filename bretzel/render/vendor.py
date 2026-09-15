"""Les trois scripts tiers, servis depuis chez toi plutôt que depuis un CDN.

Ce que ça règle
---------------

Une page Bretzel charge trois scripts qui ne viennent pas de nous : htmx,
l'extension idiomorph, et le composant web iconify. Mesuré le 2026-08-27
sur une app en mode ``prod``, cache froid, page minimale :

===============================  ==========
ressource                          durée
===============================  ==========
``unpkg.com/htmx``                  593 ms
``unpkg.com/idiomorph-ext``         592 ms
``code.iconify.design/iconify``     489 ms
``/_bretzel/runtime.js`` (local)     41 ms
``/_bretzel/style.css`` (local)      21 ms
===============================  ==========

Le ``DOMContentLoaded`` de cette page tombe à **644 ms** : il est
intégralement tenu par les trois premières lignes. Les deux ressources
servies par l'app, elles, arrivent en 20-40 ms — même connexion, déjà
ouverte, déjà chiffrée. Trois origines tierces, c'est trois résolutions
DNS, trois poignées de main TLS et trois disponibilités qui ne dépendent
pas de nous.

Le patron est celui du binaire Tailwind
----------------------------------------

Rien de tiers n'entre dans le dépôt. Les fichiers sont **téléchargés à la
demande** dans ``./.bretzel/vendor/``, exactement comme
:func:`bretzel.theme.build.download_binary` met le compilateur Tailwind
dans ``./.bretzel/bin/``. Le dossier est un cache de projet, pas une
source — il n'a pas à être committé.

Conséquence : le repli est la règle, pas l'exception. Tant que le
téléchargement n'a pas eu lieu, le shell pointe sur le CDN et tout marche
comme avant. C'est un choix, pas un accident : une app qui n'a jamais
lancé la commande ne doit pas cesser de démarrer.

    python -m bretzel.render.vendor

⚠️ **En DEV, l'app le fait d'elle-même depuis le 2026-09-13**
(:func:`ensure_vendored`, appelée au premier appel ASGI). La commande
n'était connue que de qui l'avait lue, donc le repli CDN était la règle
pour presque tout le monde — et une suite de 84 probes, qui tourne en
dev, en dépendait sans le savoir. En production rien ne change : sortir
du réseau au démarrage d'un serveur est une décision d'exploitant, et la
commande reste le chemin explicite.

L'empreinte est vérifiée
-------------------------

Chaque fichier porte son SHA-256 attendu. Un octet qui ne correspond pas
et le téléchargement est refusé, le fichier effacé : servir depuis notre
propre origine un script qu'on n'a pas vérifié serait strictement pire
que de laisser le CDN le servir, puisqu'on lui prêterait notre nom.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path
from typing import Final, NamedTuple

from bretzel.runtime.protocol import ROUTE_ICONS, ROUTE_VENDOR

#: Ré-exporté : le chemin est un mot du protocole, il vit donc dans
#: ``protocol.py`` avec les autres routes — c'est aussi ce qui permet à
#: ``PUBLIC_ASSET_ROUTES`` de le classer sans remonter la pile.
__all__ = (
    "ROUTE_ICONS",
    "ensure_vendored",
    "ROUTE_VENDOR",
    "VendoredAsset",
    "download",
    "download_all",
    "route_for",
    "url_for",
    "vendor_dir",
    "vendored_assets",
    "vendored_is_available",
    "vendored_local_path",
)


class VendoredAsset(NamedTuple):
    """Un script tiers : son nom de fichier, sa source, son empreinte."""

    filename: str
    url: str
    sha256: str


def vendor_dir() -> Path:
    """``./.bretzel/vendor/`` — le cache de projet, à côté du cwd.

    Même racine que le binaire Tailwind, pour la même raison : un cache
    par projet, jamais partagé entre deux checkouts, jamais committé.
    """
    return Path.cwd() / ".bretzel" / "vendor"


def cached_name(asset: VendoredAsset) -> str:
    """Le nom du fichier en cache — il PORTE l'empreinte attendue.

    ``htmx.min.js`` devient ``htmx.min.e209dda5.js``.

    **Le nom est la clé, et c'est le seul moyen de ne pas mentir.** Un
    cache sur disque survit au processus : rien ne l'invalidera jamais
    tout seul. Tant que le fichier s'appelait ``htmx.min.js``, il
    suffisait de monter la version dans :mod:`bretzel.render.shell` pour
    que chaque checkout existant continue de servir l'ANCIENNE, sans
    bruit — l'ancien ``download()`` rendait la main sur un simple
    ``is_file()``, et ``vendored_is_available`` ne regardait pas non plus.

    Mesuré le 2026-08-27 : ``htmx.min.js`` remplacé par 38 octets de
    n'importe quoi, ``vendored_is_available`` répondait ``True``,
    ``url_for`` servait le fichier, et ``download()`` refusait de le
    remplacer.

    Avec l'empreinte dans le nom, exister C'EST être bon : une version
    montée ne trouve simplement plus son fichier et l'app retombe sur le
    CDN — visiblement, jusqu'au prochain téléchargement. C'est la même
    règle que ``.bretzel/css/<empreinte>.css`` et que le binaire
    Tailwind, dont le nom porte la version.
    """
    tige, _, extension = asset.filename.rpartition(".")
    return f"{tige}.{asset.sha256[:8]}.{extension}"


def vendored_local_path(asset: VendoredAsset) -> Path:
    """Où ``asset`` se trouve dans le cache du projet — présent ou non."""
    return vendor_dir() / cached_name(asset)


def vendored_is_available(asset: VendoredAsset) -> bool:
    """Le fichier est-il là ? Un simple ``stat``, pas de relecture.

    Suffisant parce que le nom porte l'empreinte : un fichier présent
    sous ce nom-là a été vérifié à l'écriture (cf. :func:`download`).
    """
    return vendored_local_path(asset).is_file()


def route_for(asset: VendoredAsset) -> str:
    return f"{ROUTE_VENDOR}/{cached_name(asset)}"


def url_for(asset: VendoredAsset) -> str:
    """L'URL à mettre dans le ``<script>`` : locale si présente, CDN sinon.

    Le choix est fait au RENDU et pas au démarrage, à un ``stat`` près :
    lancer la commande de téléchargement pendant qu'un serveur de dev
    tourne doit suffire à basculer au rechargement suivant, sans
    redémarrage. En prod le fichier est là ou il n'y est pas — le
    ``stat`` porte alors sur une entrée que le système garde en cache.
    """
    return route_for(asset) if vendored_is_available(asset) else asset.url


def download(asset: VendoredAsset, *, force: bool = False) -> Path:
    """Télécharge ``asset`` dans le cache, empreinte vérifiée.

    Le fichier n'est écrit à sa place définitive qu'APRÈS vérification :
    un téléchargement interrompu ne doit pas laisser derrière lui un
    fichier tronqué que :func:`vendored_is_available` déclarerait bon, et que
    l'app servirait ensuite à la place du CDN.
    """
    target = vendored_local_path(asset)
    if target.is_file() and not force:
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"[bretzel] Téléchargement de {asset.filename} depuis {asset.url}")
    # ``User-Agent`` explicite : ``code.iconify.design`` répond **403** à
    # l'en-tête par défaut d'``urllib`` (mesuré le 2026-08-27). unpkg s'en
    # moque ; le poser pour les trois évite d'avoir deux chemins.
    request = urllib.request.Request(
        asset.url, headers={"User-Agent": "bretzel-vendor/1.0"}
    )
    with urllib.request.urlopen(request) as response:  # URL en dur
        payload = response.read()

    digest = hashlib.sha256(payload).hexdigest()
    if digest != asset.sha256:
        raise RuntimeError(
            f"{asset.filename} : empreinte inattendue.\n"
            f"  attendue : {asset.sha256}\n"
            f"  obtenue  : {digest}\n"
            "Le fichier n'a PAS été installé. Si la version amont a bougé, "
            "mettre à jour l'empreinte dans bretzel/render/vendor.py — "
            "jamais l'inverse."
        )

    target.write_bytes(payload)
    print(f"[bretzel] {asset.filename} -> {target} ({len(payload):,} octets)")
    return target


def download_all(*, force: bool = False) -> list[Path]:
    """Tout ce qui est rapatriable, dans le cache du projet."""
    return [download(asset, force=force) for asset in downloadable_assets()]


def browser_css_asset() -> VendoredAsset:
    """Le compilateur Tailwind navigateur — le QUATRIÈME tiers.

    Il vit à part de :func:`vendored_assets` parce qu'il ne se charge pas
    sur toutes les pages : seulement quand le pipeline CSS est
    ``browser``, c'est-à-dire en dev. Le mettre dans la liste commune le
    ferait émettre en prod, où la feuille est déjà compilée.

    ⚠️ **C'est le plus lourd des quatre — 276 Ko — et c'était le seul qui
    n'était ni vérifiable ni rapatriable**, parce que son URL était un
    INTERVALLE (``@4``). Conséquence mesurée le 2026-09-13 : chaque page
    de dev faisait deux allers-retours chez unpkg (un 302, puis le
    bundle), et quand ce tiers bronchait, *aucune* feuille n'était
    produite — l'encre d'un bouton passait de ``oklab(…)`` à ``rgb(0, 0,
    0)``. Une suite entière de probes tourne en dev : sa fiabilité tenait
    à un site tiers, et sa rouge se déplaçait d'un probe à l'autre sans
    jamais parler du code.
    """
    from bretzel.render.shell import (  # casse un cycle : shell → vendor
        DEFAULT_TAILWIND_BROWSER_URL,
    )

    return VendoredAsset(
        "tailwind-browser.js",
        DEFAULT_TAILWIND_BROWSER_URL,
        "a60c785630a06196808cbe79e6f7bdb4abcc8f4421a47b56f29338fc84805e3b",
    )


def downloadable_assets() -> tuple[VendoredAsset, ...]:
    """Tout ce qui peut être rapatrié — les trois communs plus le CSS.

    C'est ce que ``python -m bretzel.render.vendor`` télécharge et ce que
    la route statique sait servir. :func:`vendored_assets`, elle, ne
    répond qu'à « que charge CHAQUE page ».
    """
    return (*vendored_assets(), browser_css_asset())


def ensure_vendored() -> bool:
    """Rapatrier ce qui manque. Idempotent, et **jamais fatal**.

    Appelée au premier appel ASGI d'une app en mode dev
    (``Bretzel.__call__``), donc une fois par processus : les fichiers
    déjà là ne sont pas retéléchargés, et une app qui a tourné une fois
    ne parle plus à personne.

    Pourquoi automatiquement, et pourquoi en dev seulement
    ------------------------------------------------------
    Le rapatriement était une COMMANDE à lancer à la main
    (``python -m bretzel.render.vendor``), donc le repli CDN était la
    règle pour tout le monde — y compris pour qui ne savait pas que la
    commande existe. Une page de dev demandait alors quatre scripts à
    deux CDN, plus ses glyphes à trois hôtes Iconify.

    En dev on est sur une machine de développement : le réseau est là, le
    téléchargement se paie une fois, et la page y gagne à chaque
    rechargement de la boucle de travail. En **prod** on ne décide rien
    d'office — un serveur qui sort du réseau au démarrage est une
    surprise, et la commande reste le chemin explicite.

    ⚠️ **Un échec n'arrête rien.** Sans réseau, derrière un proxy, ou si
    une empreinte ne correspond pas, on le DIT et on continue : le repli
    CDN est exactement le comportement d'avant. Une app ne doit pas
    cesser de démarrer parce qu'un cache de confort manque.

    Rend ``True`` si les quatre sont locaux à la sortie.
    """
    manquants = [a for a in downloadable_assets() if not vendored_is_available(a)]
    for asset in manquants:
        try:
            download(asset)
        except Exception as exc:  # réseau, HTTP, empreinte — jamais fatal
            print(
                f"[bretzel] {asset.filename} non rapatrié ({exc}) — la page "
                f"le demandera à {asset.url}"
            )
    return all(vendored_is_available(a) for a in downloadable_assets())


def vendored_assets() -> tuple[VendoredAsset, ...]:
    """Les trois scripts que CHAQUE page charge, dans leur ordre.

    Les URL viennent de :mod:`bretzel.render.shell`, seule source de
    vérité pour les versions — l'import est **différé** parce que
    ``shell`` importe ce module en retour pour choisir ses ``<script>``.
    Un import au chargement ferait un cycle.

    Les empreintes ont été relevées le 2026-08-27 sur les octets servis
    par les deux origines. Elles se mettent à jour **avec** un
    changement de version, jamais parce qu'un téléchargement a échoué à
    les vérifier.
    """
    from bretzel.render.shell import (  # casse un cycle : shell → vendor
        DEFAULT_HTMX_URL,
        DEFAULT_ICONIFY_URL,
        DEFAULT_IDIOMORPH_URL,
    )

    return (
        VendoredAsset(
            "htmx.min.js",
            DEFAULT_HTMX_URL,
            "e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447",
        ),
        VendoredAsset(
            "idiomorph-ext.min.js",
            DEFAULT_IDIOMORPH_URL,
            "1589f425608653a841fa06ef2bb103a59e19f1e6d27064cff894d365efd6d948",
        ),
        VendoredAsset(
            "iconify-icon.min.js",
            DEFAULT_ICONIFY_URL,
            "758d94838db0cafdeb97eb0b54a120de36cfb3c7fe862eed989f37e80c550f02",
        ),
    )


if __name__ == "__main__":  # pragma: no cover — point d'entrée manuel
    download_all()


# ───────────────────────────────────────────────────────────────────────────
# Les DONNÉES d'icône — relayées par le serveur et mises en cache
# ───────────────────────────────────────────────────────────────────────────
#
# Rapatrier ``iconify-icon.min.js`` ne rapatrie que le composant. La coque
# configure le composant pour appeler ``/_bretzel/icons`` ; cette route lit
# d'abord le cache local, puis interroge les API Iconify depuis le serveur.
# Le navigateur du visiteur ne contacte donc aucun de ces hôtes.
#
# La géométrie, elle, ne bouge pas — une icône absente garde sa boîte, que
# le CSS dimensionne en ``1em``. C'est pourquoi ce tiers-ci ne fabriquait
# pas les rouges mouvantes de ``-m probes`` (c'était le compilateur CSS),
# et pourquoi il se voit seulement sur une capture. Il reste une
# dépendance réseau lors du premier accès à un glyphe absent du cache.

ICON_CACHE_DIRNAME = "icons"

#: L'amont, et ses deux secours — l'ordre est celui d'Iconify.
ICON_API_HOSTS: Final[tuple[str, ...]] = (
    "https://api.iconify.design",
    "https://api.simplesvg.com",
    "https://api.unisvg.com",
)


def icon_cache_dir() -> Path:
    """``./.bretzel/vendor/icons/`` — créé à la demande."""
    d = vendor_dir() / ICON_CACHE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _icon_cache_file(chemin: str) -> Path:
    """Le fichier de cache d'une requête, nommé par son EMPREINTE.

    Le chemin d'une requête Iconify porte une liste d'icônes en query
    (``lucide.json?icons=check,x``), donc il contient des caractères
    qu'un nom de fichier n'accepte pas, et il peut dépasser la longueur
    maximale d'un chemin Windows. Une empreinte règle les deux.
    """
    empreinte = hashlib.sha256(chemin.encode("utf-8")).hexdigest()[:32]
    return icon_cache_dir() / f"{empreinte}.json"


def icon_payload(chemin: str, *, allow_download: bool = True) -> bytes | None:
    """Le corps d'une réponse de l'API Iconify — du cache, ou d'amont.

    ``chemin`` est la partie qui suit l'hôte, query comprise
    (``/lucide.json?icons=check``). Rendu tel quel : on ne modélise pas
    le protocole d'Iconify, on le RELAIE. Modéliser aurait demandé de
    suivre chacun de ses points d'accès (les collections, la date de
    dernière modification, la recherche) et de repayer la dette à chaque
    évolution amont.

    Une fois en cache, plus rien ne sort de la machine. ``None`` si le
    cache est vide et qu'aucun hôte ne répond — l'appelant rend alors un
    404 et le composant retombera sur ses propres hôtes, ce qui est le
    comportement d'avant : **ne jamais faire moins bien que ne rien
    faire**.
    """
    fichier = _icon_cache_file(chemin)
    if fichier.is_file():
        return fichier.read_bytes()
    if not allow_download:
        return None
    for hote in ICON_API_HOSTS:
        requete = urllib.request.Request(
            hote + chemin,
            # ⚠️ Un ``User-Agent`` explicite, et ce n'est pas cosmétique :
            # sans lui, l'API rend **403** (mesuré le 2026-09-13), et le
            # diagnostic arrive sous la forme d'icônes absentes.
            headers={"User-Agent": "bretzel/vendor"},
        )
        try:
            with urllib.request.urlopen(requete, timeout=10) as reponse:
                corps = reponse.read()
        except Exception:  # réseau, HTTP, DNS — on essaie le suivant
            continue
        if corps:
            fichier.write_bytes(corps)
            return corps
    return None
