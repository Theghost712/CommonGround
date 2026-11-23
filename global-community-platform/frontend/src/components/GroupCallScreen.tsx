import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Mic, MicOff, PhoneOff, Users, Video, VideoOff, X } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useGroupCall, type GroupParticipant } from '../context/GroupCallContext'
import '../calls.css'

function Media({ stream, muted, className, label }: { stream: MediaStream | null; muted?: boolean; className: string; label: string }) {
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

const hasLiveVideo = (stream: MediaStream | null) => Boolean(stream?.getVideoTracks().some((track) => track.readyState === 'live' && !track.muted))

function Tile({ person, stream, isMe, muted, cameraOff, state }: { person: Pick<GroupParticipant, 'display_name'>; stream: MediaStream | null; isMe?: boolean; muted?: boolean; cameraOff?: boolean; state?: string }) {
  const [, rerender] = useState(0)
  // Remote video tracks start "muted" until frames flow; re-check when that changes.
  useEffect(() => {
    const tracks = stream?.getVideoTracks() ?? []
    const update = () => rerender((n) => n + 1)
    tracks.forEach((track) => { track.addEventListener('unmute', update); track.addEventListener('mute', update) })
    return () => tracks.forEach((track) => { track.removeEventListener('unmute', update); track.removeEventListener('mute', update) })
  }, [stream])
  const showVideo = hasLiveVideo(stream) && !(isMe && cameraOff)
  const connecting = !isMe && state !== 'connected'
  return <div className={`group-tile ${isMe ? 'is-me' : ''}`}>
    {stream && <Media stream={stream} muted={isMe} className={showVideo ? 'group-tile-video' : 'call-hidden-audio'} label={isMe ? 'Your camera' : `${person.display_name}'s ${showVideo ? 'video' : 'audio'}`} />}
    {!showVideo && <div className="group-tile-avatar" aria-hidden="true">{person.display_name.slice(0, 1).toUpperCase()}</div>}
    <span className="group-tile-name">{isMe ? 'You' : person.display_name}{isMe && muted ? ' · muted' : ''}{connecting ? (state === 'failed' ? ' · connection lost' : ' · connecting…') : ''}</span>
  </div>
}

/** Full-screen UI for a group call: a grid with everyone in the call. */
export default function GroupCallScreen() {
  const group = useGroupCall()
  const { user } = useAuth()
  const { phase, call } = group
  if (phase === 'idle') return null
  const others = (call?.participants ?? []).filter((p) => p.id !== user?.id)
  const video = call?.kind === 'video'
  const count = others.length + 1
  return createPortal(<div className="call-screen group-call-screen" role="dialog" aria-modal="true" aria-label={`Group ${video ? 'video' : 'voice'} call`}>
    <div className="group-call-head">
      <strong><Users size={16} /> {count} {count === 1 ? 'person' : 'people'}</strong>
      <span role="status">{phase === 'joining' ? 'Joining…' : phase === 'ended' ? group.message : group.joinedAt ? <Timer since={group.joinedAt} /> : ''}</span>
    </div>
    {phase !== 'ended' && <div className={`group-grid count-${Math.min(count, 9)}`}>
      <Tile person={{ display_name: user?.username ?? 'You' }} stream={group.localStream} isMe muted={group.muted} cameraOff={group.cameraOff} />
      {others.map((person) => <Tile key={person.id} person={person} stream={group.peers[person.id]?.stream ?? null} state={group.peers[person.id]?.connection} />)}
    </div>}
    {phase === 'active' && others.length === 0 && <p className="group-call-waiting">Waiting for others to join…</p>}
    <div className="call-controls">
      {phase === 'ended' ? <button type="button" className="call-btn" onClick={group.dismiss}><span>Close</span></button> : <>
        <button type="button" className={`call-btn ${group.muted ? 'is-on' : ''}`} onClick={group.toggleMute} aria-label={group.muted ? 'Unmute' : 'Mute'} aria-pressed={group.muted}>{group.muted ? <MicOff size={22} /> : <Mic size={22} />}<span>{group.muted ? 'Unmute' : 'Mute'}</span></button>
        {video && <button type="button" className={`call-btn ${group.cameraOff ? 'is-on' : ''}`} onClick={group.toggleCamera} aria-label={group.cameraOff ? 'Turn camera on' : 'Turn camera off'} aria-pressed={group.cameraOff}>{group.cameraOff ? <VideoOff size={22} /> : <Video size={22} />}<span>Camera</span></button>}
        <button type="button" className="call-btn is-decline" onClick={() => void group.leave()} aria-label="Leave call"><PhoneOff size={24} /><span>Leave</span></button>
      </>}
    </div>
  </div>, document.body)
}

/** "Amina started a group call · Join" prompt shown on any page. */
export function GroupCallInvite() {
  const group = useGroupCall()
  const [error, setError] = useState('')
  const invite = group.invite
  useEffect(() => {
    if (!invite) return
    const timer = setTimeout(group.dismissInvite, 60_000)
    return () => clearTimeout(timer)
  }, [invite, group.dismissInvite])
  if (!invite || group.phase !== 'idle') return null
  const join = () => { setError(''); group.join(invite.conversation_id, invite.kind).catch((err: Error) => setError(err.message)) }
  return createPortal(<div className="group-invite" role="alertdialog" aria-label="Group call started">
    <div className="group-invite-copy">
      <strong>{invite.started_by.display_name} started a group {invite.kind === 'video' ? 'video' : 'voice'} call</strong>
      {error ? <span className="group-invite-error">{error}</span> : <span>{invite.participants.length} in the call</span>}
    </div>
    <button type="button" className="group-invite-join" onClick={join}>{invite.kind === 'video' ? <Video size={16} /> : <Mic size={16} />} Join</button>
    <button type="button" className="icon-button" onClick={group.dismissInvite} aria-label="Dismiss"><X size={16} /></button>
  </div>, document.body)
}
