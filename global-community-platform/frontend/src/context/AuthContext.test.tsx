import { StrictMode } from 'react'
import { render, screen } from '@testing-library/react'
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

function respond(config: InternalAxiosRequestConfig, status: number, data: unknown): Promise<AxiosResponse> {
  const response: AxiosResponse = { data, status, statusText: String(status), headers: {}, config }
  return status >= 400 ? Promise.reject(new AxiosError('failed', String(status), config, null, response)) : Promise.resolve(response)
}

describe('AuthProvider session restore', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>
  let refreshCalls: number

  beforeEach(() => {
    vi.resetModules()
    refreshCalls = 0
  })

  async function mount() {
    const apiModule = await import('../services/api')
    const { AuthProvider, useAuth } = await import('./AuthContext')
    adapter = vi.fn<AxiosAdapter>((config) => {
      if (config.url === '/auth/csrf/') return respond(config, 200, { csrfToken: 'csrf' })
      if (config.url === '/auth/token/refresh/') {
        refreshCalls += 1
        // Like the real server: the refresh cookie is single-use (rotated + blacklisted).
        return refreshCalls === 1 ? respond(config, 200, { access: 'fresh' }) : respond(config, 401, { detail: 'blacklisted' })
      }
      if (config.url === '/auth/me/') return respond(config, 200, { id: 1, username: 'amani', email: '', first_name: 'Amani', last_name: '' })
      return respond(config, 404, {})
    })
    apiModule.api.defaults.adapter = adapter
    function Probe() {
      const { user, loading } = useAuth()
      return <p>{loading ? 'loading' : user ? `signed in as ${user.username}` : 'signed out'}</p>
    }
    render(<StrictMode><AuthProvider><Probe /></AuthProvider></StrictMode>)
  }

  it('restores the session with a single refresh even when StrictMode runs effects twice', async () => {
    await mount()

    expect(await screen.findByText('signed in as amani')).toBeInTheDocument()
    expect(refreshCalls).toBe(1)
  })
})

describe('refreshAccessToken', () => {
  beforeEach(() => { vi.resetModules() })

  it('shares one in-flight request between start-up and 401 retries', async () => {
    const mod = await import('../services/api')
    let calls = 0
    mod.api.defaults.adapter = vi.fn<AxiosAdapter>((config) => {
      if (config.url === '/auth/csrf/') return respond(config, 200, { csrfToken: 'csrf' })
      if (config.url === '/auth/token/refresh/') { calls += 1; return respond(config, 200, { access: `token-${calls}` }) }
      return AxiosHeadersAuth(config) === 'Bearer token-1' ? respond(config, 200, { ok: true }) : respond(config, 401, {})
    })

    const [startup, retried] = await Promise.all([mod.refreshAccessToken(), mod.api.get('/auth/me/')])

    expect(startup).toBe('token-1')
    expect(retried.data).toEqual({ ok: true })
    expect(calls).toBe(1)
  })

  it('returns null and clears the token when the session is gone', async () => {
    const mod = await import('../services/api')
    mod.setAccessToken('stale')
    mod.api.defaults.adapter = vi.fn<AxiosAdapter>((config) => config.url === '/auth/csrf/' ? respond(config, 200, { csrfToken: 'csrf' }) : respond(config, 401, {}))

    expect(await mod.refreshAccessToken()).toBeNull()
  })
})

function AxiosHeadersAuth(config: InternalAxiosRequestConfig) {
  const headers = config.headers as unknown as { get?: (name: string) => unknown; Authorization?: string }
  return (typeof headers.get === 'function' ? headers.get('Authorization') : headers.Authorization) as string | undefined
}
