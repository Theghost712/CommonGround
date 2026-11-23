import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, ShieldCheck, UserPlus } from 'lucide-react'
import AuthShell from '../components/AuthShell'
import '../account-security.css'
import { useAuth } from '../context/AuthContext'
import { getErrorMessage } from '../services/api'

export default function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const isRegister = mode === 'register'
  const { login, register, completeTwoFactor } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  // Arrived through a friend's invite link (…/register?invite=username).
  const invitedBy = isRegister ? (params.get('invite') || '').trim().replace(/^@/, '').slice(0, 150) : ''
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ username: '', email: '', first_name: '', last_name: '', password: '', password_confirm: '' })
  // Set after a correct password on an account with two-step sign-in.
  const [challenge, setChallenge] = useState('')
  const [code, setCode] = useState('')
  const [useRecovery, setUseRecovery] = useState(false)
  const update = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }))

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      if (isRegister) await register(invitedBy ? { ...form, invited_by: invitedBy } : form)
      else {
        const pending = await login(form.username, form.password)
        if (pending) { setChallenge(pending.challenge); setCode(''); return }
      }
      navigate('/home')
    } catch (err) { setError(getErrorMessage(err)) }
    finally { setBusy(false) }
  }

  const submitCode = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const { recovery_codes_left: left } = await completeTwoFactor(challenge, code)
      if (left !== undefined && left <= 3) window.alert(`You have ${left} recovery code${left === 1 ? '' : 's'} left. Create new ones in Account security.`)
      navigate('/home')
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status
      if (status === 401) { setChallenge(''); setForm((current) => ({ ...current, password: '' })) }
      setError(getErrorMessage(err))
    } finally { setBusy(false) }
  }

  if (challenge) {
    return <AuthShell eyebrow="TWO-STEP SIGN-IN" title="Enter your code" subtitle={useRecovery ? 'Type one of the recovery codes you saved when you turned on two-step sign-in.' : 'Open your authenticator app and type the 6-digit code for CommonGround.'}>
      <form onSubmit={submitCode} className="auth-form">
        <label>{useRecovery ? 'Recovery code' : 'Authentication code'}
          {useRecovery
            ? <input required autoFocus autoComplete="off" spellCheck={false} value={code} onChange={(e) => setCode(e.target.value)} placeholder="xxxxx-xxxxx" />
            : <input required autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" maxLength={7} value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9 ]/g, ''))} placeholder="123 456" />}
        </label>
        {error && <div className="error-message">{error}</div>}
        <button className="button button-primary auth-submit" disabled={busy}>{busy ? 'Checking…' : 'Verify'} <ShieldCheck size={17} /></button>
      </form>
      <p className="auth-forgot"><button type="button" className="text-button" onClick={() => { setUseRecovery(!useRecovery); setCode(''); setError('') }}>{useRecovery ? 'Use the code from my app' : "Can't use your app? Use a recovery code"}</button></p>
      <p className="auth-switch"><button type="button" className="text-button" onClick={() => { setChallenge(''); setError(''); setUseRecovery(false) }}><ArrowLeft size={14} /> Back to sign in</button></p>
    </AuthShell>
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
