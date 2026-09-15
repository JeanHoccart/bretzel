"""Gate — un contrôle lié au serveur peut transmettre TOUTES ses valeurs.

Trois pannes de la même famille, trouvées le 2026-08-19 en construisant
``examples/crm`` (findings 15, 19 et 20 du chantier). Chacune était un
contrôle capable de PORTER une valeur et incapable de l'ENVOYER — et
aucune ne levait, n'avertissait, ni ne laissait de trace :

1. **un fichier.** ``ui.file_upload`` en mode formulaire — son mode par
   DÉFAUT — pose un ``<input type="file">`` dans le ``<form>`` parent.
   Mais htmx ne construit un corps ``FormData`` que si le formulaire
   porte ``hx-encoding`` ; sinon il URL-encode, et un ``File`` n'y
   survit pas. Le handler recevait une chaîne vide. Zéro occurrence de
   ``hx-encoding`` dans tout le dépôt à ce moment-là ;
2. **une sélection multiple.** Sept contrôles portent une valeur qui
   n'est pas un scalaire et la sérialisent en ``JSON.stringify`` dans un
   champ caché — c'est la seule chose qu'un ``<input>`` sait porter.
   Aucune coercition ne la défaisait : un champ ``list`` rangeait la
   CHAÎNE ``'["a","b"]'``, le rendu suivant faisait ``list(...)`` dessus,
   et la bouillie de caractères survivait au rechargement ;
3. **un booléen faux.** Une case décochée ne soumet rien (règle HTML).
   Le ``hx-vals`` qui corrigeait ça n'existe que sur la requête que la
   case tire ELLE-MÊME ; à la soumission du formulaire parent, rien ne
   portait le ``false``, et un réglage booléen se coinçait sur ``True``.

Ce que la gate garde n'est donc pas trois correctifs mais **une seule
propriété** : ce qu'un contrôle affiche, il doit pouvoir le renvoyer.
C'est la moitié « client → serveur » de « UI = f(state) », et elle
échoue toujours en silence — jamais par une exception.

Les trois populations sont **découvertes**, pas listées : les porteurs de
JSON par un balayage des sources, les cases et le fichier par le rendu
réel des composants publics.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.form.form import contains_file_input
from bretzel.core.serialize import serialize
from bretzel.core.tree import Element, FragmentNode, HtmlNode, TextNode
from bretzel.state import SessionState, field
from tests.consistency._discovery import (
    COMPONENTS_DIR,
    parsed_sources,
    public_component_classes,
    rendered_html_of,
)

#: Le plancher du balayage de sources. ``bretzel/components/`` en compte
#: plus de 300 ; le seuil laisse de la place à une réorganisation sans
#: laisser passer un glob cassé.
_COMPONENTS_FLOOR = 150


# ───────────────────────────────────────────────────────────────────────
# 1. Le fichier — un formulaire qui en contient un s'encode en multipart
# ───────────────────────────────────────────────────────────────────────


def file_input_bearing_classes() -> list[type]:
    """Les composants publics qui rendent un ``<input type="file">``."""
    return [
        cls for cls in public_component_classes()
        if (html := rendered_html_of(cls)) and 'type="file"' in html
    ]


def file_input_bearers() -> list[str]:
    return [cls.__name__ for cls in file_input_bearing_classes()]


def test_the_file_sweep_is_not_vacuous() -> None:
    """Le contrôle POSITIF : au moins un composant pose un input fichier.

    Sans lui, la gate resterait verte le jour où ``ui.file_upload`` cesse
    d'en rendre un — c'est-à-dire précisément quand elle devrait rougir.
    """
    assert file_input_bearers(), (
        "aucun composant public ne rend un `<input type=\"file\">` — soit "
        "le balayage est cassé, soit `ui.file_upload` ne pose plus de "
        "champ, et le mode formulaire n'existe plus."
    )


def test_a_form_holding_a_file_declares_multipart() -> None:
    """L'interdiction, sur CHAQUE porteur découvert.

    Pas sur un seul composant écrit à la main : c'est ce qui fait que la
    découverte au-dessus sert à quelque chose plutôt qu'à être comptée.
    """
    from bretzel.components.inputs.form import Form

    for cls in file_input_bearing_classes():
        with render_isolated():
            with Form() as form:
                cls(name="fichier")
            rendered = serialize(form.render())
        assert 'hx-encoding="multipart/form-data"' in rendered, (
            f"un `<form>` contenant un {cls.__name__} n'annonce pas "
            f"`hx-encoding` : htmx URL-encodera le corps, et le fichier "
            f"n'atteindra jamais le handler."
        )
        assert 'enctype="multipart/form-data"' in rendered

    from bretzel.components.inputs.file_upload import FileUpload

    with render_isolated():
        with Form() as form:
            FileUpload(name="fichier")
        html = serialize(form.render())

    assert 'hx-encoding="multipart/form-data"' in html, (
        "le formulaire porte un `<input type=\"file\">` mais n'annonce pas "
        "`hx-encoding` : htmx URL-encodera le corps, et le fichier "
        "n'atteindra jamais le handler — sans erreur, sans trace. C'est le "
        "finding 15 du chantier CRM."
    )
    assert 'enctype="multipart/form-data"' in html, (
        "`enctype` manque : la soumission native (sans htmx) perdrait le "
        "fichier de la même façon."
    )


def test_a_form_without_a_file_stays_urlencoded() -> None:
    """Le versant LICITE — celui qui trouve les faux positifs.

    Encoder TOUS les formulaires en multipart ferait passer l'interdiction
    ci-dessus sans rien réparer, et changerait le chemin de lecture du
    corps pour chaque action de l'app.
    """
    from bretzel.components.inputs.form import Form
    from bretzel.components.inputs.input import Input

    with render_isolated():
        with Form() as form:
            Input(name="titre")
        html = serialize(form.render())

    assert "hx-encoding" not in html and "enctype" not in html, (
        "un formulaire sans fichier annonce un encodage multipart : "
        "l'auto-détection ne détecte plus rien, elle affirme."
    )


def test_the_file_detector_still_bites() -> None:
    """La mutation, dans les deux sens, sur un arbre FABRIQUÉ.

    Le détecteur descend récursivement : un composite pose son champ
    fichier trois ou quatre niveaux sous la racine du formulaire, donc une
    descente qui s'arrêterait au premier niveau redonnerait un formulaire
    URL-encodé sans que rien ne le dise.
    """
    nested = Element(
        tag="div", attrs={}, children=(
            Element(tag="div", attrs={}, children=(
                Element(tag="input", attrs={"type": "file"}, children=()),
            )),
        ),
    )
    licit = Element(
        tag="div", attrs={}, children=(
            Element(tag="div", attrs={}, children=(
                Element(tag="input", attrs={"type": "text"}, children=()),
            )),
        ),
    )
    assert contains_file_input((nested,)), "le détecteur ne descend plus"
    assert not contains_file_input((licit,)), (
        "le détecteur voit un fichier là où il n'y a qu'un champ texte"
    )
    # Les deux autres formes de nœud qu'un rendu produit. ``FragmentNode``
    # groupe sans enveloppe (donc sans ``attrs``), ``HtmlNode`` porte du HTML
    # brut que le framework n'a pas construit. Un fichier caché dans l'une
    # ou l'autre se perdrait exactement de la même façon.
    assert contains_file_input((
        FragmentNode(children=(
            Element(tag="input", attrs={"type": "file"}, children=()),
        )),
    )), "le détecteur ne traverse pas un FragmentNode"
    assert contains_file_input((HtmlNode(html='<input type="file" name="x">'),)), (
        "le détecteur ne regarde pas dans un HtmlNode brut"
    )
    assert not contains_file_input((HtmlNode(html="<p>rien ici</p>"),))
    assert not contains_file_input((TextNode(content='type="file"'),)), (
        "le détecteur prend un TEXTE pour un champ fichier"
    )


# ───────────────────────────────────────────────────────────────────────
# 2. La valeur composite — ce qui part en JSON revient décodé
# ───────────────────────────────────────────────────────────────────────

#: Un porteur de JSON : le composant sérialise une valeur non scalaire
#: dans un champ caché, parce qu'un ``<input>`` ne sait porter qu'une
#: chaîne. Découverts par balayage de sources plutôt que listés — un
#: huitième contrôle composite doit apparaître ici tout seul.
_STRINGIFY = re.compile(r"JSON\.stringify")

#: Les deux emplois de ``JSON.stringify`` qui ne sont PAS des porteurs de
#: formulaire, nommés plutôt que comptés (cf. `gates.md` : « pas un
#: plafond chiffré, une table dit LESQUELS ») :
#:
#: - ``base/_wiring.py`` s'en sert deux fois — un instantané de comparaison
#:   pour savoir si une sélection a changé, et l'alimentation de
#:   l'attribut ``value`` d'un ``<bz-calendar>``. Ni l'un ni l'autre ne
#:   traverse un formulaire.
_NOT_A_FORM_CARRIER = {"base/_wiring.py"}


def stringify_carriers() -> set[str]:
    """Les fichiers de composant qui sérialisent une valeur en JSON."""
    return {
        str(s.path.relative_to(COMPONENTS_DIR)).replace("\\", "/")
        for s in parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR)
        if _STRINGIFY.search(s.text)
    } - _NOT_A_FORM_CARRIER


#: Le plancher de la population. Sept au 2026-08-19 (accordion, combobox,
#: date_range_picker, resizable, select, slider, toggle_group) ; un
#: plancher BORNE, il ne fige pas.
_CARRIERS_FLOOR = 5


def test_the_carrier_sweep_is_not_vacuous() -> None:
    found = stringify_carriers()
    assert len(found) >= _CARRIERS_FLOOR, (
        f"seulement {len(found)} porteur(s) de valeur composite trouvé(s) "
        f"({sorted(found)}) — le balayage ne lit plus les sources, et la "
        f"gate passerait au vert sans rien avoir regardé."
    )


def test_the_declared_non_carriers_are_still_there() -> None:
    """Une table d'exception qui a survécu à sa cause doit PARTIR.

    Sans ce test, ``_NOT_A_FORM_CARRIER`` autoriserait pour toujours un
    fichier qui ne stringifie plus rien — le mode d'échec exact d'une
    allowlist que personne n'audite.
    """
    all_files = {
        str(s.path.relative_to(COMPONENTS_DIR)).replace("\\", "/")
        for s in parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR)
        if _STRINGIFY.search(s.text)
    }
    stale = _NOT_A_FORM_CARRIER - all_files
    assert not stale, (
        f"{sorted(stale)} est déclaré « pas un porteur de formulaire » mais "
        f"ne sérialise plus rien — retire la ligne."
    )


class _Composite(SessionState):
    """L'état qu'un contrôle composite écrit.

    Les DEUX formes d'annotation, et c'est le sujet d'un test à lui seul :
    ``list[str]`` n'est pas ``list``, et c'est la forme que ``state.md``
    donne en exemple. Un décodage qui ne couvrirait que l'annotation nue
    laisserait passer celle que tout le monde écrit.
    """

    choix: list = field(default_factory=list)
    tailles: dict = field(default_factory=dict)
    choix_types: list[str] = field(default_factory=list)
    tailles_typees: dict[str, int] = field(default_factory=dict)


@pytest.mark.parametrize(
    "posted,attendu",
    [
        ('["app","mail"]', ["app", "mail"]),   # toggle_group / select / combobox
        ('["2026-07-20","2026-08-19"]', ["2026-07-20", "2026-08-19"]),  # range
        ("[10.0, 20.0]", [10.0, 20.0]),        # slider(range=True)
        ("[]", []),                            # tout décoché
        ("", []),                              # le champ caché vidé
    ],
)
def test_a_container_field_decodes_what_a_carrier_posts(
    posted: str, attendu: list
) -> None:
    """L'interdiction : ce qui part en JSON revient en conteneur.

    Le cas ``""`` compte autant que les autres : « rien de sélectionné »
    est une valeur que l'utilisateur a CHOISIE. La sauter — comme le fait
    la chaîne vide sur un ``int`` — rendrait un multi-select impossible à
    vider, exactement le jumeau du bug de la case décochée plus bas.
    """
    with render_isolated():
        state = _Composite()
        state.choix = posted
        assert state.choix == attendu, (
            f"le champ a reçu {state.choix!r} au lieu de {attendu!r} — un "
            f"champ conteneur ne décode plus le JSON de son porteur, et le "
            f"rendu suivant le redécoupera en caractères."
        )


def test_a_parameterised_container_decodes_too() -> None:
    """``list[str]`` doit décoder comme ``list``.

    Le versant que la première version de cette gate avait manqué : elle ne
    posait qu'une annotation NUE, et le correctif ne couvrait qu'elle. Or
    ``tags: list[str] = field(default_factory=list)`` est l'exemple de la
    référence — donc le cas courant serait resté cassé, gate verte.
    """
    with render_isolated():
        state = _Composite()
        state.choix_types = '["a","b"]'
        assert state.choix_types == ["a", "b"], (
            f"une annotation paramétrée ne décode pas : {state.choix_types!r}. "
            f"`list[str]` n'est pas `list` — il faut résoudre l'origine."
        )
        state.tailles_typees = '{"a": 1}'
        assert state.tailles_typees == {"a": 1}


#: Comment construire chaque porteur pour qu'il RENDE sa valeur composite.
#: Une table nommée, parce que trois d'entre eux demandent ``multiple=True``
#: plus des options — ce que le bâtisseur partagé ne sait pas poser. Elle est
#: confrontée à la découverte par :func:`test_the_carrier_table_matches_the_sweep`,
#: donc elle ne peut ni rater un porteur neuf, ni garder une entrée périmée.
_CARRIER_BUILDERS: dict = {}


def carrier_builders() -> dict:
    """Import tardif : ces classes tirent la moitié du paquet composants."""
    if _CARRIER_BUILDERS:
        return _CARRIER_BUILDERS
    from bretzel.components.data.accordion import Accordion
    from bretzel.components.inputs.combobox import Combobox
    from bretzel.components.inputs.date_range_picker import DateRangePicker
    from bretzel.components.inputs.select import Select
    from bretzel.components.inputs.slider import Slider
    from bretzel.components.inputs.toggle_group import ToggleGroup
    from bretzel.components.layout.resizable import Resizable

    options = [("a", "A"), ("b", "B")]
    _CARRIER_BUILDERS.update({
        # L'accordéon ne pose son porteur que s'il a un nom ou un
        # gestionnaire de changement — il n'est pas un contrôle de
        # formulaire par défaut. Le ``on_change`` client suffit à le
        # faire apparaître, et c'est la forme sous laquelle il en est un.
        "data/accordion/accordion.py":
            lambda: Accordion(value=["a"], multiple=True, on_change="void 0"),
        "inputs/combobox/combobox.py":
            lambda: Combobox(options=options, value=["a"], multiple=True,
                             name="c"),
        "inputs/date_range_picker/date_range_picker.py":
            lambda: DateRangePicker(name="c"),
        "inputs/select/select.py":
            lambda: Select(options=options, value=["a"], multiple=True,
                           name="c"),
        "inputs/slider/slider.py":
            lambda: Slider(value=[10, 20], range=True, name="c"),
        "inputs/toggle_group/toggle_group.py":
            lambda: ToggleGroup(value=["a"], options=options, multiple=True,
                                name="c"),
        "layout/resizable/resizable.py":
            lambda: Resizable(sizes=[50, 50], name="c"),
    })
    return _CARRIER_BUILDERS


def test_the_carrier_table_matches_the_sweep() -> None:
    """La table de construction ne peut ni rater un porteur, ni pourrir."""
    swept, declared = stringify_carriers(), set(carrier_builders())
    assert not swept - declared, (
        f"porteur(s) de valeur composite non déclaré(s) : "
        f"{sorted(swept - declared)}. Ajoute-les à la table — sinon le test "
        f"suivant ne les exerce pas, et la découverte ne sert qu'à compter."
    )
    assert not declared - swept, (
        f"{sorted(declared - swept)} est déclaré comme porteur mais ne "
        f"sérialise plus rien — retire la ligne."
    )


def test_what_a_carrier_renders_is_what_a_field_can_read() -> None:
    """Le bout-en-bout : la valeur SSR du porteur, relue par un champ.

    C'est ce qui manquait à la première version de cette gate — elle
    comptait les sept porteurs sans jamais en rendre un, et vérifiait le
    décodage sur des chaînes que l'auteur avait écrites lui-même. Une gate
    qui fabrique son propre wire ne mesure que son imagination.
    """
    import html as html_mod

    for path, build in carrier_builders().items():
        with render_isolated():
            rendered = serialize(build().render())
        match = HIDDEN_VALUE.search(rendered)
        assert match, f"{path} ne rend plus de porteur caché avec une valeur"
        posted = html_mod.unescape(match.group(1))
        with render_isolated():
            state = _Composite()
            state.choix = posted
        assert isinstance(state.choix, list), (
            f"{path} poste {posted!r}, qu'un champ `list` range en "
            f"{type(state.choix).__name__} — le rendu suivant le redécoupera."
        )


def test_a_client_state_list_survives_the_htmx_wire() -> None:
    """⚠️ Le magasin client NE voyage PAS en JSON — le cas que la première
    version de ce correctif a CASSÉ.

    htmx sérialise un tableau **élément par élément**
    (``formDataFromObject``), donc un champ ``list`` d'un ``ClientState``
    reçoit ``"change"``, pas ``'["change"]'``. Un décodage qui lève
    là-dessus rend **500** sur toute action d'une page portant un tel état.
    Six états du playground étaient concernés, et les 16 138 tests étaient
    verts — parce qu'aucune gate ne poste un magasin client.
    """
    from bretzel.state import ClientState

    class _Store(ClientState, persist="memory"):
        log: list = field(default_factory=list)

    with render_isolated():
        store = _Store()
        store.log = "change"
        assert store.log == "change", (
            f"un élément nu a été transformé en {store.log!r} — le décodage "
            f"composite ne doit toucher QUE ce qui ressemble à un conteneur."
        )


def test_a_container_field_refuses_garbage() -> None:
    """Le versant LICITE : décoder ne veut pas dire tout accepter.

    Un décodage qui avalerait n'importe quoi rendrait le premier test vert
    en rangeant du n'importe quoi. Le refus doit remonter comme une erreur
    de champ, pas comme un 500 ni comme un silence.

    Mais il ne doit refuser QUE ce qui prétend être un conteneur : le
    versant licite est en bas, et c'est lui qui a manqué la première fois.
    """
    with render_isolated():
        state = _Composite()
        # Ce qui RESSEMBLE à un conteneur et n'en est pas un : le silence
        # serait un rangement de n'importe quoi.
        with pytest.raises(ValueError):
            state.choix = "[cassé"
        with pytest.raises(ValueError):
            state.choix = '{"a": 1}'      # un dict pour un champ list
        # Ce qui n'y ressemble pas passe INCHANGÉ — cf.
        # `test_a_client_state_list_survives_the_htmx_wire` : c'est la
        # forme sous laquelle htmx envoie un élément de tableau, et lever
        # dessus rendait 500.
        state.choix = "change"
        assert state.choix == "change"


def test_a_scalar_field_is_left_alone() -> None:
    """Le second versant licite : un champ ``str`` garde son texte.

    Décoder trop large abîmerait toute app qui stocke du JSON comme du
    texte — une signature, un gabarit, un morceau de configuration.
    """
    class _Texte(SessionState):
        brut: str = field(default='')

    with render_isolated():
        state = _Texte()
        state.brut = '["pas","touché"]'
        assert state.brut == '["pas","touché"]'


# ───────────────────────────────────────────────────────────────────────
# 3. Le booléen — une case décochée transmet quand même son faux
# ───────────────────────────────────────────────────────────────────────

#: La valeur SSR d'un porteur caché. Le garde ``(?<![\w:-])``
#: est load-bearing : sans lui, ``value="`` matche aussi
#: ``bz-attr:value="``, et la gate relit l'EXPRESSION réactive
#: au lieu de la valeur — le même piège que ``_\Z_ID`` dans
#: ``test_example_pages_render``.
HIDDEN_VALUE = re.compile(
    r'<input[^>]*type="hidden"[^>]*(?<![\w:-])value="([^"]*)"'
)

_COMPANION = re.compile(
    r'<input type="hidden" name="(?P<name>[^"]+)" value="false"\s*/?>'
)


def checkable_classes() -> list[type]:
    """Les composants publics qui rendent une case à cocher."""
    return [
        cls for cls in public_component_classes()
        if (html := rendered_html_of(cls)) and 'type="checkbox"' in html
    ]


def test_the_checkable_sweep_is_not_vacuous() -> None:
    found = checkable_classes()
    assert len(found) >= 2, (
        f"seulement {[c.__name__ for c in found]} — Checkbox ET Switch "
        f"doivent être vus ; en dessous, la gate ne garde plus rien."
    )


def test_a_named_checkable_carries_its_false() -> None:
    """L'interdiction : une case liée au serveur porte son compagnon."""
    for cls in checkable_classes():
        with render_isolated():
            html = serialize(cls(name="drapeau", checked=True).render())
        match = _COMPANION.search(html)
        assert match and match.group("name") == "drapeau", (
            f"{cls.__name__}(name=…) n'émet pas son compagnon caché : une "
            f"case décochée ne soumet rien en HTML, donc le `false` "
            f"n'atteindra jamais le serveur et le réglage restera coincé "
            f"sur `True`. C'est le finding 20 du chantier CRM."
        )


def test_a_disabled_checkable_disables_its_companion() -> None:
    """⚠️ Le versant qui INVERSE le bug si on l'oublie.

    Un contrôle désactivé ne soumet rien — ni htmx (``shouldInclude`` saute
    un ``elt.disabled``), ni le navigateur. Un compagnon resté ACTIF serait
    alors le seul à partir, et un réglage désactivé-mais-vrai s'écrirait
    ``False`` au premier enregistrement : exactement la panne que le
    compagnon existe pour empêcher, à l'envers.
    """
    for cls in checkable_classes():
        with render_isolated():
            html = serialize(
                cls(name="drapeau", checked=True, disabled=True).render()
            )
        companion = re.search(
            r'<input type="hidden" name="drapeau"[^>]*>', html
        )
        assert companion, f"{cls.__name__} désactivé n'émet plus de compagnon"
        assert "disabled" in companion.group(0), (
            f"{cls.__name__}(disabled=True) laisse son compagnon ACTIF : il "
            f"partira seul et écrira `False` sur un réglage que personne n'a "
            f"touché."
        )


def test_a_value_list_checkable_has_no_companion() -> None:
    """Le versant LICITE, et il compte : avec un ``value=`` explicite,
    « décoché = absent » EST la bonne sémantique HTML (une liste de
    valeurs cochées). Y poser un compagnon ajouterait un ``"false"``
    fantôme dans la liste."""
    for cls in checkable_classes():
        with render_isolated():
            html = serialize(
                cls(name="etiquettes", value="a", checked=True).render()
            )
        assert not _COMPANION.search(html), (
            f"{cls.__name__}(value=…) émet un compagnon : la sémantique de "
            f"liste de valeurs est cassée."
        )


def test_an_anonymous_checkable_has_no_companion() -> None:
    """Second versant licite : sans ``name=``, rien ne part au serveur —
    un compagnon anonyme serait un champ de formulaire sans destinataire."""
    for cls in checkable_classes():
        with render_isolated():
            html = serialize(cls(checked=True).render())
        assert not _COMPANION.search(html), (
            f"{cls.__name__}() sans nom émet quand même un compagnon."
        )
