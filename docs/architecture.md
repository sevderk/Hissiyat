# Architecture and conventions

## Current scope through Phase 1D

Hissiyat uses a modular monorepo with independently managed frontend and backend
dependencies. No monorepo orchestration tool or shared package is needed yet.

- Frontend: Next.js App Router, TypeScript, Tailwind CSS and next-intl.
- Backend: Python and FastAPI with a small versioned API package.
- Database: isolated local PostgreSQL 18.6 through Compose; SQLAlchemy Core and psycopg connectivity only.
- Future analysis: Python; models will be selected through experiments.
- Development: local Windows environment, 16 GB RAM; GPU availability unconfirmed.

The landing page is informational. It does not display simulated research
findings. `/api/v1/health` is process liveness; `/api/v1/health/ready` performs
an authenticated database connectivity check and returns 503 on failure.
The frontend does not call the backend at this stage.

## Backend boundaries

`app/core/config.py` reads environment configuration. `app/api/v1/` owns the first
API version; `app/main.py` creates the application and attaches the router.
`app/core/database.py` owns a small lazy connection pool. FastAPI lifespan creates
the pool without connecting and disposes it at shutdown. Sync readiness runs in
FastAPI's threadpool with bounded connection, statement and pool wait times.
There is no ORM session or model layer because this phase only needs SQLAlchemy
Core connections. Tests create isolated application instances. Add services, repositories or other
layers only when a concrete feature needs them.

No application schema, migration, ingestion connector, background job,
authentication flow, model pipeline or third-party API is included. An empty
`hissiyat_test` database is infrastructure for explicitly selected integration
tests. See `database-development.md` for the Compose and configuration contract.

`app/contracts/` adds Pydantic input validation only. It has no database or API
integration and does not perform collection, normalization, language detection or
analysis. Text inputs and trend observations have separate models. Nested policy
and collection metadata provide input-level provenance without database foreign
keys. See `data-contracts.md` for required metadata and validation boundaries.

## Localization

`src/i18n/routing.ts` is the locale configuration. Turkish (`tr`) is the default;
English (`en`) is also supported. Locale prefixes are always explicit. `/`
redirects to `/tr`; browser detection and locale cookies are disabled. The
language switcher preserves the current pathname and uses next-intl navigation.
Only the home page is a content route in this phase.

Messages, metadata, navigation labels and localized missing-page content live in
`messages/tr.json` and `messages/en.json`. Locale dictionaries must have matching
keys and actual translations. Native language names remain stable in both
dictionaries. Adding a language requires a dictionary, routing configuration and
verification updates. `src/proxy.ts` uses the Next.js 16 proxy convention.

UI locale is independent of source language and future NLP model support. No
translation service or automatic source-text translation is introduced.

## Engineering and research conventions

Use English for code identifiers, comments, filenames, technical documentation,
API paths and future commit messages. Use descriptive names and keep components
small. Communicate project-owner implementation reports in Turkish.

The platform remains domain-independent. The approved initial pilot concerns
education, career expectations and future uncertainty in English text. Turkish
text has a parallel feasibility track; additional languages remain possible.
Stack Exchange, official Google Trends CSV exports and Turkish Bluesky text are
candidate sources, without final permission for collection or analysis.

Keep observed source data, normalized data, calculated statistics, model
inferences, human annotations and interpretations distinct. Do not present
correlation as causation or online samples as whole populations. Future features
need provenance, uncertainty, human review and separate model-performance and
construct-validity evaluation. A second independent evaluator is expected but
unconfirmed; future evaluation must support multiple evaluators without claiming
that independent annotations already exist. No annotation model is implemented.

## Local security and generated files

Servers bind to loopback by default. Environment files, dependencies, caches,
datasets, model artifacts, local logs and root reference PDFs are ignored by Git.
The original proposal remains unchanged; its personal information is not copied
into application code or UI. Ignore rules are not a substitute for reviewing
files before a future commit or publication.

No public deployment, user data or production security configuration is provided.
Stop after Phase 1D until the project owner approves the next task.
