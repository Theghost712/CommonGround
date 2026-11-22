import { useCallback, useEffect, useRef, useState, type FormEvent, type PointerEvent } from 'react'
import { createPortal } from 'react-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Eye, Flag, Lock, Pause, Play, Send, Trash2, Volume2, VolumeX, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import type { Person, StoryTrayEntry } from '../types'
import { timeAgo } from './FeedPost'
import { Avatar } from './PersonBits'
import ReportDialog from './ReportDialog'

type Viewer = { viewed_at: string; person: Person }
const HOLD_MS = 220

/**
 * Full-screen story player. Tap right/left to move, hold to pause, swipe down or Esc
 * to close, arrows on the keyboard. Moves on to the next person automatically.
 */
export default function StoryViewer({ entries, startIndex = 0, onClose }: { entries: StoryTrayEntry[]; startIndex?: number; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [userIndex, setUserIndex] = useState(startIndex)
  const [storyIndex, setStoryIndex] = useState(() => {
    const first = entries[startIndex]?.stories.findIndex((story) => !story.seen) ?? 0
    return first > 0 ? first : 0
  })
  const [progress, setProgress] = useState(0)
  const [paused, setPaused] = useState(false)
  const [muted, setMuted] = useState(true)
  const [reply, setReply] = useState('')
  const [toast, setToast] = useState('')
  const [viewers, setViewers] = useState<Viewer[] | null>(null)
  const [deleted, setDeleted] = useState<Set<number>>(new Set())
  const [reporting, setReporting] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const pressTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const held = useRef(false)
  const touchStartY = useRef<number | null>(null)
  const marked = useRef<Set<number>>(new Set())

  const entry = entries[userIndex]
  const stories = entry ? entry.stories.filter((story) => !deleted.has(story.id)) : []
  const story = stories[storyIndex]
  const own = Boolean(story?.is_own)
  const typing = reply.length > 0
  const isPaused = paused || typing || viewers !== null || reporting

  const next = useCallback(() => {
    setProgress(0)
    if (storyIndex < stories.length - 1) setStoryIndex(storyIndex + 1)
    else if (userIndex < entries.length - 1) { setUserIndex(userIndex + 1); setStoryIndex(0) }
    else onClose()
  }, [storyIndex, stories.length, userIndex, entries.length, onClose])

  const previous = useCallback(() => {
    setProgress(0)
    if (storyIndex > 0) setStoryIndex(storyIndex - 1)
    else if (userIndex > 0) { setUserIndex(userIndex - 1); setStoryIndex(Math.max(0, entries[userIndex - 1].stories.length - 1)) }
  }, [storyIndex, userIndex, entries])

  // Mark each story as seen once it is on screen.
  useEffect(() => {
    if (!story || story.is_own || marked.current.has(story.id)) return
    marked.current.add(story.id)
    void api.post(`/stories/${story.id}/view/`).catch(() => {})
  }, [story])

  // Close the tray cache over: refresh rings when the viewer closes.
  useEffect(() => () => { queryClient.invalidateQueries({ queryKey: ['story-tray'] }) }, [queryClient])

  // Timer for photos and text; videos report their own progress.
  useEffect(() => {
    if (!story || story.media_type === 'video' || isPaused) return
    const started = performance.now() - progress * story.duration_ms
    let frame = 0
    const tick = (now: number) => {
      const value = Math.min(1, (now - started) / story.duration_ms)
      setProgress(value)
      if (value >= 1) next()
      else frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [story?.id, isPaused, next])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (isPaused) video.pause()
    else void video.play().catch(() => setMuted(true))
  }, [isPaused, story?.id])

  // Preload the next photo so there is no blank flash.
  useEffect(() => {
    const upcoming = stories[storyIndex + 1] ?? entries[userIndex + 1]?.stories[0]
    if (upcoming?.media_type === 'image' && upcoming.media_url) { const img = new Image(); img.src = upcoming.media_url }
  }, [stories, storyIndex, entries, userIndex])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement)?.tagName === 'INPUT') return
      if (event.key === 'Escape') onClose()
      else if (event.key === 'ArrowRight') next()
      else if (event.key === 'ArrowLeft') previous()
      else if (event.key === ' ') { event.preventDefault(); setPaused((value) => !value) }
    }
    window.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = overflow }
  }, [next, previous, onClose])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(''), 2000)
    return () => clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    if (entry && stories.length === 0) next()
  }, [entry, stories.length, next])

  if (!entry || !story) return null

  const onPointerDown = () => {
    held.current = false
    pressTimer.current = setTimeout(() => { held.current = true; setPaused(true) }, HOLD_MS)
  }
  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    clearTimeout(pressTimer.current)
    if (held.current) { held.current = false; setPaused(false); return }
    const rect = event.currentTarget.getBoundingClientRect()
    if (event.clientX - rect.left < rect.width * 0.3) previous()
    else next()
  }

  const sendReply = async (event: FormEvent) => {
    event.preventDefault()
    const body = reply.trim()
    if (!body) return
    try {
      await api.post(`/stories/${story.id}/reply/`, { body })
      setReply('')
      setToast('Reply sent')
    } catch (err) {
      setToast(getErrorMessage(err))
    }
  }

  const openViewers = async () => {
    setViewers([])
    try {
      const { data } = await api.get<{ count: number; viewers: Viewer[] }>(`/stories/${story.id}/viewers/`)
      setViewers(data.viewers)
    } catch (err) {
      setViewers(null)
      setToast(getErrorMessage(err))
    }
  }

  const remove = async () => {
    if (!window.confirm('Delete this story? It will disappear for everyone.')) return
    try {
      await api.delete(`/stories/${story.id}/`)
      setDeleted((current) => new Set(current).add(story.id))
      setProgress(0)
      setStoryIndex((index) => Math.max(0, Math.min(index, stories.length - 2)))
      setToast('Story deleted')
      queryClient.invalidateQueries({ queryKey: ['story-tray'] })
    } catch (err) {
      setToast(getErrorMessage(err))
    }
  }

  return createPortal(<div className="story-viewer" role="dialog" aria-modal="true" aria-label={`Stories from ${entry.user.username}`}
    onTouchStart={(event) => { touchStartY.current = event.touches[0].clientY }}
    onTouchEnd={(event) => { if (touchStartY.current !== null && event.changedTouches[0].clientY - touchStartY.current > 90) onClose(); touchStartY.current = null }}>
    <button type="button" className="story-viewer-close" aria-label="Close stories" onClick={onClose}><X size={26} /></button>
    {userIndex > 0 && <button type="button" className="story-viewer-jump prev" aria-label="Previous person" onClick={() => { setUserIndex(userIndex - 1); setStoryIndex(0); setProgress(0) }}><ChevronLeft size={22} /></button>}
    {userIndex < entries.length - 1 && <button type="button" className="story-viewer-jump next" aria-label="Next person" onClick={() => { setUserIndex(userIndex + 1); setStoryIndex(0); setProgress(0) }}><ChevronRight size={22} /></button>}

    <div className="story-frame">
      <div className="story-progress" aria-hidden="true">{stories.map((item, index) => <span key={item.id}><i style={{ width: `${index < storyIndex ? 100 : index === storyIndex ? progress * 100 : 0}%` }} /></span>)}</div>
      <header className="story-head">
        <Link to={`/u/${entry.user.username}`} onClick={onClose} className="story-head-who"><Avatar person={entry.user} size={34} /><strong>{entry.user.username}</strong></Link>
        <time>{timeAgo(story.created_at)}</time>
        {story.audience === 'close_friends' && <span className="story-cf-badge" title="Close friends only"><Lock size={11} /> Close friends</span>}
        <span className="story-head-actions">
          {story.media_type === 'video' && <button type="button" aria-label={muted ? 'Unmute' : 'Mute'} onClick={() => setMuted(!muted)}>{muted ? <VolumeX size={20} /> : <Volume2 size={20} />}</button>}
          <button type="button" aria-label={paused ? 'Play' : 'Pause'} onClick={() => setPaused(!paused)}>{paused ? <Play size={20} /> : <Pause size={20} />}</button>
          {!own && <button type="button" aria-label="Report story" onClick={() => setReporting(true)}><Flag size={18} /></button>}
        </span>
      </header>

      <div className="story-stage" onPointerDown={onPointerDown} onPointerUp={onPointerUp} onPointerLeave={() => clearTimeout(pressTimer.current)} onContextMenu={(event) => event.preventDefault()}>
        {story.media_type === 'image' && <img src={story.media_url} alt={story.alt_text || `Story from ${entry.user.username}`} draggable={false} />}
        {story.media_type === 'video' && <video
          key={story.id}
          ref={videoRef}
          src={story.media_url}
          poster={story.thumbnail_url || undefined}
          muted={muted}
          playsInline
          autoPlay
          aria-label={story.alt_text || `Video story from ${entry.user.username}`}
          onTimeUpdate={(event) => { const v = event.currentTarget; if (v.duration) setProgress(v.currentTime / v.duration) }}
          onEnded={next}
        />}
        {story.media_type === 'text' && <div className={`story-text-card bg-${story.background}`}><p>{story.text}</p></div>}
        {story.media_type !== 'text' && story.text && <p className="story-caption">{story.text}</p>}
      </div>

      <footer className="story-foot">
        {own
          ? <div className="story-own-bar">
              <button type="button" onClick={() => void openViewers()}><Eye size={18} /> Seen by {story.view_count ?? 0}</button>
              <button type="button" onClick={() => void remove()} aria-label="Delete story"><Trash2 size={18} /> Delete</button>
            </div>
          : <form className="story-reply" onSubmit={sendReply}>
              <input value={reply} onChange={(event) => setReply(event.target.value)} placeholder={`Reply to ${entry.user.username}…`} aria-label={`Reply to ${entry.user.username}`} maxLength={1000} />
              <button type="submit" aria-label="Send reply" disabled={!reply.trim()}><Send size={20} /></button>
            </form>}
      </footer>
      {toast && <div className="story-toast" role="status">{toast}</div>}
      {reporting && <ReportDialog targetType="story" targetId={story.id} onClose={() => setReporting(false)} />}

      {viewers !== null && <div className="story-viewers" role="dialog" aria-label="Story viewers">
        <div className="story-viewers-head"><strong><Eye size={16} /> {story.view_count ?? 0} {story.view_count === 1 ? 'view' : 'views'}</strong><button type="button" aria-label="Close viewers" onClick={() => setViewers(null)}><X size={18} /></button></div>
        {viewers.length === 0 ? <p>{story.view_count ? 'Loading…' : 'No one has seen this yet.'}</p> : <ul>{viewers.map((item) => <li key={item.person.id}><Link to={`/u/${item.person.username}`} onClick={onClose}><Avatar person={item.person} size={36} /><span><strong>{item.person.username}</strong><small>{item.person.display_name}</small></span></Link><time>{timeAgo(item.viewed_at)}</time></li>)}</ul>}
      </div>}
    </div>
  </div>, document.body)
}
