# FreeData.td — Technical Specification: Agent Ingestion Engine, Rate Limiting & Resilience

## 1. Overview & Architecture

The **FreeData.td Agent Ingestion Engine** is designed to autonomously collect, clean, validate, and store socio-economic datasets for Chad (Tchad) from 10 verified national and international public data providers.

All sector agents inherit from `BaseAgent` (`app/agents/base.py`) and implement a standardized collection and data science lifecycle:

```
+-------------------------------------------------------------------------+
|                              BASE AGENT                                 |
| - HTTP Rate Limiting & Retry Backoff (`fetch_json_with_retry`)          |
| - Data Science Rules (3*IQR Outlier Detection, Domain Flags)            |
| - Defensive Parsing & Anti-Crash Exceptions Handling                   |
+-------------------------------------------------------------------------+
       |                  |                  |                  |
+--------------+   +--------------+   +--------------+   +--------------+
| Agriculture  |   |   Economy    |   |  Education   |   | Environment  |
|    Agent     |   |    Agent     |   |    Agent     |   |    Agent     |
+--------------+   +--------------+   +--------------+   +--------------+
       |                  |
+--------------+   +--------------+
|   Markets    |   |  Transport   |
|    Agent     |   |    Agent     |
+--------------+   +--------------+
```

---

## 2. Rate Limiting & API Courtesy Policy

To ensure compliance with external public API terms of service and avoid IP bans or server overload, all network communications implement the following controls:

### 2.1 Request Throttling & Spacing
* Every HTTP GET query executed by `BaseAgent.fetch_json_with_retry` and `fetch_text_with_retry` introduces a minimum **0.15s to 0.20s delay** between consecutive requests.
* Bulk iteration loops (e.g. World Bank indicator sweeps across 13 indicators) are executed sequentially with throttling rather than parallel flooding.

### 2.2 HTTP 429 (Too Many Requests) & Exponential Backoff
* When an external API responds with **HTTP 429**, the agent parses the `Retry-After` response header.
* If `Retry-After` is specified, the agent sleeps for the exact duration requested by the remote server.
* If no header is provided, an exponential backoff formula is applied:
  $$\text{Wait Time} = 2^{\text{attempt}} \text{ seconds}$$
* Network failures or HTTP 5xx (Internal Server Errors) are retried up to 3 times before failing gracefully.

### 2.3 User-Agent Identification
All HTTP headers explicitly declare the platform identity and contact:
```http
User-Agent: FreeData.td Open Data Engine/1.0 (+https://freedata.td)
```

---

## 3. Fault Tolerance & Anti-Crash Mechanisms

Public data sources frequently update their API structures, rename JSON keys, return HTML error pages during maintenance, or report null values. The agent engine ensures **100% platform stability** through:

### 3.1 Defensive Parsing
* All JSON payloads are validated using explicit type assertions (`isinstance(payload, list)`, `isinstance(data, dict)`).
* Numerical field extractions use safe conversions:
  ```python
  try:
      value = round(float(raw_val), 2)
  except (ValueError, TypeError):
      continue  # Skip invalid record without failing batch
  ```
* Unexpected nulls or missing fields cause the single record to be skipped while continuing the rest of the dataset ingestion.

### 3.2 Error Isolation
* In multi-source agents (e.g. `AgricultureAgent` fetching from World Bank, Open-Meteo, and NASA POWER simultaneously), each fetcher runs in an isolated `try...except` block.
* If one remote API goes down or changes its schema, the remaining sources continue running and saving records.
* The main background scheduler loop (`app/services/scheduler.py`) isolates each sector agent attempt, guaranteeing that a failure in one agent never stops or crashes the backend server.

---

## 4. Anti-Deduplication & Storage Protection

To prevent database bloat and redundant record accumulation over time:

### 4.1 Unique Composite Index
The database schema enforces a strict composite unique constraint on every observation:
$$\text{UNIQUE}(\text{sector}, \text{indicator}, \text{reference\_date}, \text{region}, \text{source})$$

### 4.2 SQLite `ON CONFLICT` Upsert
In SQLite mode, records are ingested using:
```sql
INSERT INTO observations (...) VALUES (...)
ON CONFLICT(sector, indicator, reference_date, region, source) DO UPDATE SET
  value=excluded.value,
  unit=excluded.unit,
  source_url=excluded.source_url,
  collected_at=excluded.collected_at;
```
If an observation for the exact same date and indicator already exists, its value is updated cleanly without creating duplicate database rows.

### 4.3 In-Memory Supabase Deduplication
When writing to Supabase, `ObservationRepository._store_supabase_pipeline_batch` maintains a hash set `seen_rows` during payload construction to eliminate duplicate entries prior to batch insertion.

---

## 5. Scheduling & Update Frequency Alignment

Different data domains update at drastically different frequencies. The harvester schedule respects these cycles:

| Sector / Source | Source Update Frequency | Agent Collection Strategy |
|-----------------|-------------------------|---------------------------|
| **Agro-Meteorology** (Open-Meteo) | Daily | 24-Hour Automated Harvest |
| **Market Cereal Prices** (WFP / FAO) | Weekly / Monthly | 24-Hour Automated Harvest |
| **Macroeconomics** (BEAC / World Bank) | Monthly / Annual | Cached TTL (Skips redundant requests if data is <7 days old) |
| **Education & Literacy** (UNESCO / UNICEF) | Annual | Annual census sync with local fallback cache |
| **Transport Infrastructure** (OSM / HDX) | Monthly | Periodic 24h background sync |

---

## 6. Summary of Agent Files & Responsibilities

* [app/agents/base.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/base.py): Base class defining `fetch_json_with_retry`, `fetch_text_with_retry`, Data Science rules (3*IQR outliers, domain bounds), and normalization workflow.
* [app/agents/agriculture.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/agriculture.py): Agriculture, livestock & agro-meteorology agent.
* [app/agents/economy.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/economy.py): Macroeconomic, fiscal & debt metrics agent.
* [app/agents/education.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/education.py): School enrollment, literacy & gender parity agent.
* [app/agents/environment.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/environment.py): Weather, forest cover & NASA FIRMS active fire agent.
* [app/agents/markets.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/markets.py): Consumer prices, trade volume & food index agent.
* [app/agents/transport.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/transport.py): Road network, air departures & logistics quality agent.
* [app/agents/analysis.py](file:///c:/Users/Meroo/Documents/Codex/2026-08-15/je/outputs/FreeDatatd-MVP/app/agents/analysis.py): Cross-sector statistical correlation & AI insights generator.
