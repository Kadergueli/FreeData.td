# FreeData.td — Technical Specification: Agent Ingestion Engine, Rate Limiting & Resilience

## 1. Overview & Architecture

The **FreeData.td Agent Ingestion Engine** autonomously collects, cleans, validates, and stores socio-economic and environmental datasets for Chad (Tchad) across **11 sectors** from verified national and international public data providers.

All sector agents inherit from [`BaseAgent`](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/base.py) and follow a standardized collection, validation, quarantine, and storage lifecycle:

```text
+-----------------------------------------------------------------------------------+
|                                   BASE AGENT                                      |
| - HTTP Rate Limiting & Exponential Backoff (`fetch_json_with_retry`)              |
| - Data Science Rules (3*IQR Outlier Detection, Domain Bounds, Quarantine Routing) |
| - Defensive Parsing, Source Freshness Tracking & Anti-Crash Isolation             |
+-----------------------------------------------------------------------------------+
     |             |             |             |             |             |
+---------+   +---------+   +---------+   +---------+   +---------+   +---------+
|  Agri   |   | Markets |   |  Envir  |   | Economy |   | Health  |   | Energy  |
+---------+   +---------+   +---------+   +---------+   +---------+   +---------+
     |             |             |             |             |
+---------+   +---------+   +---------+   +---------+   +---------+
|Transport|   |Education|   |Demograph|   | Telecom |   |  Trade  |
+---------+   +---------+   +---------+   +---------+   +---------+
```

---

## 2. Rate Limiting & API Courtesy Policy

To comply with external public API terms of service and prevent IP bans or upstream server overload, all network communications enforce strict controls:

### 2.1 Request Throttling & Spacing
* Every HTTP GET query executed by `BaseAgent.fetch_json_with_retry` and `fetch_text_with_retry` introduces a minimum **0.15s to 0.20s delay** between consecutive requests.
* Regional sweeps (e.g., Open-Meteo, NASA POWER, or OpenStreetMap Overpass queries across the 23 Chadian provinces) execute sequentially with polite pauses.

### 2.2 HTTP 429 (Too Many Requests) & Exponential Backoff
* When an upstream API responds with **HTTP 429**, the agent inspects the `Retry-After` response header and waits the requested duration.
* If no header is provided, an exponential backoff formula is applied:
  $$\text{Wait Time} = 2^{\text{attempt}} \text{ seconds}$$
* Transient network errors or HTTP 5xx responses are retried up to 3 times before recording a structured failure note in `source_errors`.

### 2.3 Honest User-Agent & Anti-Bot Compliance
All HTTP requests declare the platform identity:
```http
User-Agent: FreeData.td Open Data Engine/1.0 (+https://freedata-td.onrender.com)
```
When an upstream portal (such as INSEED's SDMX server behind Cloudflare) presents an anti-bot challenge, the agent **never** attempts to bypass it; it logs the block cleanly and relies on the documented administrator offline import workflow (`python -m app.cli probe-inseed` / `import-inseed`).

---

## 3. Data Science Validation & Quarantine Pipeline

Every collected observation passes through a 3-stage medallion pipeline (`table_raw` → `table_clean` → `table_public`) with automated quality gates:

1. **Structural & Temporal Validation**: Verifies non-null numerical values, valid ISO dates, standardized units, and canonical regional names ([app/regions.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/regions.py)).
2. **Domain Bound & Statistical Outlier Detection ($3 \times \text{IQR}$)**:
   * Impossible domain values (e.g., percentages outside $[0, 100]$ where bounded, negative yields or prices, impossible temperatures) and statistical outliers exceeding $3 \times \text{IQR}$ are flagged `SUPERVISOR_REVIEW`.
3. **Supervisor Quarantine ([app/services/quarantine.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/quarantine.py))**:
   * Rows flagged `SUPERVISOR_REVIEW` are held in `table_quarantine` instead of being published blindly to `table_public`.
   * Administrators review, approve, correct, or reject quarantined observations in `#/admin` (tab **Qualité**), with full audit logging in `table_admin_audit`.

---

## 4. Deduplication & Storage Protection

### 4.1 Unique Composite Key
Both Supabase (`table_public`) and SQLite (`observations`) enforce a strict composite uniqueness constraint:
$$\text{UNIQUE}(\text{sector}, \text{indicator}, \text{reference\_date}, \text{region}, \text{source})$$

### 4.2 Idempotent Upserts & Respect of Admin Decisions
* Re-running a collector updates existing rows in place without creating duplicates.
* Observations deleted or corrected by an administrator (`table_deleted_observations` via [app/services/data_admin.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/data_admin.py)) are respected on subsequent harvests unless the upstream provider publishes a revised value.

---

## 5. Scheduling, Cadence & Keep-Alive (`app/services/cadence.py` & `scheduler.py`)

Each sector is harvested according to the natural update rhythm of its upstream sources ([app/services/cadence.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/cadence.py)):

| Sector | Cadence | Primary Upstream Sources |
|---|---|---|
| `agriculture` | Daily / Weekly | World Bank, Open-Meteo (23 regions), NASA POWER |
| `markets` | Daily / Weekly | FEWS NET, WFP (HDX HAPI / CSV), FAOSTAT, World Bank, INSEED |
| `environment` | Daily | Open-Meteo (23 regions), NASA POWER, NASA FIRMS, World Bank |
| `economy` | Weekly / Monthly | World Bank (WDI), IMF (WEO DataMapper) |
| `health` | Weekly / Monthly | WHO GHO, DHS Program (23 regions), UNICEF, OpenStreetMap, World Bank, INSEED |
| `energy` | Monthly | World Bank (SE4ALL), NASA POWER (solar & wind across 23 regions) |
| `transport` | Monthly | OurAirports (23 regions), Open-Meteo, World Bank |
| `education` | Monthly | UNESCO UIS, UNICEF, OpenStreetMap (schools across 23 regions), World Bank, INSEED |
| `demography` | Monthly | World Bank (WDI), UNHCR (refugees/IDPs), INSEED (RGPH census) |
| `telecom` | Monthly | World Bank / ITU (Internet, mobile, broadband, ICT trade) |
| `trade` | Monthly | World Bank (WDI), World Bank Commodity Markets (*Pink Sheet*) |

In addition to harvesting, [`SchedulerService`](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/services/scheduler.py) runs a background `_keep_alive_loop` every **14 minutes** targeting `settings.target_keep_alive_url` so Render deployments never enter idle sleep after 15 minutes of inactivity.

---

## 6. Inventory of Agent Modules (`app/agents/`)

### Sector Agents
* [app/agents/base.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/base.py): Base class (`BaseAgent`) defining HTTP retry logic, Data Science validation rules, and pipeline orchestration.
* [app/agents/wb_sector.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/wb_sector.py): Shared base class (`WorldBankSectorAgent`) for World Bank WDI sector collectors.
* [app/agents/agriculture.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/agriculture.py): `AgricultureAgent` (`agriculture`).
* [app/agents/markets.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/markets.py): `MarketsAgent` (`markets`).
* [app/agents/environment.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/environment.py): `EnvironmentAgent` (`environment`).
* [app/agents/economy.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/economy.py): `EconomyAgent` (`economy`).
* [app/agents/health.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/health.py): `HealthAgent` (`health`).
* [app/agents/energy.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/energy.py): `EnergyAgent` (`energy`).
* [app/agents/transport.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/transport.py): `TransportAgent` (`transport`).
* [app/agents/education.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/education.py): `EducationAgent` (`education`).
* [app/agents/demography.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/demography.py): `DemographyAgent` (`demography`).
* [app/agents/telecom.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/telecom.py): `TelecomAgent` (`telecom`).
* [app/agents/trade.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/trade.py): `TradeAgent` (`trade`).

### Specialized Source Connectors & Analytics
* [app/agents/fews_prices.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/fews_prices.py): FEWS NET market price parser and collision resolver.
* [app/agents/wfp_prices.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/wfp_prices.py): WFP market price connector (HDX HAPI + CSV fallback).
* [app/agents/imf.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/imf.py): IMF World Economic Outlook (WEO) DataMapper parser.
* [app/agents/who_gho.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/who_gho.py): WHO Global Health Observatory OData connector.
* [app/agents/dhs.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/dhs.py): DHS Program subnational survey connector for Chad's provinces.
* [app/agents/unicef.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/unicef.py): UNICEF SDMX connector (child health, nutrition, immunization, education).
* [app/agents/unesco_uis.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/unesco_uis.py): UNESCO Institute for Statistics (UIS) connector.
* [app/agents/osm.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/osm.py): OpenStreetMap Overpass regional infrastructure counter (schools, hospitals, pharmacies, water points).
* [app/agents/airports.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/airports.py): OurAirports connector mapping Chadian airports and airstrips to the 23 provinces.
* [app/agents/pink_sheet.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/pink_sheet.py): World Bank Commodity Markets (*Pink Sheet*) monthly workbook parser.
* [app/agents/inseed.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/inseed.py): INSEED SDMX XML parser and dataset registry.
* [app/agents/ds_insights.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/ds_insights.py): Cross-sector correlations, seasonal anomalies, spatial coverage, and freshness scoring.
* [app/agents/analysis.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/analysis.py): AI study generator (Groq LLM + deterministic statistical fallback).
