import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { MapPin, MessageCircle } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import { fetchPerson, personKey } from '../social/people'
import { Avatar, FollowButton, RelationshipChips, formatCount } from './PersonBits'
import '../social.css'

const OPEN_DELAY = 380
const CLOSE_DELAY = 220
const CARD_WIDTH = 300

export async function openDirectChat(userId: number, navigate: ReturnType<typeof useNavigate>) {
  const { data } = await api.post<{ id: number }>('/conversations/start-direct/', { user_id: userId })
  navigate(`/messages?c=${data.id}`)
}

function HoverCardBody({ username, onClose }: { username: string; onClose: () => void }) {
  const navigate = useNavigate()
  const [messageError, setMessageError] = useState('')
  const { data: person, isLoading, error } = useQuery({ queryKey: personKey(username), queryFn: () => fetchPerson(username), staleTime: 60_000 })
  if (isLoading) return <div className="hover-card-loading"><span className="skeleton skeleton-avatar" /><span className="skeleton skeleton-line" /><span className="skeleton skeleton-line short" /></div>
  if (error || !person) return <div className="hover-card-loading">{getErrorMessage(error)}</div>
  const self = person.relationship?.is_self
  return <>
    <div className="hover-card-cover" />
    <div className="hover-card-head">
      <Link to={`/u/${person.username}`} onClick={onClose} className="hover-card-avatar-link"><Avatar person={person} size={58} /></Link>
      {!self && <FollowButton person={person} compact />}
    </div>
    <Link to={`/u/${person.username}`} onClick={onClose} className="hover-card-name"><strong>{person.display_name}</strong><span>@{person.username}</span></Link>
    {person.bio && <p className="hover-card-bio">{person.bio}</p>}
    {person.country && <div className="hover-card-meta"><MapPin size={12} /> {person.country}</div>}
    <div className="hover-card-stats">
      <span><strong>{formatCount(person.discussions_count)}</strong> posts</span>
      <span><strong>{formatCount(person.followers_count)}</strong> followers</span>
      <span><strong>{formatCount(person.following_count)}</strong> following</span>
    </div>
    <RelationshipChips person={person} />
    <div className="hover-card-actions">
      <Link to={`/u/${person.username}`} onClick={onClose} className="button button-outline">View profile</Link>
      {!self && <button type="button" className="button button-outline" onClick={() => { setMessageError(''); openDirectChat(person.id, navigate).then(onClose).catch((err) => setMessageError(getErrorMessage(err))) }}><MessageCircle size={14} /> Message</button>}
    </div>
    {messageError && <div className="error-message">{messageError}</div>}
  </>
}

/**
 * A link to someone's profile that shows a floating profile card on hover or keyboard
 * focus (like Instagram / Facebook / X). Touch taps simply follow the link.
 */
export default function UserLink({ username, children, className = '' }: { username: string; children: ReactNode; className?: string }) {
  const anchorRef = useRef<HTMLAnchorElement>(null)
  const cardRef = useRef<HTMLDivElement>(null)
  const openTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const touched = useRef(false)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<{ top: number; left: number; above: boolean }>({ top: 0, left: 0, above: false })

  const clearTimers = () => { clearTimeout(openTimer.current); clearTimeout(closeTimer.current) }
  const scheduleOpen = () => {
    if (touched.current) return
    clearTimers()
    openTimer.current = setTimeout(() => setOpen(true), OPEN_DELAY)
  }
  const scheduleClose = () => {
    clearTimeout(openTimer.current)
    closeTimer.current = setTimeout(() => setOpen(false), CLOSE_DELAY)
  }
  const close = () => { clearTimers(); setOpen(false) }

  useLayoutEffect(() => {
    if (!open || !anchorRef.current) return
    const rect = anchorRef.current.getBoundingClientRect()
    const cardHeight = cardRef.current?.offsetHeight || 300
    const above = rect.bottom + 10 + cardHeight > window.innerHeight && rect.top - 10 - cardHeight > 0
    const left = Math.min(Math.max(12, rect.left), window.innerWidth - CARD_WIDTH - 12)
    setPosition({ top: above ? rect.top - 10 - cardHeight : rect.bottom + 10, left, above })
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') close() }
    window.addEventListener('scroll', close, true)
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('scroll', close, true); window.removeEventListener('keydown', onKey) }
  }, [open])

  useEffect(() => clearTimers, [])

  return <>
    <Link
      ref={anchorRef}
      to={`/u/${username}`}
      className={`user-link ${className}`}
      onPointerDown={(event) => { touched.current = event.pointerType === 'touch' }}
      onMouseEnter={scheduleOpen}
      onMouseLeave={scheduleClose}
      onFocus={scheduleOpen}
      onBlur={scheduleClose}
      onClick={close}
      aria-haspopup="dialog"
      aria-expanded={open}
    >{children}</Link>
    {open && createPortal(
      <div
        ref={cardRef}
        className={`user-hover-card ${position.above ? 'above' : ''}`}
        style={{ top: position.top, left: position.left, width: CARD_WIDTH }}
        role="dialog"
        aria-label={`Profile preview for ${username}`}
        onMouseEnter={() => clearTimeout(closeTimer.current)}
        onMouseLeave={scheduleClose}
      >
        <HoverCardBody username={username} onClose={close} />
      </div>,
      document.body,
    )}
  </>
}
