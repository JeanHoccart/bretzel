"""Ce que Bretzel sait FAIRE — la liste qu'aucun arbre ne peut donner.

Pourquoi elle existe, et pourquoi elle est écrite à la main
-----------------------------------------------------------
``describe_package`` marche l'arbre des dossiers et rend 117 lignes qui
disent **où sont les fichiers**. C'est exact, et ça ne répond pas à la
question qu'on pose vraiment : *qu'est-ce que ce framework sait faire ?*

Aucun arbre ne peut y répondre, et ce n'est pas un défaut de rédaction :
**une capacité ne tient pas dans un dossier.** Servir un fichier, c'est
``render/decorators/download.py`` + ``server/routing/downloads.py`` +
``server/routing/_csv.py`` + le ``download=`` de ``components/actions/
link`` + l'export de ``components/data/datatable``. Cinq dossiers, cinq
docstrings, et aucune qui dise « Bretzel sait servir un fichier ».

D'où une liste transverse, écrite par un humain. C'est exactement la
forme qui a fait supprimer le skill ``bretzel-api`` le 2026-08-01 — un
catalogue recopié à la main qui nommait deux composants inexistants.

Ce qui rend celle-ci différente
--------------------------------
**Elle est ANCRÉE.** Chaque capacité nomme les symboles par lesquels on
y entre, en chemins pointés, et ``test_a_capability_is_anchored``:

1. les résout pour de vrai (import + ``getattr``) — un symbole supprimé
   ou renommé fait rougir la ligne qui le cite ;
2. vérifie que l'extrait de code parse ET qu'il emploie ces symboles —
   une capacité ne peut donc pas décrire autre chose que ce qu'elle
   nomme ;
3. refuse qu'un même symbole d'entrée soit revendiqué par deux
   capacités — c'est le détecteur de doublon.

⚠️ **Ce que la gate ne garde PAS : que la phrase soit vraie.** Un
``does:`` qui promet plus que le code ne fait passe au vert. Aucune
mécanique ne peut en juger — c'est la revue. C'est pour ça que chaque
ligne porte un ``caveat:`` : la limite est aussi utile que la promesse,
et c'est elle qui dit que la PWA n'a pas encore de service worker.

La règle : un index LISTE, un chapitre ENSEIGNE
------------------------------------------------
Cette liste est un INDEX. Elle sert à savoir qu'une chose existe et par
où on y entre — pas à l'apprendre. Ce qui explique *pourquoi* et
*comment* vit dans un chapitre de ``examples/docs``, écrit à la main, et
**à un seul endroit**.

La règle a été posée le 2026-09-03 parce qu'il y avait quatre surfaces
qui répondaient à « qu'est-ce que Bretzel sait faire » — cette liste,
l'arbre des paquets, le catalogue ``ui.*``, la cheat-sheet — et aucune
règle disant laquelle fait autorité. Mesuré : les chapitres NE SE
dupliquent pas entre eux (trois paires seulement partagent quatre
symboles, et ce sont ``Bretzel``, ``page``, ``ui.button``, dont tout
extrait a besoin). Le désordre n'était donc pas de la redite, c'était
l'absence de règle sur *où l'on écrit* quand on ajoute quelque chose.

D'où :

- un **index** est généré d'une source unique, ne porte pas de prose de
  son cru, et RENVOIE vers le chapitre ;
- un **chapitre** est écrit, enseigne un mécanisme, et est le seul
  endroit où l'on explique ;
- chaque capacité déclare son chapitre dans :attr:`Capability.chapter`,
  et une capacité sans chapitre est une dette VISIBLE — affichée sur la
  page, tenue par un cliquet qui ne remonte pas.

Ce que ça ne prétend PAS être
------------------------------
Une doc. Une capacité tient en une phrase et un extrait minimal ; le
détail vit dans la docstring du symbole, que ``describe`` rend déjà.
La liste sert à SAVOIR QUE ÇA EXISTE — c'est le seul trou que ni
l'arbre, ni le catalogue ``ui.*``, ni la table par besoin ne comblent.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Capability:
    """Une chose que Bretzel permet de faire, et par où on y entre."""

    #: Le titre, à l'infinitif : on nomme une ACTION, pas un composant.
    #: « Servir un fichier », pas « Le décorateur download ».
    name: str
    #: Ce que ça permet, en une phrase, du point de vue de qui l'écrit.
    #: Pas ce que c'est — ce que ça évite d'avoir à faire soi-même.
    does: str
    #: Les symboles par lesquels on entre, en chemins pointés. Résolus
    #: par la gate : c'est ce qui empêche cette liste de dériver.
    entry: tuple[str, ...]
    #: Le plus petit code qui la met en œuvre. Doit parser, et doit
    #: employer les noms d'``entry`` — la gate le vérifie.
    snippet: str
    #: Ce qu'il faut savoir avant de s'en servir : la limite, le piège,
    #: ou le repli. Vide quand il n'y en a pas.
    caveat: str = field(default="")

    #: La route du chapitre qui l'ENSEIGNE, dans ``examples/docs``.
    #:
    #: **C'est la règle « un index liste, un chapitre enseigne ».** Une
    #: capacité tient en une phrase et un extrait ; ce qui explique
    #: pourquoi et comment vit dans un chapitre écrit à la main, et à un
    #: seul endroit. Sans ce champ, il y avait quatre surfaces qui
    #: répondaient à « qu'est-ce que ça sait faire » et aucune règle
    #: disant laquelle fait autorité.
    #:
    #: Vide = **pas encore de chapitre**, et c'est une DETTE VISIBLE :
    #: la page l'affiche en clair, et ``test_a_capability_is_anchored``
    #: tient un cliquet qui ne remonte pas. Mesuré à la pose : 8 des 19.
    chapter: str = field(default="")


def _code(texte: str) -> str:
    """Un extrait désindenté — écrit lisiblement dans la source."""
    return textwrap.dedent(texte).strip("\n")


#: ⚠️ **La liste n'est pas exhaustive.** Dix-neuf capacités au
#: 2026-09-03 ; ce qui manque encore est suivi dans
#: ``.claude/work/todo.md``. Ne pas lire l'absence d'une ligne comme
#: « Bretzel ne sait pas le faire ».
CAPABILITIES: tuple[Capability, ...] = (
    # ── Sortir de l'app : fichiers, appareil, installation, identité ──
    Capability(
        name="Servir un fichier",
        chapter="/browser",
        does=(
            "Rendre une route qui TÉLÉCHARGE au lieu de naviguer. Une "
            "liste de dicts devient un CSV avec son en-tête, son "
            "échappement et son BOM pour Excel ; on ne touche ni aux "
            "en-têtes HTTP ni au `Content-Disposition`."
        ),
        entry=("bretzel.download", "bretzel.ui.link"),
        snippet=_code(
            """
            @download("/clients.csv")
            async def clients_csv() -> list[dict]:
                return [{"nom": "Ada Lovelace", "ville": "Londres"}]

            # Le lien doit dire qu'il porte un FICHIER, sinon la coque
            # l'avale : `hx-boost` intercepte tout <a> et swappe le CSV
            # dans la page.
            ui.link("Exporter", href="/clients.csv", download=True)
            """
        ),
        caveat=(
            "Sans `download=True`, le lien est intercepté par `hx-boost` "
            "et le fichier arrive comme du HTML dans l'outlet — sans "
            "aucun signe côté serveur."
        ),
    ),
    Capability(
        name="Agir dans le navigateur sans écrire de JS",
        chapter="/browser",
        does=(
            "Copier dans le presse-papiers, ouvrir la feuille de partage, "
            "faire vibrer l'appareil, imprimer, passer en plein écran — "
            "chacun en un `on_click=`, sans aller-retour serveur et sans "
            "une ligne de JavaScript."
        ),
        entry=(
            "bretzel.copy",
            "bretzel.share",
            "bretzel.vibrate",
            "bretzel.print_page",
            "bretzel.fullscreen",
        ),
        snippet=_code(
            """
            ui.button("Copier la clé", on_click=copy(state.api_key))
            ui.button("Partager", on_click=share())
            ui.button("Vibrer", on_click=vibrate([50, 30, 50]))
            ui.button("Imprimer", on_click=print_page())
            ui.button("Plein écran", on_click=fullscreen())
            """
        ),
        caveat=(
            "`share` n'existe pas sur un navigateur de bureau : il "
            "retombe alors sur une copie de l'URL. `vibrate` ne fait "
            "rien sur un appareil sans moteur. Les deux sont silencieux "
            "à dessein — un verbe absent ne doit pas casser la page."
        ),
    ),
    Capability(
        name="S'installer comme une application",
        chapter="/browser",
        does=(
            "Servir un manifeste web pour que l'app s'ajoute à l'écran "
            "d'accueil et s'ouvre sans barre d'adresse. Une ligne dans "
            "`Bretzel(...)` ; le manifeste, sa route et ses balises sont "
            "générés."
        ),
        entry=("bretzel.PWA", "bretzel.PWAIcon"),
        snippet=_code(
            """
            app = Bretzel(
                title="Tracker",
                pwa=PWA(name="Tracker", icon="/static/logo.png",
                        theme_color="#0f172a"),
            )
            """
        ),
        caveat=(
            "Le manifeste ne suffit pas au mode hors-ligne : il n'y a "
            "pas encore de service worker, donc l'app installée exige "
            "toujours le réseau."
        ),
    ),
    Capability(
        name="Entrer par un compte Google, Microsoft ou GitHub",
        chapter="/auth",
        does=(
            "Monter une porte OAuth2/OIDC — sa route, son échange de "
            "jeton, son cookie signé et sa rotation anti-fixation. Ce "
            "qui reste à écrire est la seule décision qui vous "
            "appartienne : accepter ce profil, ou non."
        ),
        entry=("bretzel.server.oauth.OIDC", "bretzel.auth"),
        snippet=_code(
            """
            @auth.door(OIDC(
                name="google", issuer="https://accounts.google.com",
                client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
            ))
            def on_oauth_user(profile) -> str | None:
                \"\"\"Rendre None REFUSE l'entrée.\"\"\"
                if not profile.email.endswith("@monentreprise.fr"):
                    return None
                return profile.email
            """
        ),
        caveat=(
            "Bretzel possède l'identité et son transport ; l'app possède "
            "la preuve. Il n'y a ni page de connexion fournie, ni mots "
            "de passe, ni rôles — et Apple n'est pas gérée (son "
            "`client_secret` est un JWT ES256, donc une dépendance)."
        ),
    ),
    # ── Le cœur : état typé, réactivité, calcul client ────────────────
    Capability(
        name="Tenir l'état de l'app dans des classes typées",
        chapter="/state-server",
        does=(
            "Déclarer où vit une donnée — la page, la session, "
            "l'utilisateur, l'app entière, ou le navigateur — en "
            "choisissant la classe dont on hérite. Pas de chaînes de "
            "caractères pour adresser l'état, donc l'autocomplétion et "
            "le vérificateur de types marchent."
        ),
        entry=(
            "bretzel.state.PageState",
            "bretzel.state.SessionState",
            "bretzel.state.UserState",
            "bretzel.state.AppState",
            "bretzel.state.ClientState",
        ),
        snippet=_code(
            """
            class Filtre(PageState):        # meurt avec la page
                recherche: str = field(default="")

            class Panier(SessionState):     # suit l'onglet
                lignes: list[str] = field(default_factory=list)

            class Profil(UserState):        # suit la personne connectée
                prenom: str = field(default="")

            class Reglages(AppState):       # partagé par tout le monde
                maintenance: bool = field(default=False)

            class Ouvert(ClientState):      # ne quitte JAMAIS le navigateur
                panneau: bool = field(default=False)
            """
        ),
        caveat=(
            "`UserState` n'existe que si une identité est résolue : sans "
            "auth, une app qui le lit reçoit 401. `ClientState` ne "
            "voyage pas en JSON — htmx l'envoie champ par champ, ce qui "
            "surprend sur les listes."
        ),
    ),
    Capability(
        name="Rafraîchir un morceau de page sur une mutation d'état",
        chapter="/reactivity-server",
        does=(
            "Marquer une zone comme dépendant d'un état typé : toute "
            "mutation de cet état la re-rend, seule, sans que le reste "
            "de la page bouge et sans écrire le moindre appel réseau. "
            "Avec `broadcast=`, la même zone se re-rend chez TOUTES les "
            "pages ouvertes, par SSE."
        ),
        entry=("bretzel.refreshable",),
        snippet=_code(
            """
            class Panier(SessionState):
                lignes: list[str] = field(default_factory=list)

            @refreshable(deps=[Panier])
            def resume() -> None:
                ui.text(f"{len(Panier().lignes)} article(s)")

            # Ailleurs, dans un handler : la zone se re-rend toute seule.
            Panier().lignes.append("café")
            """
        ),
        caveat=(
            "La zone est TRANSPARENTE à la mise en page mais n'est pas "
            "une instance de ce qu'elle porte — un conteneur qui "
            "inspecte ses enfants doit la déballer. Et `broadcast=` "
            "n'est pas une capacité à part : c'est un mode de ce même "
            "décorateur."
        ),
    ),
    Capability(
        name="Calculer côté client sans écrire de JS",
        chapter="/reactivity-client",
        does=(
            "Écrire une expression Python sur un état client — "
            "comparaison, arithmétique, négation, concaténation — et la "
            "laisser s'évaluer DANS le navigateur. Aucun aller-retour, "
            "et le JS émis n'est jamais tapé à la main."
        ),
        entry=("bretzel.state.ClientBinding",),
        snippet=_code(
            """
            class Form(ClientState):
                nom: str = field(default="")
                age: int = field(default=0)

            f = Form()
            # ⚠️ On n'ÉCRIT jamais le nom du type : c'est l'opérateur sur
            # un champ d'état client qui le fabrique.
            vide: ClientBinding = f.nom == ""

            # Chacune de ces trois lignes produit du JS, pas un POST :
            ui.button("Valider", disabled=vide)
            ui.text("Majeur", visible=f.age >= 18)
            ui.text(f.nom + " — " + f.nom)
            """
        ),
        caveat=(
            "On n'écrit jamais `ClientBinding` : c'est le TYPE que "
            "produit un opérateur sur un champ d'état client. La gate "
            "d'ancrage a d'ailleurs refusé la première version de cet "
            "extrait, qui ne le nommait nulle part.\n"
            "  L'algèbre est finie : `bretzel describe ClientBinding` "
            "liste les opérations avec le JS que chacune émet. Une "
            "expression hors algèbre (un appel de fonction Python) "
            "s'évalue au RENDU et se fige."
        ),
    ),
    Capability(
        name="Faire vivre une page sans que personne ne clique",
        chapter="/cadence",
        does=(
            "Un compteur, une horloge, un sondage périodique : une "
            "cadence côté client qui déclenche un handler, arrêtable par "
            "un simple booléen d'état — sans tâche serveur, sans cycle "
            "de vie à gérer."
        ),
        entry=("bretzel.ui.interval",),
        snippet=_code(
            """
            class Live(ClientState):
                actif: bool = field(default=True)

            live = Live()
            ui.interval(on_tick=recharger, seconds=5, active=live.actif)
            ui.switch("Suivre en direct", value=live.actif)
            """
        ),
        caveat=(
            "C'est du TIRAGE : la page demande. Pour de la POUSSÉE — le "
            "serveur qui prévient — c'est `@refreshable(broadcast=[…])`, "
            "qui passe par SSE et ne réveille que les pages concernées."
        ),
    ),
    # ── Les listes : itérer, tabuler, déplacer ────────────────────────
    Capability(
        name="Rendre une liste qui bouge sans la re-rendre entière",
        chapter="/lists",
        does=(
            "Itérer avec une clé stable par élément, filtrer côté client "
            "sur une expression, paginer — le tout en gardant l'état "
            "client de chaque ligne (une case cochée reste cochée quand "
            "la liste se réordonne)."
        ),
        entry=(
            "bretzel.ui.each",
            "bretzel.ui.filter_each",
            "bretzel.ui.paginate_each",
        ),
        snippet=_code(
            """
            for tache in each(Taches().items, key=lambda t: t.id):
                ui.checkbox(tache.titre)

            # Filtrer sans repasser par le serveur :
            with filter_each(Taches().items, where=lambda t: t.ouverte):
                ui.text("…")

            with paginate_each(Taches().items, per_page=20):
                ui.text("…")
            """
        ),
        caveat=(
            "Un `for` nu marche tant que le corps ne produit pas d'état "
            "client : sans clé stable, idiomorph réassocie les nœuds par "
            "position et l'état saute d'une ligne à l'autre."
        ),
    ),
    Capability(
        name="Afficher un tableau qui trie, filtre, pagine et s'exporte",
        chapter="/lists",
        does=(
            "Un composant qui prend un état de requête typé et des "
            "colonnes, et rend la barre de recherche, les en-têtes "
            "cliquables, la pagination et le bouton d'export CSV. Le tri "
            "et la pagination sont faits côté SERVEUR : la table marche "
            "sur un million de lignes."
        ),
        entry=("bretzel.ui.datatable", "bretzel.ui.column"),
        snippet=_code(
            """
            class Requete(DatatableState):
                pass

            COLONNES = [
                column("titre", "Titre", sortable=True),
                column("statut", "Statut", align="center"),
            ]

            def charger(q):
                \"\"\"Rend (lignes_de_cette_page, total).\"\"\"
                return page_de(q), total_de(q)

            datatable(state=Requete, columns=COLONNES, rows=charger,
                      exportable=True, export_filename="issues.csv")
            """
        ),
        caveat=(
            "`rows=` accepte une liste (tout en mémoire) ou un callable "
            "qui reçoit la requête — seule la seconde forme évite de "
            "charger la table entière."
        ),
    ),
    Capability(
        name="Déplacer des éléments à la souris ou au doigt",
        chapter="/drag",
        does=(
            "Réordonner une liste, faire glisser une carte d'une colonne "
            "à l'autre : on déclare la zone qui accepte et l'élément qui "
            "se saisit, et le handler reçoit d'où vient quoi et où ça va."
        ),
        entry=("bretzel.ui.draggable", "bretzel.ui.dropzone"),
        snippet=_code(
            """
            with dropzone(name="a_faire", accepts=["tache"], on_move=deplacer):
                for t in Taches().a_faire:
                    with draggable(key=t.id, group="tache"):
                        ui.card(t.titre)
            """
        ),
        caveat=(
            "`accepts=` et `group=` sont ce qui empêche une carte de "
            "tomber dans une zone qui ne la comprend pas — sans eux, "
            "toutes les zones acceptent tout."
        ),
    ),
    # ── Les surfaces et la mise en page ───────────────────────────────
    Capability(
        name="Ouvrir et fermer une surface depuis le code",
        chapter="/actions-client",
        does=(
            "Dialogues, tiroirs, popovers et menus s'ouvrent par un "
            "appel — `.open()` / `.close()` — au lieu d'un booléen "
            "d'état à câbler. C'est le défaut pour tout ce qui est "
            "purement visuel : rien à déclarer, rien à synchroniser."
        ),
        entry=(
            "bretzel.ui.dialog",
            "bretzel.ui.drawer",
            "bretzel.ui.popover",
            "bretzel.ui.dropdown",
        ),
        snippet=_code(
            """
            with dialog(title="Confirmer") as confirmation:
                ui.text("Supprimer définitivement ?")

            ui.button("Supprimer", on_click=confirmation.open())

            with drawer(side="right") as panneau:
                ui.text("Filtres")
            with popover() as infos:
                ui.text("Détail")
            with dropdown() as menu:
                ui.menu_item("Renommer")
            """
        ),
        caveat=(
            "L'impératif est le défaut pour les surfaces VISUELLES. Un "
            "composant qui porte une VALEUR (un champ, un choix) reste "
            "lié par `ClientBinding` — l'état est alors la vérité, pas "
            "l'appel."
        ),
    ),
    Capability(
        name="Geler le document et faire défiler les régions",
        chapter="/scrolling",
        does=(
            "Le modèle des outils : le cadre ne bouge pas, seules les "
            "colonnes défilent — barre latérale fixe, en-tête fixe, "
            "contenu qui défile seul. L'alternative reste le défaut : un "
            "document qui défile en entier."
        ),
        entry=("bretzel.ui.viewport", "bretzel.ui.pane"),
        snippet=_code(
            """
            with viewport(direction="row"):
                with pane(padding="md"):
                    ui.text("La colonne de gauche défile seule.")
                with pane(padding="md"):
                    ui.text("Celle de droite aussi, indépendamment.")
            """
        ),
        caveat=(
            "Les deux modèles coexistent dans le dépôt (8 apps contre "
            "10) et c'est voulu. Mélanger les deux sur une même page "
            "donne deux barres de défilement imbriquées."
        ),
    ),
    Capability(
        name="Dessiner des graphiques sans bibliothèque JS",
        chapter="/charts",
        does=(
            "Courbes, barres, camemberts, nuages de points et "
            "sparklines, rendus en SVG côté serveur — donc visibles "
            "avant que le moindre script ne tourne, et imprimables."
        ),
        entry=(
            "bretzel.ui.line_chart",
            "bretzel.ui.bar_chart",
            "bretzel.ui.pie_chart",
            "bretzel.ui.scatter_chart",
            "bretzel.ui.sparkline",
        ),
        snippet=_code(
            """
            line_chart(series=[ventes], x_labels=MOIS, height=240)
            bar_chart(series=[par_region])
            pie_chart(values=[40, 35, 25], labels=["A", "B", "C"])
            scatter_chart(series=[nuage])
            sparkline(values=[3, 5, 4, 8, 6])
            """
        ),
        caveat=(
            "C'est du SVG statique enrichi côté client : pas de zoom, "
            "pas de panoramique, pas de millions de points. Pour de "
            "l'exploration interactive, une bibliothèque dédiée reste "
            "le bon outil."
        ),
    ),
    # ── L'identité visuelle et la structure ───────────────────────────
    Capability(
        name="Changer toute l'identité visuelle depuis une palette",
        chapter="/theme",
        does=(
            "Une couleur sémantique suffit : le clair, le sombre, les "
            "états de survol et les contrastes en sont dérivés, et tous "
            "les composants suivent. Tailwind v4 est compilé par un "
            "binaire Rust — aucun Node.js en production."
        ),
        entry=("bretzel.theme.Theme", "bretzel.theme.Palette"),
        snippet=_code(
            """
            THEME = Theme(semantic={"primary": "#0f766e"})

            # Surcharger UN composant, sans toucher aux autres :
            THEME = Theme(
                semantic={"primary": "#0f766e"},
                components={"card": {"slots": {"root": "rounded-none"}}},
            )
            palette = Palette  # ce que le thème résout, clair ET sombre
            """
        ),
        caveat=(
            "Une classe Tailwind ASSEMBLÉE en f-string est invisible au "
            "compilateur de prod : le HTML est identique des deux côtés, "
            "donc la casse ne se voit QU'EN production. Classe entière "
            "dans le thème, ou safelist."
        ),
    ),
    Capability(
        name="Découper une app en fonctionnalités déclarées",
        chapter="/structure",
        does=(
            "Chaque fonctionnalité déclare son nom, sa nature et ce "
            "qu'elle fournit ; le graphe est vérifié au démarrage — "
            "dépendance inconnue, cycle, collision de noms sont des "
            "erreurs, pas des surprises à l'exécution."
        ),
        entry=("bretzel.Feature",),
        snippet=_code(
            """
            feature = Feature(
                name="access",
                kind="logic",
                provides=[current_user, sign_out],
            )
            """
        ),
        caveat=(
            "La mécanique de découverte (manifeste, `include` contre "
            "balayage) est délibérément DIFFÉRÉE : `app.include(module)` "
            "reste la façon de monter une fonctionnalité."
        ),
    ),
    Capability(
        name="Parler la langue de qui visite",
        chapter="/languages",
        does=(
            "Les mots que le framework rend lui-même — « Rechercher… », "
            "« Fermer l'alerte », les libellés de pagination — sont "
            "traduits par requête, négociés depuis l'en-tête du "
            "navigateur et surchargeables par un cookie."
        ),
        entry=("bretzel.render.Language", "bretzel.render.text"),
        snippet=_code(
            """
            app = Bretzel(
                lang="fr", languages=["fr", "en"],
                texts={"fr": {"alert.dismiss": "Fermer"}},
            )

            # Dans une page, lire la langue résolue pour CETTE requête :
            ui.text(f"langue = {Language().code}")
            # Et réutiliser le vocabulaire du framework :
            ui.text(text("alert.dismiss"))
            """
        ),
        caveat=(
            "Ça couvre le vocabulaire DU FRAMEWORK. Les phrases de "
            "l'app restent à sa charge — il n'y a pas de système "
            "d'internationalisation applicatif (prévu en 2.1)."
        ),
    ),
    # ── Le framework qui se regarde lui-même ──────────────────────────
    Capability(
        name="Demander au framework ce qu'il expose",
        chapter="/tree",
        does=(
            "Interroger le code INSTALLÉ : la fiche d'un composant avec "
            "ses paramètres, ses slots et ses events ; l'arbre des "
            "paquets ; la surface d'un module classée par besoin. Rien "
            "n'est recopié, donc rien ne peut dériver."
        ),
        entry=("bretzel.introspect.describe", "bretzel.introspect.index"),
        snippet=_code(
            """
            # En ligne de commande :
            #   py -m bretzel.cli.main describe hstack
            #   py -m bretzel.cli.main describe capabilities
            print(describe("hstack"))
            print(index())          # toute la surface ui.*, une ligne par symbole
            """
        ),
        caveat=(
            "La sortie est en UTF-8, flèches et guillemets compris : sur "
            "une console Windows en cp1252, un `print` nu lève. Le CLI "
            "s'en charge, un script maison doit le faire aussi."
        ),
    ),
    Capability(
        name="Faire juger son propre code par le framework",
        chapter="/structure",
        does=(
            "Dix règles qui attrapent ce qu'aucun test ne voit : le "
            "kwarg mort (il ne lève pas, ne s'affiche pas, ne se voit "
            "pas en revue), des champs frères à des tailles différentes, "
            "un cast qui efface la provenance d'une valeur et casse la "
            "resynchronisation."
        ),
        entry=("bretzel.lint.run", "bretzel.lint.available_rules"),
        snippet=_code(
            """
            # En ligne de commande :
            #   py -m bretzel.cli.main check examples
            rapport = run(["examples"])
            print(rapport.exit_code, len(rapport.findings))

            # Ce que l'outil sait vérifier, énumérable à dessein :
            for regle in available_rules():
                print(regle)
            """
        ),
        caveat=(
            "Ce sont des RÈGLES, pas un reflet du code — c'est la "
            "moitié arrachable du framework, et le contrat "
            "`lint-stays-extractable` de `.importlinter` la garde "
            "détachable."
        ),
    ),
    Capability(
        name="Valider une donnée là où elle vit",
        chapter="/forms",
        does=(
            "Attacher une règle à un CHAMP d'état typé plutôt qu'à un "
            "formulaire. Elle tourne à chaque affectation — donc aussi "
            "bien depuis le formulaire que depuis un import ou un "
            "handler appelé d'ailleurs."
        ),
        entry=("bretzel.state.validator", "bretzel.ui.form",
               "bretzel.ui.form_field"),
        snippet=(
            "class Inscription(SessionState):\n"
            '    email: str = field(default="")\n'
            "\n"
            '    @validator("email")\n'
            "    def _valide(self, valeur: str) -> str:\n"
            "        valeur = valeur.strip().lower()\n"
            '        if "@" not in valeur:\n'
            '            raise ValueError("Adresse invalide.")\n'
            "        return valeur          # il NORMALISE aussi\n"
            "\n"
            "with ui.form(on_submit=enregistrer):\n"
            '    with ui.form_field(label="Email", error=erreur):\n'
            '        ui.input(name="email")\n'
        ),
        caveat=(
            "Une règle posée sur la VUE ne couvre que le chemin qui "
            "passe par la vue. Une app a plusieurs chemins d'écriture et "
            "un seul formulaire — c'est pour ça que le validateur vit "
            "sur le champ, pas sur le `ui.form`."
        ),
    ),
    Capability(
        name="Garder l'état après un redémarrage",
        chapter="/config",
        does=(
            "Brancher un magasin partagé — Redis — pour que les portées "
            "session et utilisateur survivent au redémarrage du process "
            "et se partagent entre plusieurs instances. Une URL, et rien "
            "d'autre à changer dans le code."
        ),
        entry=("bretzel.BretzelConfig",),
        snippet=(
            "# Sans Redis, l'état vit en mémoire et meurt avec le\n"
            "# process. Parfait en dev, faux dès qu'il y a deux\n"
            "# instances derrière un répartiteur de charge.\n"
            "app = Bretzel(\n"
            '    secret_key="…",\n'
            '    redis_url="redis://localhost:6379/0",\n'
            "    session_max_age_days=30,\n"
            ")\n"
            "\n"
            "# `BretzelConfig` porte le contrat complet des réglages.\n"
            "print(BretzelConfig.__doc__)\n"
        ),
        caveat=(
            "Ce n'est pas une base de données : l'état d'écran n'est pas "
            "vos données métier. Un panier qu'on doit retrouver dans six "
            "mois va en base, pas dans une `SessionState`."
        ),
    ),
    Capability(
        name="Refuser un double-clic et un rejeu",
        chapter="/actions-server",
        does=(
            "Marquer une action pour qu'un second envoi du même rendu ne "
            "l'exécute pas deux fois. La signature porte déjà un "
            "horodatage signé — le rejeu tardif est refusé par le socle, "
            "sans qu'on écrive quoi que ce soit."
        ),
        entry=("bretzel.idempotent",),
        snippet=(
            "from bretzel import idempotent\n"
            "\n"
            "@idempotent\n"
            "def payer() -> None:\n"
            '    """Un double-clic ne débite pas deux fois."""\n'
            "    facturer(Panier().total)\n"
        ),
        caveat=(
            "L'anti-rejeu livré est un horodatage SIGNÉ plus ce "
            "décorateur, pas une table de jetons à usage unique : la "
            "signature est calculée au RENDU, elle ne peut donc pas "
            "couvrir le corps de la requête. Rejouer n'escalade aucun "
            "privilège — le double-clic est le vrai sujet."
        ),
    ),
    Capability(
        name="Développer sans build ni rechargement manuel",
        chapter="/config",
        does=(
            "Un seul mot bascule tout l'outillage : rechargement du "
            "serveur au moindre fichier touché, CSS compilé dans le "
            "navigateur, traces complètes. En production le CSS est "
            "compilé en amont par un binaire, et il n'y a aucun Node.js."
        ),
        entry=("bretzel.Bretzel",),
        snippet=(
            "app = Bretzel(\n"
            '    secret_key="…",\n'
            '    mode="dev",            # ou "prod"\n'
            ")\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    app.run(port=8000, reload=True)\n"
        ),
        caveat=(
            "Le rechargement lance uvicorn dans un processus ENFANT. Un "
            "parent tué sans propager laisse cet enfant tenir le port, "
            "et le lancement suivant ne peut plus s'y lier — mesuré, et "
            "l'erreur ne remonte pas toujours jusqu'à l'écran."
        ),
    ),
)


def capability_names() -> tuple[str, ...]:
    """Les titres, dans l'ordre de la liste."""
    return tuple(c.name for c in CAPABILITIES)


def render_capabilities() -> str:
    """La liste en texte — ce que rend ``bretzel describe capabilities``."""
    lignes = [f"## Ce que Bretzel sait faire ({len(CAPABILITIES)})", ""]
    for cap in CAPABILITIES:
        lignes.append(f"  {cap.name}")
        lignes.append(f"    {cap.does}")
        lignes.append(f"    Entrées : {', '.join(cap.entry)}")
        lignes.append(
            f"    Chapitre : {cap.chapter}" if cap.chapter
            else "    Chapitre : (pas encore écrit)"
        )
        for ligne in cap.snippet.splitlines():
            lignes.append(f"      {ligne}")
        if cap.caveat:
            lignes.append(f"    ⚠️ {cap.caveat}")
        lignes.append("")
    return "\n".join(lignes)


__all__ = ["CAPABILITIES", "Capability", "capability_names", "render_capabilities"]
