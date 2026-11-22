import { useEffect, useRef } from 'react'
import { Bold, Italic, Underline, List, ListOrdered, Quote, Heading2, Link2 } from 'lucide-react'

const tools = [
  { label: 'Bold', icon: Bold, command: 'bold' },
  { label: 'Italic', icon: Italic, command: 'italic' },
  { label: 'Underline', icon: Underline, command: 'underline' },
  { label: 'Heading', icon: Heading2, command: 'formatBlock', value: 'h2' },
  { label: 'Bulleted list', icon: List, command: 'insertUnorderedList' },
  { label: 'Numbered list', icon: ListOrdered, command: 'insertOrderedList' },
  { label: 'Quote', icon: Quote, command: 'formatBlock', value: 'blockquote' },
]

export default function RichTextEditor({ value, onChange, placeholder = 'Share your perspective…' }: { value: string; onChange: (html: string) => void; placeholder?: string }) {
  const editorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (editorRef.current && editorRef.current.innerHTML !== value) editorRef.current.innerHTML = value || ''
  }, [value])

  const runCommand = (command: string, commandValue?: string) => {
    editorRef.current?.focus()
    if (command === 'formatBlock') document.execCommand(command, false, `<${commandValue || 'p'}>`)
    else document.execCommand(command, false)
    if (editorRef.current) onChange(editorRef.current.innerHTML)
  }

  const addLink = () => {
    const rawUrl = window.prompt('Enter link URL (https://...)')
    if (!rawUrl) return
    try {
      const url = new URL(rawUrl)
      if (!['http:', 'https:', 'mailto:'].includes(url.protocol)) throw new Error('Unsupported protocol')
      editorRef.current?.focus()
      document.execCommand('createLink', false, url.toString())
      if (editorRef.current) onChange(editorRef.current.innerHTML)
    } catch {
      window.alert('Please enter a valid http, https, or mailto link.')
    }
  }

  return <div className="rich-editor-wrap">
    <div className="rich-editor-toolbar" role="toolbar" aria-label="Text formatting">
      {tools.map(({ label, icon: Icon, command, value: commandValue }) => <button type="button" key={label} title={label} aria-label={label} onMouseDown={(event) => event.preventDefault()} onClick={() => runCommand(command, commandValue)}><Icon size={16} /></button>)}
      <span className="editor-toolbar-divider" />
      <button type="button" title="Add link" aria-label="Add link" onMouseDown={(event) => event.preventDefault()} onClick={addLink}><Link2 size={16} /></button>
    </div>
    <div ref={editorRef} className="rich-editor" contentEditable role="textbox" aria-multiline="true" data-placeholder={placeholder} suppressContentEditableWarning onInput={(event) => onChange(event.currentTarget.innerHTML)} />
  </div>
}
