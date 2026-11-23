import { API_BASE, api, getAccessToken } from './api'

/**
 * Remembers which posts were on screen and for how long (and whether a video was
 * watched to the end), then reports them in batches so the For You feed learns.
 */
type Entry = { ms: number; completed: boolean; dirty: boolean }
const entries = new Map<number, Entry>()
let timer: ReturnType<typeof setTimeout> | null = null

function pending() {
  const views = [...entries.entries()].filter(([, e]) => e.dirty).map(([id, e]) => ({ id, ms: Math.round(e.ms), completed: e.completed }))
  for (const [, e] of entries) e.dirty = false
  return views
}

function schedule() {
  if (timer) return
  timer = setTimeout(() => { timer = null; void flush() }, 8000)
}

export async function flush() {
  const views = pending()
  if (!views.length) return
  try { await api.post('/feed/views/', { views }) } catch { /* best effort */ }
}

export function recordView(id: number, ms: number, completed = false) {
  const entry = entries.get(id) ?? { ms: 0, completed: false, dirty: false }
  entry.ms = Math.max(entry.ms, ms)
  entry.completed = entry.completed || completed
  entry.dirty = true
  entries.set(id, entry)
  schedule()
}

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => {
    const views = pending()
    const token = getAccessToken()
    if (!views.length || !token) return
    void fetch(`${API_BASE}/feed/views/`, { method: 'POST', keepalive: true, credentials: 'include', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ views }) }).catch(() => {})
  })
}

/** Observe an element: counts time while at least 60% of it is on screen. */
export function trackVisibility(node: Element, id: number) {
  if (typeof IntersectionObserver === 'undefined') return () => {}
  let since = 0
  let total = 0
  const observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting && entry.intersectionRatio >= 0.6) since = performance.now()
    else if (since) { total += performance.now() - since; since = 0; if (total >= 1000) recordView(id, total) }
  }, { threshold: [0, 0.6, 1] })
  observer.observe(node)
  return () => {
    observer.disconnect()
    if (since) { total += performance.now() - since; if (total >= 1000) recordView(id, total) }
  }
}
