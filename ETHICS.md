# FreeData.td Data Ethics Charter

> *"Responsible open data for a better-understood Chad."*

## Principle 1 — Data Sovereignty & Openness

FreeData.td only collects and aggregates data that is already publicly released under open licenses by recognized national and international institutions.

- No private or personally identifiable information (PII) is collected or published.
- Every dataset and observation explicitly documents its upstream source and license.
- Data is never sold or monetized; public read access remains free and keyless.

## Principle 2 — Full Transparency & Provenance

Every published dataset and observation carries complete provenance metadata:

- Original upstream organization and API/portal URL
- Reference date and collection timestamp
- Validation, normalization, and quality rules applied
- Completeness and freshness indicators
- Known limitations and supervisor review notes
- Applicable open license (`CC BY 4.0`, `INSEED Open Licence Agreement`, etc.)

## Principle 3 — Do No Harm

FreeData.td commits to never publishing data that could stigmatize communities, regions, or social groups:

- No data is disaggregated by ethnicity or religion.
- Sensitive socioeconomic indicators are accompanied by historical and methodological context.
- Out-of-domain or anomalous values are held in quarantine (`table_quarantine`) for human supervisor review prior to publication.
- Phone numbers on the WhatsApp assistant channel are never stored in plain text (only an irreversible salted HMAC hash truncated to 16 hex characters is used for daily rate limiting).

## Principle 4 — Fair & Balanced Representation

Chad is not defined solely by crises. FreeData.td presents socioeconomic indicators in their full complexity — reflecting structural challenges alongside positive regional dynamics and development potential.

- Difficult indicators are contextualized with long-term historical series.
- Visualizations and analytical summaries remain objective, reproducible, and grounded in verified measurements.

## Principle 5 — Sustainability & Open Source

FreeData.td is engineered to be maintainable, auditable, and long-lived:

- Fully documented source code and SQL schemas
- Open contribution workflow with automated CI, security scanning, and end-to-end browser tests
- **MIT License** for the software codebase — any developer or institution can inspect, audit, or extend the platform

## Principle 6 — Attribution

- Users of the platform are asked to cite **FreeData.td** and the original upstream data providers in their research, reports, or applications.
- FreeData.td systematically attributes every observation to its original source organization.
- Ownership of upstream statistics remains with their respective producing institutions.

## What FreeData.td Will Never Do

- Collect personal data without consent or store plain-text phone numbers
- Sell data or restrict public read access behind paywalls
- Publish data disaggregated by ethnicity or religion
- Allow the platform to be used for individual surveillance
- Alter source values without recording an explicit audit trail and public note

## Citation Format

```text
Kadergueli, O. M. (2026). FreeData.td: An Open AI-Powered Socioeconomic Data
Infrastructure for Chad. GitHub.
https://github.com/Kadergueli/FreeData.td — CC BY 4.0
```
