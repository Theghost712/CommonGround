import { describe, expect, it } from 'vitest'
import { MAX_CONTACTS_PER_REQUEST, chunk, parsePasted, parseVCard } from './contacts'

describe('parseVCard', () => {
  it('reads phones and emails, including grouped and folded lines', () => {
    const vcf = [
      'BEGIN:VCARD', 'VERSION:3.0', 'FN:Mama Neema',
      'TEL;TYPE=CELL:+255 712 345 678',
      'item1.TEL;type=pref:0754 111 222',
      'EMAIL;TYPE=INTERNET:Neema@Example.com',
      'NOTE:this is a long note that is', ' folded onto the next line',
      'END:VCARD',
      'BEGIN:VCARD', 'FN:Babu', 'TEL:tel:+255-713-000-000', 'TEL;TYPE=CELL:+255 712 345 678', 'END:VCARD',
    ].join('\r\n')

    expect(parseVCard(vcf)).toEqual({
      phones: ['+255 712 345 678', '0754 111 222', '+255-713-000-000'],
      emails: ['neema@example.com'],
    })
  })

  it('returns empty lists for a file without contacts', () => {
    expect(parseVCard('hello world')).toEqual({ phones: [], emails: [] })
  })
})

describe('parsePasted', () => {
  it('splits numbers and emails on commas, semicolons and new lines', () => {
    expect(parsePasted('0712 345 678, juma@example.com\n+255 754 111 222; nope; 12')).toEqual({
      phones: ['0712 345 678', '+255 754 111 222'],
      emails: ['juma@example.com'],
    })
  })
})

describe('chunk', () => {
  it('keeps every request under the server limit', () => {
    const phones = Array.from({ length: MAX_CONTACTS_PER_REQUEST + 5 }, (_, i) => `07${String(i).padStart(8, '0')}`)
    const parts = chunk({ phones, emails: ['a@b.co'] })
    expect(parts).toHaveLength(2)
    expect(parts[0].phones.length + parts[0].emails.length).toBe(MAX_CONTACTS_PER_REQUEST)
    expect(parts[1].phones.length + parts[1].emails.length).toBe(6)
  })
})
