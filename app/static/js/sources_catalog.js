/**
 * FreeData.td — Official Data Sources Catalog (Bilingual FR/EN)
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
    desc_fr: 'PIB, inflation, dette, pauvreté et inégalités (Gini), chômage, rente pétrolière, accès à internet et au mobile, parité au parlement, agriculture et alphabétisation, depuis 2000.',
    desc_en: 'GDP, inflation, debt, poverty and inequality (Gini), unemployment, oil rents, internet and mobile access, women in parliament, agriculture and literacy, since 2000.'
  },
  {
    id: 'wfp-vam',
    name: 'WFP Food Prices (PAM)',
    org_fr: 'Programme Alimentaire Mondial des Nations Unies',
    org_en: 'United Nations World Food Programme',
    sector_fr: 'Marchés & Prix Alimentaires',
    sector_en: 'Markets & Food Prices',
    sectorId: 'markets',
    license: 'CC BY-IGO 3.0',
    url: 'https://data.humdata.org/dataset/wfp-food-prices-for-chad',
    desc_fr: 'Prix mensuels de détail des denrées par marché (fichier WFP publié sur HDX, 3 dernières années).',
    desc_en: 'Monthly retail food prices by market (WFP file published on HDX, last 3 years).'
  },
  {
    id: 'fews-net',
    name: 'FEWS NET Data Warehouse',
    org_fr: 'Famine Early Warning Systems Network (FEWS NET)',
    org_en: 'Famine Early Warning Systems Network (FEWS NET)',
    sector_fr: 'Marchés & Prix Alimentaires',
    sector_en: 'Markets & Food Prices',
    sectorId: 'markets',
    license: 'Reuse with attribution (FEWS NET)',
    license_fr: 'Réutilisation avec attribution (FEWS NET)',
    url: 'https://fews.net/data/markets-and-trade',
    desc_fr: 'Prix de détail des denrées de base (mil, sorgho, maïs, riz...) par marché du Tchad, relevés mensuels ou hebdomadaires.',
    desc_en: 'Retail prices of staple foods (millet, sorghum, maize, rice...) by market in Chad, collected monthly or weekly.'
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
    id: 'ourairports',
    name: 'OurAirports',
    org_fr: 'OurAirports (David Megginson & contributeurs)',
    org_en: 'OurAirports (David Megginson & contributors)',
    sector_fr: 'Transport & Logistique',
    sector_en: 'Transport & Infrastructure',
    sectorId: 'transport',
    license: 'Public domain',
    url: 'https://ourairports.com/countries/TD/',
    desc_fr: 'Aéroports et pistes d\'atterrissage du Tchad par région, dont ceux avec service régulier.',
    desc_en: 'Airports and airstrips of Chad by region, including those with scheduled service.'
  },
  {
    id: 'openstreetmap',
    name: 'OpenStreetMap Network',
    org_fr: 'Fondation OpenStreetMap & Communauté Open Source',
    org_en: 'OpenStreetMap Foundation & Open Community',
    sector_fr: 'Santé & Éducation',
    sector_en: 'Health & Education',
    sectorId: 'health',
    license: 'ODbL (Open Database License)',
    url: 'https://www.openstreetmap.org/',
    desc_fr: 'Nombre d\'hôpitaux, de cliniques, de pharmacies, de points d\'eau, d\'écoles et d\'universités cartographiés par région (ce qui est cartographié, pas ce qui existe).',
    desc_en: 'Number of hospitals, clinics, pharmacies, water points, schools and universities mapped per region (what contributors have mapped, not what exists).'
  },
  {
    id: 'world-bank-health',
    name: 'World Bank Health (WDI)',
    org_fr: 'Groupe de la Banque Mondiale — Indicateurs de Développement Mondial',
    org_en: 'World Bank Group — World Development Indicators',
    sector_fr: 'Santé & Développement Humain',
    sector_en: 'Health & Human Development',
    sectorId: 'health',
    license: 'CC BY 4.0 Open Data',
    url: 'https://data.worldbank.org/indicator?tab=all',
    desc_fr: 'Espérance de vie, mortalité maternelle, néonatale et infantile, vaccination, paludisme, tuberculose, VIH, personnel de santé, nutrition, dépenses de santé et accès à l\'eau, depuis 2000.',
    desc_en: 'Life expectancy, maternal, neonatal and child mortality, immunization, malaria, tuberculosis, HIV, health workforce, nutrition, health spending and access to water, since 2000.'
  },
  {
    id: 'world-bank-energy',
    name: 'World Bank Energy (SE4ALL)',
    org_fr: 'Groupe de la Banque Mondiale — Sustainable Energy for All',
    org_en: 'World Bank Group — Sustainable Energy for All (SE4ALL)',
    sector_fr: 'Énergie & Électricité',
    sector_en: 'Energy & Electricity Access',
    sectorId: 'energy',
    license: 'CC BY 4.0 Open Data',
    url: 'https://data.worldbank.org/topic/energy-and-mining',
    desc_fr: 'Accès à l\'électricité (national, rural, urbain), énergies renouvelables et combustibles propres au Tchad.',
    desc_en: 'Access to electricity (national, rural, urban), renewable energy share, and clean cooking fuels for Chad.'
  },
  {
    id: 'inseed-open-data',
    name: 'INSEED Open Data (Chad Data Portal)',
    org_fr: 'Institut National de la Statistique, des Études Économiques et Démographiques (INSEED)',
    org_en: 'National Institute of Statistics, Economic and Demographic Studies (INSEED)',
    sector_fr: 'Démographie, Santé & Prix',
    sector_en: 'Demography, Health & Prices',
    sectorId: 'demography',
    license: 'INSEED Open Licence Agreement',
    url: 'https://chad.opendataforafrica.org/tylheoe/principaux-indicateurs-statistiques',
    desc_fr: 'Statistiques officielles nationales : population par âge et sexe, établissements de santé par province, indice des prix à la consommation.',
    desc_en: 'Official national statistics: population by age and sex, health facilities by province, consumer price index.'
  },
  {
    id: 'world-bank-demography',
    name: 'World Bank Demography (WDI)',
    org_fr: 'Groupe de la Banque Mondiale — Indicateurs du développement dans le monde',
    org_en: 'World Bank Group — World Development Indicators',
    sector_fr: 'Démographie & Population',
    sector_en: 'Demography & Population',
    sectorId: 'demography',
    license: 'CC BY 4.0 Open Data',
    url: 'https://data.worldbank.org/topic/population',
    desc_fr: 'Population totale, croissance, structure par âge, urbanisation, natalité, mortalité, fécondité, migration nette et part de migrants internationaux du Tchad.',
    desc_en: 'Total population, growth, age structure, urbanisation, birth and death rates, fertility, net migration and international migrant share for Chad.'
  },
  {
    id: 'unhcr',
    name: 'UNHCR Refugee Population Statistics',
    org_fr: 'Haut-Commissariat des Nations Unies pour les réfugiés (HCR)',
    org_en: 'United Nations High Commissioner for Refugees (UNHCR)',
    sector_fr: 'Démographie & Population',
    sector_en: 'Demography & Population',
    sectorId: 'demography',
    license: 'CC BY 4.0 (UNHCR Terms of Use for Datasets)',
    url: 'https://www.unhcr.org/refugee-statistics',
    desc_fr: 'Réfugiés et demandeurs d\'asile accueillis au Tchad par pays d\'origine, déplacés internes et réfugiés tchadiens à l\'étranger, par année.',
    desc_en: 'Refugees and asylum seekers hosted in Chad by country of origin, internally displaced people, and Chadian refugees abroad, by year.'
  },
  {
    id: 'world-bank-telecom',
    name: 'World Bank Digital Development (ICT)',
    org_fr: 'Groupe de la Banque Mondiale, données de l\'Union internationale des télécommunications (UIT)',
    org_en: 'World Bank Group, data from the International Telecommunication Union (ITU)',
    sector_fr: 'Télécommunications',
    sector_en: 'Telecommunications',
    sectorId: 'telecom',
    license: 'CC BY 4.0 Open Data',
    url: 'https://data.worldbank.org/topic/infrastructure',
    desc_fr: 'Abonnements mobiles et haut débit, utilisateurs d\'Internet, téléphonie fixe, serveurs sécurisés et part des biens et services TIC dans les échanges du Tchad, depuis 2000.',
    desc_en: 'Mobile and broadband subscriptions, Internet users, fixed telephony, secure servers and the share of ICT goods and services in Chad\'s trade, since 2000.'
  },
  {
    id: 'world-bank-trade',
    name: 'World Bank Trade (WITS, UN Comtrade)',
    org_fr: 'Groupe de la Banque Mondiale, données du système WITS et de la base UN Comtrade',
    org_en: 'World Bank Group, data from WITS and the UN Comtrade database',
    sector_fr: 'Commerce extérieur',
    sector_en: 'Foreign Trade',
    sectorId: 'trade',
    license: 'CC BY 4.0 Open Data',
    url: 'https://data.worldbank.org/topic/trade',
    desc_fr: 'Valeur des exportations et importations de marchandises du Tchad et leur composition (pétrole, alimentation, matières premières agricoles, minerais), termes de l\'échange, depuis 2000.',
    desc_en: 'Value of Chad\'s merchandise exports and imports and their composition (fuel, food, agricultural raw materials, ores), terms of trade, since 2000.'
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
