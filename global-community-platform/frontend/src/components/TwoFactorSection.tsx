import { useEffect, useState, type FormEvent } from 'react'
import QRCode from 'qrcode'
import { Copy, Download, Smartphone } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { api, getErrorMessage } from '../services/api'

type Status = { enabled: boolean; confirmed_at: string | null; recovery_codes_left: number }
type Setup = { secret: string; otpauth_uri: string; qr: string }
type Mode = 'idle' | 'password' | 'scan' | 'codes' | 'disable' | 'regenerate'

/** "ABCD EFGH …" is easier to type by hand than one long string. */
const groupSecret = (secret: string) => secret.replace(/(.{4})/g, '$1 ').trim()

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const [copied, setCopied] = useState(false)
  const text = `CommonGround recovery codes\nEach code works once. Keep them somewhere safe.\n\n${codes.join('\n')}\n`
  const copy = async () => { try { await navigator.clipboard.writeText(text); setCopied(true) } catch { setCopied(false) } }
  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
    const link = Object.assign(document.createElement('a'), { href: url, download: 'commonground-recovery-codes.txt' })
    link.click(); URL.revokeObjectURL(url)
  }
  return <div className="twofa-codes">
    <p className="form-hint"><strong>Save these recovery codes now.</strong> If you lose your phone, each one lets you sign in once. You won't see them again.</p>
    <ol>{codes.map((code) => <li key={code}><code>{code}</code></li>)}</ol>
    <div className="security-actions is-start">
      <button type="button" className="button button-outline" onClick={copy}><Copy size={15} /> {copied ? 'Copied' : 'Copy'}</button>
      <button type="button" className="button button-outline" onClick={download}><Download size={15} /> Download</button>
      <button type="button" className="button button-primary" onClick={onDone}>I saved them</button>
    </div>
  </div>
}

export default function TwoFactorSection() {
  const { reloadUser } = useAuth()
  const [status, setStatus] = useState<Status | null>(null)
  const [mode, setMode] = useState<Mode>('idle')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [setup, setSetup] = useState<Setup | null>(null)
  const [codes, setCodes] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = async () => { try { setStatus((await api.get<Status>('/auth/2fa/')).data) } catch (err) { setError(getErrorMessage(err)) } }
  useEffect(() => { void load() }, [])

  const reset = (next: Mode = 'idle') => { setMode(next); setPassword(''); setCode(''); setError('') }
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError('')
    try { await action() } catch (err) { setError(getErrorMessage(err)) } finally { setBusy(false) }
  }

  const start = (event: FormEvent) => { event.preventDefault(); void run(async () => {
    const { data } = await api.post<Omit<Setup, 'qr'>>('/auth/2fa/setup/', { password })
    const qr = await QRCode.toDataURL(data.otpauth_uri, { margin: 1, width: 200 })
    setSetup({ ...data, qr }); setPassword(''); setCode(''); setMode('scan')
  }) }
  const confirm = (event: FormEvent) => { event.preventDefault(); void run(async () => {
    const { data } = await api.post<{ recovery_codes: string[] }>('/auth/2fa/confirm/', { code })
    setCodes(data.recovery_codes); setSetup(null); setCode(''); setMode('codes')
    await Promise.all([load(), reloadUser()])
  }) }
  const disable = (event: FormEvent) => { event.preventDefault(); void run(async () => {
    await api.post('/auth/2fa/disable/', { password, code })
    reset(); await Promise.all([load(), reloadUser()])
  }) }
  const regenerate = (event: FormEvent) => { event.preventDefault(); void run(async () => {
    const { data } = await api.post<{ recovery_codes: string[] }>('/auth/2fa/recovery-codes/', { password, code })
    setCodes(data.recovery_codes); setPassword(''); setCode(''); setMode('codes'); await load()
  }) }

  const passwordField = <label>Your password<input required type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
  const codeField = (label: string) => <label>{label}<input required autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="123456 or a recovery code" /></label>
  const errorBox = error && <div className="error-message" role="alert">{error}</div>

  return <section className="privacy-card security-card">
    <h2><Smartphone size={16} /> Two-step sign-in</h2>
    <p className="privacy-help">Ask for a code from an authenticator app (Google Authenticator, Microsoft Authenticator, Authy, 1Password…) when you sign in, so a stolen password isn't enough.</p>
    {status && mode !== 'codes' && <div className="security-email-row">
      {status.enabled
        ? <><span className="security-badge is-ok">On</span><span className="twofa-meta">{status.recovery_codes_left} recovery code{status.recovery_codes_left === 1 ? '' : 's'} left</span></>
        : <span className="security-badge is-warn">Off</span>}
    </div>}

    {mode === 'idle' && status && (status.enabled
      ? <div className="security-actions is-start">
        <button type="button" className="button button-outline" onClick={() => reset('regenerate')}>New recovery codes</button>
        <button type="button" className="button button-danger-outline" onClick={() => reset('disable')}>Turn off</button>
      </div>
      : <button type="button" className="button button-primary security-inline-button" onClick={() => reset('password')}>Turn on</button>)}

    {mode === 'password' && <form className="security-form" onSubmit={start}>
      {passwordField}{errorBox}
      <div className="security-actions"><button type="button" className="button button-outline" onClick={() => reset()}>Cancel</button><button className="button button-primary" disabled={busy}>{busy ? 'Please wait…' : 'Continue'}</button></div>
    </form>}

    {mode === 'scan' && setup && <form className="security-form" onSubmit={confirm}>
      <div className="twofa-scan">
        <img src={setup.qr} alt="QR code for your authenticator app" width={180} height={180} />
        <div>
          <p className="form-hint"><strong>1.</strong> Scan this with your authenticator app. On this phone? <a href={setup.otpauth_uri}>Open it in your app</a>.</p>
          <p className="form-hint">Can't scan? Enter this key: <code className="twofa-secret">{groupSecret(setup.secret)}</code></p>
          <p className="form-hint"><strong>2.</strong> Type the 6-digit code it shows.</p>
        </div>
      </div>
      <label>Code from the app<input required autoFocus inputMode="numeric" autoComplete="one-time-code" maxLength={7} value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9 ]/g, ''))} placeholder="123 456" /></label>
      {errorBox}
      <div className="security-actions"><button type="button" className="button button-outline" onClick={() => { setSetup(null); reset() }}>Cancel</button><button className="button button-primary" disabled={busy}>{busy ? 'Checking…' : 'Turn on'}</button></div>
    </form>}

    {mode === 'codes' && <RecoveryCodes codes={codes} onDone={() => { setCodes([]); reset() }} />}

    {(mode === 'disable' || mode === 'regenerate') && <form className="security-form" onSubmit={mode === 'disable' ? disable : regenerate}>
      {passwordField}{codeField(mode === 'disable' ? 'Code from your app (or a recovery code)' : 'Code from your app')}
      {mode === 'regenerate' && <p className="form-hint">Your old recovery codes stop working.</p>}
      {errorBox}
      <div className="security-actions"><button type="button" className="button button-outline" onClick={() => reset()}>Cancel</button>
        <button className={mode === 'disable' ? 'button button-danger-outline' : 'button button-primary'} disabled={busy}>{busy ? 'Please wait…' : mode === 'disable' ? 'Turn off two-step sign-in' : 'Create new codes'}</button></div>
    </form>}
    {mode === 'idle' && errorBox}
  </section>
}
