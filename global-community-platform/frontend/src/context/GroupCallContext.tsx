import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { API_BASE, api, getAccessToken, getErrorMessage } from '../services/api'
import { useAuth } from './AuthContext'
import { callsSupported, deviceId, mediaError, useCall, type CallKind, type SocketEvent } from './CallContext'

export type GroupParticipant = { id: number; username: string; display_name: string; device_id: string; joined_at: string | null }
export type GroupCallInfo = {
  id: number
  conversation_id: number
  kind: CallKind
  status: 'live' | 'ended'
  started_by: { id: number; username: string; display_name: string }
  created_at: string | null
  participants: GroupParticipant[]
  max_participants: number
}
export type GroupPeer = { userId: number; stream: MediaStream | null; connection: RTCPeerConnectionState | 'new' }
type Signal = { sdp?: RTCSessionDescriptionInit; candidate?: RTCIceCandidateInit }

type GroupCallState = {
  phase: 'idle' | 'joining' | 'active' | 'ended'
  call: GroupCallInfo | null
  message: string
  joinedAt: number | null
  localStream: MediaStream | null
  peers: Record<number, GroupPeer>
  muted: boolean
  cameraOff: boolean
}
type GroupCallValue = GroupCallState & {
  available: boolean
  /** Live group calls in my chats, by conversation id (for "Join" buttons). */
  liveCalls: Record<number, GroupCallInfo>
  /** A call someone just started in one of my chats, shown as a "Join" prompt. */
  invite: GroupCallInfo | null
  join: (conversationId: number, kind: CallKind) => Promise<void>
  leave: () => Promise<void>
  toggleMute: () => void
  toggleCamera: () => void
  dismissInvite: () => void
  dismiss: () => void
}

const HEARTBEAT_MS = 20_000
const idle: GroupCallState = { phase: 'idle', call: null, message: '', joinedAt: null, localStream: null, peers: {}, muted: false, cameraOff: false }

type PeerEntry = { pc: RTCPeerConnection; initiator: boolean; pending: RTCIceCandidateInit[]; retries: number }

const GroupCallContext = createContext<GroupCallValue | null>(null)

export function GroupCallProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const oneToOne = useCall()
  const { sendRaw, subscribe } = oneToOne
  const [state, setState] = useState<GroupCallState>(idle)
  const stateRef = useRef(state)
  stateRef.current = state
  const [liveCalls, setLiveCalls] = useState<Record<number, GroupCallInfo>>({})
  const [invite, setInvite] = useState<GroupCallInfo | null>(null)
  const peers = useRef(new Map<number, PeerEntry>())
  const localRef = useRef<MediaStream | null>(null)
  const iceRef = useRef<RTCIceServer[]>([])
  const heartbeat = useRef<ReturnType<typeof setInterval> | null>(null)
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const available = callsSupported()

  const rememberCall = useCallback((call: GroupCallInfo) => {
    setLiveCalls((current) => {
      const next = { ...current }
      if (call.status === 'live' && call.participants.length) next[call.conversation_id] = call
      else delete next[call.conversation_id]
      return next
    })
  }, [])

  const setPeer = useCallback((userId: number, patch: Partial<GroupPeer> | null) => {
    setState((current) => {
      const peersNow = { ...current.peers }
      if (patch === null) delete peersNow[userId]
      else peersNow[userId] = { ...(peersNow[userId] ?? { userId, stream: null, connection: 'new' }), ...patch }
      return { ...current, peers: peersNow }
    })
  }, [])

  const signal = useCallback((to: number, data: Signal) => {
    const call = stateRef.current.call
    if (call) sendRaw({ type: 'group_signal', group_call_id: call.id, to, data, device_id: deviceId })
  }, [sendRaw])

  const closePeer = useCallback((userId: number) => {
    peers.current.get(userId)?.pc.close()
    peers.current.delete(userId)
    setPeer(userId, null)
  }, [setPeer])

  const cleanup = useCallback(() => {
    if (heartbeat.current) clearInterval(heartbeat.current)
    heartbeat.current = null
    peers.current.forEach((entry) => entry.pc.close())
    peers.current.clear()
    localRef.current?.getTracks().forEach((track) => track.stop())
    localRef.current = null
  }, [])

  const finishLocally = useCallback((message: string) => {
    cleanup()
    setState((current) => ({ ...idle, phase: 'ended', call: current.call, message }))
    if (dismissTimer.current) clearTimeout(dismissTimer.current)
    dismissTimer.current = setTimeout(() => setState((current) => current.phase === 'ended' ? idle : current), 2500)
  }, [cleanup])

  // createPeer retries through this ref (connectTo is defined after it).
  const connectToRef = useRef<(userId: number, initiator: boolean) => void>(() => {})

  const createPeer = useCallback((userId: number, initiator: boolean, retries = 0): PeerEntry => {
    peers.current.get(userId)?.pc.close()
    const pc = new RTCPeerConnection({ iceServers: iceRef.current })
    const entry: PeerEntry = { pc, initiator, pending: [], retries }
    peers.current.set(userId, entry)
    setPeer(userId, { stream: null, connection: 'new' })
    localRef.current?.getTracks().forEach((track) => pc.addTrack(track, localRef.current!))
    pc.onicecandidate = (event) => { if (event.candidate) signal(userId, { candidate: event.candidate.toJSON() }) }
    pc.ontrack = (event) => {
      if (peers.current.get(userId)?.pc !== pc) return
      setPeer(userId, { stream: event.streams[0] ?? new MediaStream([event.track]) })
    }
    pc.onconnectionstatechange = () => {
      if (peers.current.get(userId)?.pc !== pc) return
      setPeer(userId, { connection: pc.connectionState })
      // The side that sent the offer tries again a couple of times (new network path).
      if (pc.connectionState === 'failed' && entry.initiator && entry.retries < 2) {
        setTimeout(() => { if (peers.current.get(userId)?.pc === pc && stateRef.current.phase === 'active') connectToRef.current(userId, true) }, 1500)
      }
    }
    return entry
  }, [setPeer, signal])

  const connectTo = useCallback((userId: number, initiator: boolean) => {
    const retries = (peers.current.get(userId)?.retries ?? -1) + 1
    const entry = createPeer(userId, initiator, initiator ? retries : 0)
    if (initiator) {
      void (async () => {
        try {
          const offer = await entry.pc.createOffer()
          await entry.pc.setLocalDescription(offer)
          signal(userId, { sdp: { type: offer.type, sdp: offer.sdp } })
        } catch { closePeer(userId) }
      })()
    }
  }, [createPeer, signal, closePeer])
  connectToRef.current = connectTo

  const handleSignal = useCallback(async (from: number, data: Signal) => {
    let entry = peers.current.get(from)
    if (data.sdp?.type === 'offer') entry = createPeer(from, false) // they joined after us, or re-dialled
    if (!entry) return
    const { pc } = entry
    try {
      if (data.sdp) {
        await pc.setRemoteDescription(data.sdp)
        for (const candidate of entry.pending.splice(0)) await pc.addIceCandidate(candidate).catch(() => {})
        if (data.sdp.type === 'offer') {
          const answer = await pc.createAnswer()
          await pc.setLocalDescription(answer)
          signal(from, { sdp: { type: answer.type, sdp: answer.sdp } })
        }
      } else if (data.candidate) {
        if (pc.remoteDescription) await pc.addIceCandidate(data.candidate).catch(() => {})
        else entry.pending.push(data.candidate)
      }
    } catch {
      closePeer(from)
    }
  }, [createPeer, signal, closePeer])

  /** Bring connections in line with who the server says is in the call. */
  const reconcile = useCallback((call: GroupCallInfo) => {
    const current = stateRef.current
    if (!current.call || current.call.id !== call.id || current.phase === 'idle' || current.phase === 'ended') return
    if (call.status !== 'live') { finishLocally('Call ended'); return }
    const me = call.participants.find((p) => p.id === user?.id)
    if (!me || me.device_id !== deviceId) { finishLocally(me ? 'You joined from another device' : 'You left the call'); return }
    const present = new Set(call.participants.map((p) => p.id))
    peers.current.forEach((_, userId) => { if (!present.has(userId)) closePeer(userId) })
    setState((s) => ({ ...s, call }))
  }, [user, finishLocally, closePeer])

  const onEvent = useCallback((event: SocketEvent) => {
    if (event.type === 'group_call.signal') {
      if (event.to_device !== deviceId || stateRef.current.phase !== 'active') return
      if (stateRef.current.call?.id !== event.group_call_id) return
      void handleSignal(Number(event.from), event.data as Signal)
      return
    }
    const call = event.call as GroupCallInfo | undefined
    if (!call) return
    rememberCall(call)
    reconcile(call)
    if (event.type === 'group_call.started' && call.started_by.id !== user?.id && stateRef.current.phase === 'idle' && oneToOne.phase === 'idle') setInvite(call)
    setInvite((current) => current && current.id === call.id && (call.status !== 'live' || call.participants.some((p) => p.id === user?.id)) ? null : current)
  }, [handleSignal, rememberCall, reconcile, user, oneToOne.phase])
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => subscribe((event) => onEventRef.current(event)), [subscribe])

  // Which of my chats have a call running right now (on load and every minute).
  useEffect(() => {
    if (!user || !available) return
    let stopped = false
    const load = () => api.get<{ calls: GroupCallInfo[] }>('/calls/group/active/').then(({ data }) => {
      if (stopped) return
      setLiveCalls(Object.fromEntries(data.calls.filter((c) => c.participants.length).map((c) => [c.conversation_id, c])))
    }).catch(() => {})
    void load()
    const timer = setInterval(load, 60_000)
    return () => { stopped = true; clearInterval(timer) }
  }, [user, available])

  const leave = useCallback(async () => {
    const call = stateRef.current.call
    finishLocally('You left the call')
    if (call) {
      const { data } = await api.post<{ call: GroupCallInfo }>(`/calls/group/${call.id}/leave/`, { device_id: deviceId }).catch(() => ({ data: null }))
      if (data?.call) rememberCall(data.call)
    }
  }, [finishLocally, rememberCall])

  const join = useCallback(async (conversationId: number, kind: CallKind) => {
    const phase = stateRef.current.phase
    if ((phase !== 'idle' && phase !== 'ended') || (oneToOne.phase !== 'idle' && oneToOne.phase !== 'ended')) throw new Error("You're already in a call.")
    if (!available) throw new Error("This browser can't make calls.")
    const running = liveCalls[conversationId]
    const wanted: CallKind = running?.kind ?? kind
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: wanted === 'video' ? { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' } : false })
    } catch (err) { throw new Error(mediaError(err, wanted)) }
    localRef.current = stream
    setInvite(null)
    setState({ ...idle, phase: 'joining', localStream: stream })
    try {
      const { data } = await api.post<{ call: GroupCallInfo; ice_servers: RTCIceServer[] }>('/calls/group/', { conversation_id: conversationId, kind: wanted, device_id: deviceId })
      iceRef.current = data.ice_servers
      if (data.call.kind === 'audio') stream.getVideoTracks().forEach((track) => { track.stop(); stream.removeTrack(track) })
      setState((s) => ({ ...s, phase: 'active', call: data.call, joinedAt: Date.now() }))
      stateRef.current = { ...stateRef.current, phase: 'active', call: data.call }
      rememberCall(data.call)
      // We're the newcomer: we call everyone who is already there.
      for (const participant of data.call.participants) if (participant.id !== user?.id) connectTo(participant.id, true)
      heartbeat.current = setInterval(() => {
        const call = stateRef.current.call
        if (!call) return
        api.post<{ call: GroupCallInfo }>(`/calls/group/${call.id}/heartbeat/`, { device_id: deviceId })
          .then(({ data: beat }) => reconcile(beat.call))
          .catch((err) => { if ((err as { response?: { status?: number } })?.response?.status === 410) finishLocally('You left the call') })
      }, HEARTBEAT_MS)
    } catch (err) {
      cleanup()
      setState(idle)
      throw new Error(getErrorMessage(err))
    }
  }, [available, liveCalls, oneToOne.phase, user, rememberCall, reconcile, finishLocally, cleanup, connectTo])

  // Closing the tab: tell the server right away (otherwise the heartbeat timeout does).
  useEffect(() => {
    const onUnload = () => {
      const call = stateRef.current.call
      if (!call || stateRef.current.phase !== 'active') return
      const token = getAccessToken()
      void fetch(`${API_BASE}/calls/group/${call.id}/leave/`, {
        method: 'POST', keepalive: true, credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ device_id: deviceId }),
      }).catch(() => {})
    }
    window.addEventListener('pagehide', onUnload)
    return () => window.removeEventListener('pagehide', onUnload)
  }, [])

  useEffect(() => () => { cleanup(); if (dismissTimer.current) clearTimeout(dismissTimer.current) }, [cleanup])
  // Signing out ends the call.
  useEffect(() => { if (!user && stateRef.current.phase !== 'idle') { cleanup(); setState(idle) } }, [user, cleanup])

  const toggleMute = useCallback(() => {
    const track = localRef.current?.getAudioTracks()[0]
    if (!track) return
    track.enabled = !track.enabled
    setState((current) => ({ ...current, muted: !track.enabled }))
  }, [])
  const toggleCamera = useCallback(() => {
    const track = localRef.current?.getVideoTracks()[0]
    if (!track) return
    track.enabled = !track.enabled
    setState((current) => ({ ...current, cameraOff: !track.enabled }))
  }, [])
  const dismissInvite = useCallback(() => setInvite(null), [])
  const dismiss = useCallback(() => setState((current) => current.phase === 'ended' ? idle : current), [])

  const value = useMemo<GroupCallValue>(() => ({
    ...state, available, liveCalls, invite, join, leave, toggleMute, toggleCamera, dismissInvite, dismiss,
  }), [state, available, liveCalls, invite, join, leave, toggleMute, toggleCamera, dismissInvite, dismiss])
  return <GroupCallContext.Provider value={value}>{children}</GroupCallContext.Provider>
}

export function useGroupCall() {
  const value = useContext(GroupCallContext)
  if (!value) throw new Error('useGroupCall must be used inside GroupCallProvider')
  return value
}
