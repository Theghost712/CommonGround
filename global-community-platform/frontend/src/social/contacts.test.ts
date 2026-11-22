import { describe, expect, it } from 'vitest'
import { MAX_CONTACTS_PER_REQUEST, chunk, emailUrl, internationalDigits, inviteLink, inviteMessage, parsePasted, parseVCard, smsUrl, whatsappUrl } from './contacts'

const strip = <T extends { key: string }>(list: T[]) => list.map(({ key: _key, ...rest }) => rest)

describe('parseVCard', () => {
  it('reads one contact per card with name, phones and emails (grouped and folded lines too)', () => {
    const vcf = [
      'BEGIN:VCARD', 'VERSION:3.0', 'FN:Mama Neema',
      'TEL;TYPE=CELL:+255 712 345 678',
      'item1.TEL;type=pref:0754 111 222',
      'EMAIL;TYPE=INTERNET:Neema@Example.com',
      'NOTE:this is a long note that is', ' folded onto the next line',
      'END:VCARD',
      'BEGIN:VCARD', 'N:Juma;Babu;;;', 'TEL:tel:+255-713-000-000', 'TEL;TYPE=CELL:+255-713-000-000', 'END:VCARD',
      'BEGIN:VCARD', 'FN:No Numbers', 'END:VCARD',
    ].join('\r\n')

    expect(strip(parseVCard(vcf))).toEqual([
      { name: 'Mama Neema', phones: ['+255 712 345 678', '0754 111 222'], emails: ['neema@example.com'] },
      { name: 'Babu Juma', phones: ['+255-713-000-000'], emails: [] },
    ])
  })

  it('returns nothing for a file without contacts', () => {
    expect(parseVCard('hello world')).toEqual([])
  })

  it('gives every contact its own key', () => {
    const keys = parseVCard('BEGIN:VCARD\nTEL:0712000111\nEND:VCARD\nBEGIN:VCARD\nTEL:0712000222\nEND:VCARD').map((c) => c.key)
    expect(new Set(keys).size).toBe(2)
  })
})

describe('parsePasted', () => {
  it('makes one contact per entry, ignoring junk', () => {
    expect(strip(parsePasted('0712 345 678, juma@example.com\n+255 754 111 222; nope; 12'))).toEqual([
      { name: '', phones: ['0712 345 678'], emails: [] },
      { name: '', phones: [], emails: ['juma@example.com'] },
      { name: '', phones: ['+255 754 111 222'], emails: [] },
    ])
  })
})

describe('chunk', () => {
  it('keeps every request under the server limit', () => {
    const contacts = parsePasted(Array.from({ length: MAX_CONTACTS_PER_REQUEST + 5 }, (_, i) => `07${String(i).padStart(8, '0')}`).join('\n'))
    const parts = chunk(contacts)
    expect(parts.map((p) => p.length)).toEqual([MAX_CONTACTS_PER_REQUEST, 5])
  })
})

describe('invites', () => {
  it('builds a personal invite link and message', () => {
    expect(inviteLink('Mr.Paulo', 'https://cg.example')).toBe('https://cg.example/register?invite=Mr.Paulo')
    expect(inviteMessage('asha', 'Neema Juma')).toMatch(/^Hi Neema! .*\/register\?invite=asha$/)
  })

  it('turns local numbers into international digits for WhatsApp', () => {
    expect(internationalDigits('0712 345 678')).toBe('255712345678')
    expect(internationalDigits('+254 700 111 222')).toBe('254700111222')
    expect(internationalDigits('00255712345678')).toBe('255712345678')
    expect(whatsappUrl('0712 345 678', 'Join me')).toBe('https://wa.me/255712345678?text=Join%20me')
  })

  it('builds SMS and email links', () => {
    expect(smsUrl('+255 712-345-678', 'Hi there')).toBe('sms:+255712345678?&body=Hi%20there')
    expect(emailUrl('a@b.co', 'Hi')).toBe('mailto:a@b.co?subject=Join%20me%20on%20CommonGround&body=Hi')
  })
})
