"""Gate ratchet — un probe neuf ne réécrit plus le harnais.

``bretzel.probe`` livre les AXES d'une vérification : servir l'app,
ouvrir des fenêtres, attendre l'état, compter les requêtes, balayer,
rendre un verdict. Avant lui, chaque fichier de ``tests/probes/`` les
réécrivait. Mesuré le 2026-09-10, sur 146 fichiers et 21 898 lignes :

==================  =====
marque              fois
==================  =====
``sync_playwright``    75
``def check``          66
``subprocess.Popen``   65
``def wait_server``    49
==================  =====

**Ce que la gate ne demande pas.** Elle ne demande pas de migrer les 146
— c'est la décision de l'utilisateur du 2026-09-10, « pas de migration
de front » : un big-bang sur 21 898 lignes ne se relit pas, et un probe
qu'on réécrit sans le relancer devient un probe vert à tort (il y en a
eu trois, cf. ``project_probes_rot_silently``).

**Ce qu'elle demande.** Deux choses, et c'est le cliquet :

1. **aucun fichier NEUF ne porte ces marques** — un probe écrit après le
   2026-09-10 passe par ``bretzel.probe`` ou justifie explicitement son
   inscription ici ;
2. **les totaux ne remontent jamais.** Un fichier existant peut être
   migré, jamais alourdi.

Les deux versants mordent, et le versant LICITE compte autant : la table
doit mentir dans les deux sens pour être utile, donc un fichier guéri
qu'on oublie d'en retirer rougit aussi. C'est ce versant qui a trouvé les
deux seuls bugs de gate du dépôt.
"""

from __future__ import annotations

import functools
import re

import pytest

from tests.consistency._discovery import (
    PROBES_DIR,
    PROBES_FLOOR,
    ParsedSource,
    parsed_sources,
)

#: Preuve de morsure : contrôle POSITIF — la découverte lit vraiment des
#: fichiers, donc un plafond vert n'est pas un plafond sur zéro.
MUTATION_PROOF = "test_the_sweep_reads_something"


def _scripts() -> list[ParsedSource]:
    """Les scripts de ``tests/probes/`` — probes ET bancs.

    Passe par ``parsed_sources`` plutôt que par un ``glob`` + ``read_text``
    à soi : il mémoïse, lit en ``utf-8-sig``, **lève** sur un fichier
    illisible au lieu de le laisser disparaître, et porte le plancher
    partagé. Une première version de cette gate refaisait les trois, ce
    que ``gates.md`` interdit — « ne redevine JAMAIS comment lire une
    source ».
    """
    return [
        s
        for s in parsed_sources(PROBES_DIR, floor=PROBES_FLOOR)
        if s.path.name.startswith(("probe_", "bench_"))
    ]

#: Les quatre marques du harnais réécrit à la main. Par la FORME, pas par
#: le nom d'un helper : un fichier qui renomme son ``check`` en
#: ``verifier`` n'a pas payé la dette, il l'a déguisée — d'où l'ancrage
#: sur ce qui ne peut PAS changer (l'ouverture de Playwright, le
#: lancement d'un processus) et sur les deux définitions dont le nom est
#: devenu une convention de fait.
MARKS: dict[str, re.Pattern[str]] = {
    "sync_playwright": re.compile(r"\bsync_playwright\s*\("),
    "def check": re.compile(r"^def check\(", re.M),
    "def wait_server": re.compile(r"^def wait_server\(", re.M),
    "subprocess.Popen": re.compile(r"subprocess\.Popen\("),
}

#: Gelé le 2026-09-10 à la livraison de ``bretzel.probe``, puis DESCENDU
#: deux fois : le même jour, `probe_ecole` et `bench_ecole` sont partis
#: avec leur app ; le 2026-09-11, `probe_messagerie` est devenu le
#: PREMIER porté sur le harnais, et il a rendu les quatre marques d'un
#: coup. C'est le versant licite de la gate qui exige la descente — un
#: plafond laissé haut redeviendrait de la place libre.
CEILING: dict[str, int] = {
    "sync_playwright": 73,
    "def check": 64,
    "def wait_server": 47,
    "subprocess.Popen": 63,
}

#: Les fichiers qui portaient au moins une marque ce jour-là. Un nom
#: absent de cet ensemble n'a le droit d'en porter aucune.
FROZEN: frozenset[str] = frozenset({
    "bench_drawer_server_close.py", "bench_file_list.py",
    "probe_anchored.py", "probe_anchored_floor.py", "probe_auth.py",
    "probe_batch1.py", "probe_batch3.py", "probe_boost.py",
    "probe_bottom_bar_placement.py", "probe_calendar.py",
    "probe_calendar_marks.py", "probe_calendar_width.py",
    "probe_card_hover.py", "probe_chart_empty.py", "probe_charts.py",
    "probe_clic.py", "probe_clientevent.py", "probe_combobox.py",
    "probe_combobox_events.py", "probe_combobox_width.py",
    "probe_crm_findings.py", "probe_datatable_filter.py",
    "probe_datatable_pager.py", "probe_dead_transition.py",
    "probe_diagram.py", "probe_dialog.py", "probe_download.py",
    "probe_drawer.py", "probe_dropdown_hover.py",
    "probe_fileupload.py", "probe_flex_grow.py", "probe_grid_min_col.py",
    "probe_hub.py", "probe_kanban.py", "probe_lang.py", "probe_link.py",
    "probe_load_perf.py", "probe_locale.py", "probe_messagerie.py",
    "probe_mobile_overflow.py", "probe_modals.py",
    "probe_nav_progress.py", "probe_notification.py",
    "probe_number_input.py", "probe_number_input_filter.py",
    "probe_oauth_door.py", "probe_overflow_card.py",
    "probe_overlay_bubble.py", "probe_overlay_dual_event.py",
    "probe_overlay_refresh.py", "probe_overlays.py", "probe_pending.py",
    "probe_picker_imperative.py", "probe_picker_size.py", "probe_pwa.py",
    "probe_responsive_props.py", "probe_select.py",
    "probe_select_events.py", "probe_select_position.py",
    "probe_server_events.py", "probe_shell.py", "probe_sidebar.py",
    "probe_sidebar_collapse.py", "probe_sidebar_footer.py",
    "probe_sidebar_scroll.py", "probe_sidebar_trigger.py",
    "probe_slider.py", "probe_slider_click.py", "probe_switch.py",
    "probe_switch_server.py", "probe_table.py", "probe_tabs_url.py",
    "probe_text_align.py", "probe_theme_toggle.py",
    "probe_time_picker_cells.py", "probe_tipiso.py",
    "probe_toggle_resync.py", "probe_tooltip.py", "probe_url_memory.py",
    "probe_value_resync.py", "probe_verbs.py", "probe_video_tracks.py",
})


@functools.lru_cache(maxsize=1)
def _counts() -> dict[str, int]:
    totals = dict.fromkeys(MARKS, 0)
    for script in _scripts():
        for name, rx in MARKS.items():
            totals[name] += len(rx.findall(script.text))
    return totals


def test_the_sweep_reads_something() -> None:
    """Plancher — ancré sur la DÉCOUVERTE, pas sur la population.

    Un plancher qui recompterait depuis sa propre source resterait vert
    le jour où le balayage est débranché
    (``project_gate_floors_must_read_the_gate_source``).
    """
    parsed_sources(PROBES_DIR, floor=PROBES_FLOOR)


def test_no_new_file_rewrites_the_harness() -> None:
    intruders = sorted(
        script.path.name
        for script in _scripts()
        if script.path.name not in FROZEN
        and any(rx.search(script.text) for rx in MARKS.values())
    )
    assert not intruders, (
        "ces probes réécrivent le harnais alors qu'il est livré :\n  "
        + "\n  ".join(intruders)
        + "\n\nUtilise `bretzel.probe` :\n"
        "    from bretzel.probe import probe\n"
        "    with probe(\"mon.module:app\", windows=2) as p:\n"
        "        a, b = p.windows\n"
        "\nIl sert l'app, ouvre les fenêtres, attend l'ÉTAT, compte les\n"
        "requêtes, balaie et rend le verdict. Si ton cas ne rentre pas,\n"
        "c'est le harnais qu'il faut étendre — pas le contourner."
    )


@pytest.mark.parametrize("mark", sorted(MARKS))
def test_the_boilerplate_never_grows(mark: str) -> None:
    measured = _counts()[mark]
    assert measured <= CEILING[mark], (
        f"`{mark}` passe de {CEILING[mark]} à {measured} dans "
        f"tests/probes/. Le harnais est livré : un probe neuf ne le "
        f"réécrit pas."
    )


def test_the_ceiling_does_not_lie() -> None:
    """Le versant LICITE — une dette payée doit descendre le plafond.

    Sans lui, la table resterait un souvenir de 2026-09-10 : verte parce
    que trop haute, donc incapable d'attraper le fichier suivant.
    """
    measured = _counts()
    stale = {m: (CEILING[m], measured[m]) for m in MARKS if measured[m] < CEILING[m]}
    assert not stale, (
        "des marques ont DIMINUÉ — descends `CEILING` plutôt que de laisser "
        f"la table mentir : {stale}"
    )
