"""Le palier d'un anneau de focus est décidé par SA VARIANTE.

Deux paliers, deux intentions, et la répartition est parfaite dès qu'on
regarde la **variante CSS** qui déclenche l'anneau :

``focus:`` / ``focus-within:`` → ``--bz-focus-soft`` (30 %)
    L'anneau reste allumé TOUT le temps où on interagit avec le champ,
    donc il doit être discret — sinon il fatigue.

``focus-visible:`` → ``--bz-focus`` (40 %)
    L'anneau n'apparaît qu'au CLAVIER, il est transitoire, et son travail
    est de se faire voir.

Le cas qui a motivé la gate (2026-08-30)
-----------------------------------------
``ui.link`` écrivait ``focus-visible:ring-{bg_color}/50``. Il était
**seul** : 38 autres slots en ``focus-visible:`` disaient ``/40``, dont
ses deux voisins immédiats d'``actions/``. Rien dans son historique ne
portait de raison — la ligne vient du commit d'écriture initiale de mai
2026, avant qu'aucune convention n'existe.

Ce n'était pas un cas isolé mais le symptôme d'un manque : la valeur se
recopiait d'un voisin, donc elle dérivait dès qu'on recopiait le mauvais
voisin. ``.claude/work/todo.md`` portait d'ailleurs l'écart depuis le
2026-07-14, classé « SUBJECTIF, laissé » faute de règle pour trancher.

⚠️ **Cette gate parlait d'OPACITÉS jusqu'au 2026-08-30**, et elle
s'appelait ``test_focus_ring_opacity_follows_its_variant``. Elle lisait
``ring-{bg_color}/40`` et vérifiait le nombre. La phase 3 du chantier des
jetons a supprimé les gabarits : l'opacité est devenue un **palier**, et
la règle se lit désormais sur son nom. Le fond n'a pas bougé d'un pouce —
même split, même raison, même exception.

Ce que la gate NE fait PAS
---------------------------
Elle n'aplatit pas les deux paliers en un. Le split est **intentionnel**
et c'est justement ce que la mesure a établi ; l'aplatir rendrait les
formulaires pénibles. La gate protège le split, elle ne le supprime pas.

L'exception, et pourquoi elle en est une
-----------------------------------------
``slider:handle`` écrit ``focus-visible:ring-4`` avec le palier **doux**.
C'est le seul ``ring-4`` du catalogue : deux fois la largeur, donc deux
fois la surface de couleur. Il descend d'un palier pour garder le même
poids visuel. La règle est donc énoncée sur le couple (variante,
largeur), et non sur la variante seule — sinon on « corrige » un slot qui
a raison.

Reste hors périmètre l'unique anneau **sans variante de focus** :
``file_upload:dropzone_global_drag`` s'allume quand un fichier est traîné
sur la page. Ce n'est pas un anneau de focus, la règle ne le concerne
pas, et la gate le laisse passer explicitement plutôt que de l'avaler en
silence.
"""

from __future__ import annotations

import re

from tests.consistency._discovery import theme_slot_strings, theme_sources

#: Un anneau qui lit un palier, avec les variantes qui le précèdent.
#:
#: Un anneau écrit en dur (``ring-primary/40``) n'est PAS dans le
#: périmètre : il ne suit aucune couleur de composant.
_RING = re.compile(r"((?:[\w-]+:)*)ring-\(\s*(--bz-focus[a-z-]*)\s*\)")

#: Un anneau plus large qu'un ``ring-2``, dans la même chaîne de classes.
_WIDE_RING = re.compile(r"(?:[\w-]+:)*ring-(\d+)(?![\w-])")

_TRANSIENT = "--bz-focus"       # focus-visible: — clavier seulement
_SUSTAINED = "--bz-focus-soft"  # focus: / focus-within: — allumé en frappe


def expected_step(variants: str, classes: str) -> str | None:
    """Le palier que ce couple (variante, largeur) doit porter.

    ``None`` = hors périmètre, et c'est le seul cas où la gate se tait.
    """
    if "focus-visible" in variants:
        widths = [int(w) for w in _WIDE_RING.findall(classes)]
        # Un anneau large étale la couleur sur deux fois la surface : il
        # rend le même poids visuel un palier plus bas.
        return _SUSTAINED if any(w > 2 for w in widths) else _TRANSIENT
    if "focus" in variants:
        return _SUSTAINED
    return None


def offenders() -> list[str]:
    """Les anneaux dont le palier ne suit pas leur variante."""
    wrong: list[str] = []
    for source in theme_sources():
        for slot, classes in theme_slot_strings(source.text):
            for variants, step in _RING.findall(classes):
                expected = expected_step(variants, classes)
                if expected is not None and step != expected:
                    wrong.append(
                        f"{source.path.parent.name}:{slot} — "
                        f"{variants}ring-({step}), attendu ({expected})"
                    )
    return wrong


def in_scope() -> list[str]:
    """Les anneaux que la règle couvre — la DÉCOUVERTE de la gate."""
    seen: list[str] = []
    for source in theme_sources():
        for slot, classes in theme_slot_strings(source.text):
            for variants, _step in _RING.findall(classes):
                if expected_step(variants, classes) is not None:
                    seen.append(f"{source.path.parent.name}:{slot}")
    return seen


def test_the_sweep_is_not_vacuous() -> None:
    """Le plancher lit la découverte de CETTE gate, pas les fichiers.

    Si ``theme_slot_strings`` cessait d'extraire, ou si le motif d'anneau
    cessait de matcher, ``offenders()`` rendrait une liste vide et
    l'interdiction passerait au vert en ne testant rien. Mesuré le
    2026-08-30, après la phase 3 : **50 anneaux** dans le périmètre.
    """
    seen = in_scope()
    assert len(seen) >= 45, (
        f"Le balayage ne reconnaît plus que {len(seen)} anneau(x) de focus "
        f"({seen}). L'extracteur de slots ou le motif d'anneau a cessé de "
        "matcher — la gate ne teste plus rien."
    )


def test_a_focus_ring_follows_its_variant() -> None:
    wrong = offenders()
    assert not wrong, (
        "Ces anneaux de focus ne portent pas le palier de leur variante :\n  "
        + "\n  ".join(wrong)
        + "\n\n``focus-visible:`` = ``--bz-focus`` : l'anneau n'existe qu'au "
        "clavier, il est transitoire, son travail est de se faire voir.\n"
        "``focus:`` / ``focus-within:`` = ``--bz-focus-soft`` : l'anneau "
        "reste allumé tant qu'on écrit dans le champ, donc il doit rester "
        "discret.\n"
        "Un anneau plus large qu'un ``ring-2`` étale la couleur sur deux "
        "fois la surface et redescend d'un palier (cf. ``slider:handle``)."
    )


def test_the_detector_still_bites() -> None:
    """Mutation, dans les deux sens.

    Le versant qui MORD confirme qu'on attrape la faute réelle ; le
    versant qui ÉPARGNE est celui qui trouve les faux positifs — les deux
    bugs de gate remboursés le 2026-08-19 sont venus de là.
    """
    # ── il mord ────────────────────────────────────────────────────
    assert _RING.findall("focus-visible:ring-2 focus-visible:ring-(--bz-focus)")
    assert expected_step("focus-visible:", "focus-visible:ring-2") == _TRANSIENT
    assert expected_step("focus-within:", "focus-within:ring-2") == _SUSTAINED
    assert expected_step("peer-focus-visible:", "ring-2") == _TRANSIENT

    # ── il épargne ─────────────────────────────────────────────────
    # un anneau écrit en dur ne porte aucune couleur de composant
    assert not _RING.findall("focus-visible:ring-primary/40")
    # un anneau sans variante de focus n'est pas un anneau de focus
    assert expected_step("", "ring-2 ring-(--bz-focus-soft)") is None
    # la largeur, pas le palier : ``ring-4`` autorise le doux au clavier
    assert expected_step("focus-visible:", "focus-visible:ring-4") == _SUSTAINED
    # ``ring-offset-2`` est un ÉCART, pas une largeur d'anneau
    assert not _WIDE_RING.findall("ring-offset-2")
    # une variable qui n'est pas un palier de focus
    assert not _RING.findall("ring-(--bz-solid)")
