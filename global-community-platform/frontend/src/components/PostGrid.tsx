import { BarChart3, Copy, Heart, MessageCircle, Play } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Discussion } from '../types'
import { useAttachmentUrl } from './useAttachmentUrl'

function LegacyThumb({ id, alt }: { id: number; alt: string }) {
  const { url } = useAttachmentUrl(id)
  return url ? <img src={url} alt={alt} loading="lazy" /> : null
}

/** Instagram-style square grid: photo thumbnails, text posts as coloured tiles. */
export default function PostGrid({ posts, mosaic = false }: { posts: Discussion[]; mosaic?: boolean }) {
  return <div className={`post-grid ${mosaic ? 'mosaic' : ''}`}>
    {posts.map((post, index) => {
      const images = post.attachments.filter((file) => file.is_image)
      const video = post.attachments.find((file) => file.is_video)
      const cover = video || images[0]
      const label = `${post.title || post.body.slice(0, 60) || 'Post'} by ${post.author_username}`
      return <Link key={post.id} to={`/discussions/${post.id}`} className={`post-tile ${mosaic && index % 10 === 2 ? 'tall' : ''}`} aria-label={label} style={{ backgroundColor: cover?.color || undefined }}>
        {cover
          ? cover.thumb_url
            ? <img src={cover.thumb_url} alt={cover.alt_text || label} width={cover.width || undefined} height={cover.height || undefined} loading="lazy" decoding="async" />
            : <LegacyThumb id={cover.id} alt={cover.alt_text || label} />
          : <span className="post-tile-text">{post.poll ? post.poll.question : post.title || post.body}</span>}
        {video && <Play className="post-tile-multi" size={18} fill="currentColor" aria-label="Video" />}
        {post.poll && !cover && <BarChart3 className="post-tile-multi" size={18} aria-label="Poll" />}
        {images.length > 1 && <Copy className="post-tile-multi" size={18} aria-label="Several photos" />}
        <span className="post-tile-overlay" aria-hidden="true"><span><Heart size={18} fill="currentColor" /> {post.reactions_count}</span><span><MessageCircle size={18} fill="currentColor" /> {post.comments_count}</span></span>
      </Link>
    })}
  </div>
}
