export type SafeErrorCode =
  | 'authorization_required'
  | 'rate_limited'
  | 'timeout'
  | 'invalid_response'
  | 'upstream_unavailable'
  | 'invalid_local_state';

const SAFE_MESSAGES: Record<SafeErrorCode, string> = {
  authorization_required: 'Floeva authorization is missing or expired. Reconnect the connector.',
  rate_limited: 'The Floeva daily request limit has been reached. Try again later.',
  timeout: 'The Floeva service did not respond in time.',
  invalid_response: 'Floeva returned an invalid response.',
  upstream_unavailable: 'The Floeva service is temporarily unavailable.',
  invalid_local_state: 'The local Floeva authorization state is invalid.',
};

export class SafeError extends Error {
  readonly code: SafeErrorCode;

  constructor(code: SafeErrorCode) {
    super(SAFE_MESSAGES[code]);
    this.name = 'SafeError';
    this.code = code;
  }
}

export function safeMessage(error: unknown): string {
  return error instanceof SafeError
    ? error.message
    : SAFE_MESSAGES.upstream_unavailable;
}
