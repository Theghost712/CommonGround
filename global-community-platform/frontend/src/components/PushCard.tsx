import { useEffect, useState } from 'react'
import { BellRing, Smartphone } from 'lucide-react'
import { api, getErrorMessage } from '../services/api'
import { disablePush, enablePush, getPushState, type PushState } from '../services/push'

const explain: Record<PushState, string> = {
  on: 'This device gets notifications even when CommonGround is closed.',
  off: 'Get messages, calls and replies on this device even when CommonGround is closed.',
  denied: 'Notifications are blocked for this site. Allow them in your browser or phone settings, then come back.',
  'server-off': "Push notifications aren't set up on this server yet.",
  unsupported: "This browser can't receive push notifications. Try Chrome, Edge, Firefox or Samsung Internet.",
  'needs-install': 'On iPhone and iPad: tap Share, then "Add to Home Screen", open CommonGround from the new icon, and turn this on there.',
}

export default function PushCard() {
  const [state, setState] = useState<PushState | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => { getPushState().then(setState).catch(() => setState('unsupported')) }, [])

  const run = async (action: () => Promise<PushState>) => {
    setBusy(true); setNote(null)
    try { setState(await action()) } catch (err) {
      // Errors from the browser's own push service (offline, blocked by a VPN or ad blocker, no Google services).
      const text = err instanceof DOMException
        ? "This browser couldn't reach its push service. Check your connection and try again, or try another browser."
        : getErrorMessage(err)
      setNote({ ok: false, text })
    } finally { setBusy(false) }
  }
  const test = async () => {
    setBusy(true); setNote(null)
    try { setNote({ ok: true, text: (await api.post<{ detail: string }>('/push/test/')).data.detail + ' Lock your phone or switch apps to see it.' }) }
    catch (err) { setNote({ ok: false, text: getErrorMessage(err) }) } finally { setBusy(false) }
  }

  if (!state) return null
  return <div className="preference-row push-card">
    <div className="preference-icon">{state === 'on' ? <BellRing size={18} /> : <Smartphone size={18} />}</div>
    <div className="preference-copy"><strong>Push notifications on this device {state === 'on' && <span className="push-badge">On</span>}</strong><span>{explain[state]}</span>
      {note && <span className={note.ok ? 'push-note is-ok' : 'push-note is-error'} role="status">{note.text}</span>}
    </div>
    <div className="push-actions">
      {state === 'off' && <button type="button" className="button button-primary" disabled={busy} onClick={() => run(enablePush)}>Turn on</button>}
      {state === 'on' && <>
        <button type="button" className="text-button" disabled={busy} onClick={test}>Send a test</button>
        <button type="button" className="button button-outline" disabled={busy} onClick={() => run(disablePush)}>Turn off</button>
      </>}
    </div>
  </div>
}
