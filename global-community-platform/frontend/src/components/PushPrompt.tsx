import { useEffect, useState } from 'react'
import { BellRing, X } from 'lucide-react'
import { enablePush, getPushState, type PushState } from '../services/push'

const KEY = 'cg-push-prompt-dismissed-at'
const QUIET_DAYS = 7

function dismissedRecently() {
  try { return Date.now() - Number(localStorage.getItem(KEY) || 0) < QUIET_DAYS * 86400e3 } catch { return false }
}
function remember() { try { localStorage.setItem(KEY, String(Date.now())) } catch { /* private mode */ } }

/**
 * Asks a signed-in member to turn on push notifications for this device, so messages,
 * calls and replies reach them when CommonGround isn't open. Without this, nobody
 * subscribes unless they find the switch in Notification settings.
 *
 * Shown only when push is available here and not yet on. The browser's permission
 * prompt can only be opened from a click, so the banner asks first.
 */
export default function PushPrompt() {
  const [state, setState] = useState<PushState | null>(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState('')

  useEffect(() => {
    if (dismissedRecently()) return
    let cancelled = false
    // Let the page settle first; don't compete with the first screen for attention.
    const timer = setTimeout(() => {
      getPushState().then((next) => { if (!cancelled) setState(next) }).catch(() => { /* not available: stay hidden */ })
    }, 4000)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [])

  if (state !== 'off') return null

  const close = () => { setState(null); remember() }
  const turnOn = async () => {
    setBusy(true); setFailed('')
    try {
      const next = await enablePush()
      if (next === 'on') { setState(null); return }
      // Blocked or unavailable: stop asking on this device for a while.
      setState(null); remember()
    } catch {
      setFailed("This browser couldn't reach its push service. Check your connection, or turn this on later in Notification settings.")
    } finally { setBusy(false) }
  }

  return <div className="install-prompt push-prompt" role="dialog" aria-label="Turn on notifications">
    <div className="push-prompt-icon" aria-hidden="true"><BellRing size={20} /></div>
    <div className="install-copy">
      <strong>Get notified when CommonGround is closed</strong>
      <span>{failed || 'Messages, calls and replies, on this device.'}</span>
    </div>
    <button type="button" className="install-button" disabled={busy} onClick={() => void turnOn()}>Turn on</button>
    <button type="button" className="icon-button" aria-label="Not now" onClick={close}><X size={17} /></button>
  </div>
}
