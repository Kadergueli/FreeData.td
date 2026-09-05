# Technical Architecture & Complete Project Analysis: FreeData.td MVP

## 1. Executive Summary / Présentation Générale

**FreeData.td** is an autonomous, open-data aggregation and analytics platform dedicated to Chad (Tchad). The project aims to collect, standardize, validate, and visualize public data across multiple critical socio-economic sectors.

### Key Objectives
* **Data Sovereignty & Transparency**: Provide easy, centralized access to official statistics and socio-economic datasets concerning Chad.
* **Autonomous Ingestion**: Implement specialized domain agents that periodically query, parse, and validate data from verified national and international public data sources.
* **AI-Powered Analytics**: Generate automated cross-sector insights, trends, and anomaly detection using analytical agent modules.
* **Bilingual Accessibility**: Full internationalization support (English and French) across both the backend data models and frontend user interface.

---

## 2. System Architecture Overview

```
+-----------------------------------------------------------------------+
|                            USER INTERFACE                             |
|    Vanilla JS SPA Router | Chart.js | i18n (FR/EN) | Glassmorphism    |
+-----------------------------------------------------------------------+
                                   | HTTP / REST API
+-----------------------------------------------------------------------+
|                          FASTAPI APPLICATION                          |
|  - Main Router (`app/main.py`)                                         |
|  - Security & Rate Limiting (`app/security.py`)                        |
|  - Schemas & Validation (`app/schemas/`)                              |
+-----------------------------------------------------------------------+
                 |                                      |
+---------------------------------+   +---------------------------------+
|          AGENT ENGINE           |   |         SERVICES LAYER          |
| - Base Scraper Agent            |   | - Storage Engine (SQLite/DB)    |
| - 6 Sector Agents               |   | - Background Scheduler          |
| - AI Analytical Agent           |   | - Export Engine (CSV/JSON/XLSX) |
+---------------------------------+   +---------------------------------+
                 |
+-----------------------------------------------------------------------+
|                      10 OFFICIAL DATA SOURCES                         |
| INSEED | BEAC | World Bank | FAOSTAT | WHO | UNESCO | UNICEF | HDX | BAD | PNUD |
+-----------------------------------------------------------------------+
```

---

## 3. Core Components Analysis

### 3.1 Backend Application (`app/`)
* **`main.py`**: Entry point powering the FastAPI REST server. Handles route definitions, middleware setup (CORS, compression), startup events (database migration, background scheduler launch), and static file serving.
* **`config.py`**: Configuration manager leveraging Pydantic Settings. Manages environment variables (`.env`), database URLs, cache TTLs, and API tokens.
* **`security.py`**: Provides security headers, input sanitization, CORS restrictions, and rate-limiting controls for API endpoints.

### 3.2 Agent Ingestion Engine (`app/agents/`)
Each sector is monitored by an autonomous agent inheriting from `BaseAgent` (`app/agents/base.py`):
* **`base.py`**: Provides standardized lifecycle, exponential backoff retries (`fetch_json_with_retry`), HTTP 429 rate-limiting throttling (0.15s delay, `Retry-After` header handling), polite `User-Agent` headers, and defensive schema parsing.
* **`agriculture.py`**: Scrapes & aggregates crop yields, livestock numbers, and rainfall statistics from FAOSTAT, NASA POWER, and Open-Meteo.
* **`economy.py`**: Extracts GDP, inflation rates, exchange rates, and national debt metrics from BEAC and the World Bank.
* **`education.py`**: Tracks literacy rates, school enrollment, and pupil-teacher ratios from UNESCO and UNICEF.
* **`environment.py`**: Monitors forest cover, temperature anomalies, and carbon emissions from HDX, NASA FIRMS, and Open-Meteo.
* **`markets.py`**: Collects cereal prices, fuel tariffs, and market consumer indexes across major Chadian regional hubs.
* **`transport.py`**: Aggregates road infrastructure density, flight volume, and logistics connectivity metrics.
* **`analysis.py`**: Analytical engine performing cross-agent data fusion, statistical anomaly detection, and automated text summaries.

* **Rate Limiting & Throttling**: Requests are spaced with minimum 0.15s-0.20s delays; HTTP 429 (Too Many Requests) and HTTP 5xx errors trigger automatic exponential backoff retries without blocking.
* **Deduplication & Anti-Saturation**: Strict `UNIQUE(sector, indicator, reference_date, region, source)` database constraints prevent duplicate insertions (`ON CONFLICT DO UPDATE`), preserving storage efficiency.
* **Schema Resilience & Anti-Crash**: Defensive `.get()` parsing and isolated try/except wrappers ensure that structural changes or unexpected nulls from remote APIs never crash the agent threads or scheduler loops.

### 3.3 Data Model & Validation (`app/schemas/`)
* **`observation.py`**: Pydantic schema enforcing structured data format (`ObservationCreate`, `ObservationResponse`):
  * `id`: Unique Hash ID
  * `sector`: Target sector identifier
  * `indicator`: Standardized indicator key
  * `value`: Floating point numerical value
  * `unit`: Measurement unit (e.g., %, Tonnes, FCFA)
  * `date`: Temporal stamp
  * `source_id`: Reference to official source catalog
  * `metadata`: Dynamic attributes (geolocation, confidence score, notes)

### 3.4 Services & Storage Layer (`app/services/`)
* **`storage.py`**: High-performance SQLite engine with JSON fallback mode. Supports indexing, full-text search, pagination, and multi-field filtering.
* **`scheduler.py`**: Async background worker that coordinates periodic agent runs, preventing stale data and respecting source server rate limits.
* **`export.py`**: Export service supporting CSV, JSON, and Excel format generation on-the-fly.

---

## 4. Official Data Sources Catalog (10 Verified Sources)

The platform actively aggregates data from 10 verified national and international organizations:

| # | Source Name | Key Indicators / Data Domain | Official Website |
|---|-------------|------------------------------|------------------|
| 1 | **INSEED** (Institut National de la Statistique) | Demographics, CPI Inflation, Trade Balance | [inseed.td](https://www.inseed.td) |
| 2 | **BEAC** (Banque des États de l'Afrique Centrale) | Monetary Policy, Reserves, Exchange Rates | [beac.int](https://www.beac.int) |
| 3 | **World Bank - Chad** | GDP Growth, Poverty Metrics, Development Grants | [worldbank.org/en/country/chad](https://www.worldbank.org/en/country/chad) |
| 4 | **FAOSTAT - Tchad** | Agriculture, Crop Production, Food Security | [fao.org/faostat](https://www.fao.org/faostat) |
| 5 | **WHO / OMS - Chad** | Public Health, Vaccination Rates, Disease Outbreaks | [who.int/countries/tcd](https://www.who.int/countries/tcd) |
| 6 | **UNESCO Institute for Statistics** | School Enrollment, Literacy, Educational Funding | [uis.unesco.org](https://uis.unesco.org) |
| 7 | **UNICEF Chad Data** | Child Welfare, Malnutrition, Youth Education | [unicef.org/chad](https://www.unicef.org/chad) |
| 8 | **HDX - Humanitarian Data Exchange** | Climate Hazards, Displacement, Humanitarian Need | [data.humdata.org/group/tcd](https://data.humdata.org/group/tcd) |
| 9 | **AfDB / BAD** | Infrastructure, Energy Access, Macroeconomic Outlook | [afdb.org/en/countries/central-africa/chad](https://www.afdb.org/en/countries/central-africa/chad) |
| 10 | **UNDP / PNUD Tchad** | Human Development Index (HDI), Local Governance | [undp.org/fr/chad](https://www.undp.org/fr/chad) |

---

## 5. Frontend Architecture & Dynamic Features (`app/static/`)

The frontend is designed as a modern, responsive Single Page Application (SPA) without heavy framework bloat:

* **Router (`js/router.js`)**: Client-side hash routing `#home`, `#data`, `#sectors`, `#sources`, `#insights`, `#api`, `#status`.
* **Internationalization (`js/i18n.js`)**: Dynamic language switcher (FR/EN) supporting instant UI translation and localized data formatting.
* **Views**:
  * **Home (`views/home.js`)**: Hero section, key platform metrics, institutional mission statement, 4-pillar capabilities grid (Multi-Source Harvest, QA & Governance, Open APIs, Visual Analytics), featured sector overview, and latest database observations stream.
  * **Data Explorer (`views/data.js`)**: Interactive table with real-time text filter, sector selectors, date range pickers, pagination, and download buttons.
  * **Sectors View (`views/sectors.js`)**: In-depth sector dashboards featuring dynamic Chart.js visualizations.
  * **Sources Catalog (`views/sources.js`)**: Dedicated interactive view listing all 10 sources with direct links, license policies, and ingest health statuses.
  * **Insights View (`views/insights.js`)**: AI-generated analytical summaries and multi-variable correlations.
  * **API Portal (`views/api.js`)**: Interactive documentation for developers wishing to consume FreeData.td endpoints.
  * **Status & Monitoring (`views/status.js`)**: Real-time system diagnostics, backend uptime, memory usage, and background scheduler task status.
  * **Terms & License (`views/terms.js`)**: Interactive legal notice, CC BY 4.0 license policy, citation format guidelines, API fair use policies, and privacy protection terms.

---

## 6. Testing & Quality Assurance

The codebase features comprehensive unit and integration tests located in `tests/`:
* `test_agriculture_agent.py`: Validates scraping logic, fallback data handling, and schema parsing for agriculture.
* `test_environment_agent.py`: Tests environmental data extraction, anomaly detection, and missing field handling.
* `test_analysis_security.py`: Ensures API security headers, SQL injection protection, and agent execution safety.

> [!NOTE]
> For complete technical specifications on Agent Rate Limiting, Deduplication, and Fault-Tolerance, see [agents_specification.md](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/docs/agents_specification.md).

---

## 7. Future Recommendations & Scaling Roadmap

1. **Database Scaling**: Migration path from local SQLite storage to distributed PostgreSQL/Supabase instance for heavy production traffic.
2. **GraphQL API**: Adding a GraphQL endpoint alongside existing REST API for targeted mobile app queries.
3. **Geospatial Mapping**: Enhancing front-end chart visualizers with Leaflet/Mapbox interactive maps for Chadian regional breakdown (Provinces/Departments).
4. **Agent Expansion**: Adding real-time weather scraping via satellite APIs (Copernicus/NASA EarthData).
