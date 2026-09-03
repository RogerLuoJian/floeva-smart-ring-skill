import type { WorkBuddyCredential } from './credential-store.js';
import { WORKBUDDY_BASE_URL } from './credential-store.js';
import { SafeError } from './safe-errors.js';

const MAX_RESPONSE_BYTES = 1024 * 1024;

export interface FloevaApi {
  listTools(): Promise<unknown>;
  executeTool(name: string, args: Record<string, unknown>): Promise<unknown>;
  getHealthOverview(): Promise<unknown>;
}

export interface FloevaClientOptions {
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  maxResponseBytes?: number;
  cacheTtlMs?: number;
  nowMs?: () => number;
}

export class FloevaClient implements FloevaApi {
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;
  private readonly maxResponseBytes: number;
  private readonly cacheTtlMs: number;
  private readonly nowMs: () => number;
  private cachedTools?: { expiresAt: number; value: unknown };

  constructor(
    private readonly credential: WorkBuddyCredential,
    options: FloevaClientOptions = {},
  ) {
    if (credential.baseUrl !== WORKBUDDY_BASE_URL) {
      throw new SafeError('invalid_local_state');
    }
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.maxResponseBytes = options.maxResponseBytes ?? MAX_RESPONSE_BYTES;
    this.cacheTtlMs = options.cacheTtlMs ?? 30_000;
    this.nowMs = options.nowMs ?? Date.now;
  }

  async listTools(): Promise<unknown> {
    if (this.cachedTools && this.cachedTools.expiresAt > this.nowMs()) {
      return this.cachedTools.value;
    }
    const response = await this.request('/open/v1/tool/list', 'GET');
    const data = response.data;
    if (!isRecord(data) || !Array.isArray(data.tools)) {
      throw new SafeError('invalid_response');
    }
    this.cachedTools = { expiresAt: this.nowMs() + this.cacheTtlMs, value: data.tools };
    return data.tools;
  }

  async executeTool(name: string, args: Record<string, unknown>): Promise<unknown> {
    const response = await this.request('/open/v1/tool/execute', 'POST', {
      toolName: name,
      arguments: args,
    });
    return response.data;
  }

  async getHealthOverview(): Promise<unknown> {
    const response = await this.request('/open/v1/health/overview', 'GET');
    return response.data;
  }

  private async request(
    path: '/open/v1/tool/list' | '/open/v1/tool/execute' | '/open/v1/health/overview',
    method: 'GET' | 'POST',
    body?: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(`${WORKBUDDY_BASE_URL}${path}`, {
        method,
        redirect: 'error',
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${this.credential.accessToken}`,
          ...(body ? { 'Content-Type': 'application/json' } : {}),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (response.status === 401) throw new SafeError('authorization_required');
      if (response.status === 429) throw new SafeError('rate_limited');
      if (response.status >= 500) throw new SafeError('upstream_unavailable');
      if (!response.ok) throw new SafeError('invalid_response');
      const raw = await readBoundedBody(response, this.maxResponseBytes);
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        throw new SafeError('invalid_response');
      }
      if (!isRecord(parsed) || parsed.code !== 200 || !('data' in parsed)) {
        throw new SafeError('invalid_response');
      }
      return parsed;
    } catch (error) {
      if (error instanceof SafeError) throw error;
      if (controller.signal.aborted) throw new SafeError('timeout');
      throw new SafeError('upstream_unavailable');
    } finally {
      clearTimeout(timer);
    }
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function readBoundedBody(response: Response, maximum: number): Promise<string> {
  const declared = response.headers.get('content-length');
  if (declared !== null && Number(declared) > maximum) {
    throw new SafeError('invalid_response');
  }
  if (!response.body) throw new SafeError('invalid_response');
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maximum) {
      await reader.cancel();
      throw new SafeError('invalid_response');
    }
    chunks.push(value);
  }
  const joined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    joined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(joined);
  } catch {
    throw new SafeError('invalid_response');
  }
}
