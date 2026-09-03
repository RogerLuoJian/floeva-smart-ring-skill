import {
  closeSync,
  constants,
  fstatSync,
  lstatSync,
  openSync,
  readFileSync,
} from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

import { SafeError } from './safe-errors.js';

export const WORKBUDDY_CLIENT_ID = 'floeva-workbuddy-cn';
export const WORKBUDDY_BASE_URL = 'https://server.floeva.cn/ring/api';
const MAX_STATE_BYTES = 16 * 1024;
const INSTANCE_PATTERN = /^[A-Za-z0-9_-]{16,128}$/;
const TOKEN_PATTERN = /^fv_sk_[A-Za-z0-9]{32}$/;

export interface WorkBuddyCredential {
  accessToken: string;
  baseUrl: typeof WORKBUDDY_BASE_URL;
  clientId: typeof WORKBUDDY_CLIENT_ID;
  clientInstanceId: string;
  expiresAt: number;
  region: 'cn';
}

export function defaultStateRoot(): string {
  return join(homedir(), '.floeva', 'workbuddy', WORKBUDDY_CLIENT_ID);
}

function readPrivateJson(path: string): Record<string, unknown> {
  let descriptor: number | undefined;
  try {
    const entry = lstatSync(path);
    if (!entry.isFile() || entry.isSymbolicLink()) {
      throw new SafeError('invalid_local_state');
    }
    if (process.platform !== 'win32' && (entry.mode & 0o077) !== 0) {
      throw new SafeError('invalid_local_state');
    }
    const noFollow = 'O_NOFOLLOW' in constants ? constants.O_NOFOLLOW : 0;
    descriptor = openSync(path, constants.O_RDONLY | noFollow);
    const opened = fstatSync(descriptor);
    if (!opened.isFile() || opened.size <= 0 || opened.size > MAX_STATE_BYTES) {
      throw new SafeError('invalid_local_state');
    }
    const parsed: unknown = JSON.parse(readFileSync(descriptor, 'utf8'));
    if (!isRecord(parsed)) {
      throw new SafeError('invalid_local_state');
    }
    return parsed;
  } catch (error) {
    if (error instanceof SafeError) {
      throw error;
    }
    throw new SafeError('invalid_local_state');
  } finally {
    if (descriptor !== undefined) {
      closeSync(descriptor);
    }
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function loadWorkBuddyCredential(
  stateRoot: string = defaultStateRoot(),
  nowSeconds: number = Math.floor(Date.now() / 1000),
): WorkBuddyCredential {
  const identity = readPrivateJson(join(stateRoot, 'instance.json'));
  const credential = readPrivateJson(join(stateRoot, 'credential.json'));
  const instanceId = identity.client_instance_id;
  const expiresAt = credential.expires_at;

  if (
    identity.version !== 1
    || identity.client_id !== WORKBUDDY_CLIENT_ID
    || typeof instanceId !== 'string'
    || !INSTANCE_PATTERN.test(instanceId)
    || credential.auth_mode !== 'device_authorization'
    || credential.client_id !== WORKBUDDY_CLIENT_ID
    || credential.client_instance_id !== instanceId
    || credential.base_url !== WORKBUDDY_BASE_URL
    || credential.region !== 'cn'
    || typeof credential.access_token !== 'string'
    || !TOKEN_PATTERN.test(credential.access_token)
    || typeof expiresAt !== 'number'
    || !Number.isSafeInteger(expiresAt)
    || expiresAt <= nowSeconds + 60
  ) {
    throw new SafeError('invalid_local_state');
  }

  return {
    accessToken: credential.access_token,
    baseUrl: WORKBUDDY_BASE_URL,
    clientId: WORKBUDDY_CLIENT_ID,
    clientInstanceId: instanceId,
    expiresAt,
    region: 'cn',
  };
}
