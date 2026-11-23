import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { EyeOff, ImagePlus, Lock, Search, Type, Users, X } from 'lucide-react'
import { api, getErrorMessage } from '../services/api'
import { getUploadConfig, uploadDirect } from '../services/uploads'
import type { Paginated, Person, StoryBackground } from '../types'
import { Avatar } from './PersonBits'

export const STORY_BACKGROUNDS: StoryBackground[] = ['violet', 'sunset', 'ocean', 'forest', 'night', 'rose']
const MAX_VIDEO_SECONDS = 60
const MAX_IMAGE_MB = 15
const MAX_VIDEO_MB = 50

type Mode = 'media' | 'text'
type Audience = 'followers' | 'close_friends'

/**
 * Read a video's duration and grab a poster frame (no server-side ffmpeg needed).
 * Videos recorded in browsers (MediaRecorder, many Android screen recordings) often
 * report duration = Infinity; seeking far past the end makes the browser compute it.
 */
export function inspectVideo(file: File, timeoutMs = 6000): Promise<{ seconds: number; poster: Blob | null; width?: number; height?: number }> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const video = document.createElement('video')
    let settled = false
    const fail = (message: string) => { if (settled) return; settled = true; clearTimeout(timer); URL.revokeObjectURL(url); reject(new Error(message)) }
    const timer = setTimeout(() => fail("We couldn't read this video's length. Try an MP4 file."), timeoutMs)
    video.preload = 'metadata'
    video.muted = true
    video.playsInline = true
    video.onerror = () => fail('This video could not be read. Try an MP4 file.')

    const capture = (seconds: number) => {
      video.onseeked = () => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        const canvas = document.createElement('canvas')
        const scale = Math.min(1, 720 / Math.max(video.videoWidth || 1, video.videoHeight || 1))
        canvas.width = Math.round(video.videoWidth * scale)
        canvas.height = Math.round(video.videoHeight * scale)
        let context: CanvasRenderingContext2D | null = null
        try { context = canvas.getContext('2d') } catch { context = null }
        if (!context || !canvas.width) { URL.revokeObjectURL(url); resolve({ seconds, poster: null, width: video.videoWidth, height: video.videoHeight }); return }
        context.drawImage(video, 0, 0, canvas.width, canvas.height)
        canvas.toBlob((blob) => { URL.revokeObjectURL(url); resolve({ seconds, poster: blob, width: video.videoWidth, height: video.videoHeight }) }, 'image/jpeg', 0.82)
      }
      video.currentTime = Math.min(0.5, seconds / 2)
    }

    video.onloadedmetadata = () => {
      if (Number.isFinite(video.duration) && video.duration > 0) { capture(video.duration); return }
      // Duration missing from the file: jump to the end so the browser measures it.
      video.ondurationchange = () => {
        if (!Number.isFinite(video.duration) || video.duration <= 0) return
        video.ondurationchange = null
        capture(video.duration)
      }
      video.currentTime = 1e101
    }
    video.src = url
  })
}

export function AudienceList({ kind, onClose }: { kind: 'close-friends' | 'hidden-from'; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const key = ['story-audience', kind]
  const members = useQuery({ queryKey: key, queryFn: async () => (await api.get<Person[]>(`/stories/${kind}/`)).data })
  const results = useQuery({
    queryKey: ['people-search', search.trim()],
    queryFn: async () => (await api.get<Paginated<Person>>('/people/', { params: { search: search.trim() } })).data.results,
    enabled: search.trim().length >= 2,
  })
  const change = useMutation({
    mutationFn: ({ username, add }: { username: string; add: boolean }) => add ? api.put(`/stories/${kind}/${encodeURIComponent(username)}/`) : api.delete(`/stories/${kind}/${encodeURIComponent(username)}/`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  })
  const ids = new Set((members.data || []).map((p) => p.id))
  const title = kind === 'close-friends' ? 'Close friends' : 'Hide story from'
  const help = kind === 'close-friends' ? 'Only these people see stories you share to Close friends. They are not told when you add or remove them.' : 'These people never see your stories, even if they follow you.'
  return <div className="story-audience-panel" role="dialog" aria-label={title}>
    <div className="story-audience-head"><strong>{title}</strong><button type="button" aria-label="Done" onClick={onClose}><X size={18} /></button></div>
    <p>{help}</p>
    <label className="story-audience-search"><Search size={14} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search people…" aria-label={`Search people for ${title}`} /></label>
    <ul>
      {(search.trim().length >= 2 ? results.data || [] : members.data || []).map((person) => {
        const added = ids.has(person.id)
        return <li key={person.id}><Avatar person={person} size={32} /><span><strong>{person.username}</strong><small>{person.display_name}</small></span>
          <button type="button" className={added ? 'added' : ''} onClick={() => change.mutate({ username: person.username, add: !added })} disabled={change.isPending}>{added ? 'Remove' : 'Add'}</button></li>
      })}
      {search.trim().length < 2 && members.data?.length === 0 && <li className="empty">No one yet. Search to add people.</li>}
    </ul>
  </div>
}

export default function StoryComposer({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<Mode>('media')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [video, setVideo] = useState<{ seconds: number; poster: Blob | null } | null>(null)
  const [text, setText] = useState('')
  const [background, setBackground] = useState<StoryBackground>('violet')
  const [altText, setAltText] = useState('')
  const [audience, setAudience] = useState<Audience>('followers')
  const [panel, setPanel] = useState<'close-friends' | 'hidden-from' | null>(null)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(0)

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const choose = async (event: ChangeEvent<HTMLInputElement>) => {
    const picked = event.target.files?.[0]
    event.target.value = ''
    if (!picked) return
    setError('')
    const isVideo = picked.type.startsWith('video/')
    if (!isVideo && !picked.type.startsWith('image/')) { setError('Choose a photo or a video.'); return }
    if (picked.size > (isVideo ? MAX_VIDEO_MB : MAX_IMAGE_MB) * 1024 * 1024) { setError(`${isVideo ? 'Videos' : 'Photos'} must be ${isVideo ? MAX_VIDEO_MB : MAX_IMAGE_MB} MB or smaller.`); return }
    let info: { seconds: number; poster: Blob | null } | null = null
    if (isVideo) {
      try { info = await inspectVideo(picked) } catch (err) { setError((err as Error).message); return }
      if (info.seconds > MAX_VIDEO_SECONDS) { setError(`Videos can be up to ${MAX_VIDEO_SECONDS} seconds. This one is ${Math.round(info.seconds)} seconds.`); return }
    }
    if (preview) URL.revokeObjectURL(preview)
    setFile(picked)
    setVideo(info)
    setPreview(URL.createObjectURL(picked))
  }

  const share = useMutation({
    mutationFn: async () => {
      const form = new FormData()
      form.append('audience', audience)
      if (mode === 'text') {
        form.append('media_type', 'text')
        form.append('text', text.trim())
        form.append('background', background)
      } else {
        if (!file) throw new Error('Choose a photo or video first.')
        form.append('media_type', video ? 'video' : 'image')
        const config = await getUploadConfig()
        if (config.direct) form.append('file_key', await uploadDirect(file, video ? 'story-video' : 'story-photo', (part) => setProgress(part * 0.95)))
        else form.append('file', file)
        if (text.trim()) form.append('text', text.trim())
        if (altText.trim()) form.append('alt_text', altText.trim())
        if (video) {
          form.append('duration_ms', String(Math.max(1000, Math.round(video.seconds * 1000))))
          if (video.poster) form.append('thumbnail', video.poster, 'poster.jpg')
        }
      }
      return api.post('/stories/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (event) => { const total = event.total; if (total) setProgress((current) => Math.max(current, event.loaded / total)) },
      })
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['story-tray'] }); onClose() },
    onError: (err) => { setProgress(0); setError(err instanceof Error && !('isAxiosError' in err) ? err.message : getErrorMessage(err)) },
  })

  const ready = mode === 'text' ? text.trim().length > 0 : Boolean(file)

  return createPortal(<div className="story-composer-backdrop" onClick={onClose}>
    <section className="story-composer" role="dialog" aria-modal="true" aria-label="Create a story" onClick={(event) => event.stopPropagation()}>
      <header><strong>New story</strong><button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={20} /></button></header>
      <div className="story-composer-modes" role="tablist">
        <button role="tab" aria-selected={mode === 'media'} className={mode === 'media' ? 'active' : ''} onClick={() => setMode('media')}><ImagePlus size={16} /> Photo or video</button>
        <button role="tab" aria-selected={mode === 'text'} className={mode === 'text' ? 'active' : ''} onClick={() => setMode('text')}><Type size={16} /> Text</button>
      </div>

      <div className="story-composer-preview">
        {mode === 'text'
          ? <div className={`story-text-card bg-${background}`}><textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Type something…" maxLength={500} aria-label="Story text" autoFocus /></div>
          : preview
            ? <>{video ? <video src={preview} muted playsInline autoPlay loop /> : <img src={preview} alt="Story preview" />}{text && <p className="story-caption">{text}</p>}<button type="button" className="story-change-media" onClick={() => fileRef.current?.click()}>Change</button></>
            : <button type="button" className="story-pick" onClick={() => fileRef.current?.click()}><ImagePlus size={34} /><strong>Choose a photo or video</strong><span>Photos up to {MAX_IMAGE_MB} MB · videos up to {MAX_VIDEO_SECONDS}s and {MAX_VIDEO_MB} MB</span></button>}
        <input ref={fileRef} type="file" accept="image/*,video/mp4,video/webm,video/quicktime" hidden onChange={choose} aria-label="Story photo or video" />
      </div>

      {mode === 'text'
        ? <div className="story-bg-picker" role="radiogroup" aria-label="Background">{STORY_BACKGROUNDS.map((name) => <button key={name} type="button" role="radio" aria-checked={background === name} aria-label={name} className={`bg-${name} ${background === name ? 'active' : ''}`} onClick={() => setBackground(name)} />)}</div>
        : preview && <div className="story-composer-fields">
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a caption…" maxLength={500} aria-label="Caption" />
            {!video && <input value={altText} onChange={(e) => setAltText(e.target.value)} placeholder="Alt text: describe the photo for people who can't see it" maxLength={300} aria-label="Alt text" />}
          </div>}

      <div className="story-audience" role="radiogroup" aria-label="Who can see this">
        <button type="button" role="radio" aria-checked={audience === 'followers'} className={audience === 'followers' ? 'active' : ''} onClick={() => setAudience('followers')}><Users size={15} /> Followers</button>
        <button type="button" role="radio" aria-checked={audience === 'close_friends'} className={`cf ${audience === 'close_friends' ? 'active' : ''}`} onClick={() => setAudience('close_friends')}><Lock size={15} /> Close friends</button>
      </div>
      <div className="story-audience-links"><button type="button" onClick={() => setPanel('close-friends')}>Edit close friends</button><button type="button" onClick={() => setPanel('hidden-from')}><EyeOff size={13} /> Hide story from…</button></div>

      {error && <div className="error-message">{error}</div>}
      {share.isPending && <div className="story-upload-progress" aria-label="Uploading"><i style={{ width: `${Math.round(progress * 100)}%` }} /></div>}
      <button type="button" className="button button-primary story-share" onClick={() => { setError(''); share.mutate() }} disabled={!ready || share.isPending}>{share.isPending ? `Sharing… ${Math.round(progress * 100)}%` : audience === 'close_friends' ? 'Share to Close friends' : 'Share to your story'}</button>
      <p className="story-expiry-note">Stories disappear after 24 hours and are then permanently deleted.</p>

      {panel && <AudienceList kind={panel} onClose={() => setPanel(null)} />}
    </section>
  </div>, document.body)
}
