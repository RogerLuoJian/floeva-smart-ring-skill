import { chmodSync, mkdtempSync, readFileSync, symlinkSync, unlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import {
  loadWorkBuddyCredential,
  WORKBUDDY_BASE_URL,
  WORKBUDDY_CLIENT_ID,
} from '../src/credential-store.js';

const roots: string[] = [];
const INSTANCE_A = '01234567-89ab-4def-8123-456789abcdef';
const TOKEN = 'fv_sk_0123456789abcdefghijklmnopqrstuv';

function fixture(instanceId = INSTANCE_A, credentialInstance = instanceId): string {
  const root = mkdtempSync(join(tmpdir(), 'floeva-mcp-state-'));
  roots.push(root);
  writePrivate(join(root, 'instance.json'), {
    version: 1,
    client_id: WORKBUDDY_CLIENT_ID,
    client_instance_id: instanceId,
    created_at: 1000,
  });
  writePrivate(join(root, 'credential.json'), {
    access_token: TOKEN,
    auth_mode: 'device_authorization',
    base_url: WORKBUDDY_BASE_URL,
    client_id: WORKBUDDY_CLIENT_ID,
    client_instance_id: credentialInstance,
    expires_at: 10_000,
    region: 'cn',
  });
  return root;
}

function writePrivate(path: string, payload: unknown): void {
  writeFileSync(path, JSON.stringify(payload), { mode: 0o600 });
  chmodSync(path, 0o600);
}

afterEach(async () => {
  const { rm } = await import('node:fs/promises');
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('loadWorkBuddyCredential', () => {
  it('loads a private credential bound to the current installation', () => {
    const credential = loadWorkBuddyCredential(fixture(), 1_000);
    expect(credential).toMatchObject({
      accessToken: TOKEN,
      clientId: WORKBUDDY_CLIENT_ID,
      clientInstanceId: INSTANCE_A,
      baseUrl: WORKBUDDY_BASE_URL,
      region: 'cn',
    });
  });

  it('rejects instance mismatch, expiry, unsafe permissions, and symlinks', () => {
    expect(() => loadWorkBuddyCredential(fixture(INSTANCE_A, 'fedcba98-7654-4abc-9123-456789abcdef'), 1_000))
      .toThrow('local Floeva authorization state is invalid');

    expect(() => loadWorkBuddyCredential(fixture(), 9_950))
      .toThrow('local Floeva authorization state is invalid');

    const unsafe = fixture();
    chmodSync(join(unsafe, 'credential.json'), 0o644);
    expect(() => loadWorkBuddyCredential(unsafe, 1_000))
      .toThrow('local Floeva authorization state is invalid');

    if (process.platform !== 'win32') {
      const linked = fixture();
      const target = join(linked, 'credential-target.json');
      writePrivate(target, JSON.parse(readFileSync(join(linked, 'credential.json'), 'utf8')));
      unlinkSync(join(linked, 'credential.json'));
      symlinkSync(target, join(linked, 'credential.json'));
      expect(() => loadWorkBuddyCredential(linked, 1_000))
        .toThrow('local Floeva authorization state is invalid');
    }
  });

  it('never includes state paths, tokens, or instance ids in errors', () => {
    const root = fixture(INSTANCE_A, 'mismatched-instance-value');
    let message = '';
    try {
      loadWorkBuddyCredential(root, 1_000);
    } catch (error) {
      message = String(error);
    }
    expect(message).not.toContain(root);
    expect(message).not.toContain(TOKEN);
    expect(message).not.toContain(INSTANCE_A);
  });
});
