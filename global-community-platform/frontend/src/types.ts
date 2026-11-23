export type Discussion = {
  id: number
  community: number | null
  community_name: string | null
  author: number
  author_username: string
  author_display_name?: string
  author_avatar_url?: string
  title: string
  body: string
  content_html: string
  category: string
  comments_count: number
  reactions_count: number
  bookmarks_count: number
  has_reacted: boolean
  my_reaction: 'like' | 'insightful' | 'support' | 'celebrate' | null
  has_bookmarked: boolean
  attachments: DiscussionAttachment[]
  poll?: Poll | null
  created_at: string
  updated_at: string
  /** Set on posts from /promotions/feed/: shown with a "Sponsored" label. */
  sponsored?: boolean
  promotion_id?: number
}

export type PollOption = { id: number; text: string; votes: number | null; percent: number | null }
export type Poll = {
  id: number
  question: string
  allows_multiple: boolean
  closes_at: string | null
  is_closed: boolean
  total_voters: number
  my_votes: number[]
  /** False until you vote (unless you wrote it or it has closed). */
  results_visible: boolean
  options: PollOption[]
}

export type DiscussionAttachment = {
  id: number
  original_name: string
  content_type: string
  size: number
  url: string
  is_image: boolean
  created_at: string
  /** Optimised WebP copies (signed links); empty for files that aren't photos. */
  display_url?: string
  thumb_url?: string
  width?: number | null
  height?: number | null
  color?: string
  alt_text?: string
  /** Video posts: signed stream URL; display/thumb URLs are then the poster frame. */
  is_video?: boolean
  video_url?: string
  duration_ms?: number | null
  /** Server-side video conversion: "pending" while it runs, "failed" if it wasn't a playable video. */
  processing?: '' | 'pending' | 'failed'
}

export type DiscussionCategory = { name: string; count: number }
export type Community = {
  id: number
  name: string
  slug: string
  description: string
  category: string
  visibility: 'public' | 'private' | 'restricted'
  approval_status: 'pending' | 'approved' | 'rejected' | 'suspended'
  logo_url: string
  cover_url: string
  created_by: number
  created_by_username: string
  members_count: number
  pending_requests_count: number | null
  is_member: boolean
  my_role: 'owner' | 'admin' | 'moderator' | 'member' | null
  membership_status: 'active' | 'pending' | 'rejected' | null
  created_at: string
  updated_at: string
}
export type CommunityMember = {
  id: number
  user_id: number
  username: string
  display_name: string
  role: 'owner' | 'admin' | 'moderator' | 'member'
  status: 'active' | 'pending' | 'rejected'
  joined_at: string
  reviewed_at: string | null
}
export type CommunityRule = { id: number; title: string; description: string; position: number; created_at: string; updated_at: string }
export type CommunityAnnouncement = { id: number; title: string; body: string; is_pinned: boolean; posted_by: number; posted_by_username: string; created_at: string; updated_at: string }
export type Comment = { id: number; discussion: number; author: number; author_username: string; parent: number | null; body: string; replies_count: number; replies: Comment[]; created_at: string; updated_at: string }
export type Paginated<T> = { count: number; next: string | null; previous: string | null; results: T[] }

export type EventResponse = 'going' | 'interested' | 'not_going'

export type EventRSVP = {
  id: number
  event: number
  user: number
  username: string
  response: EventResponse
  responded_at: string
}

export type CommunityEvent = {
  id: number
  community: number
  community_name: string
  created_by: number
  created_by_username: string
  title: string
  description: string
  location: string
  starts_at: string
  ends_at: string
  status: 'scheduled' | 'cancelled'
  rsvp_counts: {
    going: number
    interested: number
    not_going: number
  }
  my_response: EventResponse | null
  created_at: string
  updated_at: string
}

export type RelationLabel = 'family' | 'friend' | 'colleague' | 'classmate' | 'neighbour' | 'other'

export type Relationship = {
  is_self: boolean
  is_following: boolean
  follows_you: boolean
  is_mutual: boolean
  in_contacts: boolean
  mutual_followers_count: number
  mutual_followers_preview: string[]
  label: RelationLabel | null
  requested?: boolean
  is_private?: boolean
  can_view?: boolean
  blocked?: boolean
  muted_posts?: boolean
  muted_stories?: boolean
}

export type Person = {
  id: number
  username: string
  first_name: string
  last_name: string
  display_name: string
  avatar_url: string
  bio: string
  country: string
  followers_count: number
  following_count: number
  relationship: Relationship | null
  reason: string | null
}

export type PersonProfile = Person & {
  website: string
  interests: string[]
  date_joined: string
  discussions_count: number
}

export type StoryPerson = Person & {
  latest_post_at: string | null
  latest_discussion_id: number | null
  has_new: boolean
}

export type StoryBackground = 'violet' | 'sunset' | 'ocean' | 'forest' | 'night' | 'rose'

export type Story = {
  id: number
  media_type: 'image' | 'video' | 'text'
  media_url: string
  thumbnail_url: string
  text: string
  background: StoryBackground
  alt_text: string
  duration_ms: number
  audience: 'followers' | 'close_friends'
  processing?: '' | 'pending' | 'failed'
  created_at: string
  expires_at: string
  seen: boolean
  view_count: number | null
  is_own: boolean
}

export type StoryTrayEntry = {
  user: Person
  stories: Story[]
  all_seen: boolean
  latest_at: string
}
