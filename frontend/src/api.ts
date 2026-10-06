export type Role = 'customer' | 'agent'
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  constructor(status: number, code: string) {
    super(code)
    this.status = status
    this.code = code
  }
}
export type RequestOptions = {
  method?: 'GET' | 'POST'
  body?: unknown
  key?: string
  signal?: AbortSignal
}
export class Api {
  private token = ''
  private generation = 0
  private readonly expired: () => void
  private readonly transport: typeof fetch
  constructor(
    expired: () => void,
    transport: typeof fetch = (...args) => fetch(...args),
  ) {
    this.expired = expired
    this.transport = transport
  }
  authenticate(token: string) {
    this.token = token
    this.generation++
  }
  clear() {
    this.token = ''
    this.generation++
  }
  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const generation = this.generation
    // Revocation must report its result after local logout clears the bearer.
    const revocation = options.method === 'POST' &&
      (path === '/auth/logout' || path === '/agent/auth/logout')
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (this.token) headers.Authorization = `Bearer ${this.token}`
    if (options.body !== undefined) headers['Content-Type'] = 'application/json'
    if (options.key) headers['Idempotency-Key'] = options.key
    let response: Response
    try {
      response = await this.transport(`/api${path}`, {
        method: options.method ?? 'GET',
        headers,
        credentials: 'omit',
        cache: 'no-store',
        ...(options.body !== undefined
          ? { body: JSON.stringify(options.body) }
          : {}),
        signal: options.signal,
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError')
        throw error
      throw new ApiError(0, 'network_error')
    }
    if (options.signal?.aborted)
      throw new DOMException('Request cancelled', 'AbortError')
    if (generation !== this.generation && !revocation)
      throw new DOMException('Stale session', 'AbortError')
    if (response.status === 401 && this.token && generation === this.generation) {
      this.clear()
      this.expired()
    }
    if (!response.ok) {
      // Do not display arbitrary server text or reflect submitted credentials.
      throw new ApiError(response.status, `http_${response.status}`)
    }
    let data: T
    try {
      data = (await response.json()) as T
    } catch {
      throw new ApiError(502, 'invalid_response')
    }
    if ((!revocation && generation !== this.generation) || options.signal?.aborted)
      throw new DOMException('Stale session', 'AbortError')
    return data
  }
}
export function commandKey() {
  return crypto.randomUUID()
}
export const segment = (value: string) => encodeURIComponent(value)
