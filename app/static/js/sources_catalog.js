/**
 * FreeData.td — Official 10 Data Sources Catalog (Bilingual FR/EN)
 */

export const OFFICIAL_SOURCES = [
  {
    id: 'faostat',
    name: 'FAOSTAT (FAO)',
    org_fr: 'Organisation des Nations Unies pour l\'Alimentation et l\'Agriculture',
    org_en: 'Food and Agriculture Organization of the United Nations',
    sector_fr: 'Agriculture & Élevage',
    sector_en: 'Agriculture & Livestock',
    sectorId: 'agriculture',
    license: 'CC BY-NC-SA 3.0 IGO',
    url: 'https://www.fao.org/faostat/',
    desc_fr: 'Données mondiales sur la production agricole, l\'élevage, les récoltes et la sécurité alimentaire au Tchad.',
    desc_en: 'Global agricultural production, livestock, food security and crop yield statistics for Chad.'
  },
  {
    id: 'open-meteo',
    name: 'Open-Meteo API',
    org_fr: 'ECMWF & NOAA Open Data Network',
    org_en: 'ECMWF & NOAA Open Data Network',
    sector_fr: 'Environnement & Climat',
    sector_en: 'Environment & Climate',
    sectorId: 'environment',
    license: 'CC BY 4.0 Open Data',
    url: 'https://open-meteo.com/',
    desc_fr: 'Données météorologiques à haute résolution, précipitations, températures et réanalyses météo pour le Tchad.',
    desc_en: 'High-resolution meteorological, rainfall, temperature, and historical climate reanalysis for Chad.'
  },
  {
    id: 'nasa-firms',
    name: 'NASA FIRMS',
    org_fr: 'National Aeronautics and Space Administration (EOSDIS)',
    org_en: 'National Aeronautics and Space Administration (EOSDIS)',
    sector_fr: 'Environnement & Satellite',
    sector_en: 'Environment & Satellite Imaging',
    sectorId: 'environment',
    license: 'Domaine Public / Public Domain',
    url: 'https://firms.modaps.eosdis.nasa.gov/',
    desc_fr: 'Système d\'information sur les feux et feux de brousse en temps réel par satellites MODIS et VIIRS au Tchad.',
    desc_en: 'Real-time satellite fire and thermal anomaly tracking system for Chad via MODIS and VIIRS.'
  },
  {
    id: 'world-bank',
    name: 'World Bank Open Data',
    org_fr: 'Groupe de la Banque Mondiale',
    org_en: 'World Bank Group',
    sector_fr: 'Économie & Développement',
    sector_en: 'Economy & Development',
    sectorId: 'economy',
    license: 'CC BY 4.0 Open Data',
    url: 'https://data.worldbank.org/country/chad',
    desc_fr: 'Indicateurs de développement mondial, PIB, dépenses publiques, éducation et croissance économique du Tchad.',
    desc_en: 'World development indicators, GDP, public expenditure, literacy, and economic growth for Chad.'
  },
  {
    id: 'wfp-vam',
    name: 'WFP Food Prices (PAM)',
    org_fr: 'Programme Alimentaire Mondial des Nations Unies',
    org_en: 'United Nations World Food Programme',
    sector_fr: 'Marchés & Prix Alimentaires',
    sector_en: 'Markets & Food Prices',
    sectorId: 'markets',
    license: 'CC BY 4.0 WFP Open Data',
    url: 'https://data.humdata.org/organization/wfp',
    desc_fr: 'Suivi mensuel des prix des denrées céréalières (Maïs, Mil, Sorgho, Riz) sur les marchés régionaux du Tchad.',
    desc_en: 'Monthly food commodity price tracking (Maize, Millet, Sorghum, Rice) across Chad markets.'
  },
  {
    id: 'imf-data',
    name: 'IMF Data API',
    org_fr: 'Fonds Monétaire International (FMI)',
    org_en: 'International Monetary Fund (IMF)',
    sector_fr: 'Économie & Finances',
    sector_en: 'Economy & Financial Statistics',
    sectorId: 'economy',
    license: 'IMF Free Redistribution Terms',
    url: 'https://www.imf.org/en/Data',
    desc_fr: 'Statistiques financières internationales, ratio dette/PIB, taux d\'inflation et balances commerciales.',
    desc_en: 'International financial statistics, debt-to-GDP ratios, inflation rates, and trade balances for Chad.'
  },
  {
    id: 'unesco-uis',
    name: 'UNESCO UIS (EdStats)',
    org_fr: 'Institut de Statistique de l\'UNESCO',
    org_en: 'UNESCO Institute for Statistics',
    sector_fr: 'Éducation & Alphabétisation',
    sector_en: 'Education & Literacy',
    sectorId: 'education',
    license: 'CC BY 3.0 IGO UNESCO Policy',
    url: 'https://uis.unesco.org/',
    desc_fr: 'Taux de scolarisation au primaire/secondaire, taux d\'alphabétisation des adultes et des jeunes au Tchad.',
    desc_en: 'Primary and secondary net enrollment rates, adult literacy, and youth literacy rates for Chad.'
  },
  {
    id: 'unicef-data',
    name: 'UNICEF Data',
    org_fr: 'Fonds des Nations Unies pour l\'Enfance',
    org_en: 'United Nations Children\'s Fund',
    sector_fr: 'Éducation & ODD 4',
    sector_en: 'Education & SDG 4',
    sectorId: 'education',
    license: 'CC BY 4.0 UNICEF Policy',
    url: 'https://data.unicef.org/',
    desc_fr: 'Statistiques de l\'éducation de base, parité de genre et enfants hors du système scolaire au Tchad.',
    desc_en: 'Basic education indicators, gender parity indexes, and out-of-school children statistics in Chad.'
  },
  {
    id: 'hdx-ocha',
    name: 'HDX (OCHA Data)',
    org_fr: 'Humanitarian Data Exchange / UN OCHA',
    org_en: 'Humanitarian Data Exchange / UN OCHA',
    sector_fr: 'Transport & Logistique',
    sector_en: 'Transport & Infrastructure',
    sectorId: 'transport',
    license: 'CC BY 4.0 Humanitarian License',
    url: 'https://data.humdata.org/group/tcd',
    desc_fr: 'Base de données sur l\'infrastructure logistique, les aéroports, pistes et réseaux de transport au Tchad.',
    desc_en: 'Humanitarian logistics, airports, road networks, and infrastructure datasets for Chad.'
  },
  {
    id: 'openstreetmap',
    name: 'OpenStreetMap Network',
    org_fr: 'Fondation OpenStreetMap & Communauté Open Source',
    org_en: 'OpenStreetMap Foundation & Open Community',
    sector_fr: 'Transport & Cartographie',
    sector_en: 'Transport & Mapping',
    sectorId: 'transport',
    license: 'ODbL (Open Database License)',
    url: 'https://www.openstreetmap.org/',
    desc_fr: 'Réseau routier open source, voies de communication et cartographie des infrastructures du Tchad.',
    desc_en: 'Open source road transport network, airports, river ports, and geographical mapping for Chad.'
  }
];

export function getSourceByQuery(sourceStr = '') {
  const q = String(sourceStr).toLowerCase();
  for (const s of OFFICIAL_SOURCES) {
    if (q.includes(s.id) || q.includes(s.name.toLowerCase()) || s.name.toLowerCase().includes(q)) {
      return s;
    }
  }
  return {
    id: 'open-data',
    name: sourceStr || 'Source Publique Officielle',
    org_fr: 'Gouvernement & Organismes Internationaux',
    org_en: 'Government & International Organizations',
    sector_fr: 'Données Ouvertes',
    sector_en: 'Open Data',
    license: 'CC BY 4.0 / Public License',
    url: 'https://data.humdata.org/group/tcd',
    desc_fr: 'Données publiques vérifiées du Tchad.',
    desc_en: 'Verified public open data for Chad.'
  };
}
