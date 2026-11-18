# Google Trends in the research workspace

## Manual Explore CSV fallback

Open the local development workspace at `http://127.0.0.1:3056/tr` or
`/en` using the [topic and event research setup](topic-event-research.md#run-locally).
Select **Google Trends · CSV import** in **Create Research**. The running
local frontend can import without a backend, API key, database or network
connection.

1. In [Google Trends Explore](https://trends.google.com/trends/explore),
   choose a search term, select **Web Search** and
   **All categories**, and choose a custom date range of at least 30
   inclusive days ending before today. Choose one country or Worldwide.
   For two countries, add the same search term and date range with the
   other country to that same chart.
2. Download the **Interest over time** CSV from the chart and copy the
   full Explore URL with its filters. The
   [export and citation guide](https://support.google.com/trends/answer/4365538?hl=en-GB)
   explains Google's reuse and attribution terms.
3. Paste the link into Hissiyat, select the original CSV, confirm that
   both came from the same chart and that use is permitted, then select
   **Analyze CSV**. Use the period slider or arrow keys to inspect a date
   in the chart and the surrounding observations in the table.

The importer checks the direct HTTPS Explore URL, one search term, absolute
dates, chart filters, country codes and the category, geography and
period headings in the original Turkish or English export. The workspace
language and the presentation language on the link may differ from the CSV.
It accepts a single unmodified UTF-8 file with at
most 2,000 periods and 256 KiB. It rejects ambiguous scope, mismatched term
or geography, relative dates, topics, unsupported chart types and
irregular period sequences. An observed period can start before the
requested window if it overlaps the window. Requested dates and actual
period starts are reported separately. A boundary period can cover only
part of the requested window.

Import errors distinguish unreadable files, invalid UTF-8, malformed CSV
rows, unsupported chart layouts, file-to-link metadata mismatches, period
gaps, invalid values, file limits and unexpected application failures.
The two local exports examined during the correction both had valid UTF-8
and the same Turkish header. The legacy English-only category check stopped
the import before the code considered the period or country. Both files
passed validation with their original link after the locale-aware fix.

The reported index is relative to the Explore request and uses a 0–100
scale. A numeric zero is the reported index and may reflect low activity.
A blank is recorded as unspecified, and `<1` is kept as a threshold value.
The chart breaks each line at these gaps and numeric summaries exclude
them. The peak and trough include the earliest matching date and tie
count. Change describes the difference between the first and last
numeric observations. Two-country comparisons use only jointly observed
periods in one export. The
[normalization FAQ](https://support.google.com/trends/answer/4365533?hl=en)
and [location comparison guide](https://support.google.com/trends/answer/4359550?hl=en)
describe the source measurement and one-chart comparison.

The user supplies the provenance by selecting the original file and link.
Hissiyat checks their available metadata. The file format alone cannot
authenticate the source or detect valid-looking changes to values. The
SHA-256 fingerprint identifies the exact file bytes. The browser keeps
the file and results in tab memory with no upload, external fetch, cache
or application persistence. Reload or close the tab to clear the import.
The workspace disables import in production. Credit Google Trends when
reusing data and follow Google's terms. The workspace presents search
interest and discussion activity as distinct measurements.

## Primary research path and the official API

Select **Google Trends · official API** in the topic or event workspace.
The form accepts one plain search term, a country, and up to 12 completed
months. The country options use ISO codes TR, US and GB. The country list
and 12-month bound are Hissiyat limits. The API receives month strings
without a day component. Month restrictions do not determine returned
aggregation. The Explore CSV remains a separate fallback.

### Confirmed interface and requirements

The owner's access is active and the earlier authorized `v1beta`
`getGraph(terms="career")` call returned HTTP 200 with 275 points. The
recorded response shape is a `lines` array with a string `term` and a
`points` array. The first point had a string `date` and an integer
`value`. Those observations establish neither actual geography nor
aggregation, units, or missing-value semantics.

The supplied Google getting-started guide shows the discovery-based Python
client at `https://trends.googleapis.com/$discovery/rest?version=v1beta`.
It documents `getGraph`, `getGraphAverages`, `regions().list` and
top/rising query and topic methods. For graph requests, it documents
paired `restrictions_startDate` and `restrictions_endDate` in `YYYY-MM`,
`restrictions_geo` with ISO geography codes, `restrictions_category` with
category paths, and `restrictions_property` with `web` as the default.
Hissiyat sends only the term, country and paired months. The installed
Google SDK 2.202.0 constructs parameters from the service's discovery
document at runtime. There is no bundled or cached authenticated Trends
document locally. A fictional discovery document exercises the exact
argument names in the installed SDK. Live discovery still has to accept them.

The guide limits use to non-commercial research, disallows transfer of raw
API data and calls for sharing results in summary form. Its privacy
warning gives zeros ambiguous meaning. The API points remain in backend
memory. The local response contains only structural types and counts until
there is a verified response contract and permission for a local summary.
An authorized contract can disclose verified geography, cadence, coverage,
availability counts, a peak date and endpoint direction. Ambiguous zeros
and explicit gaps are excluded from peak and direction calculations. No
per-point API measurements appear in the browser. The local API is gated
by loopback, development opt-in, same-origin checks and an exact
scope-specific single-use permit. Each permit is consumed before outbound
I/O. The provider transport suppresses credential-bearing logs and allows
no automatic retries or redirects. There is no public provider endpoint
or export. The old read-only preview remains available for fictional
series, and the standalone schema check stays available for research.
The Explore CSV index has its own request-relative scale.

### Questions for Google support

The [public alpha page](https://developers.google.com/search/apis/trends)
describes consistently scaled data and multiple aggregation intervals. It
does not bind the installed account's `v1beta` response to that contract.
The published technical guide link and the owner's authorized browser both
report an access error. Use the
[official access troubleshooting page](https://developers.google.com/search/apis/trends/help/cant-access-docs)
to report the guide access issue. Request confirmation of these points:

1. The canonical authenticated guide and how it applies to the supplied
   `v1beta` getting-started guide and this active Research API account.
2. Whether this endpoint accepts country and subdivision codes, how it
   interprets the start and end months, and how the returned cadence and
   time zone are selected and identified.
3. Exact response fields for returned geography and cadence, index unit,
   comparability across countries or across requests, and distinctions
   among numeric zero, missing observations and suppressed values.
4. Applicable per-project rate and daily quotas and response limits.
5. Which private visualizations and aggregate summaries may be displayed
   or shared, and which attribution or retention rules apply.

### Bounded verification and owner launch

The proposed scope is topic mode, `career`, Turkey (TR), September to
October 2026. The single graph call is
`getGraph(terms="career", restrictions_geo="TR", restrictions_startDate="2026-09", restrictions_endDate="2026-10")`
on the official `v1beta` client. One discovery request comes first. The
verification expects the previously observed `lines[].term` and
`lines[].points[].date` / `value` shapes, reports recognized metadata
field names, and does not infer their meanings. The project quota and
the end-month inclusion rule are unknown.

After explicit approval for this scope, open a local PowerShell in
`backend` with the optional dependencies in `requirements-trends.txt`
available. The first-day dates below encode month selectors inside the
application. The provider request sends `2026-09` and `2026-10`.

```powershell
$env:HISSIYAT_ENVIRONMENT = 'development'
$env:HISSIYAT_LOCAL_RESEARCH = '1'
$env:HISSIYAT_GOOGLE_TRENDS_APPROVED_REQUEST = '{"source":"google_trends","mode":"topic","query":"career","geography":"TR","language":null,"start_date":"2026-09-01","end_date":"2026-10-01"}'
.\.venv\Scripts\python.exe -B -m app.trends_preview --workspace
```

Enter the API key only at the hidden prompt. The process binds to
`127.0.0.1:8059` and makes no provider request until the approved
form is submitted. Keep the first run in structural mode. If Google later
confirms response meanings and permits local summary display, the
server-side `HISSIYAT_GOOGLE_TRENDS_SUMMARY_CONTRACT` takes verified
field names and status mappings. It also requires
`measurement="consistently_scaled_search_interest"` and
`display="local_summary"`. Fixture field names are reserved for tests.

In the frontend terminal enable `HISSIYAT_LOCAL_RESEARCH=1` and set
`HISSIYAT_LOCAL_RESEARCH_PORT=8059` before starting the loopback dev
server. Select the official API option, fill the approved scope and submit
once. After using the permit, shut down the backend and clear
`HISSIYAT_GOOGLE_TRENDS_APPROVED_REQUEST` from the shell. Restarting with
the same configuration requires a new explicit approval.

### Authorized verification result

On 18 November 2026 the owner approved this exact scope and entered the
key at the hidden local prompt. One form submission completed through the
official SDK and the workspace returned HTTP 200. The graph contained 61
points. The first point had a string date and an integer value. The
allowlisted geography, cadence, scale and availability field names were
absent from the inspected response locations (root, line and first point).
The workspace displayed requested scope and response structure. The
numeric findings remained withheld. The point count does not establish
the cadence, returned geography or interval boundaries. The run was not
retried and the raw graph was not persisted.
