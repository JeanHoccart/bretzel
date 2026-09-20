"""Gate : chaque paquet dit ce qu'il fait, et l'arbre est LU, pas listé.

Ce qu'elle garde, et pourquoi ça vaut une gate
-----------------------------------------------
``bretzel describe bretzel.components.inputs`` marche depuis le
2026-09-02, et il marche parce qu'il lit la docstring que le dossier
porte. Ça tient tant que les dossiers en portent une.

Mesuré le jour de la pose : **117 paquets, 117 docstrings, zéro
manquant.** L'invariant existe donc DÉJÀ dans le dépôt — cette gate ne
demande rien de neuf, elle empêche seulement le 118ᵉ d'arriver muet.

Le contraste avec la table écrite à la main
--------------------------------------------
``introspect/modules.py`` classe sept modules symbole par symbole. C'est
plus riche, et c'est écrit à la main : un paquet ajouté n'y entre que si
quelqu'un y pense. L'arbre, lui, ne peut pas rater un dossier — il le
lit. Les deux se complètent, et il faut les deux : la table dit à QUOI
SERT un symbole, l'arbre dit CE QUI EXISTE.

C'est la leçon du skill ``bretzel-api``, supprimé le 2026-08-01 pour
avoir nommé deux composants inexistants et en avoir omis six : un
catalogue recopié dérive plus vite qu'il ne sert. La différence n'est
pas le soin qu'on y met, c'est de savoir QUI est la source.
"""

from __future__ import annotations

from bretzel.introspect.package_tree import describe_package, walk

#: Preuve de morsure : contrôle POSITIF — le lecteur rend encore des
#: docstrings réelles, et l'arbre encore des paquets.
MUTATION_PROOF = "test_the_reader_still_reads_something"

#: Le compte au moment de la pose. Plancher, pas plafond : le dépôt
#: grandit. Une chute de moitié est plus probablement un lecteur cassé
#: qu'une suppression réelle.
_PACKAGES_AT_FREEZE = 117

#: La longueur en dessous de laquelle une docstring ne dit rien. Trois
#: mots, en gros — de quoi refuser ``"""ui."""`` sans exiger un roman.
_MIN_SUMMARY = 12

#: Les symboles publics de premier niveau lus au gel, tous modules
#: confondus. C'est le CRAN DU DESSOUS, ajouté le 2026-09-02 : le
#: panneau de ``examples/docs`` paraissait vide parce qu'il s'arrêtait
#: aux dossiers, dont 73 docstrings sur 117 sont des talons — alors que
#: 97 % des symboles portent une vraie première ligne.
_SYMBOLS_AT_FREEZE = 608

#: La part documentée au gel (592/608). Plancher : elle peut monter, et
#: si elle descend beaucoup c'est qu'on ajoute du public sans le dire.
_MIN_DOCUMENTED = 0.90

#: Les docstrings de paquet de la forme ``« icon_button component. »`` —
#: générées, pas écrites. **Cliquet : ce nombre ne remonte pas.** On ne
#: demande à personne de réécrire les 73 d'un coup, mais le 74ᵉ est
#: refusé : c'est ce qui a fait paraître l'arbre vide.
_STUBS_AT_FREEZE = 73


def test_the_reader_still_reads_something() -> None:
    """Plancher, ancré sur la DÉCOUVERTE de cette gate.

    Sans lui, un lecteur qui rendrait zéro paquet ferait passer
    l'interdiction au vert en ne regardant rien.
    """
    noeuds = walk(describe_package())
    assert len(noeuds) >= _PACKAGES_AT_FREEZE // 2, (
        f"seulement {len(noeuds)} paquets vus contre {_PACKAGES_AT_FREEZE} "
        f"au gel — le balayage de l'arbre est probablement cassé. Si la "
        f"chute est réelle, baisse ce plancher DANS le même commit."
    )
    # …et il doit rendre de vraies docstrings, pas des chaînes vides :
    # un lecteur qui rendrait ``""`` partout passerait le compte et
    # échouerait l'interdiction, ce qui pointerait le mauvais coupable.
    assert any(n.doc for n in noeuds), (
        "aucune docstring lue sur AUCUN paquet — c'est le lecteur qu'il "
        "faut réparer, pas les paquets."
    )


def test_every_package_describes_itself() -> None:
    """Un paquet sans docstring est invisible à ``describe``."""
    muets = sorted(n.name for n in walk(describe_package()) if not n.doc)
    assert not muets, (
        f"{muets} n'ont pas de docstring de paquet.\n"
        f"  Ce n'est pas une exigence de style : ``bretzel describe "
        f"<paquet>`` LIT cette docstring, donc un paquet muet devient un "
        f"trou dans la seule liste du framework qui ne peut pas mentir.\n"
        f"  Une phrase suffit — ce que ce dossier fait, et pourquoi il "
        f"existe séparément de son voisin."
    )


def test_no_summary_is_a_placeholder() -> None:
    """Une docstring d'un mot passe la gate au-dessus sans rien dire.

    ⚠️ Le seuil est délibérément BAS (12 caractères). Il n'est pas là
    pour juger la qualité — impossible mécaniquement — mais pour
    attraper le cas où l'on satisfait la gate précédente par un
    ``\"\"\"inputs.\"\"\"``. Au-delà, c'est la revue qui décide.
    """
    trop_courts = sorted(
        (n.name, n.summary)
        for n in walk(describe_package())
        if n.doc and len(n.summary) < _MIN_SUMMARY
    )
    assert not trop_courts, (
        f"docstrings trop courtes pour dire quoi que ce soit : "
        f"{trop_courts}. Une phrase, pas un mot."
    )


def _tous_les_symboles() -> list:
    """Les symboles publics de tout l'arbre, à plat."""
    return [
        sym
        for noeud in walk(describe_package())
        for mod in noeud.modules
        for sym in mod.symbols
    ]


def test_the_symbol_reader_still_reads_something() -> None:
    """Plancher du CRAN DU DESSOUS — sans lui, il pourrait rendre zéro.

    Le lecteur de symboles est le seul étage qui porte du texte réel
    (97 % documentés, contre 38 % de vraies docstrings de dossier).
    S'il rendait des tuples vides, l'arbre resterait parfaitement vert et
    la page de doc redeviendrait le squelette qu'elle était.
    """
    symboles = _tous_les_symboles()
    assert len(symboles) >= _SYMBOLS_AT_FREEZE // 2, (
        f"seulement {len(symboles)} symboles publics lus contre "
        f"{_SYMBOLS_AT_FREEZE} au gel — le lecteur AST est probablement "
        f"cassé. Si la chute est réelle, baisse ce plancher DANS le même "
        f"commit."
    )
    documentes = sum(1 for s in symboles if s.summary)
    part = documentes / len(symboles)
    assert part >= _MIN_DOCUMENTED, (
        f"{documentes}/{len(symboles)} symboles publics documentés "
        f"({part:.0%}), sous le plancher de {_MIN_DOCUMENTED:.0%}.\n"
        f"  Ce n'est pas une exigence de style : c'est CE texte que rend "
        f"la page ``/tree`` de ``examples/docs``, faute de quoi elle "
        f"n'affiche qu'une liste de noms."
    )
    # …et il doit distinguer les deux genres. Un lecteur qui ne verrait
    # que les fonctions passerait les deux comptes ci-dessus.
    genres = {s.kind for s in symboles}
    assert genres == {"function", "class"}, (
        f"genres vus : {genres} — le lecteur AST en rate un."
    )


def test_package_stubs_only_shrink() -> None:
    """Cliquet sur les docstrings de dossier auto-générées.

    ⚠️ **Ce n'est pas un test de qualité rédactionnelle**, qu'on ne peut
    pas mécaniser. C'est la forme EXACTE que produit un talon —
    ``« icon_button component. »``, le nom du dossier suivi d'un mot —
    et elle passe la gate de longueur juste au-dessus (21 caractères
    pour un seuil de 12). C'est comme ça que 73 dossiers ont pu se
    déclarer sans rien dire.

    Le cliquet ne demande pas de les réécrire : il refuse le 74ᵉ.
    """
    talons = sorted(
        n.name
        for n in walk(describe_package())
        if n.summary.lower().rstrip(".").endswith(" component")
    )
    assert len(talons) <= _STUBS_AT_FREEZE, (
        f"{len(talons)} docstrings de paquet sont des talons « X "
        f"component. », contre {_STUBS_AT_FREEZE} au gel — le cliquet ne "
        f"remonte pas.\n"
        f"  Une phrase qui dit ce que le dossier fait, et pourquoi il "
        f"existe séparément de son voisin.\n"
        f"  Nouveaux : {sorted(set(talons))[-3:]}"
    )


#: Les fins de résumé qu'une PHRASE ne produit jamais. Une virgule ou
#: une conjonction en dernier mot ne peut venir que d'une coupure.
_FINS_IMPOSSIBLES = (
    ",", ";", "and", "or", "the", "a", "an", "of", "to", "with", "for",
    "et", "ou", "le", "la", "les", "un", "une", "de", "des", "du", "que",
    "qui", "dans", "sur", "par", "en", "son", "sa", "ses",
)


def test_a_summary_is_never_cut_mid_sentence() -> None:
    """Un résumé tronqué ne se lit pas comme court : il se lit comme FAUX.

    Le lecteur a d'abord pris la première *ligne*, et 68 des 592 résumés
    de symboles — 11 % — se terminaient en plein milieu d'une phrase,
    parce que leur auteur avait replié à 79 colonnes ::

        Stable 8-char hex digest used to compress IDs (and other stable

    Rien à l'écran ne disait qu'il en manquait la moitié. Le premier
    PARAGRAPHE les répare toutes les 68 pour la même longueur médiane
    (59 caractères) — mais rien n'empêche de revenir à la ligne, et cette
    gate est ce qui le dirait.

    ⚠️ Elle juge la FORME, pas le fond : un dernier mot qui est une
    virgule ou une conjonction ne peut pas venir d'une phrase finie.
    """
    coupes = [
        (mod.name, sym.name, sym.summary)
        for noeud in walk(describe_package())
        for mod in noeud.modules
        for sym in mod.symbols
        if sym.summary
        and sym.summary.rstrip().rstrip(".").split()[-1].lower().rstrip(",;")
        in _FINS_IMPOSSIBLES
    ] + [
        ("(paquet)", n.name, n.summary)
        for n in walk(describe_package())
        if n.summary
        and n.summary.rstrip().rstrip(".").split()[-1].lower().rstrip(",;")
        in _FINS_IMPOSSIBLES
    ]
    assert not coupes, (
        f"{len(coupes)} résumé(s) se terminent sur un mot qui n'achève "
        f"aucune phrase — ils sont TRONQUÉS :\n"
        + "\n".join(f"  {m}.{n} → {r!r}" for m, n, r in coupes[:8])
        + "\n  Le lecteur doit prendre le premier PARAGRAPHE, pas la "
        "première ligne."
    )
