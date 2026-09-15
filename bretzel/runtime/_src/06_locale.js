/* 06_locale.js — les noms de mois et de jours, dérivés de la langue.
 *
 * ⚠️ **Le numéro 06 est une CONTRAINTE D'ORDRE, pas une identité.** Ce
 * slab s'appelait ``22_locale.js`` jusqu'au 2026-08-27, donc chargé QUINZE
 * slabs après son unique consommateur, ``07_calendar.js``. Or celui-ci
 * appelle ``customElements.define('bz-calendar', …)``, ce qui met à niveau
 * IMMÉDIATEMENT tous les calendriers déjà dans le DOM — leur constructeur
 * lit alors ``$bz.locale.weekdayNames()`` sur un ``$bz.locale`` qui
 * n'existe pas encore.
 *
 * Mesuré : **une exception jetée par calendrier**, soit 54 sur la page
 * ``/calendar`` du playground, 44 sur ``/date_picker``, 45 sur
 * ``/date_range_picker``, 35 sur ``/month_picker``. L'écran s'en remettait
 * — la directive ``bz-text`` repasse plus tard — mais le flot d'erreurs
 * empêchait ``networkidle`` d'arriver, et ``pytest -m audit`` PENDAIT
 * dessus. Une suite d'une heure rendue inutilisable par une ligne d'ordre.
 *
 * Ce fichier ne dépend de rien (il crée ``window.$bz`` si besoin), donc il
 * pourrait vivre n'importe où avant 07. Il est posé JUSTE avant son
 * consommateur pour qu'un lecteur qui se demande « pourquoi ici ? »
 * trouve la réponse à la ligne suivante du dossier.
 *
 * Gardé par ``tests/runtime_js/test_no_page_throws_on_load.py``, qui
 * charge les 74 pages de composants et exige ZERO exception. Une gate
 * STATIQUE (interdire de lire un ``$bz.<ns>`` posé plus tard) a été
 * écartée après mesure : 9 cas dans le dépôt, et les 9 sont légitimes
 * — des lectures DIFFÉRÉES, dans des fonctions appelées bien après le
 * chargement. Ce qui distingue le défaut, c'est le MOMENT de la
 * lecture, et seul un navigateur le sépare.
 *
 * Exposé en window.$bz.locale, lu par 07_calendar.js et par les
 * expressions bz-* (``bz-text="$bz.locale.monthName(month)"``).
 *
 * Pourquoi ici plutôt que côté serveur
 * -------------------------------------
 * Python n'a aucun moyen sûr de nommer un mois dans une langue donnée :
 * le module ``locale`` de la stdlib est un état GLOBAL au processus (et
 * dépend des locales installées sur la machine), et Babel serait une
 * dépendance — que le charter exclut. Le navigateur, lui, embarque déjà
 * la table complète : ``Intl.DateTimeFormat`` la donne pour n'importe
 * quelle étiquette BCP-47, sans un octet de plus.
 *
 * La langue vient de ``<html lang>``, que ``Bretzel(lang=...)`` pose —
 * pas d'un attribut ad hoc. C'est l'endroit standard, celui qu'un
 * lecteur d'écran lit déjà pour choisir sa voix, et le seul qui reste
 * juste si l'app le change à la main.
 *
 *   $bz.locale.tag()            l'étiquette courante ("fr", "en"…)
 *   $bz.locale.monthNames()     12 noms longs, janvier en tête
 *   $bz.locale.monthName(i)     un seul, 0-indexé
 *   $bz.locale.weekdayNames()     7 noms courts, DIMANCHE en tête
 *   $bz.locale.weekdayLongNames() les mêmes en entier, pour un ``title=``
 *
 * ⚠️ Dimanche en tête, toujours : c'est l'ordre de ``Date.getDay()``, et
 * c'est le composant qui fait tourner la liste selon ``weekstart``. Une
 * liste écrite lundi-première — le réflexe français — décale toutes les
 * colonnes d'un jour (piège [14] du chantier CRM).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // Repli si le moteur n'a pas d'Intl utilisable, ou si l'étiquette est
  // invalide (Intl LÈVE sur "français"). C'est exactement ce que le
  // framework rendait avant, donc un repli ne change rien pour personne.
  const FALLBACK_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const FALLBACK_WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  // 2023-01-01 EST un dimanche, et 2023 a douze mois — les deux ancres
  // dont on a besoin. Tout est calculé en UTC : construire ces dates en
  // heure locale décalerait d'un jour à l'ouest de Greenwich, donc le
  // nom du jour aussi.
  const SUNDAY = Date.UTC(2023, 0, 1);
  const DAY_MS = 86400000;

  const memo = Object.create(null);

  function names(tag) {
    let entry = memo[tag];
    if (entry) return entry;
    try {
      const month = new Intl.DateTimeFormat(tag, {
        month: "long",
        timeZone: "UTC",
      });
      const weekday = new Intl.DateTimeFormat(tag, {
        weekday: "short",
        timeZone: "UTC",
      });
      // Le nom ENTIER, pour le ``title=`` des en-tetes de colonne. Meme
      // memo, meme construction : sept appels de plus, une seule fois par
      // etiquette de langue, jamais par calendrier.
      const weekdayLong = new Intl.DateTimeFormat(tag, {
        weekday: "long",
        timeZone: "UTC",
      });
      entry = {
        months: FALLBACK_MONTHS.map(function (_, i) {
          return month.format(new Date(Date.UTC(2023, i, 15)));
        }),
        weekdays: FALLBACK_WEEKDAYS.map(function (_, i) {
          return weekday.format(new Date(SUNDAY + i * DAY_MS));
        }),
        weekdaysLong: FALLBACK_WEEKDAYS.map(function (_, i) {
          return weekdayLong.format(new Date(SUNDAY + i * DAY_MS));
        }),
      };
    } catch (e) {
      // Le repli n'a QUE des abreviations. ``weekdaysLong`` y vaut donc
      // la meme chose : un ``title`` identique au texte visible est
      // inutile mais jamais faux, la ou inventer un nom entier le serait.
      entry = {
        months: FALLBACK_MONTHS,
        weekdays: FALLBACK_WEEKDAYS,
        weekdaysLong: FALLBACK_WEEKDAYS,
      };
    }
    memo[tag] = entry;
    return entry;
  }

  $bz.locale = {
    tag: function () {
      return (document.documentElement.getAttribute("lang") || "en").trim() || "en";
    },
    monthNames: function () {
      return names(this.tag()).months;
    },
    monthName: function (index) {
      return this.monthNames()[index] || "";
    },
    weekdayNames: function () {
      return names(this.tag()).weekdays;
    },
    weekdayLongNames: function () {
      return names(this.tag()).weekdaysLong;
    },
  };
})();
