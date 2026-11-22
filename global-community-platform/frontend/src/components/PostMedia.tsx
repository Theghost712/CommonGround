import { useRef, useState, type TouchEvent } from 'react'
import { ChevronLeft, ChevronRight, FileText, Heart } from 'lucide-react'
import type { DiscussionAttachment } from '../types'
import { useAttachmentUrl } from './useAttachmentUrl'

/** Instagram keeps a photo's own shape, but never taller than 4:5 or wider than 1.91:1. */
export function clampRatio(width: number, height: number): number {
  if (!width || !height) return 1
  return Math.min(1.91, Math.max(0.8, width / height))
}

/** Older uploads without optimised copies are loaded through the authenticated API. */
function LegacyImage({ file, onSize }: { file: DiscussionAttachment; onSize: (w: number, h: number) => void }) {
  const { url, failed } = useAttachmentUrl(file.id)
  if (failed) return <div className="feed-media-fallback"><FileText size={22} /><span>{file.original_name}</span><small>Could not load image</small></div>
  if (!url) return <div className="feed-media-skeleton" aria-label={`Loading ${file.original_name}`} />
  return <img src={url} alt={file.alt_text || file.original_name} draggable={false} onLoad={(e) => onSize(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)} />
}

export function PostImage({ file, sizes = '(max-width: 600px) 100vw, 560px', eager = false, onSize }: { file: DiscussionAttachment; sizes?: string; eager?: boolean; onSize?: (w: number, h: number) => void }) {
  if (!file.display_url) return <LegacyImage file={file} onSize={onSize || (() => {})} />
  return <img
    src={file.display_url}
    srcSet={file.thumb_url ? `${file.thumb_url} 480w, ${file.display_url} 1080w` : undefined}
    sizes={sizes}
    width={file.width || undefined}
    height={file.height || undefined}
    alt={file.alt_text || `Photo: ${file.original_name}`}
    loading={eager ? 'eager' : 'lazy'}
    decoding="async"
    draggable={false}
  />
}

const DOUBLE_TAP_MS = 300

/**
 * Photo carousel for a post: reserves the right space before loading (no layout jump),
 * shows the dominant colour as a placeholder, swipes on touch, double-tap to like.
 */
export default function PostMedia({ images, onDoubleTap, eager = false }: { images: DiscussionAttachment[]; onDoubleTap?: () => void; eager?: boolean }) {
  const [slide, setSlide] = useState(0)
  const [measured, setMeasured] = useState<number | null>(null)
  const [burst, setBurst] = useState(0)
  const lastTap = useRef(0)
  const swipeStart = useRef<number | null>(null)
  const first = images[0]
  const ratio = first?.width && first?.height ? clampRatio(first.width, first.height) : measured ?? 1
  const current = images[slide]

  const like = () => { setBurst((n) => n + 1); onDoubleTap?.() }
  const onTouchEnd = (event: TouchEvent) => {
    const now = Date.now()
    if (now - lastTap.current < DOUBLE_TAP_MS) { event.preventDefault(); lastTap.current = 0; like() } else lastTap.current = now
    if (swipeStart.current !== null && images.length > 1) {
      const dx = event.changedTouches[0].clientX - swipeStart.current
      if (Math.abs(dx) > 40) setSlide((i) => Math.min(images.length - 1, Math.max(0, i + (dx < 0 ? 1 : -1))))
    }
    swipeStart.current = null
  }

  if (!current) return null
  return <div className="feed-media-wrap">
    <div
      className="feed-media"
      style={{ aspectRatio: ratio, backgroundColor: current.color || undefined }}
      onDoubleClick={onDoubleTap ? like : undefined}
      onTouchStart={(event) => { swipeStart.current = event.touches[0].clientX }}
      onTouchEnd={onTouchEnd}
    >
      <PostImage key={current.id} file={current} eager={eager && slide === 0} onSize={(w, h) => setMeasured((m) => m ?? clampRatio(w, h))} />
      {burst > 0 && <Heart key={burst} className="feed-heart-burst" size={96} fill="currentColor" aria-hidden="true" />}
      {images.length > 1 && <>
        {slide > 0 && <button type="button" className="feed-media-nav prev" aria-label="Previous image" onClick={() => setSlide(slide - 1)}><ChevronLeft size={18} /></button>}
        {slide < images.length - 1 && <button type="button" className="feed-media-nav next" aria-label="Next image" onClick={() => setSlide(slide + 1)}><ChevronRight size={18} /></button>}
        <span className="feed-media-count">{slide + 1}/{images.length}</span>
      </>}
    </div>
    {images.length > 1 && <div className="feed-dots" aria-hidden="true">{images.map((file, index) => <i key={file.id} className={index === slide ? 'active' : ''} />)}</div>}
  </div>
}
