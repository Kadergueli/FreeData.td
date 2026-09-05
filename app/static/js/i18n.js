/**
 * FreeData.td — i18n Module
 *
 * Centralised translations for French (default) and English.
 * Usage: import { t, setLang, getLang } from './i18n.js';
 *        t('home.title')   → translated string
 */

const TRANSLATIONS = {
  fr: {
    // ── Navigation ──
    nav: {
      mission:    'Mission',
      explorer:   'Explorateur',
      repository: 'Répertoire',
      sources:    'Sources',
      insights:   'IA & Analyses',
      api:        'Export & API',
      status:     'Statut',
      terms:      'Conditions & Licence',
    },

    // ── Common ──
    common: {
      active:      'ACTIF',
      beta:        'BÊTA',
      planned:     'PLANIFIÉ',
      no_data:     'AUCUNE DONNÉE',
      loading:     'Chargement…',
      error:       'Erreur de connexion à l\'API.',
      explore:     'EXPLORER',
      collect:     'COLLECTER EN DIRECT',
      harvest_ok:  'Collecte réussie ! La base de données a été alimentée.',
      harvest_err: 'Erreur de collecte',
      records:     'ENREGISTREMENTS',
      source:      'SOURCE',
      validated:   'VALIDÉ',
      date:        'Date inconnue',
      location:    'Tchad',
      health:      'SCORE DE SANTÉ',
      refresh:     'MISE À JOUR : TEMPS RÉEL',
      open:        'OUVRIR',
      uptime:      'DISPONIBILITÉ',
      latency:     'LATENCE',
      status_ok:   'STATUT : OPÉRATIONNEL',
      copied:      'COPIÉ !',
      lang_label:  'FR',
    },

    // ── Footer ──
    footer: {
      text: 'FreeData.td — Infrastructure de Données Ouvertes pour le Tchad',
      node: 'Nœud National : TD-PROD-01',
    },

    // ── Home ──
    home: {
      title:        'INFRASTRUCTURE DE DONNÉES OUVERTES POUR LE TCHAD',
      subtitle:     'Rendre les données du Tchad accessibles, fiables et utiles pour tous.',
      hero_sub:     'INFRASTRUCTURE DE DONNÉES OUVERTES',
      hero_tagline: 'Rendre les données du Tchad accessibles, fiables et utiles pour tous.',
      btn_explore:  'EXPLORER LES DONNÉES',
      btn_harvest:  'COLLECTE EN DIRECT',
      btn_harvest_loading: 'Collecte depuis Open-Meteo & FAOSTAT…',
      stat_obs:     'OBSERVATIONS EN BASE',
      stat_score:   'SCORE DE VALIDATION',
      stat_logs:    'JOURNAUX D\'AUDIT',
      stat_sectors: 'SECTEURS ACTIFS',
      mission_title: 'MISSION & FONCTIONNALITÉS',
      mission_text:  'FreeData.td est l\'infrastructure numérique ouverte dédiée à l\'agrégation, la vérification et la libre distribution des données statistiques socio-économiques du Tchad. En centralisant les séries temporelles issues des organismes publics nationaux et internationaux, la plateforme garantit un accès libre, transparent et standardisé pour soutenir la recherche, la prise de décision et l\'innovation.',
      capabilities: [
        { icon: 'database',    title: 'Agrégation Multi-Sources', desc: 'Ingestion automatique auprès de 10 institutions officielles (INSEED, BEAC, Banque Mondiale, FAOSTAT, OMS, UNESCO...)' },
        { icon: 'shield-check',title: 'Contrôle Qualité & IA',     desc: 'Normalisation structurelle, détection d\'anomalies et validation stricte des séries temporelles.' },
        { icon: 'code-2',      title: 'APIs & Exports Ouverts',    desc: 'Endpoints REST haute performance, téléchargements CSV/JSON/Excel et licence libre CC BY 4.0.' },
        { icon: 'line-chart',  title: 'Visualisation & Analytics', desc: 'Tableaux de bord sectoriels dynamiques, graphiques interactifs et synthèses analytiques.' },
      ],
      pipeline_title: 'PIPELINE DE DONNÉES',
      pipeline: [
        { num: '01', title: 'INGESTION', desc: 'Collecte automatisée depuis FAOSTAT, NASA et la Banque mondiale.' },
        { num: '02', title: 'NETTOYAGE', desc: 'Contrôle qualité et validation structurelle des observations brutes.' },
        { num: '03', title: 'DISTRIBUTION', desc: 'APIs publiques, exports CSV et tableaux de bord analytiques interactifs.' },
      ],
      sectors_title: 'SECTEURS ACTIFS',
      latest_title:  'DERNIÈRE DONNÉE VALIDÉE EN BASE',
      loading_db:    'Chargement des données depuis la base…',
      no_obs:        'Aucune donnée en base. Cliquez sur "COLLECTE EN DIRECT" pour alimenter la base.',
    },

    // ── Sectors ──
    sectors: {
      title:         'EXPLORATEUR D\'INFRASTRUCTURE',
      search:        'RECHERCHER UN SECTEUR OU UNE SOURCE…',
      total_sources: 'TOTAL SOURCES',
      val_score:     'SCORE VALIDATION',
      active_title:  'SECTEURS ACTIFS',
      explore_data:  'EXPLORER LES DONNÉES',
      names: {
        agriculture: 'AGRICULTURE',
        environment: 'ENVIRONNEMENT',
        markets:     'MARCHÉS & PRIX',
        transport:   'TRANSPORT',
        education:   'ÉDUCATION',
        economy:     'ÉCONOMIE',
      },
    },

    // ── Sources ──
    sources: {
      title:        'RÉPERTOIRE DES 10 SOURCES OFFICIELLES',
      subtitle:     'TRANSPARENCE, CONDITIONS D\'UTILISATION ET ACCÈS DIRECT AUX PORTAILS OFFICIELS',
      search:       'RECHERCHER UNE SOURCE, UN ORGANISME OU UNE LICENCE…',
      badge_count:  '10 SOURCES OFFICIELLES VÉRIFIÉES',
      open_portal:  'ACCÉDER AU PORTAIL OFFICIEL',
      org_label:    'Organisme émetteur',
      license_label: 'Licence d\'utilisation',
    },

    // ── Data ──
    data: {
      title:        'RÉPERTOIRE DE DONNÉES OUVERTES',
      search:       'RECHERCHER PAR INDICATEUR, SOURCE OU RÉGION…',
      sectors_label: 'SECTEURS D\'ACTIVITÉ',
      obs_header:   'OBSERVATIONS',
      sort_label:   'Trier par : DATE',
      load_more:    'CHARGER PLUS DE DONNÉES',
      loading_db:   'Interrogation de la base de données…',
      trend_title:  'TENDANCE TEMPORELLE DES DONNÉES',
      trend_footer: 'HISTORIQUE ALIMENTÉ PAR LA BASE DE DONNÉES',
      live:         'API LIVE',
      harvest_loading: 'Collecte en cours…',
      empty_msg:    'Aucune donnée disponible en base pour le secteur',
      empty_btn:    'LANCER UNE COLLECTE AUTOMATIQUE',
      filter_all:   'TOUS',
    },

    // ── Insights ──
    insights: {
      agent_log:   'AGENT D\'ANALYSE IA',
      title:       'ANALYSES ET ÉTUDES IA',
      subtitle:    'EXPLORATION AUTOMATISÉE DE LA BASE & GÉNÉRATION DE RAPPORTS LLM',
      status_active:   'STATUT : ACTIF',
      status_thinking: 'STATUT : EN COURS…',
      status_done:     'STATUT : TERMINÉ',
      density_title:   'Densité des Données par Région',
      density_desc:    'Distribution des enregistrements par station et région du Tchad.',
      studies_title:   'Analyses et Études IA',
      btn_run:         'GÉNÉRER UNE ÉTUDE IA',
      btn_run_loading: 'EXÉCUTION DE L\'AGENT DE SYNTHÈSE IA…',
      btn_run_new:     'GÉNÉRER UNE NOUVELLE ÉTUDE IA',
      placeholder:     'Cliquez sur "GÉNÉRER UNE ÉTUDE IA" pour exécuter l\'Agent sur les données en base.',
      running_msg:     'L\'AnalysisAgent analyse les données pour le secteur',
      result_badge:    'ÉTUDE IA GÉNÉRÉE EN BASE',
      result_model:    'MODÈLE',
      result_title:    'Rapport d\'Analyse',
      result_obs:      'Observations analysées',
      err_msg:         'Génération de l\'étude impossible',
      err_hint:        'Vérifiez la présence d\'observations en base et la configuration de la clé API Gemini.',
      sectors: {
        all:         'TOUS LES SECTEURS',
        agriculture: 'AGRICULTURE',
        environment: 'ENVIRONNEMENT',
        markets:     'MARCHÉS',
        economy:     'ÉCONOMIE',
      },
    },

    // ── API ──
    api: {
      dev_label:   'CENTRE POUR DÉVELOPPEURS',
      title:       'EXPORTATION ET API',
      coord:       'Coordonnées : 12.134, 8.382',
      section_access: '01. Accès API',
      access_desc: 'Authentifiez-vous et accédez aux données via nos points d\'accès REST sécurisés.',
      api_key_label: 'VOTRE CLÉ API',
      no_key_msg:  'Aucune clé d\'accès générée. Cliquez sur "GÉNÉRER UNE CLÉ API" ci-dessous.',
      btn_generate: 'GÉNÉRER UNE CLÉ API',
      copy:        'Copier',
      regen:       'RÉGÉNÉRER',
      revoke:      'RÉVOQUER',
      revoked_msg: '[RÉVOQUÉ] — Cliquez sur Générer pour obtenir une nouvelle clé.',
      section_download: '02. Téléchargement des Données',
      format_label: 'FORMAT D\'EXPORTATION',
      filters_label: 'FILTRES ACTIFS :',
      filter_all:  'Secteur : Tous les jeux de données publics',
      filter_region: 'Région : Logone / Tchad',
      btn_archive: 'GÉNÉRER L\'ARCHIVE',
      premium_msg: 'Le format "$FMT" est disponible pour les clés Enterprise. Export JSON en cours.',
      section_docs: '03. Documentation',
      rate_title:  'Statut du Quota API',
      rate_msg:    'Statut nominal : 12 / 5 000 requêtes utilisées aujourd\'hui (0.2%). Réinitialisation dans 24h.',
      latency:     'LATENCE',
      docs: [
        { id: 'swagger', icon: 'file-text',  name: 'Spécification API OpenAPI et Swagger', desc: 'Spécifications complètes des points d\'accès et schémas interactifs au /docs', link: '/docs' },
        { id: 'redoc',   icon: 'book-open',  name: 'Documentation ReDoc',                desc: 'Documentation ReDoc et visionneuse de schémas au /redoc', link: '/redoc' },
        { id: 'health',  icon: 'activity',   name: 'Point d\'Accès Santé Système',       desc: 'Tester le statut live du système à /api/v1/health', link: '/api/v1/health' },
      ],
    },

    // ── Status ──
    status: {
      title:      'STATUT DU SYSTÈME',
      subtitle:   'SURVEILLANCE EN TEMPS RÉEL DE L\'INFRASTRUCTURE',
      pipelines_title: 'Pipelines d\'Ingestion et Audit',
      sources_title:   'Sources de Données Actives',
      load_title:      'Charge et Latence du Système',
      scheduler_label: 'Planificateur',
      scheduler_running: 'En cours',
      scheduler_idle:    'En attente',
      uptime:     'DISPONIBILITÉ',
      requests:   'REQUÊTES/HEURE',
      errors:     'TAUX D\'ERREUR',
    },

    // ── Terms & Conditions ──
    terms: {
      badge: 'LICENCE COMPATIBLE CC BY 4.0',
      title: 'CONDITIONS D\'UTILISATION & MENTIONS LÉGALES',
      subtitle: 'Cadre juridique, licence Creative Commons, citation des données et politique d\'utilisation équitable de FreeData.td.',
      last_updated: 'Dernière mise à jour : Septembre 2026',
      sec1_title: '1. Politique d\'Accès Ouvert et Licence (CC BY 4.0)',
      sec1_text: 'L\'ensemble des jeux de données publiques, statistiques et synthèses mis à disposition sur FreeData.td est distribué sous la licence internationale Creative Commons Attribution 4.0 (CC BY 4.0). Vous êtes libre de partager, copier, distribuer, adapter, transformer et réutiliser ces données à toutes fins, y compris commerciales, sous réserve du respect des conditions d\'attribution.',
      sec2_title: '2. Obligations de Citation et d\'Attribution',
      sec2_text: 'Toute réutilisation ou publication (articles, rapports, applications web, études de recherche) utilisant les données de FreeData.td doit obligatoirement mentionner la source d\'origine primaire ainsi que le nœud d\'agrégation.',
      sec2_example_label: 'EXEMPLE DE FORMAT DE CITATION RECOMMANDÉ :',
      sec3_title: '3. Exonération de Garantie et Limitation de Responsabilité',
      sec3_text: 'Les données sont fournies "EN L\'ÉTAT" et "SELON DISPONIBILITÉ". Bien que FreeData.td applique un contrôle qualité rigoureux et une validation automatique via des agents IA, la plateforme ne garantit pas l\'absence totale d\'erreurs ou la mise à jour en temps réel des sources secondaires. FreeData.td décline toute responsabilité pour toute décision économique, politique ou financière prise sur la base de ces informations.',
      sec4_title: '4. Utilisation Équitable et Accès API',
      sec4_text: 'Les APIs publiques et l\'infrastructure de FreeData.td sont ouvertes à tous. Les utilisateurs s\'engagent à ne pas effectuer de requêtes malveillantes ou abusives (DDOS) susceptibles de dégrader les performances du service. Des limites de débit (Rate Limiting) sont appliquées pour garantir un accès équitable à l\'ensemble de la communauté.',
      sec5_title: '5. Protection de la Vie Privée et Données Personnelles',
      sec5_text: 'FreeData.td collecte et traite exclusivement des données publiques nationales et internationales agrégées. Aucune donnée personnelle nominative n\'est stockée ou commercialisée. Les seuls journaux techniques conservés concernent les métriques anonymisées de latence et de fréquentation du réseau pour des besoins de sécurité.',
      sec6_title: '6. Droit Applicable et Contact',
      sec6_text: 'Ces conditions d\'utilisation s\'inspirent des meilleures pratiques des portails internationaux de données ouvertes (World Bank Open Data, UN Data, US Data.gov). Pour toute question, suggestion ou signalement relatif aux données, veuillez contacter l\'équipe via l\'API ou le répertoire des sources.',
    },
  },

  // ────────────────────────────────────────────────
  en: {
    nav: {
      mission:    'Mission',
      explorer:   'Explorer',
      repository: 'Repository',
      sources:    'Data Sources',
      insights:   'AI Insights',
      api:        'Export & API',
      status:     'Status',
      terms:      'Terms & License',
    },
    common: {
      active:      'ACTIVE',
      beta:        'BETA',
      planned:     'PLANNED',
      no_data:     'NO DATA',
      loading:     'Loading…',
      error:       'API connection error.',
      explore:     'EXPLORE',
      collect:     'COLLECT LIVE DATA',
      harvest_ok:  'Harvest complete! Database updated with new records.',
      harvest_err: 'Harvest error',
      records:     'RECORDS',
      source:      'SOURCE',
      validated:   'VALIDATED',
      date:        'Unknown date',
      location:    'Chad',
      health:      'HEALTH SCORE',
      refresh:     'REFRESH: REALTIME',
      open:        'OPEN',
      uptime:      'UPTIME',
      latency:     'LATENCY',
      status_ok:   'STATUS: OPERATIONAL',
      copied:      'COPIED!',
      lang_label:  'EN',
    },
    footer: {
      text: 'FreeData.td — Open Data Infrastructure for Chad',
      node: 'National Node: TD-PROD-01',
    },
    home: {
      title:        'OPEN DATA INFRASTRUCTURE FOR CHAD',
      subtitle:     "Making Chad's data accessible, reliable and useful for everyone.",
      hero_sub:     'OPEN DATA INFRASTRUCTURE',
      hero_tagline: "Making Chad's data accessible, reliable and useful for everyone.",
      btn_explore:  'EXPLORE DATA',
      btn_harvest:  'COLLECT LIVE DATA',
      btn_harvest_loading: 'Harvesting from Open-Meteo & FAOSTAT…',
      stat_obs:     'OBSERVATIONS IN DATABASE',
      stat_score:   'VALIDATION SCORE',
      stat_logs:    'AUDIT LOGS',
      stat_sectors: 'ACTIVE SECTORS',
      mission_title: 'MISSION & CORE CAPABILITIES',
      mission_text:  'FreeData.td is the central open data infrastructure dedicated to aggregating, validating, and freely distributing Chad\'s socio-economic statistical datasets. By unifying time series from official national and international public agencies, the platform ensures open, transparent, and standardized access for research, policy-making, and digital innovation.',
      capabilities: [
        { icon: 'database',    title: 'Multi-Source Aggregation', desc: 'Automated harvest from 10 official agencies (INSEED, BEAC, World Bank, FAOSTAT, WHO, UNESCO...)' },
        { icon: 'shield-check',title: 'Data Governance & QA',      desc: 'Structural normalization, anomaly detection, and strict schema validation.' },
        { icon: 'code-2',      title: 'Open APIs & Export',        desc: 'High-performance REST endpoints, instant CSV/JSON/Excel export, and CC BY 4.0 licensing.' },
        { icon: 'line-chart',  title: 'Analytics & Dashboards',    desc: 'Dynamic sector dashboards, interactive data visualizations, and automated AI insights.' },
      ],
      pipeline_title: 'DATA PIPELINE',
      pipeline: [
        { num: '01', title: 'INGESTION',     desc: 'Automated collection from FAOSTAT, NASA, and World Bank.' },
        { num: '02', title: 'CLEANING',      desc: 'Quality control and structural validation of raw observations.' },
        { num: '03', title: 'DISTRIBUTION',  desc: 'Public APIs, CSV exports, and interactive analytical dashboards.' },
      ],
      sectors_title: 'ACTIVE SECTORS',
      latest_title:  'LATEST VALIDATED DATA FROM DATABASE',
      loading_db:    'Loading data from database…',
      no_obs:        'No data in database. Click "COLLECT LIVE DATA" to populate.',
    },
    sectors: {
      title:         'INFRASTRUCTURE EXPLORER',
      search:        'SEARCH BY SECTOR OR SOURCE…',
      total_sources: 'TOTAL SOURCES',
      val_score:     'VALIDATION SCORE',
      active_title:  'ACTIVE SECTORS',
      explore_data:  'EXPLORE DATA',
      names: {
        agriculture: 'AGRICULTURE',
        environment: 'ENVIRONMENT',
        markets:     'MARKETS & PRICES',
        transport:   'TRANSPORT',
        education:   'EDUCATION',
        economy:     'ECONOMY',
      },
    },

    // ── Sources ──
    sources: {
      title:        'OFFICIAL 10 DATA SOURCES DIRECTORY',
      subtitle:     'TRANSPARENCY, TERMS OF USE AND DIRECT ACCESS TO OFFICIAL PORTALS',
      search:       'SEARCH SOURCE, ORGANIZATION OR LICENSE…',
      badge_count:  '10 VERIFIED OFFICIAL SOURCES',
      open_portal:  'OPEN OFFICIAL PORTAL',
      org_label:    'Issuing Organization',
      license_label: 'Usage License',
    },
    data: {
      title:        'OPEN DATA REPOSITORY',
      search:       'SEARCH BY INDICATOR, SOURCE OR REGION…',
      sectors_label: 'SECTORS',
      obs_header:   'OBSERVATIONS',
      sort_label:   'Sort by: DATE',
      load_more:    'LOAD MORE DATA',
      loading_db:   'Querying the database…',
      trend_title:  'DATA TIME TREND',
      trend_footer: 'HISTORY SOURCED FROM DATABASE',
      live:         'LIVE API',
      harvest_loading: 'Harvesting…',
      empty_msg:    'No data available in database for sector',
      empty_btn:    'RUN AUTOMATIC COLLECTION',
      filter_all:   'ALL',
    },
    insights: {
      agent_log:   'AI ANALYSIS AGENT',
      title:       'AI INSIGHTS AND STUDIES',
      subtitle:    'AUTOMATED DATABASE EXPLORATION & LLM STUDY GENERATION',
      status_active:   'STATUS: ACTIVE',
      status_thinking: 'STATUS: THINKING…',
      status_done:     'STATUS: COMPLETE',
      density_title:   'Data Density by Region',
      density_desc:    'Record distribution by station and region in Chad.',
      studies_title:   'AI Analyses and Studies',
      btn_run:         'GENERATE AI STUDY',
      btn_run_loading: 'RUNNING AI SYNTHESIS AGENT…',
      btn_run_new:     'GENERATE NEW AI STUDY',
      placeholder:     'Click "GENERATE AI STUDY" to run the Analysis Agent on database data.',
      running_msg:     'AnalysisAgent is analysing data for sector',
      result_badge:    'AI STUDY GENERATED',
      result_model:    'MODEL',
      result_title:    'Analysis Report',
      result_obs:      'Observations analysed',
      err_msg:         'Study generation failed',
      err_hint:        'Check that observations exist in the database and that the Gemini API key is configured.',
      sectors: {
        all:         'ALL SECTORS',
        agriculture: 'AGRICULTURE',
        environment: 'ENVIRONMENT',
        markets:     'MARKETS',
        economy:     'ECONOMY',
      },
    },
    api: {
      dev_label:   'DEVELOPER CENTER',
      title:       'EXPORT AND API',
      coord:       'Coordinates: 12.134, 8.382',
      section_access: '01. API Access',
      access_desc: 'Authenticate and request data via our secure REST endpoints.',
      api_key_label: 'YOUR API KEY',
      no_key_msg:  'No access key generated yet. Click "GENERATE API KEY" below.',
      btn_generate: 'GENERATE API KEY',
      copy:        'Copy',
      regen:       'REGENERATE',
      revoke:      'REVOKE',
      revoked_msg: '[REVOKED] — Click Generate to request a new key.',
      section_download: '02. Data Download',
      format_label: 'EXPORT FORMAT',
      filters_label: 'ACTIVE FILTERS:',
      filter_all:  'Sector: All Public Datasets',
      filter_region: 'Region: Logone / Chad',
      btn_archive: 'GENERATE ARCHIVE',
      premium_msg: 'The format "$FMT" is available for Enterprise keys. Triggering JSON export fallback.',
      section_docs: '03. Documentation',
      rate_title:  'API Quota Status',
      rate_msg:    'Normal status: 12 / 5,000 requests used today (0.2%). Reset in 24h.',
      latency:     'LATENCY',
      docs: [
        { id: 'swagger', icon: 'file-text', name: 'OpenAPI and Swagger Specification', desc: 'Full endpoint specifications, interactive schemas & try-it-out at /docs', link: '/docs' },
        { id: 'redoc',   icon: 'book-open', name: 'ReDoc Documentation',                 desc: 'Clean ReDoc documentation & schema viewer at /redoc', link: '/redoc' },
        { id: 'health',  icon: 'activity',  name: 'System Health Check Endpoint',          desc: 'Test API system status live at /api/v1/health', link: '/api/v1/health' },
      ],
    },
    status: {
      title:      'SYSTEM STATUS',
      subtitle:   'REAL-TIME INFRASTRUCTURE MONITORING',
      pipelines_title: 'Ingestion Pipelines and Audit',
      sources_title:   'Active Data Sources',
      load_title:      'System Load and Latency',
      scheduler_label: 'Scheduler',
      scheduler_running: 'Running',
      scheduler_idle:    'Idle',
      uptime:     'DISPONIBILITÉ',
      requests:   'REQUÊTES/HEURE',
      errors:     'TAUX D\'ERREUR',
    },

    // ── Terms & Conditions ──
    terms: {
      badge: 'CC BY 4.0 COMPLIANT LICENSE',
      title: 'TERMS OF SERVICE & LEGAL NOTICE',
      subtitle: 'Legal framework, Creative Commons licensing, data attribution guidelines, and API fair use policy for FreeData.td.',
      last_updated: 'Last Updated: September 2026',
      sec1_title: '1. Open Access Policy & Licensing (CC BY 4.0)',
      sec1_text: 'All public datasets, statistics, and synthesized indicators made available on FreeData.td are licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0). You are free to share, copy, redistribute, adapt, transform, and build upon the data for any purpose, including commercial applications, provided proper attribution is given.',
      sec2_title: '2. Citation & Attribution Requirements',
      sec2_text: 'Any reuse or publication (articles, reports, web applications, research papers) incorporating datasets from FreeData.td must explicitly cite the primary source provider as well as FreeData.td.',
      sec2_example_label: 'RECOMMENDED CITATION FORMAT:',
      sec3_title: '3. Disclaimer of Warranty & Limitation of Liability',
      sec3_text: 'Data is provided on an "AS IS" and "AS AVAILABLE" basis. While FreeData.td applies strict automated validation and quality assurance via AI agent workers, the platform does not guarantee absolute freedom from errors or instantaneous updates from external primary providers. FreeData.td assumes no liability for economic, policy, or financial decisions made based on these datasets.',
      sec4_title: '4. API Fair Use & Rate Limiting Policy',
      sec4_text: 'FreeData.td public APIs and data endpoints are open for all developers. Users agree not to engage in malicious traffic, excessive scraping, or denial-of-service attempts that degrade system stability. Rate limits are enforced to guarantee equitable access for the entire global community.',
      sec5_title: '5. Privacy & Personal Data Protection',
      sec5_text: 'FreeData.td exclusively aggregates and processes public macro-level socio-economic statistics. No personal or identifiable data is collected, stored, or commercialized. Technical logs are limited to anonymous network telemetry, request latency, and uptime performance metrics.',
      sec6_title: '6. Governing Principles & Contact',
      sec6_text: 'These terms reflect international open data governance standards (World Bank Open Data, UN Data, European Data Portal). For inquiries, corrections, or source data feedback, please reach out via our API portal or official sources directory.',
    },
  },
};

// ── State ──
let _lang = localStorage.getItem('fd_lang') || 'fr';

export function getLang() { return _lang; }

export function setLang(lang) {
  if (!TRANSLATIONS[lang]) return;
  _lang = lang;
  localStorage.setItem('fd_lang', lang);
  // Dispatch event so router/views can re-render
  window.dispatchEvent(new CustomEvent('langchange', { detail: { lang } }));
}

/**
 * Translate a dot-separated key, e.g. t('home.title')
 * Falls back to key if not found.
 */
export function t(key) {
  const parts = key.split('.');
  let node = TRANSLATIONS[_lang];
  for (const part of parts) {
    if (node == null) return key;
    node = node[part];
  }
  return node != null ? node : key;
}
