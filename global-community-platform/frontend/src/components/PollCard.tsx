import { useState } from 'react'
import { Check, Clock3 } from 'lucide-react'
import { api, getErrorMessage } from '../services/api'
import type { Poll } from '../types'

export function timeLeft(closesAt: string | null, now = Date.now()): string {
  if (!closesAt) return ''
  const ms = new Date(closesAt).getTime() - now
  if (ms <= 0) return 'Final results'
  const hours = Math.floor(ms / 3_600_000)
  if (hours >= 24) { const days = Math.round(hours / 24); return `${days} ${days === 1 ? 'day' : 'days'} left` }
  if (hours >= 1) return `${hours} ${hours === 1 ? 'hour' : 'hours'} left`
  const minutes = Math.max(1, Math.ceil(ms / 60_000))
  return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'} left`
}

/** Vote, see results (after voting), change or take back a vote. */
export default function PollCard({ postId, poll: initial }: { postId: number; poll: Poll }) {
  const [poll, setPoll] = useState(initial)
  const [picked, setPicked] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const voted = poll.my_votes.length > 0
  const showResults = poll.results_visible

  const send = async (optionIds: number[] | null) => {
    setBusy(true); setError('')
    try {
      const url = `/discussions/${postId}/vote/`
      const { data } = optionIds ? await api.post<Poll>(url, { option_ids: optionIds }) : await api.delete<Poll>(url)
      setPoll(data); setPicked([])
    } catch (err) { setError(getErrorMessage(err)) } finally { setBusy(false) }
  }
  const choose = (id: number) => {
    if (poll.allows_multiple) setPicked((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id])
    else void send([id])
  }

  return <section className="poll-card" aria-label={`Poll: ${poll.question}`}>
    <h3>{poll.question}</h3>
    {poll.allows_multiple && !showResults && <p className="poll-hint">Choose one or more</p>}
    <ul>
      {poll.options.map((option) => {
        const mine = poll.my_votes.includes(option.id)
        if (showResults) {
          return <li key={option.id} className={`poll-result ${mine ? 'is-mine' : ''}`}>
            <i style={{ width: `${option.percent ?? 0}%` }} aria-hidden="true" />
            <span>{option.text}{mine && <Check size={14} aria-label="Your vote" />}</span>
            <strong>{option.percent ?? 0}%</strong>
          </li>
        }
        const selected = picked.includes(option.id)
        return <li key={option.id}>
          <button type="button" className={`poll-option ${selected ? 'is-selected' : ''}`} aria-pressed={poll.allows_multiple ? selected : undefined} disabled={busy || poll.is_closed} onClick={() => choose(option.id)}>{option.text}</button>
        </li>
      })}
    </ul>
    {poll.allows_multiple && !showResults && <button type="button" className="button button-primary poll-submit" disabled={busy || picked.length === 0} onClick={() => void send(picked)}>Vote</button>}
    <footer>
      <span>{poll.total_voters} {poll.total_voters === 1 ? 'vote' : 'votes'}</span>
      {poll.closes_at && <span><Clock3 size={12} /> {timeLeft(poll.closes_at)}</span>}
      {voted && !poll.is_closed && <button type="button" className="text-button" disabled={busy} onClick={() => void send(null)}>Undo vote</button>}
    </footer>
    {error && <div className="error-message">{error}</div>}
  </section>
}
