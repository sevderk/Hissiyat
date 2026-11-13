import {isCohort, isSearchInterest, isTextAnalysis} from '@/lib/demo-contract';

function backendOrigin() {
  const url = new URL(process.env.HISSIYAT_DEMO_API_ORIGIN ?? 'http://127.0.0.1:8000');
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ||
      url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('Expected a local demo API origin');
  }
  return url.origin;
}

function error(status: number, code: string) {
  return Response.json({code}, {status, headers: {'Cache-Control': 'no-store'}});
}

export async function GET(request: Request, {params}: {params: Promise<{section: string}>}) {
  const {section} = await params;
  if (section !== 'text-analysis' && section !== 'search-interest') return error(404, 'not_found');
  const query = new URL(request.url).searchParams;
  const cohort = query.get('cohort') ?? 'general';
  if (!isCohort(cohort) || query.getAll('cohort').length > 1 ||
      [...query.keys()].some((key) => section !== 'text-analysis' || key !== 'cohort')) {
    return error(400, 'invalid_request');
  }

  let payload: unknown;
  try {
    const url = new URL('/api/v1/demo/' + section, backendOrigin());
    if (section === 'text-analysis') url.searchParams.set('cohort', cohort);
    const upstream = await fetch(url, {
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(4000)
    });
    if (!upstream.ok) return error(503, 'unavailable');
    try {
      payload = await upstream.json();
    } catch {
      return error(502, 'invalid_contract');
    }
  } catch {
    return error(503, 'unavailable');
  }
  const valid = section === 'text-analysis' ? isTextAnalysis(payload, cohort) : isSearchInterest(payload);
  if (!valid) return error(502, 'invalid_contract');
  return Response.json(payload, {headers: {'Cache-Control': 'no-store'}});
}
