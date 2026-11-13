# Phase 4A synthetic analysis dashboard

The localized home routes `/tr` and `/en` display fixed fictional aggregates.
Run both applications on loopback. From `frontend`, start FastAPI in one
PowerShell terminal and Next.js in another.

```powershell
$env:HISSIYAT_ENVIRONMENT = 'development'
& ..\backend\.venv\Scripts\python.exe -B -m uvicorn app.main:app --app-dir ..\backend --host 127.0.0.1 --port 8000
```

```powershell
npm run dev
```

Open `http://127.0.0.1:3000/tr` or `/en`. To use another backend port, set
`HISSIYAT_DEMO_API_ORIGIN` in the frontend terminal before starting Next.js.
The default is `http://127.0.0.1:8000`. The proxy accepts only HTTP loopback
origins and two named demo routes. It validates the upstream payload and
rejects unexpected fields before replying. Both requests use the frontend
origin, so the browser needs no cross-origin access. The FastAPI routes
are registered in development and test. They use no database connections
and need no database settings or API credentials.

| FastAPI route | Contract 1.0 |
| --- | --- |
| `GET /api/v1/demo/text-analysis?cohort=general` | 240 fictional documents, four category groups and document counts per label. |
| `GET /api/v1/demo/text-analysis?cohort=uncertainty-enriched` | 126 fictional documents with different group counts and its own denominator. |
| `GET /api/v1/demo/search-interest` | 12 fictional Monday intervals, an explicit 0–100 relative scale, and distinct `missing` and `suppressed` states with `null` values. |

Each contract declares the demo flag, version, source category, fictional
provenance, method and limitations. Label counts are bounded by the selected
cohort's document total. Labels overlap and emotions represent explicit
fictional expressions. The enriched cohort describes its own selection.
The time series uses a fictional query and geography, with visible gaps
and an accessible list of weekly values. Text cohort changes affect only
the text request. Keep cross-source interpretation and any research claims
out of the demo. Its fixtures contain aggregate counts and index values only.

A failed request offers a localized retry. An invalid contract displays a
separate error and an empty result displays an explicit empty state. The
synthetic notice stays visible throughout.

Run `npm run lint`, `npm run typecheck`, `npm run test:demo`, and `npm run build`
from `frontend`. With Next.js running, `npm run test:routes` checks locale
routes, message parity and the initial dashboard shell. The demo API tests
are in `backend/tests/unit/test_demo.py`.
