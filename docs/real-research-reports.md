# Real aggregate research reports

## Scope and owner operation

Start the existing local Qwen runtime, backend and development frontend using
[the Phase 10A instructions](local-research-interpretation.md#owner-operation).
No database, source API key or new model download is needed for these paths.

In the main Turkish/English workspace:

1. Select Explore CSV, paste its source Explore URL, select the existing file,
   confirm the same-chart scope and import it. Inspect the existing chart and
   then select **Generate local AI interpretation** for the relevant region.
2. Alternatively, open either historical wages or job-opportunities comparison
   and use its separate AI interpretation action. No source comments are loaded.
3. Read the evidence catalogue alongside the generated observations, limitations
   and research question. Generation failure leaves the evidence available.

The model's last successful generation is distinguished from unknown availability.
Startup failures, invalid evidence, unsupported claims and timeouts have fixed
Turkish/English messages. Generation never silently substitutes a template or retries.

## CSV evidence and trust boundary

The browser first uses the existing bilingual CSV parser and chart. Selecting
AI generation sends only the selected file and its scope to the loopback Next
server. This bounded upload is needed to revalidate the file rather than trust
browser-supplied statistics. The server reuses the same parser, calculates the
file digest and recomputes aggregates. It never fetches the Explore URL.

Only those aggregates reach FastAPI `/api/v1/local/evidence`: observed coverage,
missing/suppressed/ambiguous-zero counts, extrema and ties, first/last observations
and their difference. Python validates types, source URL, scope, ranges and
aggregate consistency. It trusts the first-party local Next parser to calculate
those aggregates; it does not independently reconstruct them from observations.
Arbitrary local programs with control over the trusted host are outside this
boundary. Browser callers cannot replace statistics through the Next endpoint.

Raw CSV bytes and complete series are not forwarded to the model or returned
by the evidence endpoint. The browser already holds its selected chart data.
The application adds no file, database record or raw-response log. Existing files
are neither copied into Git nor modified.

Source attribution is **user supplied**. A SHA-256 identifies uploaded bytes;
it does not cryptographically establish Google as their origin. Query, requested
period, region and recognized headers must agree. Supported AI regions currently
are TR, US, GB and worldwide; existing CSV chart support for other regions remains.
Each region gets its own report. The existing 256 KiB / 2,000-row parser limits
apply; the JSON upload is separately bounded to account for base64 encoding.

Explore values are request-relative 0–100 indices. Endpoint changes are **index
points**, not percentages or absolute search counts. Zero does not establish
zero searches. Blank and `<1` cells remain distinct missing/suppressed categories.
The first/last observed bucket is distinguished from the requested date window.
These values are not assigned the official Research API's separate, unresolved scale.

## Historical evidence

The backend reads only the already committed
`frontend/src/lib/civil-comparison-data.json`. Its LF-normalized SHA-256 is pinned
in `imported_evidence.py`; unexpected changes stop preparation. The endpoint
accepts a fixed question identifier, never a path or client-provided historical counts.
No archive retrieval, original comment reconstruction or NLP experiment occurs.

The recorded scope is English, 2015–2017, from the previously verified Civil
Comments/Jigsaw split under CC0 1.0. Geographic attribution and article context
remain unavailable. Archive screening, query filtering and the article cap
limit coverage. This is not current public opinion.

The catalogue retains both policy denominators, selection overlap/turnover,
long-document coverage, expression counts, paired-subset counts, ARI and
silhouettes. Independent thematic validity is not established. Unpaired count
changes do not establish better rule accuracy or changes in emotions. Zero
rule matches do not establish absence of expressions.

## Generation and claim validation

The existing local Qwen adapter produces actual structured prose. CSV reports
explain observed extrema and endpoint change. Historical reports explain coverage,
updated-sample wording matches and clustering limitations. Named historical
fields bind each sentence to the correct evidence fact regardless of JSON order.
Scope and references are attached by the application, not invented by the model.
The full catalogue remains visible separately from the short selected explanation.

Raw source text, queries, source URLs, credentials and full CSV observations
are excluded from the model prompt. Fixed fictional style examples illustrate
format and language; they are not fallback responses. The returned model prose
is checked against the current package, including numerical vocabulary, recognized
numerator/denominator relationships, index units, dates and known unsupported
inferences. Unsupported historical prevalence claims and invented reasons for
missing thematic validation are withheld.

These are conservative checks, not a proof of every semantic relationship.
Human scrutiny is still needed. Correct numbers can be combined misleadingly;
unsupported wording can escape lexical filters and valid wording can be withheld.
Model claims never establish causal effects, psychological states or population opinions.

Search-interest and text-expression reports stay separate. Their topic definitions,
years and geographic scopes do not justify a combined synthesis in this phase.
The official Research API's authorization and display gates are unchanged.
Both preparation and interpretation are development-only, loopback-only,
same-origin/no-store paths. Production returns 404.

## Acceptance

The owner explicitly authorized reading only the two named existing CSV paths.
They had identical byte digests. The original file was selected through the
browser; no dataset or model was downloaded and no source API was called.

Executed real Qwen/CPU generation before interruption:

| Input | Language | Approximate time | Verified observations |
| --- | --- | --- | --- |
| Owner's real Explore CSV | Turkish | 25 s | 61 daily periods, peak 100, trough 48, endpoint difference +13 index points |
| Historical wages | English | 23 s | 65/100 policy samples; 35 shared; 2 matched updated documents; ARI -0.002; thematic validity unverified |
| Historical job opportunities | English | 24 s | 42/76 policy samples; 42 shared; 1 matched updated document; ARI 0.3582; thematic validity unverified |
| Fictional two-document sample | English | 13 s | Explicit insufficient-evidence abstention |

After resumption the pending Turkish historical/mobile case passed with real
Qwen in 42 s. It reported the 65/100 samples, 35 shared documents, 2 updated
matches and ARI -0.002, and stated that thematic validity lacks independent
assessment. Long method identifiers now wrap inside the 430 px evidence catalogue.
English acceptance used a 1,365 px viewport. Evidence anchors, scope bindings,
missing translations and loopback-only browser requests were checked.

Earlier unsupported/reordered/truncated model claims were withheld; named
historical fields and compact prompts corrected the observed failures. Successful
real-source cases were not replaced by fictional data or rerun after interruption.

Final checks after resumption:

- Backend: 501 tests passed; 90 PostgreSQL integration tests deliberately not run.
  Python compilation and dependency checks passed. One existing Starlette/httpx
  deprecation warning remained.
- Frontend: 46 tests passed; ESLint, TypeScript and production build passed.
  Next.js reported the existing unrelated lockfile outside the repository.
- Development and production Turkish/English route regressions passed. Live
  loopback HTTP checks rejected malformed JSON, injected historical statistics,
  combined sources, cross-origin calls, query parameters and oversized bodies.
- With the actual model stopped, both browser languages showed the sanitized
  unavailable-model message, retained their evidence catalogue and produced no
  substitute AI report. Production preparation/interpretation endpoints returned
  404 even with local feature flags set; production controls remained disabled.
- No Google Trends API, Reddit, X, dataset download or external LLM request was
  made. No Docker/PostgreSQL service was started. The previous experiment and
  the two untracked thesis documents were preserved.
