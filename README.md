# FreeData.td 🇹🇩

> An Open AI-Powered Data Infrastructure for Chad

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Data License: CC BY 4.0](https://img.shields.io/badge/Data-CC%20BY%204.0-green.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Status: In Development](https://img.shields.io/badge/Status-In%20Development-orange.svg)]()

## Vision

FreeData.td est une infrastructure de données ouverte alimentée par des agents 
AI autonomes. Son objectif : collecter, nettoyer, valider et rendre accessibles 
les données socioéconomiques du Tchad — gratuitement, pour tous.

## Pourquoi ChadData ?

Le Tchad souffre d'un déficit chronique de données publiques structurées.
Chercheurs, startups, ONG et décideurs font face au même obstacle : 
l'absence d'une source de données fiable, centralisée et accessible.
ChadData est la réponse à ce problème.

## Secteurs couverts

| Secteur | Sources | Statut |
|---|---|---|
| 🌾 Agriculture | FAOSTAT, WFP VAM | 🔄 En développement |
| 🛒 Marchés & Prix | WFP VAM, World Bank | 📋 Planifié |
| 🚗 Transports | OpenStreetMap, OSR | 📋 Planifié |
| 📚 Education | UNESCO, UNICEF | 📋 Planifié |
| 🌍 Environnement | Open-Meteo, NASA | 📋 Planifié |
| 💰 Economie | World Bank, IMF | 📋 Planifié |

## Architecture

## Accès aux données

- 🌐 **Plateforme web** : visualisation interactive (coming soon)
- 📥 **Téléchargement** : CSV / JSON par secteur (coming soon)
- 🔌 **API publique** : `GET /api/v1/agriculture` (coming soon)

## Installation

```bash
git clone https://github.com/kadergueli/FreeData.td.git
cd FreeData.td
pip install -r requirements.txt


