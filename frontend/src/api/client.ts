export type ApiErrorKind = 'invalid_base' | 'network' | 'not_found' | 'http'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly kind: ApiErrorKind,
    public readonly url?: string,
    public readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export const API_BASE_URL = 'http://127.0.0.1:8000/api'

export function normalizeApiBase(input: string): string {
  const value = String(input || '').trim()
  if (!value) throw new ApiError('API Base 不能为空', 'invalid_base')
  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new ApiError('API Base 必须是完整的 http:// 或 https:// 地址', 'invalid_base')
  }
  if (!['http:', 'https:'].includes(url.protocol) || !url.hostname) {
    throw new ApiError('API Base 只支持有效的 HTTP 或 HTTPS 地址', 'invalid_base')
  }
  const segments = url.pathname.split('/').filter(Boolean)
  while (segments.length && segments[segments.length - 1].toLowerCase() === 'api') segments.pop()
  if (segments.length) {
    throw new ApiError('API Base 路径只能为空或 /api', 'invalid_base')
  }
  url.pathname = '/api'
  url.search = ''
  url.hash = ''
  return url.toString().replace(/\/$/, '')
}

export function getApiBaseUrl(): string {
  return normalizeApiBase(localStorage.getItem('apiBaseUrl') || API_BASE_URL)
}

export function getApiOrigin(): string {
  return getApiBaseUrl().replace(/\/api$/, '')
}

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path

  const baseUrl = getApiBaseUrl()
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  try {
    const basePath = new URL(baseUrl).pathname.replace(/\/$/, '')
    if (basePath && (normalizedPath === basePath || normalizedPath.startsWith(`${basePath}/`))) {
      return `${baseUrl}${normalizedPath.slice(basePath.length) || '/'}`
    }
  } catch {
    // normalizeApiBase normally prevents this; retain deterministic fallback.
  }
  return `${baseUrl}${normalizedPath}`
}

export function describeApiError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : '未知接口错误'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = apiUrl(`/${String(path || '').replace(/^\/+/, '')}`)
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new ApiError(`无法连接后端服务：${url}`, 'network', url)
  }
  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = typeof body === 'string' ? body : body?.detail?.message || body?.detail || body?.message
    const reason = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : response.statusText
    if (response.status === 404) {
      throw new ApiError(`资源不存在：${reason}`, 'not_found', url, 404)
    }
    throw new ApiError(`接口请求失败（${response.status}）：${reason}`, 'http', url, response.status)
  }
  return body as T
}

export async function apiGet<T>(path: string): Promise<T> {
  return request<T>(path)
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  })
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const formData = new FormData()
  formData.append('file', file)
  return request<T>(path, { method: 'POST', body: formData })
}
