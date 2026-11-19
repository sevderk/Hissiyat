import {projectAIInterpretation, projectEvidencePackage} from '@/lib/research-interpretation';
import {isResearchEnabled} from '@/lib/topic-research';

const noStore = {'Cache-Control': 'no-store'};
const error = (status: number, code: string) => Response.json({code}, {status, headers: noStore});
export function GET() { return error(404, 'not_found'); }
export const OPTIONS = GET;

export async function POST(request: Request) {
  const headers = request.headers;
  const host = headers.get('host') ?? '';
  if (!isResearchEnabled(process.env.NODE_ENV, process.env.HISSIYAT_LOCAL_RESEARCH) ||
      !/^127\.0\.0\.1(?::[0-9]{1,5})?$/.test(host)) return error(404, 'not_found');
  if (headers.get('origin') !== `http://${host}` || headers.has('sec-fetch-site') && headers.get('sec-fetch-site') !== 'same-origin') {
    return error(403, 'forbidden');
  }
  if (new URL(request.url).search || headers.has('content-encoding') ||
      headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json' || !request.body) return error(400, 'invalid_input');
  const reader = request.body.getReader();
  const buffer = new Uint8Array(512);
  let size = 0;
  let timedOut = false;
  const timeout = setTimeout(() => { timedOut = true; void reader.cancel().catch(() => {}); }, 5000);
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      if (size + value.length > buffer.length) { void reader.cancel().catch(() => {}); return error(413, 'too_large'); }
      buffer.set(value, size);
      size += value.length;
    }
  } catch { return error(400, 'invalid_input'); }
  finally { clearTimeout(timeout); reader.releaseLock(); }
  if (!size || timedOut) return error(400, 'invalid_input');
  try {
    const input: unknown = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(buffer.subarray(0, size)));
    if (!input || typeof input !== 'object' || !('package_id' in input) || !('language' in input) ||
        Object.keys(input).length !== 2 || typeof input.package_id !== 'string' || !/^[0-9a-f]{32}$/.test(input.package_id) ||
        input.language !== 'en' && input.language !== 'tr') return error(400, 'invalid_input');
    const port = process.env.HISSIYAT_LOCAL_RESEARCH_PORT ?? process.env.HISSIYAT_LOCAL_ANALYSIS_PORT ?? '8000';
    if (!/^[1-9][0-9]{0,4}$/.test(port) || Number(port) > 65535) return error(503, 'model_unavailable');
    const response = await fetch(`http://127.0.0.1:${port}/api/v1/local/interpretation`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Hissiyat-Local-Research': '1'},
      body: buffer.subarray(0, size), cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(160000),
    });
    const raw: unknown = await response.json();
    if (response.ok && raw && typeof raw === 'object' && 'evidence_package' in raw) {
      const evidence = projectEvidencePackage(raw.evidence_package);
      const report = evidence && evidence.package_id === input.package_id && projectAIInterpretation(raw, evidence, input.language);
      if (report) return Response.json({...report, evidence_package: evidence}, {headers: noStore});
    }
    const codes: Record<number, string[]> = {400: ['invalid_input'], 404: ['not_found'], 409: ['evidence_expired'],
      413: ['too_large'], 422: ['unsupported_claim', 'invalid_model_output'], 429: ['busy'],
      503: ['model_unavailable'], 504: ['model_timeout']};
    if (raw && typeof raw === 'object' && 'code' in raw && typeof raw.code === 'string' && codes[response.status]?.includes(raw.code)) {
      return error(response.status, raw.code);
    }
  } catch { /* Keep transport failures and model payloads out of logs. */ }
  return error(503, 'model_unavailable');
}
