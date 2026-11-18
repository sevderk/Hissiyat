import {isResearchEnabled, projectResearchResult, researchErrorFor, researchUpstreamStatus} from '@/lib/topic-research';
import {projectOfficialTrends} from '@/lib/trends-research';

const noStore = {'Cache-Control': 'no-store'};
const replyError = (status: number, code: string) => Response.json({code}, {status, headers: noStore});

export function GET() {
  return replyError(404, 'not_found');
}

export const OPTIONS = GET;

export async function POST(request: Request) {
  const headers = request.headers;
  const host = headers.get('host') ?? '';
  if (!isResearchEnabled(process.env.NODE_ENV, process.env.HISSIYAT_LOCAL_RESEARCH) ||
      !/^127\.0\.0\.1(?::[0-9]{1,5})?$/.test(host)) return replyError(404, 'not_found');
  if (headers.get('origin') !== `http://${host}` ||
      (headers.has('sec-fetch-site') && headers.get('sec-fetch-site') !== 'same-origin')) {
    return replyError(403, 'forbidden');
  }
  if (new URL(request.url).search || headers.has('content-encoding') ||
      headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json' || !request.body) {
    return replyError(400, 'invalid_input');
  }

  const reader = request.body.getReader();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    void reader.cancel().catch(() => {});
  }, 5000);
  const buffer = new Uint8Array(4096);
  let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      if (size + value.byteLength > buffer.byteLength) {
        void reader.cancel().catch(() => {});
        return replyError(413, 'too_large');
      }
      buffer.set(value, size);
      size += value.byteLength;
    }
  } catch {
    return replyError(400, 'invalid_input');
  } finally {
    clearTimeout(timeout);
    reader.releaseLock();
  }
  if (!size || timedOut) return replyError(400, 'invalid_input');

  let input: unknown;
  try {
    input = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(buffer.subarray(0, size)));
  } catch {
    return replyError(400, 'invalid_input');
  }
  const isTrends = typeof input === 'object' && input !== null && 'source' in input && input.source === 'google_trends';
  try {
    const port = process.env.HISSIYAT_LOCAL_RESEARCH_PORT ?? process.env.HISSIYAT_LOCAL_ANALYSIS_PORT ?? '8000';
    if (!/^[1-9][0-9]{0,4}$/.test(port) || Number(port) > 65535) return replyError(503, 'unavailable');
    const upstream = await fetch(`http://127.0.0.1:${port}/api/v1/local/research`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Hissiyat-Local-Research': '1'},
      body: buffer.subarray(0, size), cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(90000),
    });
    const data: unknown = await upstream.json();
    if (upstream.ok) {
      const result = isTrends ? projectOfficialTrends(data) : projectResearchResult(data);
      if (result) return Response.json(result, {headers: noStore});
    } else {
      const code = researchErrorFor(upstream.status, data);
      if (code !== 'unavailable') {
        const status = researchUpstreamStatus(code, data);
        if (status === null) return replyError(upstream.status, code);
        return Response.json({code, upstream_status: status}, {status: upstream.status, headers: noStore});
      }
    }
  } catch {
    // Return a fixed error without logging transport exceptions or payloads.
  }
  return replyError(503, 'unavailable');
}
