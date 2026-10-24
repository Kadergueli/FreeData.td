Third-party scripts served from our own origin (no CDN: lets the Content-Security-Policy
allow only `'self'` scripts and removes a supply-chain dependency).

| File | Package | Version | Source |
|---|---|---|---|
| lucide-0.469.0.min.js | lucide | 0.469.0 | `npm pack lucide@0.469.0` -> dist/umd/lucide.min.js |
| chart-4.4.7.umd.js | chart.js | 4.4.7 | `npm pack chart.js@4.4.7` -> dist/chart.umd.js |

To upgrade, repeat the `npm pack`, copy the file under its new versioned name and update
index.html / js/charts.js.
