"""Aucun dialecte Alpine ne survit dans ``bretzel/``.

Alpine est sorti du framework en V3 : le moteur de directives
(``runtime/_src/02_directives.js``) ne scanne que ``bz-attr:`` et ``bz-on:``.
Un attribut ``:x`` / ``@x`` / ``x-x`` émis par un composant partirait donc
dans le DOM, valide, et **personne ne le lirait jamais** — zéro erreur, zéro
warning, zéro effet.

Ce que cette gate couvre, et pourquoi elle a deux moitiés
---------------------------------------------------------
1. **Le socle refuse** (``reject_dead_alpine_attr``) — donc un utilisateur ne
   PEUT plus en passer, ni par ``**kwargs`` ni par ``attrs={...}``.
2. **Aucun composant n'en écrit** — le refus ne protège que la surface
   publique ; un composant qui écrirait ``attrs[":class"] = …`` dans son
   ``render()`` contournerait le contrôle. C'est ce que le balayage vérifie.

Pourquoi cette gate existe (audit du socle 2026-07-29, item 4)
---------------------------------------------------------------
``_PASSTHROUGH_PREFIXES`` valait ``(":", "@", "x-", "hx-")``. Le commit
``10e34c2e`` (2026-07-03) a renommé ``_RAW_ALPINE_PREFIXES`` →
``_PASSTHROUGH_PREFIXES`` en annonçant « Pure behaviour-neutral rename […]
no logic touched » : **le nom a été dé-Alpiné, la valeur non**. Le dialecte
mort a donc survécu neuf mois sous un nom neutre.

⚠️ Retirer les préfixes de la liste ne fermait PAS le mode d'échec :
``normalize_attr_name`` renvoie tel quel tout nom contenant ``-``/``:``/``@``,
donc le catch-all ``raw_html`` émettait exactement le même attribut. C'est le
**refus bruyant** qui est le fix ; le tuple n'était que du vocabulaire.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    component_sources,
)

# Un littéral de nom d'attribut Alpine dans une chaîne Python : ``":class"``,
# ``'@click'``, ``"x-show"``. On borne à gauche sur le guillemet pour ne pas
# ramasser un ``:`` de milieu de chaîne (``"flex:1"``) ni un ``@`` d'email.
_ALPINE_LITERAL = re.compile(
    r"""["'](?::[a-z][\w.-]*|@[a-z][\w.:-]*|x-(?!ref\b)[a-z][\w.-]*)["']""",
    re.IGNORECASE,
)

# ``x-ref`` est exclu du motif ci-dessus : c'est un faux ami. Le dépôt écrit
# ``bz-ref``, mais le mot « x-ref » apparaît dans de la prose (« cf. x-ref »).
# Aucun composant n'émet l'attribut.


def test_the_sweep_visits_the_components() -> None:
    """Plancher de non-vacuité — le test ci-dessous est une interdiction."""
    assert_sweep_is_not_vacuous()


@pytest.mark.parametrize(
    "path", component_sources(), ids=lambda p: p.name
)
def test_no_component_emits_an_alpine_attribute(path) -> None:
    offenders: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text(encoding="utf8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if _ALPINE_LITERAL.search(line):
            offenders.append((i, stripped[:88]))

    assert not offenders, (
        f"{path.name} écrit un attribut au dialecte Alpine :\n"
        + "\n".join(f"    :{i}  {text}" for i, text in offenders)
        + "\n  Alpine est sorti en V3 — le runtime ne scanne que `bz-attr:` "
          "et `bz-on:` (02_directives.js). Cet attribut partirait dans le DOM "
          "sans que rien ne le lise.\n"
          "  `@x` → `bz-on:x` · `:x` → `bz-attr:x` · `x-y` → `bz-y`. Pour "
          "brancher le SERVEUR, déclare un handler `on_<event>=` et laisse le "
          "socle émettre le POST signé."
    )


def test_the_base_still_refuses_them_at_the_door() -> None:
    """La moitié « surface publique » du contrat, figée ici pour qu'un
    retrait du refus ne passe pas inaperçu."""
    from bretzel.components.base.attrs import (
        ComponentUsageError,
        reject_dead_alpine_attr,
    )

    for name in (":disabled", "@click", "x-show"):
        with pytest.raises(ComponentUsageError, match="Alpine"):
            reject_dead_alpine_attr("Probe", name)

    # Et les dialectes vivants passent.
    for name in ("hx-post", "bz-show", "bz-on:click", "data-testid", "class"):
        reject_dead_alpine_attr("Probe", name)
