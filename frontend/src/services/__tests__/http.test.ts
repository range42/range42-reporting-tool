import { describe, expect, it, vi } from 'vitest'
import { ApiError, apiGet } from '@/services/http'

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
})
