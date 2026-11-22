import { useState } from 'react'
import { createPortal } from 'react-dom'
import { CheckCircle2, Flag, X } from 'lucide-react'
import { api, getErrorMessage } from '../services/api'

export type ReportTarget = 'user' | 'post' | 'comment' | 'story' | 'message'

const REASONS: [string, string][] = [
  ['spam', 'Spam'],
  ['harassment', 'Bullying or harassment'],
  ['hate', 'Hate speech or symbols'],
  ['violence', 'Violence or threats'],
  ['nudity', 'Nudity or sexual content'],
  ['self_harm', 'Suicide or self-harm'],
  ['scam', 'Scam or fraud'],
  ['false_info', 'False information'],
  ['impersonation', 'Pretending to be someone else'],
  ['ip', 'Intellectual property'],
  ['other', 'Something else'],
]
const NOUN: Record<ReportTarget, string> = { user: 'account', post: 'post', comment: 'comment', story: 'story', message: 'message' }

/** Anonymous report flow: pick a reason, optional details, confirmation. */
export default function ReportDialog({ targetType, targetId, onClose }: { targetType: ReportTarget; targetId: number; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const [details, setDetails] = useState('')
  const [sending, setSending] = useState(false)
  const [done, setDone] = useState<string | null>(null)
  const [error, setError] = useState('')

  const send = async () => {
    setSending(true); setError('')
    try {
      const { data } = await api.post<{ already_reported: boolean }>('/safety/reports/', { target_type: targetType, target_id: targetId, reason, details: details.trim() })
      setDone(data.already_reported ? 'You already reported this. We will review it.' : 'Thanks for letting us know. Your report is anonymous.')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setSending(false)
    }
  }

  return createPortal(<div className="story-composer-backdrop report-backdrop" onClick={onClose}>
    <section className="report-dialog" role="dialog" aria-modal="true" aria-label={`Report ${NOUN[targetType]}`} onClick={(event) => event.stopPropagation()}>
      <header><strong><Flag size={16} /> Report {NOUN[targetType]}</strong><button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button></header>
      {done
        ? <div className="report-done"><CheckCircle2 size={40} /><p>{done}</p><button type="button" className="button button-primary" onClick={onClose}>Done</button></div>
        : <>
            <p className="report-intro">Why are you reporting this {NOUN[targetType]}? The person won&apos;t know who reported it.</p>
            <div className="report-reasons" role="radiogroup" aria-label="Reason">
              {REASONS.map(([value, label]) => <label key={value} className={reason === value ? 'active' : ''}><input type="radio" name="report-reason" value={value} checked={reason === value} onChange={() => setReason(value)} />{label}</label>)}
            </div>
            {reason && <textarea value={details} onChange={(event) => setDetails(event.target.value)} maxLength={1000} rows={3} placeholder="Anything else we should know? (optional)" aria-label="Details" />}
            {error && <div className="error-message">{error}</div>}
            <button type="button" className="button button-primary" disabled={!reason || sending} onClick={() => void send()}>{sending ? 'Sending…' : 'Submit report'}</button>
          </>}
    </section>
  </div>, document.body)
}
