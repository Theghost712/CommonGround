import { useEffect, useRef, useState } from 'react'
import { api } from '../services/api'

type GoogleId = {
  accounts: { id: {
    initialize: (options: { client_id: string; callback: (response: { credential: string }) => void; ux_mode?: string; auto_select?: boolean; cancel_on_tap_outside?: boolean }) => void
    renderButton: (element: HTMLElement, options: Record<string, unknown>) => void
  } }
}
declare global { interface Window { google?: GoogleId } }

let providers: Promise<string> | null = null
const clientId = () => (providers ??= api.get<{ google_client_id: string }>('/auth/providers/').then(({ data }) => data.google_client_id || '').catch(() => { providers = null; return '' }))

let script: Promise<void> | null = null
function loadScript() {
  script ??= new Promise((resolve, reject) => {
    const tag = document.createElement('script')
    tag.src = 'https://accounts.google.com/gsi/client'
    tag.async = true
    tag.onload = () => resolve()
    tag.onerror = () => { script = null; reject(new Error('Google sign-in could not load.')) }
    document.head.appendChild(tag)
  })
  return script
}

/** Google's official "Continue with Google" button. Renders nothing until the server has a client id. */
export default function GoogleButton({ onCredential, text = 'continue_with' }: { onCredential: (credential: string) => void; text?: 'continue_with' | 'signup_with' | 'signin_with' }) {
  const box = useRef<HTMLDivElement>(null)
  const [available, setAvailable] = useState(false)
  const callback = useRef(onCredential)
  callback.current = onCredential

  useEffect(() => {
    let cancelled = false
    void clientId().then(async (id) => {
      if (!id || cancelled) return
      setAvailable(true)
      try { await loadScript() } catch { if (!cancelled) setAvailable(false); return }
      if (cancelled || !box.current || !window.google) return
      window.google.accounts.id.initialize({ client_id: id, callback: (response) => callback.current(response.credential), cancel_on_tap_outside: true })
      window.google.accounts.id.renderButton(box.current, { theme: 'outline', size: 'large', shape: 'pill', text, width: Math.min(box.current.clientWidth || 320, 400), logo_alignment: 'center' })
    })
    return () => { cancelled = true }
  }, [text])

  if (!available) return null
  return <div className="google-signin">
    <div className="auth-divider"><span>or</span></div>
    <div ref={box} className="google-button" />
  </div>
}
