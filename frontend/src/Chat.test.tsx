import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import ChatScreen from './components/Chat/ChatScreen'
import ChatMessage from './components/Chat/ChatMessage'
import ChatInput from './components/Chat/ChatInput'
import type { ThreadMessage } from './hooks/useChat'

// ── Module mocks ─────────────────────────────────────────────────

// Mock useChat so ChatScreen tests don't depend on localStorage / SSE
const mockSend = vi.fn()
const mockSelectSession = vi.fn()
const mockNewSession = vi.fn()

vi.mock('./hooks/useChat', () => ({
  useChat: () => ({
    thread: [],
    isStreaming: false,
    sessions: [],
    currentSessionId: null,
    send: mockSend,
    selectSession: mockSelectSession,
    newSession: mockNewSession,
  }),
}))

// Mock streamChat so it doesn't open real connections in ChatMessage/useChat tests
vi.mock('./api/chat', () => ({
  streamChat: vi.fn(),
}))

// ── Helpers ──────────────────────────────────────────────────────

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

// ── ChatInput tests ──────────────────────────────────────────────

describe('ChatInput', () => {
  beforeEach(() => {
    mockSend.mockReset()
  })

  it('renders textarea and send button', () => {
    render(<ChatInput onSend={mockSend} />)
    expect(screen.getByTestId('chat-input-textarea')).toBeInTheDocument()
    expect(screen.getByTestId('send-btn')).toBeInTheDocument()
  })

  it('calls onSend on Enter key', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'hello' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(mockSend).toHaveBeenCalledWith('hello', undefined, undefined)
  })

  it('does not call onSend on Shift+Enter', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'hello' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true })
    expect(mockSend).not.toHaveBeenCalled()
  })

  it('calls onSend when send button clicked', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'world' } })
    fireEvent.click(screen.getByTestId('send-btn'))
    expect(mockSend).toHaveBeenCalledWith('world', undefined, undefined)
  })

  it('does not send empty or whitespace-only input', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: '   ' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(mockSend).not.toHaveBeenCalled()
  })

  it('send button is disabled while streaming', () => {
    render(<ChatInput onSend={mockSend} disabled />)
    const btn = screen.getByTestId('send-btn')
    expect(btn).toBeDisabled()
  })

  it('renders voice button when onVoiceClick is provided', () => {
    render(<ChatInput onSend={mockSend} onVoiceClick={vi.fn()} />)
    expect(screen.getByTestId('voice-btn')).toBeInTheDocument()
  })

  it('does not render voice button when onVoiceClick is absent', () => {
    render(<ChatInput onSend={mockSend} />)
    expect(screen.queryByTestId('voice-btn')).toBeNull()
  })

  it('shows URL pills when message contains a URL', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'Check out https://example.com/page' } })
    expect(screen.getByTestId('url-pills')).toBeInTheDocument()
    // The pill should be active (opted-in) by default
    expect(screen.getByTestId('url-pill-active')).toBeInTheDocument()
  })

  it('does not show URL pills when message has no URL', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'just a plain message' } })
    expect(screen.queryByTestId('url-pills')).toBeNull()
  })

  it('shows a pill for each distinct URL', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'https://foo.com and https://bar.com' } })
    expect(screen.getAllByTestId('url-pill-active')).toHaveLength(2)
  })

  it('deduplicates repeated URLs in pills', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'https://example.com https://example.com' } })
    expect(screen.getAllByTestId('url-pill-active')).toHaveLength(1)
  })

  it('clicking an active pill opts it out (dims it)', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'https://example.com' } })
    const pill = screen.getByTestId('url-pill-active')
    fireEvent.click(pill)
    expect(screen.getByTestId('url-pill-opted-out')).toBeInTheDocument()
    expect(screen.queryByTestId('url-pill-active')).toBeNull()
  })

  it('clicking an opted-out pill re-activates it', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'https://example.com' } })
    fireEvent.click(screen.getByTestId('url-pill-active'))
    fireEvent.click(screen.getByTestId('url-pill-opted-out'))
    expect(screen.getByTestId('url-pill-active')).toBeInTheDocument()
  })

  it('Send button passes opted-in URLs as fetchUrls', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'https://example.com' } })
    fireEvent.click(screen.getByTestId('send-btn'))
    expect(mockSend).toHaveBeenCalledWith('https://example.com', undefined, ['https://example.com'])
  })

  it('Enter key passes opted-in URLs as fetchUrls (default-on)', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'Check this https://example.com' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(mockSend).toHaveBeenCalledWith('Check this https://example.com', undefined, ['https://example.com'])
  })

  it('opting out a URL removes it from fetchUrls', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'https://example.com' } })
    fireEvent.click(screen.getByTestId('url-pill-active'))
    fireEvent.click(screen.getByTestId('send-btn'))
    // fetchUrls should be undefined since all URLs opted-out
    expect(mockSend).toHaveBeenCalledWith('https://example.com', undefined, undefined)
  })

  it('opting out one URL in multi-URL message only excludes that URL', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'https://foo.com and https://bar.com' } })
    // Opt out the first pill
    const pills = screen.getAllByTestId('url-pill-active')
    fireEvent.click(pills[0])
    fireEvent.click(screen.getByTestId('send-btn'))
    const call = mockSend.mock.calls[0]
    // fetchUrls should contain only the second URL
    expect(call[2]).toHaveLength(1)
    expect(call[2][0]).toBe('https://bar.com')
  })

  it('no URL in message sends without fetchUrls', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'just text' } })
    fireEvent.click(screen.getByTestId('send-btn'))
    expect(mockSend).toHaveBeenCalledWith('just text', undefined, undefined)
  })
})

// ── ChatInput history navigation tests ───────────────────────────

describe('ChatInput history navigation', () => {
  beforeEach(() => {
    mockSend.mockReset()
  })

  it('ArrowUp with no history has no effect', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea') as HTMLTextAreaElement
    fireEvent.keyDown(textarea, { key: 'ArrowUp' })
    expect(textarea.value).toBe('')
  })

  it('ArrowUp after sending shows the last sent message', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'first message' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(textarea.value).toBe('')
    fireEvent.keyDown(textarea, { key: 'ArrowUp' })
    expect(textarea.value).toBe('first message')
  })

  it('ArrowUp twice shows older message', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'first' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    fireEvent.change(textarea, { target: { value: 'second' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    fireEvent.keyDown(textarea, { key: 'ArrowUp' })
    expect(textarea.value).toBe('second')
    fireEvent.keyDown(textarea, { key: 'ArrowUp' })
    expect(textarea.value).toBe('first')
  })

  it('ArrowUp clamped at oldest entry', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'only' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    fireEvent.keyDown(textarea, { key: 'ArrowUp' })
    fireEvent.keyDown(textarea, { key: 'ArrowUp' })
    expect(textarea.value).toBe('only')
  })

  it('ArrowDown after ArrowUp restores unsent draft', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'sent msg' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    fireEvent.change(textarea, { target: { value: 'my draft' } })
    fireEvent.keyDown(textarea, { key: 'ArrowUp' })
    expect(textarea.value).toBe('sent msg')
    fireEvent.keyDown(textarea, { key: 'ArrowDown' })
    expect(textarea.value).toBe('my draft')
  })

  it('ArrowDown when not browsing history has no effect', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'typing' } })
    fireEvent.keyDown(textarea, { key: 'ArrowDown' })
    expect(textarea.value).toBe('typing')
  })

  it('duplicate consecutive sends are deduplicated in history', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'same' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    fireEvent.change(textarea, { target: { value: 'same' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    // ArrowUp twice should still show 'same' (not navigate past it)
    fireEvent.keyDown(textarea, { key: 'ArrowUp' })
    expect(textarea.value).toBe('same')
    fireEvent.keyDown(textarea, { key: 'ArrowUp' })
    expect(textarea.value).toBe('same')
  })
})

// ── ChatMessage tests ─────────────────────────────────────────────

describe('ChatMessage', () => {
  it('renders user message text', () => {
    const msg: ThreadMessage = { role: 'user', content: 'Hello there' }
    render(<ChatMessage message={msg} />)
    expect(screen.getByText('Hello there')).toBeInTheDocument()
  })

  it('applies user alignment class', () => {
    const msg: ThreadMessage = { role: 'user', content: 'test' }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.chat-message--user')).toBeTruthy()
  })

  it('applies assistant alignment class', () => {
    const msg: ThreadMessage = { role: 'assistant', content: 'response' }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.chat-message--assistant')).toBeTruthy()
  })

  it('renders assistant message with markdown wrapper', () => {
    const msg: ThreadMessage = { role: 'assistant', content: '**bold**' }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.chat-message__markdown')).toBeTruthy()
  })

  it('renders tool call disclosures', () => {
    const msg: ThreadMessage = {
      role: 'assistant',
      content: '',
      toolCalls: [{ name: 'search_vault', resultCount: 4 }],
    }
    const { container } = render(<ChatMessage message={msg} />)
    const tools = container.querySelector('[data-testid="tool-calls"]')
    expect(tools).toBeTruthy()
    expect(tools?.textContent).toContain('search_vault')
    expect(tools?.textContent).toContain('4 results')
  })

  it('renders tool call with singular result count', () => {
    const msg: ThreadMessage = {
      role: 'assistant',
      content: '',
      toolCalls: [{ name: 'read_note', resultCount: 1 }],
    }
    const { container } = render(<ChatMessage message={msg} />)
    const summary = container.querySelector('.tool-call__summary')
    expect(summary?.textContent).toContain('1 result')
  })

  it('renders error tool call with error class', () => {
    const msg: ThreadMessage = {
      role: 'assistant',
      content: '',
      toolCalls: [{ name: 'search_vault', error: 'timeout' }],
    }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.tool-call--error')).toBeTruthy()
  })

  it('renders note created card', () => {
    const msg: ThreadMessage = {
      role: 'assistant',
      content: 'Done',
      noteCreated: { filePath: 'people/alice.md', type: 'person_note' },
    }
    renderWithRouter(<ChatMessage message={msg} />)
    expect(screen.getByTestId('note-card')).toBeInTheDocument()
    expect(screen.getByTestId('note-card').textContent).toContain('alice.md')
  })

  it('click on note card navigates to document browser', () => {
    const msg: ThreadMessage = {
      role: 'assistant',
      content: 'Done',
      noteCreated: { filePath: 'inbox/lucas-gallagher.md', type: 'other' },
    }
    renderWithRouter(<ChatMessage message={msg} />)
    fireEvent.click(screen.getByTestId('note-card'))
    expect(window.location.pathname).toBe('/docs')
  })

  it('vault path in message text becomes a clickable link', () => {
    const msg: ThreadMessage = {
      role: 'assistant',
      content: 'See inbox/lucas-gallagher.md for details.',
    }
    renderWithRouter(<ChatMessage message={msg} />)
    const link = screen.getByRole('button', { name: 'inbox/lucas-gallagher.md' })
    expect(link).toBeInTheDocument()
    fireEvent.click(link)
    expect(window.location.pathname).toBe('/docs')
  })

  it('shows blinking cursor when streaming', () => {
    const msg: ThreadMessage = { role: 'assistant', content: '', isStreaming: true }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.chat-message__cursor')).toBeTruthy()
  })

  it('does not show cursor when not streaming', () => {
    const msg: ThreadMessage = { role: 'assistant', content: 'done', isStreaming: false }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.chat-message__cursor')).toBeFalsy()
  })
})

// ── ChatScreen tests ──────────────────────────────────────────────

describe('ChatScreen', () => {
  beforeEach(() => {
    mockSend.mockReset()
    mockNewSession.mockReset()
    mockSelectSession.mockReset()
  })

  it('renders 6 chat starter tiles when thread is empty', () => {
    renderWithRouter(<ChatScreen />)
    const starters = screen.getAllByTestId('chat-starter')
    expect(starters).toHaveLength(6)
  })

  it('renders session picker', () => {
    renderWithRouter(<ChatScreen />)
    expect(screen.getByTestId('session-picker')).toBeInTheDocument()
  })

  it('renders the chat input', () => {
    renderWithRouter(<ChatScreen />)
    expect(screen.getByTestId('chat-input-textarea')).toBeInTheDocument()
  })

  it('clicking a starter with prompt calls send', () => {
    renderWithRouter(<ChatScreen />)
    // "Open action items" starter sends directly
    const starters = screen.getAllByTestId('chat-starter')
    const actionItemsStarter = starters.find(el => el.textContent?.includes('Open action items'))
    expect(actionItemsStarter).toBeTruthy()
    act(() => { fireEvent.click(actionItemsStarter!) })
    expect(mockSend).toHaveBeenCalledWith('Show me all open action items', 'search_vault')
  })

  it('session picker shows + New session as default option', () => {
    renderWithRouter(<ChatScreen />)
    const picker = screen.getByTestId('session-picker') as HTMLSelectElement
    expect(picker.options[0].text).toBe('+ New session')
  })

  it('selecting + New session calls newSession', () => {
    renderWithRouter(<ChatScreen />)
    const picker = screen.getByTestId('session-picker')
    fireEvent.change(picker, { target: { value: '' } })
    expect(mockNewSession).toHaveBeenCalled()
  })
})
