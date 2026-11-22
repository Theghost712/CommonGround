import type { Person } from '../types'
import { Avatar, FollowButton, RelationshipChips } from './PersonBits'
import UserLink from './UserHoverCard'

/** One person in a list: avatar, name, why they're shown, how you're connected, follow button. */
export default function PersonRow({ person }: { person: Person }) {
  return <article className="person-row">
    <UserLink username={person.username} className="person-row-avatar"><Avatar person={person} size={48} /></UserLink>
    <div className="person-row-copy">
      <UserLink username={person.username} className="person-row-name"><strong>{person.display_name}</strong><span>@{person.username}</span></UserLink>
      {person.reason && <span className="person-row-reason">{person.reason}</span>}
      {!person.reason && person.bio && <span className="person-row-bio">{person.bio}</span>}
      <RelationshipChips person={person} showMutualNames={false} omit={[person.reason]} />
    </div>
    <FollowButton person={person} compact />
  </article>
}
