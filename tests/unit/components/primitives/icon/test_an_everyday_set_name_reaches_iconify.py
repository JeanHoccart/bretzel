"""``set="phosphor"`` draws: its everyday name becomes the prefix Iconify knows.

Iconify knows Phosphor as ``ph``. ``phosphor:heart`` answered 404 from
the relay and from every upstream host, so ``ui.icon(..., set="phosphor")``
drew nothing at all, and the empty 404 page of the relay kept the icon
page's network busy forever (the component audit timed out on ``icon``).
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.icon import Icon
from bretzel.core.serialize import serialize


def _icon_attr(icon: Icon) -> str:
    out = serialize(icon.render())
    return out.split('icon="', 1)[1].split('"', 1)[0]


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({"name": "heart", "set": "phosphor"}, "ph:heart"),
    ({"name": "heart", "set": "phosphor", "icon_style": "bold"}, "ph:heart-bold"),
    ({"name": "phosphor:moon"}, "ph:moon"),
    ({"name": "heart", "set": "ph", "icon_style": "fill"}, "ph:heart-fill"),
    ({"name": "heart", "set": "tabler", "icon_style": "filled"}, "tabler:heart-filled"),
    ({"name": "heart"}, "lucide:heart"),
    ({"name": "mdi:home"}, "mdi:home"),
])
def test_the_prefix_is_iconify_s(kwargs: dict, expected: str) -> None:
    with render_isolated():
        icon = Icon(**kwargs)
    assert _icon_attr(icon) == expected
