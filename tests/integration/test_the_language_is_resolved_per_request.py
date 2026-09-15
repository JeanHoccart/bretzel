"""La langue est choisie par REQUÊTE, pas par application.

Ce que ce fichier garde
------------------------
Une app déclare ``languages=["en", "fr"]``, et deux visiteurs de la même
URL reçoivent deux langues sans que personne n'ait écrit une ligne de
logique. C'est la promesse entière, et elle repose sur une chaîne de
trois maillons dont **l'ordre est le sujet** :

1. le cookie ``bz_lang`` — un CHOIX, donc il gagne ;
2. ``Accept-Language`` — un défaut de première visite ;
3. ``lang=`` — le repli.

Cet ordre est celui de Django (``LocaleMiddleware``), de Rails et de
next-intl, et l'inverser ne casse **rien de visible** : la négociation
continue de marcher, les pages continuent de rendre, et seul le
sélecteur de langue cesse d'avoir un effet — pour les gens dont l'OS
n'est pas dans la langue qu'ils ont choisie. C'est précisément le genre
de régression qu'aucune page qui rend ne signale.

Trois choses ne sont PAS testées ici
-------------------------------------
Le rechargement de :meth:`bretzel.Language.set` (``HX-Refresh``) demande un
navigateur : ``tests/probes/probe_lang.py``. Les noms de mois du
calendrier aussi — ils sont dérivés par ``Intl`` **dans le navigateur**
à partir du ``<html lang>`` que ce fichier vérifie, donc ce qu'on garde
ici est le maillon serveur de cette chaîne. Et les chaînes de l'app
elle-même n'ont pas de mécanisme à tester : :func:`bretzel.lang` rend
la langue, le dict est à l'app.
"""

from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from bretzel import Bretzel, Language, page, ui

_SECRET = "x" * 32

#: ``alert.dismiss`` est un ``aria-label``, donc il traverse
#: l'échappement HTML. Le mot choisi n'a ni apostrophe ni accent — une
#: assertion qui cherche « Fermer l'alerte » dans la réponse échoue sur
#: ``'`` et fait croire à un bug de négociation (vécu en écrivant
#: ce fichier).
_FR_DISMISS = "Fermer"

app = Bretzel(
    secret_key=_SECRET,
    lang="en",
    languages=["en", "fr"],
    texts={"fr": {"alert.dismiss": _FR_DISMISS}},
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack():
        ui.text(f"resolved={Language().code}")
        ui.alert("hello", dismissible=True)


app.include(sys.modules[__name__])


def _served_language(response) -> str:
    """La langue RÉELLEMENT servie, lue sur un mot du framework.

    Volontairement lue sur le rendu et pas sur ``<html lang>`` : les deux
    peuvent diverger (l'attribut vient de ``ctx.lang``, la phrase de
    ``ctx.texts``), et c'est cette divergence qui ferait un calendrier
    français dans une page anglaise.
    """
    return "fr" if f'aria-label="{_FR_DISMISS}"' in response.text else "en"


def _html_lang(response) -> str:
    return response.text.split('<html lang="')[1].split('"')[0]


class TestTheHeaderDecidesOnTheFirstVisit:
    def test_a_french_browser_gets_french_without_asking(self) -> None:
        with TestClient(app) as client:
            r = client.get("/", headers={"accept-language": "fr-CA,fr;q=0.9,en;q=0.8"})
        assert _served_language(r) == "fr"
        assert _html_lang(r) == "fr", "le calendrier lit cet attribut"

    def test_an_unknown_language_falls_back_to_the_default(self) -> None:
        with TestClient(app) as client:
            r = client.get("/", headers={"accept-language": "de,es;q=0.7"})
        assert _served_language(r) == "en"

    def test_no_header_at_all_falls_back(self) -> None:
        with TestClient(app) as client:
            r = client.get("/")
        assert _served_language(r) == "en"


class TestTheCookieOutranksTheHeader:
    def test_a_choice_beats_the_operating_system(self) -> None:
        """Le maillon qui rend un sélecteur de langue possible.

        Sans lui, quelqu'un dont le système est anglais mais qui lit en
        français n'a aucun moyen de le dire — et l'app n'a aucun moyen
        de le lui offrir.
        """
        with TestClient(app) as client:
            r = client.get(
                "/",
                headers={"accept-language": "en-US,en;q=0.9"},
                cookies={"bz_lang": "fr"},
            )
        assert _served_language(r) == "fr"
        assert _html_lang(r) == "fr"

    def test_a_cookie_naming_a_dropped_language_is_ignored(self) -> None:
        """Sinon un visiteur reste coincé dans une langue retirée, avec
        une table qui n'existe plus — et c'est une ``KeyError`` sur
        chaque page, pas un repli."""
        with TestClient(app) as client:
            r = client.get(
                "/",
                headers={"accept-language": "fr"},
                cookies={"bz_lang": "zz"},
            )
        assert r.status_code == 200
        assert _served_language(r) == "fr", "l'en-tête reprend la main"


class TestAMonolingualAppIsUntouched:
    def test_nothing_is_negotiated_without_languages(self) -> None:
        """Le chemin par défaut : aucune app existante ne change de
        comportement parce que la négociation a été ajoutée.

        Éprouvé sur le résolveur directement plutôt que par HTTP :
        monter une SECONDE app dans ce module ferait enregistrer ses
        pages sur la première aussi (``include`` balaie les attributs du
        module), et le test mentirait sur ce qu'il monte.
        """
        from bretzel.render.lang import resolve_language

        mono = Bretzel(secret_key=_SECRET, lang="fr", mode="dev")
        assert mono.config.languages == ("fr",), "normalisé, pas vide"
        assert resolve_language(
            cookie=None,
            header="en-US,en;q=0.9",
            available=mono.config.languages,
            default=mono.config.lang,
        ) == "fr"

    def test_a_bilingual_app_reads_the_header_on_the_same_input(self) -> None:
        """Le témoin de l'assertion ci-dessus : c'est bien ``languages=``
        qui change la décision, pas l'en-tête qui serait ignoré partout.
        """
        from bretzel.render.lang import resolve_language

        assert resolve_language(
            cookie=None,
            header="en-US,en;q=0.9",
            available=app.config.languages,
            default=app.config.lang,
        ) == "en"
