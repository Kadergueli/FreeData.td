# FreeData.td 🇹🇩

> **An Open AI-Powered Socioeconomic Data Infrastructure for Chad**

[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE)
[![Data License: CC BY 4.0](https://img.shields.io/badge/Data-CC%20BY%204.0-green.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.2.0-009688.svg)]()

---

## 1. Vision & Objective

Chad suffers from a chronic deficit of centralized, structured, and machine-readable public statistics. Researchers, farmers, NGOs, students, startups, and policymakers all face the same barrier: socioeconomic data is scattered across dozens of national and international portals.

**FreeData.td** addresses this challenge by autonomously collecting, cleaning, validating, and openly publishing socioeconomic and agro-climatic observations across all **23 official provinces of Chad** — free of charge, requiring no API key for reading, under the **CC BY 4.0** open license.

---

## 2. Covered Sectors (11 Production Sectors)

| Sector | API Identifier | Primary Upstream Sources | Geographic Scope | Status |
|---|---|---|---|---|
| 🌾 **Agriculture** | `agriculture` | World Bank (WDI), Open-Meteo, NASA POWER | National & 23 regions | ✅ Production |
| 🛒 **Markets & Prices** | `markets` | FEWS NET, WFP (HDX HAPI), FAOSTAT, World Bank, INSEED | Regional markets & National | ✅ Production |
| 🌍 **Environment** | `environment` | Open-Meteo, NASA POWER, NASA FIRMS (active fires), World Bank | National & 23 regions | ✅ Production |
| 💰 **Economy** | `economy` | World Bank (WDI), IMF (WEO), BEAC | National | ✅ Production |
| 🏥 **Health** | `health` | WHO (GHO), DHS Program, UNICEF (SDMX), OpenStreetMap, World Bank, INSEED | National & 23 regions | ✅ Production |
| ⚡ **Energy** | `energy` | World Bank (SE4ALL / IEA), NASA POWER (solar & wind potential) | National & 23 regions | ✅ Production |
| 🚗 **Transport** | `transport` | OurAirports, Open-Meteo, World Bank | National & 23 regions | ✅ Production |
| 📚 **Education** | `education` | UNESCO UIS, UNICEF (SDMX), OpenStreetMap (schools by region), World Bank, INSEED | National & 23 regions | ✅ Production |
| 👥 **Demography** | `demography` | World Bank (WDI), UNHCR (refugees & IDPs), INSEED (RGPH census) | National & 23 regions | ✅ Production |
| 📡 **Telecom** | `telecom` | World Bank / ITU (Internet, mobile cellular, broadband, ICT trade) | National | ✅ Production |
| 🚢 **Foreign Trade** | `trade` | World Bank, World Bank Commodity Markets (*Pink Sheet*) | National & Global | ✅ Production |

---

## 3. Key Capabilities

- 🤖 **Autonomous Multi-Source Ingestion**: 11 domain agents with cadence-aware scheduling (`app/services/cadence.py`), statistical outlier detection ($3 \times \text{IQR}$ and domain bounds), strict deduplication, and automatic quarantine of suspicious values (`SUPERVISOR_REVIEW`).
- 🌱 **Crop Suitability Engine (`app/crops/`)**: Evaluates and ranks staple and cash crops in Chad (pearl millet, sorghum, maize, groundnut, sesame, cowpea, rice, cassava, cotton, onion, okra, etc.) across all **23 regions** using the **FAO EcoCrop** method (Liebig's law of the minimum with trapezoid scoring) combined with **NASA POWER** climatology (`climate.json`) and **SoilGrids 2.0 / ISRIC** soil profiles (`soils.json`).
- 🧠 **Data Science Analytics & AI Studies (`#/insights`)**: Pure-Python cross-sector correlations (Pearson/Spearman with temporal lag detection), seasonal anomalies (Z-score), spatial coverage, source freshness scoring, and bilingual study generation powered by Groq LLM (with a deterministic offline statistical fallback).
- 💬 **Conversational Data Assistant & WhatsApp Bot (`app/assistant/`, `app/whatsapp.py`)**: Answers natural-language questions (French/English, typo-tolerant) on market commodity prices and regional weather via the web interface and the **Meta WhatsApp Cloud API** webhook.
- 📥 **Open Exports & Streaming (`#/api`)**: Direct downloads in **CSV, JSON, XML, and Apache Parquet**, including memory-flat unlimited streaming exports (`?full=true`) and cursor pagination (`X-Next-Offset`).
- 🌐 **Open Data Discoverability & PWA**: Installable Progressive Web App (`/manifest.webmanifest`, `/sw.js`), standardized **Schema.org JSON-LD** (`/api/v1/catalog.jsonld`) and **DCAT-AP** (`/api/v1/catalog.dcat.json`) feeds, `/sitemap.xml`, and `/robots.txt`.
- 🛡️ **Administration & Governance Portal (`#/admin`)**: Protected by Supabase Auth + email allowlisting (`ADMIN_EMAILS` / `table_admins`), featuring quarantine review, audited data editing/deletion with mandatory rationale, harvest run history, and team management.

---

## 4. Architecture & Project Structure

```text
FreeDatatd-MVP/
├── app/
│   ├── main.py                  # FastAPI entry point, public routes, CSP/CORS/Cache/Rate-limit middleware
│   ├── config.py                # Pydantic Settings configuration (.env)
│   ├── security.py              # Per-IP rate limiting, collection API key auth, security helpers
│   ├── admin.py                 # Admin routes (/api/v1/admin/*) & Supabase JWT verification
│   ├── whatsapp.py              # Meta WhatsApp Cloud API webhook (/api/v1/whatsapp/webhook)
│   ├── regions.py               # Canonical registry of Chad's 23 provinces and alias normalization
│   ├── cli.py                   # Command-line tools (collection, exports, live probes, INSEED import)
│   ├── agents/                  # Autonomous ingestion engine (11 sector agents + specialized connectors)
│   │   ├── base.py              # BaseAgent class (exponential backoff, Data Science rules, pipeline)
│   │   ├── agriculture.py       # Agriculture, livestock & agro-meteorology
│   │   ├── markets.py           # Market prices & food indices (FEWS NET, WFP, FAOSTAT, WB)
│   │   ├── environment.py       # Climate, forest cover & NASA FIRMS active fires
│   │   ├── economy.py           # Macroeconomics, GDP, debt & public finance (WB, IMF WEO)
│   │   ├── health.py            # Public health (WHO GHO, DHS, UNICEF, OSM hospitals/pharmacies/water, WB)
│   │   ├── energy.py            # Electricity access & regional solar/wind potential (WB, NASA POWER)
│   │   ├── transport.py         # Air infrastructure (OurAirports), logistics & regional weather
│   │   ├── education.py         # Enrollment, literacy & school infrastructure (UNESCO, UNICEF, OSM, WB)
│   │   ├── demography.py        # Demography, vital statistics & refugees (WB, UNHCR, INSEED)
│   │   ├── telecom.py           # Telecommunications & digital access (WB / ITU)
│   │   ├── trade.py             # Foreign trade & global commodity prices (WB, Pink Sheet)
│   │   ├── analysis.py          # AI study report generator (Groq LLM + statistical fallback)
│   │   ├── ds_insights.py       # Pure-Python Data Science metrics (correlations, anomalies, freshness, coverage)
│   │   └── ...                  # Connectors: fews_prices, wfp_prices, imf, who_gho, dhs, unesco_uis, unicef, osm, airports, pink_sheet, inseed, wb_sector
│   ├── crops/                   # Crop suitability engine (FAO EcoCrop + NASA POWER + SoilGrids 2.0)
│   │   ├── api.py               # REST endpoints (/api/v1/crops, /api/v1/crops/suitability)
│   │   ├── engine.py            # Trapezoid scoring and ranking via Liebig's law of the minimum
│   │   ├── profile.py           # Rainy-season agro-climatic profile builder
│   │   ├── sites.py             # Regional soil & climate loader with fuzzy region matching
│   │   ├── requirements.json    # Verified FAO EcoCrop agronomic parameters per crop
│   │   ├── soils.json           # Regional soil pH, clay, sand, and organic carbon (0-30 cm)
│   │   ├── climate.json         # Regional monthly mean rainfall (mm/day) and temperature (°C)
│   │   ├── soils_chad.py        # SoilGrids 2.0 extraction script (COG/VRT reader)
│   │   └── climate_chad.py      # NASA POWER climatology extraction script
│   ├── assistant/               # Conversational data assistant (market prices & weather)
│   │   ├── engine.py            # Intent routing, guardrails, and response orchestration
│   │   ├── markets.py           # Commodity price lookup and trend synthesis by market
│   │   ├── weather.py           # Regional weather summaries and forecasts
│   │   ├── spellfix.py          # Typo-tolerant fuzzy matcher (cities, provinces, crops)
│   │   └── ...                  # cache.py, guardrails.py, rich.py, text.py
│   ├── schemas/                 # Pydantic models (ObservationCreate, ObservationRecord, StudyReport...)
│   ├── services/                # Business logic, storage, and background orchestration
│   │   ├── storage.py           # Hybrid repository: Supabase (table_raw/clean/public) + local SQLite fallback
│   │   ├── scheduler.py         # Background harvester + 14-minute Render keep-alive loop
│   │   ├── cadence.py           # Per-sector collection cadence (daily, weekly, monthly)
│   │   ├── export.py            # CSV, JSON, XML, Parquet generation & full streaming exports
│   │   ├── discoverability.py   # Schema.org JSON-LD, DCAT-AP, XML Sitemap & PWA icons
│   │   ├── quarantine.py        # Quarantine store for out-of-domain / suspicious observations
│   │   ├── data_admin.py        # Audited correction, deletion, and restoration of published rows
│   │   ├── harvest_runs.py      # Persistent history of collection runs
│   │   ├── freshness.py         # Per-source data freshness calculator
│   │   ├── admin_store.py       # Administrator allowlist and audit log persistence
│   │   └── assistant_log.py     # Anonymized query logging and per-user rate limits
│   └── static/                  # Frontend SPA (Vanilla ES6 Modules, CSS, Chart.js, Lucide, PWA)
│       ├── index.html           # HTML5 shell + Schema.org microdata + responsive navigation
│       ├── manifest.webmanifest # Progressive Web App manifest
│       ├── sw.js                # Service Worker (offline shell caching)
│       ├── css/                 # Stylesheets (main.css, components.css)
│       └── js/                  # SPA router, FR/EN i18n, API client, and 9 views (home, data, sectors, sources, insights, api, status, terms, admin)
├── supabase/                    # SQL schema setup, RLS policies, aggregation RPCs, and maintenance scripts
├── tests/                       # Pytest suite (unit, API, security) + Playwright E2E browser tests (tests/e2e/)
├── docs/                        # Technical documentation (architecture.md, agents_specification.md, deployment.md)
└── .github/workflows/           # CI pipeline (ci.yml), daily harvest (scheduled_harvest.yml), keep-warm (keep_warm.yml)
```

---

## 5. Quick Start (Local Development)

```powershell
git clone https://github.com/Kadergueli/FreeData.td.git
cd FreeData.td
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env

# Seed a deterministic demo dataset and start the server
python -m app.cli collect-agriculture --demo
uvicorn app.main:app --reload
```

- **Web Portal**: `http://127.0.0.1:8000`
- **Interactive OpenAPI Documentation (Swagger)**: `http://127.0.0.1:8000/docs`
- **Admin Portal**: `http://127.0.0.1:8000/#/admin` (or press `Ctrl + Shift + A` from any page)

*(When `SUPABASE_URL` is left blank in `.env`, the application automatically uses a local SQLite database at `data/freedatatd.db`).*

---

## 6. Core Public API Endpoints

All public read endpoints are **open and keyless** (protected by per-IP courtesy rate limits: 120 reads/min, 10 exports/min):

- `GET /api/v1/observations?sector=markets&region=Lac&q=mil&limit=200&offset=0` — Filtered and paginated observations (`X-Next-Offset` response header indicates the next page).
- `GET /api/v1/stats` — Global observation counts, sector/region breakdown, and validation score.
- `GET /api/v1/catalog` | `/api/v1/catalog.jsonld` | `/api/v1/catalog.dcat.json` — Dataset catalog (JSON, Schema.org JSON-LD, DCAT-AP).
- `GET /api/v1/regions` — Distinct regions currently represented in the database.
- `GET /api/v1/crops` & `GET /api/v1/crops/suitability?region=Moundou&crop=sorghum` — Evaluable crops and regional agro-climatic suitability rankings.
- `GET /api/v1/insights/cross-sector` — Cross-sector correlations, seasonal anomalies, spatial coverage, and freshness scores.
- `GET /api/v1/studies` & `POST /api/v1/studies?sector=agriculture` — Study library and AI report generation.
- `GET /api/v1/export/{csv|json|xml|parquet}?sector=agriculture&region=...` — Direct file downloads (`&full=true` on CSV/JSON streams every matching row with no row cap).
- `GET /api/v1/health` & `GET /api/v1/sources/freshness` — System health, scheduler state, and upstream source freshness.

---

## 7. CLI Commands & Testing

```powershell
# CLI collection and export
python -m app.cli collect-agriculture --source world-bank
python -m app.cli export --sector agriculture --format csv

# Live upstream diagnostics (no database required)
python -m app.cli probe-prices    # Probe the FEWS NET market-price API for Chad
python -m app.cli probe-sources   # Probe IMF, WFP (HDX), OurAirports, and OpenStreetMap
python -m app.cli probe-inseed    # Download INSEED SDMX flows into data/raw/
python -m app.cli import-inseed   # Ingest saved data/raw/inseed_*.xml files into the pipeline

# Refresh regional soil & climate reference files (23 regions)
python app/crops/soils_chad.py    # Generate app/crops/soils.json (SoilGrids 2.0)
python app/crops/climate_chad.py  # Generate app/crops/climate.json (NASA POWER)

# Run automated test suites
pip install -r requirements-dev.txt
python -m pytest -q --ignore=tests/e2e
python -m pytest -q tests/e2e     # Requires: playwright install chromium
```

---

## 8. Additional Documentation

- 📐 **Technical Architecture**: [docs/architecture.md](docs/architecture.md)
- 🤖 **Agent Specification, Rate Limiting & Resilience**: [docs/agents_specification.md](docs/agents_specification.md)
- 🚀 **Deployment Guide (Render, Supabase, GitHub Actions, WhatsApp, Keep-Alive)**: [docs/deployment.md](docs/deployment.md)
- 🗄️ **Supabase SQL Setup Order**: [supabase/README.md](supabase/README.md)
- ⚖️ **Data Ethics Charter**: [ETHICS.md](ETHICS.md)
