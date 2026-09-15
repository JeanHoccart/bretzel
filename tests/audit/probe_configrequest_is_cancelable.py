"""Probe — ``htmx:configRequest`` est-il ANNULABLE en htmx 2.0.4 ?

Toute la garde runtime « un contrôle ``aria-disabled`` ne poste pas »
repose sur cette seule question. On la mesure AVANT d'écrire la garde,
plutôt que de lire la doc et d'espérer : le dépôt charge htmx depuis un
CDN (``render/shell.py``), donc la version réellement exécutée est celle
du navigateur, pas celle d'un fichier vendu qu'on pourrait relire.

Le probe fabrique deux boutons ``hx-post`` identiques, en annule UN
depuis ``configRequest``, et compte les ``htmx:beforeRequest``. Le second
bouton est le **témoin** : sans lui, « zéro requête » pourrait tout aussi
bien vouloir dire « htmx n'a jamais vu le clic ».

    py -m tests.audit.probe_configrequest_is_cancelable
"""

from __future__ import annotations

import sys

from tests.audit.harness import audit_server, browser_page

sys.stdout.reconfigure(encoding="utf-8")

_SETUP = """
() => {
  window.__probe = { before: [], config: [] };

  const mk = (id, blocked) => {
    const b = document.createElement('button');
    b.id = id;
    b.setAttribute('hx-post', '/_bz_probe_never_exists');
    b.setAttribute('hx-swap', 'none');
    if (blocked) b.setAttribute('data-probe-block', 'true');
    b.textContent = id;
    document.body.appendChild(b);
    window.htmx.process(b);
    return b;
  };

  document.body.addEventListener('htmx:configRequest', (e) => {
    window.__probe.config.push(e.detail.elt.id);
    if (e.detail.elt.closest('[data-probe-block]')) e.preventDefault();
  });
  document.body.addEventListener('htmx:beforeRequest', (e) => {
    window.__probe.before.push(e.detail.elt.id);
  });

  mk('probe-blocked', true);
  mk('probe-control', false);
}
"""


def main() -> int:
    with audit_server() as base_url:
        with browser_page(base_url, "/bottom-bar") as page:
            page.wait_for_function("() => !!window.htmx", timeout=10_000)
            page.evaluate(_SETUP)
            # Clic DOM, pas clic pointeur : les boutons injectes sont
            # recouverts par le layout de la page, et ce que htmx ecoute
            # est l'evenement, pas le curseur.
            page.evaluate("() => document.getElementById('probe-blocked').click()")
            page.evaluate("() => document.getElementById('probe-control').click()")
            page.wait_for_timeout(600)
            probe = page.evaluate("() => window.__probe")

    print(f"   configRequest vu pour : {probe['config']}")
    print(f"   beforeRequest vu pour : {probe['before']}")

    failures = []
    if "probe-blocked" not in probe["config"]:
        failures.append(
            "htmx n'a jamais émis configRequest pour le bouton bloqué — "
            "le probe ne mesure rien"
        )
    if "probe-control" not in probe["before"]:
        failures.append(
            "TÉMOIN : le bouton NON bloqué n'a pas posté non plus. « Zéro "
            "requête » ne prouve donc rien sur l'annulation"
        )
    if "probe-blocked" in probe["before"]:
        failures.append(
            "preventDefault sur configRequest n'annule PAS la requête en "
            "htmx 2.0.4 — la garde runtime doit passer par un autre canal"
        )

    print("\n" + "=" * 60)
    if failures:
        for item in failures:
            print(f"   [X] {item}")
        return 1
    print("[OK] preventDefault sur configRequest ANNULE la requete "
          "(et le temoin, lui, part bien)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
