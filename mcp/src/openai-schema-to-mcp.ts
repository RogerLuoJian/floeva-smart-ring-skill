import * as z from 'zod/v4';

export const HEALTH_OVERVIEW_TOOL = 'get_health_overview';
const TOOL_NAME = /^[A-Za-z0-9_-]{1,64}$/;

type JsonObject = Record<string, unknown>;

export interface AdaptedTool {
  name: string;
  description: string;
  inputSchema: z.ZodObject<z.ZodRawShape>;
}

function record(value: unknown): JsonObject | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : undefined;
}

function knownKeys(value: JsonObject, allowed: ReadonlySet<string>): void {
  if (Object.keys(value).some((key) => !allowed.has(key))) {
    throw new Error('unsupported schema keyword');
  }
}

function propertySchema(raw: unknown): z.ZodType {
  const schema = record(raw);
  if (!schema || typeof schema.type !== 'string') {
    throw new Error('invalid property schema');
  }
  knownKeys(
    schema,
    new Set([
      'type', 'description', 'enum', 'minimum', 'maximum', 'minLength',
      'maxLength', 'pattern', 'items', 'properties', 'required', 'additionalProperties',
    ]),
  );
  const description = schema.description;
  if (description !== undefined && typeof description !== 'string') {
    throw new Error('invalid schema description');
  }

  let result: z.ZodType;
  if (schema.enum !== undefined) {
    if (!Array.isArray(schema.enum) || schema.enum.length === 0) {
      throw new Error('invalid enum');
    }
    const values = schema.enum;
    if (schema.type === 'string' && values.every((value) => typeof value === 'string')) {
      result = z.enum(values as [string, ...string[]]);
    } else {
      throw new Error('unsupported enum');
    }
  } else {
    switch (schema.type) {
      case 'string': {
        let stringSchema = z.string();
        if (schema.minLength !== undefined) {
          if (!Number.isSafeInteger(schema.minLength) || Number(schema.minLength) < 0) throw new Error('invalid minLength');
          stringSchema = stringSchema.min(Number(schema.minLength));
        }
        if (schema.maxLength !== undefined) {
          if (!Number.isSafeInteger(schema.maxLength) || Number(schema.maxLength) < 0) throw new Error('invalid maxLength');
          stringSchema = stringSchema.max(Number(schema.maxLength));
        }
        if (schema.pattern !== undefined) {
          if (typeof schema.pattern !== 'string' || schema.pattern.length > 256) throw new Error('invalid pattern');
          stringSchema = stringSchema.regex(new RegExp(schema.pattern));
        }
        result = stringSchema;
        break;
      }
      case 'integer':
      case 'number': {
        let numberSchema = schema.type === 'integer' ? z.number().int() : z.number();
        if (schema.minimum !== undefined) {
          if (typeof schema.minimum !== 'number' || !Number.isFinite(schema.minimum)) throw new Error('invalid minimum');
          numberSchema = numberSchema.min(schema.minimum);
        }
        if (schema.maximum !== undefined) {
          if (typeof schema.maximum !== 'number' || !Number.isFinite(schema.maximum)) throw new Error('invalid maximum');
          numberSchema = numberSchema.max(schema.maximum);
        }
        result = numberSchema;
        break;
      }
      case 'boolean':
        result = z.boolean();
        break;
      case 'array':
        if (schema.items === undefined) throw new Error('array items are required');
        result = z.array(propertySchema(schema.items));
        break;
      case 'object':
        result = objectSchema(schema);
        break;
      default:
        throw new Error('unsupported schema type');
    }
  }
  return typeof description === 'string' ? result.describe(description) : result;
}

function objectSchema(schema: JsonObject): z.ZodObject<z.ZodRawShape> {
  if (schema.type !== 'object' || record(schema.properties) === undefined) {
    throw new Error('tool parameters must be an object schema');
  }
  if (schema.additionalProperties !== false) {
    throw new Error('tool parameters must reject additional properties');
  }
  const properties = record(schema.properties) as JsonObject;
  const required = schema.required ?? [];
  if (
    !Array.isArray(required)
    || required.some((item) => typeof item !== 'string')
    || new Set(required).size !== required.length
  ) {
    throw new Error('invalid required fields');
  }
  const requiredNames = new Set(required as string[]);
  if ([...requiredNames].some((name) => !(name in properties))) {
    throw new Error('required field is missing from properties');
  }
  const shape: Record<string, z.ZodType> = {};
  for (const [name, rawProperty] of Object.entries(properties)) {
    if (!TOOL_NAME.test(name)) throw new Error('invalid property name');
    const parsed = propertySchema(rawProperty);
    shape[name] = requiredNames.has(name) ? parsed : parsed.optional();
  }
  return z.object(shape).strict();
}

export function adaptOpenAiTools(rawTools: unknown): AdaptedTool[] {
  if (!Array.isArray(rawTools)) {
    throw new Error('tool list must be an array');
  }
  const names = new Set<string>([HEALTH_OVERVIEW_TOOL]);
  return rawTools.map((rawTool) => {
    const tool = record(rawTool);
    const fn = record(tool?.function);
    if (tool?.type !== 'function' || !fn) throw new Error('invalid tool definition');
    const { name, description, parameters } = fn;
    if (typeof name !== 'string' || !TOOL_NAME.test(name) || names.has(name)) {
      throw new Error('invalid or duplicate tool name');
    }
    if (typeof description !== 'string' || description.length === 0 || description.length > 1000) {
      throw new Error('invalid tool description');
    }
    const parameterObject = record(parameters);
    if (!parameterObject) throw new Error('invalid tool parameters');
    knownKeys(parameterObject, new Set(['type', 'properties', 'required', 'additionalProperties']));
    const inputSchema = objectSchema(parameterObject);
    names.add(name);
    return { name, description, inputSchema };
  });
}
