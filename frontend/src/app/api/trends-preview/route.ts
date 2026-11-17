import {isTrendsPreview, isTrendsPreviewEnabled} from '@/lib/trends-research';

const headers = {'Cache-Control': 'no-store'};
const notFound = () => Response.json({code: 'not_found'}, {status: 404, headers});

export async function GET(request: Request) {
  const host = request.headers.get('host') ?? '';
  const origin = request.headers.get('origin');
  const site = request.headers.get('sec-fetch-site');
  if (!isTrendsPreviewEnabled(process.env.NODE_ENV, process.env.HISSIYAT_TRENDS_PREVIEW) ||
      !/^127\.0\.0\.1(?::[0-9]{1,5})?$/.test(host) || (origin !== null && origin !== `http://${host}`) ||
      (site !== null && site !== 'same-origin') || new URL(request.url).search) return notFound();
  try {
    const result = await fetch('http://127.0.0.1:8058/api/v1/local/trends-preview', {
      headers: {'X-Hissiyat-Trends-Preview': '1'}, redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(4000)
    });
    if (result.status === 404) return notFound();
    const data: unknown = result.ok ? await result.json() : null;
    if (isTrendsPreview(data)) return Response.json(data, {headers});
  } catch {
    // Local transport and parsing errors have a fixed response.
  }
  return Response.json({code: 'unavailable'}, {status: 503, headers});
}
