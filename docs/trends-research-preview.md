# Google Trends Research API local preview

The owner-operated client uses the previously verified `v1beta` discovery
URL and `getGraph(terms="career")`. The browser can only read a prepared series
from memory on loopback. Browser navigation, refresh, and language switches
make no Google request. Both the dashboard section and its read route are
off by default and absent in production. The fictional Trends demo remains
available in its own section.

## Verified connectivity and limits

The Phase 7B owner-authorized `career` graph request returned HTTP 200.
Its sanitized structural report found `lines`, a string `term`, and a
`points` array with 275 items. In the first point, `date` was a string
and `value` an integer. The count and field types establish connectivity and
response shape. No raw values, keys, or authenticated discovery document are
retained in this record.

| Semantics or permission | Checkpoint status |
| --- | --- |
| Measurement family | Google's public alpha documentation describes consistently scaled search interest. The exact units and interpretation of this response remain unverified. |
| Geographic scope | Unresolved for the `career` response. |
| Temporal aggregation | Unresolved. The 275 items do not establish a cadence. |
| Meaning of `date` | Unresolved. The report establishes a string field only. |
| Missing and suppressed observations | Unresolved for the authenticated response. Fixture markers are examples for the adapter. |
| Use and disclosure | The owner authorized one schema inspection. Permission to display actual values locally or publish them remains unverified. |

The Phase 8A inspection was offline. The real chart stays withheld until
the missing semantics and display permission are documented. The fictional
chart continues to distinguish observed zero, missing and suppressed states.
See the [public alpha documentation](https://developers.google.com/search/apis/trends).

## Before using the real API

Obtain the project owner's explicit approval for a single `career` query
and confirm the owner's access terms permit that inspection. Allow only the
one discovery request and one graph attempt, with no retries. Keep API keys
out of command arguments, environment files, application logs and Git.
Install the optional `backend/requirements-trends.txt` into the backend local
environment if needed. Use this command from `backend` in an interactive PowerShell.

```powershell
$env:HISSIYAT_ENVIRONMENT = 'development'
.\.venv\Scripts\python.exe -B -m app.trends_preview
```

Launch the command only after explicit approval. Enter the key at the hidden prompt.
Without field definitions, the command shows only allowlisted structural
metadata and exits. It writes no response to disk.

For local display, first confirm the owner's terms permit displaying values
and verify the field semantics against authenticated documentation. Pass
`--fields` with the path to a private JSON mapping of documented field names.
Use no credentials or returned data in that file. The mapping names the
geography and aggregation fields of `lines[0]`, the date, numeric value and
status fields of each `points` member, and the exact status strings and their
meanings. The only accepted standard forms are ISO calendar-period start
dates, explicit daily, weekly, monthly or yearly aggregation, and explicit
observed, missing or suppressed states. This version requires contiguous
periods and null values for missing and suppressed states. Other encodings,
undocumented defaults, implicit gaps and ambiguous values withhold the chart.
The test field names are fictional and must never be used as API documentation.

Only a validated series starts a local preview server on `127.0.0.1:8058`.
In the frontend terminal set `HISSIYAT_TRENDS_PREVIEW=1` before `npm.cmd run dev`.
Open the `#trends-research` section of `/tr` or `/en`. Shut down the preview server
to discard the series. Treat any later request as a new bounded operation.

## Interpretation and offline checks

The chart places observations at their true temporal spacing and labels the
axis in original value units. Zero retains an observation marker. Missing and
suppressed periods have distinct gap markers and show no invented value in the
accessible period list. The displayed endpoints are the first and last period
starts, as opposed to inferred request boundaries. The measured quantity is
relative search interest. It supports no inference about population-level
experience, emotions, or causation from this single query. Compare sources
only with independently justified geography, dates and definitions.

The fictional fixture exercises a value above 100, zero, explicit missing and
suppressed periods, and decimal values. Run `pytest tests/unit/test_trends_research.py`
from `backend`. The backend and browser do not persist the returned series.
