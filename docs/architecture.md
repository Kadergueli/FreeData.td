# Technical Architecture & Complete Project Analysis: FreeData.td

## 1. Executive Summary / Présentation Générale

**FreeData.td** is an autonomous, open-data aggregation, validation, and analytics infrastructure dedicated to Chad (Tchad). The platform collects, standardizes, validates, and visualizes socioeconomic and agro-climatic datasets across **11 critical sectors** and all **23 official provinces of Chad**.

### Key Objectives
* **Data Sovereignty & Transparency**: Provide free, keyless, centralized access to verified national and international statistics concerning Chad under the **CC BY 4.0** open license.
* **Autonomous Multi-Source Ingestion**: Run 11 specialized domain agents with cadence-aware scheduling, exponential backoff, statistical outlier detection ($3 \times \text{IQR}$), and supervisor quarantine (`table_quarantine`).
* **Agronomic Decision Support**: Evaluate crop suitability across all 23 Chadian regions by combining FAO EcoCrop requirements with NASA POWER climatology and SoilGrids 2.0 soil profiles (`app/crops/`).
* **AI & Data Science Analytics**: Compute pure-Python cross-sector correlations, seasonal anomalies, spatial coverage, and LLM-assisted sector studies (`app/agents/ds_insights.py`, `app/agents/analysis.py`).
* **Omnichannel & Bilingual Accessibility**: Full French/English internationalization across the Progressive Web App (PWA) SPA, REST API, and WhatsApp Cloud API assistant (`app/assistant/`, `app/whatsapp.py`).

---

## 2. System Architecture Overview

```text
+-----------------------------------------------------------------------------------+
|                               USER INTERFACES                                     |
|  - Progressive Web App SPA (`app/static/`): Vanilla JS | Chart.js | FR/EN i18n    |
|  - WhatsApp Cloud API Bot (`app/whatsapp.py`) & Web Data Assistant                |
|  - Open Data Harvesters: Schema.org JSON-LD | DCAT-AP | Sitemap XML               |
+-----------------------------------------------------------------------------------+
                                         | HTTPS / REST API (GZip, CSP, CDN Cache)
+-----------------------------------------------------------------------------------+
|                            FASTAPI APPLICATION (`app/main.py`)                    |
|  - Public Data & Export API (`/api/v1/observations`, `/api/v1/export/*`)          |
|  - Crop Suitability API (`app/crops/api.py` -> `/api/v1/crops/*`)                 |
|  - Admin & Governance API (`app/admin.py` -> `/api/v1/admin/*`)                   |
|  - Security, IP Rate Limiting & Headers (`app/security.py`)                       |
+-----------------------------------------------------------------------------------+
         |                               |                               |
+-----------------------+   +---------------------------+   +-----------------------+
|   11 SECTOR AGENTS    |   |   CROP & ASSISTANT CORES  |   |    SERVICES LAYER     |
| (`app/agents/`)       |   | - `app/crops/` (EcoCrop + |   | (`app/services/`)     |
| - BaseAgent Pipeline  |   |   SoilGrids + NASA POWER) |   | - Hybrid Storage      |
| - 11 Domain Agents    |   | - `app/assistant/`        |   |   (Supabase / SQLite) |
| - DS Insights Engine  |   |   (Markets & Weather NLP) |   | - Cadence Scheduler   |
| - Groq Study Agent    |   |                           |   |   & 14m Keep-Alive    |
+-----------------------+   +---------------------------+   | - Quarantine & Audit  |
         |                                                  | - CSV/JSON/XML/Parquet|
         v                                                  +-----------------------+
+-----------------------------------------------------------------------------------+
|                        VERIFIED UPSTREAM DATA PROVIDERS                           |
|  INSEED | World Bank (WDI & Pink Sheet) | IMF (WEO) | FEWS NET | WFP (HDX HAPI)   |
|  FAOSTAT | WHO (GHO) | DHS Program | UNICEF | UNESCO UIS | UNHCR | NASA POWER     |
|  NASA FIRMS | Open-Meteo | SoilGrids (ISRIC) | OpenStreetMap | OurAirports        |
+-----------------------------------------------------------------------------------+
```

---

## 3. Core Backend Components (`app/`)

### 3.1 Application Core & Middleware
* **[main.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/main.py)**: FastAPI entry point defining public endpoints, streaming exports, SEO/discoverability routes (`/sitemap.xml`, `/robots.txt`, `/api/v1/catalog.jsonld`, `/api/v1/catalog.dcat.json`), PWA routes (`/manifest.webmanifest`, `/sw.js`), and middleware stack (`SecurityHeadersMiddleware`, `NoCacheJSMiddleware`, `ReadRateLimitMiddleware`, `GZipMiddleware`).
* **[config.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/config.py)**: Pydantic Settings configuration loading `.env` variables, database credentials, rate limits, WhatsApp secrets, and Render keep-alive URL (`target_keep_alive_url`).
* **[security.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/security.py)**: Per-IP token-bucket rate limiting (120 reads/min, 10 exports/min, 5 AI study generations/hour) and `X-Collection-Key` authentication for administrative triggers.
* **[regions.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/regions.py)**: Canonical reference and alias normalizer for all 23 provinces of Chad and their capitals.
* **[admin.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/admin.py)**: Administrative REST router (`/api/v1/admin/*`) protected by Supabase JWT verification and explicit email allowlisting (`ADMIN_EMAILS` + `table_admins`).
* **[whatsapp.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/whatsapp.py)**: Meta Cloud API webhook (`GET/POST /api/v1/whatsapp/webhook`) with HMAC-SHA256 signature verification (`X-Hub-Signature-256`) and salted phone-number hashing.
* **[cli.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/cli.py)**: Command-line interface for manual collection, exports, live upstream diagnostics (`probe-prices`, `probe-sources`, `probe-inseed`), and offline SDMX ingestion (`import-inseed`).

### 3.2 Autonomous Agent Engine (`app/agents/`)
All 11 sector collectors inherit from [`BaseAgent`](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/base.py):
1. **[agriculture.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/agriculture.py)** (`agriculture`): Crop production, yields, livestock, and regional agro-meteorology (World Bank, Open-Meteo, NASA POWER).
2. **[markets.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/markets.py)** (`markets`): Regional food commodity prices and market indicators via [fews_prices.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/fews_prices.py) (FEWS NET), [wfp_prices.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/wfp_prices.py) (WFP HDX HAPI / CSV), FAOSTAT, and World Bank.
3. **[environment.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/environment.py)** (`environment`): Regional climate parameters, forest area, CO₂ emissions, and NASA FIRMS satellite active fire detections.
4. **[economy.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/economy.py)** (`economy`): GDP, inflation, fiscal balance, and external debt via World Bank and [imf.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/imf.py) (IMF World Economic Outlook DataMapper API).
5. **[health.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/health.py)** (`health`): Mortality, vaccination, disease incidence, and regional health infrastructure via World Bank, [who_gho.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/who_gho.py) (WHO GHO OData), [dhs.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/dhs.py) (DHS Program subnational surveys), [unicef.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/unicef.py) (UNICEF SDMX), and [osm.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/osm.py) (hospitals, pharmacies, water points per province).
6. **[energy.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/energy.py)** (`energy`): Urban/rural electricity access, clean cooking, renewable share (World Bank SE4ALL), plus monthly solar irradiance and 50m wind speed across all 23 regions (NASA POWER).
7. **[transport.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/transport.py)** (`transport`): Air transport, logistics performance, regional weather conditions, and airport/airstrip counts per province via [airports.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/airports.py) (OurAirports).
8. **[education.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/education.py)** (`education`): Literacy, enrollment, completion, and regional school counts via [unesco_uis.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/unesco_uis.py) (UNESCO UIS BDDS), [unicef.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/unicef.py), [osm.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/osm.py), and World Bank.
9. **[demography.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/demography.py)** (`demography`): Population growth, age structure, urbanization, fertility, UNHCR refugee/IDP populations, and INSEED census breakdowns ([inseed.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/inseed.py)).
10. **[telecom.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/telecom.py)** (`telecom`): Internet penetration, mobile cellular subscriptions, fixed broadband, secure servers, and ICT trade (World Bank / ITU via [wb_sector.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/wb_sector.py)).
11. **[trade.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/trade.py)** (`trade`): Merchandise exports/imports, fuel/food trade shares, terms of trade (World Bank), and monthly global commodity prices via [pink_sheet.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/pink_sheet.py) (World Bank Pink Sheet).

Analytical & Data Science modules:
* **[ds_insights.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/ds_insights.py)**: Pure-Python computation of cross-sector correlations (with lag detection), seasonal anomalies, spatial coverage across the 23 regions, and source freshness scores.
* **[analysis.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/analysis.py)**: Generates structured bilingual study reports using Groq LLM (`GROQ_API_KEY`) with an automatic deterministic statistical fallback when no LLM key is configured.

### 3.3 Crop Suitability Engine (`app/crops/`)
* **[engine.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/crops/engine.py)**: Pure functional implementation of the **FAO EcoCrop** trapezoid scoring method (`rain_mm`, `temp_mean_c`, `ph`) and Liebig's law of the minimum (`very_suitable`, `suitable`, `marginal`, `unsuitable`).
* **[profile.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/crops/profile.py)**: Derives wet-season cumulative rainfall, mean wet-season temperature, and season length from 12 monthly climatology averages.
* **[sites.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/crops/sites.py)**: Loads regional soil ([soils.json](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/crops/soils.json)) and climate ([climate.json](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/crops/climate.json)) profiles and performs accent-insensitive fuzzy region lookup.
* **[api.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/crops/api.py)**: Exposes `GET /api/v1/crops` and `GET /api/v1/crops/suitability?region=...&crop=...`.
* **[soils_chad.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/crops/soils_chad.py)** & **[climate_chad.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/crops/climate_chad.py)**: Standalone data-refresh scripts querying SoilGrids 2.0 COGs (via pure-Python HTTP Range requests) and NASA POWER climatology for all 23 regional centers.

### 3.4 Conversational Data Assistant (`app/assistant/`)
* **[engine.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/assistant/engine.py)**: Intent router combining [markets.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/assistant/markets.py) (live market prices by city/commodity), [weather.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/assistant/weather.py) (regional weather), [spellfix.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/assistant/spellfix.py) (fuzzy matching for Chadian place names and crops), and [guardrails.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/assistant/guardrails.py).

### 3.5 Services & Storage Layer (`app/services/`)
* **[storage.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/storage.py)**: `ObservationRepository` implementing the 3-stage medallion pipeline (`table_raw` → `table_clean` → `table_public`, plus `table_logs`, `table_rapports`, `table_etudes`) on **Supabase** in production and **SQLite** in local/test environments.
* **[scheduler.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/scheduler.py)** & **[cadence.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/cadence.py)**: Background harvester respecting per-sector update frequencies (daily, weekly, monthly) plus an integrated **14-minute keep-alive loop** (`_keep_alive_loop`) that prevents Render free-tier spin-down.
* **[export.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/export.py)**: Generates **CSV, JSON, XML, and Apache Parquet** exports, including memory-flat streaming generators (`stream_csv`, `stream_json`) for unlimited full exports (`?full=true`).
* **[quarantine.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/quarantine.py)**, **[data_admin.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/data_admin.py)**, **[harvest_runs.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/harvest_runs.py)**, **[admin_store.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/admin_store.py)**: Governance services backing the `#/admin` portal.
* **[discoverability.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/discoverability.py)**: Builds `schema.org/DataCatalog` JSON-LD, `DCAT-AP` JSON-LD, dynamic XML sitemaps, and PWA icons for all 11 sectors.

---

## 4. Frontend Architecture (`app/static/`)

The frontend is a fast, zero-build Single Page Application (SPA) written in modular ES6 JavaScript:
* **Router ([js/router.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/router.js))**: Client-side hash router (`#/home`, `#/data`, `#/sectors`, `#/sources`, `#/insights`, `#/api`, `#/status`, `#/terms`, `#/admin`).
* **Internationalization ([js/i18n.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/i18n.js))**: Instant FR/EN translation of the shell, views, indicator labels, and data-science narratives.
* **Views (`js/views/`)**:
  * **[home.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/views/home.js)**: Hero metrics, interactive market & weather assistant widget, mission statement, and sector cards.
  * **[data.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/views/data.js)**: Interactive data explorer with full-text search, sector/region filters, chart visualization, and pagination.
  * **[sectors.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/views/sectors.js)**: Deep-dive dashboards for all 11 sectors with Chart.js visualizations.
  * **[sources.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/views/sources.js)**: Live source catalog with licensing metadata and real-time freshness indicators.
  * **[insights.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/views/insights.js)**: Cross-sector correlations, seasonal anomalies, spatial coverage, and AI study generator.
  * **[api.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/views/api.js)**: Compact interactive endpoint selector (`cURL` / `Python` / `JS`), archive generator (`CSV`, `JSON`, `XML`, `Parquet`), and streaming full-export trigger.
  * **[status.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/views/status.js)**: Live pipeline audit (`table_raw` → `table_clean` → `table_public`), scheduler status, and source freshness table.
  * **[terms.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/views/terms.js)**: CC BY 4.0 open license, attribution rules, and privacy policy.
  * **[admin.js](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/static/js/views/admin.js)**: Authenticated back-office for harvest triggers, quarantine review, observation editing/deletion, AI study moderation, assistant logs, and team management.

---

## 5. Quality Assurance & CI/CD (`.github/workflows/`)

* **[ci.yml](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/.github/workflows/ci.yml)**: Runs on every push and PR on `ubuntu-24.04` (Python 3.13):
  1. `tests`: 740+ unit, integration, security, and schema tests (`pytest --ignore=tests/e2e`).
  2. `browser-tests`: Full end-to-end Chromium browser suite via Playwright (`pytest tests/e2e`).
  3. `security`: Static linting (`ruff`), security scanning (`bandit`), and dependency vulnerability audit (`pip-audit`).
* **[scheduled_harvest.yml](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/.github/workflows/scheduled_harvest.yml)**: Daily automated harvest triggering `/api/v1/collection/run-scheduled-harvest`.
* **[keep_warm.yml](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/.github/workflows/keep_warm.yml)**: Pings `/api/v1/health` every 14 minutes 24/7 so the Render container never spins down.
