import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type ApiModule = typeof import('./api')

/** Load a fresh copy of the module so its in-memory token/CSRF state starts empty. */
async function loadApi(): Promise<ApiModule> {
  vi.resetModules()
  return import('./api')
}

function respond(config: InternalAxiosRequestConfig, status: number, data: unknown): Promise<AxiosResponse> {
  const response: AxiosResponse = { data, status, statusText: String(status), headers: {}, config }
  if (status >= 400) {
    return Promise.reject(new AxiosError(`Request failed with status code ${status}`, String(status), config, null, response))
  }
  return Promise.resolve(response)
}

function headerOf(config: InternalAxiosRequestConfig, name: string) {
  return AxiosHeaders.from(config.headers).get(name)
}

describe('getErrorMessage', () => {
  let getErrorMessage: ApiModule['getErrorMessage']

  beforeEach(async () => {
    ;({ getErrorMessage } = await loadApi())
  })

  const axiosError = (data: unknown) => {
    const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig
    return new AxiosError('Request failed', '400', config, null, { data, status: 400, statusText: '400', headers: {}, config })
  }

  it('returns a plain string body', () => {
    expect(getErrorMessage(axiosError('Server exploded'))).toBe('Server exploded')
  })

  it('returns the first DRF field error', () => {
    expect(getErrorMessage(axiosError({ password_confirm: ['Passwords do not match.'] }))).toBe('Passwords do not match.')
  })

  it('returns a DRF detail message', () => {
    expect(getErrorMessage(axiosError({ detail: 'You do not have permission.' }))).toBe('You do not have permission.')
  })

  it('falls back to the axios message when there is no body', () => {
    expect(getErrorMessage(axiosError(undefined))).toBe('Request failed')
  })

  it('turns a 429 into a friendly wait message using Retry-After', () => {
    const throttled = (retryAfter?: string) => {
      const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig
      const headers = retryAfter ? { 'retry-after': retryAfter } : {}
      return new AxiosError('Request failed', '429', config, null, { data: { detail: 'Request was throttled. Expected available in 2190 seconds.' }, status: 429, statusText: '429', headers, config })
    }
    expect(getErrorMessage(throttled('2190'))).toBe('Too many attempts. Please wait 37 minutes and try again.')
    expect(getErrorMessage(throttled('45'))).toBe('Too many attempts. Please wait 45 seconds and try again.')
    expect(getErrorMessage(throttled('60'))).toBe('Too many attempts. Please wait 1 minute and try again.')
    expect(getErrorMessage(throttled())).toBe('Too many attempts. Please wait a moment and try again.')
  })

  it('uses a generic message for non-axios errors', () => {
    expect(getErrorMessage(new Error('boom'))).toBe('Something went wrong. Please try again.')
  })
})

describe('api client interceptors', () => {
  let mod: ApiModule
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(async () => {
    mod = await loadApi()
    adapter = vi.fn<AxiosAdapter>()
    mod.api.defaults.adapter = adapter
  })

  it('adds the bearer token to requests', async () => {
    adapter.mockImplementation((config) => respond(config, 200, { ok: true }))
    mod.setAccessToken('access-1')

    await mod.api.get('/communities/')

    expect(headerOf(adapter.mock.calls[0][0], 'Authorization')).toBe('Bearer access-1')
  })

  it('fetches a CSRF token once and sends it on unsafe methods only', async () => {
    adapter.mockImplementation((config) => respond(config, 200, config.url === '/auth/csrf/' ? { csrfToken: 'csrf-abc' } : {}))

    await mod.api.get('/discussions/')
    await mod.api.post('/discussions/', { title: 'x' })
    await mod.api.delete('/discussions/1/')

    const urls = adapter.mock.calls.map(([config]) => `${config.method} ${config.url}`)
    expect(urls).toEqual(['get /discussions/', 'get /auth/csrf/', 'post /discussions/', 'delete /discussions/1/'])
    expect(headerOf(adapter.mock.calls[0][0], 'X-CSRFToken')).toBeFalsy()
    expect(headerOf(adapter.mock.calls[2][0], 'X-CSRFToken')).toBe('csrf-abc')
    expect(headerOf(adapter.mock.calls[3][0], 'X-CSRFToken')).toBe('csrf-abc')
  })

  it('refreshes the access token on 401 and retries the request once', async () => {
    mod.setAccessToken('expired')
    adapter.mockImplementation((config) => {
      if (config.url === '/auth/csrf/') return respond(config, 200, { csrfToken: 'csrf' })
      if (config.url === '/auth/token/refresh/') return respond(config, 200, { access: 'fresh' })
      const auth = headerOf(config, 'Authorization')
      return auth === 'Bearer fresh' ? respond(config, 200, { name: 'ok' }) : respond(config, 401, { detail: 'expired' })
    })

    const response = await mod.api.get('/communities/')

    expect(response.data).toEqual({ name: 'ok' })
    const refreshCalls = adapter.mock.calls.filter(([config]) => config.url === '/auth/token/refresh/')
    expect(refreshCalls).toHaveLength(1)
  })

  it('shares one refresh request between parallel 401 responses', async () => {
    mod.setAccessToken('expired')
    adapter.mockImplementation((config) => {
      if (config.url === '/auth/csrf/') return respond(config, 200, { csrfToken: 'csrf' })
      if (config.url === '/auth/token/refresh/') return respond(config, 200, { access: 'fresh' })
      return headerOf(config, 'Authorization') === 'Bearer fresh' ? respond(config, 200, {}) : respond(config, 401, {})
    })

    await Promise.all([mod.api.get('/communities/'), mod.api.get('/discussions/'), mod.api.get('/events/')])

    expect(adapter.mock.calls.filter(([config]) => config.url === '/auth/token/refresh/')).toHaveLength(1)
  })

  it('signals auth expiry when the refresh fails', async () => {
    const expired = vi.fn()
    window.addEventListener('commonground:auth-expired', expired)
    adapter.mockImplementation((config) => {
      if (config.url === '/auth/csrf/') return respond(config, 200, { csrfToken: 'csrf' })
      return respond(config, 401, { detail: 'nope' })
    })

    await expect(mod.api.get('/communities/')).rejects.toMatchObject({ response: { status: 401 } })

    expect(expired).toHaveBeenCalledTimes(1)
    window.removeEventListener('commonground:auth-expired', expired)
  })

  // Authenticated /auth/ endpoints must recover from an expired access token like any other API call.
  it.each([
    ['get', '/auth/me/'],
    ['get', '/auth/profile/'],
    ['patch', '/auth/profile/'],
    ['post', '/auth/ws-ticket/'],
  ] as const)('refreshes and retries %s %s after a 401', async (method, url) => {
    mod.setAccessToken('expired')
    adapter.mockImplementation((config) => {
      if (config.url === '/auth/csrf/') return respond(config, 200, { csrfToken: 'csrf' })
      if (config.url === '/auth/token/refresh/') return respond(config, 200, { access: 'fresh' })
      return headerOf(config, 'Authorization') === 'Bearer fresh' ? respond(config, 200, { ok: url }) : respond(config, 401, { detail: 'expired' })
    })

    const response = method === 'get' ? await mod.api.get(url) : await mod.api[method](url, {})

    expect(response.data).toEqual({ ok: url })
    expect(adapter.mock.calls.filter(([config]) => config.url === '/auth/token/refresh/')).toHaveLength(1)
  })

  it.each(['/auth/token/', '/auth/token/refresh/', '/auth/register/', '/auth/logout/'])(
    'does not try to refresh when %s itself returns 401',
    async (url) => {
      const expired = vi.fn()
      window.addEventListener('commonground:auth-expired', expired)
      adapter.mockImplementation((config) => {
        if (config.url === '/auth/csrf/') return respond(config, 200, { csrfToken: 'csrf' })
        return respond(config, 401, { detail: 'bad credentials' })
      })

      await expect(mod.api.post(url, {})).rejects.toBeInstanceOf(AxiosError)

      expect(adapter.mock.calls.filter(([config]) => config.url === '/auth/token/refresh/')).toHaveLength(url === '/auth/token/refresh/' ? 1 : 0)
      expect(expired).not.toHaveBeenCalled()
      window.removeEventListener('commonground:auth-expired', expired)
    },
  )

  it('matches skip paths exactly, ignoring query strings and absolute URLs', () => {
    expect(mod.skipsTokenRefresh('/auth/token/')).toBe(true)
    expect(mod.skipsTokenRefresh('/auth/token/?next=1')).toBe(true)
    expect(mod.skipsTokenRefresh('http://api.example.com/api/v1/auth/logout/')).toBe(true)
    expect(mod.skipsTokenRefresh('/auth/me/')).toBe(false)
    expect(mod.skipsTokenRefresh('/auth/ws-ticket/')).toBe(false)
    expect(mod.skipsTokenRefresh('/communities/')).toBe(false)
    expect(mod.skipsTokenRefresh(undefined)).toBe(false)
  })
})
