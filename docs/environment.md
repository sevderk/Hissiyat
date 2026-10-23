# Verified environment and dependencies

Inspection date: 2026-10-17. Working directory:
`C:\Users\Asus\Desktop\Hissiyat`.

## Existing tools

| Tool | Verified version |
| --- | --- |
| Node.js | 24.4.1 |
| npm | 11.4.2 |
| Python | 3.12.9 |
| pip | 24.3.1 |
| Git | 2.47.0.windows.1 |
| Docker CLI | 29.7.2, build a7dcaa6 |
| PostgreSQL CLI | `psql` not found on PATH |

Docker availability means only that its CLI responds; daemon availability was not
tested. Absence of `psql` on PATH does not establish that PostgreSQL is not
installed elsewhere. Neither tool is required, installed or configured here.
No system tools were upgraded.

The initial workspace contained only the proposal PDF (136,958 bytes), with no
existing application or Git repository. Its SHA-256 before implementation was
`9A3B5DFA0296FC747839694CD365DEF29605955A52352EF4C606A6C2E34F02B0`.

## Frontend direct dependencies

| Package | Pinned version |
| --- | --- |
| next / eslint-config-next | 16.4.2 |
| next-intl | 4.14.9 |
| react / react-dom | 19.3.1 |
| tailwindcss / @tailwindcss/postcss | 4.3.3 |
| typescript | 5.9.3 |
| eslint | 9.39.5 |
| @types/node | 24.19.2 |
| @types/react / @types/react-dom | 19.3.0 |

TypeScript 5.9.3 was selected within the TypeScript ESLint parser's supported
range. ESLint 10 was evaluated but some plugins shipped by eslint-config-next
16.4.2 declare peer ranges that exclude it. ESLint 9.39.5 is therefore retained
for a valid dependency tree. The registry marks ESLint 9 as unsupported; this
development-tool limitation must be revisited when compatible plugins are
available. Peer dependencies were not bypassed with force or legacy-peer-deps.

Two optional WebAssembly support dependencies are pinned through npm overrides:
`@emnapi/core` 1.11.3 and `@emnapi/wasi-threads` 1.2.3. npm 11.4.2 initially
resolved older versions outside the ranges required by Tailwind's optional WASI
package; a regular targeted update did not repair the tree. The overrides satisfy
those ranges and `npm ls --all` reports no dependency problems. They are not
additional direct application dependencies.

## Backend direct dependencies

| Package | Pinned version |
| --- | --- |
| fastapi | 0.143.3 |
| pydantic-settings | 2.16.0 |
| uvicorn | 0.54.0 |
| pytest | 9.1.1 |
| httpx | 0.28.1 |

The Phase 1A backend lock contained 25 resolved packages, including
Pydantic 2.14.1 and Starlette 1.8.0. Packages were installed only inside the local
virtual environment. The lock targets this tested Windows/Python 3.12 setup.

## Sandbox observations

The Codex sandbox blocked registry DNS, Python ensurepip temporary files, SWC
native-cache access and local socket connections. Appropriate operations were
retried through the approval mechanism. In-process endpoint tests also stalled
inside the sandbox, then passed outside it. These observations concern the agent
execution environment, not a requirement to run the application as administrator.
No machine-wide security or PowerShell execution-policy changes were made.

TypeScript explicitly includes only Node and React ambient types. This prevents
unrelated type packages from ancestor directories affecting the project.

## Reference documentation

- [Next.js installation](https://nextjs.org/docs/app/getting-started/installation)
- [next-intl routing](https://next-intl.dev/docs/routing/setup)
- [Tailwind CSS with Next.js](https://tailwindcss.com/docs/installation/framework-guides/nextjs)

Package versions and peer ranges were verified against npm and PyPI metadata.

## Phase 1B verification

The Docker CLI and running Linux daemon now report 29.8.2; Compose reports
v5.6.0. These versions were discovered, not installed or upgraded by this task.
An unrelated Supabase/PostgreSQL stack already exists on host port 54322 and
remains untouched. Existing application listeners occupy 3000 and 8000, so new
verification servers use 3001, 8001 and 8002. Port 55432 was free before setup.
No pre-existing `hissiyat-dev` Compose volume or network was found.

The new runtime packages are SQLAlchemy 2.1.5 and psycopg / psycopg-binary 3.3.6;
tzdata 2026.5 is the driver's new Windows transitive dependency. Existing locked
packages were held with pip constraints during installation, without unrelated
upgrades. The updated backend lock contains 29 packages.

The selected official image is `postgres:18.6-bookworm`. Version 18 is stable and
supported; PostgreSQL 19 was still a release candidate at verification time.
The pulled image digest was
`postgres@sha256:afc7e2d441324c0388fa80c3d24f733b4194a4eb7f47dd8ee2b08eb1a24a647c`.
See `database-development.md` for the PostgreSQL 18 volume path and exact setup
commands, and `validation-phase-1b.md` for execution results. Local generated
environment files are ignored and contain no reused production credentials.
