"""Gate : le CSS de prod DÉCLARE les dossiers où vivent ses classes.

Tailwind ne compile pas que le CSS d'entrée : il balaie des fichiers pour
savoir quelles classes garder. Sans directive, il ne balaie que le
``cwd`` — le dossier de l'app. Or les classes du framework vivent dans
les ``theme.py`` de ses composants, donc dans le **paquet**.

Tant que le ``cwd`` était la racine du dépôt, le paquet s'y trouvait par
accident. Installé par pip, il n'y est plus. Mesuré le 2026-08-29, ``cwd``
= un dossier d'app quelconque, chemin de prod réel
(``get_or_build_css``) ::

    sans la directive   609 Ko   tabular-nums ABSENT · 16rem ABSENT
    avec                684 Ko   tabular-nums PRESENT · 16rem PRESENT

Ce qui survivait sans elle : la safelist (couleurs, layout, responsive) et
les classes écrites par l'app. Donc une UI **aux bonnes couleurs et sans
mise en forme**, sans une erreur nulle part — le mode de défaillance que
ce dépôt chasse en priorité, parce qu'il ne se voit qu'à l'œil, en prod,
et jamais ici.

La safelist ne pouvait pas rattraper le coup, et c'est le point qui rend
cette gate nécessaire à côté d'elle : la safelist ne clôt que ce que le
scanner ne PEUT pas voir (un ``{bg_color}`` non résolu). ``rounded-md``
est parfaitement visible — à condition qu'on regarde le bon dossier.

**Ce que la gate affirme**, et pourquoi dans ce sens : pas « le CSS cite
le chemin du paquet » (une chaîne vaut ce que vaut sa mise à jour) mais
« chaque ``theme.py`` de composant tombe SOUS une racine déclarée ». Un
composant sorti du paquet un jour, ou une racine rognée, rougit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bretzel.components import (
    dynamic_responsive_classes,
)
from bretzel.theme import Theme, sources, strip_safelist
from bretzel.theme.build import _content_fingerprint, scan_roots
from bretzel.theme.css import _SOURCE_INLINE_RE, _SOURCE_PATH_RE
from bretzel.theme.sources import (
    ENTRY_POINT_GROUP,
    FRAMEWORK_SOURCE_ROOT,
    all_source_roots,
    discovered_source_roots,
)
from tests.consistency._discovery import THEMES_FLOOR, theme_sources

#: Le détecteur, extrait pour être MUTABLE (cf. `gates.md`).
_DECLARED = re.compile(r'^@source "([^"]+)";$', re.M)


def prod_css() -> str:
    """Le CSS que le compilateur de prod ingère — celui de ``lifecycle``."""
    return Theme().generate_css(
        responsive_classes=dynamic_responsive_classes(),
    )


def declared_roots(css: str) -> list[Path]:
    """Les racines que CE CSS déclare, telles qu'un lecteur les lit."""
    return [Path(brut) for brut in _DECLARED.findall(css)]


def orphan_themes(css: str) -> list[str]:
    """Les thèmes de composant qu'AUCUNE racine de ``css`` ne couvre.

    Le détecteur de cette gate, extrait pour être mutable : on peut lui
    passer un CSS fabriqué et vérifier qu'il voit — ou ne voit pas.
    """
    racines = declared_roots(css)
    return [
        source.path.name
        for source in theme_sources()
        if not any(
            racine == source.path or racine in source.path.parents
            for racine in racines
        )
    ]


# ── ① Le plancher — il lit la DÉCOUVERTE, pas une source fraîche ────────
def test_the_declared_roots_are_not_vacuous() -> None:
    """Une racine déclarée qui ne couvre rien passerait ② sans rien dire.

    Le plancher se compte donc SOUS les racines déclarées : débrancher la
    déclaration le fait tomber à zéro. Le compter depuis un ``rglob`` du
    dépôt le laisserait vert (memory ``gate_floors_must_read_the_gate_source``).
    """
    racines = declared_roots(prod_css())
    assert racines, "le CSS de prod ne déclare AUCUNE racine de balayage"
    couverts = {
        source.path
        for source in theme_sources()
        for racine in racines
        if racine == source.path or racine in source.path.parents
    }
    assert len(couverts) >= THEMES_FLOOR, (
        f"{len(couverts)} thèmes de composant sous une racine déclarée, "
        f"plancher {THEMES_FLOOR} — la déclaration ne couvre plus le paquet."
    )


# ── ② L'invariant ───────────────────────────────────────────────────────
def test_every_component_theme_lives_under_a_declared_root() -> None:
    orphelins = orphan_themes(prod_css())
    assert not orphelins, (
        "ces thèmes ne sont sous aucune racine balayée — leurs classes "
        f"statiques manqueront du ``style.css`` de prod : {orphelins}"
    )


# ── ③ L'interdiction — un chemin de disque n'a aucun sens en dev ────────
def test_the_dev_inline_css_declares_no_filesystem_root() -> None:
    """Le compilateur navigateur lit le DOM, pas le disque.

    Lui envoyer un chemin absolu est au mieux ignoré, au pire une erreur
    de compilation DANS la page — et il porterait en prime le chemin
    d'installation du serveur dans chaque page servie.
    """
    inline = strip_safelist(prod_css())
    assert not declared_roots(inline), (
        f"le CSS inliné en dev porte encore {declared_roots(inline)}"
    )
    assert "@source inline(" not in inline, "la safelist non plus n'y a rien à faire"


# ── ④ Le cache suit les racines, sinon il sert du périmé ────────────────
def test_the_fingerprint_follows_a_root_outside_the_cwd(tmp_path: Path) -> None:
    """Sans ça, éditer un thème du paquet ne recompilerait rien.

    C'est exactement le bug du 2026-08-27 (``transition-all`` remplacé,
    rendu inchangé), un cran plus loin : là c'était le ``cwd`` qui n'était
    pas dans la clé, ici c'est le paquet.
    """
    fichier = tmp_path / "theme.py"
    fichier.write_text('CLASSES = "rounded-md"', encoding="utf-8")
    avant = _content_fingerprint([tmp_path])
    fichier.write_text('CLASSES = "rounded-full"', encoding="utf-8")
    assert _content_fingerprint([tmp_path]) != avant

    # Et le versant licite : un fichier dans un dossier élagué ne compte pas.
    ignore = tmp_path / "__pycache__"
    ignore.mkdir()
    (ignore / "theme.py").write_text("x = 1", encoding="utf-8")
    assert _content_fingerprint([tmp_path]) == _content_fingerprint([tmp_path])


def test_scan_roots_prunes_a_root_nested_in_the_cwd() -> None:
    """Le dépôt en développement : ``cwd`` contient le paquet.

    Le parcourir deux fois doublerait le walk sans changer une entrée.
    """
    racines = scan_roots(f'@source "{Path.cwd().as_posix()}/bretzel";\n')
    assert racines == [Path.cwd().resolve()]


# ── ⑤ La preuve que ça mord — sur un CSS FABRIQUÉ, dans les deux sens ──
def test_the_detector_still_bites_on_a_fabricated_css() -> None:
    """Le versant coupable et le versant licite, côte à côte.

    Le premier confirme ce qu'on croyait ; le second est celui qui trouve
    les faux positifs — c'est lui qui a débusqué les deux seuls bugs de
    gate du 2026-08-19 (cf. `gates.md`).
    """
    vrai = prod_css()
    # Coupable : le même CSS, sa déclaration retirée. C'est EXACTEMENT
    # l'état d'avant le correctif, et celui d'un paquet installé par pip.
    ampute = _DECLARED.sub("", vrai)
    assert orphan_themes(ampute), (
        "sans aucune racine déclarée, le détecteur devrait voir TOUS les "
        "thèmes comme orphelins — il n'en voit aucun, donc il ne balaie rien"
    )
    assert len(orphan_themes(ampute)) == len(theme_sources())
    # Licite : la vraie déclaration n'en laisse aucun.
    assert not orphan_themes(vrai)
    # Et une racine PLAUSIBLE mais fausse ne doit pas tromper : c'est le
    # cas où l'on croit avoir déclaré et où le compilateur, lui, ne
    # descendra jamais assez bas.
    voisin = '@source "' + (Path.cwd().parent / "voisin").as_posix() + '";'
    assert orphan_themes(voisin) == orphan_themes(ampute)


def test_the_two_source_forms_do_not_catch_each_other() -> None:
    """Les deux motifs de ``css.py`` partagent le mot ``@source``.

    Les confondre reviendrait à retirer la safelist en croyant retirer
    une racine — ou l'inverse, ce qui republierait le chemin d'install.
    """
    chemin = '@source "C:/site-packages/bretzel";' + chr(10)
    safelist = '@source inline("bg-primary md:gap-6");' + chr(10)
    assert _SOURCE_PATH_RE.search(chemin)
    assert not _SOURCE_PATH_RE.search(safelist)
    assert _SOURCE_INLINE_RE.search(safelist)
    assert not _SOURCE_INLINE_RE.search(chemin)


# ── ⑥ La découverte : un paquet tiers n'a QU'À se déclarer ──────────────
class _Point:
    """Un point d'entrée fabriqué — la forme minimale que lit la découverte."""

    def __init__(self, name: str, module: str) -> None:
        self.name = name
        self.module = module


@pytest.fixture
def declared(monkeypatch: pytest.MonkeyPatch):
    """Installe des points d'entrée fabriqués, et rend la mémoïsation propre.

    ``discovered_source_roots`` est mémoïsée pour la vie du process : sans
    ce nettoyage des deux côtés, le premier test qui la touche figerait sa
    valeur pour tous les suivants — y compris les gates d'à côté.
    """
    def poser(*points: _Point) -> None:
        monkeypatch.setattr(
            sources.metadata, "entry_points",
            lambda **kw: list(points) if kw.get("group") == ENTRY_POINT_GROUP else [],
        )
        discovered_source_roots.cache_clear()

    discovered_source_roots.cache_clear()
    yield poser
    discovered_source_roots.cache_clear()


def test_a_declared_package_reaches_the_sheet(declared) -> None:
    """Le point : ``pip install`` suffit. L'app n'écrit RIEN.

    C'est ce qui sépare cette porte des deux autres qu'on a écartées (un
    kwarg de ``Theme``, une option de config) : le paquet qui PORTE les
    classes est le seul à savoir où elles sont.
    """
    declared(_Point("mes-composants", "tests"))
    racines = all_source_roots()
    assert racines[0] == FRAMEWORK_SOURCE_ROOT, "le framework reste en tête"
    assert any(r.name == "tests" for r in racines), racines
    assert str(Path("tests").resolve().as_posix()) in prod_css()


def test_a_dead_entry_point_does_not_break_the_boot(declared, capsys) -> None:
    """Une app n'est pas responsable des métadonnées d'un tiers.

    Mais le silence n'est pas une option : les classes de ce paquet
    manqueraient en prod, et rien d'autre ne le dirait.
    """
    declared(_Point("desinstalle", "ce_module_nexiste_pas_du_tout"))
    assert discovered_source_roots() == ()
    assert "WARN" in capsys.readouterr().out


def test_the_discovery_order_is_stable(declared) -> None:
    """L'ordre des points d'entrée suit le ``sys.path``, donc rien.

    Or ces racines entrent dans le CSS, dont l'empreinte NOMME le fichier
    compilé en cache : un ordre instable donnerait deux empreintes pour un
    même environnement, donc une recompilation de deux secondes à chaque
    démarrage.
    """
    a, b = _Point("a", "tests"), _Point("b", "examples")
    declared(a, b)
    premier = discovered_source_roots()
    declared(b, a)
    assert discovered_source_roots() == premier
    assert list(premier) == sorted(premier)


def test_the_entry_point_group_is_the_written_one() -> None:
    """Le nom du groupe est une API PUBLIQUE, écrite chez des tiers.

    Le renommer casse leur ``pyproject.toml`` sans qu'aucun autre test de
    ce dépôt ne s'en aperçoive — ce littéral est la seule alarme.
    """
    assert ENTRY_POINT_GROUP == "bretzel.scan_roots"
