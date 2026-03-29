/**
 * Cloudflare Worker: OpenClaw Status API
 *
 * Serves live OpenClaw agent swarm data from KV storage.
 * Deploy as a Worker (not Pages Function) at andremacedo.com/api/status
 * or api.andremacedo.com.
 *
 * KV Namespace binding: OPENCLAW_STATUS
 * Key: "latest" — JSON payload pushed by push-status.sh every 5 minutes
 */

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Content-Type': 'application/json',
  'Cache-Control': 'public, max-age=60',
};

const FALLBACK_PAYLOAD = {
  timestamp: new Date().toISOString(),
  agents: [
    {
      id: 'andremacedo-creative',
      status: 'active',
      last_action: 'Evolved site to new generation',
      last_active: new Date().toISOString(),
      model: 'claude-opus-4-6',
      tokens_today: 0,
    },
  ],
  system: {
    total_agents: 25,
    active_now: 0,
    total_tokens_today: 0,
    uptime_hours: 0,
  },
  gold_price: null,
  mood: 'unknown',
};

export default {
  async fetch(request, env) {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (request.method !== 'GET') {
      return new Response(JSON.stringify({ error: 'Method not allowed' }), {
        status: 405,
        headers: CORS_HEADERS,
      });
    }

    try {
      const data = await env.OPENCLAW_STATUS.get('latest', { type: 'json' });

      if (data) {
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: CORS_HEADERS,
        });
      }

      // KV empty — return fallback
      return new Response(JSON.stringify(FALLBACK_PAYLOAD), {
        status: 200,
        headers: { ...CORS_HEADERS, 'X-Data-Source': 'fallback' },
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: 'Internal error', detail: err.message }),
        { status: 500, headers: CORS_HEADERS }
      );
    }
  },
};
