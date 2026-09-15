"""Quelle langue servir à CETTE requête — et la table de mots qui va avec.

Pair de :mod:`bretzel.render.screen`, et pour la même raison : le
navigateur sait quelque chose que le serveur doit rendre. Là-bas c'est la
forme de l'écran, ici la langue ; dans les deux cas un cookie porte le
choix, et le serveur rend depuis une vraie valeur plutôt que de deviner.

Le partage avec :mod:`bretzel.render.texts` est net : **ce module choisit
la langue, l'autre possède les mots.**

La chaîne, et pourquoi son ordre est le sujet
----------------------------------------------
1. le cookie ``bz_lang``, s'il nomme une langue déclarée ;
2. ``Accept-Language``, négocié contre les langues de l'app ;
3. la langue par défaut (``Bretzel(lang=…)``).

C'est l'ordre de Django (``LocaleMiddleware``), de Rails et de
next-intl, et ce n'est pas un goût. ``Accept-Language`` décrit la
configuration du système d'exploitation, **pas un choix de lecture** :
quelqu'un dont le système est anglais mais qui lit en français doit
pouvoir le dire, et sans un cookie au-dessus de l'en-tête un sélecteur
de langue serait inécrivable. Une page qui dépend du seul en-tête cesse
aussi d'être adressable — deux personnes ouvrant la même URL voient deux
pages, ce qui casse les favoris, le référencement, et oblige le cache à
``Vary``.

Inverser cet ordre ne casse **rien de visible** : la négociation
continue de marcher, les pages continuent de rendre, et seul le
sélecteur cesse d'avoir un effet, pour les gens dont le système n'est
pas dans la langue qu'ils ont choisie. D'où deux mesures plutôt qu'une
relecture : ``tests/integration/test_the_language_is_resolved_per_request.py``
et ``tests/probes/probe_lang.py``, qui l'éprouve au navigateur.

Ce que ce module ne fait pas
-----------------------------
Traduire les chaînes de l'app. :attr:`Language.code` rend la langue
résolue, et un
dict par langue dans l'app fait le reste en six lignes ; les catalogues,
l'extraction et les règles de pluriel par langue sont un chantier à part
(v2.1). Ce qui manquait vraiment, c'était de savoir QUELLE langue servir.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from bretzel.core.errors import BretzelError
from bretzel.render.texts import DEFAULT_TEXTS, TextsError, resolve_texts
from bretzel.runtime.protocol import LANG_COOKIE

__all__ = [
    "Language",
    "LanguageTables",
    "negotiate_language",
    "resolve_language",
]


#: ``fr``, ``fr-CA``, ``*`` — plus un ``;q=0,8`` toléré (des proxys en
#: produisent). Tout le reste est ignoré silencieusement : un en-tête mal
#: formé est du bruit venu du réseau, pas une erreur de l'app.
_ACCEPT_ITEM = re.compile(
    r"^\s*(?P<tag>[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*|\*)"
    r"\s*(?:;\s*q\s*=\s*(?P<q>[0-9]+(?:[.,][0-9]+)?))?\s*$"
)


def _primary(tag: str) -> str:
    """``fr-CA`` → ``fr``. La comparaison se fait toujours en minuscules."""
    return tag.lower().split("-", 1)[0]


def negotiate_language(
    header: str | None,
    available: Sequence[str],
    *,
    default: str,
) -> str:
    """La langue à servir d'après ``Accept-Language``, ou ``default``.

    Chaque étiquette annoncée est essayée d'abord ENTIÈRE (``fr-CA``
    contre ``fr-CA``), puis sur son sous-marqueur primaire (``fr-CA``
    contre ``fr``), avant de passer à la suivante. Sans ce dégroupage, un
    navigateur canadien — ou n'importe quel ``en-US``, qui est le réglage
    d'usine de Chrome aux États-Unis — ne correspondrait jamais.

    ``q`` ordonne les préférences ; à ``q`` égal, l'ordre d'écriture
    tranche, parce que c'est ce que le navigateur veut dire. Un ``q=0``
    est un REFUS explicite et sort l'étiquette, contrairement à une
    absence. ``*`` rend le défaut : « n'importe laquelle » n'est pas un
    choix.

    Une seule langue disponible sort immédiatement : il n'y a rien à
    choisir, donc rien à analyser. C'est le chemin d'une app monolingue,
    et c'est **ici** qu'il vit plutôt que chez trois appelants — ceux-ci
    testaient un ``languages`` vide, ce qui faisait deux représentations
    du même état.
    """
    if len(available) <= 1 or not header:
        return default

    ranked: list[tuple[float, str]] = []
    for chunk in header.split(","):
        match = _ACCEPT_ITEM.match(chunk)
        if match is None:
            continue
        raw_q = match.group("q")
        quality = float(raw_q.replace(",", ".")) if raw_q else 1.0
        if quality > 0:
            ranked.append((quality, match.group("tag")))
    # ``sort`` est STABLE, y compris avec ``reverse`` : l'ordre d'ajout
    # (celui de l'en-tête) départage donc les qualités égales, sans avoir
    # à porter un index dans le tuple.
    ranked.sort(key=lambda row: row[0], reverse=True)

    #: dernier gagnant — deux entrées de même étiquette sont une faute de
    #: l'app, pas une ambiguïté à arbitrer.
    exact = {code.lower(): code for code in available}
    #: premier gagnant : ``["fr-CA", "fr"]`` doit servir ``fr-BE`` par
    #: ``fr-CA``, la première déclarée, pas par la dernière.
    primaries: dict[str, str] = {}
    for code in available:
        primaries.setdefault(_primary(code), code)

    for _, tag in ranked:
        if tag == "*":
            return default
        hit = exact.get(tag.lower()) or primaries.get(_primary(tag))
        if hit is not None:
            return hit
    return default


class LanguageTables:
    """Les tables de mots du framework, une par langue déclarée.

    **Pourquoi un objet plutôt qu'un dict sur la config.** La première
    version rangeait ``{code: table}`` dans ``BretzelConfig.texts`` et le
    middleware faisait ``cfg.texts[resolved]``. Ça marchait — parce qu'un
    invariant non écrit tenait, réparti sur trois fichiers : la config
    exigeait ``lang ∈ languages``, elle construisait ses clés depuis les
    deux, et le middleware n'honorait un cookie que s'il était dans
    ``languages``. Le jour où l'un des trois glisse, la conséquence n'est
    pas un repli mais un ``KeyError`` **sur chaque requête** — une 500
    complète pour une erreur de configuration.

    Une table qu'on INTERROGE ne peut pas rater : :meth:`for_language`
    retombe sur la langue par défaut. L'invariant cesse d'avoir besoin
    d'être vrai, donc il cesse d'avoir besoin d'être gardé.

    ``texts=`` accepte DEUX formes, distinguées par le type des valeurs :

    - **plate** (``{"alert.dismiss": "Fermer"}``) — la surcharge de la
      langue par défaut, la forme d'avant l'axe de langue ;
    - **par langue** (``{"fr": {"alert.dismiss": "Fermer"}}``).

    Les mélanger **lève** : un dict qui contient à la fois une phrase et
    une table n'a pas de lecture juste, et deviner rangerait la moitié
    des clés dans une langue nommée « alert.dismiss ».
    """

    __slots__ = ("_default", "_tables")

    def __init__(
        self,
        overrides: Mapping[str, Any] | None,
        *,
        languages: Iterable[str],
        default: str,
    ) -> None:
        codes = list(dict.fromkeys([default, *languages]))
        self._default = default
        # Toute langue déclarée mais non surchargée retombe sur l'anglais.
        # Pas d'erreur : une app qui ajoute ``"de"`` avant d'avoir traduit
        # doit pouvoir la servir, en anglais, plutôt que refuser de démarrer.
        self._tables: dict[str, Mapping[str, str]] = dict.fromkeys(
            codes, DEFAULT_TEXTS
        )
        if not overrides:
            return

        nested = {k for k, v in overrides.items() if isinstance(v, Mapping)}
        # ``flat`` = tout le reste, pas « les chaînes » : une valeur d'un
        # troisième type se glisserait entre deux listes et échapperait au
        # garde ci-dessous.
        flat = set(overrides) - nested
        if nested and flat:
            raise TextsError(
                f"texts= mélange les deux formes : {sorted(flat)[:3]} sont des "
                f"phrases (forme plate) et {sorted(nested)[:3]} des tables "
                f"(forme par langue). Choisis-en une — un dict qui contient "
                f"les deux n'a pas de lecture juste."
            )
        if not nested:
            self._tables[default] = resolve_texts(overrides)  # type: ignore[arg-type]
            return

        unknown = sorted(nested - set(codes))
        if unknown:
            raise TextsError(
                f"texts= surcharge des langues non déclarées : "
                f"{', '.join(repr(c) for c in unknown)}. Ajoute-les à "
                f"``languages=``, sinon personne ne les recevra jamais — une "
                f"table que rien ne peut sélectionner est du travail perdu en "
                f"silence."
            )
        for code in nested:
            self._tables[code] = resolve_texts(overrides[code])

    def for_language(self, code: str) -> Mapping[str, str]:
        """La table de ``code``, ou celle de la langue par défaut.

        Le repli est la raison d'être de cette classe : voir l'en-tête.
        """
        return self._tables.get(code) or self._tables[self._default]

    def languages(self) -> tuple[str, ...]:
        """Les codes couverts, défaut en tête."""
        return tuple(self._tables)

    def __repr__(self) -> str:
        return f"LanguageTables({', '.join(self.languages())})"


def resolve_language(
    *,
    cookie: str | None,
    header: str | None,
    available: Sequence[str],
    default: str,
) -> str:
    """La langue de cette requête. **C'est la politique**, en un endroit.

    Les trois maillons sont documentés en tête de module, ainsi que la
    raison pour laquelle le cookie passe devant l'en-tête.

    Un cookie qui nomme une langue RETIRÉE de ``available`` est ignoré,
    pas honoré : sinon un visiteur resterait coincé dans une langue que
    l'app ne sait plus rendre.

    Fonction plutôt que classe — contrairement à :class:`~bretzel.render
    .screen.Screen`, qui se construit dans un contexte de rendu déjà là.
    Celle-ci tourne AVANT que le contexte existe, puisque c'est elle qui
    décide de la table de mots qu'il portera.
    """
    if cookie and cookie in available:
        return cookie
    return negotiate_language(header, available, default=default)


class Language:
    """La langue de cette requête — la LIRE, et la CHOISIR.

    Lecture, dans la même forme que ses trois sœurs d'ambiance
    (:class:`~bretzel.render.screen.Screen`,
    :class:`~bretzel.theme.ColorScheme`,
    :class:`~bretzel.state.LiveConnection`) — un objet, un champ ::

        Language().code            # "en", "fr-CA"…

    C'est la couture par laquelle une app traduit **ses propres**
    chaînes, que le framework ne connaît pas et ne connaîtra pas ::

        STRINGS = {"en": {"save": "Save"}, "fr": {"save": "Enregistrer"}}

        def t(key, **fmt):
            return STRINGS.get(Language().code, STRINGS["en"])[key].format(**fmt)

    Six lignes plutôt qu'un système de catalogues, et c'est délibéré :
    l'extraction, les fichiers ``.po`` et les règles de pluriel par
    langue sont un chantier à part (v2.1).

    Écriture par :meth:`set`, qui MIME
    :meth:`~bretzel.theme.ColorScheme.set` — deux préférences de lecteur,
    un même objet nommé, un même verbe.

    ⚠️ **La ressemblance s'arrête à l'invocation, et c'est un fait, pas
    un oubli.** ``ColorScheme.set("dark")`` rend de la source JS parce
    que la couleur vit dans le navigateur ; ``Language.set`` AGIT, parce
    que c'est le serveur qui écrit le texte. On l'écrit donc avec
    ``partial``, comme les 29 autres handlers à argument lié du dépôt ::

        ui.button("Français", on_click=partial(Language.set, "fr"))
        ui.button("Sombre",   on_click=ColorScheme.set("dark"))

    Faire rendre un handler par ``Language.set("fr")`` aurait donné deux
    lignes identiques — mais alors ``Language.set(u.langue)`` appelé
    DEPUIS un handler (appliquer la langue enregistrée après connexion)
    n'aurait rien fait, sans un mot. Un no-op silencieux coûte plus cher
    qu'un ``partial`` visible.

    Hors contexte de rendu, :attr:`code` rend l'anglais : un composant
    construit dans une suite unitaire reste utilisable.

    """

    __slots__ = ("code",)

    #: La langue résolue de cette requête, en BCP-47 — ``"en"``,
    #: ``"fr-CA"``.
    #:
    #: Annotée ICI et pas seulement assignée dans ``__init__`` : le
    #: descripteur que ``__slots__`` pose suffirait à l'exécution, mais
    #: ``test_cited_symbols_resolve`` lit les classes à l'AST, où un
    #: slot n'est qu'une chaîne dans un tuple. Sans cette ligne, toute
    #: prose qui écrit ``:attr:`Language.code``` rougit. (``Screen`` s'en
    #: passe parce qu'aucune prose ne cite ses champs par un rôle.)
    code: str

    #: Un an. Une préférence de langue n'a pas de raison d'expirer avec la
    #: session : quelqu'un qui a choisi le français le veut encore au retour.
    _COOKIE_MAX_AGE = 365 * 24 * 3600

    def __init__(self) -> None:
        from bretzel.render.context import maybe_current_context

        ctx = maybe_current_context()
        self.code = getattr(ctx, "lang", None) or "en"

    @classmethod
    def set(cls, code: str) -> None:
        """Choisir la langue, et recharger la page dans cette langue.

        Le sélecteur de langue d'une app, en entier ::

            ui.button("Français", on_click=partial(Language.set, "fr"))

        **Pourquoi ça existe alors que la langue est automatique** :
        ``Accept-Language`` décrit la configuration du système
        d'exploitation, pas un choix de lecture. Sans un moyen de dire le
        contraire, une personne dont le système est anglais mais qui lit
        en français serait prisonnière de la négociation. Le cookie posé
        ici gagne sur l'en-tête à la requête suivante (cf.
        :func:`resolve_language`).

        Le rechargement — et non un re-rendu — est expliqué sur
        :func:`~bretzel.server.navigation.reload` : la langue change la
        page ENTIÈRE, alors qu'une réponse d'action ne rapporte que les
        zones qu'elle a rafraîchies.

        Lève si ``code`` n'est pas une langue déclarée. Le cookie serait
        sinon posé puis ignoré à la requête suivante : un bouton sans
        effet visible, et rien dans les journaux.
        """
        # ``navigation`` est AU-DESSUS de ``render`` dans le DAG, d'où
        # l'import différé — même forme que ``render/context.py``, qui
        # remonte vers ``server.handlers`` pour signer une action.
        # ``current_context`` est de la même couche, différé par la même
        # convention que ``render/screen.py``.
        #
        # Cette remontée est l'asymétrie du sujet, et elle est vraie :
        # ``Language`` est la seule des quatre lectures d'ambiance dont
        # l'ÉCRITURE est un aller-retour serveur (cookie + rechargement).
        # Son versant lecture reste où on le lit ; son versant écriture
        # remonte. (Le concept, lui, s'étale déjà sur trois couches — le
        # nom du cookie est dans ``runtime/protocol.py``, la déclaration
        # ``languages`` dans ``server/config.py``.)
        from bretzel.render.context import current_context
        from bretzel.server.navigation import reload as _reload

        ctx = current_context()
        languages = ctx.app.config.languages
        if code not in languages:
            hint = (
                " L'app n'en déclare qu'une : ajoute Bretzel(languages=['en', 'fr'])."
                if len(languages) <= 1
                else ""
            )
            raise BretzelError(
                f"Language.set({code!r}) : langue non déclarée. languages="
                f"{list(languages)}.{hint}"
            )
        ctx.set_cookie(
            LANG_COOKIE,
            code,
            max_age=cls._COOKIE_MAX_AGE,
            samesite="lax",
            # Lisible en JS À DESSEIN, contrairement au cookie de session :
            # ce n'est pas un secret, et une app qui veut proposer sa langue
            # côté client doit pouvoir la lire.
            httponly=False,
            path="/",
        )
        _reload()
