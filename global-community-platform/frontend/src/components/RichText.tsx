import { Fragment } from 'react'
import { Link } from 'react-router-dom'

// #tag (any language, needs a letter), @username, and http(s) links.
const TOKEN = /(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])|(^|[^\w#&])#((?=[\p{L}\p{N}_]*\p{L})[\p{L}\p{N}_]{2,50})|(^|[^\w@])@([A-Za-z0-9_.+-]{2,150})/gu

/**
 * Plain text with clickable #hashtags, @mentions and links (Instagram doesn't make
 * caption links clickable; we do, safely: new tab, no referrer, no opener).
 */
export default function RichText({ text, className }: { text: string; className?: string }) {
  const parts: React.ReactNode[] = []
  let last = 0
  let key = 0
  for (const match of text.matchAll(TOKEN)) {
    const [whole, url, tagLead, tag, mentionLead, mention] = match
    const start = match.index ?? 0
    const lead = tagLead ?? mentionLead ?? ''
    parts.push(text.slice(last, start + lead.length))
    if (url) parts.push(<a key={key++} href={url} target="_blank" rel="noopener noreferrer nofollow ugc" className="rich-link">{url.replace(/^https?:\/\//, '').slice(0, 60)}{url.length > 68 ? '…' : ''}</a>)
    else if (tag) parts.push(<Link key={key++} to={`/tags/${encodeURIComponent(tag.toLowerCase())}`} className="rich-tag">#{tag}</Link>)
    else if (mention) parts.push(<Link key={key++} to={`/u/${encodeURIComponent(mention.replace(/\.$/, ''))}`} className="rich-mention">@{mention.replace(/\.$/, '')}</Link>, mention.endsWith('.') ? '.' : '')
    last = start + whole.length
  }
  parts.push(text.slice(last))
  return <span className={className}>{parts.map((part, i) => <Fragment key={`t${i}`}>{part}</Fragment>)}</span>
}

const HTML_TOKEN = /(^|[^\w#&])#((?=[\p{L}\p{N}_]*\p{L})[\p{L}\p{N}_]{2,50})|(^|[^\w@])@([A-Za-z0-9_+-]{2,150})/gu

/**
 * Add #hashtag and @mention links inside already-sanitised rich-text HTML. Only plain
 * text nodes are touched (never inside existing links or code). Links carry
 * data-internal so the page can route them without a full reload.
 */
export function linkifyHtml(html: string): string {
  if (typeof DOMParser === 'undefined' || !/[#@]/.test(html)) return html
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html')
  const root = doc.body.firstElementChild as HTMLElement
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  while (walker.nextNode()) {
    const node = walker.currentNode as Text
    if (!node.parentElement?.closest('a,code,pre')) nodes.push(node)
  }
  for (const node of nodes) {
    const text = node.data
    HTML_TOKEN.lastIndex = 0
    if (!HTML_TOKEN.test(text)) continue
    HTML_TOKEN.lastIndex = 0
    const fragment = doc.createDocumentFragment()
    let last = 0
    for (const match of text.matchAll(HTML_TOKEN)) {
      const [whole, tagLead, tag, mentionLead, mention] = match
      const lead = tagLead ?? mentionLead ?? ''
      const start = (match.index ?? 0) + lead.length
      fragment.append(text.slice(last, start))
      const link = doc.createElement('a')
      link.setAttribute('data-internal', 'true')
      if (tag) { link.href = `/tags/${encodeURIComponent(tag.toLowerCase())}`; link.className = 'rich-tag'; link.textContent = `#${tag}` }
      else { link.href = `/u/${encodeURIComponent(mention)}`; link.className = 'rich-mention'; link.textContent = `@${mention}` }
      fragment.append(link)
      last = (match.index ?? 0) + whole.length
    }
    fragment.append(text.slice(last))
    node.replaceWith(fragment)
  }
  return root.innerHTML
}
