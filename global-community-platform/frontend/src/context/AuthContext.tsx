import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ensureCsrfToken, refreshAccessToken, setAccessToken } from '../services/api'
import { forgetPushOnSignOut } from '../services/push'

export type User = { id: number; username: string; email: string; email_verified: boolean; two_factor_enabled?: boolean
  has_password?: boolean
  google_linked?: boolean; can_moderate?: boolean; is_staff?: boolean; first_name: string; last_name: string }
type AuthValue = {
  user: User | null
  loading: boolean
  /** Resolves to a challenge when the account needs a second step (authenticator code). */
  login: (username: string, password: string) => Promise<TwoFactorChallenge | null>
  /** Second sign-in step: a 6-digit app code or a recovery code. */
  completeTwoFactor: (challenge: string, code: string) => Promise<{ recovery_codes_left?: number }>
  /** Sign in (or sign up) with a Google ID token. Returns a 2FA challenge when needed. */
  googleSignIn: (credential: string, invitedBy?: string) => Promise<{ challenge: string } | null>
  register: (data: Record<string, string>) => Promise<void>
  logout: () => Promise<void>
  /** Re-read /auth/me/ (after email verification, for example). */
  reloadUser: () => Promise<void>
  /** Use a new access token the server issued (password change); null signs out locally. */
  applySession: (access: string | null) => Promise<void>
}
export type TwoFactorChallenge = { challenge: string }
type LoginResponse = { access?: string; two_factor_required?: boolean; challenge?: string }

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchMe = async () => {
    const response = await api.get<User>('/auth/me/')
    setUser(response.data)
  }

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        await ensureCsrfToken()
        // Shared with any other in-flight refresh, so StrictMode's second run
        // reuses the first request instead of racing it with the same cookie.
        if (!(await refreshAccessToken())) throw new Error('No session')
        const response = await api.get<User>('/auth/me/')
        if (active) setUser(response.data)
      } catch {
        if (active) setUser(null)
      } finally {
        if (active) setLoading(false)
      }
    })()
    const onExpired = () => setUser(null)
    window.addEventListener('commonground:auth-expired', onExpired)
    return () => { active = false; window.removeEventListener('commonground:auth-expired', onExpired) }
  }, [])

  const login = async (username: string, password: string) => {
    await ensureCsrfToken()
    const { data } = await api.post<LoginResponse>('/auth/token/', { username, password })
    if (data.two_factor_required && data.challenge) return { challenge: data.challenge }
    setAccessToken(data.access ?? null)
    await fetchMe()
    return null
  }

  const googleSignIn = async (credential: string, invitedBy = '') => {
    await ensureCsrfToken()
    const { data } = await api.post<LoginResponse>('/auth/google/', { credential, invited_by: invitedBy || undefined })
    if (data.two_factor_required && data.challenge) return { challenge: data.challenge }
    setAccessToken(data.access ?? null)
    await fetchMe()
    return null
  }

  const completeTwoFactor = async (challenge: string, code: string) => {
    await ensureCsrfToken()
    const { data } = await api.post<{ access: string; recovery_codes_left?: number }>('/auth/token/2fa/', { challenge, code })
    setAccessToken(data.access)
    await fetchMe()
    return { recovery_codes_left: data.recovery_codes_left }
  }

  const register = async (data: Record<string, string>) => {
    await ensureCsrfToken()
    await api.post('/auth/register/', data)
    await login(data.username, data.password)
  }

  const logout = async () => {
    // While still signed in, so the server forgets this device's push subscription.
    await forgetPushOnSignOut()
    try { await api.post('/auth/logout/', {}) } finally {
      setAccessToken(null)
      setUser(null)
    }
  }

  const reloadUser = async () => { try { await fetchMe() } catch { /* the 401 handler signs out */ } }

  const applySession = async (access: string | null) => {
    setAccessToken(access)
    if (access) await fetchMe()
    else setUser(null)
  }

  return <AuthContext.Provider value={{ user, loading, login, completeTwoFactor, googleSignIn, register, logout, reloadUser, applySession }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
