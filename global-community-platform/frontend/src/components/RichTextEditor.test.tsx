import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RichTextEditor from './RichTextEditor'

describe('RichTextEditor', () => {
  let execCommand: ReturnType<typeof vi.fn>

  beforeEach(() => {
    // jsdom does not implement execCommand, so stub it for the toolbar.
    execCommand = vi.fn(() => true)
    Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true })
  })

  it('renders the initial HTML value', () => {
    render(<RichTextEditor value="<p>Hello <strong>world</strong></p>" onChange={vi.fn()} />)

    expect(screen.getByRole('textbox')).toContainHTML('<strong>world</strong>')
  })

  it('reports typed content through onChange', () => {
    const onChange = vi.fn()
    render(<RichTextEditor value="" onChange={onChange} />)
    const editor = screen.getByRole('textbox')

    editor.innerHTML = '<p>Typed</p>'
    fireEvent.input(editor)

    expect(onChange).toHaveBeenCalledWith('<p>Typed</p>')
  })

  it('runs formatting commands from the toolbar', async () => {
    const user = userEvent.setup()
    render(<RichTextEditor value="" onChange={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Bold' }))
    await user.click(screen.getByRole('button', { name: 'Heading' }))

    expect(execCommand).toHaveBeenCalledWith('bold', false)
    expect(execCommand).toHaveBeenCalledWith('formatBlock', false, '<h2>')
  })

  it('inserts safe links', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('https://example.test/page')
    const user = userEvent.setup()
    render(<RichTextEditor value="" onChange={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Add link' }))

    expect(execCommand).toHaveBeenCalledWith('createLink', false, 'https://example.test/page')
  })

  it.each(['javascript:alert(1)', 'not a url', 'data:text/html,hi'])('rejects unsafe link %s', async (url) => {
    vi.spyOn(window, 'prompt').mockReturnValue(url)
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => {})
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<RichTextEditor value="" onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Add link' }))

    expect(execCommand).not.toHaveBeenCalledWith('createLink', expect.anything(), expect.anything())
    expect(onChange).not.toHaveBeenCalled()
    expect(alert).toHaveBeenCalledWith('Please enter a valid http, https, or mailto link.')
  })
})
