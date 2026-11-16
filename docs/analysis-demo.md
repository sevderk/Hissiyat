# Analysis dashboard and local research preview

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

## Local research preview

To show the Phase 5E section on the same localized home routes, set the
server-side opt-in before starting Next.js in development:

```powershell
$env:HISSIYAT_RESEARCH_PREVIEW = '1'
npm run dev
```

The findings render from the curated constants in
`frontend/src/lib/research-preview.ts`. They do not require the demo API.
The synthetic section continues to use its own endpoints and contracts.
The research preview defaults to off and is never rendered by a production
build, even if the opt-in is set. Keep the development server on loopback.
A separate publication review is required for any public presentation of
real-derived metrics.

Run `npm run test:research` to check the aggregate allowlist and caveats.
Against the opted-in local server, set
`FRONTEND_EXPECT_RESEARCH_PREVIEW=1` for `npm run test:routes`. For the
default or production server leave this test setting unset. Both modes
verify that the research and annotation URLs return 404.

## Local text analysis

From the repository root, install the optional pinned CPU packages into the
existing backend virtual environment. Run each server in its own PowerShell:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-analysis.txt
$env:HISSIYAT_ENVIRONMENT = 'development'
$env:HISSIYAT_LOCAL_TEXT_ANALYSIS = '1'
.\backend\.venv\Scripts\python.exe -B -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-proxy-headers
```

```powershell
Set-Location frontend
$env:HISSIYAT_LOCAL_TEXT_ANALYSIS = '1'
$env:HISSIYAT_RESEARCH_PREVIEW = '1' # Optional, independent of text analysis.
npm.cmd run dev
```

Open `http://127.0.0.1:3000/tr#local-text-analysis` (or replace `tr` with `en`).
Select either fictional collection or enter fictional or appropriately
de-identified English texts, one per line. Run with two or three groups.
The 12–100 text limit, 500-character limit per text, and 64 KiB JSON limit
apply to both examples and custom input. Only bounded in-memory CPU analysis
and aggregate output are used. A keyword needs at least three distinct
modeled texts in its group and must appear in the neutral disclosure vocabulary.
Keep both services on loopback, without a reverse proxy or remote exposure.
Use a single API worker. If port 8000 is occupied, select another loopback
backend port and set `HISSIYAT_LOCAL_ANALYSIS_PORT` in the frontend terminal.
To serve the synthetic demo from the same alternate backend, set
`HISSIYAT_DEMO_API_ORIGIN` to its loopback HTTP origin too.

For MiniLM and comparison mode, install `backend/requirements-minilm.txt`
and set `HISSIYAT_LOCAL_ANALYSIS_MODEL_DIR` in the backend terminal to the
absolute local directory outside the repository containing `model.onnx` and
`tokenizer.json` from the verified `all-MiniLM-L6-v2` revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Set
`TOKENIZERS_PARALLELISM=false` in that terminal to tokenize each small batch
without spawning a tokenizer worker pool. Restart the backend after changing
the model directory or assets. The first MiniLM request validates both files
and loads a CPU-only session. There is no model download or fallback. An
unavailable model produces a controlled message and the NMF selection stays
available.

MiniLM uses two inference threads, batches of eight, a 256-token limit and
K-means with seed 42 and 20 initializations. Its displayed terms summarize
recurring words in the assigned texts using TF-IDF after clustering. The
comparison runs both methods on the same submission and reports adjusted
Rand index over the texts assigned by both. Group numbers are arbitrary.
Topic validity and generalization require separate evaluation.

Run `npm.cmd run test:routes` with `FRONTEND_EXPECT_LOCAL_ANALYSIS=1` to
exercise both examples through the proxy. Also set `FRONTEND_EXPECT_MINILM=1`
when the verified model is configured. The backend unit tests cover
validation, output disclosure and concurrency with the optional CPU packages.
