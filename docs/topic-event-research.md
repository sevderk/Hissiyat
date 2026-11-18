# Local topic and event research

The Turkish and English home pages open with **Create Research**. Topic and
event mode use the same query, inclusive UTC dates, source and optional language
filters. Event mode searches the words supplied by the user in the source index.
The search does not discover the boundaries of an event or enumerate every post.
Civil Comments applies the search locally to a published archive.
The result shows the normalized query sent upstream, requested and observed
date coverage, retrieved and eligible counts, exclusion counts, and UTC dates
represented in the eligible records. Geography remains unknown.

## Source selection

- **Lemmy.World** uses one [v0.19 search](https://join-lemmy.org/lemmy-js-client-docs/v0.19/interfaces/Search.html)
  `GET https://lemmy.world/api/v3/search` with `type_=Posts` or `type_=Comments`,
  `listing_type=Local`, `sort=New` and `limit=25`. One authorization covers one
  record type and one page. The adapter requires local records in public local
  communities with canonical instance links. A [comment view](https://join-lemmy.org/lemmy-js-client-docs/v0.19/interfaces/CommentView.html)
  includes a comment, its parent post and the community. The adapter checks
  all three for applicable safety and visibility flags and verifies the
  parent-post ID before projecting a thread link. The comment's own reported
  `published` timestamp determines date eligibility and does not come from the
  parent or last edit. The endpoint has no date-range or language filter in
  this version. UTC dates filter the returned page locally. The positive
  source-native `language_id` comes from each [post](https://join-lemmy.org/lemmy-js-client-docs/v0.19/interfaces/Post.html)
  or [comment](https://join-lemmy.org/lemmy-js-client-docs/v0.19/interfaces/Comment.html).
  A missing or undetermined language stays unknown.
  The implementation sends no credentials. Private instances can require login
  and the server can set [its own search limit](https://join-lemmy.org/lemmy-js-client-docs/v0.19/interfaces/LocalSiteRateLimit.html).
  The effective Lemmy.World search quota is unverified. The [instance terms](https://legal.lemmy.world/tos/)
  cover the API, permit good-faith use of provided methods, impose an age
  requirement, and prohibit disruption and evasion of blocks. They provide no
  verified general right to republish the posts. The one-request verification
  is link-only, with no excerpts, publication, or further corpus collection.
- **Bluesky** remains a candidate. The Phase 8B request used the documented
  `app.bsky.feed.searchPosts` GET on the public AppView with no credentials.
  The client merged 401 and 403 into `provider_denied`, so the original status
  and exact rejection reason cannot be recovered. The [official lexicon clarification](https://github.com/bluesky-social/atproto/pull/3844)
  says access can require authentication. A [historical maintainer account](https://github.com/bluesky-social/bsky-docs/issues/332)
  describes a deliberate 403 load restriction, and a [third-party incident report](https://github.com/cyanheads/bluesky-mcp-server/issues/32)
  describes 403 on first-page anonymous searches. These make deliberate
  restriction plausible for Phase 8B. The documented method and approved query
  give no evidence of invocation error. The current client distinguishes a
  401 authentication error from a 403 access refusal and forwards only the
  numeric HTTP status with the fixed local error code. A later authenticated
  investigation could use the [official PDS session/proxy route](https://bsky.network/docs/bluesky-api/request-proxying/)
  under separate approval. Its availability for this use remains unverified.
- **Google Trends** stays visible as a core search-interest source. Real
  measurement metadata and permission to display results remain unresolved.
  The [separate Trends preview](trends-research-preview.md) documents this
  checkpoint and how to view the labeled fictional example offline.
- **Mastodon** remains an alternative. [Full-text status search](https://docs.joinmastodon.org/methods/search/)
  requires user authentication and an instance with status indexing. A
  [public hashtag timeline](https://docs.joinmastodon.org/methods/timelines/#tag)
  may work at instances that allow anonymous public timelines. It depends on
  exact hashtag usage and what that instance sees. [Status metadata](https://docs.joinmastodon.org/entities/Status/)
  include a source URL, timestamp, optional language, visibility, a sensitive
  flag, and content warning. The status body is HTML. Mastodon documents a
  [default rate limit](https://docs.joinmastodon.org/api/rate-limits/) of 300
  requests per five minutes per account or IP, with possible instance or
  endpoint differences. An eventual integration needs an instance-specific
  terms, moderation and reuse check. Lemmy v0.19 gives this phase a concrete,
  plain-text query with explicit local coverage and post/community flags.
- **Other sources.** Stack Exchange remains secondary. YouTube remains
  conditional on its policies and relevant approvals. Reddit is on hold.
  X is outside the current scope.

## Boundaries and interpretation

The public result view exposes vetted links, UTC publication timestamps and
available language metadata. Bluesky can select by index time and use the
provider's language detection. Publication time is checked separately, and
language or profile information is never used to infer geography. Lemmy
excludes flags for sensitive, removed, deleted, hidden or nonpublic content.
Required flags must be present with the expected types. Bluesky excludes
recognized [moderation and self-labels](https://github.com/bluesky-social/bsky-docs/blob/main/docs/advanced-guides/moderation.md)
when supplied. Unmarked material can still be unsuitable. The client never
fetches media or renders source Markdown or HTML. Source text exists in
process memory for the duration of the request. Links and summary counts stay
in tab memory. A source search only runs after explicit form submission.

The [Bluesky terms](https://bsky.social/about/support/tos) describe authors'
rights and Bluesky's license. Local inspection uses a link-only public view.
Displaying excerpts, storing a corpus or sending posts to NLP needs separate
source-use and privacy review. The first page is a search-index sample whose
counts describe its own contents. Comparative research requires a justified
sampling design across time and sources. Search interest is a separate measure
from the opinions and experiences expressed in text.

## Discussion analysis and source permissions

Lemmy.World's [terms](https://legal.lemmy.world/tos/) cover the API, allow good-faith
use of provided methods, and prohibit disruption, block evasion and privacy
abuse. The terms and [privacy notice](https://legal.lemmy.world/privacy-policy/)
provide no verified authorization for this project's temporary local NLP on
real posts or comments, showing excerpts, or publishing derived results. No
explicit prohibition on every temporary non-commercial analysis was identified.
The software's API contract describes access and fields. A separate assessment
must establish applicable content rights and the personal-data processing basis.
Türkiye's [KVKK, articles 3 and 28](https://www.kvkk.gov.tr/Icerik/6649/Personal-Data-Protection-Law)
defines automated collection or categorization as processing when personal data
is involved and makes the scientific-purpose exception conditional. Its
application to this corpus remains unresolved. Keeping text in memory and
reporting aggregate counts reduces disclosure but does not resolve those issues.

The live route accepts separately authorized metadata checks only. The API search
response can still include comment/post text and profile fields. The adapter
does not expose source text to the browser, retain it, or use it for NLP. There
is no automatic aggregation of the meaning of live text. The numeric Lemmy
language ID is shown as source metadata. Future live analysis will also need a
verified language mapping and an independently justified eligibility protocol.

The fictional discussion example includes 6 posts and 10 replies. It runs the
existing two-group TF-IDF + NMF and offline MiniLM + K-means methods over the
same distinct, eligible English texts. A missing MiniLM model leaves NMF
available. Fewer than 12 eligible texts skip grouping. The existing explicit
English expression rules count emotion, needs and reported personal experience
per text, and categories may overlap. They measure wording, with limited
coverage and reliability. Outputs include method distributions, expression
counts, and row indices pointing to the input set behind those aggregates.
No assignments, embeddings, or AI-written interpretation are returned.

## Historical Civil Comments pilot

[Civil Comments](https://www.tensorflow.org/datasets/catalog/civil_comments)
contains public comments originally posted on English-language news sites in
2015–2017. The archive and the Jigsaw toxicity annotations are distributed as
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). CC0 addresses
copyright reuse and does not eliminate privacy risks in comment text.
The simplified [Google Civil Comments export](https://huggingface.co/datasets/google/civil_comments/raw/main/README.md)
contains text and seven scores, with no publication date, article ID or publication
ID. TFDS 1.2.4 documents all three fields and a 9,969-row in-context configuration
with a prepared size of 9.63 MiB. The TFDS public bucket did not list a prepared
object for this dataset. Its builder points to a full 427.41 MiB archive.

The original Civil Comments corpus is the platform's news-comment archive.
Jigsaw used that archive to build the Unintended Bias in Toxicity Classification
dataset, adding crowd annotations. Its [release builder](https://huggingface.co/datasets/google/jigsaw_unintended_bias/blob/d46022c9df7c8b74ba52876f314f81ef60fa1727/jigsaw_unintended_bias.py)
version 1.1.0 maps `test_public_expanded.csv` to
`test_public_leaderboard`, one split of the Jigsaw dataset. The pilot uses
this split from a [pinned distribution mirror](https://huggingface.co/datasets/shuttie/jigsaw-unintended-bias/tree/9beb047ad342ac2c3ac209d2d74e0b7c833fe294/data).
The exact object is `test_public_expanded.csv.gz`, revision
`9beb047ad342ac2c3ac209d2d74e0b7c833fe294`, 16,425,656 bytes,
SHA-256 `a5a8fba390af3f17639b1bcef9b1c1b38373d3e45728f7eb814bfe5f3ea1c3d2`.
The 40-character revision pins the repository state. The 64-character SHA-256
checks the compressed file bytes. Original publisher byte equivalence
was not independently established. The importer verifies the gzip, schema and
97,320-row split count in memory. It uses comment ID for ordering and deduplication,
comment text, the original date with its explicit time offset, article and
publication IDs, source moderation status and a subset of the safety fields.
The UTC representation preserves the publication instant. The evidence view
keeps the article and publication IDs separate from links. The split supplies
neither the news headline nor the comment permalink, and all countries are unknown.

Both research modes use Unicode-normalized, case-insensitive literal word or
phrase matching. For historical searches, a pipe separates two to eight
alternatives of two to six words. Any full phrase qualifies and each comment
counts once. Repeated whitespace is collapsed. There is no stemming,
synonym expansion or semantic event classifier.
Matched comments must fall within the approved UTC dates, pass a simple English
wording check and be no longer than 500 characters. The pilot requires an
`approved` moderation status, a positive number of toxicity annotators,
`toxicity < 0.2`, and zero on sexual explicitness, obscenity, threats and severe
toxicity. Missing or malformed required scores fail screening. Visible contact
and markup patterns are excluded. These rules can miss personal information or
unsuitable language and narrow the sample to particular types of expression.
The adapter ignores identity scores, parent identifiers and user information.
After deduplication by comment ID and normalized text, the SHA-256 ordering
of comment IDs selects at most 100 comments, at most four per known article
and four total with unknown article IDs. Text and identifiers used internally
for selection are not persisted. Only metadata and allowlisted aggregates
reach the local browser. No text goes to an external model.

### First authorized run

On 18 November 2026, one archive download, including the distribution CDN
redirect, passed SHA-256 verification. The query was the literal word `work`
over 1 January 2015 to 31 December 2017, UTC. From 97,320 examined rows there
were 3,665 literal matches. Of those matches, 2,356 failed the content or
metadata screen and one was a duplicate. There were 1,308 eligible comments
before sampling, of which 100 were selected and analyzed. The sample spans
98 article IDs and 11 publication IDs. All 100 records have unknown geography.

| Measure | Observation among 100 selected comments |
| --- | --- |
| Original publication coverage (UTC) | 14 February 2016 to 9 November 2017. 20 comments in 2016, 80 in 2017. |
| TF-IDF + NMF, two groups | 93 and 7, all assigned. |
| Offline MiniLM + K-means, two groups | 62 and 38, all assigned. |
| Between-method agreement | ARI −0.0267 across 100 common assignments. |
| Explicit wording rules | Curiosity matched in one comment. Other supported emotion, need and reported experience rules had zero matches. |

The rules measure matching expressions, and zero counts do not establish
absence of an experience or need. Topic groups are exploratory and their
keywords come from a restricted disclosure vocabulary. The query word can
appear in both groups by construction. Sampling and screening affect the
monthly distribution. This test split cannot estimate news audiences' views,
population experiences, event participation, cross-country differences or
trends. The workspace links the archive, distribution and license and shows
monthly publication counts for observed months.

### Focused employment study

The broad `work` search could include employment, tasks, and whether
something functions. Its original input texts were ephemeral, so differences
in wording, length, or subject matter cannot be assigned as causes of the
93/7 NMF partition. NMF assigns each comment to its highest-weight component
in a sparse word-based representation. MiniLM and K-means use dense vectors
and distance to centroids. Differences in what these representations group
together can contribute to disagreement. The common search word may dominate
some of the surfaced terms. The display vocabulary and the requirement of
support in at least three distinct texts limit the keywords available for
interpretation.

The near-zero [Adjusted Rand Index](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.adjusted_rand_score.html)
describes low overlap after accounting for chance. It provides no reference
labels for evaluating accuracy. Two groups were requested. A 93/7 split can
follow a common component and a small set of distinctive records, and it
does not establish a minor social theme. Expression rules cover a restricted
set of explicit English phrasings and treat quotations, uncertainty and
attribution conservatively. A news-comment sample may contain considerable
indirect argument or general statements. Those possibilities remain unverified
for the original pilot. Sample filtering and the 500-character limit can
also affect what types of expression enter an analysis.

Two queries were fixed before data access. Both use 1 January 2015 to
31 December 2017 UTC, apply the existing filters, and select at most
100 comments with the same article cap. Matched comment records may overlap
across questions. Counts for individual phrases can overlap within a question.

| Question | Exact alternatives |
| --- | --- |
| How much archived discussion evidence matches wage-floor and low-pay phrases, and what grouping and explicit wording signals are observable in the sample? | `minimum wage`, `living wage`, `hourly wages`, `low wages` |
| How much matches phrases about job opportunities, job creation, or finding work, and what grouping and explicit wording signals are observable in the sample? | `job opportunities`, `job creation`, `create jobs`, `creating jobs`, `find a job`, `finding a job`, `looking for work` |

The study reports the first reason for each screened exclusion, selected
median character length, coverage and original comment dates, phrase counts,
expression counts and method distributions. The primary grouping has
`k=2` when at least 12 texts are analyzable. A prespecified `k=3`
sensitivity check requires 24 texts and uses the same selected comments and
settings. Neither setting estimates the number of true topics. The workspace
flags groups with fewer than 10% of a method's assigned records, ARI up to
0.10 as low agreement, and groups without displayable terms. These are
descriptive rules, with no guarantee of thematic validity. Article context,
stance, psychological inference and event attribution remain unverified.

The one-time CLI uses the pinned Hugging Face mirror, checks
the archive once and runs the two queries on that one in-memory payload. It
prints aggregate evidence only. Obtain separate owner approval before
launching `python -B -m app.core.civil_study --authorized-retrieval`
from the backend environment. Supply the existing verified local model
directory through `--model-dir` when available.

#### Authorized results

On 18 November 2026 one owner-authorized download passed the pinned SHA-256
check. Both queries used the same 97,320-row split in memory. Per query, the
counts below describe its own comment sample, and samples may overlap.

| Measure | Wage floor and low pay | Job opportunities and creation |
| --- | ---: | ---: |
| Literal matches | 236 | 104 |
| Excluded by content or metadata screening | 157 | 62 |
| Eligible before sampling | 79 | 42 |
| Selected and analyzed | 65 | 42 |
| Distinct known articles / publications | 48 / 13 | 40 / 9 |
| Observed UTC dates | 2016-02-14 to 2017-11-10 | 2016-03-11 to 2017-11-07 |
| Selected publication counts for 2016 / 2017 | 21 / 44 | 10 / 32 |
| Selected median length, characters | 289 | 301.5 |
| NMF sizes at `k=2` | 57 / 8 | 28 / 14 |
| MiniLM sizes at `k=2` | 31 / 34 | 25 / 17 |
| ARI at `k=2` | 0.0209 over 65 | 0.2070 over 42 |
| NMF sizes at `k=3` | 45 / 7 / 13 | 18 / 12 / 12 |
| MiniLM sizes at `k=3` | 17 / 37 / 11 | 18 / 15 / 9 |
| ARI at `k=3` | −0.0700 over 65 | 0.0868 over 42 |
| Comments with a supported explicit wording match | 0 of 65 | 0 of 42 |

The first screening reasons for wages were length 125, contact or markup 6,
English wording 15, moderation 2, and safety labels 9. For job opportunities
they were 50, 0, 5, 1, and 6 in the same order. Neither query had duplicates,
invalid timestamps or IDs, or matches outside the approved dates. The article
cap removed 14 of the 79 eligible wage comments from the sample. All selected
comments had known article and publication IDs and unknown geography.

In the wage sample the four phrases in protocol order occurred in 47, 14, 1,
and 3 of 65 comments. For job opportunities the seven phrases occurred in
3, 4, 17, 2, 7, 1, and 8 of 42 comments. These counts describe the wording
that matched. They cannot distinguish positions on a policy, identify affected
people or establish relevance to a particular news event.

Length accounted for 125 of 236 wage matches and 50 of 104 job matches as a
first exclusion reason. This shows substantial selection toward shorter texts;
the effects of the length limit on clustering or expression rates were not
isolated. At `k=2` the smaller wage NMF group had no terms meeting the display
criteria. The job sample's lower agreement at `k=3` shows sensitivity to the
requested group count. Across both questions the evidence supports sample
coverage and exploratory distributions. Shared theme labels, stance and
emotion prevalence remain unverified.

## Licensed Wikimedia discussion pilot

The pilot targets the English Wikipedia article discussion page `Talk:USB flash drive`.
It requests one current snapshot using the first-party [DiscussionTools Action API](https://www.mediawiki.org/wiki/Extension:DiscussionTools#API)
with `threaditemshtml`, `transcludedfrom`, and signature stripping. The module is
marked internal in its [implementation](https://github.com/wikimedia/mediawiki-extensions-DiscussionTools/blob/master/includes/ApiDiscussionToolsPageInfo.php).
Treat its response shape as version-sensitive. The [Revisions API](https://www.mediawiki.org/wiki/API:Revisions)
reports edit-level metadata. The pilot instead uses [DiscussionTools](https://www.mediawiki.org/wiki/Extension:DiscussionTools/How_it_works)
comment nodes and signature timestamps. These may miss unsigned comments and some
nonstandard discussions. The adapter rejects ambiguous structure and ignores
heading body, archive pages, and text with unresolved transclusion origin or
imported quotations. It screens at most 25 candidates from up to 512 KiB,
prioritizing the newest identified comments inside the requested UTC window.
The API may return more than 25 items before local screening. Requests follow
no redirects or pagination and make no retries.

[Wikimedia's Terms of Use, section 7](https://foundation.wikimedia.org/wiki/Terms_of_Use#7._Licensing_of_Content)
provide CC BY-SA 4.0 for suitable original contributor text. The discussion page
and its history provide attribution to contributors. Redistributing copied or
adapted text calls for the applicable license notice and attribution, with
changes identified and the ShareAlike condition applied to adaptations.
Imported material and project exceptions require separate review. This pilot
handles screened text in memory, keeps DiscussionTools IDs and author fields
out of outputs, and exposes page, history and license links with numerical
summaries. Personal-data risks remain separate from the copyright license.
Pattern checks reject common identifier and quotation markers, yet cannot
guarantee anonymity or language identity. Real comments, excerpts, author
metadata and payloads are never saved or sent to external models. The response
records the page and acquisition time. This endpoint does not pin the revision.

The [API access policy](https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy)
requires an identifying User-Agent. The pilot uses the public Hissiyat repository
URL as contact. The [current rate-limit guide](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits)
lists up to 200 requests per minute for appropriately identified anonymous clients,
subject to change and operational limits. This pilot permits one request per approval.

The deterministic **Research interpretation** section shows the source, date
window, screened count, and eligible text denominator. Expression counts can
overlap. Method group sizes come from the existing models. The publication-day
distribution describes the sample. The panel links to the evidence and to
page attribution when present. Generative summaries are disabled.

## Run locally

From `backend` in one PowerShell window:

```powershell
$env:HISSIYAT_ENVIRONMENT = 'development'
$env:HISSIYAT_LOCAL_RESEARCH = '1'
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8059 --no-proxy-headers --no-access-log
```

From `frontend` in another window:

```powershell
$env:HISSIYAT_LOCAL_RESEARCH = '1'
$env:HISSIYAT_LOCAL_RESEARCH_PORT = '8059'
npm.cmd run dev -- --port 3056
```

Open `http://127.0.0.1:3056/tr` or `/en`. Load either topic or event example
and select **Run research**. Both examples contain invented records. Repeat
the run with new query words to see what a zero-result response looks like.
Load the discussion example and run it for the full fictional analysis. Set
`HISSIYAT_LOCAL_ANALYSIS_MODEL_DIR` to the existing verified offline MiniLM
directory if it is available.

Live sources start locked. Before any real search, obtain explicit owner
approval for the exact provider, query, UTC window and 25-post cap. Set
`HISSIYAT_LEMMY_APPROVED_REQUEST` in the process environment of a single new
backend worker to a JSON object with `mode`, `query`, `start_date`, `end_date`,
`source` set to `"lemmy"`, and `language` and `geography` set to `null`. Add
`"content": "comments"` for a comments-only verification. An omitted content
field means posts. For an
independently authorized Bluesky search, the existing
`HISSIYAT_BLUESKY_APPROVED_REQUEST` uses source `"bluesky"` and optional
`"en"` or `"tr"` language. Enter the same scope in the local workspace and
submit once. Configure just one permit and clear it from the shell after
launch. Use a single worker without reload. The worker consumes approval
before attempting the request. There are no retries, redirects or next pages.
Restarting with the same setting would reload approval. Obtain fresh approval
for each later run. The proxy and backend remain off in production.

For the Wikimedia pilot the single-process setting is
`HISSIYAT_WIKIMEDIA_APPROVED_REQUEST`. Use source `"wikimedia"`, mode `"topic"`,
query `"Talk:USB flash drive"`, content `"comments"`, and `null` for both
`language` and `geography`. Include the approved dates and
`"analyze_discussion": true` only when the one-shot permission includes analysis.
The first owner-authorized check returned HTTP 200. One detected comment entered
screening and zero qualified. It produced no real-text or temporal finding.

For a separately approved Civil Comments run set
`HISSIYAT_CIVIL_APPROVED_REQUEST` with source `"civil_comments"`, the approved
mode, query and UTC dates, `"content": "comments"`, `"language": "en"`,
`"geography": null` and `"analyze_discussion": true`. This setting is
development-only and single-use. A run permits only the pinned file and its
observed HTTPS CDN redirect, with no download retries. Each new transfer
requires fresh approval. No input file or data cache is created.

Run `pytest tests/unit/test_topic_research.py tests/unit/test_civil_comments.py` from the backend environment
and `npm run test:topic-research` from `frontend` for offline tests. With the
local servers running, set `FRONTEND_BASE_URL` to the local frontend URL and
`FRONTEND_EXPECT_TOPIC_RESEARCH=1` before `npm run test:routes`.
