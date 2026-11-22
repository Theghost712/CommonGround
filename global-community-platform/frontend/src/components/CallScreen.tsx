import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Mic, MicOff, Phone, PhoneOff, Video, VideoOff } from 'lucide-react'
import { useCall } from '../context/CallContext'
import { useAuth } from '../context/AuthContext'
import '../calls.css'

function StreamView({ stream, muted, className, label }: { stream: MediaStream | null; muted?: boolean; className: string; label: string }) {
  const ref = useRef<HTMLVideoElement>(null)
  useEffect(() => { if (ref.current && ref.current.srcObject !== stream) ref.current.srcObject = stream }, [stream])
  return <video ref={ref} className={className} autoPlay playsInline muted={muted} aria-label={label} />
}

function Timer({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id) }, [])
  const seconds = Math.max(0, Math.floor((now - since) / 1000))
  return <span className="call-timer">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</span>
}

/** Full-screen call UI: incoming ring, outgoing "Calling…", the live call, and the end card. */
export default function CallScreen() {
  const call = useCall()
  const { user } = useAuth()
  const { phase, call: info } = call
  useEffect(() => {
    if (phase !== 'incoming' || !info) return
    const previous = document.title
    document.title = `📞 ${info.caller.display_name} is calling…`
    return () => { document.title = previous }
  }, [phase, info])
  if (phase === 'idle' || !info) return null

  const other = user?.id === info.caller.id ? info.callee : info.caller
  const video = info.kind === 'video'
  const status = phase === 'incoming' ? `Incoming ${video ? 'video' : 'voice'} call`
    : phase === 'outgoing' ? 'Calling…'
    : phase === 'connecting' ? 'Connecting…'
    : phase === 'ended' ? call.message : ''
  const showRemoteVideo = video && call.remoteStream && phase === 'active'

  return createPortal(<div className={`call-screen ${showRemoteVideo ? 'has-video' : ''}`} role="dialog" aria-modal="true" aria-label={`${video ? 'Video' : 'Voice'} call with ${other.display_name}`}>
    {showRemoteVideo ? <StreamView stream={call.remoteStream} className="call-remote" label={`${other.display_name}'s video`} />
      : <>{call.remoteStream && <StreamView stream={call.remoteStream} className="call-hidden-audio" label="Call audio" />}</>}
    <div className="call-identity">
      {!showRemoteVideo && <div className={`call-avatar ${phase === 'incoming' || phase === 'outgoing' ? 'is-ringing' : ''}`}>{other.display_name.slice(0, 1).toUpperCase()}</div>}
      <h2>{other.display_name}</h2>
      <p role="status">{phase === 'active' && call.startedAt ? <Timer since={call.startedAt} /> : status}</p>
    </div>
    {video && call.localStream && phase !== 'ended' && phase !== 'incoming' && <StreamView stream={call.localStream} muted className={`call-local ${call.cameraOff ? 'is-off' : ''}`} label="Your camera" />}

    <div className="call-controls">
      {phase === 'incoming' ? <>
        <button type="button" className="call-btn is-decline" onClick={() => void call.decline()} aria-label="Decline"><PhoneOff size={26} /><span>Decline</span></button>
        <button type="button" className="call-btn is-accept" onClick={() => void call.accept()} aria-label="Accept">{video ? <Video size={26} /> : <Phone size={26} />}<span>Accept</span></button>
      </> : phase === 'ended' ? <button type="button" className="call-btn" onClick={call.dismiss} aria-label="Close"><span>Close</span></button>
      : <>
        <button type="button" className={`call-btn ${call.muted ? 'is-on' : ''}`} onClick={call.toggleMute} aria-label={call.muted ? 'Unmute' : 'Mute'} aria-pressed={call.muted}>{call.muted ? <MicOff size={22} /> : <Mic size={22} />}<span>{call.muted ? 'Unmute' : 'Mute'}</span></button>
        {video && <button type="button" className={`call-btn ${call.cameraOff ? 'is-on' : ''}`} onClick={call.toggleCamera} aria-label={call.cameraOff ? 'Turn camera on' : 'Turn camera off'} aria-pressed={call.cameraOff}>{call.cameraOff ? <VideoOff size={22} /> : <Video size={22} />}<span>Camera</span></button>}
        <button type="button" className="call-btn is-decline" onClick={() => void call.hangUp()} aria-label="End call"><PhoneOff size={24} /><span>End</span></button>
      </>}
    </div>
  </div>, document.body)
}
