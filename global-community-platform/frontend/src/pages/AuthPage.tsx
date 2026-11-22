import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowRight, UserPlus } from 'lucide-react'
import AuthShell from '../components/AuthShell'
import '../account-security.css'
import { useAuth } from '../context/AuthContext'
import { getErrorMessage } from '../services/api'

export default function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const isRegister = mode === 'register'
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  // Arrived through a friend's invite link (…/register?invite=username).
  const invitedBy = isRegister ? (params.get('invite') || '').trim().replace(/^@/, '').slice(0, 150) : ''
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ username: '', email: '', first_name: '', last_name: '', password: '', password_confirm: '' })
  const update = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }))

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      if (isRegister) await register(invitedBy ? { ...form, invited_by: invitedBy } : form)
      else await login(form.username, form.password)
      navigate('/home')
    } catch (err) { setError(getErrorMessage(err)) }
    finally { setBusy(false) }
  }

  return <AuthShell eyebrow="YOUR COMMUNITY STARTS HERE" title={isRegister ? 'Create your account' : 'Welcome back'} subtitle={isRegister ? 'Join the conversation. There is a place for your voice.' : 'Sign in to pick up where the conversation left off.'}>
      {invitedBy && <div className="auth-invite" role="note"><UserPlus size={15} /> <span><strong>@{invitedBy}</strong> invited you. You'll follow each other when you join.</span></div>}
      <form onSubmit={submit} className="auth-form">
        {isRegister && <div className="form-grid"><label>First name<input required value={form.first_name} onChange={(e) => update('first_name', e.target.value)} placeholder="Your first name" /></label><label>Last name<input value={form.last_name} onChange={(e) => update('last_name', e.target.value)} placeholder="Your last name" /></label></div>}
        <label>Username<input required autoComplete="username" value={form.username} onChange={(e) => update('username', e.target.value)} placeholder="e.g. alexm" /></label>
        {isRegister && <label>Email address<input required type="email" autoComplete="email" value={form.email} onChange={(e) => update('email', e.target.value)} placeholder="you@example.com" /></label>}
        <label>Password<input required type="password" minLength={8} autoComplete={isRegister ? 'new-password' : 'current-password'} value={form.password} onChange={(e) => update('password', e.target.value)} placeholder="At least 8 characters" /></label>
        {isRegister && <label>Confirm password<input required type="password" minLength={8} value={form.password_confirm} onChange={(e) => update('password_confirm', e.target.value)} placeholder="Enter your password again" /></label>}
        {error && <div className="error-message">{error}</div>}
        <button className="button button-primary auth-submit" disabled={busy}>{busy ? 'Please wait…' : isRegister ? 'Create account' : 'Sign in'} <ArrowRight size={17} /></button>
      </form>
      {!isRegister && <p className="auth-forgot"><Link to="/forgot-password">Forgot password?</Link></p>}
      <p className="auth-switch">{isRegister ? 'Already part of the community?' : 'New to CommonGround?'} <Link to={isRegister ? '/login' : '/register'}>{isRegister ? 'Sign in' : 'Create an account'}</Link></p><p className="terms-note">By continuing, you agree to be respectful, curious, and constructive.</p>
  </AuthShell>
}
