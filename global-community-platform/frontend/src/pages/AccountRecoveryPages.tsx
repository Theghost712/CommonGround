import { useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, CheckCircle2, MailCheck } from 'lucide-react'
import AuthShell from '../components/AuthShell'
import { useAuth } from '../context/AuthContext'
import { api, ensureCsrfToken, getErrorMessage } from '../services/api'
import '../account-security.css'

export function ForgotPasswordPage() {
  const [login, setLogin] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState('')
  const [error, setError] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      await ensureCsrfToken()
      const { data } = await api.post<{ detail: string }>('/auth/password/reset/', { login: login.trim() })
      setSent(data.detail)
    } catch (err) { setError(getErrorMessage(err)) } finally { setBusy(false) }
  }

  return <AuthShell eyebrow="ACCOUNT RECOVERY" title="Forgot your password?" subtitle="Enter your username or email. We'll email you a link to choose a new password.">
    {sent
      ? <div className="auth-result" role="status"><MailCheck size={22} /><div><strong>Check your email</strong><p>{sent}</p><p className="auth-result-small">The link works for 1 hour.</p></div></div>
      : <form onSubmit={submit} className="auth-form">
        <label>Username or email<input required autoFocus autoComplete="username" value={login} onChange={(e) => setLogin(e.target.value)} placeholder="e.g. alexm or you@example.com" /></label>
        {error && <div className="error-message">{error}</div>}
        <button className="button button-primary auth-submit" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'} <ArrowRight size={17} /></button>
      </form>}
    <p className="auth-switch">Remembered it? <Link to="/login">Back to sign in</Link></p>
  </AuthShell>
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const uid = params.get('uid') ?? ''
  const token = params.get('token') ?? ''
  const [form, setForm] = useState({ new_password: '', new_password_confirm: '' })
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState('')
  const [error, setError] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError('')
    if (form.new_password !== form.new_password_confirm) { setError('Passwords do not match.'); return }
    setBusy(true)
    try {
      await ensureCsrfToken()
      const { data } = await api.post<{ detail: string }>('/auth/password/reset/confirm/', { uid, token, ...form })
      setDone(data.detail)
    } catch (err) { setError(getErrorMessage(err)) } finally { setBusy(false) }
  }

  if (!uid || !token) {
    return <AuthShell eyebrow="ACCOUNT RECOVERY" title="Link incomplete" subtitle="This reset link is missing some parts. Open the link from the email again, or ask for a new one.">
      <Link to="/forgot-password" className="button button-primary auth-submit">Ask for a new link <ArrowRight size={17} /></Link>
    </AuthShell>
  }

  return <AuthShell eyebrow="ACCOUNT RECOVERY" title={done ? 'Password changed' : 'Choose a new password'} subtitle={done ? 'For your safety, every device was signed out.' : 'Use at least 8 characters. Avoid passwords you use on other sites.'}>
    {done
      ? <><div className="auth-result" role="status"><CheckCircle2 size={22} /><div><strong>All set</strong><p>{done}</p></div></div><Link to="/login" className="button button-primary auth-submit">Sign in <ArrowRight size={17} /></Link></>
      : <form onSubmit={submit} className="auth-form">
        <label>New password<input required autoFocus type="password" minLength={8} autoComplete="new-password" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} placeholder="At least 8 characters" /></label>
        <label>Confirm new password<input required type="password" minLength={8} autoComplete="new-password" value={form.new_password_confirm} onChange={(e) => setForm({ ...form, new_password_confirm: e.target.value })} placeholder="Enter it again" /></label>
        {error && <div className="error-message">{error}{/expired|invalid/i.test(error) && <> <Link to="/forgot-password">Ask for a new link.</Link></>}</div>}
        <button className="button button-primary auth-submit" disabled={busy}>{busy ? 'Saving…' : 'Save new password'} <ArrowRight size={17} /></button>
      </form>}
  </AuthShell>
}

// One request per token, even when React StrictMode runs the effect twice. An
// email-change link only works once, so a second request would report failure.
const verifications = new Map<string, Promise<string>>()
function verifyOnce(token: string) {
  let pending = verifications.get(token)
  if (!pending) {
    pending = ensureCsrfToken().then(() => api.post<{ detail: string }>('/auth/email/verify/', { token })).then(({ data }) => data.detail)
    verifications.set(token, pending)
    pending.catch(() => verifications.delete(token))
  }
  return pending
}

export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const { user, reloadUser } = useAuth()
  const [state, setState] = useState<{ status: 'working' | 'done' | 'failed'; message: string }>({ status: 'working', message: '' })

  useEffect(() => {
    if (!token) { setState({ status: 'failed', message: 'This link is missing its code. Open it from the email again.' }); return }
    let active = true
    verifyOnce(token).then(async (message) => {
      if (!active) return
      setState({ status: 'done', message })
      await reloadUser()
    }).catch((err) => { if (active) setState({ status: 'failed', message: getErrorMessage(err) }) })
    return () => { active = false }
    // reloadUser changes identity every render; the token is what matters.
  }, [token])

  const next = user ? { to: '/home', label: 'Go to your feed' } : { to: '/login', label: 'Sign in' }
  return <AuthShell eyebrow="EMAIL CONFIRMATION" title={state.status === 'working' ? 'Confirming…' : state.status === 'done' ? 'Email confirmed' : "We couldn't confirm it"} subtitle={state.status === 'working' ? 'One moment.' : ''}>
    {state.status !== 'working' && <div className={`auth-result ${state.status === 'failed' ? 'is-error' : ''}`} role="status">{state.status === 'done' ? <CheckCircle2 size={22} /> : <MailCheck size={22} />}<div><p>{state.message}</p></div></div>}
    {state.status === 'failed' && user && <Link to="/settings/security" className="button button-outline auth-submit">Send a new link</Link>}
    {state.status !== 'working' && <Link to={next.to} className="button button-primary auth-submit">{next.label} <ArrowRight size={17} /></Link>}
  </AuthShell>
}
