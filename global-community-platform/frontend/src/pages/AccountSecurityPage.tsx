import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, KeyRound, LogOut, Mail, MailWarning, MonitorSmartphone, ShieldCheck, Trash2 } from 'lucide-react'
import TwoFactorSection from '../components/TwoFactorSection'
import { useAuth } from '../context/AuthContext'
import { api, getErrorMessage } from '../services/api'
import '../social.css'
import '../account-security.css'

type Result = { ok: boolean; message: string } | null

function Feedback({ result }: { result: Result }) {
  if (!result) return null
  return <div className={result.ok ? 'success-message' : 'error-message'} role={result.ok ? 'status' : 'alert'}>{result.message}</div>
}

function Card({ icon, title, help, children }: { icon: ReactNode; title: string; help: string; children: ReactNode }) {
  return <section className="privacy-card security-card"><h2>{icon} {title}</h2><p className="privacy-help">{help}</p>{children}</section>
}

function EmailSection() {
  const { user } = useAuth()
  const [resend, setResend] = useState<Result>(null)
  const [busy, setBusy] = useState(false)
  const [changing, setChanging] = useState(false)
  const [form, setForm] = useState({ new_email: '', password: '' })
  const [change, setChange] = useState<Result>(null)

  const sendAgain = async () => {
    setBusy(true)
    try { setResend({ ok: true, message: (await api.post<{ detail: string }>('/auth/email/resend/')).data.detail }) }
    catch (err) { setResend({ ok: false, message: getErrorMessage(err) }) }
    finally { setBusy(false) }
  }
  const submitChange = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true)
    try {
      const { data } = await api.post<{ detail: string }>('/auth/email/change/', form)
      setChange({ ok: true, message: data.detail }); setForm({ new_email: '', password: '' }); setChanging(false)
    } catch (err) { setChange({ ok: false, message: getErrorMessage(err) }) } finally { setBusy(false) }
  }

  return <Card icon={<Mail size={16} />} title="Email address" help="Used to reset your password and for security alerts. Never shown on your profile.">
    <div className="security-email-row">
      <strong>{user?.email || 'No email address'}</strong>
      {user?.email_verified ? <span className="security-badge is-ok"><CheckCircle2 size={12} /> Confirmed</span> : <span className="security-badge is-warn"><MailWarning size={12} /> Not confirmed</span>}
    </div>
    {!user?.email_verified && user?.email && <button type="button" className="text-button" disabled={busy} onClick={sendAgain}>Send confirmation link again</button>}
    <Feedback result={resend} />
    {changing
      ? <form className="security-form" onSubmit={submitChange}>
        <label>New email address<input required type="email" autoComplete="email" value={form.new_email} onChange={(e) => setForm({ ...form, new_email: e.target.value })} /></label>
        <label>Your password<input required type="password" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        <p className="form-hint">Your email changes after you open the link we send to the new address.</p>
        <div className="security-actions"><button type="button" className="button button-outline" onClick={() => { setChanging(false); setChange(null) }}>Cancel</button><button className="button button-primary" disabled={busy}>{busy ? 'Sending…' : 'Send confirmation link'}</button></div>
      </form>
      : <button type="button" className="button button-outline security-inline-button" onClick={() => { setChanging(true); setChange(null) }}>Change email</button>}
    <Feedback result={change} />
  </Card>
}

function PasswordSection() {
  const { applySession } = useAuth()
  const empty = { current_password: '', new_password: '', new_password_confirm: '' }
  const [form, setForm] = useState(empty)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Result>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (form.new_password !== form.new_password_confirm) { setResult({ ok: false, message: 'New passwords do not match.' }); return }
    setBusy(true); setResult(null)
    try {
      const { data } = await api.post<{ access: string; detail: string }>('/auth/password/change/', form)
      await applySession(data.access)
      setForm(empty); setResult({ ok: true, message: data.detail })
    } catch (err) { setResult({ ok: false, message: getErrorMessage(err) }) } finally { setBusy(false) }
  }
  const field = (key: keyof typeof empty, label: string, autoComplete: string) => <label>{label}<input required type="password" minLength={key === 'current_password' ? undefined : 8} autoComplete={autoComplete} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} /></label>

  return <Card icon={<KeyRound size={16} />} title="Password" help="Changing it signs out every other device. This one stays signed in.">
    <form className="security-form" onSubmit={submit}>
      {field('current_password', 'Current password', 'current-password')}
      <div className="form-grid">{field('new_password', 'New password', 'new-password')}{field('new_password_confirm', 'Confirm new password', 'new-password')}</div>
      <Feedback result={result} />
      <div className="security-actions"><Link to="/forgot-password" className="text-button">Forgot your current password?</Link><button className="button button-primary" disabled={busy}>{busy ? 'Saving…' : 'Change password'}</button></div>
    </form>
  </Card>
}

function SessionsSection() {
  const { applySession } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Result>(null)

  const revoke = async (keepCurrent: boolean) => {
    const question = keepCurrent ? 'Sign out of every other phone, tablet and computer?' : 'Sign out everywhere, including this device?'
    if (!window.confirm(question)) return
    setBusy(true)
    try {
      const { data } = await api.post<{ access?: string; detail: string }>('/auth/sessions/revoke/', { keep_current: keepCurrent })
      if (keepCurrent && data.access) { await applySession(data.access); setResult({ ok: true, message: data.detail }) }
      else { await applySession(null); navigate('/login', { replace: true }) }
    } catch (err) { setResult({ ok: false, message: getErrorMessage(err) }) } finally { setBusy(false) }
  }

  return <Card icon={<MonitorSmartphone size={16} />} title="Where you're signed in" help="Lost a phone or signed in on a shared computer? End those sessions here. It can take up to 10 minutes for an open tab elsewhere to notice.">
    <div className="security-actions is-start">
      <button type="button" className="button button-outline" disabled={busy} onClick={() => revoke(true)}><LogOut size={15} /> Sign out other devices</button>
      <button type="button" className="button button-danger-outline" disabled={busy} onClick={() => revoke(false)}>Sign out everywhere</button>
    </div>
    <Feedback result={result} />
  </Card>
}

function DeleteAccountSection() {
  const { applySession } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ password: '', code: '', confirm: '' })
  const [twoFactor, setTwoFactor] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Result>(null)
  useEffect(() => {
    if (!open) return
    api.get<{ enabled: boolean }>('/auth/2fa/').then(({ data }) => setTwoFactor(data.enabled)).catch(() => {})
  }, [open])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true); setResult(null)
    try {
      await api.post('/auth/account/delete/', form)
      await applySession(null)
      navigate('/login', { replace: true, state: { message: 'Your account has been deleted.' } })
    } catch (err) { setResult({ ok: false, message: getErrorMessage(err) }) } finally { setBusy(false) }
  }

  return <Card icon={<Trash2 size={16} />} title="Delete account" help="Permanently deletes your profile, posts, comments, stories and messages. Communities and group chats you created pass to another member. This can't be undone.">
    {!open ? <div className="security-actions is-start"><button type="button" className="button button-danger-outline" onClick={() => setOpen(true)}>Delete my account…</button></div>
      : <form className="security-form" onSubmit={submit}>
        <label>Password<input required type="password" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        {twoFactor && <label>Authenticator or recovery code<input required inputMode="text" autoComplete="one-time-code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>}
        <label>Type DELETE to confirm<input required autoComplete="off" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} /></label>
        <Feedback result={result} />
        <div className="security-actions">
          <button type="button" className="text-button" onClick={() => { setOpen(false); setResult(null) }}>Cancel</button>
          <button className="button button-danger-outline" disabled={busy || form.confirm.trim().toUpperCase() !== 'DELETE'}>{busy ? 'Deleting…' : 'Delete my account forever'}</button>
        </div>
      </form>}
  </Card>
}

export default function AccountSecurityPage() {
  return <div className="people-page privacy-page security-page">
    <Link to="/profile" className="back-link"><ArrowLeft size={16} /> Back to profile settings</Link>
    <div className="page-intro-row"><div><span className="eyebrow"><ShieldCheck size={12} /> SETTINGS</span><h1>Account security</h1><p>Your email, password, two-step sign-in and signed-in devices.</p></div></div>
    <EmailSection />
    <PasswordSection />
    <TwoFactorSection />
    <SessionsSection />
    <DeleteAccountSection />
  </div>
}
