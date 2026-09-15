"""Blocs de rendu du chapitre RUNTIME — les mirrors de ``runtime_surface``.

Même contrat que :mod:`examples.docs.lib.blocks` : un mirror ne connaît
aucun contenu, il rend ce que l'introspection lui donne. Ajouter une
directive, un magic ou un ``$bz.<nom>`` au framework le fait apparaître
ici au prochain rendu, sans toucher à ce fichier.

Séparé de ``blocks.py`` le temps du chantier « surface d'API » en cours —
cf. la note de chantier de :mod:`examples.docs.lib.runtime_surface`. Au
repli, :func:`grouped_tables` et :func:`section` ont vocation à servir
les autres chapitres : ``client_algebra_mirror`` (blocks.py) réinline
aujourd'hui le corps exact de la première, et six pages de ``features/``
réécrivent la seconde à la main.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager

from bretzel import ui

from examples.docs.lib.runtime_surface import (
    binding_order,
    bundle_facts,
    describe_directives,
    describe_magics,
    describe_runtime_api,
    describe_runtime_modules,
)


@contextmanager
def section(title: str, intro: str = ""):
    """Une carte de chapitre : titre, chapeau, puis le corps.

    Les pages du dossier écrivent ce préambule à la main, à quatre
    niveaux d'indentation ; ``cheatsheet.py`` l'avait déjà extrait pour
    son propre usage.
    """
    with ui.card():
        with ui.vstack(gap="sm"):
            ui.heading(title, level=2)
            if intro:
                ui.text(intro, color="muted", size="sm")
            yield


def grouped_tables(
    ops: Sequence,
    columns: Iterable,
    row: Callable[[object], dict[str, str]],
) -> None:
    """Une table par catégorie, précédée de son libellé et de son compte.

    ``ops`` arrive déjà trié par catégorie (les ``describe_*`` s'en
    chargent), donc les groupes sont contigus et ``groupby`` suffit.
    """
    for category, group in itertools.groupby(ops, key=lambda o: o.category):
        items = list(group)
        with ui.vstack(gap="xs"):
            with ui.hstack(align="center", gap="sm"):
                ui.text(category, weight="bold", size="sm")
                ui.badge(str(len(items)), color="muted", variant="outline")
            ui.table(columns=list(columns), rows=[row(o) for o in items],
                     size="sm")


def runtime_modules_mirror() -> None:
    """Les modules du bundle, dans l'ordre de chargement, avec leur poids
    réel. Le socle et les moteurs de composants sont séparés parce que ce
    n'est pas la même nature de code : le premier est le runtime, le
    second est ce que les composants y déposent."""
    facts = bundle_facts()
    with ui.hstack(gap="sm", wrap=True, align="center"):
        ui.badge(f"{facts['modules']} modules", color="info", variant="soft")
        ui.badge(f"socle : {facts['core_modules']} fichiers, "
                 f"{facts['core_lines']} lignes", color="primary", variant="soft")
        ui.badge(f"bundle : {facts['bundle_bytes'] // 1024} Ko",
                 color="muted", variant="outline")

    grouped_tables(
        describe_runtime_modules(),
        [
            ui.column("file", label="Fichier"),
            ui.column("title", label="Rôle"),
            ui.column("lines", label="Lignes", align="right"),
        ],
        lambda m: {"file": m.name, "title": m.title, "lines": str(m.lines)},
    )


def directives_mirror() -> None:
    """Les directives, groupées par ce qu'elles GARANTISSENT (pas par le
    module qui les implémente).

    Deux colonnes de texte, et elles n'ont pas le même statut : la
    « garantie » est une glose éditoriale, le « contrat » est la
    définition que le socle donne de sa propre directive, lue dans
    ``protocol.py``. Afficher les deux évite que la seconde soit
    recouverte en silence par la première.
    """
    ops = describe_directives()
    unwired = [o for o in ops if not o.implemented]
    if unwired:
        with ui.card(color="error"):
            ui.text(
                "Déclarée côté Python, jamais branchée dans le runtime : "
                + ", ".join(o.name for o in unwired)
                + ". Rien ne lève à l'exécution — une directive à moitié "
                "vivante est simplement ignorée par le navigateur.",
                size="sm",
            )

    grouped_tables(
        ops,
        [
            ui.column("syntax", label="Écrit dans le HTML"),
            ui.column("doc", label="Ce qu'elle garantit"),
            ui.column("contract", label="Déclarée par"),
        ],
        lambda o: {
            "syntax": o.syntax,
            "doc": o.doc,
            "contract": (f"{o.constant} — {o.protocol_note}"
                         if o.implemented
                         else f"{o.constant} — ⚠ non branchée"),
        },
    )

    order = binding_order()
    if order:
        with ui.vstack(gap="xs"):
            ui.text("Ordre de câblage sur un même élément", weight="bold",
                    size="sm")
            ui.text(" → ".join(order), classes="font-mono", size="sm",
                    color="muted")
            ui.text(
                "Lu dans le moteur. Il n'est pas cosmétique : bz-ref est "
                "câblé en premier (un voisin peut le lire), bz-init en "
                "dernier (le nœud est entièrement câblé quand il tourne).",
                color="muted", size="xs",
            )


def magics_mirror() -> None:
    """Les variables disponibles dans une expression ``bz-*``, lues à leur
    source exacte : la liste d'arguments du compilateur d'expressions."""
    grouped_tables(
        describe_magics(),
        [
            ui.column("name", label="Variable"),
            ui.column("doc", label="Contenu"),
        ],
        lambda m: {"name": m.name, "doc": m.doc},
    )


def runtime_api_mirror() -> None:
    """La surface de l'objet global ``$bz``, module par module.

    La colonne « expose » est lue dans le littéral JS : c'est ce qui
    empêche qu'un onzième helper reste invisible parce que la prose en
    listait dix.

    Le privé (préfixe ``_``) n'est pas masqué mais réduit à un compte et
    une liste : le lire dit ce que le framework se réserve, sans laisser
    croire que c'est une API.
    """
    ops = describe_runtime_api()
    public = [o for o in ops if o.public]
    private = [o for o in ops if not o.public]

    grouped_tables(
        public,
        [
            ui.column("name", label="Nom"),
            ui.column("doc", label="Ce que c'est"),
            ui.column("members", label="Expose"),
            ui.column("module", label="Défini dans"),
        ],
        lambda o: {
            "name": f"$bz.{o.name}",
            "doc": o.doc,
            "members": ", ".join(o.members) or "—",
            "module": o.module,
        },
    )

    if private:
        with ui.accordion(collapsible=True):
            with ui.accordion_item(
                "private",
                label=f"{len(private)} entrées internes (préfixe _)",
                icon="lock",
            ):
                ui.text(
                    "Le framework se les réserve : elles changent sans "
                    "préavis et aucun composant ne doit les appeler. Deux "
                    "font exception et sont invoquées depuis le HTML rendu "
                    "par le serveur ($bz._resolveIcon, $bz._tick) — le "
                    "préfixe dit « le framework écrit ça », pas « personne "
                    "ne l'appelle ».",
                    color="muted", size="sm",
                )
                ui.text(
                    "  ".join(f"$bz.{o.name}" for o in private),
                    classes="font-mono", size="xs", color="muted",
                )
