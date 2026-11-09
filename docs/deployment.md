# Deployment Guide (Render + Supabase + GitHub Actions)

## 1. Render Environment Variables

| Variable | Value | Purpose |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Your project credentials | Production database storage (server-only) |
| `READ_RATE_LIMIT_PER_MINUTE`, `EXPORT_RATE_LIMIT_PER_MINUTE` | `120` / `10` (default) | Per-IP rate limits for the public read & export API |
| `COLLECTION_API_KEY` | Long random secret (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) | Protects `/api/v1/collection/*` trigger endpoints |
| `GROQ_API_KEY` | Your Groq API key | AI study generation (falls back to deterministic statistical reports if unset) |
| `ALLOWED_ORIGINS` | Your public site URL | CORS allowlist |
| **`FORWARDED_ALLOW_IPS`** | **`*`** | **Required on Render so Uvicorn reads the real visitor IP instead of Render's proxy IP for per-IP rate limiting** |
| `MALLOC_ARENA_MAX` | `2` | Caps glibc thread arena memory fragmentation on 512 MB instances |
| `SUPABASE_ANON_KEY` | Project "anon / publishable" key (Project Settings > API) | Enables browser sign-in to `#/admin` (public by design) |
| `ADMIN_EMAILS` | Comma-separated owner emails | Permanent owners of the `#/admin` portal |
| `KEEP_ALIVE_URL` | Optional (`RENDER_EXTERNAL_URL` is auto-detected on Render) | Public URL pinged every 14 minutes to prevent Render free-tier idle sleep |
| `KEEP_ALIVE_INTERVAL_MINUTES` | `14` (default) | Self-ping interval (below Render's 15-minute idle threshold) |

---

## 2. Automated Daily Harvesting (All 11 Sectors)

The workflow `.github/workflows/scheduled_harvest.yml` runs daily: it wakes the service, triggers collection for sectors that are due (each sector follows its own daily, weekly, or monthly cadence defined in `app/services/cadence.py`), and polls until completion. Passing `?force=true` to `run-scheduled-harvest` forces collection across all sectors.

Configure two secrets in GitHub (*Settings > Secrets and variables > Actions*):
- `APP_URL`: Your Render service URL without a trailing `/`
- `COLLECTION_API_KEY`: The exact same secret configured on Render

Manual trigger: *Actions > "Daily harvest (sectors that are due)" > Run workflow*.

---

## 3. 24/7 Keep-Alive (Preventing Render Cold Starts) & CDN Caching (Cloudflare)

1. **Preventing Cold Starts Every 14 Minutes (`app/services/scheduler.py` & `.github/workflows/keep_warm.yml`)**:
   - On Render's free tier (750 hours/month included, which exceeds a full 31-day month = 744 hours), a container spins down after **15 minutes** of inactivity (causing 30–50s cold starts and Meta WhatsApp webhook timeouts).
   - **Layer 1 (In-process backend self-ping)**: On startup, `app/services/scheduler.py` launches `_keep_alive_loop`, sending `GET /api/v1/health` every **14 minutes** to the public Render URL (`RENDER_EXTERNAL_URL`, automatically injected by Render, or `KEEP_ALIVE_URL`).
   - **Layer 2 (GitHub Actions 24/7 cron)**: `.github/workflows/keep_warm.yml` pings `GET /api/v1/health` every **14 minutes 24/7** (`*/14 * * * *`) using the `APP_URL` secret.
   - **Layer 3 (Recommended external monitor)**: For second-level precision, add a free **cron-job.org** or **UptimeRobot** HTTP monitor set to **14 minutes** targeting `https://<your-site>/api/v1/health`.

2. **Upstream CDN Caching (Cloudflare)**:
   - Public read endpoints (`/api/v1/observations`, `/api/v1/stats`, `/api/v1/catalog`, `/api/v1/catalog.jsonld`, `/api/v1/catalog.dcat.json`, `/api/v1/regions`, `/api/v1/crops`, `/api/v1/sources/freshness`, `/api/v1/export/*`, `/sitemap.xml`) emit `Cache-Control: public, max-age=3600` (1 hour), whereas `/api/v1/health` and `/api/v1/collection/scheduler-status` emit `Cache-Control: no-store`.
   - Placing your domain behind **Cloudflare** (Proxy enabled + Cache Rule *"Respect Origin Cache-Control"* for `/api/v1/*` and `/sitemap.xml`) offloads 80–90% of read and export traffic from Render's 512 MB RAM and bandwidth limits.

---

## 4. SEO Discoverability & Open Data Harvesting (Google Dataset Search, HDX, OpenDataSoft)

- **`/sitemap.xml` & `/robots.txt`**: List the portal, documentation, and dataset feeds for all **11 sectors**.
- **`/api/v1/catalog.jsonld`**: Full **schema.org/DataCatalog & Dataset** (JSON-LD) feed for Google Dataset Search.
- **`/api/v1/catalog.dcat.json`**: Full **DCAT-AP** (JSON-LD) catalog for automated harvesting by HDX, OpenDataSoft, and CKAN.
- **Static Microdata (`index.html`)**: Includes `schema.org/DataCatalog` microdata and a `<noscript>` block with direct CSV/Parquet links for crawlers that do not execute JavaScript.

---

## 5. Crop Suitability Reference Files (`app/crops/`)

The `/api/v1/crops` and `/api/v1/crops/suitability` endpoints read three versioned JSON files in `app/crops/` (zero external network calls during user requests):
- `app/crops/requirements.json`: Verified FAO EcoCrop agronomic thresholds per crop.
- `app/crops/soils.json`: Weighted 0–30 cm soil pH, clay, sand, and organic carbon (SoilGrids 2.0) across Chad's 23 regions, regenerable via `python app/crops/soils_chad.py`.
- `app/crops/climate.json`: Monthly mean rainfall and temperature (NASA POWER) across Chad's 23 regions, regenerable via `python app/crops/climate_chad.py`.

---

## 6. Administrator Portal (`#/admin`)

1. Supabase: Run `supabase/admin_setup.sql` (creates `table_admins` and `table_admin_audit`).
2. Supabase > Authentication > Users > *Add user*: Create your admin account (email + strong password) and check *"Auto Confirm User"*. **Disable public sign-ups** (*Authentication > Sign In / Providers > disable "Allow new users to sign up"*).
3. Render: Set `SUPABASE_ANON_KEY` and `ADMIN_EMAILS`.
4. Open `https://<your-site>/#/admin` directly in your browser (or press `Ctrl + Shift + A` from any page; no link is shown on the public footer) and sign in.

Even with a valid Supabase session, any account not listed in `ADMIN_EMAILS` or `table_admins` is rejected (`403 Forbidden`). Every login and administrative action is recorded in `table_admin_audit`.

---

## 7. Harvest History, Quarantine & Data Governance (`#/admin`)

- **Harvest Runs (`#/admin` > Collections)**: Run `supabase/harvest_runs_setup.sql` once (`table_harvest_runs`). Records start/end timestamps, trigger source, sectors, status (`completed`, `partial`, `failed`, `interrupted`), and error details.
- **Quality Quarantine (`#/admin` > Quality)**: Run `supabase/quarantine_setup.sql` once (`table_quarantine`). Observations flagged `SUPERVISOR_REVIEW` (out-of-domain values or statistical outliers) wait in quarantine until an administrator approves, corrects, or rejects them.
- **Published Data, AI Reports & Team (`#/admin` > Data / AI Reports / Team)**: Run `supabase/data_admin_setup.sql` once (`table_deleted_observations`). Allows audited corrections, reversible deletions with mandatory reasons, AI study moderation, and administrator team management (reserved to permanent owners in `ADMIN_EMAILS`).

---

## 8. INSEED Statistics (Offline PC Import Workflow)

The `chad.opendataforafrica.org` portal serves national indicators via an SDMX API behind a Cloudflare bot challenge, which automated servers never bypass. Administrators can download and import INSEED flows from their local workstation:

```powershell
pip install -r requirements.txt
python -m app.cli probe-inseed     # Downloads and saves data/raw/inseed_<flow>.xml
python -m app.cli import-inseed    # Validates and ingests them into the database
```

---

## 9. Supabase Aggregations (`supabase/aggregates_setup.sql`)

Supabase caps standard `SELECT` queries at 1,000 rows per page. Run `supabase/aggregates_setup.sql` once in the Supabase SQL Editor so region lists and catalog counts are computed server-side across the full table.

---

## 10. WhatsApp Assistant (Meta Cloud API)

The conversational assistant (market prices + regional weather) answers on WhatsApp. The channel stays **off** (`503`) until all required variables are set:

1. Supabase: Run `supabase/assistant_log_setup.sql`.
2. Meta (`developers.facebook.com`): Create a Business app and add the **WhatsApp** product.
3. Render: Configure the following variables:

| Variable | Value |
|---|---|
| `WHATSAPP_VERIFY_TOKEN` | Arbitrary secret string used during webhook registration |
| `WHATSAPP_APP_SECRET` | Meta > App Settings > Basic > *App Secret* (used to verify `X-Hub-Signature-256`) |
| `WHATSAPP_ACCESS_TOKEN` | Permanent system-user token |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp > API Setup > *Phone number ID* |
| `WHATSAPP_HASH_SALT` | Long random secret used to hash phone numbers (never change once set) |
| `WHATSAPP_DAILY_LIMIT` | Max answered questions per number per 24h (`30` by default) |

4. Meta > WhatsApp > Configuration > Webhook: Set callback URL to `https://<your-site>/api/v1/whatsapp/webhook`, verify token to `WHATSAPP_VERIFY_TOKEN`, and subscribe to **`messages`**.

---

## 11. WFP Market Prices (HDX HAPI)

1. Generate a free App Identifier at `https://hapi.humdata.org/docs` (*Generate App Identifier*).
2. Set `HDX_APP_IDENTIFIER` in your Render environment variables.
3. Trigger a harvest of the `markets` sector.
