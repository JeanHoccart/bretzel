"""Gate : écrire l'attribut ``value`` observé, c'est COMMITER.

Le pendant statique et rapide de
``tests/runtime_js/test_calendar_range_pending_survives_rescan.py``. Les
deux sont nécessaires et ne se remplacent pas : celui-ci lit la source,
celui-là prouve au navigateur que le miroir re-tourne vraiment sur un
rescan — ce qu'aucune lecture du source ne peut observer.

Ce que cette gate ferme
-----------------------
Un attribut **observé** d'un custom element est une surface de synchro
avec l'extérieur : le framework écrit dedans depuis un ``bz-effect``
piloté par le scope du composant Python (``calendar_value_mirror``), et
cet effet re-tourne à CHAQUE swap HTMX, le bridge rescannant la cible.
Tout état que le scope ne sait pas représenter et qu'on range là sera
donc écrasé — c'est une question de quand, pas de si.

C'est ce qui est arrivé au mode ``range`` du ``<bz-calendar>``. Il
commite en deux temps, et le début en attente du premier clic vivait dans
l'attribut. Le miroir, voyant un scope vide, y poussait ``''`` ; le
second clic rouvrait alors une plage au lieu de la fermer, et le champ
restait vide indéfiniment. Le symptôme dépendait d'un aller-retour
serveur tombant ENTRE les deux clics, donc il passait pour aléatoire.

La forme vérifiable de l'invariant
----------------------------------
« L'attribut ne porte que du commité » n'est pas lisible par une machine.
Sa forme opérationnelle l'est, et c'est exactement ce que le fix a
établi : **toute écriture interne de ``value`` est immédiatement suivie
de son émission de ``change``**.

    this.setAttribute('value', X);
    this._syncHiddenAndFireChange(X, Y);

Une écriture SANS émission est, par construction, un état intermédiaire
rangé dans l'attribut — la faute. C'est un proxy, pas la phrase anglaise,
au même titre que le ``void this._geom`` de
``test_measured_deps_are_declared`` : la phrase n'est pas mécanisable, le
mécanisme l'est.

Mutation-testée par l'histoire plutôt que par une fabrication : le code
d'avant ``5a52a398`` contenait
``this.setAttribute('value', JSON.stringify([s, '']));`` suivi d'un
``return;`` nu. Cette gate est donc rouge sur le parent et verte sur
HEAD, sans qu'on ait eu à inventer un cas.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import (
    assert_runtime_sweep_is_not_vacuous,
    runtime_slabs,
)

#: ``this.setAttribute('value', …)`` / ``self.setAttribute("value", …)``.
#: Balaie TOUS les modules du runtime, pas seulement le calendrier : le
#: jour où un second custom element arrive, il est couvert sans qu'on y
#: pense — c'est le seul moment où on aurait pu y penser.
_VALUE_WRITE = re.compile(
    r"""\b(?:this|self)\.setAttribute\(\s*['"]value['"]"""
)
#: L'émission qui fait d'une écriture un commit.
_COMMIT = "_syncHiddenAndFireChange"


def _next_statement(text: str, start: int) -> str:
    """L'instruction suivante, commentaires et sauts de ligne retirés.

    Les commentaires sont sautés à dessein : une explication intercalée
    entre l'écriture et son émission est légitime, et l'interdire
    pousserait à en écrire moins — le contraire de ce que ce dépôt veut.
    """
    kept = [
        line.strip()
        for line in text[start:start + 400].splitlines()
        if line.strip() and not line.strip().startswith(("//", "/*", "*"))
    ]
    return " ".join(kept).partition(";")[0].strip()


def _write_sites() -> list[tuple[str, int, str]]:
    """``(module, ligne 1-based, instruction suivante)`` par écriture.

    ⚠️ Le balayage porte sur le TEXTE entier, pas ligne à ligne, et c'est
    load-bearing. Appliquée par ligne, la recherche rate un appel coupé
    en deux :

        this.setAttribute(
            'value', JSON.stringify([s, ''])
        );

    — qui est EXACTEMENT la forme qu'avait le site fautif avant le fix.
    Écrite ligne à ligne, cette gate passait au vert sur le bug qu'elle
    existe pour attraper. Attrapé en la mutation-testant, pas en la
    relisant : c'est la « regex aveugle » que
    ``test_prohibition_gates_declare_a_floor`` documente comme
    non-détectable structurellement.
    """
    sites: list[tuple[str, int, str]] = []
    for slab in runtime_slabs():
        text = slab.read_text(encoding="utf-8")
        for match in _VALUE_WRITE.finditer(text):
            end = text.find(";", match.end())
            sites.append((
                slab.name,
                text.count("\n", 0, match.start()) + 1,
                _next_statement(text, end + 1) if end != -1 else "",
            ))
    return sites


def test_the_write_site_population_is_not_vacuous() -> None:
    """Le plancher : sans lui, un renommage rendrait la gate verte à vide.

    Cinq sites mesurés le 2026-08-05 dans ``07_calendar.js`` (``set``, la
    cellule de mois, les modes ``picker`` / ``week``, et la fermeture de
    plage). Le plancher est serré à dessein — c'est précisément une gate
    devenue introuvable qui a laissé passer le bug qu'elle garde.
    """
    assert_runtime_sweep_is_not_vacuous()
    sites = _write_sites()
    assert len(sites) >= 5, (
        f"le balayage ne trouve plus que {len(sites)} écriture(s) de "
        f"l'attribut ``value`` (5 mesurées le 2026-08-05) — vérifie le "
        f"motif avant de croire que cette gate passe."
    )


def test_every_observed_value_write_is_immediately_committed() -> None:
    """Aucune écriture de ``value`` ne laisse d'état intermédiaire."""
    offenders = [
        f"{module}:{line} — suivie de {following!r}"
        for module, line, following in _write_sites()
        if _COMMIT not in following
    ]
    assert not offenders, (
        "une écriture de l'attribut ``value`` observé n'est pas suivie de "
        f"``{_COMMIT}`` :\n  " + "\n  ".join(offenders) + "\n\n"
        "Un attribut observé est piloté de l'extérieur par le "
        "``bz-effect`` miroir, qui re-tourne à chaque swap HTMX : tout "
        "état non commité rangé là sera écrasé. S'il s'agit d'une "
        "sélection en cours, elle va dans un champ interne de l'élément "
        "(cf. ``_pendingStart`` / ``_hoverDate``), pas dans l'attribut."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-q"])


def test_the_detector_still_bites() -> None:
    """Mutation : une écriture de l'attribut ``value`` est encore reconnue.

    Chaque écriture doit être suivie de son commit — sinon la valeur
    observée et l'état divergent. Une regex aveugle rendrait
    l'interdiction verte sur zéro site d'écriture.
    """
    for offending in ('this.setAttribute("value", v)', "self.setAttribute( 'value' , v)"):
        assert _VALUE_WRITE.search(offending), f"{offending!r} devrait mordre"
    for licit in ('el.setAttribute("value", v)', 'this.setAttribute("data-x", v)'):
        assert not _VALUE_WRITE.search(licit), f"{licit!r} : faux positif"
