import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, ImagePlus, Trash2, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import { getUploadConfig, uploadDirect } from '../services/uploads'
import type { Community, Discussion, Paginated } from '../types'
import { DISCUSSION_TOPICS } from '../pages/CreateDiscussionPage'

export const MAX_PHOTOS = 10
const MAX_PHOTO_MB = 15
const UPLOAD_EDGE = 2160
const CAPTION_LIMIT = 2200

type Draft = { id: string; file: File; preview: string; alt: string }

/**
 * Shrink a photo in the browser before upload (JPEG, longest side 2160px). A 12 MB phone
 * photo becomes ~1 MB: much faster on mobile data, and EXIF/GPS never leaves the device.
 * The server still re-processes everything, so this is purely an optimisation.
 */
export async function shrinkForUpload(file: File, edge = UPLOAD_EDGE): Promise<File> {
  if (typeof createImageBitmap !== 'function' || file.type === 'image/gif') return file
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    const scale = Math.min(1, edge / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    const context = canvas.getContext('2d')
    if (!context) return file
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close?.()
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9))
    if (!blob || blob.size >= file.size) return file
    return new File([blob], file.name.replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' })
  } catch {
    return file // e.g. HEIC on browsers that can't decode it: let the server try
  }
}

export default function PostComposer({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [slide, setSlide] = useState(0)
  const [caption, setCaption] = useState('')
  const [category, setCategory] = useState('General')
  const [community, setCommunity] = useState('')
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(0)
  const { data } = useQuery({ queryKey: ['communities'], queryFn: async () => (await api.get<Paginated<Community> | Community[]>('/communities/')).data })
  const communities = (Array.isArray(data) ? data : data?.results || []).filter((item) => item.is_member)

  useEffect(() => () => drafts.forEach((d) => URL.revokeObjectURL(d.preview)), []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const add = (event: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files || [])
    event.target.value = ''
    setError('')
    const images = picked.filter((file) => file.type.startsWith('image/'))
    if (images.length < picked.length) setError('Only photos can be added to a post.')
    const tooBig = images.find((file) => file.size > MAX_PHOTO_MB * 1024 * 1024)
    if (tooBig) { setError(`${tooBig.name} is larger than ${MAX_PHOTO_MB} MB.`); return }
    setDrafts((current) => {
      const room = MAX_PHOTOS - current.length
      if (images.length > room) setError(`A post can have up to ${MAX_PHOTOS} photos.`)
      return [...current, ...images.slice(0, room).map((file) => ({ id: `${file.name}-${file.size}-${Math.random()}`, file, preview: URL.createObjectURL(file), alt: '' }))]
    })
  }
  const remove = (index: number) => {
    setDrafts((current) => { URL.revokeObjectURL(current[index].preview); return current.filter((_, i) => i !== index) })
    setSlide((s) => Math.max(0, Math.min(s, drafts.length - 2)))
  }
  const move = (index: number, direction: -1 | 1) => {
    setDrafts((current) => {
      const next = [...current]
      const target = index + direction
      if (target < 0 || target >= next.length) return current
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
    setSlide(index + direction)
  }
  const setAlt = (index: number, alt: string) => setDrafts((current) => current.map((d, i) => i === index ? { ...d, alt } : d))

  const share = useMutation({
    mutationFn: async () => {
      if (!drafts.length) throw new Error('Add at least one photo.')
      const form = new FormData()
      const files = await Promise.all(drafts.map((d) => shrinkForUpload(d.file)))
      const config = await getUploadConfig()
      if (config.direct) {
        // Straight to storage, one by one, so a 10-photo post isn't one huge request.
        for (const [index, file] of files.entries()) {
          form.append('image_keys', await uploadDirect(file, 'post-photo', (part) => setProgress((index + part) / files.length * 0.95)))
        }
      } else {
        files.forEach((file) => form.append('images', file))
      }
      drafts.forEach((d) => form.append('alt_texts', d.alt.trim()))
      form.append('caption', caption.trim())
      form.append('category', category)
      if (community) form.append('community', community)
      return (await api.post<Discussion>('/posts/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (event) => { const total = event.total; if (total) setProgress((current) => Math.max(current, event.loaded / total)) },
      })).data
    },
    onSuccess: (post) => {
      for (const key of ['discussions', 'trending-discussions', 'discussion-categories', 'community-discussions']) queryClient.invalidateQueries({ queryKey: [key] })
      onClose()
      navigate(`/discussions/${post.id}`)
    },
    onError: (err) => { setProgress(0); setError(err instanceof Error && !('isAxiosError' in err) ? err.message : getErrorMessage(err)) },
  })

  const current = drafts[slide]
  return createPortal(<div className="story-composer-backdrop" onClick={onClose}>
    <section className="post-composer" role="dialog" aria-modal="true" aria-label="Create a post" onClick={(event) => event.stopPropagation()}>
      <header><strong>New post</strong><button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={20} /></button></header>
      <div className="post-composer-body">
        <div className="post-composer-stage">
          {current
            ? <>
                <img src={current.preview} alt={current.alt || 'Selected photo'} />
                <div className="post-composer-tools">
                  <button type="button" aria-label="Move photo earlier" disabled={slide === 0} onClick={() => move(slide, -1)}><ArrowLeft size={16} /></button>
                  <span>{slide + 1}/{drafts.length}</span>
                  <button type="button" aria-label="Move photo later" disabled={slide === drafts.length - 1} onClick={() => move(slide, 1)}><ArrowRight size={16} /></button>
                  <button type="button" aria-label="Remove photo" onClick={() => remove(slide)}><Trash2 size={16} /></button>
                </div>
              </>
            : <button type="button" className="story-pick" onClick={() => fileRef.current?.click()}><ImagePlus size={36} /><strong>Add photos</strong><span>Up to {MAX_PHOTOS} photos · {MAX_PHOTO_MB} MB each</span></button>}
          <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={add} aria-label="Post photos" />
        </div>
        {drafts.length > 0 && <div className="post-composer-strip">
          {drafts.map((d, index) => <button type="button" key={d.id} className={index === slide ? 'active' : ''} onClick={() => setSlide(index)} aria-label={`Photo ${index + 1}`}><img src={d.preview} alt="" /></button>)}
          {drafts.length < MAX_PHOTOS && <button type="button" className="post-composer-add" onClick={() => fileRef.current?.click()} aria-label="Add more photos"><ImagePlus size={18} /></button>}
        </div>}
        <div className="post-composer-fields">
          {current && <input value={current.alt} onChange={(e) => setAlt(slide, e.target.value)} maxLength={300} placeholder={`Alt text for photo ${slide + 1}: describe it for people who can't see it`} aria-label={`Alt text for photo ${slide + 1}`} />}
          <textarea value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={CAPTION_LIMIT} rows={4} placeholder="Write a caption… Links, #hashtags and @mentions work." aria-label="Caption" />
          <span className="post-caption-count">{caption.length}/{CAPTION_LIMIT}</span>
          <div className="post-composer-row">
            <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Topic">{DISCUSSION_TOPICS.map((t) => <option key={t}>{t}</option>)}</select>
            <select value={community} onChange={(e) => setCommunity(e.target.value)} aria-label="Share to"><option value="">Everyone</option>{communities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          </div>
        </div>
      </div>
      {error && <div className="error-message">{error}</div>}
      {share.isPending && <div className="story-upload-progress" aria-label="Uploading"><i style={{ width: `${Math.round(progress * 100)}%` }} /></div>}
      <button type="button" className="button button-primary story-share" disabled={!drafts.length || share.isPending} onClick={() => { setError(''); share.mutate() }}>{share.isPending ? `Sharing… ${Math.round(progress * 100)}%` : 'Share post'}</button>
    </section>
  </div>, document.body)
}
