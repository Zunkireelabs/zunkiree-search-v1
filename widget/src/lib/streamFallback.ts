// P3 Part B keep-live fallback (brief D3), tightened per roadmap review
// (session 52): the widget must fall back to the direct Zunkiree path
// ONLY when the configured chat_stream_url (Orca) is genuinely down —
// a fetch rejection (network failure) or an HTTP 5xx. A kill-switch
// SSE {"type":"error"} frame or any 4xx response is a final answer from
// a service that IS reachable and must not be retried, or an Orca kill
// switch / spend cap would silently not apply to chat.

/** Marks an error as eligible for the one-shot direct-path retry. */
export class RetryableStreamError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'RetryableStreamError'
  }
}

/**
 * Runs fetch() and reclassifies a rejection (network failure — e.g. DNS
 * failure, connection refused, CORS block surfaced as an opaque
 * TypeError) as retryable, since the browser never got a response at
 * all.
 */
export async function fetchStream(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init)
  } catch (err) {
    throw new RetryableStreamError(err instanceof Error ? err.message : 'Network error')
  }
}

/**
 * Throws when `response` is not ok. 5xx is retryable (the service is
 * down); any 4xx (including a kill-switch 403) is final — the service
 * answered and said no.
 */
export async function assertOkOrThrow(response: Response): Promise<void> {
  if (response.ok) return
  const data = await response.json().catch(() => ({}))
  const message = data.detail?.message || 'Failed to get answer'
  if (response.status >= 500) throw new RetryableStreamError(message)
  throw new Error(message)
}

/**
 * Decides whether the caught error should trigger the one-shot retry
 * against the direct Zunkiree path.
 *
 * Never retries once a token has reached the visitor (would duplicate
 * content), never retries when there's nowhere else to go (already on
 * the direct path), and never retries a non-`RetryableStreamError` —
 * that covers both a 4xx response and an SSE `{"type":"error"}` frame,
 * which is thrown as a plain `Error` by the caller.
 */
export function shouldRetryDirect(
  err: unknown,
  firstTokenReceived: boolean,
  alreadyDirect: boolean,
): boolean {
  if (firstTokenReceived || alreadyDirect) return false
  return err instanceof RetryableStreamError
}
