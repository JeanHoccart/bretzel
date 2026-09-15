"""Les en-tetes de colonne du calendrier nomment leur jour en entier.

Ce que ca ferme
---------------
Les sept colonnes rendent l'abreviation qu'``Intl`` donne (``mer.``,
``Wed``). Deux personnes y perdent quelque chose : celle qui survole et
n'a aucun moyen de lever le doute, et celle qui ecoute — un lecteur
d'ecran EPELLE ``M-E-R`` la ou il pourrait dire « mercredi ».

Le ``title=`` coute sept appels ``Intl`` de plus, memoises **une fois par
etiquette de langue** dans ``$bz.locale`` — pas par calendrier, ce qui
compte sur une page qui en rend cinquante.

⚠️ Ce que ce test ne prouve PAS, et pourquoi il ne le vise pas
---------------------------------------------------------------
L'idee venait d'une capture ou l'on lisait ``WED -> EPOUSER``,
``SUN -> SOLEIL``. Ce n'etait pas Bretzel : c'etait **Google Translate**,
declenche parce que le banc rendait une page mixte (``lang="en"`` avec
des titres francais en dur). Le banc a ete corrige, et avec une langue
correctement declaree le navigateur ne propose jamais de traduire.
Concevoir contre l'auto-traduction serait viser la mauvaise cible — ce
test vise le survol et le lecteur d'ecran, rien d'autre.

Trois abstentions, chacune deliberee
-------------------------------------
- **L'app fournit ses propres abreviations** (``weekday_names=``) : aucun
  ``title``. Deviner « mer. » -> « mercredi » marcherait en francais et
  nulle part ailleurs, et un title FAUX est pire que pas de title.
- **Pas d'``Intl`` utilisable** : le repli n'a que des abreviations, donc
  le long vaut le court, donc rien n'est emis.
- **Le long EGALE le court** (certaines langues) : rien non plus. Un
  ``title`` qui repete le texte visible est du bruit a l'oreille.

Lourd (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_a_weekday_header_names_its_day.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="j" * 32, title="jours", mode="dev", lang="fr")


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-6"):
        ui.calendar(id="auto", weekstart=1)
        # Abreviations fournies par l'app : la locale ne peut pas savoir
        # de quels jours entiers elles sont l'abreviation.
        ui.calendar(id="fourni", weekstart=1,
                    weekday_names=["D", "L", "M", "M", "J", "V", "S"])


app.include(__name__)

_ENTETES = """
(id) => {
  const cal = document.querySelector('#' + id + ', [bz-id="' + id + '"]')
           || document.getElementById(id);
  if (!cal) return {error: 'calendrier ' + id + ' introuvable'};
  const cells = [...cal.querySelectorAll('div')]
    .filter(d => d.children.length === 0 && d.textContent.trim().length
                 && d.textContent.trim().length <= 4
                 && !/^\\d+$/.test(d.textContent.trim()));
  const sept = cells.slice(0, 7);
  return {
    textes: sept.map(d => d.textContent.trim()),
    titres: sept.map(d => d.getAttribute('title')),
  };
}
"""


@pytest.fixture(scope="module")
def calendrier():
    with audit_server(app) as url, browser_page(url, "/") as pg:
        pg.wait_for_selector("html.bz-ready", state="attached")
        pg.wait_for_timeout(500)
        yield pg


def test_the_header_row_is_actually_found(calendrier) -> None:
    """Plancher : sans lui, « aucun titre manquant » passerait sur zero
    cellule — le mode d'echec que tout ce dossier documente."""
    vu = calendrier.evaluate(_ENTETES, "auto")
    assert "error" not in vu, vu
    assert len(vu["textes"]) == 7, (
        f"7 en-tetes attendus, {len(vu['textes'])} vus : {vu['textes']}. "
        f"Le selecteur ne trouve plus la rangee des jours."
    )


def test_each_weekday_header_carries_its_full_name(calendrier) -> None:
    vu = calendrier.evaluate(_ENTETES, "auto")
    manquants = [
        (txt, ttl) for txt, ttl in zip(vu["textes"], vu["titres"])
        if not ttl
    ]
    assert not manquants, (
        f"des en-tetes sans title : {manquants}. Le survol ne leve pas le "
        f"doute, et un lecteur d'ecran epelle l'abreviation."
    )
    # Le title doit APPORTER quelque chose : plus long que ce qu'on voit.
    inutiles = [
        (txt, ttl) for txt, ttl in zip(vu["textes"], vu["titres"])
        if ttl and len(ttl) <= len(txt)
    ]
    assert not inutiles, (
        f"title qui n'ajoute rien : {inutiles} — c'est du bruit a "
        f"l'oreille, pas une aide."
    )
    # Et il doit nommer LE BON jour : lundi en tete avec weekstart=1.
    assert vu["titres"][0].lower().startswith("lun"), (
        f"avec weekstart=1 la premiere colonne est lundi, title vu : "
        f"{vu['titres'][0]!r}. Les noms entiers ne sont pas tournes du "
        f"meme nombre de crans que les abreviations."
    )


def test_app_supplied_abbreviations_get_no_title(calendrier) -> None:
    """Le versant ABSTENTION — sans lui, la gate passerait aussi bien si
    on inventait un nom entier pour n'importe quelle abreviation."""
    vu = calendrier.evaluate(_ENTETES, "fourni")
    assert "error" not in vu, vu
    assert vu["textes"][:3] == ["L", "M", "M"], (
        f"les abreviations de l'app ne sont pas rendues : {vu['textes']}"
    )
    assert not any(vu["titres"]), (
        f"des titles ont ete inventes pour des abreviations fournies par "
        f"l'app : {vu['titres']}. Deviner « M » -> « mardi » ou « mercredi » "
        f"n'est pas decidable."
    )
