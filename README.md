# FreeDatatd

FreeDatatd is an open data infrastructure for Chad. This MVP collects, validates, stores and exposes socioeconomic observations, beginning with agriculture.

## What works now

- Agriculture collection pipeline with a safe demo dataset and a World Bank adapter.
- Validation, deduplication and provenance fields for every observation.
- Supabase storage when credentials are configured; SQLite fallback for local development.
- FastAPI endpoints for catalogue, filtering and CSV/JSON exports.
- Lightweight dashboard served by the API.

## Quick start

```powershell
cd freedatatd
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.cli collect-agriculture --demo
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` for the dashboard and `http://127.0.0.1:8000/docs` for the API documentation.

## Connect Supabase

1. Create a Supabase project.
2. Your existing `table_raw`, `table_clean`, `table_public`, `table_logs` and `table_rapports` schema is supported directly. Run `supabase/post_setup.sql` once to add performance indexes and activate RLS.
3. Add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` to `.env`.
4. Restart the API and run the collection command again. Data will follow `table_raw → table_clean → table_public`; validation summaries and transformation traces are added to `table_rapports` and `table_logs`.

Never expose the service-role key in the browser or commit `.env`.

## Main commands

```powershell
python -m app.cli collect-agriculture --demo
python -m app.cli collect-agriculture --source world-bank
python -m app.cli export --sector agriculture --format csv
pytest
```

## Project layout

```text
app/agents/       Collection agents and shared pipeline
app/services/     Storage and export services
app/main.py       FastAPI application
supabase/         Cloud database schema and row-level security
tests/            Automated tests
```

The next production steps are adding FAOSTAT and WFP adapters, scheduled runs through GitHub Actions, and authentication/usage limits for public downloads.

## LLM studies with Groq

Add `GROQ_API_KEY` and a long random `ANALYSIS_API_KEY` to `.env`, run `supabase/studies.sql` once, then send a `POST` request to `/api/v1/studies?sector=agriculture` with an `X-Analysis-Key` header. The dashboard asks for this access key but never saves it. The endpoint is limited to five requests per hour per IP by default.
