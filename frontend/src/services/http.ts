export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public details: unknown[] = [],
    public traceId?: string,
  ) {
    super(message)
  }
}

interface DataEnvelope<T> {
  data: T
  meta?: unknown
}
interface ErrorEnvelope {
  error: { code: string; message: string; details: unknown[] }
  trace_id?: string
}

export async function apiGet<T>(path: string, token?: string): Promise<T> {
  const res = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  const body = await res.json()
  if (!res.ok) {
    const e = body as ErrorEnvelope
    throw new ApiError(e.error.code, e.error.message, e.error.details, e.trace_id)
  }
  return (body as DataEnvelope<T>).data
}
