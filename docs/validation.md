# Phase 1A validation

Date: 2026-10-17. Platform: Windows, Node.js 24.4.1, Python 3.12.9.

## Executed checks

| Check | Result |
| --- | --- |
| Workspace, proposal and existing-code inspection | Only the original proposal existed before initialization |
| Frontend dependency installation | `npm install`, followed by clean `npm ci`, completed |
| Complete dependency tree | `npm ls --all` reports no dependency problems |
| TypeScript | `npm run typecheck` passed |
| ESLint | `npm run lint` passed without lint warnings |
| Production build | `npm run build` passed; `/tr` and `/en` prerendered |
| Locale HTTP smoke test | `npm run test:routes` passed against the production server |
| Backend lock consistency | `pip install --no-index -r requirements.lock.txt` completed against installed packages |
| Python dependency integrity | `python -m pip check`: no broken requirements |
| Backend import | `from app.main import app` succeeded |
| pytest | 3 passed, 1 upstream deprecation warning |
| Real backend HTTP request | `/api/v1/health` returned `{"status":"ok"}` |
| Browser language switch | Turkish page changed to actual English content via the English link |
| Production npm security audit | `npm audit --omit=dev`: zero reported vulnerabilities |
| Full npm security audit | Five high-severity entries in the development lint dependency chain |
| Proposal integrity | Final SHA-256 equals the original recorded hash |
| Git history | Repository initialized; zero commits |

The backend lock consistency check used the already installed packages, not a
second empty virtual environment. No database, external API, dataset or model was
involved in testing. A dedicated mobile-device test and comprehensive automated
accessibility audit were not performed; the layout uses responsive styles and
semantic navigation, headings, focus indicators and a skip link.

## Locale checks

- `/` redirects to `/tr` even with `Accept-Language: en`.
- `/tr` and `/en` return HTTP 200 with the correct HTML `lang`, translated
  purpose/status and links to both locales.
- Both message dictionaries contain matching, nonempty keys.
- `/tr/missing-page` and `/en/missing-page` return HTTP 404 with localized text.
- The initial missing-page test found that Next.js used its global fallback;
  adding a locale-scoped catch-all route fixed the issue.

## Initial failures and corrections

- Registry access failed with DNS restrictions in the sandbox. Approved retries
  retrieved version metadata and installed project dependencies.
- Python virtual environment creation failed in ensurepip because temporary
  files were blocked. An approved retry completed the virtual environment.
- Sandbox SWC native-cache checks and loopback socket access were blocked.
  Approved executions completed type generation, build and HTTP checks.
- Endpoint tests stalled inside the sandbox; they were interrupted and passed
  outside it.
- Implicit ambient types from ancestor directories caused TypeScript errors.
  Explicit Node/React ambient types isolate this project's type environment.
- An initial PostCSS anonymous-default-export lint warning was corrected.
- ESLint 10 ran checks but failed some plugin peer ranges. The final tree uses
  ESLint 9.39.5 without forcing peer resolution.
- Optional WASI dependency versions initially failed `npm ls --all`. Two
  compatible, exact transitive overrides repaired the dependency tree. See
  `environment.md`.
- A sandbox lock-consistency check emitted temporary-directory cleanup warnings;
  the approved repeat completed without those warnings.

## Unresolved dependency notices

The full npm audit reports `braces` stack-exhaustion denial of service
([GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm))
through `micromatch`, `fast-glob`, `@next/eslint-plugin-next` and
`eslint-config-next`. The five entries represent the affected chain, not five
independent root flaws. They are development dependencies. The registry's latest
`braces` version was 3.0.3, still within the advisory's affected range.
`npm audit fix --force` was not used: its proposed Next lint-config downgrade
would introduce a major-version mismatch. Do not feed untrusted glob patterns
into this development tooling; revisit compatible upstream fixes before
publication or broader use. An audit reports known advisories, not a guarantee of
security.

The registry marks ESLint 9.39.5 unsupported. ESLint 10's incompatible plugin peer
ranges are documented in `environment.md`; do not silently upgrade it or bypass
peer checks.

Starlette 1.8.0 emits a warning that its httpx TestClient compatibility is
deprecated in favor of httpx2. The three tests still passed. This warning is not
suppressed and can be addressed in a subsequent approved dependency maintenance
task.

## Command record

Read-only inspection used `Get-Location`, `Get-ChildItem`, `rg --files`,
`Get-Command`, tool version commands, `Get-FileHash`, applicable instruction-file
checks and `git rev-parse --show-toplevel`. npm/PyPI metadata and official
framework documentation were read to select versions.

Initialization used `git init` and `python -m venv backend/.venv`.
Files were created with patches. Dependency resolution used `npm install`,
`npm ci`, targeted npm metadata/update commands, `python -m pip install -r
requirements-dev.txt`, and `python -m pip freeze` to create the Python lock.

Validation used the commands in the table, `npm ls --depth=0`, `npm audit --json`,
`npm run start`, `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
`Invoke-RestMethod`, browser inspection, `git status --short`,
`git ls-files --others --exclude-standard`, and `git rev-list --all --count`.
For frontend checks, `NEXT_TELEMETRY_DISABLED=1` was set in the command process.

Temporary verification servers were stopped after validation. No deployment,
system-tool installation, database initialization or Git commit was performed.
