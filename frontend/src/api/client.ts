export const API_BASE_URL = localStorage.getItem('apiBaseUrl') || 'http://127.0.0.1:8000/api'

export function apiUrl(path: string): string {
  const baseUrl = (localStorage.getItem('apiBaseUrl') || API_BASE_URL).replace(/\/$/, '')
  if (/^https?:\/\//i.test(path)) return path

  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  try {
    const basePath = new URL(baseUrl).pathname.replace(/\/$/, '')
    // Backend download links are API-rooted (for example `/api/versions/2/...`),
    // while the configurable base URL already normally ends in `/api`.
    // Strip that shared prefix so callers never produce `/api/api/...`.
    if (basePath && (normalizedPath === basePath || normalizedPath.startsWith(`${basePath}/`))) {
      return `${baseUrl}${normalizedPath.slice(basePath.length) || '/'}`
    }
  } catch {
    // Keep the normal concatenation behavior for an invalid user-provided base.
  }
  return `${baseUrl}${normalizedPath}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init)
  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = typeof body === 'string' ? body : body?.detail?.message || body?.detail || body?.message
    const message = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : response.statusText
    throw new Error(message)
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
