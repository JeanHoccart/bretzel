"""``ui.image`` : la boîte tient-elle quand l'URL casse ?

C'est LA revendication du composant — celle qui justifie qu'il n'ait ni
prop ``fallback=`` ni prop ``skeleton=`` : le fond de l'image est déjà
les deux états. Elle est écrite dans le docstring, dans
``bretzel describe``, et dans le banc.

Et elle ne tient qu'à deux classes de thème (``bg-muted/30`` + le
``aspect-*`` du ratio). Personne ne casserait ça exprès ; quelqu'un
« nettoierait » le thème en trouvant le fond décoratif, et les deux
comportements disparaîtraient sans qu'un seul test SSR bronche — le HTML
émis serait toujours un ``<img>`` parfaitement valide.

Aucune suite non-navigateur ne peut répondre : il faut qu'un vrai moteur
tente le chargement, échoue, et qu'on mesure ce qui reste à l'écran.

Run : ``py -m pytest tests/runtime_js/test_image_box_survives_a_broken_url.py -q -m browser``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

#: L'image du banc ``/image`` dont l'URL n'existe pas, adressée par son
#: ``alt`` — stable, et lisible dans le diff si le banc bouge.
_BROKEN_ALT = "Cette image ne se chargera pas"

_MEASURE = """
(alt) => {
  const el = document.querySelector(`img[alt="${alt}"]`);
  if (!el) return {error: 'image introuvable sur /image'};
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return {
    width: Math.round(r.width),
    height: Math.round(r.height),
    ratio: r.height ? r.width / r.height : 0,
    background: cs.backgroundColor,
    // 0 prouve que le chargement a VRAIMENT échoué : sans ça, le test
    // pourrait passer sur une image qui se charge et ne rien mesurer.
    naturalWidth: el.naturalWidth,
    complete: el.complete,
  };
}
"""


def test_a_broken_url_keeps_its_reserved_box() -> None:
    with audit_server() as base_url:
        with browser_page(base_url, "/image") as page:
            m = page.evaluate(_MEASURE, _BROKEN_ALT)

    assert "error" not in m, m

    # 1. Le chargement a bien échoué — sinon on ne mesure rien d'utile.
    assert m["complete"] is True
    assert m["naturalWidth"] == 0, (
        "L'image de test se charge : le banc ne pointe plus vers une URL "
        f"cassée, donc ce test ne prouve plus rien. Mesuré : {m}"
    )

    # 2. Et pourtant elle occupe toujours sa place.
    assert m["width"] > 0 and m["height"] > 0, (
        "La boîte s'est effondrée sur une URL cassée — le contenu d'en "
        f"dessous remonte, et la page saute. Mesuré : {m}"
    )

    # 3. Au ratio déclaré (le banc la rend en ``ratio="video"`` = 16/9).
    assert m["ratio"] == pytest.approx(16 / 9, rel=0.02), (
        "La place réservée ne respecte plus le ratio déclaré — c'est tout "
        f"l'intérêt de la prop. Mesuré : {m}"
    )

    # 4. Avec un fond visible : c'est lui qui EST le fallback.
    bg = m["background"]
    assert bg not in ("transparent", "rgba(0, 0, 0, 0)"), (
        "Le fond de l'image a disparu. C'est lui le skeleton ET le "
        "fallback — sans lui, une URL cassée laisse un trou, et le "
        "composant devrait alors porter une vraie prop fallback=. "
        f"Mesuré : {m}"
    )
