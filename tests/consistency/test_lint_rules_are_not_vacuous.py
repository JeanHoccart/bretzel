"""Gate : les règles de `bretzel.lint` attrapent, et n'attrapent QUE ça.

Une règle de lint a deux façons d'être inutile, et une seule se voit :
elle peut ne rien attraper (silencieuse), ou tout attraper (elle sera
désactivée à la première session). Les gates de ce dépôt vérifient
d'habitude le premier sens ; ici il faut les deux, parce que la règle
tourne sur **du code qu'on n'a pas écrit** — CLAUDE.md règle 8 : « qu'elle
rougisse sur un cas fabriqué ne dit rien de son taux de faux positifs sur
le corpus réel ».

Le corpus réel, c'est `examples/` : 322 fichiers qui exercent toute la
surface publique, et que `test_examples_pass_real_kwargs` garde honnêtes.
Un faux positif s'y verrait immédiatement.

Ce que ce fichier a changé le 2026-08-16
-----------------------------------------

Il était écrit **pour une règle** : un `_PROBE` unique, `_MUST_FLAG` /
`_MUST_NOT_FLAG` au niveau module, et le test de corpus câblé sur
`kwargs_rule.RULE`. Une sixième règle arrivait donc dans un jeu de gates
qui ne pouvait pas la voir — et la copier aurait reproduit exactement ce
que `0701d2c5` a défait (« la gate portait la règle ; elle ne porte plus
que son corpus »).

La table `_PROBES` porte maintenant un cas fabriqué **par règle**, et
`test_every_rule_declares_a_probe` en fait un cliquet : une règle neuve ne
peut plus entrer dans `STATIC` sans déclarer ce qu'elle doit attraper ET
ce qu'elle doit épargner.

⚠️ **Cliquet, pas exigence rétroactive** — même arbitrage que
`test_prohibition_gates_declare_a_floor` : quatre règles antérieures n'ont
pas de sonde et sont listées dans `_NO_PROBE_DEBT`. Les rendre rouges d'un
coup serait un effet de bord non demandé. L'égalité est **stricte** : une
règle qui gagne sa sonde doit sortir de la dette, sinon la table pourrit
comme les allowlists qu'elle imite.

⚠️ Ce que cette gate ne peut PAS attraper
------------------------------------------

Elle prouve qu'un constat **tombe** et qu'aucun ne tombe à tort. Elle ne
juge pas *lequel* : un sujet peut être signalé par le bon constat ou par un
constat voisin, et les deux passent. Mutation-testée le 2026-08-16, la
quatrième mutation le montre — débrancher le constat « composant inconnu »
laisse `crad` signalé quand même, par la règle de groupe qui suit
(« `crad` n'a pas de groupe `slots` »). Le message est moins juste, l'auteur
est prévenu au bon endroit, la gate reste verte. C'est une dégradation de
diagnostic, pas un silence — et pour la distinguer il faudrait asserter sur
la formulation, c'est-à-dire mesurer la prose, ce que ce fichier vient
justement d'arrêter de faire.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

from bretzel.lint import available_rules, run
from bretzel.lint.rules import STATIC

_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class _Probe:
    """Un cas fabriqué et son verdict attendu, dans les deux sens.

    **Deux fichiers séparés, et c'est nécessaire.** La première version
    n'en avait qu'un, et vérifiait le sens 2 en cherchant l'absence d'une
    sous-chaîne dans le rapport entier. Ça s'est cassé le jour même :
    ``theme-vocabulaire-inconnu`` produit un *hint* qui contient le mot
    ``sidebar`` (« ``sidebar_section`` s'écrit sous ``'sidebar'`` »), donc
    la forme légitime paraissait signalée alors que le constat portait
    ailleurs. Une assertion qui peut être mise en défaut par la PROSE d'un
    message ne mesure pas ce qu'elle croit.

    Avec ``legitimate`` isolé, le sens 2 devient une affirmation nette —
    **zéro constat** — qu'aucune formulation ne peut fausser.
    """

    #: Le code fautif. Chaque faute doit apparaître dans ``must_flag``.
    faulty: str
    must_flag: tuple[str, ...]
    #: Du code CORRECT qui ressemble à une faute. Doit produire zéro
    #: constat. C'est la moitié qui coûte, et celle qu'on oublie.
    legitimate: str
    #: Tenue au zéro absolu sur le corpus réel ? Toutes ne peuvent pas :
    #: certaines signalent des formes *légitimes mais coûteuses*, dont la
    #: population est gelée par `test_lint_baseline_on_examples`.
    zero_on_corpus: bool
    why: str


_PROBES: dict[str, _Probe] = {
    "lien-dans-un-lien": _Probe(
        faulty=textwrap.dedent(
            """
            from bretzel import ui

            def case() -> None:
                with ui.card(href="/classe/3"):
                    ui.text("6e2")
                    ui.link(label="cahier", href="/cahier?classe=3")
            """
        ),
        must_flag=("link",),
        legitimate=textwrap.dedent(
            """
            from bretzel import ui

            # La forme correcte : la carte ne mène nulle part, elle
            # PORTE deux liens. C'est ce que le constat recommande.
            def case() -> None:
                with ui.card():
                    ui.link(label="6e2", href="/classe/3")
                    ui.link(label="cahier", href="/cahier?classe=3")

            # Une carte-lien SANS lien dedans reste licite.
            def tuile() -> None:
                with ui.card(href="/classe/3"):
                    ui.text("6e2")

            # `href=None` dit « pas de lien ici » — l'app l'écrit quand
            # la route n'existe pas encore. Ce n'est pas une ancre.
            def pas_encore() -> None:
                with ui.card(href=None):
                    ui.link(label="cahier", href="/cahier")
            """
        ),
        zero_on_corpus=True,
        why="un `<a>` dans un `<a>` n'a aucune forme légitime",
    ),
    "zone-qui-ecoute-trop": _Probe(
        faulty=textwrap.dedent(
            """
            from bretzel import refreshable, ui
            from bretzel.state import PageState, field

            class Brouillon(PageState):
                ouvert: bool = field(default=False)

            @refreshable(deps=[Brouillon])
            def dialogue() -> None:
                ui.text("ouvert" if Brouillon().ouvert else "ferme")

            # La parente porte la dependance de son ENFANT, qui la
            # declare deja : ouvrir le dialogue rend tout le panneau.
            @refreshable(deps=[Brouillon])
            def panneau() -> None:
                ui.text("beaucoup de contenu")
                dialogue()
            """
        ),
        must_flag=("panneau",),
        legitimate=textwrap.dedent(
            """
            from bretzel import refreshable, ui
            from bretzel.state import AppState, PageState, field

            class Brouillon(PageState):
                ouvert: bool = field(default=False)

            class Revision(AppState):
                rev: int = field(default=0, merge="add")

            @refreshable(deps=[Brouillon])
            def dialogue() -> None:
                ui.text("ouvert" if Brouillon().ouvert else "ferme")

            # 1. Un JETON de revision : declare, jamais lu, et c'est
            #    l'idiome recommande — une ecriture en base ne touche
            #    aucun etat type, donc rien ne se rafraichirait sans lui.
            # 2. `Brouillon` est LU ici aussi : la parente a sa raison.
            @refreshable(deps=[Revision, Brouillon])
            def panneau() -> None:
                ui.text(str(Brouillon().ouvert))
                dialogue()

            # Une zone sans enfant ne peut rien porter pour personne.
            @refreshable(deps=[Revision])
            def seule() -> None:
                ui.text("liste relue en base")
            """
        ),
        zero_on_corpus=True,
        why="porter la dependance d'un enfant autonome n'a pas de forme legitime",
    ),
    "palier-de-taille-a-moitie-surcharge": _Probe(
        faulty=textwrap.dedent(
            """
            from bretzel.theme import Theme

            THEME = Theme(components={
                "input": {"sizes": {"md": {"input": "h-8 px-3"}}},
                "select": {"sizes": {"md": {"trigger": "h-8 px-3"}}},
            })
            """
        ),
        # `calendar` est le premier de la liste triée des manquants —
        # le message en nomme quatre, pas dix-sept.
        must_flag=("calendar",),
        legitimate=textwrap.dedent(
            """
            from bretzel.theme import Theme

            # Aucune taille touchée : couleurs et rayons ne déplacent
            # aucune hauteur.
            COULEURS = Theme(
                semantic={"primary": "#2f7d6b"},
                shape={"box": "0.625rem"},
            )

            # La base de l'échelle : un jeton, toute la densité. C'est
            # la sortie que le constat recommande, elle ne doit rien
            # lever.
            DENSITE = Theme(spacing="0.2rem")

            # Un composant hors famille `inputs` : retailler un badge ne
            # casse aucune parité de contrôle.
            BADGE = Theme(components={
                "badge": {"sizes": {"md": {"root": "h-5 px-2"}}},
            })
            """
        ),
        zero_on_corpus=True,
        why="une surcharge partielle se corrige, elle ne se gèle pas",
    ),

    "page-declaree-dans-une-fonction": _Probe(
        faulty=textwrap.dedent(
            """
            from bretzel import Bretzel, page, ui

            def monter():
                app = Bretzel(title="t", secret_key="z" * 24)

                @page("/")
                def orpheline() -> None:
                    ui.text("salut")

                app.include(__name__)
                return app
            """
        ),
        must_flag=("orpheline",),
        legitimate=textwrap.dedent(
            """
            from bretzel import Bretzel, error_page, page, ui

            PAGES = []

            @page("/")
            def au_niveau_module() -> None:
                ui.text("vue par le balayage")

            def monter():
                app = Bretzel(title="t", secret_key="z" * 24)

                # Passée DIRECTEMENT : `include` accepte un callable marqué.
                @page("/directe")
                def directe() -> None:
                    ui.text("ok")

                app.include(directe)
                return app

            def collecter():
                # L'itérable — le chemin documenté des pages générées.
                @page("/collectee")
                def collectee() -> None:
                    ui.text("ok")

                PAGES.append(collectee)

            def rendre():
                @error_page(404)
                def absente() -> None:
                    ui.text("perdu")

                return absente
            """
        ),
        zero_on_corpus=True,
        why=(
            "`examples/` ne déclare aucune page imbriquée — le corpus est "
            "donc vert par construction, et c'est `tests/` qui mesure "
            "vraiment cette règle : 2 constats sur 75 déclarations "
            "imbriquées le 2026-09-10, tous deux VRAIS (`test_static_dir` "
            "et `test_protocol_compat_gate` déclarent une page `/` que "
            "`include(__name__)` ne peut pas voir — vérifié, `GET /` rend "
            "404 et `home` n'est pas un attribut de son module). Les 73 "
            "autres passent la fonction à `include`, et sont épargnées."
        ),
    ),
    "client-de-test-sans-lifespan": _Probe(
        faulty=textwrap.dedent(
            """
            from fastapi.testclient import TestClient

            from monapp import app, fabrique

            client_orphelin = TestClient(app)
            client_orphelin.get("/")

            TestClient(fabrique()).get("/")
            """
        ),
        # Les deux formes prouvables : la liaison à un nom qu'aucun `with`
        # ne reprend, et la construction jetée en instruction nue.
        must_flag=("client_orphelin", "TestClient(fabrique())"),
        legitimate=textwrap.dedent(
            """
            from fastapi.testclient import TestClient

            from monapp import app


            def _client() -> TestClient:
                # Le `with` a lieu chez l'appelant — illisible d'ici, donc
                # silence. C'est la forme du dépôt (1 cas sur 219).
                return TestClient(app)


            def test_direct() -> None:
                with TestClient(app) as client:
                    assert client.get("/").status_code == 200


            def test_en_deux_temps() -> None:
                client = TestClient(app)
                with client:
                    assert client.get("/").status_code == 200


            def test_par_la_fabrique() -> None:
                with _client() as client:
                    assert client.get("/").status_code == 200
            """
        ),
        zero_on_corpus=True,
        why=(
            "`examples/` n'utilise pas `TestClient` : le corpus est vert "
            "sans rien mesurer, et c'est `tests/` qui compte pour cette "
            "règle — 219 occurrences, ZÉRO constat le 2026-09-10. Les 217 "
            "formes `with` sont reconnues, la fabrique qui `return` est "
            "épargnée délibérément (son `with` est chez l'appelant), et la "
            "forme en deux temps aussi."
        ),
    ),
    "palier-de-theme-change-de-forme": _Probe(
        faulty=textwrap.dedent(
            """
            from bretzel.theme import Theme

            THEME = Theme(
                components={
                    "button": {"sizes": {"md": {"root": "h-8 px-3"}}},
                    "select": {"sizes": {"md": "h-8 px-3"}},
                }
            )
            """
        ),
        # Les DEUX sens, parce qu'ils ne se comportent pas pareil : le
        # premier est muet (le palier perd tous ses jetons, la page rend
        # en 200), le second lève au rendu. Une sonde qui n'aurait que le
        # premier laisserait débrancher la moitié de la règle.
        must_flag=("button", "select"),
        legitimate=textwrap.dedent(
            """
            from bretzel.theme import Theme

            TAILLE = "h-8 px-3"

            THEME = Theme(
                components={
                    # Même forme que le thème livré — la surcharge normale.
                    "button": {"sizes": {"md": "h-8 px-3"}},
                    "select": {"sizes": {"md": {"trigger": "h-8 px-3"}}},
                    # Une clé NEUVE : extension supportée, pas une faute.
                    "badge": {
                        "sizes": {"jumbo": {"root": "h-20"}},
                        "variants": {"brand": "bg-teal-600"},
                    },
                    # Un slot, forme chaîne — inchangé.
                    "card": {"slots": {"root": "block w-full"}},
                    # Illisible statiquement : la règle se tait.
                    "alert": {"sizes": {"md": TAILLE}},
                }
            )
            """
        ),
        zero_on_corpus=True,
        why=(
            "Elle ne juge que les clés DÉJÀ livrées, et seulement leur forme. "
            "Une clé neuve est exempte — c'est la façon supportée d'étendre le "
            "thème, que `theme-vocabulaire-inconnu` protège explicitement. "
            "Vérifié le 2026-09-10 : zéro constat sur les 292 fichiers "
            "d'`examples/`."
        ),
    ),
    "etat-construit-sur-la-boucle": _Probe(
        faulty=textwrap.dedent(
            """
            from __future__ import annotations

            from bretzel.state import AppState, field

            class Panier(AppState):
                n: int = field(default=0)

            async def importer():
                Panier().n += 1
            """
        ).strip(),
        must_flag=("Panier",),
        # Les trois formes qui RESSEMBLENT à la faute. La porte prévue
        # (`await X.load()`) est un appel d'attribut, pas un nom nu ; un
        # `ClientState` n'a aucun backend à attendre, donc le construire
        # sur la boucle est gratuit ; et la même ligne dans un `def` est
        # le cas NOMINAL — c'est celui que le framework délestera.
        legitimate=textwrap.dedent(
            """
            from __future__ import annotations

            from bretzel.state import AppState, ClientState, field

            class Panier(AppState):
                n: int = field(default=0)

            class Vue(ClientState):
                ouvert: bool = field(default=False)

            async def importer():
                panier = await Panier.load()
                panier.n += 1
                Vue().ouvert = True

            def incrementer():
                Panier().n += 1
            """
        ).strip(),
        zero_on_corpus=True,
        why=(
            "construire un état serveur sur la boucle marche en mémoire et "
            "lève avec Redis — la faute attend la prod pour se montrer"
        ),
    ),
    "compteur-partage-non-declare": _Probe(
        faulty=textwrap.dedent(
            """
            from __future__ import annotations

            from bretzel.state import AppState, field

            class Stats(AppState):
                vues: int = field(default=0)

            def vendre():
                Stats().vues += 1

            def annuler():
                s = Stats()
                s.vues -= 1
            """
        ).strip(),
        must_flag=("Stats.vues",),
        # Les quatre formes qui RESSEMBLENT à la faute et n'en sont pas.
        # La quatrième est la plus importante : `+=` sur une SESSION est
        # aussi souvent une pagination qu'un total, et la règle s'arrête
        # volontairement au partage entre utilisateurs.
        legitimate=textwrap.dedent(
            """
            from __future__ import annotations

            from bretzel.state import AppState, SessionState, field

            class Stats(AppState):
                vues: int = field(default=0, merge="add")
                facteur: int = field(default=2)

            class Vue(SessionState):
                page: int = field(default=1)

            def vendre():
                Stats().vues += 1

            def doubler():
                Stats().facteur *= 2

            def suivante():
                Vue().page += 1

            def poser():
                Stats().facteur = 3
            """
        ).strip(),
        zero_on_corpus=True,
        why=(
            "un incrément perdu ne lève pas et ne s'affiche pas : le "
            "compteur avance simplement moins vite que les clics, et seul "
            "un second utilisateur peut le révéler"
        ),
    ),
    "kwargs-inconnu": _Probe(
        faulty=textwrap.dedent(
            """
            from bretzel import ui

            def page():
                ui.input(label="Display name")
                ui.buton("faute de frappe")
            """
        ).strip(),
        must_flag=("label", "buton"),
        # ``aria_label=`` est l'échappatoire HTML brute (99 appels dans ce
        # dépôt, tous corrects) ; ``justify=`` est une prop réactive
        # héritée que ``HStack`` retire de son ``__init__`` sans la
        # sceller. Les deux ressemblent à des kwargs inconnus.
        legitimate=textwrap.dedent(
            """
            from bretzel import ui

            def page():
                ui.icon_button(aria_label="Fermer")
                ui.hstack(justify="between")
            """
        ).strip(),
        zero_on_corpus=True,
        why="un kwarg mort n'a jamais de bonne raison d'exister",
    ),
    "theme-vocabulaire-inconnu": _Probe(
        faulty=textwrap.dedent(
            """
            from bretzel.theme import Theme

            FAUTIF = Theme(components={
                "crad": {"slots": {"root": "x"}},
                "card": {"slotz": {"root": "x"}, "slots": {"rooot": "x"}},
                "sidebar_section": {"slots": {"section": "x"}},
            })
            """
        ).strip(),
        # ``sidebar_section`` est un nom ``ui.*`` RÉEL et une clé de thème
        # MORTE : la classe déclare ``THEME_KEY = "sidebar"``, donc
        # ``_resolved_theme`` ne consulte jamais cette entrée (prouvé par
        # rendu : l'override sous ``"sidebar_section"`` n'atteint pas le
        # HTML, celui sous ``"sidebar"`` oui).
        #
        # Il est ici parce qu'il est la SEULE forme qui distingue un index
        # bâti sur ``THEME_KEY`` d'un index bâti sur les noms ``ui.*`` —
        # partout ailleurs les deux coïncident. Sans ce cas, muter l'index
        # vers ``ui_name`` laissait la gate entièrement verte (mesuré le
        # 2026-08-16 : mutation M3, 10 tests passés).
        must_flag=("crad", "slotz", "rooot", "sidebar_section"),
        # Les trois pièges du domaine, et ils sont subtils :
        # - ``sidebar`` est la clé de ``sidebar_section`` / ``sidebar_title``
        #   (``THEME_KEY`` ≠ nom ``ui.*`` sur huit composants) — un index
        #   bâti sur les noms ``ui.*`` le signalerait ;
        # - ``brand`` est une variante que l'APP ajoute, et c'est le chemin
        #   supporté pour dévier du thème livré : le signaler condamnerait
        #   la seule sortie propre ;
        # - ``section_label`` est un slot réel du thème partagé.
        legitimate=textwrap.dedent(
            """
            from bretzel.theme import Theme

            LEGITIME = Theme(components={
                "card": {"slots": {"root": "block w-full"}},
                "sidebar": {"slots": {"section_label": "x"}},
                "button": {"variants": {"brand": "bg-indigo-500"}},
            })
            """
        ).strip(),
        zero_on_corpus=True,
        why="un nom de thème inconnu ne rend rien, jamais, nulle part",
    ),
    "valeur-hors-table": _Probe(
        faulty=textwrap.dedent(
            """
            from bretzel import ui

            def page():
                ui.button("Casse", variant="ghots")
                ui.link("Lien", href="/", variant="solid")
                ui.icon("zap", size="4xl")
            """
        ).strip(),
        # `solid` est une vraie variante… de `Button`. Sur un `Link` (dont
        # les variantes sont hover/text/underline) elle ne matche rien ET
        # écrase le défaut `hover` : le lien perd toute affordance. 13
        # occurrences trouvées dans `examples/` au premier passage.
        #
        # `size="4xl"` sur une icône est l'autre confusion réelle, trouvée
        # elle aussi dans `examples/` : chez `Icon`, `size="xl"` RESSORT la
        # classe Tailwind `text-4xl`, donc l'auteur écrit l'échelle du
        # rendu au lieu de celle du composant (qui s'arrête à `2xl`).
        must_flag=("ghots", "solid", "4xl"),
        legitimate=textwrap.dedent(
            """
            from bretzel import ui
            from bretzel.theme import Theme

            IDENTITY = Theme(components={
                "button": {"variants": {"brand": "bg-indigo-500"}},
            })

            def page():
                ui.button("Livree", variant="ghost")
                ui.button("Maison", variant="brand")
                ui.bar_chart(data=[], variant="grouped")
                ui.button("Calculee", variant=CHOSEN)
                ui.date_picker(size="sm")
                ui.heading("Titre", size="6xl")
                ui.avatar(alt="x", size="2xl")
                ui.radio_group(size="sm")
            """
        ).strip(),
        # Les formes qu'il ne faut pas confondre avec une faute :
        #
        # - une variante LIVRÉE ; une variante que l'APP déclare (le chemin
        #   recommandé pour dévier du thème — le condamner rendrait l'outil
        #   nuisible) ; un composant qui accepte `variant=` SANS table
        #   (`bar_chart`, `file_upload`, `pie_chart`) ; une valeur calculée,
        #   hors de portée du statique ;
        # - `date_picker(size="sm")` : sa table `sizes` est indexée par
        #   SLOT (`{"input_field": {"sm": …}}`), donc lire ses clés brutes
        #   fait conclure que `sm` n'existe pas. C'est le faux positif que
        #   la première version produisait, et la raison d'être de
        #   `size_vocabulary` ;
        # - `heading(size="6xl")` et `avatar(size="2xl")` : l'échelle n'est
        #   PAS globale — la typographie va jusqu'à `8xl`, l'avatar à
        #   `2xl`. Une règle qui aurait figé `SIZE_SCALE` comme vocabulaire
        #   universel les signalerait tous les deux ;
        # - `radio_group(size="sm")` : accepte `size=` sans aucune table,
        #   son `render` en fait autre chose.
        #
        # ⚠️ Ici le thème est dans le MÊME fichier ; le cas qui compte
        # vraiment — thème dans un autre fichier — est couvert par
        # `test_declared_theme_is_seen_across_files` plus bas, parce
        # qu'une sonde à un seul fichier ne peut pas l'exprimer.
        zero_on_corpus=True,
        why="une variante hors table retire la classe et laisse le composant nu",
    ),
    "tailles-melangees": _Probe(
        # Les deux fautes RÉELLES trouvées dans ce dépôt le 2026-08-23,
        # reproduites telles quelles. La première est celle qu'un
        # utilisateur a vue sur une capture d'écran ; la seconde n'avait
        # jamais été vue par personne.
        faulty=textwrap.dedent(
            """
            from bretzel import ui

            def filtres():
                with ui.grid(cols=2):
                    with ui.form_field(label="Période"):
                        ui.date_range_picker(size="sm")
                    with ui.form_field(label="Type"):
                        ui.select(options=[])

            def tiroir():
                with ui.form():
                    ui.input(placeholder="Titre")
                    ui.select(options=[], size="sm")
                    ui.select(options=[], size="sm")
            """
        ).strip(),
        must_flag=("date_range_picker", "input"),
        # Les quatre formes correctes qui ressemblent à la faute :
        #
        # - un groupe où TOUT est explicitement à `sm` ;
        # - un `size=` explicite qui vaut le DÉFAUT du voisin : `md` et
        #   l'absence rendent le même HTML, donc les traiter comme deux
        #   valeurs signalerait du code juste — c'est la raison pour
        #   laquelle les défauts sont résolus sur la classe ;
        # - un `ui.vstack` : conteneur de PAGE, pas de ligne. L'inclure
        #   faisait passer les constats de 2 à 22 sur `examples/`, tous
        #   faux (un groupe avalait une carte entière) ;
        # - deux tailles dans des conteneurs de ligne DIFFÉRENTS : deux
        #   voisinages, donc aucun rapport visuel.
        legitimate=textwrap.dedent(
            """
            from bretzel import ui

            def tout_petit():
                with ui.hstack():
                    ui.input(size="sm")
                    ui.select(options=[], size="sm")

            def defaut_explicite():
                with ui.hstack():
                    ui.input(size="md")
                    ui.select(options=[])

            def pile_de_page():
                with ui.vstack():
                    ui.input(size="sm")
                    ui.select(options=[])

            def deux_lignes():
                with ui.hstack():
                    ui.input(size="sm")
                with ui.hstack():
                    ui.select(options=[])
            """
        ).strip(),
        # Deux bancs du playground comparent délibérément deux tailles
        # côte à côte — gelés dans `test_lint_baseline_on_examples`.
        zero_on_corpus=False,
        why="un banc qui compare deux tailles est un mélange délibéré",
    ),
    "classe-doublee-par-une-prop": _Probe(
        # Les trois façons dont une classe de `classes=` rencontre une prop
        # sur le MÊME élément : contre un DÉFAUT (`justify` vaut `start`
        # sans qu'on demande rien — le cas réel, deux fois de suite dans
        # `examples/playground/features/diagram/ui.py`), contre une valeur
        # PASSÉE dans le même appel, et le doublon pur (la prop pose
        # exactement la classe qu'on réécrit).
        faulty=textwrap.dedent(
            """
            from bretzel import ui

            def page():
                with ui.vstack(gap="none", align="start",
                               classes="h-full w-full justify-center px-3"):
                    ui.text("centré — et pourtant collé en haut")
                with ui.hstack(align="center", classes="items-end"):
                    ui.text("deux items-* de même spécificité")
                with ui.flex(direction="col", classes="flex-col"):
                    ui.text("le doublon pur")
            """
        ).strip(),
        must_flag=("justify-center", "items-end", "flex-col"),
        # Les cinq formes qui RESSEMBLENT à la faute. Les trois premières
        # sont l'échappatoire même — ce qu'aucune valeur de prop ne rend,
        # un variant (autre portée ET autre rang dans la feuille), un
        # important (l'écart est assumé et il gagne). La quatrième est le
        # piège du préfixe : `flex-1` et `flex-nowrap` ne sont PAS la
        # famille de `direction=`, et un simple `flex-*` en aurait fait
        # quatre faux positifs par app. Les deux dernières sont le code
        # qu'on RECOMMANDE : la prop plutôt que la classe, et un composant
        # hors portée (`ui.grid` ne déclare pas `THEME_TABLES`).
        legitimate=textwrap.dedent(
            """
            from bretzel import ui

            def page():
                with ui.vstack(classes="justify-normal items-normal"):
                    ui.text("hors table : aucune prop ne rend ça")
                with ui.vstack(classes="md:justify-center"):
                    ui.text("un variant")
                with ui.hstack(classes="justify-end!"):
                    ui.text("un important")
                with ui.flex(classes="flex-1 flex-nowrap"):
                    ui.text("flex-* qui n'est pas une direction")
                with ui.vstack(gap="none", align="start", justify="center",
                               classes="h-full w-full px-3"):
                    ui.text("la prop, pas la classe")
                with ui.grid(cols=2, classes="gap-4"):
                    ui.text("hors portée, et écrit dans la docstring")
            """
        ).strip(),
        zero_on_corpus=True,
        why=(
            "Les 21 sites d'`examples/` ont été corrigés le 2026-09-06 — "
            "tous le même motif, un `justify-*` de `classes=` contre le "
            "`justify-start` du défaut, dont sept pages d'erreur "
            "« centrées » qui ne l'étaient pas. La règle est un cliquet."
        ),
    ),
    "etat-perdu-par-un-cast": _Probe(
        faulty=textwrap.dedent(
            """
            from bretzel import ui

            def page(draft, prefs):
                ui.stepper(value=int(draft.etape))
                ui.input(value=str(prefs["nom"]))
                ui.calendar(month=draft.jour or draft.fin)
                ui.input(value=f"{draft.nom}")
            """
        ).strip(),
        must_flag=("draft.etape", "prefs['nom']", "draft.jour", "draft.nom"),
        # Les formes qui RESSEMBLENT a la faute et n'en sont pas : la
        # valeur nue (ce qu'il faut ecrire), un litteral assume, un cast
        # sur un slot de TEXTE (aucun signal client a re-adopter), un cast
        # qui n'enveloppe aucune lecture d'etat.
        #
        # Les trois dernieres gardent l'ELARGISSEMENT du 2026-08-30 : un
        # `or` entre litteraux n'efface aucune provenance, une f-string
        # sans lecture d'etat non plus, et l'ARITHMETIQUE reste dehors
        # volontairement — ses trois sites du depot portent tous sur des
        # litteraux (`'A' * 200`), et elargir jusque-la serait bruyant.
        legitimate=textwrap.dedent(
            """
            from bretzel import ui

            def page(draft):
                ui.tabs(value=draft.onglet)
                ui.stepper(value=2)
                ui.badge(label=str(draft.n))
                ui.text(content=str(draft.n))
                ui.stepper(value=int(3))
                ui.calendar(month="2026-01" or "2026-02")
                ui.input(value=f"fixe")
                ui.badge(label=draft.nom or "anonyme")
            """
        ).strip(),
        zero_on_corpus=True,
        why=(
            "Les quatre sites du depot ont ete corriges le 2026-08-25 : "
            "le stepper de l'ecran d'import du CRM et les trois entrees "
            "de la page slider du playground. La regle est un cliquet. "
            "Elargie aux `BoolOp` et `JoinedStr` le 2026-08-30 : UN site "
            "de plus sur 384 fichiers, zero faux positif — le `month=jour "
            "or fin` de l'agenda du CRM, ou l'estampille survivait quand "
            "le jour etait rempli et disparaissait quand il etait vide."
        ),
    ),
}

#: Règles antérieures au cliquet, sans sonde. Égalité stricte : une entrée
#: qui gagne sa sonde sort d'ici. Mesuré au 2026-08-16.
_NO_PROBE_DEBT: frozenset[str] = frozenset({
    "classe-tailwind-assemblee",
    "handler-lambda",
    "html-non-litteral",
    "transport-a-la-main",
})


def test_the_registry_is_not_empty() -> None:
    """Plancher : `run` a des règles à faire tourner."""
    assert available_rules(), (
        "aucune règle enregistrée — `bretzel.lint.run` rendrait un rapport "
        "vide et vert sur n'importe quoi."
    )


def test_every_rule_declares_a_probe() -> None:
    """Le cliquet : une règle neuve déclare ce qu'elle attrape et épargne.

    Sans lui, ajouter une règle à ``STATIC`` suffit à la mettre en
    production sans qu'aucun test ne sache ce qu'elle est censée faire —
    et une règle silencieuse est indistinguable d'une règle qui marche.
    """
    covered = set(_PROBES) | _NO_PROBE_DEBT
    known = set(STATIC)

    assert known - covered == set(), (
        f"règle(s) sans sonde : {sorted(known - covered)}. Ajoute une entrée "
        f"à `_PROBES` avec son cas fabriqué, ce qu'il DOIT signaler, et ce "
        f"qu'il ne doit PAS signaler."
    )
    assert covered - known == set(), (
        f"`_PROBES`/`_NO_PROBE_DEBT` citent des règles inconnues : "
        f"{sorted(covered - known)}. Une entrée morte fait croire à une "
        f"couverture qui n'existe plus."
    )
    assert not (set(_PROBES) & _NO_PROBE_DEBT), (
        f"règle(s) à la fois sondée et inscrite en dette : "
        f"{sorted(set(_PROBES) & _NO_PROBE_DEBT)}. Retire-la de la dette — "
        f"sinon la table autorise indéfiniment ce qui est déjà réparé."
    )


@pytest.mark.parametrize("rule", sorted(_PROBES))
def test_the_rule_catches_the_fabricated_case(rule: str, tmp_path: Path) -> None:
    """Sens 1 — ce qui doit rougir rougit."""
    probe = _PROBES[rule]
    (tmp_path / "app.py").write_text(probe.faulty, encoding="utf-8")
    report = run([tmp_path], rules=(rule,))

    assert report.findings, f"[{rule}] le cas fabriqué ne produit aucun constat"
    # Les MESSAGES seuls, jamais les hints. Un message nomme son sujet ; un
    # hint explique, et son explication peut citer une autre forme —
    # `theme-vocabulaire-inconnu` écrit « `sidebar_section` s'écrit sous
    # `'sidebar'` », ce qui rendait l'assertion vraie sans qu'aucun constat
    # ne porte là-dessus. Mesuré le 2026-08-16 : la mutation qui indexait
    # par nom `ui.*` au lieu de `THEME_KEY` laissait la gate verte, dans
    # les DEUX sens, parce que les deux assertions lisaient de la prose.
    subjects = "\n".join(f.message for f in report.findings)
    for needle in probe.must_flag:
        assert needle in subjects, (
            f"[{rule}] `{needle}` devait être le SUJET d'un constat et ne "
            f"l'est pas — la règle est devenue silencieuse sur son propre "
            f"cas d'école.\nConstats obtenus :\n{subjects}"
        )


@pytest.mark.parametrize("rule", sorted(_PROBES))
def test_the_rule_spares_the_legitimate_forms(rule: str, tmp_path: Path) -> None:
    """Sens 2 — ce qui ne doit PAS rougir ne rougit pas.

    Zéro constat, pas « telle sous-chaîne absente » : le rapport d'un
    constat voisin peut citer la forme légitime dans son *hint*, et
    l'assertion par sous-chaîne se fait alors piéger par la prose du
    message plutôt que par le comportement de la règle (vécu le
    2026-08-16 avec ``sidebar``).
    """
    probe = _PROBES[rule]
    (tmp_path / "app.py").write_text(probe.legitimate, encoding="utf-8")
    report = run([tmp_path], rules=(rule,))

    assert report.files_scanned == 1, (
        f"[{rule}] la sonde légitime n'a pas été lue — le test serait vert "
        f"sans avoir rien mesuré."
    )
    assert not report.findings, (
        f"[{rule}] {len(report.findings)} faux positif(s) sur des formes "
        f"légitimes — c'est ce qui fait désactiver un outil :\n"
        + "\n".join(f.format() for f in report.findings)
    )


@pytest.mark.parametrize("corpus", ["examples", "tests/e2e/apps"])
@pytest.mark.parametrize(
    "rule", sorted(r for r, p in _PROBES.items() if p.zero_on_corpus)
)
def test_no_false_positive_on_the_real_corpus(rule: str, corpus: str) -> None:
    """Le taux de faux positifs, mesuré là où ça compte.

    ⚠️ **Seules les règles qui le déclarent sont tenues au zéro absolu.**
    Les autres signalent des formes *légitimes mais coûteuses* (le banc
    `ui.html` démontre `ui.html`), et leur population connue est gelée
    dans `test_lint_baseline_on_examples`. Exiger zéro partout aurait
    forcé à mutiler des bancs de démo pour faire taire un outil — le
    chemin le plus court vers un outil désactivé.
    """
    report = run([_ROOT / corpus], rules=(rule,))
    assert report.files_scanned > 0, f"{corpus} n'a été balayé sur aucun fichier"
    assert not report.findings, (
        f"{len(report.findings)} constat(s) [{rule}] sur `{corpus}`, qui est "
        f"du code correct et gardé — {_PROBES[rule].why} :\n"
        + "\n".join(f.format(root=_ROOT) for f in report.findings)
    )


def test_declared_theme_is_seen_across_files(tmp_path: Path) -> None:
    """Une variante déclarée dans un AUTRE fichier n'est pas une faute.

    C'est le seul cas que les sondes ne peuvent pas porter : elles tiennent
    dans un fichier, et le vrai motif en demande deux — le thème d'un côté,
    les call-sites de l'autre, ce qui est la disposition normale d'une app.

    L'enjeu n'est pas académique. ``Theme(components={…: {"variants": …}})``
    est le chemin **recommandé** pour dévier du thème livré ; une règle qui
    le signalerait comme faute condamnerait ce qu'on conseille, et se ferait
    désactiver à la première session. C'est pour ce cas précis que ``run``
    expose le corpus du passage (``corpus.bound``).
    """
    (tmp_path / "identity.py").write_text(
        "from bretzel.theme import Theme\n\n"
        'IDENTITY = Theme(components={"button": {"variants": {"brand": "bg-x"}}})\n',
        encoding="utf-8",
    )
    (tmp_path / "page.py").write_text(
        "from bretzel import ui\n\n"
        "def page():\n"
        '    ui.button("Maison", variant="brand")\n'
        '    ui.button("Faute", variant="brnad")\n',
        encoding="utf-8",
    )

    report = run([tmp_path], rules=("valeur-hors-table",))
    subjects = "\n".join(f.message for f in report.findings)

    assert "brnad" in subjects, (
        "la faute de frappe voisine n'est plus vue — la règle s'est tue au "
        "lieu de discriminer."
    )
    assert "brand" not in subjects.replace("brnad", ""), (
        "`brand` est signalé alors qu'un `Theme(components=…)` du corpus le "
        "déclare. La règle ne lit plus que son propre module, donc elle "
        "condamne l'échappatoire documentée."
    )
