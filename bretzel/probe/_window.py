"""Une fenêtre — un contexte de navigateur, sa page, ce qu'elle a vu.

Une fenêtre est un contexte Playwright, pas un onglet : cookies et
stockage lui appartiennent, donc deux fenêtres sont deux SESSIONS. C'est
la seule façon de mesurer ce qui fait un framework fullstack — ce qu'une
session écrit et qu'une autre doit voir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bretzel.probe._settle import settle_page

#: Combien de temps un élément a le droit de se faire attendre avant que
#: le harnais déclare qu'il ne viendra pas. Même ordre que les attentes
#: écrites à la main dans les probes du dépôt (5 s).
APPEAR_MS = 5000


@dataclass(frozen=True, slots=True)
class Box:
    """Describe an element's geometry in CSS pixels."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2


@dataclass(frozen=True, slots=True)
class Seen:
    """Une requête vue partir depuis une fenêtre."""

    method: str
    url: str
    kind: str


class ElementNotFoundError(LookupError):
    """Raised when a selector matches no element in a probe window."""


class DropMissedError(AssertionError):
    """Raised when a drag operation does not land on its intended target."""


class Window:
    """Control one browser window during a probe."""

    def __init__(self, page: Any, base_url: str, out: Path, name: str) -> None:
        self.page = page
        self.name = name
        self._base = base_url.rstrip("/")
        self._out = out
        self.errors: list[str] = []
        self.console: list[str] = []
        self.broken: list[str] = []
        self._seen: list[Seen] = []
        self._wire()

    # ── ce que la fenêtre enregistre toute seule ──────────────────────
    #
    # L'ancien harnais se contentait d'IMPRIMER les erreurs JS, et ça a
    # coûté : 178 exceptions ont vécu deux jours dans une sortie que
    # personne ne lit tant qu'un test ne tombe pas. Ici on collecte, et
    # le balayage final asserte.
    def _wire(self) -> None:
        self.page.on("pageerror", lambda err: self.errors.append(str(err)))
        self.page.on(
            "console",
            lambda msg: (
                self.console.append(f"{msg.type}: {msg.text}")
                if msg.type in ("error", "warning")
                else None
            ),
        )
        self.page.on("request", self._note)
        self.page.on("response", self._note_response)

    def _note_response(self, response: Any) -> None:
        if not response.url.startswith(self._base):
            return
        if response.status >= 400:
            self.broken.append(
                f"{response.status} {response.url[len(self._base):]}"
            )

    def _note(self, request: Any) -> None:
        if not request.url.startswith(self._base):
            return
        # `eventsource` est exclu volontairement : le flux SSE d'une zone
        # `broadcast=` ne se ferme jamais, le compter ferait mentir tout
        # décompte de geste.
        if request.resource_type not in ("fetch", "xhr", "document"):
            return
        self._seen.append(
            Seen(request.method, request.url[len(self._base):], request.resource_type)
        )

    # ── agir ──────────────────────────────────────────────────────────
    def goto(self, path: str) -> None:
        if not path.startswith("/"):
            # Sans ce refus, Playwright rend « Cannot navigate to invalid
            # URL » avec la pile complète. Le cas arrive pour de vrai :
            # sous Git Bash, un `--route /x` est réécrit en chemin Windows
            # avant même d'atteindre Python (mesuré le 2026-09-10).
            raise ValueError(
                f"une route commence par « / » — reçu {path!r}. Sous Git "
                "Bash, préfixe la commande de MSYS_NO_PATHCONV=1."
            )
        # `wait_until="load"` et pas `networkidle` : une page qui porte
        # une zone `broadcast=` ouvre un EventSource, donc l'inactivité
        # réseau n'arrive jamais et le goto expire à 30 s.
        self.page.goto(self._base + path, wait_until="load")
        # `load` est déjà passé : rien n'est en train de débouncer, donc
        # le plancher anti-debounce n'aurait rien à couvrir.
        self.settle(floor=0)

    def click(self, sel: str) -> None:
        self._one(sel).click()

    def type(self, sel: str, text: str) -> None:
        """Type text one key at a time."""
        el = self._one(sel)
        el.click()
        el.press_sequentially(text, delay=15)

    def press(self, keys: str) -> None:
        self.page.keyboard.press(keys)

    def hover(self, sel: str) -> None:
        self._one(sel).hover()

    def drag(self, src: str, dst: str) -> None:
        """Perform a drag with real mouse gestures."""
        mouse = self.page.mouse
        ax, ay = self.box(src).center
        mouse.move(ax, ay)
        mouse.down()
        bx, by = self.box(dst).center
        self._glide(ax, ay, bx, by)
        # La cible a bougé sous le geste : on refait le dernier segment
        # vers là où elle est MAINTENANT. Sans déplacement c'est une
        # série de mouvements sur place, que le moteur encaisse.
        cx, cy = self.box(dst).center
        self._glide(bx, by, cx, cy)
        self._assert_landed(dst)
        mouse.up()

    #: Où est l'élément en cours de glissement, à cet instant. Le moteur
    #: pose ``data-bz-dragging`` à l'ouverture du geste et le retire au
    #: relâchement, donc cette fenêtre-là est la seule où la question a
    #: une réponse.
    _LANDED_JS = """
    (sel) => {
        const item = document.querySelector('[data-bz-dragging]');
        // Pas de glisser de NŒUD en cours : curseur d'un slider, poignée
        // de `ui.resizable`… Rien à vérifier, et surtout rien à refuser.
        if (!item) return null;
        const cible = document.querySelector(sel);
        if (!cible) return null;
        const zone = item.closest('[data-bz-dropzone]');
        return {
            ok: cible.contains(item),
            zone: zone ? zone.getAttribute('data-bz-dropzone') : null,
        };
    }
    """

    def _assert_landed(self, dst: str) -> None:
        """Juste avant de lâcher : l'élément est-il DANS la cible ?

        Le re-visé ne suffit pas à le garantir. Il se prouve pour des
        zones SŒURS d'un même flux — retirer l'élément de sa zone
        actuelle décale la cible d'une hauteur d'élément, l'y déposer la
        fait grandir d'autant, et les deux se compensent au bord qui
        compte. Il cesse de se prouver dès que le segment de correction
        traverse une TROISIÈME zone, ce qui demande un élément plus haut
        qu'une zone intermédiaire — une géométrie que rien n'interdit.

        D'où cette vérification plutôt qu'un raisonnement : elle coûte un
        aller-retour et transforme un atterrissage muet en erreur qui
        nomme le harnais. C'est la moitié qui manquait au re-visé, et
        elle existait déjà à la main dans ``probe_kanban``.
        """
        landed = self.page.evaluate(self._LANDED_JS, dst)
        if landed is None or landed["ok"]:
            return
        self.page.mouse.up()  # ne pas laisser un bouton enfoncé derrière soi
        raise DropMissedError(
            f"[{self.name}] le glisser visait {dst!r} et l'élément est "
            f"dans {landed['zone']!r} au moment de lâcher.\n"
            "Le harnais vise le CENTRE de la cible ; une zone qui porte "
            "déjà des éléments peut demander un point plus haut."
        )

    def _glide(self, ax: float, ay: float, bx: float, by: float) -> None:
        """Douze pas de souris de (ax, ay) vers (bx, by)."""
        mouse = self.page.mouse
        steps = 12
        for i in range(1, steps + 1):
            mouse.move(ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps)

    # ── lire ──────────────────────────────────────────────────────────
    def has(self, sel: str) -> bool:
        return self.page.locator(sel).count() > 0

    def count(self, sel: str) -> int:
        return int(self.page.locator(sel).count())

    def text(self, sel: str) -> str:
        return (self._one(sel).inner_text() or "").strip()

    def value(self, sel: str) -> str:
        return str(self._one(sel).input_value())

    def box(self, sel: str) -> Box:
        raw = self._one(sel).bounding_box()
        if raw is None:
            raise ElementNotFoundError(
                f"[{self.name}] {sel!r} existe mais n'a pas de géométrie "
                "(display:none, ou détaché)."
            )
        return Box(raw["x"], raw["y"], raw["width"], raw["height"])

    def css(self, sel: str, prop: str) -> str:
        return str(
            self._one(sel).evaluate(
                "(el, p) => getComputedStyle(el).getPropertyValue(p)", prop
            )
        )

    def shot(self, name: str) -> Path:
        path = self._out / f"{self.name}-{name}.png"
        self.page.screenshot(path=str(path), full_page=False)
        return path

    # ── attendre ──────────────────────────────────────────────────────
    def settle(self, *, timeout: float = 5.0, floor: int | None = None) -> str:
        return settle_page(
            self.page,
            timeout=timeout,
            **({} if floor is None else {"floor": floor}),
        )

    def resize(self, size: tuple[int, int]) -> None:
        self.page.set_viewport_size({"width": size[0], "height": size[1]})

    def mark(self) -> int:
        """Return the number of requests observed by this window so far."""
        return len(self._seen)

    def since(self, mark: int) -> tuple[Seen, ...]:
        """Return requests observed since ``mark``."""
        return tuple(self._seen[mark:])

    def _one(self, sel: str) -> Any:
        """Le premier élément désigné — en l'ATTENDANT s'il arrive.

        ``count()`` est un instantané, et un probe agit presque toujours
        sur quelque chose qu'un geste précédent vient de faire apparaître.
        Refuser tout de suite obligeait chaque appelant à faire précéder
        son clic d'une attente écrite à la main : mesuré en portant
        ``probe_messagerie`` le 2026-09-11, six fois dans un seul
        fichier, pour un bouton qui arrivait 200 ms plus tard.

        C'est bien une attente d'ÉTAT, pas une durée : elle rend la main
        dès que le nœud est attaché. Le plafond n'est là que pour dire
        « il ne viendra pas » au lieu de pendre.

        ⚠️ Ne vaut QUE pour les éléments sur lesquels on agit ou qu'on
        lit. :meth:`has` et :meth:`count` interrogent le DOM directement,
        et doivent le faire : une attente les ferait mentir sur une
        absence, qui est souvent ce qu'on mesure.
        """
        # Import différé, comme ``_browser`` : Playwright est un extra de
        # développement, et ``import bretzel.probe`` ne doit pas en
        # dépendre. On attrape l'expiration SEULE — un sélecteur mal
        # formé doit lever tel quel, pas se déguiser en « rien ne
        # correspond ».
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        loc = self.page.locator(sel).first
        try:
            loc.wait_for(state="attached", timeout=APPEAR_MS)
        except PlaywrightTimeout as exc:
            raise ElementNotFoundError(
                f"[{self.name}] rien ne correspond à {sel!r} après "
                f"{APPEAR_MS / 1000:g} s."
            ) from exc
        return loc
