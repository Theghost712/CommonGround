/** Reading contacts from the device, a .vcf file, or pasted text. Nothing here is stored. */

type PickedContact = { tel?: string[]; email?: string[] }
type ContactsManager = { select: (properties: string[], options?: { multiple?: boolean }) => Promise<PickedContact[]> }

export type ContactBatch = { phones: string[]; emails: string[] }

/** The Contact Picker API exists only in Chrome on Android, on HTTPS (or localhost). */
export function contactPickerSupported(): boolean {
  return typeof navigator !== 'undefined' && 'contacts' in navigator && typeof window !== 'undefined' && 'ContactsManager' in window && window.isSecureContext
}

export async function pickDeviceContacts(): Promise<ContactBatch> {
  const manager = (navigator as Navigator & { contacts: ContactsManager }).contacts
  const picked = await manager.select(['tel', 'email'], { multiple: true })
  return dedupe({
    phones: picked.flatMap((contact) => contact.tel || []),
    emails: picked.flatMap((contact) => contact.email || []),
  })
}

/** Parse TEL and EMAIL lines from vCard (.vcf) text, including folded lines. */
export function parseVCard(text: string): ContactBatch {
  const unfolded = text.replace(/\r\n|\r/g, '\n').replace(/\n[ \t]/g, '')
  const phones: string[] = []
  const emails: string[] = []
  for (const line of unfolded.split('\n')) {
    const match = /^(?:item\d+\.)?(TEL|EMAIL)\b[^:]*:(.+)$/i.exec(line.trim())
    if (!match) continue
    const value = match[2].replace(/^tel:/i, '').replace(/^mailto:/i, '').trim()
    if (match[1].toUpperCase() === 'TEL') phones.push(value)
    else emails.push(value)
  }
  return dedupe({ phones, emails })
}

/** Split pasted text on commas, semicolons or new lines into phones and emails. */
export function parsePasted(text: string): ContactBatch {
  const parts = text.split(/[\n,;]+/).map((part) => part.trim()).filter(Boolean)
  return dedupe({
    phones: parts.filter((part) => !part.includes('@') && /\d{6,}/.test(part.replace(/\D/g, ''))),
    emails: parts.filter((part) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(part)),
  })
}

function dedupe(batch: ContactBatch): ContactBatch {
  return {
    phones: [...new Set(batch.phones.map((p) => p.trim()).filter(Boolean))],
    emails: [...new Set(batch.emails.map((e) => e.trim().toLowerCase()).filter(Boolean))],
  }
}

export const MAX_CONTACTS_PER_REQUEST = 2000

export function chunk(batch: ContactBatch): ContactBatch[] {
  const items = [...batch.phones.map((v) => ['p', v] as const), ...batch.emails.map((v) => ['e', v] as const)]
  const chunks: ContactBatch[] = []
  for (let i = 0; i < items.length; i += MAX_CONTACTS_PER_REQUEST) {
    const slice = items.slice(i, i + MAX_CONTACTS_PER_REQUEST)
    chunks.push({ phones: slice.filter(([k]) => k === 'p').map(([, v]) => v), emails: slice.filter(([k]) => k === 'e').map(([, v]) => v) })
  }
  return chunks
}
