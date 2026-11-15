"""Le balayage pèse ce que ``visible=`` cache, et les zones redessinées cachées.

Mesuré sur Orga (2026-11-14) : la moitié de la page cachée par le
``ClientState`` de la coque, et une liste compacte redessinée à chaque fil
ouvert, panneau fermé — vert partout ailleurs.

⚠️ On exerce la DÉCISION, pas le navigateur, comme
``test_the_sweep_sees_clipped_content`` : le JavaScript qui mesure tourne
pour de vrai à chaque probe ; ici on lui fabrique sa sortie. Les deux
versants : lourd → rouge et nommé ; un menu fermé, une petite branche,
une zone redessinée visible → vert.
"""

from __future__ import annotations

from typing import Any

from bretzel.probe._hidden import judge_loads, judge_redraws


def _verdicts(judge: Any, seen: Any) -> list[tuple[bool, str]]:
    out: list[tuple[bool, str]] = []
    judge(lambda _name, ok, detail: out.append((bool(ok), str(detail))), "f1", seen)
    return out


def _load(page: int, by_visible: int, hidden: int | None = None) -> dict[str, Any]:
    return {
        "page": page,
        "hidden": by_visible if hidden is None else hidden,
        "byVisible": by_visible,
        "biggest": [{"bytes": by_visible, "by": "$bz.state.disposition.panneau === 'mail'",
                     "what": "div", "text": "Boîte de réception"}] if by_visible else [],
    }


def test_a_heavy_hidden_branch_is_red_and_named() -> None:
    # La coque d'Orga : 170 Ko cachés sur 338.
    [(ok, detail)] = _verdicts(judge_loads, [("/", _load(338_000, 170_000))])
    assert not ok
    assert "disposition.panneau" in detail and "Boîte de réception" in detail


def test_a_quarter_of_a_small_page_is_red() -> None:
    [(ok, _)] = _verdicts(judge_loads, [("/", _load(40_000, 12_000))])
    assert not ok


def test_light_or_closed_content_is_green() -> None:
    # Une petite branche, et 60 Ko de dialogues fermés : pas un visible=.
    verdicts = _verdicts(judge_loads, [("/", _load(200_000, 3_000, hidden=63_000)),
                                       ("/vide", _load(10_000, 0))])
    assert [ok for ok, _ in verdicts] == [True, True]


def test_a_zone_redrawn_hidden_is_red_and_counted() -> None:
    hidden = {"zone": "refresh_ab12cd34", "by": "$bz.state.disposition.ouvert",
              "bytes": 9_000, "text": "Fils"}
    shown = {"zone": "refresh_00000000", "by": None, "bytes": 4_000, "text": "Lecture"}
    [(ok, detail)] = _verdicts(judge_redraws, [hidden, shown, hidden])
    assert not ok
    assert "2 of 3" in detail and "refresh_ab12cd34 ×2" in detail


def test_zones_redrawn_in_view_are_green() -> None:
    shown = {"zone": "refresh_00000000", "by": None, "bytes": 4_000, "text": "Lecture"}
    assert [ok for ok, _ in _verdicts(judge_redraws, [shown, shown])] == [True]
    assert [ok for ok, _ in _verdicts(judge_redraws, [])] == [True]
