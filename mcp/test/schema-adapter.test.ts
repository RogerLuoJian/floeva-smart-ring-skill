import { describe, expect, it } from 'vitest';

import { adaptOpenAiTools } from '../src/openai-schema-to-mcp.js';

function definition(parameters: Record<string, unknown>, name = 'get_sleep_data') {
  return {
    type: 'function',
    function: {
      name,
      description: 'Get sleep data.',
      parameters,
    },
  };
}

describe('adaptOpenAiTools', () => {
  it('adapts object schemas and preserves required versus optional fields', () => {
    const [tool] = adaptOpenAiTools([
      definition({
        type: 'object',
        properties: {
          days: { type: 'integer', description: 'Days', minimum: 1, maximum: 60 },
          language: { type: 'string', enum: ['zh', 'en'] },
        },
        required: ['days'],
        additionalProperties: false,
      }),
    ]);

    expect(tool?.inputSchema.safeParse({ days: 7 }).success).toBe(true);
    expect(tool?.inputSchema.safeParse({ days: 7, language: 'en' }).success).toBe(true);
    expect(tool?.inputSchema.safeParse({}).success).toBe(false);
    expect(tool?.inputSchema.safeParse({ days: 7, unexpected: true }).success).toBe(false);
    expect(tool?.inputSchema.safeParse({ days: 61 }).success).toBe(false);
  });

  it('accepts a strict empty property object', () => {
    const [tool] = adaptOpenAiTools([
      definition({ type: 'object', properties: {}, required: [], additionalProperties: false }, 'get_baseline'),
    ]);
    expect(tool?.inputSchema.safeParse({}).success).toBe(true);
    expect(tool?.inputSchema.safeParse({ extra: 1 }).success).toBe(false);
  });

  it.each([
    undefined,
    {},
    [definition({ type: 'array', properties: {}, required: [], additionalProperties: false })],
    [definition({ type: 'object', properties: {}, required: [], additionalProperties: true })],
    [definition({ type: 'object', properties: { value: { type: 'null' } }, required: [], additionalProperties: false })],
    [definition({ type: 'object', properties: {}, required: ['missing'], additionalProperties: false })],
  ])('fails closed for malformed schema %#', (value) => {
    expect(() => adaptOpenAiTools(value)).toThrow();
  });

  it('rejects duplicate names and the reserved overview name', () => {
    const empty = { type: 'object', properties: {}, required: [], additionalProperties: false };
    expect(() => adaptOpenAiTools([definition(empty), definition(empty)])).toThrow();
    expect(() => adaptOpenAiTools([definition(empty, 'get_health_overview')])).toThrow();
  });
});
