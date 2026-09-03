import { describe, expect, it, vi } from 'vitest';

import type { WorkBuddyCredential } from '../src/credential-store.js';
import { WORKBUDDY_BASE_URL, WORKBUDDY_CLIENT_ID } from '../src/credential-store.js';
import { FloevaClient } from '../src/floeva-client.js';
import { SafeError } from '../src/safe-errors.js';

const TOKEN = 'fv_sk_0123456789abcdefghijklmnopqrstuv';
const credential: WorkBuddyCredential = {
  accessToken: TOKEN,
  baseUrl: WORKBUDDY_BASE_URL,
  clientId: WORKBUDDY_CLIENT_ID,
  clientInstanceId: '01234567-89ab-4def-8123-456789abcdef',
  expiresAt: 10_000,
  region: 'cn',
};

function jsonResponse(body: unknown, status = 200, headers?: HeadersInit): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

describe('FloevaClient', () => {
  it('injects authorization only into fixed HTTPS endpoints and forwards validated calls', async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ code: 200, data: { tools: [] } }))
      .mockResolvedValueOnce(jsonResponse({ code: 200, data: { ok: true } }))
      .mockResolvedValueOnce(jsonResponse({ code: 200, data: { overview: true } }));
    const client = new FloevaClient(credential, { fetchImpl: fetchMock });

    await expect(client.listTools()).resolves.toEqual([]);
    await expect(client.executeTool('get_sleep_data', { days: 7 })).resolves.toEqual({ ok: true });
    await expect(client.getHealthOverview()).resolves.toEqual({ overview: true });

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      `${WORKBUDDY_BASE_URL}/open/v1/tool/list`,
      `${WORKBUDDY_BASE_URL}/open/v1/tool/execute`,
      `${WORKBUDDY_BASE_URL}/open/v1/health/overview`,
    ]);
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init?.headers).get('Authorization')).toBe(`Bearer ${TOKEN}`);
      expect(init?.redirect).toBe('error');
    }
    expect(fetchMock.mock.calls[1]?.[1]?.body).toBe(
      JSON.stringify({ toolName: 'get_sleep_data', arguments: { days: 7 } }),
    );
  });

  it('uses a short in-process discovery cache and never caches a failed discovery', async () => {
    let now = 1_000;
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ code: 200, data: { tools: [{ type: 'function' }] } }))
      .mockResolvedValueOnce(jsonResponse({ code: 200, data: { tools: [] } }));
    const client = new FloevaClient(credential, { fetchImpl: fetchMock, nowMs: () => now });

    await client.listTools();
    await client.listTools();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    now += 31_000;
    await client.listTools();
    expect(fetchMock).toHaveBeenCalledTimes(2);

    const failedFetch = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({}, 401))
      .mockResolvedValueOnce(jsonResponse({ code: 200, data: { tools: [] } }));
    const retrying = new FloevaClient(credential, { fetchImpl: failedFetch });
    await expect(retrying.listTools()).rejects.toMatchObject({ code: 'authorization_required' });
    await expect(retrying.listTools()).resolves.toEqual([]);
    expect(failedFetch).toHaveBeenCalledTimes(2);
  });

  it.each([
    [401, 'authorization_required'],
    [429, 'rate_limited'],
    [500, 'upstream_unavailable'],
  ])('maps HTTP %i to safe error %s', async (status, code) => {
    const client = new FloevaClient(credential, {
      fetchImpl: vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({}, status)),
    });
    await expect(client.getHealthOverview()).rejects.toMatchObject({ code });
  });

  it('enforces timeout and maximum response size without leaking secrets', async () => {
    const waitingFetch = vi.fn<typeof fetch>((_url, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    }));
    const timeoutClient = new FloevaClient(credential, { fetchImpl: waitingFetch, timeoutMs: 1 });
    await expect(timeoutClient.getHealthOverview()).rejects.toMatchObject({ code: 'timeout' });

    const largeClient = new FloevaClient(credential, {
      fetchImpl: vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse({ code: 200, data: {} }, 200, { 'content-length': '2000' }),
      ),
      maxResponseBytes: 100,
    });
    let message = '';
    try {
      await largeClient.getHealthOverview();
    } catch (error) {
      expect(error).toBeInstanceOf(SafeError);
      message = String(error);
    }
    expect(message).not.toContain(TOKEN);
    expect(message).not.toContain(credential.clientInstanceId);
  });

  it('maps malformed UTF-8 responses to a safe error', async () => {
    const client = new FloevaClient(credential, {
      fetchImpl: vi.fn<typeof fetch>().mockResolvedValue(
        new Response(new Uint8Array([0xff]), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    });

    await expect(client.getHealthOverview()).rejects.toMatchObject({ code: 'invalid_response' });
  });
});
