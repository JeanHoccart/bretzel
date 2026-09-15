"""Lire l'état d'un overlay — sans se tromper de propriété CSS.

Pourquoi ce module existe (mesuré au navigateur le 2026-08-19)
--------------------------------------------------------------
Quatre probes testaient ``getComputedStyle(el).display === 'none'`` pour
savoir si un Dialog / Drawer était fermé. **Un modal ne se ferme pas en
``display``** : il garde ``display: flex`` et part en
``visibility: hidden ; opacity: 0`` (mesuré sur les deux dialogs de
``bench_dialog``, ouverts comme fermés). Conséquences observées :

- ``wait_for_function("… .display === 'none'")`` n'aboutissait jamais →
  **30 s de timeout, puis une stacktrace Playwright** au lieu d'un
  diagnostic. C'est ce qui faisait « rougir » ``probe_dialog`` et
  ``probe_drawer`` ;
- l'inverse, ``display !== 'none'``, est vrai DÈS LE REPOS : le probe
  croyait avoir attendu l'ouverture alors qu'il n'avait rien attendu.

Et le piège n'est pas uniforme, c'est ce qui le rend coûteux : un
panneau de Tooltip, lui, se cache **bien** en ``display: none``. Une
règle « ne jamais tester display » serait donc fausse aussi.

La sortie de ce piège est de ne pas deviner la propriété : les overlays
publient leur état sur ``data-open``, qui est la même donnée que celle
dont le composant dérive son style. On lit ça, et on retombe sur les
propriétés calculées seulement pour ce qui n'en porte pas.
"""

from __future__ import annotations

_STATE_JS = """
(arg) => {
  const nodes = document.querySelectorAll(arg.selector);
  const el = nodes[arg.index];
  if (!el) return 'absent';
  // ``data-open`` est la source du composant — le style en DÉCOULE.
  const flag = el.getAttribute('data-open');
  if (flag !== null) return flag === 'true' ? 'open' : 'closed';
  const cs = getComputedStyle(el);
  const hidden = cs.display === 'none'
              || cs.visibility === 'hidden'
              || cs.opacity === '0';
  return hidden ? 'closed' : 'open';
}
"""


def overlay_state(page, selector: str, index: int = 0) -> str:
    """``"open"`` / ``"closed"`` / ``"absent"`` pour l'overlay visé."""
    return page.evaluate(_STATE_JS, {"selector": selector, "index": index})


def wait_overlay(page, selector: str, state: str, *, index: int = 0,
                 timeout: int = 5000) -> str:
    """Attendre ``state``, puis RENDRE l'état réel — sans lever.

    Un ``wait_for_function`` qui expire jette une stacktrace Playwright à
    la place du diagnostic ; ici l'appelant reçoit ce qu'il y avait
    vraiment et l'écrit dans son ``check``.
    """
    import contextlib

    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    js = f"(arg) => ({_STATE_JS})(arg) === {state!r}"
    with contextlib.suppress(PlaywrightTimeout):
        page.wait_for_function(js, arg={"selector": selector, "index": index},
                               timeout=timeout)
    return overlay_state(page, selector, index)
