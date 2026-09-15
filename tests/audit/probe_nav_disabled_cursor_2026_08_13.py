"""Probe — l'affordance disabled des trois items de nav PEINT-elle ?

Rejouable. Répond à la question que ``test_disabled_affordance`` ne peut
pas poser : la gate lit du HTML, or le défaut est une **annulation CSS**
— ``pointer-events-none`` sur le même élément que ``cursor-not-allowed``
empêche le curseur de peindre.

⚠️ **Et ``getComputedStyle`` ne suffit PAS non plus.** Première version de
ce probe : elle lisait ``cs.cursor`` et déclarait le fix bon. Son témoin
— la forme d'avant — rendait ``'not-allowed'`` lui aussi. La propriété
CALCULE toujours ; le navigateur ne s'en sert simplement jamais quand
l'élément n'est pas la cible du hit-test. L'instrument juste est
``elementFromPoint`` au centre de l'élément (cf. le commentaire de
``_READ``). Sans le témoin, ce probe aurait signé un « vérifié au
navigateur » qui ne mesurait rien.

⚠️ Deux niveaux de preuve, et ils ne valent pas la même chose :

1. ``/bottom-bar`` a une carte « item : disabled » — mesure RÉELLE, sur
   un item rendu par le composant, dans sa page.
2. Le playground n'a **pas** de banc ``/navbar`` ni ``/sidebar``. Pour
   ces deux-là on injecte la chaîne de classes lue dans leur thème et on
   mesure le CSS qu'elle produit. Ça prouve que Tailwind compile bien ces
   utilitaires et que la règle gagne — pas que le composant les émet
   (ça, c'est ``test_disabled_affordance`` et les tests unitaires).

⚠️ **Ce fichier n'est collecté par aucune suite** (``probe_*``, pas
``test_*``) — donc il pourrit en silence, comme tous ses voisins
(memory ``project_probes_rot_silently``). Ce qui EST gardé
automatiquement, c'est la moitié déterministe : le combo de classes
interdit (``test_disabled_affordance``) et la bascule statique/réactif
(``test_nav_item_wiring``). Ce probe garde la moitié qu'aucun test
déterministe ne peut voir — que le curseur PEINT — et il faut le
relancer à la main quand on touche au disabled d'un item de nav.

Lancer :

    py -m tests.audit.probe_nav_disabled_cursor_2026_08_13
"""

from __future__ import annotations

import sys

from bretzel.components.navigation.navbar.theme import NAVBAR_ITEM_THEME
from bretzel.components.navigation.sidebar.theme import SIDEBAR_ITEM_THEME
from tests.audit.harness import audit_server, browser_page

sys.stdout.reconfigure(encoding="utf-8")

# ⚠️ ``getComputedStyle(el).cursor`` NE RÉPOND PAS À LA QUESTION, et le
# témoin de ce probe l'a prouvé avant qu'on s'y fie : il rend
# ``not-allowed`` même sous ``pointer-events: none``. C'est correct — la
# propriété CALCULE, le navigateur ne s'en sert simplement jamais, parce
# que l'élément n'est pas la cible du hit-test.
#
# L'instrument juste est donc ``elementFromPoint`` au CENTRE de
# l'élément : si le point ne renvoie pas l'élément (ou un de ses
# descendants), c'est un ancêtre qui reçoit le survol, et c'est le
# curseur de l'ANCÊTRE qui est peint. « cursor calculé » ET « je suis la
# cible » sont les deux moitiés de la preuve ; une seule ne vaut rien.
_READ = """
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const cs = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  const hit = document.elementFromPoint(r.left + r.width / 2,
                                        r.top + r.height / 2);
  return {
    tag: el.tagName,
    cursor: cs.cursor,
    pointerEvents: cs.pointerEvents,
    opacity: cs.opacity,
    background: cs.backgroundColor,
    hasHref: el.hasAttribute('href'),
    tabindex: el.getAttribute('tabindex'),
    isHitTarget: !!hit && (hit === el || el.contains(hit)),
    hitTag: hit ? hit.tagName : null,
  };
}
"""

_INJECT = """
([cls, id_]) => {
  const el = document.createElement('div');
  el.id = id_;
  el.setAttribute('class', cls);
  el.setAttribute('aria-disabled', 'true');
  el.setAttribute('data-active', 'false');
  el.textContent = 'probe';
  document.body.appendChild(el);
}
"""


def _check(label: str, row: dict | None, failures: list[str]) -> None:
    """Les trois assertions communes aux deux niveaux de preuve."""
    if row is None:
        failures.append(f"{label} : nœud introuvable")
        return
    if row["pointerEvents"] == "none":
        failures.append(
            f"{label} : pointer-events:none sur un disabled STATIQUE — "
            f"le curseur ne peut pas peindre"
        )
    if row["cursor"] != "not-allowed":
        failures.append(
            f"{label} : cursor={row['cursor']!r}, attendu 'not-allowed'"
        )
    if not row["isHitTarget"]:
        failures.append(
            f"{label} : le survol atterrit sur {row['hitTag']}, pas sur "
            f"l'élément — son curseur ne peint donc jamais"
        )


def _resolve(template: str) -> str:
    """Le thème porte ``{bg_color}`` — le composant le résout au rendu."""
    return template.replace("{bg_color}", "primary")


def main() -> int:
    failures: list[str] = []
    with audit_server() as base_url:
        # ── 1. mesure RÉELLE sur le banc bottom_bar ──────────────────
        with browser_page(base_url, "/bottom-bar") as page:
            sel = '[aria-disabled="true"]'
            page.wait_for_selector(sel, timeout=10_000)
            page.hover(sel)
            row = page.evaluate(_READ, sel)
            print("=== /bottom-bar — item désactivé, souris dessus ===")
            print(f"   {row}")
            _check("/bottom-bar", row, failures)
            if row and row["hasHref"]:
                failures.append(
                    "/bottom-bar : href encore présent — l'item navigue"
                )

            # ── 2. les deux thèmes sans banc — classes injectées ─────
            # Même page : le hover de la partie 1 est consommé, et ouvrir
            # un second cycle navigateur pour injecter deux div ne prouve
            # rien de plus.
            for label, theme in (
                ("navbar_item", NAVBAR_ITEM_THEME),
                ("sidebar_item", SIDEBAR_ITEM_THEME),
            ):
                node_id = f"probe-{label}"
                page.evaluate(
                    _INJECT, [_resolve(theme["slots"]["root"]), node_id]
                )
                page.wait_for_timeout(400)  # le JIT dev régénère sa feuille
                page.hover(f"#{node_id}")
                row = page.evaluate(_READ, f"#{node_id}")
                print(f"\n=== {label} (classes injectées, souris dessus) ===")
                print(f"   {row}")
                _check(label, row, failures)

            # ── 3. LE TÉMOIN — la forme d'AVANT le fix ───────────────
            # Sans lui, « cursor: not-allowed » ne prouve rien : peut-être
            # que ce navigateur le peint quoi qu'il arrive. On injecte la
            # chaîne telle qu'elle était (root + pointer-events-none) et on
            # exige que la mesure ÉCHOUE. Un probe dont le témoin passe est
            # un probe qui ne mesure pas ce qu'il croit.
            page.evaluate(
                _INJECT,
                [
                    _resolve(NAVBAR_ITEM_THEME["slots"]["root"])
                    + " aria-disabled:pointer-events-none",
                    "probe-temoin",
                ],
            )
            page.wait_for_timeout(400)
            row = page.evaluate(_READ, "#probe-temoin")
            print("\n=== TÉMOIN — la forme d'avant (root + p-e-none) ===")
            print(f"   {row}")
            if row is None or row["pointerEvents"] != "none":
                failures.append(
                    "témoin : pointer-events n'est pas 'none' — la classe "
                    "d'avant ne s'applique pas, donc la comparaison ne "
                    "prouve rien"
                )
            elif row["isHitTarget"]:
                failures.append(
                    "témoin : l'élément reste la cible du hit-test SOUS "
                    "pointer-events:none — l'hypothèse du diagnostic est "
                    "fausse, il faut rouvrir F1"
                )
            else:
                print(
                    f"   -> le survol atterrit sur {row['hitTag']} : c'est "
                    f"SON curseur qui peint, jamais celui de l'item. "
                    f"(cursor calculé = {row['cursor']!r}, et c'est "
                    f"exactement pourquoi getComputedStyle seul ment.)"
                )

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} ECHEC(S) :")
        for item in failures:
            print(f"   [X] {item}")
        return 1
    print("[OK] curseur not-allowed PEINT, pointeur actif, href retire")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
