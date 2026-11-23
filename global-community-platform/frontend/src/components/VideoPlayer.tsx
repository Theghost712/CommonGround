import { useEffect, useRef, useState } from 'react'
import { Pause, Play, Volume2, VolumeX } from 'lucide-react'
import type { DiscussionAttachment } from '../types'

export function formatDuration(ms?: number | null): string {
  if (!ms) return ''
  const total = Math.round(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// Only one feed video plays sound at a time; remembering the choice feels like Instagram.
let soundOn = false

/**
 * Feed/reels video: plays muted while at least 60% visible, pauses when scrolled away,
 * loads nothing until near the screen (preload="none" + poster), tap to pause, button for sound.
 */
export default function VideoPlayer({ file, fill = false, className = '', onProgress }: { file: DiscussionAttachment; fill?: boolean; className?: string; onProgress?: (fraction: number, seconds: number) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(!soundOn)
  const [userPaused, setUserPaused] = useState(false)
  const ratio = file.width && file.height ? Math.min(1.91, Math.max(0.5625, file.width / file.height)) : 0.8

  useEffect(() => {
    const video = videoRef.current
    if (!video || typeof IntersectionObserver === 'undefined' || reducedMotion()) return
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
        if (!userPaused) { video.muted = !soundOn; setMuted(!soundOn); void video.play().catch(() => { video.muted = true; setMuted(true); void video.play().catch(() => {}) }) }
      } else video.pause()
    }, { threshold: [0, 0.6, 1] })
    observer.observe(video)
    return () => observer.disconnect()
  }, [userPaused])

  const toggle = () => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) { setUserPaused(false); void video.play().catch(() => {}) } else { setUserPaused(true); video.pause() }
  }
  const toggleSound = () => {
    const video = videoRef.current
    if (!video) return
    soundOn = video.muted
    video.muted = !video.muted
    setMuted(video.muted)
  }

  if (file.processing === 'failed' || !file.video_url) {
    return <div className={`video-player is-unavailable ${fill ? 'is-fill' : ''} ${className}`} style={fill ? undefined : { aspectRatio: ratio, backgroundColor: file.color || '#111' }}>
      {file.display_url && <img src={file.display_url} alt="" />}
      <p role="status">This video couldn't be processed.</p>
    </div>
  }

  return <div className={`video-player ${fill ? 'is-fill' : ''} ${className}`} style={fill ? undefined : { aspectRatio: ratio, backgroundColor: file.color || '#111' }}>
    <video
      ref={videoRef}
      src={file.video_url}
      poster={file.display_url}
      preload="none"
      muted={muted}
      loop
      playsInline
      aria-label={file.alt_text || 'Video'}
      onPlay={() => setPlaying(true)}
      onPause={() => setPlaying(false)}
      onClick={toggle}
      onTimeUpdate={onProgress ? (event) => { const v = event.currentTarget; if (v.duration) onProgress(v.currentTime / v.duration, v.currentTime) } : undefined}
    />
    {!playing && <button type="button" className="video-big-play" aria-label="Play video" onClick={toggle}><Play size={30} fill="currentColor" /></button>}
    <div className="video-controls">
      {file.duration_ms ? <span className="video-duration">{formatDuration(file.duration_ms)}</span> : <span />}
      <span>
        <button type="button" aria-label={playing ? 'Pause' : 'Play'} onClick={toggle}>{playing ? <Pause size={16} /> : <Play size={16} />}</button>
        <button type="button" aria-label={muted ? 'Turn sound on' : 'Mute'} onClick={toggleSound}>{muted ? <VolumeX size={16} /> : <Volume2 size={16} />}</button>
      </span>
    </div>
  </div>
}
