import { useState } from 'react'
import { Check, Contact, Heart, UserCheck, UserPlus, Users } from 'lucide-react'
import { RELATION_LABELS, initialsOf, useFollow } from '../social/people'
import type { Person } from '../types'
import { getErrorMessage } from '../services/api'

export function Avatar({ person, size = 40 }: { person: Pick<Person, 'display_name' | 'avatar_url'>; size?: number }) {
  const [broken, setBroken] = useState(false)
  const style = { width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.36)) }
  if (person.avatar_url && !broken) return <img className="person-avatar" style={style} src={person.avatar_url} alt="" onError={() => setBroken(true)} />
  return <span className="person-avatar person-avatar-initials" style={style} aria-hidden="true">{initialsOf(person.display_name)}</span>
}

/** Instagram-style: "Follow", "Follow back", or "Following" (hover → "Unfollow"). */
export function FollowButton({ person, compact = false }: { person: Person; compact?: boolean }) {
  const follow = useFollow(person.username)
  const [error, setError] = useState('')
  const relation = person.relationship
  if (!relation || relation.is_self || relation.blocked) return null
  const following = relation.is_following
  const requested = Boolean(relation.requested) && !following
  const engaged = following || requested
  const label = following ? 'Following' : requested ? 'Requested' : relation.follows_you ? 'Follow back' : 'Follow'
  const toggle = () => {
    setError('')
    if (following && !window.confirm(`Unfollow ${person.display_name}?${relation.is_private ? ' You will need to request again to see their posts.' : ''}`)) return
    follow.mutate(!engaged, { onError: (err) => setError(getErrorMessage(err)) })
  }
  const action = following ? 'Unfollow' : requested ? 'Cancel follow request to' : 'Follow'
  return <span className="follow-button-wrap">
    <button type="button" className={`follow-button ${engaged ? 'is-following' : ''} ${requested ? 'is-requested' : ''} ${compact ? 'compact' : ''}`} onClick={toggle} disabled={follow.isPending} aria-pressed={engaged} aria-label={`${action} ${person.display_name}`}>
      {engaged ? <UserCheck size={15} /> : <UserPlus size={15} />}<span>{follow.isPending ? '…' : label}</span>
    </button>
    {error && <span className="follow-error" role="alert">{error}</span>}
  </span>
}

/** Badges explaining how you are connected, e.g. "Mutual", "In your contacts", "Family". */
export function RelationshipChips({ person, showMutualNames = true, omit = [] }: { person: Person; showMutualNames?: boolean; omit?: (string | null)[] }) {
  const relation = person.relationship
  if (!relation || relation.is_self) return null
  const chips: { key: string; text: string; tone: string; icon: typeof Heart }[] = []
  if (relation.label) chips.push({ key: 'label', text: RELATION_LABELS.find((item) => item.value === relation.label)?.label || relation.label, tone: 'label', icon: Heart })
  if (relation.is_mutual) chips.push({ key: 'mutual', text: 'Mutual', tone: 'mutual', icon: Check })
  else if (relation.follows_you) chips.push({ key: 'follows', text: 'Follows you', tone: 'follows', icon: UserCheck })
  if (relation.in_contacts) chips.push({ key: 'contacts', text: 'In your contacts', tone: 'contacts', icon: Contact })
  if (relation.mutual_followers_count > 0) {
    const names = relation.mutual_followers_preview
    const others = relation.mutual_followers_count - names.length
    const text = showMutualNames && names.length
      ? `Followed by ${names.join(', ')}${others > 0 ? ` +${others}` : ''}`
      : `${relation.mutual_followers_count} mutual`
    chips.push({ key: 'mutuals', text, tone: 'neutral', icon: Users })
  }
  const shown = chips.filter((chip) => !omit.includes(chip.text))
  if (!shown.length) return null
  return <div className="relationship-chips">{shown.map(({ key, text, tone, icon: Icon }) => <span key={key} className={`relationship-chip tone-${tone}`}><Icon size={11} />{text}</span>)}</div>
}

export const formatCount = (value: number) => value >= 1_000_000 ? `${(value / 1_000_000).toFixed(1).replace(/\.0$/, '')}M` : value >= 1000 ? `${(value / 1000).toFixed(1).replace(/\.0$/, '')}K` : String(value)
