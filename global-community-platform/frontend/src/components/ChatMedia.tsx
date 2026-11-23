import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Eye, EyeOff, Image as ImageIcon, Mic, Pause, Play, Repeat2, Send, Square, Timer, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import { getUploadConfig, uploadDirect } from '../services/uploads'
import { inspectVideo } from './StoryComposer'

export type ChatMediaMessage = {
  id: number
  sender: number
  kind: 'text' | 'photo' | 'video' | 'voice' | 'post' | 'system'
  body: string
  preview?: string
  media_url?: string
  thumb_url?: string
  width?: number | null
  height?: number | null
  duration_ms?: number | null
  processing?: string
  view_once?: boolean
  opened_by?: number[]
  shared_post?: { id: number; author: string; title: string; text: string; thumb_url: string; is_video: boolean } | null
  expires_at?: string | null
}

export const DISAPPEAR_OPTIONS: { seconds: number; label: string }[] = [
  { seconds: 0, label: 'Off' }, { seconds: 3600, label: '1 hour' }, { seconds: 86400, label: '24 hours' }, { seconds: 604800, label: '7 days' },
]

function clock(ms?: number | null) {
  const total = Math.max(0, Math.round((ms || 0) / 1000))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

/** A compact voice-message player (play/pause, progress, duration). */
function VoicePlayer({ src, durationMs }: { src: string; durationMs?: number | null }) {
  const audio = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const toggle = () => { const a = audio.current; if (!a) return; if (a.paused) void a.play(); else a.pause() }
  return <div className="voice-player">
    <button type="button" className="voice-play" aria-label={playing ? 'Pause voice message' : 'Play voice message'} onClick={toggle}>{playing ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}</button>
    <div className="voice-track" aria-hidden="true"><span style={{ width: `${progress * 100}%` }} /></div>
    <span className="voice-time">{clock(playing || elapsed ? elapsed * 1000 : durationMs)}</span>
    <audio ref={audio} src={src} preload="none" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
      onEnded={() => { setPlaying(false); setProgress(0); setElapsed(0) }}
      onTimeUpdate={(e) => { const a = e.currentTarget; setElapsed(a.currentTime); if (a.duration && Number.isFinite(a.duration)) setProgress(a.currentTime / a.duration) }} />
  </div>
}

/** Full-screen viewer for a view-once photo/video: closes on tap, after 10 s (photos) or at the end (videos). */
function OnceViewer({ url, kind, onClose }: { url: string; kind: 'photo' | 'video'; onClose: () => void }) {
  useEffect(() => {
    if (kind !== 'photo') return
    const timer = setTimeout(onClose, 10_000)
    return () => clearTimeout(timer)
  }, [kind, onClose])
  return createPortal(<div className="once-viewer" role="dialog" aria-modal="true" aria-label="View-once media" onClick={onClose} onContextMenu={(e) => e.preventDefault()}>
    {kind === 'photo' ? <img src={url} alt="View-once photo" draggable={false} /> : <video src={url} autoPlay playsInline onEnded={onClose} />}
    <span className="once-hint"><Eye size={14} /> View once · tap to close</span>
  </div>, document.body)
}

function Lightbox({ url, onClose }: { url: string; onClose: () => void }) {
  return createPortal(<div className="once-viewer" role="dialog" aria-modal="true" aria-label="Photo" onClick={onClose}>
    <img src={url} alt="" />
    <button type="button" className="once-close" aria-label="Close"><X size={22} /></button>
  </div>, document.body)
}

/** Renders the inside of a chat bubble for every kind of message. */
export function MessageBody({ message, own, conversationId, currentUserId, onChanged }: {
  message: ChatMediaMessage; own: boolean; conversationId: number; currentUserId?: number; onChanged?: () => void
}) {
  const [viewing, setViewing] = useState<string | null>(null)
  const [zoom, setZoom] = useState(false)
  const [error, setError] = useState('')
  const kind = message.kind || 'text'
  const ratio = message.width && message.height ? `${message.width} / ${message.height}` : undefined

  if (message.view_once && (kind === 'photo' || kind === 'video')) {
    const label = kind === 'photo' ? 'Photo' : 'Video'
    const openedByMe = currentUserId !== undefined && (message.opened_by || []).includes(currentUserId)
    const open = async () => {
      setError('')
      try {
        const { data } = await api.post<{ url: string }>(`/conversations/${conversationId}/messages/${message.id}/open/`)
        setViewing(data.url)
      } catch (err) { setError(getErrorMessage(err)); onChanged?.() }
    }
    return <div className="chat-once">
      {own ? <span className="chat-once-chip"><Eye size={15} /> {label} · {(message.opened_by || []).length ? 'Opened' : 'Delivered'}</span>
        : openedByMe ? <span className="chat-once-chip is-opened"><EyeOff size={15} /> {label} · Opened</span>
        : <button type="button" className="chat-once-chip is-new" onClick={() => void open()}><Eye size={15} /> Tap to view {label.toLowerCase()}</button>}
      {error && <small className="chat-media-error">{error}</small>}
      {viewing && <OnceViewer url={viewing} kind={kind} onClose={() => { setViewing(null); onChanged?.() }} />}
    </div>
  }
  if (kind === 'photo') {
    return <div className="chat-media">
      {message.media_url ? <button type="button" className="chat-photo" style={{ aspectRatio: ratio }} onClick={() => setZoom(true)} aria-label="Open photo">
        <img src={message.thumb_url || message.media_url} alt={message.body || 'Photo'} loading="lazy" />
      </button> : <span className="chat-media-gone">Photo unavailable</span>}
      {message.body && <p className="chat-media-caption">{message.body}</p>}
      {zoom && message.media_url && <Lightbox url={message.media_url} onClose={() => setZoom(false)} />}
    </div>
  }
  if (kind === 'video') {
    return <div className="chat-media">
      {message.processing === 'failed' || !message.media_url ? <span className="chat-media-gone">This video couldn't be processed.</span>
        : <video className="chat-video" src={message.media_url} poster={message.thumb_url || undefined} controls playsInline preload="none" style={{ aspectRatio: ratio }} />}
      {message.body && <p className="chat-media-caption">{message.body}</p>}
    </div>
  }
  if (kind === 'voice') {
    return message.media_url ? <VoicePlayer src={message.media_url} durationMs={message.duration_ms} /> : <span className="chat-media-gone">Voice message unavailable</span>
  }
  if (kind === 'post') {
    const post = message.shared_post
    return <div className="chat-media">
      {post ? <Link to={`/discussions/${post.id}`} className="chat-shared-post">
        {post.thumb_url && <img src={post.thumb_url} alt="" loading="lazy" />}
        <span><small><Repeat2 size={12} /> @{post.author}</small><strong>{post.title || post.text || (post.is_video ? 'Video' : 'Photo')}</strong>{post.title && post.text && <em>{post.text}</em>}</span>
      </Link> : <span className="chat-media-gone">This post is no longer available.</span>}
      {message.body && <p className="chat-media-caption">{message.body}</p>}
    </div>
  }
  return <>{message.body}</>
}

type Draft = { file: File; url: string; kind: 'photo' | 'video'; seconds?: number; poster?: Blob | null }

/** Attach photos/videos (optionally view-once) and record voice messages. */
export function ChatAttachments({ conversationId, onSent, disabled }: { conversationId: number; onSent: () => void; disabled?: boolean }) {
  const picker = useRef<HTMLInputElement>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [caption, setCaption] = useState('')
  const [once, setOnce] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [recording, setRecording] = useState(false)
  const [recordMs, setRecordMs] = useState(0)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const started = useRef(0)
  const cancelled = useRef(false)

  useEffect(() => () => { if (draft) URL.revokeObjectURL(draft.url) }, [draft])
  useEffect(() => {
    if (!recording) return
    const timer = setInterval(() => {
      const ms = Date.now() - started.current
      setRecordMs(ms)
      if (ms >= 5 * 60 * 1000) recorder.current?.stop()
    }, 200)
    return () => clearInterval(timer)
  }, [recording])

  const send = async (file: Blob & { name?: string }, kind: 'photo' | 'video' | 'voice', extra: Record<string, string | Blob> = {}) => {
    setError(''); setProgress(0)
    try {
      const config = await getUploadConfig()
      const form = new FormData()
      form.append('kind', kind)
      if (config.direct) form.append('file_key', await uploadDirect(file, `chat-${kind}`, (part) => setProgress(part * 0.95)))
      else form.append('file', file, file.name || `${kind}.${kind === 'voice' ? 'webm' : 'bin'}`)
      for (const [key, value] of Object.entries(extra)) form.append(key, value)
      await api.post(`/conversations/${conversationId}/media/`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
      onSent()
      return true
    } catch (err) { setError(getErrorMessage(err)); return false } finally { setProgress(null) }
  }

  const choose = async (file: File | undefined) => {
    setError('')
    if (!file) return
    if (file.type.startsWith('image/')) { setDraft({ file, url: URL.createObjectURL(file), kind: 'photo' }); return }
    if (file.type.startsWith('video/')) {
      if (file.size > 50 * 1024 * 1024) { setError('Videos in chat can be up to 50 MB.'); return }
      let info: { seconds: number; poster: Blob | null } = { seconds: 0, poster: null }
      try { info = await inspectVideo(file) } catch { /* poster is optional */ }
      setDraft({ file, url: URL.createObjectURL(file), kind: 'video', seconds: info.seconds, poster: info.poster })
      return
    }
    setError('Choose a photo or a video.')
  }

  const sendDraft = async () => {
    if (!draft) return
    const extra: Record<string, string | Blob> = { caption, view_once: once ? 'true' : 'false' }
    if (draft.kind === 'video') {
      if (draft.seconds) extra.duration_ms = String(Math.round(draft.seconds * 1000))
      if (draft.poster) extra.poster = new File([draft.poster], 'poster.jpg', { type: 'image/jpeg' })
    }
    if (await send(draft.file, draft.kind, extra)) { setDraft(null); setCaption(''); setOnce(false) }
  }

  const startRecording = async () => {
    setError('')
    if (typeof MediaRecorder === 'undefined' || !navigator.mediaDevices?.getUserMedia) { setError("This browser can't record voice messages."); return }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      const type = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find((t) => MediaRecorder.isTypeSupported?.(t))
      const rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined)
      chunks.current = []
      cancelled.current = false
      rec.ondataavailable = (e) => { if (e.data.size) chunks.current.push(e.data) }
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        setRecording(false)
        const ms = Date.now() - started.current
        if (cancelled.current || ms < 700) return
        const mime = (rec.mimeType || 'audio/webm').split(';')[0]
        const ext = mime.includes('mp4') ? 'm4a' : mime.includes('ogg') ? 'ogg' : 'weba'
        void send(new File(chunks.current, `voice.${ext}`, { type: mime }), 'voice', { duration_ms: String(ms) })
      }
      recorder.current = rec
      started.current = Date.now()
      setRecordMs(0)
      rec.start()
      setRecording(true)
    } catch (err) {
      const name = (err as { name?: string })?.name
      setError(name === 'NotAllowedError' ? 'Allow microphone access to record voice messages.' : getErrorMessage(err))
    }
  }
  const stopRecording = (discard = false) => { cancelled.current = discard; recorder.current?.stop() }

  return <>
    {recording ? <div className="chat-recording" role="status">
      <span className="rec-dot" aria-hidden="true" /> Recording {clock(recordMs)}
      <button type="button" className="icon-button" aria-label="Cancel recording" onClick={() => stopRecording(true)}><X size={17} /></button>
      <button type="button" className="chat-rec-send" aria-label="Send voice message" onClick={() => stopRecording(false)}><Square size={13} fill="currentColor" /> Send</button>
    </div> : <div className="chat-attach">
      <input ref={picker} type="file" accept="image/*,video/*" hidden onChange={(e) => { void choose(e.target.files?.[0]); e.target.value = '' }} />
      <button type="button" className="icon-button" aria-label="Send a photo or video" title="Photo or video" disabled={disabled || progress !== null} onClick={() => picker.current?.click()}><ImageIcon size={19} /></button>
      <button type="button" className="icon-button" aria-label="Record a voice message" title="Voice message" disabled={disabled || progress !== null} onClick={() => void startRecording()}><Mic size={19} /></button>
    </div>}
    {progress !== null && <div className="chat-upload-progress" role="status">Sending… {Math.round(progress * 100)}%</div>}
    {error && <div className="chat-attach-error" role="alert" onClick={() => setError('')}>{error}</div>}
    {draft && createPortal(<div className="sheet-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget && progress === null) setDraft(null) }}>
      <div className="sheet chat-draft" role="dialog" aria-modal="true" aria-label={`Send ${draft.kind}`}>
        <div className="sheet-head"><strong>Send {draft.kind}</strong><button type="button" className="icon-button" aria-label="Cancel" disabled={progress !== null} onClick={() => setDraft(null)}><X size={18} /></button></div>
        {draft.kind === 'photo' ? <img className="chat-draft-media" src={draft.url} alt="Preview" /> : <video className="chat-draft-media" src={draft.url} controls playsInline />}
        <label className="chat-once-toggle"><input type="checkbox" checked={once} onChange={(e) => setOnce(e.target.checked)} /><Eye size={16} /> View once <small>They can open it one time, then it's gone</small></label>
        {!once && <input className="chat-draft-caption" value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={1000} placeholder="Add a caption…" aria-label="Caption" />}
        {error && <p className="sheet-error">{error}</p>}
        <div className="sheet-row"><button type="button" className="button button-primary" disabled={progress !== null} onClick={() => void sendDraft()}><Send size={15} /> {progress !== null ? `Sending ${Math.round(progress * 100)}%` : 'Send'}</button></div>
      </div>
    </div>, document.body)}
  </>
}

export function disappearLabel(seconds?: number) {
  return DISAPPEAR_OPTIONS.find((o) => o.seconds === seconds)?.label ?? ''
}

export function DisappearingBadge({ seconds }: { seconds?: number }) {
  if (!seconds) return null
  return <span className="chat-disappear-badge" title={`Messages disappear after ${disappearLabel(seconds)}`}><Timer size={13} /> {disappearLabel(seconds)}</span>
}
