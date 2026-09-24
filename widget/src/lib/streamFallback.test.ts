import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchStream, assertOkOrThrow, shouldRetryDirect, RetryableStreamError } from './streamFallback'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status })
}

describe('assertOkOrThrow', () => {
  it('does not throw for an ok response', async () => {
    await expect(assertOkOrThrow(jsonResponse(200, {}))).resolves.toBeUndefined()
  })

  it('throws a plain (non-retryable) Error on a 403 kill-switch response', async () => {
    const response = jsonResponse(403, { detail: { message: 'tenant kill-switched' } })
    await expect(assertOkOrThrow(response)).rejects.toThrow('tenant kill-switched')
    await expect(assertOkOrThrow(jsonResponse(403, {}))).rejects.not.toBeInstanceOf(RetryableStreamError)
  })

  it('throws a plain (non-retryable) Error on any other 4xx', async () => {
    await expect(assertOkOrThrow(jsonResponse(404, {}))).rejects.not.toBeInstanceOf(RetryableStreamError)
  })

  it('throws a RetryableStreamError on a 502', async () => {
    const response = jsonResponse(502, { detail: { message: 'bad gateway' } })
    await expect(assertOkOrThrow(response)).rejects.toBeInstanceOf(RetryableStreamError)
  })

  it('throws a RetryableStreamError on any 5xx', async () => {
    await expect(assertOkOrThrow(jsonResponse(500, {}))).rejects.toBeInstanceOf(RetryableStreamError)
  })
})

describe('fetchStream', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reclassifies a fetch() rejection (network failure) as a RetryableStreamError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(fetchStream('https://orca.example/stream', {})).rejects.toBeInstanceOf(RetryableStreamError)
  })

  it('passes through a resolved response untouched', async () => {
    const response = jsonResponse(200, {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    await expect(fetchStream('https://orca.example/stream', {})).resolves.toBe(response)
  })
})

describe('shouldRetryDirect', () => {
  it('retries on a RetryableStreamError (5xx or network failure) before the first token', () => {
    expect(shouldRetryDirect(new RetryableStreamError('bad gateway'), false, false)).toBe(true)
  })

  it('does not retry a kill-switch SSE error frame (a plain Error, not a 5xx)', () => {
    // The widget throws SSE {"type":"error"} frames as a plain Error —
    // see runStream's `event.type === 'error'` branch in Widget.tsx.
    expect(shouldRetryDirect(new Error('kill switch active'), false, false)).toBe(false)
  })

  it('does not retry a 403 (a plain Error, not a RetryableStreamError)', () => {
    expect(shouldRetryDirect(new Error('tenant kill-switched'), false, false)).toBe(false)
  })

  it('retries a 502 (RetryableStreamError)', () => {
    expect(shouldRetryDirect(new RetryableStreamError('bad gateway'), false, false)).toBe(true)
  })

  it('retries a network failure (RetryableStreamError)', () => {
    expect(shouldRetryDirect(new RetryableStreamError('Failed to fetch'), false, false)).toBe(true)
  })

  it('never retries once a token has been shown, even for a retryable error', () => {
    expect(shouldRetryDirect(new RetryableStreamError('bad gateway'), true, false)).toBe(false)
  })

  it('never retries when already on the direct path', () => {
    expect(shouldRetryDirect(new RetryableStreamError('bad gateway'), false, true)).toBe(false)
  })
})
