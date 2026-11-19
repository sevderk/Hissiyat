# Local evidence-grounded research interpretation

## Architecture and scope

The development topic/event workspace can request a local model interpretation
of a completed backend result. `build_evidence` creates a versioned aggregate
package with an opaque ID, exact query/filter scope, date unit, geography,
counts, denominators, units, methods, source references and missing-evidence
facts. Observations, exploratory outputs and insufficiency have separate kinds.
Discussion counts refer to documents. Search summaries retain period units and
ambiguous-zero, missing and suppressed categories.

Only the latest package is held in backend memory. A completed research run
replaces it and shutdown removes it. The endpoint accepts its ID and output
language. Clients cannot submit replacement statistics, model URLs or source
text. An unavailable/replaced ID gets `evidence_expired`. Source authorization
and NLP permission checks run before evidence creation. Interpretation uses the
completed package without source retrieval.
An in-flight generation retains its original package until completion; its
response stays bound to that ID even if another research run replaces the cache.

The current pathway covers completed server-side topic/event research and
documented official API summaries. Unverified API measurement/display semantics
produce insufficient evidence. Browser-only Explore CSV imports retain their
existing view and need server-side provenance integration for this pathway.
The curated Phase 9C comparison retains its existing aggregate view.

## Approved local model

- Official `Qwen/Qwen3-1.7B-GGUF`, revision
  `90862c4b9d2787eaed51d12237eafdfe7c5f6077`, Q8_0, 1,834,426,016 bytes.
  SHA-256 `061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a`.
  The [model card](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF) identifies Apache 2.0.
- Portable Windows CPU llama.cpp `b12359`, 25,097,509-byte archive.
  SHA-256 `837c1655e87df3b66989f4be33a792a1399c785bf259038dc75c900096683e69`.
  Runtime build 12359 / `b1b770d90` uses the
  [MIT license](https://github.com/ggml-org/llama.cpp/blob/b12359/LICENSE).

The owner approved both artifacts outside Git before download. The completed
files were reused after interruption and both digests verified again. No second
model download was required. The CPU runtime uses four threads, one slot, an
8,192-token context, offline mode, disabled logging and disabled web UI on
`127.0.0.1`. No system PATH or startup setting changes. The observed model
process working set on the owner's 16 GB / Ryzen 7 5800H machine was about 2.9–3.5 GB.
The starter disables reasoning and uses the built-in ChatML template without
the Jinja/native PEG chat parser. This avoids the observed native parser failure.
A small conflicting-instruction probe verified that schema constraints actually
apply. The pure-content parser was rejected during development because it
ignored those constraints. Application-side JSON/claim validation remains enabled.

## Owner operation

Run these commands from the repository root in separate PowerShell terminals.

```powershell
# Terminal 1 verifies existing files and starts the model without downloading.
.\scripts\start-local-ai.ps1
```

```powershell
# Terminal 2 uses the existing backend environment.
Set-Location backend
$env:HISSIYAT_ENVIRONMENT = 'development'
$env:HISSIYAT_LOCAL_RESEARCH = '1'
$env:HISSIYAT_LOCAL_INTERPRETATION = '1'
$env:HISSIYAT_LOCAL_INTERPRETATION_PORT = '8091'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
```

```powershell
# Terminal 3 can match another backend port using HISSIYAT_LOCAL_RESEARCH_PORT.
$env:HISSIYAT_LOCAL_RESEARCH = '1'
npm.cmd --prefix frontend run dev
```

Open `/tr` or `/en`, load the existing fictional discussion example, run the
research and select **AI Research Interpretation**. The interface sends only
the evidence ID and language through its same-origin proxy. Backend port 8000
and model port 8091 are separate. Docker and PostgreSQL are unnecessary.
Production disables the local interpretation route and controls.

## Generation and checks

`local_interpretation.GENERATION_PROMPTS` contains the auditable bilingual prompts. The adapter calls
only `/v1/chat/completions` on the configured loopback port, with proxies and
redirects disabled. Input contains selected computed aggregates. Raw posts,
comments, sentences, API observations, credentials and private review records
are excluded. The model has no tool interface. Logging, response streaming and
persistent prompt caching are disabled. The alias must be `hissiyat-qwen3-1.7b`.

Generation uses a JSON-schema prose draft and application-bound scope/language/status/references,
non-thinking mode, temperature 0.3, seed 42 and a 1,000-token output cap.
The prompt requests short sentences. Grammar patterns cap prose length, constrain
its Latin-script characters, require exploratory prefixes and a question mark;
independent backend checks still reject invalid lengths/language and known copied
instruction placeholders. Pattern length bounds are explicit because the runtime
did not combine a string's `maxLength` with its custom pattern during acceptance.
The built-in ChatML request explicitly prefills Qwen's closed thinking block;
its Jinja-only `enable_thinking` argument alone is ineffective in this mode.
The model writes an overview, exactly the selected number of findings, one
uncertainty and one question. The application binds each to its original fact
ID/kind and the original scope. The model cannot substitute metadata or IDs. Validated
sentences are preserved. Localized numeric observations in the evidence
catalogue come from application data and have a separate label.

The model sees a declared selection to fit the small CPU model: sample counts, the largest
document-level expression match category (stable input-order tie breaking), the
first topic method and the missing-metadata category. Query strings are excluded.
Expression labels have fixed bilingual glosses; the catalogue retains versioned
rule references and complete topic keyword lists. Keyword lists are omitted from
the short prose prompt to avoid incomplete enumerations. A different fictional
Turkish sample illustrates sentence style; its counts cannot satisfy the current
sample's numeric checks. The full catalogue,
including other expression categories, topic methods and ARI, stays available
to the user and validator. The generated prose is a selective explanation,
not an exhaustive account or an independent comparison of methods.
The short discussion uncertainty/question uses the missing-context fact;
search interpretation uses its measurement-limit fact. Other limitations stay
visible in the complete catalogue.

Every substantive field cites an existing fact. Scope, denominator, country,
period, language, identity and framing are checked against the server-held
package. Numerical tokens must occur in the cited fact or denominator. Dates
must match that fact. Invented counts, source counts derived from document
counts, unsupported percentages and known causal/population/superiority claims
are withheld. Topic prose requires an uncertainty qualifier. Oversized,
truncated or malformed output, wrong aliases and tool calls are rejected.
An insufficient package permits metadata findings, without exploratory findings.
Recognized English fractions and Turkish document fractions check numerator and
denominator order, including reversals with otherwise valid numbers. Truncated
unbalanced quotations and document counts mislabeled as sample counts are rejected.
Failures use fixed sanitized messages. There is no automatic retry or template
fallback. The existing busy flag serializes local analysis work. Generation has
a 150-second timeout, with longer proxy/browser limits for controlled failures.

## Limits

Numeric vocabulary checks cannot prove every grammatical relationship or
interpretation. Lexical language/inference filters cover selected cases and can
withhold valid wording or miss semantic errors. The local service and host
processes are trusted. The alias provides a protocol check, without per-response
cryptographic attestation. Source-text and query injection are excluded from model
input through aggregate construction, while output
checks constrain known failures. These controls provide no guarantee that all
hallucinations or prompt injection are eliminated.

Topic partitions and expression rules retain their thematic and psychological
limitations. Date coverage alone cannot establish a temporal comparison.
Search-interest summaries support no emotion, opinion, causal or absolute-count
inference. Model explanations retain these boundaries.

## Verification

Backend unit tests use fictional/mocked material. Frontend contracts check scope,
citations and privacy projections. `frontend/scripts/verify-local-ai.mjs` is an
explicit real-model acceptance test against the running local services. It uses
a fictional Turkish topic sample and a small English event sample, checks
citations and insufficiency, and creates an isolated Chrome profile with
non-loopback DNS blocked. It retrieves no dataset and invokes no provider.

```powershell
Set-Location frontend
$env:FRONTEND_BASE_URL = 'http://127.0.0.1:3084'
# Optional when a separate local production build is running.
$env:FRONTEND_PRODUCTION_URL = 'http://127.0.0.1:3085'
node scripts/verify-local-ai.mjs
```

### Executed acceptance (2026-11-19)

- Backend: `python -m pytest -q` — 482 passed, 90 PostgreSQL integration tests
  deselected. One existing Starlette/httpx deprecation warning. `compileall`
  and `pip check` succeeded. PostgreSQL and Docker were not started.
- Frontend: `node --test scripts/*.test.mjs` — 43 passed; ESLint, TypeScript
  and the Next.js 16.4.6 production build succeeded. Next.js warned about an
  unrelated lockfile outside the repository.
- Existing bilingual route checks passed in development and production,
  including offline MiniLM/NMF comparison, request limits and production gates.
- Real Qwen generation through the browser: Turkish topic / 16 fictional
  documents, exploratory, 21 seconds; English event / 2 fictional documents,
  insufficient, 12 seconds. Both displayed model-generated prose with valid
  references. The English overview explicitly declined thematic conclusions.
  The Turkish result described 11 matched documents and two groups of 8,
  without asserting validated themes. No deterministic response substituted for
  model generation.
- Isolated Chrome checked Turkish at 430 px and English at 1,365 px, evidence
  anchors, no horizontal overflow, production route/UI restrictions and
  loopback-only browser requests. The test backend also blocked non-loopback
  socket connections and had no configured source approvals or API credentials.
- Development failures were withheld, including native-parser errors, copied
  placeholders, wrong language/script, invalid lengths and unsupported claims.
  Earlier broad numeric-token checks missed a reversed fraction; explicit
  numerator/denominator regression checks now cover that known pattern. These
  tests do not establish a universal semantic validation guarantee.

No real research experiment or authenticated source request was repeated.
Model artifacts remain outside Git. The two existing untracked thesis
documents retained their original SHA-256 digests and were excluded from the commit.
