export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public details: unknown[] = [],
    public traceId?: string,
    public status?: number,
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

let unauthorizedHandler: () => void = () => {}

/** Register a callback fired whenever any request returns 401 (auth store clears + redirects). */
export function registerUnauthorizedHandler(fn: () => void): void {
  unauthorizedHandler = fn
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  token?: string,
): Promise<T> {
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return unwrap<T>(res)
}

async function unwrap<T>(res: Response): Promise<T> {
  if (res.status === 401) unauthorizedHandler()
  if (res.status === 204) return undefined as T
  let parsed: unknown
  try {
    parsed = await res.json()
  } catch {
    throw new ApiError('NON_JSON_RESPONSE', res.statusText || `HTTP ${res.status}`)
  }
  if (!res.ok) {
    const e = parsed as ErrorEnvelope
    throw new ApiError(e.error.code, e.error.message, e.error.details, e.trace_id, res.status)
  }
  return (parsed as DataEnvelope<T>).data
}

/** Multipart upload — no explicit Content-Type so the browser sets the boundary. */
export async function apiUpload<T>(path: string, file: File, token?: string): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(path, { method: 'POST', headers, body: form })
  return unwrap<T>(res)
}

/** Authenticated binary GET (bearer header — plain <img>/<a> tags cannot send it). */
export async function apiGetBlob(path: string, token?: string): Promise<Blob> {
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(path, { method: 'GET', headers })
  if (res.status === 401) unauthorizedHandler()
  if (!res.ok)
    throw new ApiError(
      'DOWNLOAD_FAILED',
      res.statusText || `HTTP ${res.status}`,
      [],
      undefined,
      res.status,
    )
  return res.blob()
}

export function apiGet<T>(path: string, token?: string): Promise<T> {
  return request<T>('GET', path, undefined, token)
}
export function apiPost<T>(path: string, body: unknown, token?: string): Promise<T> {
  return request<T>('POST', path, body, token)
}
export function apiPatch<T>(path: string, body: unknown, token?: string): Promise<T> {
  return request<T>('PATCH', path, body, token)
}
export function apiDelete(path: string, token?: string): Promise<void> {
  return request<void>('DELETE', path, undefined, token)
}
