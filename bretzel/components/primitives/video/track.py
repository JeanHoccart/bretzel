"""``Track`` — une piste de sous-titres décrite en données.

Pourquoi un descripteur et pas des enfants
-------------------------------------------
Le HTML met les pistes DANS la balise ::

    <video src="demo.mp4" controls>
      <track kind="captions" src="fr.vtt" srclang="fr" label="Français" default>
    </video>

:class:`~bretzel.components.Video` ne peut pas suivre cette forme sans
cesser d'être une **feuille** (``IS_CONTAINER = False``), et ce contrat
est ce qui empêche aujourd'hui d'y glisser un bouton ou un tableau — que
le navigateur avalerait sans un mot. Une piste n'a de toute façon aucun
balisage à porter : elle est faite d'attributs, tous les cinq connus
d'avance. On la décrit donc, comme :class:`~bretzel.components.Series`
décrit une série de graphique et ``ui.column`` une colonne de tableau.

Le gain qui compte est ailleurs que dans la syntaxe : un objet typé se
relit. ``srclang`` et ``label`` sont ici des champs OBLIGATOIRES, donc
une piste sans langue ni nom de menu ne se construit pas — alors qu'une
chaîne HTML brute passée à ``ui.html`` ne se fait juger par personne.
C'est un trou d'accessibilité qu'on ferme ; le fermer à moitié n'aurait
pas de sens.

``kind="metadata"`` n'est pas accepté
--------------------------------------
Les quatre valeurs de :data:`TRACK_KINDS` s'adressent toutes à un humain
et se pilotent depuis les contrôles du navigateur. ``metadata`` est le
seul ``kind`` qui ne s'adresse qu'à du JS (vignettes de survol, marqueurs
d'un lecteur maison) — il n'a ni langue ni libellé de menu à porter, donc
les deux champs obligatoires ci-dessus n'auraient aucun sens pour lui, et
``ui.video`` a tranché au cadrage qu'il n'est pas un lecteur. Le jour où
le besoin remonte, il remonte avec sa forme.
"""

from __future__ import annotations

from dataclasses import dataclass

from bretzel.components.base import ComponentUsageError

#: Les ``kind`` acceptés. ``metadata`` en est absent volontairement —
#: cf. la docstring du module.
TRACK_KINDS: tuple[str, ...] = (
    "captions",
    "subtitles",
    "descriptions",
    "chapters",
)


@dataclass(frozen=True, slots=True)
class Track:
    """Une piste temporelle d'un média — sous-titres, description, chapitres.

    - ``src`` est l'URL du fichier WebVTT.
    - ``srclang`` est le code langue BCP 47 de la piste (``"fr"``,
      ``"en-GB"``). Obligatoire : sans lui le navigateur ne peut pas
      choisir la piste selon la langue du lecteur, et le HTML l'exige
      pour ``kind="subtitles"``.
    - ``label`` est le nom affiché dans le menu des sous-titres.
      Obligatoire : sans lui le menu propose une entrée sans nom, ce qui
      rend le choix impossible dès qu'il y a deux pistes.
    - ``kind`` vaut ``"captions"`` par défaut — la transcription du
      dialogue ET des sons signifiants, donc le choix utile au plus grand
      nombre. ``"subtitles"`` ne transcrit que la parole (traduction),
      ``"descriptions"`` décrit l'image pour qui ne la voit pas,
      ``"chapters"`` découpe la timeline.
    - ``default`` désigne la piste activée si le navigateur n'a pas
      d'autre préférence. Au plus une par ``kind``.
    """

    src: str
    srclang: str
    label: str
    kind: str = "captions"
    default: bool = False

    def __post_init__(self) -> None:
        if self.kind not in TRACK_KINDS:
            raise ComponentUsageError(
                f"ui.track: kind={self.kind!r} inconnu — les valeurs sont "
                f"{', '.join(TRACK_KINDS)}. ``metadata`` n'est pas accepté : "
                f"il ne s'adresse qu'à du JS, et ui.video n'est pas un "
                f"lecteur (cf. sa docstring)."
            )
        for field_name in ("src", "srclang", "label"):
            if not getattr(self, field_name).strip():
                raise ComponentUsageError(
                    f"ui.track: {field_name}= est vide. Les trois sont "
                    f"obligatoires — une piste sans langue ni libellé "
                    f"n'est pas choisissable dans le menu, et c'est "
                    f"précisément ce que cette API existe pour empêcher."
                )


# Sucre exposé en ``ui.track(...)``, pour que le code utilisateur n'ait
# pas à importer la dataclass — même geste que ``ui.column``.
def track(
    src: str,
    *,
    srclang: str,
    label: str,
    kind: str = "captions",
    default: bool = False,
) -> Track:
    """Construit un :class:`Track`. Sucre pour ``ui.track(...)``."""
    return Track(
        src=src, srclang=srclang, label=label, kind=kind, default=default,
    )
