import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1'
export const api = axios.create({ baseURL: API_BASE, withCredentials: true, headers: { 'Content-Type': 'application/json' } })

let accessToken: string | null = null
let csrfToken: string | null = null
let csrfRequest: Promise<string> | null = null
export const setAccessToken = (token: string | null) => { accessToken = token }

export async function ensureCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken
  csrfRequest ??= api.get<{ csrfToken: string }>('/auth/csrf/').then(({ data }) => {
    csrfToken = data.csrfToken
    return csrfToken
  }).finally(() => { csrfRequest = null })
  return csrfRequest
}

api.interceptors.request.use(async (config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  if (['post', 'put', 'patch', 'delete'].includes((config.method || '').toLowerCase()) && !String(config.url).includes('/auth/csrf/')) {
    config.headers['X-CSRFToken'] = await ensureCsrfToken()
  }
  return config
})

// Endpoints whose 401 means bad credentials or a dead session, not an expired
// access token. Refreshing for these would be pointless or loop forever.
// Other /auth/ endpoints (me, profile, ws-ticket) need the refresh-and-retry.
const NO_REFRESH_PATHS = [
  '/auth/token/', '/auth/token/refresh/', '/auth/csrf/', '/auth/register/', '/auth/logout/',
  // Signed-out account recovery: a 401 here can't be fixed by refreshing.
  '/auth/password/reset/', '/auth/password/reset/confirm/', '/auth/email/verify/',
]

export function skipsTokenRefresh(url: string | undefined): boolean {
  const path = String(url ?? '').split('?')[0]
  return NO_REFRESH_PATHS.some((skip) => path === skip || path.endsWith(skip))
}

let refreshing: Promise<string | null> | null = null

/**
 * Exchange the refresh cookie for a new access token, sharing one request between
 * every caller. The server rotates and blacklists the refresh token on each use, so
 * two parallel refreshes (React StrictMode's double effect, app start-up racing a
 * 401 retry, several 401s at once) would make all but one fail and log the user out.
 */
export function refreshAccessToken(): Promise<string | null> {
  refreshing ??= api.post<{ access: string }>('/auth/token/refresh/', {}).then(({ data }) => {
    setAccessToken(data.access)
    return data.access
  }).catch(() => {
    setAccessToken(null)
    return null
  }).finally(() => { refreshing = null })
  return refreshing
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && original && !original._retry && !skipsTokenRefresh(original.url)) {
      original._retry = true
      const nextToken = await refreshAccessToken()
      if (nextToken) {
        original.headers.Authorization = `Bearer ${nextToken}`
        return api(original)
      }
      window.dispatchEvent(new Event('commonground:auth-expired'))
    }
    return Promise.reject(error)
  },
)

function waitText(seconds: number): string {
  if (seconds < 60) return `${Math.max(1, Math.ceil(seconds))} seconds`
  const minutes = Math.ceil(seconds / 60)
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 429) {
      const retryAfter = Number(error.response.headers?.['retry-after'])
      const wait = Number.isFinite(retryAfter) && retryAfter > 0 ? ` Please wait ${waitText(retryAfter)} and try again.` : ' Please wait a moment and try again.'
      return `Too many attempts.${wait}`
    }
    const data = error.response?.data
    if (typeof data === 'string') return data
    if (data && typeof data === 'object') {
      const values = Object.values(data as Record<string, unknown>).flatMap((value) => Array.isArray(value) ? value : [value])
      if (values.length) return String(values[0])
    }
    return error.message
  }
  return 'Something went wrong. Please try again.'
}
