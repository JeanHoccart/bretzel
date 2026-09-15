"""Le theme studio EXPORTE tout ce qu'il règle — et sous les vrais noms.

Ce que cette gate ferme
-----------------------

Le studio a deux sorties, et une seule se voit. La première est la page
elle-même, repeinte en direct par ``repaint_effect()`` ; la seconde est
le bloc de code du bas, produit par ``export_expression()``, qui est LA
raison d'être de la page — on règle pour repartir avec.

Jusqu'au 2026-08-31, ces deux sorties ne portaient pas la même chose.
Les vingt-deux couleurs allaient dans les deux. Les cinq curseurs —
trois familles de rayon, le trait, la densité — n'allaient que dans la
première. On réglait donc un rayon, on le VOYAIT changer sous ses yeux,
on copiait le code, et le rayon n'y était pas.

Rien ne pouvait le dire : la sortie restait un ``Theme(...)`` valide, et
son défaut est une absence. C'est le mode d'échec que ce dépôt paie le
plus cher — plausible, silencieux, et découvert chez l'utilisateur.

Pourquoi la découverte lit le STORE
------------------------------------

Le store ``Studio`` EST la liste de ce que la page règle : un curseur
sans champ ne se retient pas d'un rendu à l'autre, donc il n'existe pas.
Ancrer là plutôt que sur une liste écrite ici rend la gate vraie pour le
prochain réglage sans qu'on y touche — c'est la même mécanique que
``test_foreground_algebra_is_mirrored``.
"""

from __future__ import annotations

import inspect
import re

import pytest

from bretzel.theme import Theme
from examples.playground.features import theme_studio

#: Preuve de morsure : le lecteur de mots-clés du gabarit, sur ses DEUX
#: versants. Un plancher dit que la population n'est pas vide ; il ne dit
#: rien du détecteur, et c'est le détecteur qui peut cesser de voir.
MUTATION_PROOF = "test_the_template_reader_still_bites"

#: Les curseurs, c'est-à-dire tout ce qui n'est pas une couleur. C'est ce
#: sous-ensemble-là qui manquait à l'export, donc il a son propre
#: plancher : les couleurs se comptent EXACTEMENT (cf.
#: :func:`test_the_knob_set_is_non_trivial`), et sans ce second seuil une
#: régression qui retirerait les cinq curseurs d'un coup laisserait la
#: population globale d'aplomb.
_SLIDER_FLOOR = 5


def knobs() -> list[str]:
    """Les champs du store, découverts par le socle d'état.

    ``_all_fields()`` est privé et c'est assumé ici : c'est la même
    lecture que ``bretzel/introspect/state.py`` et que
    ``test_a_runtime_seeded_state_still_has_its_python_class``, et
    ``dataclasses.fields`` ne marche pas — un ``ClientState`` n'est pas
    une dataclass, il a sa métaclasse.
    """
    return sorted(theme_studio.Studio._all_fields())


def color_fields() -> set[str]:
    """Les champs qui portent une couleur — les deux modes."""
    return {
        prefix + name
        for name, *_ in theme_studio.SLOTS
        for prefix in ("", "d_")
    }


_KNOBS = knobs()
_COLORS = color_fields()
_SLIDERS = [k for k in _KNOBS if k not in _COLORS]
_EXPORT = theme_studio.export_expression()
_REPAINT = theme_studio.repaint_effect()
_RESET = theme_studio.reset_expression()


def test_the_knob_set_is_non_trivial() -> None:
    """Plancher sur la DÉCOUVERTE, pas sur le fichier.

    Compter les lignes de ``theme_studio.py`` ne dirait rien : c'est la
    résolution store↔export qui peut casser en silence.

    Le versant couleurs se vérifie EXACTEMENT et non par un seuil : leur
    nombre est déjà connu de ``SLOTS``, donc un plancher chiffré serait
    un second nombre à tenir à la main, qui dériverait au prochain slot
    ajouté.
    """
    absents = sorted(_COLORS - set(_KNOBS))
    assert not absents, (
        f"le store `Studio` ne porte plus {absents}, que `SLOTS` "
        f"déclare — la page ne peut plus régler ces couleurs, et la "
        f"boucle ci-dessous ne les vérifierait plus."
    )
    assert len(_SLIDERS) >= _SLIDER_FLOOR, (
        f"{len(_SLIDERS)} curseur(s) hors couleurs (plancher "
        f"{_SLIDER_FLOOR}) — ce sont EUX qui manquaient à l'export, et "
        f"les perdre de vue rendrait cette gate vide sur son propre "
        f"sujet."
    )
    assert len(_EXPORT) > 500, "`export_expression()` est quasi vide."
    oublies = sorted(set(_KNOBS) - set(theme_studio.SHIPPED_DEFAULTS))
    assert not oublies, (
        f"`SHIPPED_DEFAULTS` ne couvre pas {oublies}, que le store règle. "
        f"La classe lit cette table pour ses défauts, donc un champ absent "
        f"lèverait à l'import — mais un champ EN TROP y passerait, et la "
        f"remise à zéro écrirait alors un signal que personne ne lit."
    )
    intrus = sorted(set(theme_studio.SHIPPED_DEFAULTS) - set(_KNOBS))
    assert not intrus, (
        f"`SHIPPED_DEFAULTS` porte {intrus}, qui ne sont pas des champs du "
        f"store : « Réinitialiser » écrirait dans le vide."
    )


@pytest.mark.parametrize("knob", _KNOBS)
def test_every_knob_reaches_the_exported_code(knob: str) -> None:
    """Chaque champ réglé doit se lire dans l'expression exportée."""
    assert theme_studio.path(knob) in _EXPORT, (
        f"le studio règle `{knob}` mais ne l'exporte pas.\n"
        f"  Le curseur bougera la page et disparaîtra du code copié : "
        f"la sortie reste un `Theme(...)` valide, simplement amputée, "
        f"donc rien à l'écran ne le dira.\n"
        f"  Répare `export_expression()` dans "
        f"`examples/playground/features/theme_studio.py`."
    )


@pytest.mark.parametrize("knob", _KNOBS)
def test_every_knob_also_repaints_the_page(knob: str) -> None:
    """Le versant LICITE, et il a déjà mordu dans l'autre sens.

    Une gate qui n'exigerait que l'export laisserait passer l'inverse
    exact du bug d'origine : un curseur exporté que la page ne repeint
    pas. Le studio serait alors muet là où il doit montrer, ce qui est
    aussi grave — c'est ce qui est arrivé au foreground le 2026-08-30.
    """
    assert theme_studio.path(knob) in _REPAINT, (
        f"le studio règle `{knob}` mais ne repeint rien avec : le "
        f"curseur bougera sans effet visible."
    )


#: Le lecteur de mots-clés du gabarit. Sorti en constante parce qu'il est
#: le seul DÉTECTEUR de ce fichier — le reste cherche des sous-chaînes
#: connues — et qu'un détecteur se prouve, donc il se partage entre la
#: règle et sa preuve.
_KWARG = re.compile(r"\\n    (\w+)=")


def test_the_template_reader_still_bites() -> None:
    """Les deux versants du seul détecteur de ce fichier.

    ``_KWARG`` cherche une FORME — quatre espaces après un saut de ligne
    échappé — donc il peut cesser de voir sans que rien ne rougisse : un
    simple reformatage d'``export_expression()`` suffirait, et
    :func:`test_the_exported_keywords_are_real_theme_parameters`
    passerait alors en ne vérifiant plus aucun mot-clé. C'est la
    pathologie que `gates.md` nomme « une gate qui cherche un NOM peut
    être vide sans le dire ».
    """
    licite = "'Theme(\\n    semantic={\\n' + x + '\\n    },\\n    stroke=\"'"
    assert set(_KWARG.findall(licite)) == {"semantic", "stroke"}, (
        "le lecteur ne reconnaît plus le gabarit d'export."
    )
    # Le versant qui ÉPARGNE : un `=` dans une VALEUR émise n'est pas un
    # paramètre. Sans ce contre-cas, élargir le motif à `(\w+)=` tout
    # court ferait remonter du bruit comme des kwargs inexistants, et la
    # gate rougirait sur un export CORRECT — le pire des deux échecs,
    # parce qu'il pousse à débrancher la règle.
    assert not _KWARG.findall("'--spacing: ' + v + 'rem; }\"'"), (
        "le lecteur prend un `=` de valeur pour un paramètre."
    )


def test_the_exported_keywords_are_real_theme_parameters() -> None:
    """Le code exporté doit s'exécuter — pas seulement exister.

    Cherche les ``<mot>=`` que le gabarit émet et exige que chacun soit
    un paramètre de ``Theme.__init__``. Sans ça, renommer un paramètre du
    framework laisserait le studio produire un extrait qui lève
    ``TypeError`` à la première ligne collée, et aucun test du framework
    ne regarde ce que cette page ÉCRIT.
    """
    emitted = set(_KWARG.findall(_EXPORT))
    assert emitted, (
        "aucun paramètre trouvé dans le gabarit d'export — le format a "
        "changé, et cette gate ne vérifie plus rien."
    )
    accepted = set(inspect.signature(Theme.__init__).parameters)
    unknown = sorted(emitted - accepted)
    assert not unknown, (
        f"le studio exporte {unknown}, que `Theme.__init__` n'accepte "
        f"pas : le code copié lèvera `TypeError`.\n"
        f"  Paramètres acceptés : {sorted(accepted - {'self'})}"
    )


@pytest.mark.parametrize("knob", _KNOBS)
def test_every_knob_can_also_be_reset(knob: str) -> None:
    """Le troisième versant : ce qui se règle doit pouvoir se DÉRÉGLER.

    ``Studio`` est ``persist="local"``, donc un réglage survit à tout —
    y compris à un changement du thème livré. Sans une remise à zéro
    exhaustive, la page ment sur les défauts du framework, et c'est ce
    qui s'est produit : elle affichait un rose saisi des semaines plus
    tôt pendant que le défaut était un indigo (2026-09-13).

    Un bouton qui remet TOUT sauf un curseur est pire qu'aucun bouton :
    il a l'air de marcher. D'où un contrôle par champ.
    """
    assert theme_studio.path(knob) in _RESET, (
        f"le studio règle `{knob}` mais ne le remet pas : après un clic "
        f"sur « Réinitialiser », ce curseur gardera la valeur saisie et la "
        f"page prétendra montrer les défauts du framework."
    )


def test_the_reset_restores_the_shipped_values() -> None:
    """Et il remet les valeurs du FRAMEWORK, pas celles du studio.

    Les deux peuvent diverger sans rien casser : le studio recopie les
    hexadécimaux des défauts dans ses propres champs. Le jour où la
    palette livrée bouge et pas cette copie, « Réinitialiser » ramènerait
    à un thème qui n'existe plus nulle part — un troisième état, ni le
    réglage de l'utilisateur ni le défaut réel.
    """
    livre = Theme().get_palette()
    ecarts = [
        f"{nom}: studio={valeur} framework={attendu}"
        for nom, valeur in theme_studio.SHIPPED_DEFAULTS.items()
        if (attendu := _shipped_hex(livre, nom)) is not None
        and valeur != attendu
    ]
    assert not ecarts, (
        "les défauts du studio ne sont plus ceux du framework :\n  "
        + "\n  ".join(ecarts)
        + "\n\nLe bouton « Réinitialiser » ramènerait donc à un thème qui "
        "n'existe nulle part."
    )


def _shipped_hex(palette: object, champ: str) -> str | None:
    """L'hexadécimal livré pour un champ de couleur du studio, ou ``None``.

    ``None`` pour les curseurs (rayons, trait, densité) : ceux-là ne sont
    pas des couleurs, et leur accord avec le framework se mesure ailleurs
    (``test_the_exported_density_reaches_the_stylesheet``).
    """
    mode = "dark" if champ.startswith("d_") else "light"
    nom = champ.removeprefix("d_")
    if nom not in {slot for slot, *_ in theme_studio.SLOTS}:
        return None
    return palette.resolve(nom, mode).bg_hex  # type: ignore[attr-defined]


def test_the_exported_density_reaches_the_stylesheet() -> None:
    """La densité sort en ``spacing=``, et ce paramètre émet vraiment.

    Elle sortait par ``css="@theme { --spacing: … }"`` jusqu'au
    2026-09-13, faute de paramètre à elle. Les deux formes marchent — d'où
    l'intérêt de garder un test ici plutôt que de faire confiance au
    renommage : ce que ce fichier protège n'est pas la SYNTAXE de l'export
    mais le fait que le réglage arrive dans la feuille. Un export qui
    nomme un paramètre inexistant lèverait (c'est
    :func:`test_the_exported_keywords_are_real_theme_parameters`) ; un
    export qui nomme le bon paramètre pendant que l'émetteur a disparu
    serait un no-op SILENCIEUX, et c'est celui-là qu'on ferme.
    """
    assert "spacing=" in _EXPORT, (
        "l'export ne porte plus `spacing=` : la densité réglée à l'écran ne "
        "part nulle part."
    )
    assert "--spacing: 0.3rem" in Theme(spacing="0.3rem").generate_css(), (
        "`Theme(spacing=…)` n'émet plus le jeton : tout ce que le studio "
        "exporte est accepté à la construction et sans effet."
    )
