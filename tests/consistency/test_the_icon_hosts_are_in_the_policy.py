"""Les hôtes qu'iconify interroge sont tous dans ``connect-src``.

``<iconify-icon>`` va chercher chaque jeu d'icônes à distance au premier
usage, et les hôtes sont câblés **dans le fichier vendoré**, pas dans un
réglage qu'on contrôle. :data:`~bretzel.server.security.ICON_API_ORIGINS`
les recopie ; cette gate vérifie que la copie dit encore la vérité.

Ce qu'elle empêche : une montée de version d'iconify qui changerait ou
ajouterait un hôte. Sous CSP, la conséquence est que **toutes les icônes
de toutes les pages disparaissent** — et comme les deux hôtes
secondaires ne servent que si le premier échoue, en oublier un donnerait
une panne intermittente, celle qu'on ne reproduit jamais.

Le fichier vendoré est un CACHE DE PROJET (``.bretzel/vendor/``,
téléchargé par ``python -m bretzel.render.vendor``), pas une source
committée. La gate ne peut donc pas TOUJOURS le lire — mais elle ne se
laisse pas devenir vide pour autant : le plancher affirme la forme de la
constante dans tous les cas, et seul le versant qui confronte le fichier
réel est conditionné à sa présence.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bretzel.server.security import ICON_API_ORIGINS, build_policy

#: Le cache que ``bretzel.render.vendor`` remplit.
_VENDOR_DIR = Path(__file__).resolve().parents[2] / ".bretzel" / "vendor"

#: Un hôte d'API dans le JS minifié. On cherche la forme complète
#: (schéma + hôte) pour ne pas confondre avec un nom de collection.
_HOTE = re.compile(r"https://api\.[a-z0-9.-]+")


def vendored_iconify() -> Path | None:
    """Le fichier iconify rapatrié, si le cache a été rempli."""
    trouves = sorted(_VENDOR_DIR.glob("iconify-icon.min.*.js"))
    return trouves[0] if trouves else None


def hosts_in_the_file() -> set[str]:
    """La DÉCOUVERTE : les hôtes réellement câblés dans le fichier livré."""
    fichier = vendored_iconify()
    if fichier is None:
        return set()
    return set(_HOTE.findall(fichier.read_text("utf-8-sig")))


def test_the_constant_is_not_empty() -> None:
    """Plancher, valable même sans le cache vendor.

    Une constante vidée par mégarde rendrait la politique silencieusement
    plus stricte, et la gate d'à côté passerait (aucun hôte à comparer).
    """
    assert len(ICON_API_ORIGINS) >= 3, (
        f"ICON_API_ORIGINS n'a plus que {len(ICON_API_ORIGINS)} hôte(s) : "
        f"iconify en câble trois (un principal, deux replis)."
    )
    assert all(o.startswith("https://") for o in ICON_API_ORIGINS)


def test_the_policy_carries_them() -> None:
    """Ils doivent finir dans ``connect-src``, pas seulement exister."""
    politique = build_policy(inline_bodies=(), script_urls=())
    connect = next(
        d for d in politique.split("; ") if d.startswith("connect-src ")
    )
    for hote in ICON_API_ORIGINS:
        assert hote in connect, (
            f"{hote} est déclaré mais absent de connect-src — les icônes "
            f"qu'il sert disparaîtront sous CSP."
        )


def test_no_host_in_the_shipped_file_is_missing() -> None:
    """L'interdiction, contre le fichier RÉEL."""
    fichier = vendored_iconify()
    if fichier is None:
        pytest.skip(
            "cache vendor absent — lance ``python -m bretzel.render.vendor``. "
            "Le plancher au-dessus reste vérifié."
        )
    trouves = hosts_in_the_file()
    assert trouves, (
        f"aucun hôte d'API trouvé dans {fichier.name} : le détecteur ne "
        f"lit plus ce fichier, la gate ne mesure rien."
    )
    manquants = trouves - set(ICON_API_ORIGINS)
    assert not manquants, (
        f"iconify interroge {sorted(manquants)}, absent(s) de "
        f"ICON_API_ORIGINS. Sous CSP les icônes servies par ces hôtes ne "
        f"se chargeront pas — et si c'est un repli, la panne sera "
        f"intermittente. Ajoute-les dans bretzel/server/security.py."
    )


def test_the_detector_still_bites() -> None:
    """La mutation, dans les deux sens."""
    assert _HOTE.findall('a="https://api.iconify.design"') == [
        "https://api.iconify.design"
    ]
    # Le versant licite : un nom de collection ou un chemin ne doit pas
    # être pris pour un hôte, sinon la gate exigerait d'autoriser des
    # origines qui n'existent pas.
    assert not _HOTE.findall('icon="lucide:home"')
    assert not _HOTE.findall('"/_bretzel/vendor/iconify-icon.min.js"')
