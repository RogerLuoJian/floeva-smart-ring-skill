import { fileURLToPath } from 'node:url';

import { McpServer } from '@modelcontextprotocol/server';
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import * as z from 'zod/v4';

import { loadWorkBuddyCredential } from './credential-store.js';
import { FloevaClient, type FloevaApi } from './floeva-client.js';
import {
  adaptOpenAiTools,
  HEALTH_OVERVIEW_TOOL,
  type AdaptedTool,
} from './openai-schema-to-mcp.js';
import { safeMessage } from './safe-errors.js';

export async function discoverTools(api: FloevaApi): Promise<AdaptedTool[]> {
  return adaptOpenAiTools(await api.listTools());
}

export function buildMcpServer(api: FloevaApi, tools: AdaptedTool[]): McpServer {
  const server = new McpServer(
    { name: 'floeva-workbuddy-cn', version: '0.1.0' },
    {
      instructions:
        'Read-only Floeva wearable health data. Preserve missing values and do not make medical diagnoses.',
    },
  );

  for (const tool of tools) {
    server.registerTool(
      tool.name,
      { description: tool.description, inputSchema: tool.inputSchema },
      async (args) => toolResult(() => api.executeTool(tool.name, args as Record<string, unknown>)),
    );
  }

  server.registerTool(
    HEALTH_OVERVIEW_TOOL,
    {
      description: 'Get the latest Floeva health overview with recent sleep, heart, activity, and baseline data.',
      inputSchema: z.object({}).strict(),
    },
    async () => toolResult(() => api.getHealthOverview()),
  );
  return server;
}

async function toolResult(operation: () => Promise<unknown>) {
  try {
    const result = await operation();
    return { content: [{ type: 'text' as const, text: JSON.stringify(result) }] };
  } catch (error) {
    return {
      isError: true,
      content: [{ type: 'text' as const, text: safeMessage(error) }],
    };
  }
}

export async function main(): Promise<void> {
  const credential = loadWorkBuddyCredential();
  const api = new FloevaClient(credential);
  const tools = await discoverTools(api);
  serveStdio(() => buildMcpServer(api, tools));
  console.error('Floeva MCP server running on stdio');
}

const launchedDirectly = process.argv[1] !== undefined
  && fileURLToPath(import.meta.url) === process.argv[1];
if (launchedDirectly) {
  main().catch(() => {
    console.error('Unable to start the Floeva MCP server. Reconnect the connector.');
    process.exitCode = 1;
  });
}
