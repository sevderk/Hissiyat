import {analysisLimits, isLocalAnalysisEnabled, isLocalAnalysisResult, isMethodResult} from '@/lib/local-analysis-contract';

const noStore = {'Cache-Control': 'no-store'};
const loopbackHost = /^127\.0\.0\.1(?::[0-9]{1,5})?$/;

function error(status: number, code: string) {
  return Response.json({code}, {status, headers: noStore});
}

export function GET() {
  return error(404, 'not_found');
}

export const OPTIONS = GET;

export async function POST(request: Request) {
  const headers = request.headers;
  const host = headers.get('host') ?? '';
  if (!isLocalAnalysisEnabled(process.env.NODE_ENV, process.env.HISSIYAT_LOCAL_TEXT_ANALYSIS) ||
      !loopbackHost.test(host)) return error(404, 'not_found');
  // A page on a different origin cannot submit or read analysis through this proxy.
  if (headers.get('origin') !== `http://${host}` ||
      (headers.has('sec-fetch-site') && headers.get('sec-fetch-site') !== 'same-origin')) {
    return error(403, 'forbidden');
  }
  if (new URL(request.url).search || headers.has('content-encoding') ||
      headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json' || !request.body) {
    return error(400, 'invalid_input');
  }

  const reader = request.body.getReader();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    void reader.cancel().catch(() => {});
  }, 5000);
  const buffer = new Uint8Array(analysisLimits.maxBytes);
  let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      if (size + value.byteLength > buffer.byteLength) {
        void reader.cancel().catch(() => {});
        return error(413, 'too_large');
      }
      buffer.set(value, size);
      size += value.byteLength;
    }
  } catch {
    return error(400, 'invalid_input');
  } finally {
    clearTimeout(timeout);
    reader.releaseLock();
  }
  if (!size || timedOut) return error(400, 'invalid_input');

  try {
    const port = process.env.HISSIYAT_LOCAL_ANALYSIS_PORT ?? '8000';
    if (!/^[1-9][0-9]{0,4}$/.test(port) || Number(port) > 65535) throw new Error('Invalid local analysis port');
    const response = await fetch(`http://127.0.0.1:${port}/api/v1/local/text-analysis`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Hissiyat-Local-Analysis': '1'},
      body: buffer.subarray(0, size), cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(60000)
    });
    switch (response.status) {
      case 400: return error(400, 'invalid_input');
      case 413: return error(413, 'too_large');
      case 422: return error(422, 'insufficient_variation');
      case 429: return error(429, 'busy');
      case 503: {
        const failure: unknown = await response.json();
        if (typeof failure === 'object' && failure && 'code' in failure && failure.code === 'model_unavailable') {
          return error(503, 'model_unavailable');
        }
        break;
      }
      case 200: {
        const result: unknown = await response.json();
        if (isLocalAnalysisResult(result) || isMethodResult(result)) return Response.json(result, {headers: noStore});
      }
    }
  } catch {
    return error(503, 'unavailable');
  }
  return error(503, 'unavailable');
}
