"""En-têtes de sécurité — les ennuyeux toujours, la CSP à la demande.

Deux étages, et la ligne qui les sépare est « est-ce que ça peut casser
l'app ».

**Les en-têtes ennuyeux** (:data:`BORING_HEADERS`) ne dépendent de rien
que Bretzel ne connaisse : ils sont posés par défaut, et
``Bretzel(security_headers=False)`` les retire. Aucune décision à
prendre.

**La CSP**, elle, dépend de ce que l'app charge — ses polices, ses CDN,
ses ``ui.video`` distants — et le framework ne peut pas le deviner. Elle
est donc opt-in : ``Bretzel(csp="report-only")`` puis ``csp=True``. Mais
le dev ne rédige pas la politique : Bretzel connaît **ses propres**
besoins et les calcule ; ``csp_sources=`` ne sert qu'à déclarer ce que
l'app ajoute.

Ce que Bretzel doit à lui-même
------------------------------

- ``'unsafe-eval'`` : le moteur de directives compile chaque attribut
  ``bz-*`` en fonction (``new Function`` dans
  :file:`runtime/_src/02_directives.js` et :file:`03_scope.js`). Mesuré
  le 2026-09-05 : 29 % des 134 057 expressions émises par le playground
  sortent d'un sous-ensemble interprétable (fonctions fléchées à corps
  d'instructions 17 %, ``if``/``return`` 9,5 %, indexation calculée
  9 %, ``new X()`` 2,3 %), et ce sont les directives du framework qui
  les écrivent — ``bz-init`` 97 %, ``bz-on:focus`` 97 %, ``bz-class``
  92 %. S'en passer demanderait un interpréteur JS, pas une passe de
  nettoyage.

  ⚠️ Ça n'annule PAS la protection : sans ``'unsafe-inline'`` dans
  ``script-src``, une balise ``<script>`` injectée ne s'exécute pas —
  et c'est la classe XSS dominante. ``'unsafe-eval'`` ne sert un
  attaquant qu'une fois qu'il peut déjà faire entrer une chaîne dans
  une expression, ce que :func:`~bretzel.core.escape.escape_js` ferme.

- **Trois empreintes** plutôt qu'un ``nonce``. Les corps inline que la
  coque émet (:func:`~bretzel.render.shell.inline_scripts`) sont
  déterministes — mesuré : 3 empreintes distinctes sur 77 pages × 2
  requêtes. Un ``nonce`` aurait imposé une valeur par réponse (donc une
  page non cachable) et un paramètre de plus à toute coque
  personnalisée ; les hashes ne coûtent rien et ne touchent aucune
  signature.

- **Les hôtes d'API d'icônes.** La coque actuelle configure
  ``<iconify-icon>`` pour passer par la route locale
  ``/_bretzel/icons``. Les origines historiques restent autorisées pour
  compatibilité ; c'est le serveur qui les interroge lors d'un manque en
  cache, pas le navigateur du visiteur.

- **Les origines des assets, telles qu'elles sont**. Le repli CDN est
  la règle tant que ``python -m bretzel.render.vendor`` n'a pas tourné
  (cf. :mod:`bretzel.render.vendor`) : une politique écrite en dur
  mentirait une fois sur deux. Les URL viennent donc de
  :func:`~bretzel.render.shell.shell_sources`, la même source que ce que
  la coque émet — et c'est ce qui fait suivre la politique toute seule
  quand une quatrième dépendance arrive.

"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Final
from urllib.parse import urlsplit

__all__ = [
    "BORING_HEADERS",
    "CSP_DIRECTIVES",
    "ICON_API_ORIGINS",
    "build_policy",
    "script_hash",
]


#: Posés sur chaque réponse, sauf ``security_headers=False``.
#:
#: Aucun des trois ne dépend de ce que l'app charge, ce qui est la
#: raison pour laquelle ils sont un défaut et la CSP n'en est pas un.
#:
#: - ``nosniff`` empêche le navigateur de re-deviner le type d'une
#:   réponse — c'est ce qui transforme un fichier uploadé en script.
#: - ``strict-origin-when-cross-origin`` est le défaut des navigateurs
#:   modernes ; l'écrire le rend vrai aussi sur les vieux.
#: - ``SAMEORIGIN`` et non ``DENY`` : une app a le droit de s'inclure
#:   elle-même dans une iframe (aperçus, docs), et le clickjacking
#:   vient d'ailleurs. Quand la CSP est active, ``frame-ancestors``
#:   dit la même chose et prime.
BORING_HEADERS: Final[dict[str, str]] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "SAMEORIGIN",
}

#: Les hôtes historiques d'Iconify, conservés dans la politique pour
#: compatibilité. La coque dirige aujourd'hui les glyphes vers la route
#: locale ``/_bretzel/icons`` ; le relais serveur utilise la même liste.
#:
#: Gaté par ``tests/consistency/test_the_icon_hosts_are_in_the_policy.py``
#: : une mise à jour d'iconify qui changerait ces hôtes doit rougir ici
#: plutôt que faire disparaître les icônes en production.
ICON_API_ORIGINS: Final[tuple[str, ...]] = (
    "https://api.iconify.design",
    "https://api.simplesvg.com",
    "https://api.unisvg.com",
)

def _base_policy(
    *,
    hashes: Sequence[str],
    js_ext: Sequence[str],
    css_ext: Sequence[str],
) -> dict[str, list[str]]:
    """La politique que Bretzel se doit à lui-même.

    Extraite pour que :data:`CSP_DIRECTIVES` en DÉRIVE au lieu de la
    recopier : ajouter une directive ici la rend extensible par une app
    sans qu'on y pense, là où deux listes divergeaient en silence.
    """
    return {
        "default-src": ["'self'"],
        # ``'unsafe-eval'`` : le moteur de directives. Pas
        # ``'unsafe-inline'`` — c'est ce qui tue le <script> injecté.
        "script-src": ["'self'", "'unsafe-eval'", *hashes, *js_ext],
        # ``'unsafe-inline'`` est ici IRRÉDUCTIBLE : la page porte des
        # attributs ``style=``, et un hash ou un nonce ne couvre pas un
        # attribut — pire, en présence de l'un d'eux le navigateur
        # IGNORE ``'unsafe-inline'`` et l'attribut saute quand même.
        # Le compilateur Tailwind navigateur (mode dev) injecte en plus
        # sa feuille au runtime.
        "style-src": ["'self'", "'unsafe-inline'", *css_ext],
        "img-src": ["'self'", "data:", "blob:"],
        "font-src": ["'self'", "data:"],
        # Le pont POSTe en même origine, le SSE aussi. Les hôtes d'icônes
        # restent autorisés pour compatibilité avec l'ancien chemin direct.
        "connect-src": ["'self'", *ICON_API_ORIGINS, *js_ext],
        "media-src": ["'self'", "data:", "blob:"],
        "manifest-src": ["'self'"],
        "form-action": ["'self'"],
        # Le pendant de ``X-Frame-Options: SAMEORIGIN``, et il prime.
        "frame-ancestors": ["'self'"],
        "base-uri": ["'self'"],
        # Rien n'a besoin de <object>/<embed>, et ils contournent
        # ``script-src`` sur de vieux moteurs.
        "object-src": ["'none'"],
    }


#: Les directives qu'une app a le droit d'étendre via ``csp_sources``.
#:
#: La liste existe pour qu'une **faute de frappe soit une erreur** :
#: ``{"img_src": [...]}`` ou ``{"image-src": [...]}`` ne fait rien du
#: tout dans un navigateur, la ressource est simplement bloquée, et le
#: seul indice est une ligne de console. Refuser la clé au démarrage
#: coûte moins cher.
CSP_DIRECTIVES: Final[frozenset[str]] = frozenset(
    # DÉRIVÉE de la politique de base, plus recopiée : deux listes à
    # tenir d'accord divergeaient au premier ajout, et le symptôme
    # tombait chez le dev qui ESSAIE d'étendre la directive, pas chez
    # celui qui l'a ajoutée.
    _base_policy(hashes=(), js_ext=(), css_ext=())
) | frozenset(
    # Les deux que le socle ne porte pas : sans valeur par défaut, elles
    # héritent de ``default-src``, et une app doit pouvoir les déclarer.
    {"frame-src", "worker-src"}
)


def script_hash(body: str) -> str:
    """Rendre le ``'sha256-…'`` d'un corps de ``<script>`` inline.

    Le navigateur hache les octets **exactement** tels qu'ils sont entre
    les balises : pas de trim, pas de normalisation. D'où le
    ``encode("utf-8")`` nu.
    """
    digest = hashlib.sha256(body.encode("utf-8")).digest()
    return f"'sha256-{base64.b64encode(digest).decode('ascii')}'"


def _origin(url: str) -> str | None:
    """Rendre l'origine d'une URL absolue, ou ``None`` si elle est relative.

    Une URL relative (``/_bretzel/vendor/htmx.min.js``) est couverte par
    ``'self'`` et n'a rien à ajouter à la politique.
    """
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def build_policy(
    *,
    inline_bodies: Iterable[str],
    script_urls: Iterable[str],
    style_urls: Iterable[str] = (),
    extra: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """Composer la valeur de l'en-tête ``Content-Security-Policy``.

    ``script_urls`` et ``style_urls`` sont les URL que la coque va
    réellement émettre — c'est ce qui rend la politique juste que le
    rapatriement vendor ait eu lieu ou non, et ce qui la fait suivre
    toute seule quand une quatrième dépendance arrive. Les deux sont
    séparées parce qu'une origine de script n'a rien à faire dans
    ``style-src`` : l'y mettre autoriserait une feuille de style qu'on
    n'a jamais eu l'intention de charger. ``inline_bodies`` sont les
    corps de :func:`~bretzel.render.shell.inline_scripts`.

    Les valeurs de ``extra`` sont ajoutées **en plus** des sources du
    framework : une app peut élargir, jamais rétrécir. Rétrécir se ferait
    en silence et casserait le framework chez le dev qui l'a fait.
    """
    js_ext = sorted({o for u in script_urls if (o := _origin(u))})
    css_ext = sorted({o for u in style_urls if (o := _origin(u))})
    hashes = [script_hash(b) for b in inline_bodies]

    politique = _base_policy(hashes=hashes, js_ext=js_ext, css_ext=css_ext)

    for nom, ajouts in (extra or {}).items():
        if nom not in CSP_DIRECTIVES:
            connues = ", ".join(sorted(CSP_DIRECTIVES))
            raise ValueError(
                f"csp_sources : directive inconnue {nom!r}. "
                f"Une directive mal orthographiée ne fait RIEN dans un "
                f"navigateur — la ressource est bloquée sans message. "
                f"Les directives acceptées sont : {connues}."
            )
        # ⚠️ Une directive ABSENTE de la politique n'est pas permissive :
        # elle retombe sur ``default-src``. La déclarer la fait donc
        # sortir de ce repli, et ce que ``default-src`` autorisait est
        # perdu — c'est un RÉTRÉCISSEMENT déguisé en ajout.
        #
        # Mesuré le 2026-09-05 sur le playground : ``frame-src: ["data:"]``
        # a bloqué une iframe MÊME-ORIGINE qui passait avant, parce que
        # ``frame-src`` héritait jusque-là de ``default-src 'self'``. On
        # amorce donc avec ce dont la directive héritait, pour que
        # « élargir, jamais rétrécir » soit vrai et pas seulement écrit.
        politique.setdefault(nom, list(politique["default-src"]))
        for source in ajouts:
            if source not in politique[nom]:
                politique[nom].append(source)

    return "; ".join(f"{nom} {' '.join(vals)}" for nom, vals in politique.items())
