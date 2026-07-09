import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  registerUnauthorizedHandler,
} from '@/services/http'

describe('apiGet', () => {
  it('unwraps the data envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ data: { app_name: 'X' } }), { status: 200 })),
    )
    const data = await apiGet<{ app_name: string }>('/api/v1/config')
    expect(data.app_name).toBe('X')
  })

  it('throws ApiError with code + trace_id on error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ error: { code: 'X', message: 'bad', details: [] }, trace_id: 't1' }),
            { status: 400 },
          ),
      ),
    )
    await expect(apiGet('/api/v1/x')).rejects.toMatchObject({
      code: 'X',
      traceId: 't1',
    } as ApiError)
  })

  it('throws ApiError on a non-JSON response body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response('<html>502 Bad Gateway</html>', {
            status: 502,
            statusText: 'Bad Gateway',
            headers: { 'content-type': 'text/html' },
          }),
      ),
    )
    await expect(apiGet('/api/v1/x')).rejects.toMatchObject({
      code: 'NON_JSON_RESPONSE',
    } as ApiError)
  })
})

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('http write verbs', () => {
  beforeEach(() => {
    registerUnauthorizedHandler(() => {})
  })

  it('apiPost sends JSON body + bearer token and unwraps data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, { data: { id: 'r1' } }))
    vi.stubGlobal('fetch', fetchMock)
    const out = await apiPost<{ id: string }>('/api/v1/roles', { role_key: 'x' }, 'tok')
    expect(out).toEqual({ id: 'r1' })
    const [path, init] = fetchMock.mock.calls[0]!
    expect(path).toBe('/api/v1/roles')
    expect(init.method).toBe('POST')
    expect(init.headers.Authorization).toBe('Bearer tok')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual({ role_key: 'x' })
  })

  it('apiDelete returns void on 204 (no body)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(apiDelete('/api/v1/roles/r1', 'tok')).resolves.toBeUndefined()
    expect(fetchMock.mock.calls[0]![1].method).toBe('DELETE')
  })

  it('apiPatch throws ApiError on an error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(409, { error: { code: 'HTTP_ERROR', message: 'in use', details: [] } }),
        ),
    )
    await expect(apiPatch('/api/v1/roles/r1', {}, 'tok')).rejects.toMatchObject({
      code: 'HTTP_ERROR',
      message: 'in use',
    })
    await expect(apiPatch('/api/v1/roles/r1', {}, 'tok')).rejects.toBeInstanceOf(ApiError)
  })

  it('invokes the unauthorized handler on a 401', async () => {
    const onUnauth = vi.fn()
    registerUnauthorizedHandler(onUnauth)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(401, {
          error: { code: 'HTTP_ERROR', message: 'session invalid', details: [] },
        }),
      ),
    )
    await expect(apiGet('/api/v1/auth/me', 'tok')).rejects.toBeInstanceOf(ApiError)
    expect(onUnauth).toHaveBeenCalledOnce()
  })
})
