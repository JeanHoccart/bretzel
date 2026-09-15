"""Gate navigateur — à ``size=`` égal, un contrôle de formulaire fait UNE
hauteur.

Ce qu'elle garde
-----------------
``ui.input(size="md")`` et ``ui.date_picker(size="md")`` doivent rendre la
même boîte. C'est l'invariant qui rend `size=` utilisable : on met deux
champs côte à côte dans une grille et ils s'alignent, sans que l'appelant
n'ait à mesurer quoi que ce soit.

Il était FAUX jusqu'au 2026-08-23, et faux systématiquement — les cinq
pickers rendaient **2 px de plus** que les quatre contrôles plats, à
chacun des cinq paliers ::

    md :  input 40   select 40   combobox 40   number 40
          date 42    date_range 42   time 42   month 42   week 42

La cause est une divergence de STRUCTURE, pas de valeur. ``ui.input``
pose sa hauteur et sa bordure sur le même élément : en ``box-sizing:
border-box`` (le préréglage Tailwind), ``h-10`` vaut 40 px bordure
comprise. Les pickers posaient la bordure sur le cadre et la hauteur sur
l'``<input>`` à l'intérieur : 40 px d'enfant + 2 px de cadre = 42.

Pourquoi une gate de navigateur, et pas de rendu Python
--------------------------------------------------------
Aucune lecture du HTML n'attrape ça. Les deux thèmes portent le même
token — ``h-10`` est écrit des deux côtés, avec la même valeur, dans la
même table ``sizes``. Un test qui compare des classes voit deux
composants d'accord. Ce sont les 2 px que seul un moteur de rendu
calcule. C'est exactement le mode d'échec de la discipline #3 : j'ai
d'abord conclu « aligné » sur un grep de classes, et c'est l'utilisateur
qui a vu l'écart sur une capture d'écran.

Les boutons en font partie
---------------------------
``ui.button`` et ``ui.icon_button`` ne sont pas de la famille ``inputs``,
mais « un champ, un bouton » est la ligne la plus courante du web
(recherche + valider, filtre + appliquer). Mesuré le 2026-08-23 : ils
s'alignent déjà aux cinq paliers — ils sont ici pour que ça le reste.
``ui.badge`` non : 16/20/24/28/32, délibérément plus petit qu'un
contrôle.

Ce que la découverte garantit
------------------------------
La famille des pickers n'est pas écrite en dur : elle est **découverte**
en cherchant le slot ``input_frame`` dans les thèmes de
``bretzel/components/inputs/``. Un sixième picker hérite donc de la gate
sans que personne n'y pense — et ``test_no_input_dir_is_silently_skipped``
refuse qu'un dossier de ``inputs/`` soit ni couvert ni exclu-avec-raison.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_form_controls_share_one_height.py -q -m browser
"""

from __future__ import annotations

import pathlib

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_INPUTS = _ROOT / "bretzel" / "components" / "inputs"

#: Les cinq paliers. Tous, parce que la panne était présente aux cinq et
#: qu'un seul palier testé aurait laissé les quatre autres dériver.
SIZES = ("xs", "sm", "md", "lg", "xl")

#: Les contrôles PLATS — hauteur et bordure sur le même élément. Ils sont
#: la référence : c'est ``ui.input`` qui définit ce que « md » veut dire,
#: et les trois autres s'accordaient déjà avec lui.
_FLAT = ("input", "select", "combobox", "number_input")

#: Hors famille ``inputs``, et pourtant du même invariant : un bouton
#: posé à côté d'un champ est la ligne la plus courante du web (recherche
#: + valider, filtre + appliquer). Mesuré le 2026-08-23 : ils s'alignent
#: déjà aux cinq paliers — ils sont ici pour que ça le reste, pas parce
#: qu'ils sont cassés.
#:
#: ``ui.badge`` n'y est PAS et n'a pas à y être : 16/20/24/28/32, il est
#: délibérément plus petit qu'un contrôle. Un composant n'entre ici que
#: si son palier est censé donner une hauteur de CHAMP.
_ALSO_ALIGNED = ("button", "icon_button")

#: Les clusters : une barre de segments joints, pas un champ — mais posée
#: dans la même grille de formulaire, donc soumise au même palier. Elle
#: était EXCLUE ici jusqu'au 2026-08-25, avec pour raison « dimensionnée
#: par ses boutons ». C'était la description du bug, pas une raison :
#: `ui.toggle_group(size="md")` rendait 42 px contre 40 pour le
#: `ui.select` voisin, à chacun des cinq paliers. Même cause que les
#: pickers — la bordure du cadre sur la racine, la hauteur sur l'enfant —
#: et c'est encore l'utilisateur qui l'a vue, sur une capture de deux
#: champs voisins.
_CLUSTERS = ("toggle_group",)

#: Ce qui n'a PAS de hauteur de palier, et pourquoi. Sans cette table, un
#: dossier oublié serait indiscernable d'un dossier délibérément hors
#: sujet — le silence qui fait pourrir une gate.
_EXCLUDED: dict[str, str] = {
    "textarea": "multi-ligne : sa hauteur vient de `rows=`, pas du palier",
    "file_upload": "la dropzone se dimensionne par son padding + son contenu",
    "slider": "une piste, pas un champ — aucune bordure de champ",
    "switch": "un interrupteur ; son palier règle la pastille, pas une boîte",
    "checkbox": "une case ; même raison que switch",
    "radio": "un bouton radio ; même raison que switch",
    "signature_pad": "une toile de dessin, hauteur fixée par l'appelant",
    "calendar": "une grille de jours, pas un champ",
    "form": "un conteneur",
    "form_field": "un conteneur (label + aide autour d'un champ)",
}

#: Comment construire chaque sujet. Les clés sont vérifiées contre la
#: découverte par ``test_every_discovered_picker_is_built``.
_BUILDERS = {
    "input": lambda s, i: ui.input(size=s, placeholder="abc", id=i),
    "select": lambda s, i: ui.select(size=s, value="a",
                                     options=[("a", "A")], id=i),
    "combobox": lambda s, i: ui.combobox(size=s, value="a",
                                         options=[("a", "A")], id=i),
    "number_input": lambda s, i: ui.number_input(size=s, value=1, id=i),
    "date_picker": lambda s, i: ui.date_picker(size=s, id=i),
    "date_range_picker": lambda s, i: ui.date_range_picker(size=s, id=i),
    "time_picker": lambda s, i: ui.time_picker(size=s, id=i),
    "month_picker": lambda s, i: ui.month_picker(size=s, id=i),
    "week_picker": lambda s, i: ui.week_picker(size=s, id=i),
    # Livré le 2026-08-30, et resté hors de cette table jusqu'au
    # 2026-08-31 : il était donc DÉCOUVERT — son thème déclare
    # `input_frame` — puis jamais mesuré. C'est exactement le trou que
    # `test_every_discovered_picker_is_built` existe pour montrer, et
    # elle l'a montré au premier `-m browser` de la session.
    "color_picker": lambda s, i: ui.color_picker(size=s, value="#2f5fd0",
                                                 id=i),
    "button": lambda s, i: ui.button("Go", size=s, id=i),
    "icon_button": lambda s, i: ui.icon_button("search", size=s,
                                               aria_label="Chercher", id=i),
    "toggle_group": lambda s, i: ui.toggle_group(size=s, value="a",
                                                 options=[("a", "A"),
                                                          ("b", "B")], id=i),
}


def discovered_pickers() -> set[str]:
    """Les composants à cadre — ceux dont le thème déclare ``input_frame``.

    Lue depuis la SOURCE et non recopiée : c'est ce qui fait qu'un picker
    ajouté demain entre dans la gate tout seul. Cf. la memory
    ``project_gate_floors_must_read_the_gate_source``.
    """
    found = set()
    for theme in sorted(_INPUTS.glob("*/theme.py")):
        if '"input_frame"' in theme.read_text(encoding="utf-8"):
            found.add(theme.parent.name)
    return found


def covered() -> tuple[str, ...]:
    return (tuple(_FLAT) + _ALSO_ALIGNED + _CLUSTERS
            + tuple(sorted(discovered_pickers())))


app = Bretzel(secret_key="u" * 32, title="Bretzel · hauteurs", mode="dev")


@page("/")
def grille() -> None:
    """Chaque contrôle, à chaque palier. Un ``id`` par couple."""
    with ui.container(), ui.vstack(gap="lg"):
        for size in SIZES:
            for name in covered():
                _BUILDERS[name](size, f"{name}--{size}")


app.include(__name__)

#: Mesure la RACINE — la boîte que la grille dispose, donc celle dont
#: l'écart se voit. ``bordered`` porte en plus la hauteur du premier
#: descendant bordé, qui sert de contrôle : pour un picker, la racine doit
#: valoir exactement son cadre (mesuré : elle vaut, le panneau étant
#: ``absolute`` et le porteur ``type=hidden``). Un bouton ``solid`` n'a
#: aucune bordure et rend donc ``null`` — c'est légitime, et c'est
#: pourquoi la mesure ne peut PAS être bâtie sur la chasse à la bordure.
#: Elle l'était : la gate est passée au rouge dès qu'on lui a donné un
#: bouton.
_BOX = """(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const h = n => Math.round(n.getBoundingClientRect().height * 100) / 100;
  const bordered = [el, ...el.querySelectorAll('*')].find(
    n => parseFloat(getComputedStyle(n).borderTopWidth) > 0);
  return {h: h(el), bordered: bordered ? h(bordered) : null};
}"""


@pytest.fixture(scope="module")
def mesures():
    with audit_server(app) as url, browser_page(url, "/") as pg:
        pg.set_viewport_size({"width": 1400, "height": 900})
        pg.wait_for_selector("html.bz-ready", state="attached")
        pg.wait_for_timeout(500)
        yield {
            (name, size): pg.evaluate(_BOX, f"#{name}--{size}")
            for size in SIZES
            for name in covered()
        }


# ───────────────────────────────────────────────────────────────────────
# ① Planchers — la gate voit quelque chose, et ne saute rien
#
# ⚠️ Les trois premiers ne lisent que des fichiers, mais ils ne tournent
# PAS pour autant dans la suite rapide : ``tests/runtime_js/conftest.py``
# marque le dossier entier ``browser``. Le cliquet « un picker neuf n'a
# pas de fabrique » se déclenche donc à la cadence de ``-m browser``, pas
# à chaque ``pytest`` nu. Acceptable ici — un picker sans fabrique fait
# de toute façon rougir la mesure, faute d'``id`` dans la page — mais à
# savoir avant de compter dessus comme sur une gate de cohérence.
# ───────────────────────────────────────────────────────────────────────


def test_the_picker_family_was_discovered() -> None:
    """Le balayage trouve la famille, sinon l'interdiction porte à vide."""
    found = discovered_pickers()
    assert len(found) >= 5, (
        f"seulement {len(found)} composant(s) à cadre découvert(s) sous "
        f"{_INPUTS} : {sorted(found)}. Le slot `input_frame` a été renommé, "
        f"et l'interdiction ci-dessous ne porte plus que sur les contrôles "
        f"plats — qui étaient déjà d'accord entre eux."
    )


def test_every_discovered_picker_is_built() -> None:
    """Un picker découvert mais non construit serait avalé en silence."""
    missing = set(covered()) - set(_BUILDERS)
    assert not missing, (
        f"{sorted(missing)} déclare(nt) un `input_frame` mais n'a/ont pas "
        f"de fabrique dans `_BUILDERS` : le composant serait découvert puis "
        f"jamais mesuré. Ajoute une ligne — c'est le prix d'un picker neuf."
    )


def test_no_input_dir_is_silently_skipped() -> None:
    """Chaque dossier de ``inputs/`` est couvert OU exclu AVEC une raison."""
    dirs = {p.parent.name for p in _INPUTS.glob("*/theme.py")}
    unaccounted = dirs - set(covered()) - set(_EXCLUDED)
    assert not unaccounted, (
        f"{sorted(unaccounted)} n'est ni mesuré ni exclu. Un dossier "
        f"oublié ressemble exactement à un dossier hors sujet : si sa "
        f"hauteur n'est pas un palier, ajoute-le à `_EXCLUDED` avec la "
        f"raison ; sinon donne-lui une fabrique."
    )


@pytest.mark.browser
def test_the_probe_measured_every_subject(mesures) -> None:
    """Plancher de la sonde : chaque sujet a rendu une boîte non nulle.

    Sans ce test, un sélecteur qui ne matche rien rendrait ``None`` pour
    tout le monde et l'égalité serait vraie par vacuité.
    """
    for (name, size), box in mesures.items():
        assert box is not None, (
            f"`ui.{name}(size={size!r})` n'a pas été trouvé dans la page : "
            f"le composant n'a pas rendu, ou son `id=` ne descend plus "
            f"jusqu'à la racine."
        )
        assert box["h"] > 0, f"{name}/{size} rend une boîte de hauteur nulle"


@pytest.mark.browser
def test_a_picker_root_is_exactly_its_frame(mesures) -> None:
    """Contrôle de la sonde : sur un picker, la racine EST le cadre.

    La racine d'un picker enveloppe le cadre, le porteur caché et le
    panneau. Si l'un des deux derniers reprenait de la place — un panneau
    qui cesse d'être ``absolute``, un porteur qui cesse d'être
    ``type=hidden`` — la racine grandirait sans que le champ bouge, et la
    gate accuserait le mauvais coupable. On vérifie donc que les deux
    hauteurs coïncident.

    Les boutons ne sont pas concernés : un ``solid`` n'a pas de bordure.
    """
    for name in sorted(discovered_pickers()):
        for size in SIZES:
            box = mesures[(name, size)]
            assert box["bordered"] is not None, (
                f"`ui.{name}(size={size!r})` n'a plus aucun descendant "
                f"bordé : son cadre a perdu sa bordure, ou la structure a "
                f"changé — la mesure ne porte plus sur ce qu'on croit."
            )
            assert abs(box["bordered"] - box["h"]) < 0.5, (
                f"`ui.{name}(size={size!r})` : la racine fait {box['h']}px "
                f"mais son cadre {box['bordered']}px. Quelque chose d'autre "
                f"que le cadre prend de la place dans la racine (panneau "
                f"remis en flux ? porteur devenu visible ?)."
            )


# ───────────────────────────────────────────────────────────────────────
# ② L'interdiction
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.browser
@pytest.mark.parametrize("size", SIZES)
def test_one_size_means_one_height(mesures, size) -> None:
    hauteurs = {name: mesures[(name, size)]["h"] for name in covered()}
    lo, hi = min(hauteurs.values()), max(hauteurs.values())
    assert hi - lo < 0.5, (
        f"à `size={size!r}`, les contrôles ne font pas la même hauteur — "
        f"{hi - lo:.2f} px d'écart :\n"
        + "\n".join(f"    ui.{n:<20} {h:>7} px"
                    for n, h in sorted(hauteurs.items(), key=lambda kv: kv[1]))
        + f"\n  La cause historique : la hauteur du palier posée sur "
        f"l'`<input>` INTÉRIEUR pendant que le cadre porte la bordure. En "
        f"`border-box`, le cadre vaut alors l'enfant + ses 2 px. La "
        f"hauteur doit vivre sur l'élément QUI PORTE LA BORDURE — c'est ce "
        f"que fait `ui.input`, et c'est lui la référence."
    )


# ───────────────────────────────────────────────────────────────────────
# ③ Le versant licite — la sonde sait aussi voir une différence
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_the_paliers_are_actually_different(mesures) -> None:
    """Contrôle POSITIF, et il n'est pas décoratif.

    « Tout le monde a la même hauteur » serait aussi vrai si la sonde
    lisait toujours le même élément, ou si `size=` n'atteignait plus
    rien. Les cinq paliers doivent donc rendre cinq hauteurs DISTINCTES,
    et croissantes.
    """
    for name in covered():
        suite = [mesures[(name, s)]["h"] for s in SIZES]
        assert len(set(suite)) == len(SIZES), (
            f"`ui.{name}` rend {sorted(set(suite))} pour les cinq paliers : "
            f"deux paliers se confondent, donc `size=` n'atteint plus la "
            f"hauteur. L'égalité mesurée plus haut serait alors vraie sans "
            f"rien prouver."
        )
        assert suite == sorted(suite), (
            f"`ui.{name}` n'est pas croissant en taille : {suite} pour "
            f"{SIZES}."
        )
