import { useEffect, useState } from 'react'
import { Download, Share, X } from 'lucide-react'

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> }

const KEY = 'cg-install-dismissed-at'
const QUIET_DAYS = 14

function dismissedRecently() {
  try { const at = Number(localStorage.getItem(KEY) || 0); return Date.now() - at < QUIET_DAYS * 86400e3 } catch { return false }
}
function remember() { try { localStorage.setItem(KEY, String(Date.now())) } catch { /* private mode */ } }
const standalone = () => typeof window !== 'undefined' && (window.matchMedia?.('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true)
const isIos = () => typeof navigator !== 'undefined' && /iphone|ipad|ipod/i.test(navigator.userAgent) && !/crios|fxios/i.test(navigator.userAgent)

/** "Install CommonGround" banner: one tap on Android/desktop Chrome, instructions on iPhone. */
export default function InstallPrompt() {
  const [event, setEvent] = useState<InstallEvent | null>(null)
  const [ios, setIos] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (standalone() || dismissedRecently()) return
    const onPrompt = (e: Event) => { e.preventDefault(); setEvent(e as InstallEvent); setOpen(true) }
    window.addEventListener('beforeinstallprompt', onPrompt)
    // iPhone Safari has no install event: show the "Add to Home Screen" tip after a short visit.
    let timer: ReturnType<typeof setTimeout> | null = null
    if (isIos()) timer = setTimeout(() => { setIos(true); setOpen(true) }, 20_000)
    const onInstalled = () => { setOpen(false); remember() }
    window.addEventListener('appinstalled', onInstalled)
    return () => { window.removeEventListener('beforeinstallprompt', onPrompt); window.removeEventListener('appinstalled', onInstalled); if (timer) clearTimeout(timer) }
  }, [])

  if (!open) return null
  const close = () => { setOpen(false); remember() }
  const install = async () => {
    if (!event) return
    await event.prompt()
    const choice = await event.userChoice.catch(() => ({ outcome: 'dismissed' as const }))
    setOpen(false)
    if (choice.outcome !== 'accepted') remember()
  }
  return <div className="install-prompt" role="dialog" aria-label="Install CommonGround">
    <img src="/icons/icon-192.png" alt="" width={40} height={40} />
    <div className="install-copy">
      <strong>Get the CommonGround app</strong>
      {ios ? <span>Tap <Share size={13} aria-label="Share" /> then <b>Add to Home Screen</b>.</span> : <span>Faster to open, works full screen, gets notifications.</span>}
    </div>
    {!ios && <button type="button" className="install-button" onClick={() => void install()}><Download size={15} /> Install</button>}
    <button type="button" className="icon-button" aria-label="Not now" onClick={close}><X size={17} /></button>
  </div>
}
