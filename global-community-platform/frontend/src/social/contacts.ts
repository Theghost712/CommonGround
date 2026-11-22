/**
 * Reading contacts from the phone's contact picker, a .vcf file, or pasted text.
 * Each contact keeps its name, numbers and emails together, so the app can show
 * "Follow" for people already here and "Invite" for everyone else. Nothing here is
 * stored; the server forgets the numbers after matching.
 */

type PickedContact = { name?: string[]; tel?: string[]; email?: string[] }
type ContactsManager = {
  select: (properties: string[], options?: { multiple?: boolean }) => Promise<PickedContact[]>
  getProperties?: () => Promise<string[]>
}

export type Contact = { key: string; name: string; phones: string[]; emails: string[] }

/**
 * The Contact Picker opens the phone's own contact list and the person ticks who to
 * share. Browsers never let a website read contacts silently; this exists only in
 * Chrome on Android, on HTTPS.
 */
export function contactPickerSupported(): boolean {
  return typeof navigator !== 'undefined' && 'contacts' in navigator && typeof window !== 'undefined' && 'ContactsManager' in window && window.isSecureContext
}

let counter = 0
const nextKey = () => `c${Date.now().toString(36)}${(counter++).toString(36)}`

function clean(contact: Omit<Contact, 'key'>): Contact | null {
  const phones = [...new Set(contact.phones.map((p) => p.trim()).filter((p) => /\d{6,}/.test(p.replace(/\D/g, ''))))]
  const emails = [...new Set(contact.emails.map((e) => e.trim().toLowerCase()).filter((e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)))]
  if (!phones.length && !emails.length) return null
  return { key: nextKey(), name: contact.name.trim(), phones, emails }
}

export async function pickDeviceContacts(): Promise<Contact[]> {
  const manager = (navigator as Navigator & { contacts: ContactsManager }).contacts
  const supported = (await manager.getProperties?.()) ?? ['name', 'tel', 'email']
  const wanted = ['name', 'tel', 'email'].filter((p) => supported.includes(p))
  const picked = await manager.select(wanted, { multiple: true })
  return picked.map((c) => clean({ name: c.name?.[0] ?? '', phones: c.tel ?? [], emails: c.email ?? [] })).filter((c): c is Contact => c !== null)
}

/** Parse vCard (.vcf) text into contacts: FN/N for the name, TEL and EMAIL lines. */
export function parseVCard(text: string): Contact[] {
  const unfolded = text.replace(/\r\n|\r/g, '\n').replace(/\n[ \t]/g, '')
  const contacts: Contact[] = []
  let current: Omit<Contact, 'key'> | null = null
  for (const raw of unfolded.split('\n')) {
    const line = raw.trim()
    if (/^BEGIN:VCARD$/i.test(line)) { current = { name: '', phones: [], emails: [] }; continue }
    if (/^END:VCARD$/i.test(line)) { const done = current && clean(current); if (done) contacts.push(done); current = null; continue }
    if (!current) continue
    const match = /^(?:item\d+\.)?(FN|N|TEL|EMAIL)\b[^:]*:(.+)$/i.exec(line)
    if (!match) continue
    const field = match[1].toUpperCase()
    const value = match[2].replace(/^tel:/i, '').replace(/^mailto:/i, '').trim()
    if (field === 'FN') current.name = value
    else if (field === 'N' && !current.name) current.name = value.split(';').filter(Boolean).reverse().join(' ')
    else if (field === 'TEL') current.phones.push(value)
    else if (field === 'EMAIL') current.emails.push(value)
  }
  return contacts
}

/** Each pasted entry (split on commas, semicolons or new lines) becomes one contact. */
export function parsePasted(text: string): Contact[] {
  return text.split(/[\n,;]+/).map((part) => part.trim()).filter(Boolean)
    .map((part) => clean(part.includes('@') ? { name: '', phones: [], emails: [part] } : { name: '', phones: [part], emails: [] }))
    .filter((c): c is Contact => c !== null)
}

export const MAX_CONTACTS_PER_REQUEST = 400

export function chunk(contacts: Contact[], size = MAX_CONTACTS_PER_REQUEST): Contact[][] {
  const parts: Contact[][] = []
  for (let i = 0; i < contacts.length; i += size) parts.push(contacts.slice(i, i + size))
  return parts
}

// ---------------------------------------------------------------- invites

export function inviteLink(username: string, origin = window.location.origin): string {
  return `${origin}/register?invite=${encodeURIComponent(username)}`
}

export function inviteMessage(username: string, name = ''): string {
  const greeting = name ? `Hi ${name.split(' ')[0]}! ` : 'Hi! '
  return `${greeting}I'm on CommonGround, a place for communities and good conversations. Join me: ${inviteLink(username)}`
}

/** Digits with country code for wa.me (local 0712… numbers are treated as Tanzanian). */
export function internationalDigits(phone: string, countryCode = '255'): string {
  const digits = phone.replace(/\D/g, '')
  if (phone.trim().startsWith('+')) return digits
  if (digits.startsWith('00')) return digits.slice(2)
  if (digits.startsWith('0')) return countryCode + digits.slice(1)
  return digits
}

export function whatsappUrl(phone: string, message: string): string {
  return `https://wa.me/${internationalDigits(phone)}?text=${encodeURIComponent(message)}`
}

export function smsUrl(phone: string, message: string): string {
  // "?&body=" works on both Android and iOS.
  return `sms:${phone.replace(/[^\d+]/g, '')}?&body=${encodeURIComponent(message)}`
}

export function emailUrl(email: string, message: string): string {
  return `mailto:${email}?subject=${encodeURIComponent('Join me on CommonGround')}&body=${encodeURIComponent(message)}`
}
