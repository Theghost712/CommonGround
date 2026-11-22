import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clapperboard, ListChecks, Plus, Trash2, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import type { Community, Discussion, Paginated } from '../types'
import { DISCUSSION_TOPICS } from '../pages/CreateDiscussionPage'
import { inspectVideo } from './StoryComposer'
import { formatDuration } from './VideoPlayer'

export const MAX_VIDEO_MB = 100
export const MAX_VIDEO_SECONDS = 180
export const MAX_POLL_OPTIONS = 6
const CAPTION_LIMIT = 2200
export const POLL_DURATIONS = [{ hours: 1, label: '1 hour' }, { hours: 24, label: '1 day' }, { hours: 72, label: '3 days' }, { hours: 168, label: '1 week' }]

function useAudience() {
  const [category, setCategory] = useState('General')
  const [community, setCommunity] = useState('')
  const { data } = useQuery({ queryKey: ['communities'], queryFn: async () => (await api.get<Paginated<Community> | Community[]>('/communities/')).data })
  const communities = (Array.isArray(data) ? data : data?.results || []).filter((item) => item.is_member)
  const fields = <div className="post-composer-row">
    <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Topic">{DISCUSSION_TOPICS.map((t) => <option key={t}>{t}</option>)}</select>
    <select value={community} onChange={(e) => setCommunity(e.target.value)} aria-label="Share to"><option value="">Everyone</option>{communities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
  </div>
  return { category, community, fields }
}

function usePublished(onClose: () => void) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return (post: Discussion) => {
    for (const key of ['discussions', 'trending-discussions', 'discussion-categories', 'community-discussions', 'reels']) queryClient.invalidateQueries({ queryKey: [key] })
    onClose()
    navigate(`/discussions/${post.id}`)
  }
}

function Dialog({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return createPortal(<div className="story-composer-backdrop" onClick={onClose}>
    <section className="post-composer" role="dialog" aria-modal="true" aria-label={label} onClick={(event) => event.stopPropagation()}>
      <header><strong>{label}</strong><button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={20} /></button></header>
      {children}
    </section>
  </div>, document.body)
}

type VideoDraft = { file: File; preview: string; seconds: number; poster: Blob }

export function VideoComposer({ onClose }: { onClose: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [draft, setDraft] = useState<VideoDraft | null>(null)
  const [caption, setCaption] = useState('')
  const [alt, setAlt] = useState('')
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(0)
  const [reading, setReading] = useState(false)
  const audience = useAudience()
  const published = usePublished(onClose)
  useEffect(() => () => { if (draft) URL.revokeObjectURL(draft.preview) }, [draft])

  const pick = async (file: File | undefined) => {
    setError('')
    if (!file) return
    if (!file.type.startsWith('video/')) { setError('Choose a video file (MP4, MOV or WebM).'); return }
    if (file.size > MAX_VIDEO_MB * 1024 * 1024) { setError(`Videos can be up to ${MAX_VIDEO_MB} MB. This one is ${Math.round(file.size / 1024 / 1024)} MB.`); return }
    setReading(true)
    try {
      const info = await inspectVideo(file)
      if (info.seconds > MAX_VIDEO_SECONDS) { setError(`Videos can be up to ${MAX_VIDEO_SECONDS / 60} minutes. This one is ${formatDuration(info.seconds * 1000)}.`); return }
      if (!info.poster) { setError("We couldn't read a cover frame from this video. Try an MP4 file."); return }
      setDraft({ file, preview: URL.createObjectURL(file), seconds: info.seconds, poster: info.poster })
    } catch (err) { setError((err as Error).message) } finally { setReading(false) }
  }

  const share = useMutation({
    mutationFn: async () => {
      if (!draft) throw new Error('Choose a video.')
      const form = new FormData()
      form.append('video', draft.file)
      form.append('poster', new File([draft.poster], 'poster.jpg', { type: 'image/jpeg' }))
      form.append('duration_ms', String(Math.round(draft.seconds * 1000)))
      form.append('caption', caption.trim())
      form.append('alt_text', alt.trim())
      form.append('category', audience.category)
      if (audience.community) form.append('community', audience.community)
      return (await api.post<Discussion>('/posts/video/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (event) => { if (event.total) setProgress(event.loaded / event.total) },
      })).data
    },
    onSuccess: published,
    onError: (err) => { setProgress(0); setError(err instanceof Error && !('isAxiosError' in err) ? err.message : getErrorMessage(err)) },
  })

  return <Dialog label="New video" onClose={onClose}>
    <div className="post-composer-body">
      <div className="post-composer-stage">
        {draft
          ? <><video src={draft.preview} controls playsInline muted /><div className="post-composer-tools"><span>{formatDuration(draft.seconds * 1000)}</span><button type="button" aria-label="Remove video" onClick={() => setDraft(null)}><Trash2 size={16} /></button></div></>
          : <button type="button" className="story-pick" disabled={reading} onClick={() => fileRef.current?.click()}><Clapperboard size={36} /><strong>{reading ? 'Reading video…' : 'Choose a video'}</strong><span>Up to {MAX_VIDEO_SECONDS / 60} minutes · {MAX_VIDEO_MB} MB · MP4, MOV or WebM</span></button>}
        <input ref={fileRef} type="file" accept="video/mp4,video/quicktime,video/webm,video/*" hidden onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = '' }} aria-label="Post video" />
      </div>
      <div className="post-composer-fields">
        <input value={alt} onChange={(e) => setAlt(e.target.value)} maxLength={300} placeholder="Describe the video for people who can't see it (optional)" aria-label="Video description" />
        <textarea value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={CAPTION_LIMIT} rows={3} placeholder="Write a caption… #hashtags and @mentions work." aria-label="Caption" />
        <span className="post-caption-count">{caption.length}/{CAPTION_LIMIT}</span>
        {audience.fields}
      </div>
    </div>
    {error && <div className="error-message">{error}</div>}
    {share.isPending && <div className="story-upload-progress" aria-label="Uploading"><i style={{ width: `${Math.round(progress * 100)}%` }} /></div>}
    <button type="button" className="button button-primary story-share" disabled={!draft || share.isPending} onClick={() => { setError(''); share.mutate() }}>{share.isPending ? `Uploading… ${Math.round(progress * 100)}%` : 'Share video'}</button>
  </Dialog>
}

export function PollComposer({ onClose }: { onClose: () => void }) {
  const [question, setQuestion] = useState('')
  const [options, setOptions] = useState(['', ''])
  const [multiple, setMultiple] = useState(false)
  const [hours, setHours] = useState(24)
  const [caption, setCaption] = useState('')
  const [error, setError] = useState('')
  const audience = useAudience()
  const published = usePublished(onClose)
  const filled = options.map((o) => o.trim()).filter(Boolean)

  const share = useMutation({
    mutationFn: async () => (await api.post<Discussion>('/posts/poll/', {
      question: question.trim(), options: filled, allows_multiple: multiple, duration_hours: hours,
      caption: caption.trim(), category: audience.category, community: audience.community ? Number(audience.community) : null,
    })).data,
    onSuccess: published,
    onError: (err) => setError(getErrorMessage(err)),
  })
  const submit = () => {
    setError('')
    if (!question.trim()) { setError('Ask a question.'); return }
    if (filled.length < 2) { setError('Add at least two options.'); return }
    if (new Set(filled.map((o) => o.toLowerCase())).size !== filled.length) { setError('Each option must be different.'); return }
    share.mutate()
  }

  return <Dialog label="New poll" onClose={onClose}>
    <div className="post-composer-fields poll-composer">
      <label>Question<input autoFocus value={question} maxLength={300} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask something…" /></label>
      <fieldset><legend>Options</legend>
        {options.map((option, index) => <div className="poll-composer-option" key={index}>
          <input value={option} maxLength={100} onChange={(e) => setOptions(options.map((o, i) => i === index ? e.target.value : o))} placeholder={`Option ${index + 1}`} aria-label={`Option ${index + 1}`} />
          {options.length > 2 && <button type="button" className="icon-button" aria-label={`Remove option ${index + 1}`} onClick={() => setOptions(options.filter((_, i) => i !== index))}><Trash2 size={15} /></button>}
        </div>)}
        {options.length < MAX_POLL_OPTIONS && <button type="button" className="text-button" onClick={() => setOptions([...options, ''])}><Plus size={14} /> Add option</button>}
      </fieldset>
      <div className="post-composer-row">
        <select value={hours} onChange={(e) => setHours(Number(e.target.value))} aria-label="Poll length">{POLL_DURATIONS.map((d) => <option key={d.hours} value={d.hours}>Ends in {d.label}</option>)}</select>
        <label className="toggle-row poll-multi"><input type="checkbox" checked={multiple} onChange={(e) => setMultiple(e.target.checked)} /><span><strong>Allow several answers</strong></span></label>
      </div>
      <textarea value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={CAPTION_LIMIT} rows={2} placeholder="Add some context (optional)" aria-label="Caption" />
      {audience.fields}
    </div>
    {error && <div className="error-message">{error}</div>}
    <button type="button" className="button button-primary story-share" disabled={share.isPending} onClick={submit}><ListChecks size={16} /> {share.isPending ? 'Posting…' : 'Post poll'}</button>
  </Dialog>
}
