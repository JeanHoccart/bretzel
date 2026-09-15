"""Tout ``<script>`` inline d'une page a son empreinte dans la politique.

La dérive que cette gate empêche est précise et silencieuse : quelqu'un
ajoute un quatrième ``<script>`` inline directement dans ``_build_head``
au lieu de le déclarer dans
:func:`~bretzel.render.shell.inline_scripts`. Rien ne casse — tant que la
CSP est désactivée, ce qui est le défaut. Le jour où une app la passe à
``True``, ce script-là est refusé par le navigateur, et comme les deux
premiers sont l'anti-FOUC et la synchro d'écran, le symptôme est une
page qui clignote ou se recharge en boucle, sans une ligne de log
serveur.

C'est exactement la classe de bug que ce dépôt gate plutôt que de
corriger : le fix seul redériverait à la prochaine occasion.

La gate lit une page RENDUE, pas la source. C'est ce qui la rend
insensible à la façon dont le script arrive dans le HTML — un helper, une
f-string, une coque personnalisée, peu importe : s'il est entre deux
balises ``<script>`` sans ``src``, le navigateur exigera son empreinte.
"""

from __future__ import annotations

import re

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.server.security import script_hash

_SECRET = "x" * 32

#: Un ``<script>`` sans ``src=`` — donc dont le CORPS s'exécute, donc
#: dont le navigateur voudra l'empreinte.
_INLINE = re.compile(r"<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>", re.S)


def _app(**kwargs) -> Bretzel:
    app = Bretzel(secret_key=_SECRET, mode="dev", **kwargs)

    @page("/")
    def home() -> None:
        ui.text("ok")

    app.include(home)
    return app


def inline_bodies_and_policy() -> tuple[list[str], str]:
    """La DÉCOUVERTE de cette gate : ce que la page émet + ce qu'on autorise.

    Extraite pour que le plancher lise la même chose que l'interdiction —
    un plancher qui re-rendrait sa propre page resterait vert si celle-ci
    cessait d'être inspectée.
    """
    with TestClient(_app(csp=True)) as client:
        reponse = client.get("/")
    corps = [m.group(1) for m in _INLINE.finditer(reponse.text)]
    return corps, reponse.headers.get("content-security-policy", "")


def unhashed() -> list[str]:
    """Les corps inline dont l'empreinte MANQUE à la politique."""
    corps, politique = inline_bodies_and_policy()
    return [c for c in corps if script_hash(c) not in politique]


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher. Une page sans script inline passerait l'interdiction.

    Quatre, et pas « au moins un » : c'est le compte que la coque émet
    (anti-FOUC, synchro d'écran, thème, et le fournisseur d'icônes depuis
    le 2026-09-13). En perdre un silencieusement serait déjà une dérive.
    """
    corps, politique = inline_bodies_and_policy()
    assert len(corps) == 4, (
        f"la page émet {len(corps)} script(s) inline, pas 4 — si c'est "
        f"voulu, mets à jour ce plancher ET vérifie que "
        f"``inline_scripts`` les déclare tous."
    )
    assert politique, "aucune politique posée : la gate ne mesure rien"


def test_every_inline_script_is_hashed() -> None:
    """L'interdiction."""
    manquants = unhashed()
    assert not manquants, (
        "Ces scripts inline sont dans la page mais leur empreinte n'est "
        "pas dans script-src — sous CSP le navigateur refusera de les "
        "exécuter, sans erreur serveur :\n"
        + "\n".join(f"  {c[:90]!r}" for c in manquants)
        + "\n\nUn script inline se déclare dans "
        "``bretzel.render.shell.inline_scripts``, jamais directement "
        "dans ``_build_head``."
    )


def test_the_detector_still_bites() -> None:
    """La mutation, dans les deux sens.

    Le versant licite compte autant : un détecteur qui attraperait aussi
    les ``<script src=…>`` exigerait l'empreinte de fichiers externes,
    que le navigateur ne hache pas — la gate rougirait pour rien.
    """
    assert _INLINE.search("<script>window.x=1</script>"), (
        "le détecteur ne voit plus un script inline nu"
    )
    assert not _INLINE.search('<script defer src="/a.js"></script>'), (
        "le détecteur attrape un script EXTERNE : son corps est vide et "
        "son empreinte n'a pas à figurer dans la politique"
    )
    corps, politique = inline_bodies_and_policy()
    faux = script_hash(corps[0] + " /*muté*/")
    assert faux not in politique, (
        "un corps modifié garde son empreinte : le hachage ne dépend "
        "donc pas du contenu, et la gate ne prouve rien"
    )


@pytest.mark.parametrize("mode", [True, "report-only"])
def test_both_csp_modes_carry_the_hashes(mode: object) -> None:
    """``report-only`` publie la MÊME politique — sinon l'observation
    mentirait sur ce que le blocage fera."""
    with TestClient(_app(csp=mode)) as client:
        reponse = client.get("/")
    entete = (
        "content-security-policy"
        if mode is True
        else "content-security-policy-report-only"
    )
    politique = reponse.headers[entete]
    for corps in _INLINE.findall(reponse.text):
        assert script_hash(corps) in politique
