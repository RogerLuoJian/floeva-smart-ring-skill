import { Client, InMemoryTransport } from '@modelcontextprotocol/client';
import { describe, expect, it } from 'vitest';

import type { FloevaApi } from '../src/floeva-client.js';
import { adaptOpenAiTools } from '../src/openai-schema-to-mcp.js';
import { SafeError } from '../src/safe-errors.js';
import { buildMcpServer } from '../src/server.js';

function definitions() {
  return adaptOpenAiTools([
    {
      type: 'function',
      function: {
        name: 'get_sleep_data',
        description: 'Get sleep data.',
        parameters: {
          type: 'object',
          properties: { days: { type: 'integer' } },
          required: [],
          additionalProperties: false,
        },
      },
    },
  ]);
}

async function connected(api: FloevaApi) {
  const server = buildMcpServer(api, definitions());
  const client = new Client({ name: 'test-client', version: '1.0.0' });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);
  return { client, server };
}

describe('Floeva MCP server', () => {
  it('lists only discovered tools plus the stable overview and forwards calls', async () => {
    const calls: unknown[] = [];
    const api: FloevaApi = {
      listTools: async () => [],
      executeTool: async (name, args) => {
        calls.push({ name, args });
        return { sleep: true };
      },
      getHealthOverview: async () => ({ overview: true }),
    };
    const { client, server } = await connected(api);
    try {
      const listed = await client.listTools();
      expect(listed.tools.map((tool) => tool.name).sort()).toEqual([
        'get_health_overview',
        'get_sleep_data',
      ]);
      const sleep = await client.callTool({ name: 'get_sleep_data', arguments: { days: 7 } });
      expect(sleep.isError).not.toBe(true);
      expect(calls).toEqual([{ name: 'get_sleep_data', args: { days: 7 } }]);
      const overview = await client.callTool({ name: 'get_health_overview', arguments: {} });
      expect(JSON.stringify(overview)).toContain('overview');
    } finally {
      await client.close();
      await server.close();
    }
  });

  it('rejects unknown tools and invalid arguments before the API call', async () => {
    let executions = 0;
    const api: FloevaApi = {
      listTools: async () => [],
      executeTool: async () => {
        executions += 1;
        return {};
      },
      getHealthOverview: async () => ({}),
    };
    const { client, server } = await connected(api);
    try {
      await expect(client.callTool({ name: 'arbitrary_http', arguments: {} })).rejects.toThrow();
      const invalid = await client.callTool({ name: 'get_sleep_data', arguments: { days: 'seven' } });
      expect(invalid).toMatchObject({ isError: true });
      expect(executions).toBe(0);
    } finally {
      await client.close();
      await server.close();
    }
  });

  it('returns safe MCP errors for Open API failures', async () => {
    const api: FloevaApi = {
      listTools: async () => [],
      executeTool: async () => { throw new SafeError('rate_limited'); },
      getHealthOverview: async () => { throw new Error('secret upstream body'); },
    };
    const { client, server } = await connected(api);
    try {
      const limited = await client.callTool({ name: 'get_sleep_data', arguments: {} });
      expect(limited).toMatchObject({ isError: true });
      expect(JSON.stringify(limited)).toContain('daily request limit');
      const overview = await client.callTool({ name: 'get_health_overview', arguments: {} });
      expect(JSON.stringify(overview)).not.toContain('secret upstream body');
      expect(overview).toMatchObject({ isError: true });
    } finally {
      await client.close();
      await server.close();
    }
  });
});
